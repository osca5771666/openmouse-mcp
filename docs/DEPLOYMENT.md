# 部署教程

## 前置条件

- Windows 10 或 Windows 11。
- Python 3.10 或更高版本。
- Chrome、Edge、Brave 或其他 Chromium 浏览器。
- Codex 0.147.0 或更高版本，或支持 MCP 的 OpenClaw。
- 支持 MCP 客户端的 OpenClaw 版本。OpenClaw 旧版本如果不存在 `openclaw mcp` 命令，需要先升级。
- Ollama 仅负责运行模型。它本身不是通用 MCP 宿主；要让 Ollama 模型获得本工具，应通过 Ollama 启动 OpenClaw，或在其他 MCP 宿主中接入 Ollama 模型。

## 1. 安装 Python 插件

在当前项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

脚本会：

1. 创建 `.venv`。
2. 安装 `mcp`、`websockets`、`PyAutoGUI`、`pynput` 等依赖。
3. 生成 `.runtime\browser-token.txt`。
4. 输出浏览器扩展需要填写的共享令牌。

也可以手动安装：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## 2. 安装浏览器扩展

1. 打开 `chrome://extensions` 或 `edge://extensions`。
2. 开启“开发者模式”。
3. 选择“加载已解压的扩展程序”。
4. 选择项目中的 `browser-extension` 目录。
5. 点击扩展的“选项”。
6. 将 Bridge URL 保持为 `ws://127.0.0.1:8765`。
7. 粘贴 `.runtime\browser-token.txt` 中的令牌。
8. 保存设置。

连接成功后扩展角标显示 `ON`。扩展请求站点访问权限，是为了向当前页面派发可控鼠标事件和截图；它只连接 `127.0.0.1` 的插件内桥。

常见受限页面包括 `chrome://`、扩展商店、浏览器内置 PDF 查看器和开发者工具，这些页面不能使用内容脚本截图或点击。

## 3. 自检

先打开一个普通网页，并让浏览器处于前台，然后运行：

```powershell
.\.venv\Scripts\python.exe -m mouse_mcp --diagnose --diagnose-wait 4
```

输出中应看到：

```json
{
  "route": {
    "environment": "browser"
  },
  "browser": {
    "connected": true,
    "fresh": true
  }
}
```

如果把终端或编辑器切到前台再运行，自动路由应变成：

```json
{
  "route": {
    "environment": "desktop"
  }
}
```

这就是自动环境适配，不需要改工具参数。

## 4. 接入 OpenClaw

### 自动注册

在 MCP 能力正常的 OpenClaw 版本上运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-openclaw.ps1
```

等价命令：

```powershell
openclaw mcp add openmouse-mcp `
  --command "D:\absolute\path\openmouse-mcp\.venv\Scripts\python.exe" `
  --arg "-m" `
  --arg "mouse_mcp" `
  --cwd "D:\absolute\path\openmouse-mcp"

openclaw mcp doctor openmouse-mcp --probe
```

### 手动配置

在 `~/.openclaw/openclaw.json` 的 `mcp.servers` 下加入：

```json5
{
  mcp: {
    servers: {
      "openmouse-mcp": {
        command: "D:\\absolute\\path\\openmouse-mcp\\.venv\\Scripts\\python.exe",
        args: ["-m", "mouse_mcp"],
        cwd: "D:\\absolute\\path\\openmouse-mcp",
        transport: "stdio",
        enabled: true,
      },
    },
  },
}
```

完整示例见 `examples/openclaw-mcp.snippet.json5`。令牌默认从项目内的 `.runtime\browser-token.txt` 读取，不需要写进 Agent 配置。

OpenClaw 会把 MCP 工具放入 Agent 的工具目录，并自动注入 MCP 服务说明。要额外强化操作纪律，可将 `docs/AGENT_SYSTEM_PROMPT.md` 内容加入 Agent 指令。

## 4A. 接入 Codex

当前 Codex CLI 0.147.0 支持：

```powershell
codex mcp add <name> -- <command> [args...]
```

使用项目脚本直接注册：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-codex.ps1
```

脚本会备份 `~/.codex/config.toml`，注册名为 `openmouse` 的 stdio MCP，并设置：

- `PYTHONPATH` 指向 `src`
- `MOUSE_MCP_TOKEN_FILE` 指向浏览器令牌文件
- `MOUSE_MCP_ENV=auto`
- `MOUSE_MCP_CLOUD_BROWSER=off`，避免本地 Codex 误用云浏览器

验证：

```powershell
codex mcp get openmouse --json
codex mcp list --json
```

Codex 启用了 `ToolSearchAlwaysDeferMcpTools` 时，鼠标工具可能不会出现在首屏。新会话中让 Agent：

```text
先 tool_search 搜索 openmouse computer_observe mouse_status，再调用发现的工具。
```

注册新 MCP 后需要新开 Codex 会话。运行中的旧会话不会热更新工具目录。

### OpenClaw 旧版本

如果 `openclaw mcp --help` 显示不存在该命令，当前安装不支持 MCP 客户端。此时不能把普通 `openclaw plugins install` 当成 MCP 注册命令；应升级到支持 `mcp.servers` 的版本，或改用支持 `stdio` MCP 的宿主。

## 5. 接入 Ollama + OpenClaw

推荐先由 Ollama 配置并启动 OpenClaw：

```powershell
ollama launch openclaw --model qwen3-coder
```

随后按上一节注册 `openmouse-mcp`。模型由 Ollama 提供，MCP 工具由 OpenClaw 提供。不要尝试用 `ollama run <model>` 直接加载 MCP 配置，因为 Ollama CLI 本身不是 MCP 客户端宿主。

如果使用其他 Ollama Agent 宿主，只要它支持 stdio MCP，使用 `examples/mcp-generic.json` 的配置形状即可。

## 5A. 云端 Streamable HTTP

完整说明见 [CLOUD.md](CLOUD.md)。

本地验证云端模式：

```powershell
$env:MOUSE_MCP_ENV = "cloud"
$env:MOUSE_MCP_CLOUD_BROWSER = "on"
$env:MOUSE_MCP_HTTP_TOKEN = "replace-with-a-long-random-token"

.\.venv\Scripts\python.exe -m mouse_mcp `
  --transport streamable-http `
  --host 127.0.0.1 `
  --port 8766 `
  --cloud-browser
```

注册云端 MCP：

```powershell
$env:OPENMOUSE_MCP_TOKEN = "replace-with-the-same-token"
codex mcp add openmouse-cloud `
  --url "https://mcp.example.com/mcp" `
  --bearer-token-env-var OPENMOUSE_MCP_TOKEN
```

云端容器中的浏览器是隔离浏览器，不是用户本地桌面。要控制本地任务栏和软件，必须使用本地 stdio 实例。

## 6. 接入其他 Agent

通用参数：

```text
command: <project>\.venv\Scripts\python.exe
args:    -m mouse_mcp
cwd:     <project>
env:     optional MOUSE_MCP_* overrides
```

不要使用 `python.exe` 相对名称，除非宿主进程的 PATH 可以稳定解析它。Agent 服务或桌面应用通常有独立的启动环境。

## 7. 可选环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MOUSE_MCP_ENV` | `auto` | 调试可设 `browser` 或 `desktop` |
| `MOUSE_MCP_BRIDGE_HOST` | `127.0.0.1` | 不建议改 |
| `MOUSE_MCP_BRIDGE_PORT` | `8765` | 与扩展选项一致 |
| `MOUSE_MCP_BROWSER_TOKEN` | 令牌文件 | 覆盖扩展共享令牌 |
| `MOUSE_MCP_HEARTBEAT_TIMEOUT` | `4.0` | 扩展失效判定秒数 |
| `MOUSE_MCP_COMMAND_TIMEOUT` | `20.0` | 浏览器命令超时秒数 |
| `MOUSE_MCP_MIN_ACTION_DELAY` | `0.2` | 动作后最小停顿 |
| `MOUSE_MCP_MAX_ACTION_DELAY` | `1.3` | 动作后最大停顿 |
| `MOUSE_MCP_CONFIRM_HIGH_RISK` | `true` | 只能设为严格模式；关闭时高危动作直接拒绝 |
| `MOUSE_MCP_CLOUD_BROWSER` | `auto` | `auto`、`on` 或 `off` |
| `MOUSE_MCP_HTTP_TOKEN` | 空 | 云端 Streamable HTTP Bearer Token |
| `MOUSE_MCP_HTTP_ALLOWED_HOSTS` | 空 | 云端允许的 Host，逗号分隔 |
| `MOUSE_MCP_CLOUD_ALLOW_PRIVATE_URLS` | `false` | 是否允许云端打开内网 URL |

## 8. 运行验证

### 浏览器测试页

```powershell
py -m http.server 8099 --directory demo
```

浏览器打开：

```text
http://127.0.0.1:8099/browser-demo.html
```

对 Agent 发送：

```text
先截图，识别 Save note 按钮，点击一次，然后截图验证 Save count 变为 1。
```

### Windows 桌面测试

1. 打开记事本或一个空白测试窗口。
2. 让该窗口处于前台。
3. 让 Agent 先调用 `computer_observe`，确认任务栏、活动窗口和窗口矩形。
4. 指示它只移动光标到窗口标题栏边缘，不点击。
5. 人工确认轨迹和边界后再测试点击。

首次桌面测试不要把目标设为删除按钮、关闭按钮、终端执行按钮或未保存文档。

## 9. 故障排查

### 扩展显示 ERR 或没有 ON

- 检查服务端是否在运行。
- 检查扩展选项中的令牌是否与 `.runtime\browser-token.txt` 完全一致。
- 检查 `8765` 端口是否被另一个实例占用。
- 修改端口后，服务端环境变量和扩展 Bridge URL 必须同时修改。

### 自动路由一直走桌面

- 确保浏览器窗口真的处于焦点。
- 在扩展选项页确认服务端 URL 和令牌。
- 运行 `mouse_status`，检查 `fresh` 和 `focused`。
- 浏览器最小化或失去焦点时，插件会按设计走桌面。

### 点击被页面忽略

- 页面可能只接受可信输入，并检查 `event.isTrusted`。
- 跨域 iframe 内容不在当前内容脚本作用域内。
- 浏览器原生右键菜单通常不接受合成 `contextmenu`。
- 截图后等待页面动画结束，再重新截图定位。

### 截图尺寸和坐标不一致

使用 `computer_observe` 或 `mouse_screenshot` 返回的 `image_width`、`image_height`、`viewport_width`、`viewport_height` 进行比例换算。不要直接假设截图是 1:1 CSS 像素。

### PyAutoGUI 无动作

- 确认 Agent 进程不是无桌面会话。
- 确认目标软件与 Agent 进程权限等级一致。以管理员权限运行的软件可能拒绝普通进程输入。
- 检查 ESC 保护或连续失败是否已经触发停止。
- 运行 `mouse_status` 查看 `desktop_available`。

## 10. 卸载

1. 从 OpenClaw 或 MCP 宿主中移除 `openmouse-mcp`。
2. 在浏览器扩展页移除扩展。
3. 删除项目目录或只删除 `.venv`。
