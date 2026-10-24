# Codex 适配

## 当前安装结果

本机 Codex CLI `0.147.0` 已注册：

```text
MCP name: openmouse
Transport: stdio
Command: D:\Desktop\新建文件夹 (16)\.venv\Scripts\python.exe -m mouse_mcp
```

检查：

```powershell
codex mcp get openmouse --json
codex mcp list --json
codex doctor --summary --no-color
```

实际新会话已经验证：

1. Codex 启动 OpenMouse MCP。
2. 握手并读取 11 个工具。
3. Agent 通过 `tool_search` 发现 `openmouse`。
4. `mouse_status` 返回 `environment=desktop`。
5. `computer_observe` 返回当前 Windows 截图和任务栏矩形。

## 为什么工具没有直接出现

当前 Codex 启用了 `ToolSearchAlwaysDeferMcpTools`。MCP 工具会延迟到 Tool Search 中，避免把大型工具目录全部塞入每个首轮上下文。

自然语言示例：

```text
先用 tool_search 搜索 openmouse computer_observe mouse_status，
然后观察屏幕并告诉我任务栏位置，不要移动鼠标。
```

发现后，Codex 会直接调用 `mcp__openmouse__computer_observe` 等工具。

## 已安装 Codex Skill

技能位置：

```text
C:\Users\28330\.codex\skills\openmouse-computer-use\SKILL.md
```

项目内可重装源文件：

```text
codex\openmouse-computer-use\
```

触发场景包括：

- 看屏幕、识别任务栏、操作软件窗口
- 点击、拖拽、滚动网页
- 使用截图做 GUI grounding
- Windows 真鼠标或云端浏览器 computer-use

技能会指导 Codex：

1. 先用 `computer_observe`。
2. 使用当前截图和窗口元数据定位。
3. 每次点击、拖拽、滚动都填写 `intent`。
4. 动作后再次观察。
5. 高风险动作等待用户确认。

## 重新安装或更新

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-codex.ps1
```

脚本会：

- 备份 `~/.codex/config.toml` 为 `config.toml.openmouse-backup`
- 替换同名 `openmouse` 配置
- 指向项目 `.venv`、`src` 和浏览器令牌
- 打印 `codex mcp get` 结果

注册或修改 MCP 后请新开 Codex 会话。运行中的旧线程不会自动重新加载工具目录。

## 本地模式

本地 Codex 使用：

```text
MOUSE_MCP_ENV=auto
MOUSE_MCP_CLOUD_BROWSER=off
```

- 受控 Chromium 在焦点中：网页虚拟鼠标。
- 其他前台窗口：Windows 真鼠标。
- `computer_observe` 返回任务栏、窗口、显示器和全屏截图。

## 云端模式

另注册一个远程 MCP：

```powershell
$env:OPENMOUSE_MCP_TOKEN = "same-token-as-cloud-server"

codex mcp add openmouse-cloud `
  --url "https://mcp.example.com/mcp" `
  --bearer-token-env-var OPENMOUSE_MCP_TOKEN
```

云端 Codex 使用的是容器内 Playwright 浏览器，不连接你的本地桌面。完整部署见 [CLOUD.md](CLOUD.md)。

## 安全建议

- 本地 MCP 工具可控制真实鼠标，应在可信工作区启用。
- 云端 MCP 必须使用 Bearer Token、HTTPS 和 Host 白名单。
- 高风险点击依赖 MCP elicitation 和 Agent 提示词，不可在无人监督下运行。
