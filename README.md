# OpenMouse MCP

内置式视觉鼠标操控 MCP 插件。本地 Agent 直接以 `stdio` 启动，云部署可暴露 Streamable HTTP。插件内部自动选择执行面：

- 前台是已连接的 Chromium 浏览器时，使用页面内 JS 虚拟光标、DOM Pointer/Mouse 事件和当前标签页截图。
- 前台不是该浏览器时，在 Windows 上使用 PyAutoGUI 操控真实系统鼠标，可操作桌面、窗口和终端。
- 在 Linux/云端或显式启用云浏览器时，使用 MCP 进程内 Playwright Chromium，提供可信浏览器输入。

浏览器端不会穿透网页去移动系统鼠标；Windows 端可以操作桌面任意软件。

## 能力

| 工具 | 作用 |
| --- | --- |
| `mouse_move` | 贝塞尔轨迹移动，带轻微抖动和中途停顿 |
| `mouse_click` | 左键单击、左键双击、右键单击 |
| `mouse_drag` | 人类化拖拽与浏览器文本选择 |
| `mouse_scroll` | 鼠标滚轮上下滚动 |
| `mouse_position` | 读取当前虚拟光标或真实光标坐标 |
| `mouse_screenshot` | 浏览器当前标签页或 Windows 全屏截图 |
| `computer_observe` | 全屏截图 + 任务栏、窗口、显示器、浏览器视口等视觉元数据 |
| `browser_open` | 在云端 Playwright 浏览器打开 HTTP(S) 页面 |
| `mouse_stop` | 紧急停止、释放按键、清空动作队列 |
| `mouse_status` | 查看自动路由、扩展心跳和失败状态 |

所有鼠标动作共用同一套 MCP 参数，Agent 不传环境参数。`computer_observe` 提供截图给模型做视觉识别，形成“观察 → 定位 → 动作 → 再观察”的 computer-use 闭环。

## 安全机制

- 每次移动、点击、拖拽和滚动都使用曲线轨迹，并附加 `0.2` 到 `1.3` 秒随机停顿。
- `mouse_click` 最多自动重试 2 次。连续 3 次操作失败后直接紧急停止。
- 全局 `ESC` 监听会设置当前动作取消标志、清空排队任务，并通知浏览器扩展停止。
- Windows 坐标限制在虚拟屏幕范围内。浏览器点击、拖拽、滚动的目标越界时直接拒绝；普通移动会夹取到视口边界。
- 删除、清空、格式化、批量提交、关闭全部等语义会触发 MCP elicitation。没有用户明确批准就不执行。
- 浏览器页面还可用 `data-openmouse-risk="high"` 标记高风险控件。

## 目录

```text
src/mouse_mcp/           Python MCP 服务、云浏览器、桌面视觉观察、自动路由
browser-extension/       Chromium MV3 扩展、网页虚拟鼠标、截图
demo/                    浏览器人工测试页
docs/                    架构、部署、Agent 提示词、工具与风险文档
examples/                OpenClaw 和通用 MCP 配置
scripts/                 Windows 安装、注册和检查脚本
tests/                   单元测试、浏览器 E2E、stdio E2E
codex/                   Codex Skill 源文件
Dockerfile               云端 Playwright Chromium 镜像
```

## 快速开始

### 作为 Codex 插件安装

先安装 Python 依赖：

```powershell
python -m pip install "git+https://github.com/osca5771666/openmouse-mcp.git"
```

再从 GitHub marketplace 安装插件：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-codex-plugin.ps1
```

等价命令：

```powershell
codex plugin marketplace add osca5771666/openmouse-mcp --ref main
codex plugin add openmouse@openmouse
```

插件会同时注册 `openmouse` MCP 和 `openmouse-computer-use` Skill。新开 Codex 会话后生效。

### 从源码安装

在 PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

然后：

1. 打开 `chrome://extensions`，启用开发者模式，选择“加载已解压的扩展程序”，目录选 `browser-extension`。
2. 打开扩展选项，填入安装脚本输出的浏览器令牌。
3. 运行 `.\.venv\Scripts\python.exe -m mouse_mcp --diagnose` 验证桥状态。
4. 运行 `scripts\install-codex-plugin.ps1` 安装 Codex 插件，或按 [OpenClaw 部署说明](docs/DEPLOYMENT.md) 注册其他 MCP 宿主。
5. 将 [Agent 系统提示词](docs/AGENT_SYSTEM_PROMPT.md) 加入 Agent 的系统提示词或工作区说明。
6. 云端使用 [CLOUD.md](docs/CLOUD.md) 的 Streamable HTTP 或 Docker 配置。

## 已验证

- Python 单元测试：32 项通过。
- Node 人类化轨迹测试：3 项通过。
- Chromium 真实扩展 E2E：单击、双击、拖拽选择、滚动、截图、高风险拦截通过。
- MCP `stdio` E2E：初始化、10 个工具发现、桌面观察和截图通过。
- 云端 Playwright E2E：页面打开、可信点击、截图通过。
- 云 HTTP E2E：Bearer 鉴权、Streamable HTTP、云端页面操作通过。
- Windows 桌面观察：任务栏矩形、活动窗口、显示器、窗口清单和 1920×1200 截图通过。
- Codex 0.147.0：真实 `tool_search` 发现和 `mouse_status` / `computer_observe` 调用通过。

## 文档

- [整体架构](docs/ARCHITECTURE.md)
- [云端与本地双模式](docs/CLOUD.md)
- [Codex 适配](docs/CODEX.md)
- [MCP 工具接口](docs/MCP_TOOLS.md)
- [部署教程](docs/DEPLOYMENT.md)
- [Agent 系统提示词](docs/AGENT_SYSTEM_PROMPT.md)
- [测试用例](docs/TEST_CASES.md)
- [风险说明](docs/RISK.md)

## 许可

MIT
