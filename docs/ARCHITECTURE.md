# 整体架构

## 目标

OpenMouse MCP 让 Agent 用一套工具名和参数控制三个执行面：

1. 浏览器页面内的虚拟鼠标。
2. Windows 操作系统上的真实硬件鼠标。
3. 云端 MCP 进程内的 Playwright Chromium。

本地插件随 Agent 以 stdio 启动。云端可以把同一个 MCP 进程暴露为 Streamable HTTP，并由进程自己启动浏览器。

## 组件

```text
Agent / Codex / OpenClaw
       |
       | stdio or Streamable HTTP
       v
openmouse-mcp Python process
  |-- MCP tool registry
  |-- action scheduler + ESC emergency stop
  |-- safety classifier + MCP elicitation
  |-- environment router
  |-- screenshot normalization
  |
  |-- PyAutoGUI -----------------------> Windows desktop
  |
  |-- Playwright Chromium ------------> Cloud browser
  |
  `-- loopback WebSocket 127.0.0.1:8765
           ^
           |
      Chromium extension
        |-- background service worker
        |-- page content script
        `-- page-level virtual cursor
```

Python 进程是 Agent 的 MCP 子进程，随 Agent 加载和退出。浏览器扩展只是插件自带的前端适配器，不提供独立业务后台。

## 启动方式

Agent 执行：

```text
<venv-python> -m mouse_mcp
```

进程启动后：

1. 在 `127.0.0.1:8765` 启动插件内 WebSocket 桥。
2. 创建串行动作队列。
3. 在 Windows 上启动 PyAutoGUI 驱动和全局 ESC 监听。
4. 通过 MCP `stdio` 暴露 11 个工具。
5. 浏览器扩展主动连接桥，并每秒发送一次心跳。

云端可执行：

```text
python -m mouse_mcp --transport streamable-http --host 0.0.0.0 --port 8766 --cloud-browser
```

设置 `MOUSE_MCP_HTTP_TOKEN` 后，`/mcp` 使用 Bearer Token；`/healthz` 不要求鉴权。

桥只绑定回环地址。扩展必须提供与服务端一致的共享令牌，否则握手被拒绝。

## 自动环境选择

路由器按以下顺序判断：

1. 如果配置为调试强制模式，使用指定环境。
2. 如果扩展心跳新鲜、浏览器窗口处于焦点，且 Windows 前台进程属于 Chrome、Edge、Brave、Firefox、Opera、Vivaldi 或 Chromium，则选择浏览器。
3. 如果云浏览器显式启用，或当前不是 Windows 且 Playwright 可用，则选择云端 Chromium。
4. 否则，如果当前系统是 Windows 且 PyAutoGUI 可用，则选择桌面。
5. 在非 Windows 主机上，如果浏览器心跳有效，则选择浏览器。
6. 都不可用时返回明确错误。

默认配置是 `MOUSE_MCP_ENV=auto`。Agent 不需要传入环境字段。`browser`、`desktop` 和 `cloud` 可用于诊断或自动化测试。

这种路由意味着：当 Agent 自己的窗口在前台时，操作真实桌面；当用户已把受控 Chromium 标签页切到前台时，操作网页虚拟鼠标。每一次工具调用都会重新判断，避免一次失败后卡在旧环境。

## 浏览器端动作

扩展后台服务接收 WebSocket 命令，并把动作发给当前活动标签页的内容脚本。

内容脚本负责：

- 创建 `pointer-events: none` 的 Shadow DOM 虚拟光标。
- 用三次贝塞尔曲线、抖动和随机停顿生成轨迹。
- 在目标位置派发 `pointerdown`、`mousedown`、`pointermove`、`mousemove`、`pointerup`、`mouseup` 和 `click` 或 `contextmenu` 事件。
- 双击执行两次点击序列并派发 `dblclick`。
- 拖拽过程中持续派发移动事件，必要时通过 Selection API 选择文本。
- 在页面内监听 `Escape`，立即取消动画和拖拽，并把紧急停止消息发给 MCP 进程。
- 在派发危险动作前读取目标文本、`aria-label`、标题和表单规模，发现高风险目标时返回 `blocked`。

浏览器截图由扩展 service worker 调用 `chrome.tabs.captureVisibleTab`。截图前隐藏虚拟光标，截图后恢复。

## 云端浏览器

`CloudBrowserDriver` 在 ActionRunner 线程内启动 Playwright persistent context。它使用浏览器协议派发可信鼠标事件：

- `page.mouse.move` 执行人类化轨迹。
- `page.mouse.click` 支持单击、双击和右键。
- `page.mouse.down/move/up` 执行拖拽。
- `page.mouse.wheel` 执行滚动。
- `page.screenshot` 返回视口截图。

`browser_open` 只接受 HTTP(S) URL。云浏览器的 Cookie 和会话与本地浏览器相互隔离。

## Windows 端动作

桌面驱动使用 PyAutoGUI：

- `moveTo` 逐点执行 Python 贝塞尔轨迹，没有坐标瞬移。
- `fast` 档保留贝塞尔曲线和轻微抖动，但把常见移动压缩到约 `0.1` 到 `0.38` 秒，普通动作间隔为 `0.04` 到 `0.16` 秒。
- 单击和双击前先完成人类化移动。
- 拖拽使用 `mouseDown`、轨迹移动和 `finally` 中的 `mouseUp`，保证异常时释放按键。
- 滚动按每次一个滚轮档位分片执行。
- 截图使用 `pyautogui.screenshot()` 获取全屏 PNG。
- `computer_observe` 同时枚举活动窗口、任务栏矩形、显示器、可见窗口和 PID。

`pynput` 全局监听 ESC。按 ESC 后，当前动作的取消事件被置位，队列中的任务全部失败返回，已按下的鼠标键被释放。

## 动作队列与失败保护

所有动作进入单线程串行队列，防止 Agent 并发点击互相干扰。

一次 `mouse_click` 最多执行三次尝试，即首次加两次重试。每次失败会清除按键状态。连续三个工具操作失败时，运行时直接触发紧急停止。

超时或响应丢失后的重试可能重复执行已经到达页面的非幂等动作。Agent 提示词要求使用截图验证，风险说明也明确记录这一限制。

## 高风险确认

服务端首先检查 Agent 提供的 `intent` 和 `target_description`。浏览器端还会检查实际 DOM 目标。

发现高风险后，工具调用挂起并通过 MCP elicitation 请求明确批准：

```text
高风险动作 -> 用户拒绝/取消 -> 不执行
高风险动作 -> 用户批准 -> 带 risk_approved 重试一次
```

MCP 客户端不支持 elicitation 时，服务端失败关闭，动作不执行。插件没有“忽略确认”的工具参数。

## 截图坐标约定

浏览器工具使用 CSS 视口像素。截图返回：

```json
{
  "image_width": 1536,
  "image_height": 960,
  "viewport_width": 1280,
  "viewport_height": 800,
  "device_pixel_ratio": 1.2,
  "coordinate_space": "CSS viewport pixels"
}
```

将截图坐标映射到工具坐标：

```text
x_css = x_image * viewport_width / image_width
y_css = y_image * viewport_height / image_height
```

Windows 桌面截图和 PyAutoGUI 使用物理桌面像素。`computer_observe` 会把 Win32 窗口矩形换算到相同的物理像素空间，并报告 DPI 比例。

## 线程模型

| 线程 | 职责 |
| --- | --- |
| MCP 事件循环 | 接收工具调用、elicitation、返回图片 |
| ActionRunner worker | 串行执行鼠标动作和人类化停顿 |
| Browser bridge server | 接受扩展连接和心跳 |
| Browser connection handler | 解析扩展响应与紧急停止 |
| pynput listener | 全局 ESC |

阻塞的 PyAutoGUI 动作通过 AnyIO worker 调回异步 MCP 工具层，避免堵住 MCP 主事件循环。

## 边界

- 浏览器内容脚本默认只运行在顶层页面，不直接进入跨域 iframe 内部。
- 合成 DOM 事件不是浏览器可信输入。依赖 `event.isTrusted` 的页面可能拒绝操作。
- 浏览器右键的合成 `contextmenu` 通常不能打开浏览器原生菜单。
- 截图不包含浏览器地址栏和标签栏，只包含当前视口。
- 受限页面，例如 `chrome://`、扩展商店和部分 PDF 查看器，禁止内容脚本或截图。
- 云端 MCP 不能直接越过网络控制用户本机鼠标；本机控制必须运行本地 stdio 插件。
- 云端 HTTP 必须放在 TLS 反向代理后，并设置 Bearer Token 和 Host 白名单。
