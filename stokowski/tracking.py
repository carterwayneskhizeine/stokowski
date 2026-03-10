"""Pipeline stage tracking via structured Linear comments."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("stokowski.tracking")

# Pattern to match our structured tracking comments
STAGE_PATTERN = re.compile(r"<!-- stokowski:stage ({.*?}) -->")
GATE_PATTERN = re.compile(r"<!-- stokowski:gate ({.*?}) -->")


def make_stage_comment(
    stage: str,
    index: int,
    total: int,
    pipeline_run: int = 1,
) -> str:
    """Build a structured stage-tracking comment."""
    payload = {
        "stage": stage,
        "index": index,
        "pipeline_run": pipeline_run,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    machine = f"<!-- stokowski:stage {json.dumps(payload)} -->"
    human = (
        f"**[Stokowski]** Starting stage: **{stage}** "
        f"(stage {index + 1} of {total}, run {pipeline_run})"
    )
    return f"{machine}\n\n{human}"


def make_gate_comment(
    gate_name: str,
    status: str,
    prompt: str = "",
    rework_to: str | None = None,
    pipeline_run: int = 1,
) -> str:
    """Build a structured gate-tracking comment."""
    payload: dict[str, Any] = {
        "gate": gate_name,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if rework_to:
        payload["rework_to"] = rework_to
    if pipeline_run > 1:
        payload["pipeline_run"] = pipeline_run

    machine = f"<!-- stokowski:gate {json.dumps(payload)} -->"

    if status == "waiting":
        human = f"**[Stokowski]** Awaiting human gate: **{gate_name}**"
        if prompt:
            human += f" — {prompt}"
    elif status == "approved":
        human = f"**[Stokowski]** Gate **{gate_name}** approved. Advancing pipeline."
    elif status == "rework":
        human = (
            f"**[Stokowski]** Gate **{gate_name}** requested rework. "
            f"Returning to stage: **{rework_to}**"
        )
        if pipeline_run > 1:
            human += f" (pipeline run {pipeline_run})"
    else:
        human = f"**[Stokowski]** Gate **{gate_name}** status: {status}"

    return f"{machine}\n\n{human}"


def parse_latest_tracking(comments: list[dict]) -> dict[str, Any] | None:
    """Parse comments (oldest-first) to find the latest stage or gate tracking entry.

    Returns a dict with keys:
        - "type": "stage" or "gate"
        - Plus all fields from the JSON payload (stage, index, pipeline_run, etc.)

    Returns None if no tracking comments found.
    """
    latest: dict[str, Any] | None = None

    for comment in comments:
        body = comment.get("body", "")

        stage_match = STAGE_PATTERN.search(body)
        if stage_match:
            try:
                data = json.loads(stage_match.group(1))
                data["type"] = "stage"
                latest = data
            except json.JSONDecodeError:
                pass

        gate_match = GATE_PATTERN.search(body)
        if gate_match:
            try:
                data = json.loads(gate_match.group(1))
                data["type"] = "gate"
                latest = data
            except json.JSONDecodeError:
                pass

    return latest


def resolve_stage_index(pipeline_stages: list[str], stage_name: str) -> int | None:
    """Find the index of a stage in the pipeline. Returns None if not found."""
    for i, s in enumerate(pipeline_stages):
        if s == stage_name or s == f"gate:{stage_name}":
            return i
    return None
