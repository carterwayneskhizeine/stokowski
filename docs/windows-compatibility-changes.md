# Windows 兼容性修改记录

本文档记录了为使 Stokowski 在 Windows 上正常工作所做的修改。

## 修改日期
2026-03-13

## 问题概述

Stokowski 原本是为 Unix/Linux 系统设计的，在 Windows 上运行时遇到了多个兼容性问题：

1. `termios` 和 `tty` 模块在 Windows 上不存在
2. `pgrep` 命令在 Windows 上不可用
3. 文件读取编码问题（GBK vs UTF-8）
4. 打包配置问题

---

## 修改详情

### 1. `stokowski/main.py` - Windows 键盘处理支持

**问题**: `termios` 和 `tty` 是 Unix 特有模块，Windows 不支持。

**解决方案**: 添加平台检测，在 Windows 上使用 `msvcrt` 模块。

```python
# 添加平台检测
import platform

# Windows doesn't have termios/tty
if platform.system() == "Windows":
    import msvcrt
    termios = None
    tty = None
else:
    import termios
    import tty
```

**修改 `KeyboardHandler._run()` 方法**:

```python
def _run(self):
    if not sys.stdin.isatty():
        return

    # Windows path
    if termios is None:
        try:
            while not self._stop.is_set():
                if msvcrt.kbhit():
                    ch = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                    self._handle(ch)
                self._stop.wait(0.1)
        except Exception:
            pass
        return

    # Unix path (原有代码)
    ...
```

### 2. `stokowski/main.py` - 进程清理支持 Windows

**问题**: `_force_kill_children()` 函数使用 `pgrep` 命令查找进程，Windows 不支持。

**解决方案**: 在 Windows 上使用 `tasklist` 和 `taskkill` 命令。

```python
def _force_kill_children():
    """Kill any lingering claude -p processes."""
    import subprocess

    # Windows path: use taskkill
    if platform.system() == "Windows":
        try:
            # Find processes by command line pattern
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq claude.exe", "/FO", "CSV"],
                capture_output=True, text=True,
            )
            # Parse and kill each claude.exe process
            for line in result.stdout.strip().split('\n')[1:]:  # Skip header
                if not line.strip():
                    continue
                try:
                    pid = line.split(',')[1].strip('"')
                    subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
                except (ValueError, IndexError):
                    pass
        except Exception:
            pass
        return

    # Unix path: use pgrep (原有代码)
    ...
```

### 3. `stokowski/config.py` - UTF-8 编码支持

**问题**: Windows 默认使用 GBK 编码读取文件，导致包含中文注释的 `workflow.yaml` 解析失败。

**解决方案**: 明确指定使用 UTF-8 编码读取文件。

```python
# 修改前
content = path.read_text()

# 修改后
content = path.read_text(encoding="utf-8")
```

### 4. `stokowski/prompt.py` - UTF-8 编码支持

**问题**: 同上，prompt 文件读取也需要 UTF-8 编码。

**解决方案**: 明确指定使用 UTF-8 编码读取文件。

```python
# 修改前
return p.read_text()

# 修改后
return p.read_text(encoding="utf-8")
```

### 5. `stokowski/prompt.py` - Jinja2 兼容性修复

**问题**: `_SilentUndefined` 类没有继承 `jinja2.Undefined`，在 Jinja2 3.0+ 版本中会报错：
```
'undefined' must be a subclass of 'jinja2.Undefined'
```

**解决方案**: 让 `_SilentUndefined` 继承 `jinja2.Undefined` 基类。

```python
# 修改前
class _SilentUndefined:
    """Jinja2 undefined that renders as empty string."""
    ...

# 修改后
from jinja2 import BaseLoader, Environment, Undefined

class _SilentUndefined(Undefined):
    """Jinja2 undefined that renders as empty string."""

    def __str__(self) -> str:
        return ""

    def __iter__(self):  # type: ignore[override]
        return iter(())
```

### 6. `stokowski/prompt.py` - 支持嵌套 issue 对象

**问题**: Prompt 模板使用 `{{ issue.identifier }}` 等嵌套变量，但 `build_template_context()` 只提供扁平化变量（如 `{{ issue_identifier }}`），导致模板渲染报错：
```
'issue' is undefined
```

**解决方案**: 在 `build_template_context()` 中同时提供扁平化变量和嵌套的 `issue` 对象，保持向后兼容。

```python
# 在返回的 dict 中添加嵌套的 issue 对象
return {
    # Flat keys for backward compatibility
    "issue_id": issue.id,
    "issue_identifier": issue.identifier,
    ...
    # Nested issue object for easier template access
    "issue": {
        "id": issue.id,
        "identifier": issue.identifier,
        "title": issue.title,
        "description": issue.description or "",
        "url": issue.url or "",
        "priority": issue.priority,
        "state": issue.state,
        "branch_name": issue.branch_name or "",
        "labels": issue.labels,
    },
    ...
}
```

现在模板可以使用两种格式：
- `{{ issue_identifier }}` - 扁平化格式
- `{{ issue.identifier }}` - 嵌套对象格式

### 7. `pyproject.toml` - 打包配置修复

**问题**: setuptools 自动发现了 `stokowski/` 和 `prompts/` 两个目录，而 `prompts/` 只是示例文件，不应该被打包。

**解决方案**: 明确指定只包含 `stokowski*` 包。

```toml
[project.scripts]
stokowski = "stokowski.main:cli"

[tool.setuptools.packages.find]
include = ["stokowski*"]
```

---

## 用户配置建议

### Windows 环境注意事项

1. **路径格式**
   - `workflow.yaml` 中的路径可以使用正斜杠 `/` 或反斜杠 `\`
   - 建议使用正斜杠（更通用）：`C:/Code/workspaces`
   - 或使用双反斜杠转义：`C:\\Code\\workspaces`

2. **PowerShell 环境变量**
   - 设置环境变量：`$env:LINEAR_API_KEY = "your-key"`
   - 永久设置：添加到系统环境变量或 `$PROFILE` 文件
   - 验证：`echo $env:LINEAR_API_KEY`

3. **Git 和 SSH 配置**
   - Windows 上需要安装 Git for Windows
   - 确保 `ssh-agent` 服务正在运行（可选，用于 SSH 密钥管理）
   - 验证 GitHub 连接：`ssh -T git@github.com`

4. **GitHub CLI**
   - Windows 上安装：`winget install --id GitHub.cli`
   - 认证：`gh auth login`
   - 验证：`gh auth status`

### workflow.yaml 配置

对于使用 **pnpm** 的项目（而非 npm），需要修改 `hooks.after_create`:

```yaml
hooks:
  after_create: |
    git clone --depth 1 git@github.com:user/repo.git .
    pnpm install  # 使用 pnpm 而非 npm
```

### Linear 状态设置

确保 Linear 项目中创建以下状态：

| 状态 | 用途 |
|------|------|
| `Todo` | 人工创建工单后的初始状态 |
| `In Progress` | Agent 正在工作 |
| `Human Review` | 等待人工审查 |
| `Gate Approved` | 人工批准，进入下一阶段 |
| `Rework` | 请求修改 |
| `Done` | 完成 |

### Linear 项目配置

1. **获取正确的 `project_slug`**

   `project_slug` 是 Linear 项目 URL 中的十六进制 ID，不是项目名称。

   ```
   正确示例: project_slug: "7e6b4c9bcd1d"
   错误示例: project_slug: "clawx-2-0-1"
   ```

   可以从项目 URL 中获取：`https://linear.app/team/workspaces/{project_slug}-{project_name}`

2. **配置 Linear Workflow Rules**

   由于 Linear 的默认工作流限制，某些状态转换可能被阻止。需要在 Linear 中手动配置：

   - 进入 Linear → Settings → **Workflow**
   - 点击每个状态，在 **Transitions** 部分添加允许的转换：
     - `In Progress` → `Human Review`
     - `Human Review` → `Gate Approved`
     - `Human Review` → `Rework`
     - `Rework` → `In Progress`
   - 确保工作流允许所有必要的状态转换

3. **验证 API Key 权限**

   确保你的 `LINEAR_API_KEY` 有足够的权限：
   - **Read: Issues** - 读取 issue 数据
   - **Write: Issues** - 修改 issue 状态
   - **Write: Comments** - 在 issue 上发布评论

   可以通过以下命令测试：
   ```bash
   curl -X POST https://api.linear.app/graphql \
     -H "Authorization: $LINEAR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"query":"query { viewer { name } }"}'
   ```

### 手动操作流程（如果自动状态更新失败）

如果 Linear API 返回 400 错误导致状态无法自动更新，可以采用手动操作流程：

```
1. 在 Linear 创建 issue，状态为 Todo
2. 手动把状态改为 "In Progress" → Agent 开始工作
3. Agent 完成后，日志显示 "Gate entered" → 手动改为 "Human Review"
4. 审查结果，手动改为 "Gate Approved" 继续，或 "Rework" 返回
5. 重复步骤 3-4 直到所有阶段完成
6. 最后手动改为 "Done"
```

**注意**: 如果在 Agent 运行时手动改状态，Stokowski 的 reconciliation 机制会检测到 issue 不再处于 active 状态，会取消 Agent 并清理 workspace。因此，**只能在 Agent 完成工作后（看到 "Gate entered" 日志）才手动改状态**。

---

## 已知问题

### Linear 状态自动更新失败

**问题**: Agent 完成工作后，Stokowski 尝试自动更新 Linear 状态（如从 "In Progress" 改为 "Human Review"），但 Linear API 返回 400 错误：

```
ERROR Failed to update state for xxx: Client error '400 Bad Request' for url 'https://api.linear.app/graphql'
INFO  Gate entered issue=CLA-XX gate=research-review run=1
```

**原因**: Linear 的 Workflow Rules 阻止了某些状态转换。默认情况下，Linear 可能不允许从 "In Progress" 直接转换到 "Human Review"。

**解决方案**:

1. **配置 Linear Workflow Rules**（推荐）
   - 进入 Linear → Settings → **Workflow**
   - 点击 "In Progress" 状态
   - 在 **Transitions** 里添加 "Human Review" 为允许的转换
   - 为其他状态也配置相应的转换规则

2. **手动更新状态**（临时方案）
   - 看到 `Gate entered` 日志后，手动在 Linear 改状态
   - **注意**: 只在 Agent 完成后才手动改，不要在 Agent 运行时改

3. **简化状态映射**
   - 如果不想修改 Linear 工作流，可以让多个 agent 状态都映射到同一个 Linear 状态
   - 只依赖 gate 的评论记录来区分阶段

**影响**: 状态更新失败不会影响 Agent 的工作结果，只是需要手动操作 Linear 状态来推进流程。

### 手动改状态导致 Agent 被取消

**问题**: 在 Agent 运行时手动修改 Linear 状态，导致 Agent 立即被取消，workspace 被清理：

```
INFO     Worker cancelled issue=CLA-11
```

**原因**: Stokowski 的 reconciliation 机制每 15 秒检查一次运行中的 issue，如果发现 issue 不再处于 `active` 状态（"In Progress"），会认为该 issue 不应该继续运行，因此取消 Agent。

**解决方案**:
- **不要在 Agent 运行时手动改状态**
- 等待 Agent 完成（看到 `Turn complete` 或 `Gate entered` 日志）
- 然后再手动改状态

**正确流程**:
```
Agent 运行中 (In Progress) → 不要动！
        ↓
Agent 完成 (Gate entered) → 现在可以手动改状态
        ↓
手动改成 Human Review → 继续
```

### Web 仪表板端口绑定问题

在某些 Windows 配置上，可能遇到端口绑定权限错误：

```
PermissionError: [Errno 13] error while attempting to bind on address ('127.0.0.1', 4200)
[WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。
```

**尝试过的解决方案**:

1. **原始代码** (`asyncio.create_task(_uvicorn_server.serve())`) - 失败，抛出 `SystemExit`
2. **使用 `uvicorn.run()` 在独立线程中运行** (`asyncio.to_thread()`) - 失败
3. **管理员权限** - 已排除，不是权限问题
4. **端口占用** - 已排除，不是端口问题
5. **捕获 `SystemExit` 和 `OSError`** ✅ **成功** - 在异步包装函数中捕获异常并优雅降级

**可能的根本原因**:
- Windows 安全软件（Defender、防火墙、VPN、代理）阻止了 127.0.0.1 的端口绑定
- Windows 网络栈的某些配置问题

**解决方案**:

1. **推荐：使用排除范围外的端口** ✅
   Windows 预留了一段端口范围（通过 `netsh int ipv4 show excludedportrange protocol=tcp` 查看），使用不在范围内的端口即可。

   ```
   # 4200 在排除范围内（4169-4268），不可用
   # 9001 可用
   stokowski --port 9001
   ```

2. **备选：捕获绑定异常**
   程序也会捕获绑定异常，允许在 Web 仪表板启动失败的情况下继续运行。

   ```powershell
   # 不使用 Web 仪表板
   stokowski
   ```
3. 在 Linux/macOS 容器或虚拟机中运行

### 8. `stokowski/runner.py` - 增大 NDJSON 流缓冲区

**问题**: asyncio `StreamReader` 默认缓冲区上限为 64KB。Claude Code 输出的某些 NDJSON 行（如包含大量代码的 `tool_use` 或 `assistant` 事件）超过此限制，导致：

```
ValueError: Separator is found, but chunk is longer than limit
```

进而触发重试（`error=continuation`）。

**解决方案**: 在两处 `asyncio.create_subprocess_exec` 调用中传入 `limit=10MB`：

```python
# 修改前
proc = await asyncio.create_subprocess_exec(
    *args,
    cwd=str(workspace_path),
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    start_new_session=True,
)

# 修改后
proc = await asyncio.create_subprocess_exec(
    *args,
    cwd=str(workspace_path),
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    start_new_session=True,
    limit=10 * 1024 * 1024,  # 10MB — default 64KB is too small for large NDJSON lines
)
```

两处调用均需修改，此修改与平台无关（非 Windows 专属）。

---

## 故障排查

### 问题：Stokowski 没有发现我在 Linear 创建的 issue

**可能原因**:
1. Issue 状态不是 "In Progress"（Stokowski 只监听 active 状态）
2. `project_slug` 配置错误
3. API Key 无权限访问该项目

**解决方案**:
- 手动把 issue 状态改成 "In Progress"
- 检查 `workflow.yaml` 中的 `project_slug` 是否为正确的十六进制 ID
- 运行 `stokowski --dry-run` 验证配置

### 问题：Agent 完成后没有自动创建 PR

**可能原因**:
1. Prompt 文件没有指示 Agent 创建 PR
2. `gh` CLI 未登录或没有权限
3. Workspace 没有正确克隆仓库

**解决方案**:
- 检查 `prompts/implement.example.md` 是否包含创建 PR 的指令
- 运行 `gh auth status` 和 `gh auth login` 确保 GitHub CLI 可用
- 检查 `hooks.after_create` 中的 `git clone` 命令是否正确

### 问题：Agent 工作正常但 Linear 状态不变

**可能原因**:
- Linear Workflow Rules 阻止了状态转换
- API Key 没有 Write 权限

**解决方案**:
- 在 Linear 中配置 Workflow Rules 允许相应转换
- 手动改状态作为临时方案
- 检查 API Key 权限

### 问题：手动改状态后 Agent 消失

**可能原因**:
- 在 Agent 运行时改了状态，触发 reconciliation 取消

**解决方案**:
- 等待 Agent 完成后再手动改状态
- 检查日志确认 Agent 已完成（`Gate entered`）

### 问题：无法连接到 GitHub（ssh: Could not resolve hostname）

**可能原因**:
- 网络连接问题
- SSH 配置问题

**解决方案**:
- 检查网络连接
- 测试 SSH 连接：`ssh -T git@github.com`
- 如果持续失败，可考虑使用 HTTPS URL 克隆仓库

---

## 测试验证

### 验证配置

```bash
# 在工作目录运行
stokowski --dry-run
```

应输出：
- 配置验证通过
- Linear 连接成功
- 状态机正确解析
- 候选工单列表

### 完整运行

```bash
# 不带 Web 仪表板
stokowski

# 带 Web 仪表板（如果端口可用）
stokowski --port 4200
```

---

## 贡献者

这些修改是在 Windows 11 环境下开发和测试的。

如果遇到其他 Windows 兼容性问题，请提交 Issue 或 Pull Request。
