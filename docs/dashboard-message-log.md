# Dashboard Message Log 功能增强

本文档记录了 2026-03-14 对 Stokowski Dashboard 进行的增强，实现了完整的 Agent 输出日志保留和展示功能。

## 改动概述

之前的 Dashboard 只显示实时的动态输出，刷新页面后所有日志都会丢失。增强后的版本会将完整的 Agent 运行历史保留在页面中，并支持展开查看详细的对话内容。

## 技术实现

### 1. 数据模型变更

**文件**: `stokowski/models.py`

```python
@dataclass
class RunAttempt:
    # ... 原有字段 ...
    message_log: list[dict] = field(default_factory=list)  # 新增：完整事件历史
```

`message_log` 是一个事件列表，每条记录包含：
- `type`: 事件类型 (`assistant`, `tool_use`, `tool_result`, `result`)
- `text` / `tool` / `summary`: 事件内容

### 2. Runner 事件捕获

**文件**: `stokowski/runner.py` - `_process_event()` 函数

在每次处理 NDJSON 事件时，将事件追加到 `attempt.message_log`：

```python
# assistant 事件 - 保存 AI 回复文本
if event_type == "assistant":
    text = extract_text_from_content(event.get("message", {}).get("content", ""))
    log_entry = {"type": "assistant", "text": text[:2000]}

# tool_use 事件 - 保存工具调用信息
elif event_type == "tool_use":
    tool_name = event.get("name", "")
    summary = extract_tool_summary(tool_name, event.get("input", {}))
    log_entry = {"type": "tool_use", "tool": tool_name, "summary": summary[:500]}

# tool_result 事件 - 保存工具执行结果
elif event_type == "tool_result":
    text = extract_text_from_content(event.get("content", ""))
    log_entry = {"type": "tool_result", "text": text[:2000]}

# result 事件 - 保存最终结果
elif event_type == "result":
    result_text = event.get("result", "")
    log_entry = {"type": "result", "text": result_text[:2000]}
```

**限制策略**:
- 单条文本内容最长 2000 字符
- 工具摘要最长 500 字符
- 整个日志最多 500 条记录，超出后保留最新的 400 条

### 3. Orchestrator 历史管理

**文件**: `stokowski/orchestrator.py`

新增 `completed_runs` 列表保存已完成运行的历史：

```python
self.completed_runs: list[dict] = []  # capped at 50
```

Worker 退出时（`_on_worker_exit()`）将完整运行记录保存到历史：

```python
self.completed_runs.append({
    "issue_id": attempt.issue_id,
    "issue_identifier": attempt.issue_identifier,
    "status": attempt.status,
    "state_name": attempt.state_name,
    "turn_count": attempt.turn_count,
    "tokens": {...},
    "started_at": ...,
    "completed_at": ...,
    "error": attempt.error,
    "message_log": attempt.message_log,  # 完整的日志历史
})
```

**限制策略**: 最多保留 50 条已完成运行记录，超出后自动清理最早的记录。

### 4. API 端点扩展

**文件**: `stokowski/orchestrator.py` - `get_state_snapshot()`

```python
{
    "running": [
        {
            # ... 原有字段 ...
            "message_log": r.message_log,  # 新增：当前运行的日志
        }
    ],
    "completed": self.completed_runs,  # 新增：已完成运行列表
    "totals": {...}
}
```

### 5. Dashboard 前端重写

**文件**: `stokowski/web.py` - `HTML` 常量

#### 5.1 Agent 卡片可展开

每个运行中的 Agent 卡片现在可以展开/折叠：

```javascript
// 点击卡片切换展开状态
card.addEventListener('click', () => {
    card.classList.toggle('expanded');
    // 展开时自动滚动到底部
    if (card.classList.contains('expanded')) {
        log.scrollTop = log.scrollHeight;
    }
});
```

#### 5.2 日志分类渲染

不同类型的事件使用不同的样式渲染：

| 事件类型 | 样式 |
|---------|------|
| `assistant` | 白色文本，普通段落 |
| `tool_use` | 蓝/紫色背景 + 工具名 + 摘要（Bash 命令、文件路径等） |
| `tool_result` | 灰色背景，左边框，带滚动区域 |
| `result` | 绿色文本，标题样式 |
| 错误 | 红色文本 |

#### 5.3 Completed Runs 区域

页面底部新增 "Completed Runs" 区域：

- 显示已完成的所有 agent 运行（最多 50 条）
- 按完成时间倒序排列（最新的在最前）
- 每个已完成运行同样可展开查看完整日志
- 包含状态、耗时、token 统计等信息

#### 5.4 展开状态持久化

- 展开/折叠状态在页面刷新时保持不变
- 展开日志时自动滚动到最新内容

## 使用方式

1. 启动 Stokowski（带或不带 Dashboard）：

```bash
stokowski --port 4200
```

2. 打开浏览器访问 `http://localhost:4200`

3. 查看 Running Agents:
   - 每个 Agent 卡片下方显示简要状态
   - 点击卡片展开查看完整的对话日志

4. 查看 Completed Runs:
   - 页面底部显示已完成运行的列表
   - 包含完整的状态转换、token 消耗、日志历史

## 数据流

```
Claude Code (stream-json)
    ↓ NDJSON events
runner._process_event()
    ↓ append to attempt.message_log
orchestrator._on_worker_exit()
    ↓ save to completed_runs (with message_log)
orchestrator.get_state_snapshot()
    ↓ include in API response
web.py GET /api/v1/state
    ↓ JSON response
Dashboard JavaScript
    ↓ render with expandable logs
Browser DOM
```

## 兼容性

- 完全向后兼容，不影响现有 API
- 旧版 Dashboard（无 message_log 字段）仍可正常工作
- `message_log` 字段为可选，新启动的 orchestrator 会自动包含

## 性能考虑

- 单个运行的日志限制：500 条
- 已完成运行保留数量：50 条
- 日志内容截断策略避免内存膨胀
- Dashboard 轮询频率保持 3 秒一次

## 后续优化方向

1. **日志搜索**: 在展开的日志中支持关键词搜索
2. **日志下载**: 导出完整日志为 JSON 文件
3. **分页加载**: Completed Runs 数量增多时使用分页
4. **日志过滤**: 按状态、issue、日期筛选

---

## Bug Fix: JavaScript 语法错误 (2026-03-14)

### 问题描述

Dashboard 页面加载后显示 "—" 且无任何数据，浏览器控制台报错：
```
(索引):683 Uncaught SyntaxError: Unexpected string
```

### 根因分析

在 `stokowski/web.py` 中，HTML 模板使用 Python 三引号字符串。当中的 JavaScript `onclick` 事件处理：

```python
# 原始代码（错误）
'<div class="agent-header" onclick="toggleLog(\'' + cardId + '\')">' +
```

Python 三引号字符串会将 `\'` 处理为单个 `'`，导致渲染出的 HTML 变成：

```html
<div class="agent-header" onclick="toggleLog('' + cardId + '')">
```

两个相邻的单引号字符串 → JavaScript 语法错误。

### 修复方案

使用 `\\'` 转义，让 Python 输出字面的 `\'`：

```python
# 修复后
'<div class="agent-header" onclick="toggleLog(\\'' + cardId + '\\')">' +
```

渲染后 HTML 正确：

```html
<div class="agent-header" onclick="toggleLog(\'' + cardId + '\')">
```

### 经验教训

在 Python 多行字符串中嵌入 JavaScript 时，必须用双反斜杠 `\\` 来输出单反斜杠 `\'`。
