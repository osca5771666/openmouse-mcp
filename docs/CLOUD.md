# 云端与本地双模式

## 两种部署形态

OpenMouse MCP 使用同一套工具接口，但部署位置不同：

| 形态 | 执行面 | 入口 |
| --- | --- | --- |
| 本地 | 真实 Windows 鼠标、任务栏、软件窗口 | Codex/OpenClaw 通过 stdio 启动 |
| 云端 | 容器内 Playwright Chromium | Codex/其他 MCP 宿主通过 Streamable HTTP 连接 |

云端 MCP 进程同时拥有自己的无头 Chromium，不需要另一个浏览器服务。它是“插件进程内浏览器”，不是独立业务后台。

## 云端本地启动测试

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

端点：

```text
http://127.0.0.1:8766/mcp
```

健康检查：

```text
http://127.0.0.1:8766/healthz
```

除健康检查外，设置 `MOUSE_MCP_HTTP_TOKEN` 后所有 MCP 请求必须带：

```http
Authorization: Bearer <token>
```

## Docker

`Dockerfile` 基于官方 Playwright Python 镜像，已包含 Chromium 运行依赖。

```powershell
$env:MOUSE_MCP_HTTP_TOKEN = "replace-with-a-long-random-token"
$env:MOUSE_MCP_HTTP_ALLOWED_HOSTS = "mcp.example.com,localhost,127.0.0.1"
docker compose up --build -d
```

Compose 默认只绑定宿主机回环端口：

```text
127.0.0.1:8766
```

公网部署时，使用带 TLS 和认证的 Caddy、Nginx、Cloudflare Tunnel 或其他反向代理转发到该端口。不要把未认证的 `8766` 直接暴露到公网。

本机当前没有 Docker，因此 Dockerfile 已提供但未在当前机器上实际构建。应用层的 Streamable HTTP、Bearer Token 和云浏览器链路已经通过 E2E。

## 云端 Codex 注册

```powershell
$env:OPENMOUSE_MCP_TOKEN = "replace-with-the-same-http-token"

codex mcp add openmouse-cloud `
  --url "https://mcp.example.com/mcp" `
  --bearer-token-env-var OPENMOUSE_MCP_TOKEN

codex mcp get openmouse-cloud --json
```

Codex 当前会把 MCP 工具放在 Tool Search 后面。新会话中看到鼠标/浏览器任务时，Agent 先用 `tool_search` 搜索 `openmouse computer_observe mouse_status`，再调用发现的工具。

在云端会话里：

1. `browser_open` 打开 HTTP(S) 页面。
2. `computer_observe` 获取云端页面图片和视口信息。
3. `mouse_*` 执行点击、拖拽、滚动。
4. 再次 `computer_observe` 验证。

## 云端和本地不能直接共享鼠标状态

云端容器无法越过网络直接控制用户电脑的真实鼠标。它不是远程桌面协议，也不应被当成绕过本机权限的通道。

- 要操作本机桌面，运行本地 stdio MCP。
- 要操作云端隔离浏览器，运行云端 HTTP MCP。
- 如果未来需要“云端 Agent 控制本机”，应在可信本地 companion 上建立带认证的反向通道，这是另一层安全设计。

## 云端环境变量

| 变量 | 说明 |
| --- | --- |
| `MOUSE_MCP_HTTP_TOKEN` | Streamable HTTP Bearer Token |
| `MOUSE_MCP_HTTP_ALLOWED_HOSTS` | 允许的 Host，逗号分隔 |
| `MOUSE_MCP_CLOUD_BROWSER` | `on` 或 `auto` |
| `MOUSE_MCP_CLOUD_HEADLESS` | 默认 `1` |
| `MOUSE_MCP_CLOUD_VIEWPORT_WIDTH` | 云浏览器视口宽度 |
| `MOUSE_MCP_CLOUD_VIEWPORT_HEIGHT` | 云浏览器视口高度 |
| `MOUSE_MCP_CLOUD_USER_DATA_DIR` | 可选持久化浏览器资料目录 |
| `MOUSE_MCP_CLOUD_CHROMIUM_EXECUTABLE` | 可选 Chromium 路径 |
| `MOUSE_MCP_CLOUD_ALLOW_PRIVATE_URLS` | 默认 `0`；只应在可信内网环境中设为 `1` |

`browser_open` 默认拒绝 localhost、内网、链路本地、保留和特殊地址，降低云端浏览器被用作 SSRF 通道的风险。该检查不能替代容器网络层的出站防火墙和 DNS 策略。
