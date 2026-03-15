# Stokowski 工作流深度指南

本文档记录了 Stokowski 工作流的深入理解和常见问题解答。

## 目录

- [Session 模式](#session-模式)
- [State 类型](#state-类型)
- [状态移动机制](#状态移动机制)
- [Prompt 注入时机](#prompt-注入时机)
- [Terminal 状态](#terminal-状态)
- [Bug 修复](#bug-修复)
- [中文 Prompt 文件同步](#中文-prompt-文件同步)

---

## Session 模式

在 `workflow.yaml` 中，每个 agent 状态可以配置 `session` 字段：

```yaml
states:
  investigate:
    session: inherit  # 或 fresh
```

### session: inherit

继承会话 — 代理保留之前所有对话的上下文和记忆。当前状态的代理可以看到之前所有状态的操作历史，继续在同一个会话中工作。

**适用场景**：需要连续性的状态，如 `implement` → `merge`

### session: fresh

全新会话 — 代理从零开始，没有任何之前的上下文。这是一种对抗性审查设计。

**适用场景**：`code-review` — 需要独立客观视角进行代码审查

---

## State 类型

工作流中有三种状态类型：

| 类型 | 含义 | 行为 |
|------|------|------|
| `agent` | 代理执行状态 | 运行 Claude Code 处理任务 |
| `gate` | 人工审查门控 | 暂停等待人类审批或要求修改 |
| `terminal` | 终止状态 | 任务完成，清理工作区 |

### Gate 机制

Gate 状态需要人类在 Linear 中手动操作：

1. Agent 完成前一个状态，发送完成评论
2. Agent 把 Linear issue 移动到 review 状态
3. Stokowski 检测到 gate 状态，停止 agent
4. 人类审批或请求修改：
   - 审批 → 触发 `approve` transition
   - 修改 → 触发 `rework_to` transition

---

## 状态移动机制

### 谁来移动 Linear 状态？

**Agent** 负责移动 Linear 状态，不是 Stokowski。

每个阶段的 prompt（如 `implement.example.md`）都包含指令：

```markdown
2. **Move the Linear issue to "Human Review" state** to trigger the implementation review gate.
```

### 手动干预流程

当 Agent 卡住时，人类可以手动干预：

1. 在 Linear 中把 issue 移动到非 active 状态（如 "Backlog"、"Human Review"）
2. 等待 15-30 秒（polling interval）
3. 再把状态改回 "In Progress"
4. Stokowski 会重新 dispatch

---

## Prompt 注入时机

### 三层 Prompt 结构

每次 Agent turn 开始时，prompt 由三层组成：

```
Layer 1: Global prompt (prompts/global.example.md)
Layer 2: Stage prompt (如 prompts/implement.example.md)
Layer 3: Lifecycle injection (自动生成)
```

### 何时注入

- **每个 turn 开始时**：重新加载并组装 prompt
- **Stage 之间**：当一个 stage 完成，开始下一个 stage 时
- **Turn 之间**：当一个 turn 完成，开始下一个 turn 时

### 实时修改

Stokowski 支持 **hot-reload**：

- 每次 tick（默认 15 秒）重新加载 workflow.yaml
- 每次 assemble_prompt 重新读取 prompt 文件
- **可以在 Agent 运行期间修改 prompt 文件**

### 无法实时注入的情况

Agent 正在执行工具时，无法实时注入新内容。只能在 turn 结束后才能看到新的外部输入。

---

## Terminal 状态

在 `workflow.yaml` 中配置：

```yaml
linear_states:
  terminal:
    - Done
    - Closed
    - Cancelled
    - Canceled
    - Duplicate
```

### 行为完全相同

当 Agent 运行时，手动把 issue 移动到任意 terminal 状态：

| 步骤 | 操作 |
|------|------|
| 1 | 停止 Agent worker |
| 2 | 删除工作区目录 |
| 3 | 从 running/claimed 中移除 |

**所有 terminal 状态行为相同** — 没有区别。

### 唯一区别

当 Agent **正常完成**并 transition 到 terminal 时，会自动移动到 terminal 列表的**第一个状态**（即 "Done"）。

---

## Bug 修复

### Review 状态不释放 Claimed

**问题**：当人类手动把 issue 从 "In Progress" 移动到 "Human Review" 后，再移动到 "Gate Approved"，Stokowski 不会触发 transition。

**原因**：`_reconcile()` 方法在检测到 review 状态时，没有从 `claimed` 集合中移除 issue。

**修复**：在 `orchestrator.py` 第 1085 行添加：

```python
elif state_lower == review_lower:
    # In review/gate state — stop worker but keep gate tracking
    task = self._tasks.get(issue_id)
    if task:
        task.cancel()
    self.running.pop(issue_id, None)
    self._tasks.pop(issue_id, None)
    self.claimed.discard(issue_id)  # 新增
```

---

## 中文 Prompt 文件同步

### 文件列表

| 英文版 | 中文版 |
|--------|--------|
| `prompts/global.example.md` | `prompts/global.example_CN.md` |
| `prompts/investigate.example.md` | `prompts/investigate.example_CN.md` |
| `prompts/implement.example.md` | `prompts/implement.example_CN.md` |
| `prompts/review.example.md` | `prompts/review.example_CN.md` |
| `prompts/merge.example.md` | `prompts/merge.example_CN.md` |

### 主要内容差异

#### Completion Protocol

`implement.example.md` 和 `investigate.example.md` 包含完成协议，告诉 Agent 何时任务完成：

```markdown
## Completion protocol

When the investigation is complete:

1. Post your final `## Investigation` summary as a Linear comment.
2. **STOP** — Your task is complete when the comment is posted.
   Do not continue investigating, do not re-read files.
   The orchestrator will handle the next steps.
```

#### STOP and EXIT 指令

`review.example.md` 和 `merge.example.md` 包含 STOP 指令：

```markdown
7. **STOP and EXIT immediately** after posting the review comment. Do not:
   - Re-check the PR status or re-read your comment
   - Post additional comments or confirmations
   - Verify that the comment was received
   - Wait for responses or human action
```

**注意**：这些指令可能导致 transition 不触发的问题，应谨慎使用。

#### Global Prompt 中的关键规则

`global.example.md` 包含防止无限循环的规则：

```markdown
5. **CRITICAL: Do not loop indefinitely.** When your task is complete (PR created, tests passing, comments posted), you MUST stop and exit. Do not:
   - Check status repeatedly
   - Post "done" comments multiple times
   - Wait for human responses
   - Continue working after posting completion
```

---

## 配置提示

### Prompts 文件位置

Prompts 文件可以放在任意位置，但需要在 `workflow.yaml` 中配置正确路径：

**方法 1：使用绝对路径**

```yaml
prompts:
  global_prompt: C:/Code/clawx_goldie/prompts/global.example_CN.md

states:
  investigate:
    prompt: C:/Code/clawx_goldie/prompts/investigate.example_CN.md
```

**方法 2：把 workflow.yaml 放到 prompts 同目录**

```
C:/Code/clawx_goldie/
├── workflow.yaml
└── prompts/
    ├── global.example_CN.md
    └── ...
```

然后使用相对路径。

### Prompts 在 Git 仓库

Prompts 文件可以放在 git 仓库中，也可以放在本地自定义位置。没有安全风险，除非包含敏感的自定义指令。

---

## 相关文档

- [workflow.example.yaml](../workflow.example.yaml) — 完整的工作流配置示例
- [CLAUDE.md](../CLAUDE.md) — Stokowski 项目架构文档
