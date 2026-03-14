# Gate Transition Fixes

修复自动状态转换不可靠及手动 Gate Approved 无法触发正确流程的问题。

---

## 问题描述

在实际使用中，Stokowski 的 gate 自动状态转换存在以下两个问题：

### 问题1：手动 Gate Approved 无法恢复流程

当用户在 agent 仍在运行续集 turn 时手动将 issue 移到 "Gate Approved"，会导致：

1. `_reconcile` 检测到 issue 离开 active 状态（In Progress），取消 worker task
2. `attempt.status` 变为 `"canceled"`，`_on_worker_exit` 不触发状态转换
3. `_handle_gate_responses` 尝试找到待处理的 gate，但查找逻辑过于严格：
   - 先查内存中的 `_pending_gates`（已被清空）
   - 再查 Linear 评论中 `status: "waiting"` 的 gate 评论（不存在或上一个 gate 已是 "approved"）
4. 两种查找均失败 → `gate_state = None` → 什么都不做
5. Issue 卡在 "Gate Approved"，整个流程中断

### 问题2：续集 turn 过多导致用户提前干预

`_run_worker` 的多轮循环（`max_turns` 最多 30 轮）在 agent 完成工作后仍持续发送通用续集 prompt：

```
"Continue working on CLA-14. Check your progress and continue the task."
```

Agent 只能重复检查并确认已完成，用户看到 issue 长时间停留在 "In Progress" 后手动干预，进而触发上述问题1。

---

## 修复内容

### 1. `orchestrator.py` — 新增 `_infer_pending_gate` 方法

在 `_handle_gate_responses` 之前增加一个推断方法，当标准查找失败时作为 fallback：

**推断逻辑（优先级从高到低）：**

1. 检查 `_issue_current_state[issue.id]`：
   - 若当前已是 gate 状态 → 直接使用
   - 若是 agent 状态 → 查找其 `complete` 转换目标是否为 gate
2. 检查 Linear 最新的 state 追踪评论（`<!-- stokowski:state {...} -->`）：
   - 读取评论中记录的最后一个 agent 状态
   - 查找该状态的 `complete` 转换目标是否为 gate

**示例：** issue 最后一条追踪评论为 `implement` 状态，`implement.transitions.complete = "implementation-review"`（gate 类型），则推断待处理 gate 为 `implementation-review`。

### 2. `orchestrator.py` — `_handle_gate_responses` 使用 fallback

在 approved 和 rework 两个处理分支中，标准查找失败后调用 `_infer_pending_gate`：

```python
if not gate_state:
    gate_state = self._infer_pending_gate(issue, tracking)
```

### 3. `orchestrator.py` — 改进续集 prompt

从：
```
"Continue working on {identifier}. The issue is still in '{state}' state.
Check your progress and continue the task."
```

改为：
```
"Continue working on {identifier} if there is remaining work.
The issue is in '{state}' state.
If all tasks for this stage are already complete, post a brief completion
summary to the Linear issue and stop — do not repeat work already done."
```

### 4. `prompt.py` — lifecycle `### When Done` 明确化

在每个 agent turn 的 lifecycle 注入部分，明确告知 agent 不要手动触发状态转换：

```markdown
### When Done

When you have completed your work for this stage:

1. Post a summary comment on the Linear issue (see global instructions for how).
2. **Do NOT** change the Linear issue state or try to move to the next stage —
   Stokowski handles all state transitions automatically when you finish.
3. Simply complete your final response and stop.
```

### 5. `prompts/global.example.md` — 新增 Linear 评论发布方法

在 global prompt 中增加用 Python stdlib 发布 Linear 评论的具体方法，包含 `{{ issue_id }}` 模板变量（由 Stokowski 自动替换为真实 UUID）。Agent 不再因不知道如何调用 API 而跳过评论发布步骤。

---

## 影响范围

| 文件 | 变更类型 |
|------|----------|
| `stokowski/orchestrator.py` | 新增方法、修改 gate 查找逻辑、修改续集 prompt |
| `stokowski/prompt.py` | 修改 lifecycle 注入内容 |
| `C:\Code\clawx_goldie\prompts\global.example.md` | 新增 Linear 评论发布指南 |

---

## 重新安装

修改后需重新安装才能生效：

```bash
conda activate stokowski
cd D:\Code\stokowski
pip install -e ".[web]"
```

然后重启 Stokowski daemon。
