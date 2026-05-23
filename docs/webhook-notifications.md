# Webhook Notifications

Stokowski can push gate-event notifications to an external webhook endpoint (e.g. Hermes Agent) so that humans or AI agents are alerted immediately when a gate is entered or escalated. This replaces the cron-based polling pattern with zero-latency push notifications.

---

## How it works

```
Stokowski  →  Agent finishes work  →  Gate entered
                                         │
                                         ▼
                                   HTTP POST (JSON + HMAC signature)
                                         │
                                         ▼
                                   Hermes Webhook  →  Gate Manager skill triggered immediately
```

Two events trigger a webhook notification:

| Event | When |
|-------|------|
| `gate_waiting` | An agent completes work and the issue enters a gate state for human review |
| `gate_escalated` | A gate exceeds its `max_rework` limit and requires human escalation |

---

## Configuration

### Stokowski side (`workflow.yaml`)

Add a `webhook` section at the top level (or per project in multi-project mode):

```yaml
webhook:
  url: "http://127.0.0.1:8644/webhooks/stokowski-gate"
  secret: "$STOKOWSKI_WEBHOOK_SECRET"
  enabled: true
  timeout_seconds: 10
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | `""` | Full webhook endpoint URL. Supports `$VAR` env references. |
| `secret` | string | `""` | HMAC-SHA256 shared secret. Supports `$VAR` env references. |
| `enabled` | bool | `true` | Master switch. Set `false` to disable without removing the block. |
| `timeout_seconds` | int | `10` | HTTP request timeout in seconds. |

When `url` is empty or `enabled` is `false`, webhook notifications are silently skipped — no errors, no logs.

### Environment variables

The `secret` field supports `$VAR` references. Define the shared secret in your `.env` file:

```bash
STOKOWSKI_WEBHOOK_SECRET=your-shared-secret-here
```

Stokowski loads `.env` from the working directory on startup. Both sides (Stokowski and the webhook receiver) must use the same secret.

---

## Hermes Agent side (`config.yaml`)

Hermes already has a built-in webhook platform. Configure a route to receive Stokowski gate events:

```yaml
platforms:
  webhook:
    enabled: true
    extra:
      host: "127.0.0.1"
      port: 8644
      routes:
        stokowski-gate:
          events: ["gate_waiting", "gate_escalated"]
          secret: "${STOKOWSKI_WEBHOOK_SECRET}"
          prompt: |
            ## Stokowski Gate Review Required

            **Issue:** {issue.identifier}
            **Title:** {issue.title}
            **Gate:** {gate_state}
            **Status:** {gate_status}
            **Run:** {run}

            {issue.description}

            Linear: {issue.url}

            Please review this issue immediately.
          skills: ["devops/stokowski-gate-manager"]
          deliver: telegram
          deliver_extra:
            chat_id: "-100xxxxxxxxxx"
            thread_id: "1"
```

No code changes needed on the Hermes side — the webhook platform handles HMAC validation, event filtering, prompt rendering, and skill loading out of the box.

For a lighter-weight notification without AI processing, add `deliver_only: true` to the route. The rendered prompt template is delivered directly to the target (Telegram, Discord, etc.) with zero LLM cost.

---

## Payload format

Stokowski sends a JSON payload via `POST` with `Content-Type: application/json` and `X-Webhook-Signature` header containing the HMAC-SHA256 hex digest of the request body.

### `gate_waiting`

```json
{
  "event_type": "gate_waiting",
  "issue": {
    "id": "uuid",
    "identifier": "PROJ-42",
    "title": "Implement feature X",
    "description": "...",
    "url": "https://linear.app/issue/PROJ-42"
  },
  "gate_state": "research-review",
  "gate_status": "waiting",
  "run": 1,
  "timestamp": "2026-05-23T14:30:00+00:00"
}
```

### `gate_escalated`

```json
{
  "event_type": "gate_escalated",
  "issue": {
    "id": "uuid",
    "identifier": "PROJ-42",
    "title": "Implement feature X",
    "description": "...",
    "url": "https://linear.app/issue/PROJ-42"
  },
  "gate_state": "implementation-review",
  "gate_status": "escalated",
  "run": 6,
  "max_rework": 5,
  "timestamp": "2026-05-23T14:30:00+00:00"
}
```

---

## Security

- **HMAC-SHA256** signature via `X-Webhook-Signature` header — the receiver validates before processing
- Both sides must share the same secret (configured via env var)
- Bind to `127.0.0.1` to only accept local connections — not exposed to the network
- Hermes refuses `INSECURE_NO_AUTH` on non-loopback binds as a safety rail

---

## Error handling

Webhook notifications are non-blocking:

- HTTP errors (network failure, timeout, non-2xx response) are logged as warnings
- The main Stokowski flow (gate entry, state transitions) continues regardless
- Retries are not attempted — the next gate event will trigger a fresh notification
- Cron-based polling (if configured) serves as a fallback to catch any missed notifications

---

## Testing

### Verify the Hermes webhook is listening

```bash
curl http://127.0.0.1:8644/health
# {"status": "ok", "platform": "webhook"}
```

### Send a manual test payload

```bash
SECRET="your-shared-secret"
BODY='{"event_type":"gate_waiting","issue":{"identifier":"TEST-1","title":"Test issue","description":"Test","url":"https://linear.app/issue/TEST-1"},"gate_state":"research-review","gate_status":"waiting","run":1}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)

curl -X POST http://127.0.0.1:8644/webhooks/stokowski-gate \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: $SIG" \
  -d "$BODY"
```

Expected response: `{"status": "accepted", "route": "stokowski-gate", "event": "gate_waiting", ...}` with HTTP 202.

---

## Multi-project setups

In multi-project mode, `webhook` can be set at the top level (inherited by all projects) or per project:

```yaml
# Top-level default
webhook:
  url: "http://127.0.0.1:8644/webhooks/stokowski-gate"
  secret: "$STOKOWSKI_WEBHOOK_SECRET"

projects:
  - name: project-a
    # Inherits top-level webhook
    ...

  - name: project-b
    webhook:
      url: "http://127.0.0.1:8644/webhooks/project-b-gate"
      secret: "$PROJECT_B_WEBHOOK_SECRET"
    # Uses its own webhook endpoint
    ...
```
