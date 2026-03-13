# Stokowski

[OpenAI Symphony](https://github.com/openai/symphony) 的 Claude Code 版本。通过 Linear issues 协调 Claude Code 智能体。

本文档是贡献者的唯一权威参考，涵盖架构、设计决策、关键行为以及如何参与开发。

---

## 功能概述

Stokowski 是一个长期运行的 Python 守护进程，能够：

1. 轮询 Linear 中配置的活动状态 issues
2. 为每个 issue 创建独立的 git 克隆工作区
3. 在该工作区中启动 Claude Code（`claude -p`）
4. 通过 `--resume <session_id>` 管理多轮会话
5. 使用指数退避重试失败
6. 根据 Linear 状态变化协调运行中的智能体
7. 暴露实时 Web 仪表板和终端 UI

智能体提示、运行时配置和工作区设置都位于操作员的 `workflow.yaml` 中 — 而非本代码库。

---

## 包结构

```
stokowski/
  config.py        workflow.yaml 解析器 + 类型化配置数据类
  linear.py        Linear GraphQL 客户端（httpx 异步）
  models.py        领域模型：Issue、RunAttempt、RetryEntry
  orchestrator.py  主轮询循环、调度、协调、重试
  prompt.py        状态机工作流的三层提示组装
  runner.py        Claude Code CLI 集成、stream-json 解析器
  tracking.py      通过结构化 Linear 评论进行状态机跟踪
  workspace.py     每个 issue 的工作区生命周期和钩子
  web.py           可选的 FastAPI 仪表板
  main.py          CLI 入口、键盘处理器
  __main__.py      支持 python -m stokowski
```

---

## 关键设计决策

### 使用 Claude Code CLI 而非 Codex app-server
Symphony 使用 Codex 的 JSON-RPC `app-server` 协议通过 stdio 通信。Stokowski 使用 Claude Code 的 CLI：
- 首轮：`claude -p "<prompt>" --output-format stream-json --verbose`
- 继续：`claude -p "<prompt>" --resume <session_id> --output-format stream-json --verbose`

`--verbose` 是 `stream-json` 工作的必要参数。`session_id` 从 NDJSON 流中的 `result` 事件提取。

### 使用 Python + asyncio 而非 Elixir/OTP
更简单的运维方案 — 单进程、无 BEAM 运行时、无分布式问题。通过 `asyncio.create_task` 实现并发。每个智能体轮次都是一个通过 `asyncio.create_subprocess_exec` 启动的子进程。

### 无持久化数据库
所有状态都保存在内存中。协调器通过重新轮询 Linear 并重新发现活动 issues 来从重启中恢复。磁盘上的工作区目录作为持久化状态。

### workflow.yaml 作为操作员契约
操作员的 `workflow.yaml` 定义了运行时配置和状态机。Stokowski 在每次轮询时重新解析它 — 配置更改无需重启即可生效。支持 `.yaml` 和遗留的 `.md`（YAML 头 + Jinja2 正文）格式。提示模板现在是从配置中通过路径引用的独立 `.md` 文件。

### 状态机工作流
每个工作流定义了一组映射到 Linear 状态的内部状态。状态有类型：`agent`（运行 Claude Code）、`gate`（等待人工审核）或 `terminal`（issue 完成）。状态之间的转换在配置中显式声明。

**三层提示组装：** 每次智能体轮次的提示由三层拼接而成：
1. **全局提示** — 从 `.md` 文件加载的共享上下文（通过 `prompts.global_prompt` 引用）
2. **阶段提示** — 从状态的 `prompt` 路径加载的状态特定指令
3. **生命周期注入** — 自动生成的部分，包含 issue 元数据、转换、重构上下文和最近评论

**Gate 协议：** 当智能体完成一个转换到 gate 的状态时，Stokowski 将 issue 移动到 gate 的 Linear 状态并发布结构化跟踪评论。人类通过 Linear 状态变化批准或请求重构。批准后，Stokowski 推进到 gate 的 `approve` 转换目标。重构时，它返回 gate 的 `rework_to` 状态。

**结构化评论跟踪：** 状态转换和 gate 决策以 HTML 评论形式持久化在 Linear issues 上（`<!-- stokowski:state {...} -->` 和 `<!-- stokowski:gate {...} -->`）。这些支持崩溃恢复，并为重构运行提供上下文。

### 工作区隔离
每个 issue 在 `workspace.root` 下有自己的目录。智能体在设置 `cwd` 为该目录的情况下运行。工作区在同一次会话的多轮中保持持久化；当 issue 达到终止状态时删除。

### 无头系统提示
每次首轮启动都会通过 `--append-system-prompt` 追加一个系统提示，指示 Claude 不使用交互式技能、斜杠命令或计划模式。这防止智能体在交互式工作流上卡住。

---

## 组件详解

### config.py
将 `workflow.yaml`（或遗留的带 front matter 的 `.md`）解析为类型化数据类：

- `TrackerConfig` — Linear 端点、API 密钥、项目 slug
- `PollingConfig` — 轮询间隔
- `WorkspaceConfig` — 根路径（支持 `~` 和 `$VAR` 展开）
- `HooksConfig` — 生命周期事件的 shell 脚本 + 超时（包括 `on_stage_enter`）
- `ClaudeConfig` — 命令、权限模式、模型、超时、系统提示
- `AgentConfig` — 并发限制（全局 + 按状态）
- `ServerConfig` — 可选 Web 仪表板端口
- `LinearStatesConfig` — 将逻辑状态名（`active`、`review`、`gate_approved`、`rework`、`terminal`）映射到实际的 Linear 状态名
- `PromptsConfig` — 全局提示文件引用
- `StateConfig` — 状态机中的单个状态：类型、提示路径、linear_state 键、运行器、会话模式、转换、按状态覆盖（model、max_turns、timeouts、hooks）、gate 特定字段（rework_to、max_rework）

`ServiceConfig` 提供辅助方法：`entry_state`（首个智能体状态）、`active_linear_states()`、`gate_linear_states()`、`terminal_linear_states()`。

`merge_state_config(state, root_claude, root_hooks)` 合并按状态覆盖与根默认值 — 仅覆盖指定的字段。返回 `(ClaudeConfig, HooksConfig)`。

`parse_workflow_file()` 通过文件扩展名检测格式：`.yaml`/`.yml` 文件解析为纯 YAML；`.md` 文件通过 `---` 分隔符分割为 front matter + 正文。

`validate_config()` 检查状态机完整性：所有转换指向已存在状态、gate 有 `rework_to` 和 `approve` 转换、至少存在一个智能体和一个终止状态、对不可达状态发出警告。

`ServiceConfig.resolved_api_key()` 按优先级顺序解析密钥：
1. YAML 中的字面值
2. 从环境解析的 `$VAR` 引用
3. `LINEAR_API_KEY` 环境变量作为后备

### linear.py
基于 httpx 的异步 GraphQL 客户端。三个查询：

- `fetch_candidate_issues()` — 分页获取活动状态中的所有 issues，包含完整详情（标签、阻塞者、分支名）
- `fetch_issue_states_by_ids()` — 轻量级协调查询，返回 `{id: state_name}`
- `fetch_issues_by_states()` — 启动清理时使用，返回最小的 Issue 对象

注意：协调查询使用 `issues(filter: { id: { in: $ids } })` — 而非 Linear API 中不存在的 `nodes(ids:)`。

### models.py
三个数据类：

- `Issue` — 标准化的 Linear issue。即使是最小化获取也需要 `title`（使用 `title=""`）。
- `RunAttempt` — 每个 issue 的运行时状态：session_id、轮次计数、token 使用量、状态、最后消息
- `RetryEntry` — 重试队列条目，包含到期时间和错误

### orchestrator.py
主循环。`start()` 运行直到调用 `stop()`：

```
while running:
    _tick()          # 协调 → 获取 → 调度
    sleep(interval)  # 通过 asyncio.Event 可中断
```

**调度逻辑：**
1. Issues 按优先级排序（越小 = 越高），然后按 created_at，然后按 identifier
2. `_is_eligible()` 检查：有效字段、活动状态、未运行/未被认领、阻塞已解决
3. 按状态并发限制与 `max_concurrent_agents_by_state` 比较
4. `_dispatch()` 创建 `RunAttempt`，添加到 `self.running`，生成 `_run_worker` 任务

**协调：** 每次轮询获取所有运行中 issue ID 的当前状态。如果 issue 移动到终止状态 → 取消 worker + 清理工作区。如果移出活动状态 → 取消 worker、释放认领。

**重试逻辑：**
- `succeeded` → 1 秒后安排继续重试（检查是否需要更多工作）
- `failed/timed_out/stalled` → 指数退避：`min(10000 * 2^(attempt-1), max_retry_backoff_ms)`
- `canceled` → 立即释放认领

**关闭：** `stop()` 设置 `_stop_event`，通过 `os.killpg` 杀死所有子 PID，取消异步任务。

### runner.py
`run_agent_turn()` 构建 CLI 参数，启动子进程，流式输出 NDJSON。

**PID 跟踪：** `on_pid` 回调向协调器注册/注销子 PID 以便干净关闭。

**卡住检测：** 后台 `stall_monitor()` 任务检查自上次输出以来的时间。如果超过 `stall_timeout_ms` 则杀死进程。

**轮次超时：** `asyncio.wait()` 以 `turn_timeout_ms` 作为总体截止日期。

**事件处理**（`_process_event`）：
- `result` 事件 → 提取 `session_id`、token 使用量、结果文本
- `assistant` 事件 → 提取最后一条消息用于显示
- `tool_use` 事件 → 用工具名更新最后消息

### workspace.py
`ensure_workspace()` 在需要时创建目录，首次创建时运行 `after_create` 钩子。
`remove_workspace()` 运行 `before_remove` 钩子，然后删除目录。
`run_hook()` 通过 `asyncio.create_subprocess_shell` 超时执行 shell 脚本。

工作区键是清理后的 issue identifier：仅 `[A-Za-z0-9._-]` 字符。

### web.py
返回 `create_app(orch)` 的可选 FastAPI 应用。路由：

- `GET /` — HTML 仪表板（IBM Plex Mono 字体、深色主题、琥珀色点缀）
- `GET /api/v1/state` — 来自 `orch.get_state_snapshot()` 的完整 JSON 快照
- `GET /api/v1/{issue_identifier}` — 单个 issue 状态
- `POST /api/v1/refresh` — 立即触发 `orch._tick()`

仪表板 JS 每 3 秒轮询 `/api/v1/state` 并无刷新更新 DOM。

Uvicorn 作为 `asyncio.create_task` 启动，`install_signal_handlers` 猴子补丁为空操作以防止劫持 SIGINT/SIGTERM。关闭时设置 `server.should_exit = True` 并等待任务，带 2 秒超时。

### main.py
CLI 入口（`cli()`）和键盘处理器。

**`KeyboardHandler`** 在守护线程中使用 `tty.setcbreak()`（非 `setraw` — `setraw` 禁用 `OPOST` 输出处理导致对角日志输出）运行。使用 `select.select()` 100ms 超时进行非阻塞键读取。在 `finally` 中恢复终端状态。

**`_make_footer()`** 构建通过 `Live` 显示在终端底部的 Rich `Text` 状态行。

**`check_for_updates()`** 通过 httpx 调用 GitHub releases API（`/repos/Sugar-Coffee/stokowski/releases/latest`），比较最新标签与已安装的 `__version__`，如果存在新版本则设置 `_update_message`。尽力而为 — 所有异常静默吞掉。

**`_force_kill_children()`** 在 `KeyboardInterrupt` 时作为最后手段使用 `pgrep -f "claude.*-p.*--output-format.*stream-json"` 清理。

**`_load_dotenv()`** 启动时从 cwd 读取 `.env` — 支持 `KEY=value` 格式，忽略注释和空行。项目本地的 `.env` 优先于 shell 环境（使用直接赋值，覆盖现有环境变量）。

### prompt.py
状态机工作流的三层提示组装。入口点是 `assemble_prompt()`。

**`load_prompt_file(path, workflow_dir)`** 解析提示文件路径（绝对或相对于 workflow 目录）并返回其内容。

**`render_template(template_str, context)`** 使用 `_SilentUndefined` 渲染 Jinja2 模板 — 缺失变量渲染为空字符串而非引发错误。

**`build_template_context(issue, state_name, run, attempt, last_run_at)`** 构建用于 Jinja2 渲染的扁平字典。包括：`issue_id`、`issue_identifier`、`issue_title`、`issue_description`、`issue_url`、`issue_priority`、`issue_state`、`issue_branch`、`issue_labels`、`state_name`、`run`、`attempt`、`last_run_at`。

**`build_lifecycle_section()`** 生成追加到每个提示的自动注入生命周期部分。包括 issue 元数据、带审查评论的重构上下文、最近活动可用转换和完成说明。用 HTML 注释清晰分隔。

**`assemble_prompt()`** 协调三层：加载并渲染全局提示、加载并渲染阶段提示、生成生命周期部分、用双换行符连接。

### tracking.py
通过结构化 Linear 评论进行状态机跟踪：

- `make_state_comment(state, run)` — 构建带隐藏 JSON（`<!-- stokowski:state {...} -->`）+ 人类可读文本的状态条目评论
- `make_gate_comment(state, status, prompt, rework_to, run)` — 构建 gate 状态评论（waiting/approved/rework/escalated）
- `parse_latest_tracking(comments)` — 扫描评论（从旧到新）查找最新的状态或 gate 跟踪条目以支持崩溃恢复
- `get_last_tracking_timestamp(comments)` — 查找最新跟踪评论的时间戳
- `get_comments_since(comments, since_timestamp)` — 过滤给定时间戳之后的非跟踪评论（用于收集重构运行的审查反馈）

---

## 数据流：从 issue 调度到 PR

```
workflow.yaml 解析 → 加载状态 + 配置
    → Linear 轮询 → 获取 issue → 从跟踪评论解析状态
    → 调用 _dispatch()
        → 在 self.running 中创建 RunAttempt
        → 生成 _run_worker() 任务
            → ensure_workspace() → after_create 钩子（git clone、npm install 等）
            → assemble_prompt() → 3 层：全局 + 阶段 + 生命周期
            → 在循环中调用 run_agent_turn()（最多 max_turns）
                → build_claude_args() → claude -p 子进程
                → NDJSON 流式传输：tool_use 事件、assistant 消息、result
                → 捕获 session_id 用于下一轮
            → 调用 _on_worker_exit()
                → 成功时状态转换 → 发布跟踪评论
                → 聚合 token/时间
                → 安排重试或继续
```

智能体本身处理：移动 Linear 状态、发布评论、创建分支、通过 `gh pr create` 打开 PR、链接 PR 到 issue。Stokowski 不做这些 — 它是调度器，不是智能体。

---

## Stream-json 事件格式

Claude Code 使用 `--output-format stream-json --verbose` 运行时在 stdout 上输出 NDJSON。关键事件类型：

```json
{"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}]}}
{"type": "tool_use", "name": "Bash", "input": {"command": "..."}}
{"type": "result", "session_id": "uuid", "usage": {"input_tokens": 1234, "output_tokens": 456, "total_tokens": 1690}, "result": "final message text"}
```

退出码 0 = 成功。非零 = 失败（stderr 捕获用于错误消息）。

---

## 开发设置

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[web]"

# 验证配置而不调度智能体
stokowski --dry-run

# 运行详细日志
stokowski -v

# 运行 Web 仪表板
stokowski --port 4200
```

除了 `--dry-run` 没有自动化测试。最佳验证方式是在真实的 Linear 项目中使用测试工单运行。

---

## 贡献指南

### 添加新的 tracker（非 Linear）
1. 在新文件中添加客户端（例如 `github_issues.py`），实现与 `LinearClient` 相同的三个方法
2. 在 `config.py` 解析中添加新的 tracker 类型
3. 更新 `orchestrator.py` 根据 `cfg.tracker.kind` 实例化正确的客户端
4. 更新 `validate_config()` 处理新类型

### 添加配置字段
1. 在 `config.py` 的相关数据类中添加字段
2. 在 `parse_workflow_file()` 中解析
3. 在需要的地方使用
4. 更新 `WORKFLOW.example.md` 和 README 配置参考

### 修改 Web 仪表板
`web.py` 是自包含的。HTML/CSS/JS 内联在 `HTML` 常量中。仪表板故意在前端无依赖 — 无构建步骤、无 npm。

### 常见陷阱
- **`tty.setraw` vs `tty.setcbreak`**：不要切换回 `setraw`。它禁用 `OPOST` 输出处理导致 Rich 日志行对角渲染（换行无回车）。
- **`Issue(title=...)` 是必需的**：最小化 Issue 构造函数（`linear.py` 的 `fetch_issues_by_states` 和 `orchestrator.py` 状态检查默认值）必须传入 `title=""` — 它是必需的 positional 字段。
- **带 stream-json 的 `--verbose`**：Claude Code 在使用 `--output-format stream-json` 时需要 `--verbose`。没有它会报错。
- **Linear 项目 slug**：`project_slug` 是项目 URL 中的十六进制 `slugId`，而非人类可读名称。这些看起来像 `abc123def456`。
- **Uvicorn 信号处理器**：必须在调用 `serve()` 前猴子补丁（`server.install_signal_handlers = lambda: None`），否则 uvicorn 会劫持 SIGINT。
- **workflow.yaml 是纯 YAML**：无 markdown front matter。遗留的带 `---` 分隔符的 `.md` 格式仍支持，但 `.yaml` 是规范格式。
- **提示文件使用 Jinja2 且静默 undefined**：缺失变量变为空字符串而非引发错误。这是故意的 — 并非所有变量在每个上下文中都可用。
