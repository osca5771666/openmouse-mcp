# MCP 工具接口

服务名：`openmouse-mcp`

传输：`stdio`

全部坐标使用浮点或整数都可以。浏览器使用 CSS 视口像素，Windows 使用物理桌面像素。

## mouse_move

```json
{
  "x": 640,
  "y": 360
}
```

移动光标。目标超出边界时夹取到最近的有效坐标，并返回 `clamped: true`。

## mouse_click

```json
{
  "x": 720,
  "y": 410,
  "button": "left",
  "clicks": 1,
  "intent": "click Save note",
  "target_description": "Save note"
}
```

参数：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `x`, `y` | 否 | 都省略时点击当前光标位置 |
| `button` | 是 | `left` 或 `right` |
| `clicks` | 是 | `1` 或 `2`；双击只支持左键 |
| `intent` | 是 | 具体预期效果，不能是模糊描述 |
| `target_description` | 否 | 可见标签或辅助功能名称 |

单击最多自动重试 2 次。

## mouse_drag

```json
{
  "from_x": 300,
  "from_y": 280,
  "to_x": 760,
  "to_y": 280,
  "button": "left",
  "intent": "select the note sentence",
  "target_description": "note text"
}
```

浏览器端会派发连续拖拽事件，并在普通文本区域尝试用 Selection API 形成选择。

## mouse_scroll

```json
{
  "direction": "down",
  "clicks": 4,
  "intent": "scroll to the footer",
  "target_description": "page body"
}
```

`x`、`y` 可选。提供时先移动到该位置再滚动。`clicks` 范围是 `1` 到 `20`。

## mouse_position

无参数。返回：

```json
{
  "x": 640,
  "y": 400,
  "environment": "browser",
  "width": 1280,
  "height": 800,
  "device_pixel_ratio": 1.2
}
```

桌面模式返回 `screen_width`、`screen_height`。

## mouse_screenshot

无参数。MCP 返回一个文本内容和一个 PNG 图片内容。

文本示例：

```json
{
  "environment": "browser",
  "format": "png",
  "image_width": 1536,
  "image_height": 960,
  "viewport_width": 1280,
  "viewport_height": 800,
  "device_pixel_ratio": 1.2,
  "scroll_x": 0,
  "scroll_y": 0,
  "coordinate_space": "CSS viewport pixels"
}
```

Agent 应使用 `viewport_width / image_width` 和 `viewport_height / image_height` 把截图坐标换算为点击坐标。

## computer_observe

无参数。比 `mouse_screenshot` 返回更多用于视觉 computer-use 的上下文：

- Windows：截图、活动窗口、任务栏矩形、显示器、可见窗口和 DPI 缩放。
- 本地浏览器：截图、URL、标题、视口和滚动位置。
- 云端浏览器：当前页面截图和 Playwright 视口。

返回 MCP 文本元数据和一个 PNG 图片。

## browser_open

```json
{
  "url": "https://example.com/",
  "browser": "default"
}
```

快速打开绝对 HTTP(S) URL。Windows 本地使用 Shell 直接启动默认浏览器，也可以用 `browser="edge"` 或 `browser="chrome"` 指定浏览器，不执行截图、任务栏点击或地址栏自动化。云端模式则导航内嵌 Playwright 浏览器，并默认阻断内网地址。

## app_open

```json
{
  "name": "feishu"
}
```

快速聚焦已运行的本地应用，或通过可执行文件/开始菜单快捷方式启动。内置别名包括 `feishu`、`notepad`、`explorer`、`cmd`、`powershell`、`calculator`、`edge` 和 `chrome`。

## mouse_stop

无参数。取消当前动作、清空队列、释放鼠标键，并向浏览器扩展广播停止。

## mouse_status

无参数，只读。返回当前平台、路由、扩展心跳、视口、桌面可用性和连续失败次数。

## 错误语义

- 边界违规：目标在点击、拖拽或滚动前被拒绝。
- 高风险拦截：返回需要用户确认的信息；拒绝后不得绕过。
- 连续失败：第三次连续失败触发紧急停止。
- 环境不可用：提示启动扩展或检查 Windows/PyAutoGUI。
