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

---

## 已知问题

### Web 仪表板端口绑定问题

在某些 Windows 配置上，可能遇到端口绑定权限错误：

```
PermissionError: [Errno 13] error while attempting to bind on address ('127.0.0.1', 4200)
```

**解决方案**:
1. 不使用 Web 仪表板，直接运行 `stokowski`
2. 以管理员权限运行
3. 检查防火墙设置

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
