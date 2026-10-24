# 测试用例

## 自动测试

运行全部快速测试：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

运行完整浏览器与 stdio E2E：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1 -BrowserE2E -CloudE2E -CloudHttpE2E -StdioE2E
```

或者单独执行：

```powershell
$env:PYTHONPATH = "src"
python -m pytest
node --test browser-extension/tests/humanize.test.mjs
python tests/e2e_browser.py
python tests/e2e_cloud.py
python tests/e2e_cloud_http.py
python tests/e2e_stdio.py
```

`tests/e2e_browser.py` 会启动可见的 Chromium 窗口并加载未打包扩展。它只操作网页虚拟鼠标。E2E 截图写入 `.runtime/browser-e2e.png`。

## 用例 01：截图定位并单击

前置条件：

```powershell
py -m http.server 8099 --directory demo
```

打开 `http://127.0.0.1:8099/browser-demo.html`。

Agent 高层计划：

1. 调用 `computer_observe`。
2. 观察蓝色 “Save note” 按钮。
3. 根据截图尺寸换算 CSS 坐标。
4. 调用 `mouse_click`，`intent` 为 “click Save note”。
5. 再截图并确认 Save count 增加。

预期：

- 光标曲线移动，不瞬移。
- 页面计数增加。
- 动作后至少有 0.2 秒停顿。

## 用例 02：左键双击

页面初始 Save count 为 0。

调用：

```json
{
  "x": 140,
  "y": 285,
  "button": "left",
  "clicks": 2,
  "intent": "double click Save note",
  "target_description": "Save note"
}
```

预期：

- 光标先移动。
- 两次 click 序列和一次 dblclick 被派发。
- 测试页 Save count 增加 2。

## 用例 03：拖拽选择文本

调用 `mouse_drag` 从 Editor 第一行左侧拖到右侧。

预期：

- 移动过程中持续派发 `pointermove` 和 `mousemove`。
- 普通文本区域形成非空 Selection。
- 页面 Selection length 大于 0。
- 结束或 ESC 后不残留按下状态。

## 用例 04：滚动

在 Scrollable panel 内执行 `mouse_scroll(direction="down", clicks=4)`。

预期：

- 先派发 wheel 事件。
- 可滚动祖先执行滚动。
- 页面 Scroll position 增加。

## 用例 05：高风险点击被拦截

目标：“Delete all records” 按钮，该按钮带有 `data-openmouse-risk="high"`。

Agent 调用 `mouse_click`，`intent` 明确写为 “delete all records”。

预期：

- 首次调用返回 `blocked: true`，并包含 DOM 证据。
- MCP 发起用户确认。
- 用户拒绝后页面按钮不执行动作。
- 用户批准后才允许再次派发。

## 用例 06：ESC 清空动作队列

1. 让 Agent 发起长距离移动或拖拽。
2. 动作进行中按 ESC。
3. 紧接着调用 `mouse_position`。

预期：

- 当前轨迹立即结束。
- 当前工具返回取消错误。
- 排队动作全部不执行。
- 浏览器和桌面均不存在残留按键。

## 用例 07：边界保护

浏览器：

```json
{"x": -20, "y": 30}
```

调用 `mouse_move` 时夹取到视口内。

调用 `mouse_click` 或 `mouse_drag` 使用越界目标时直接拒绝，不点击边缘。

Windows：

- 移动目标会被夹取到虚拟屏幕范围。
- 点击和拖拽目标越界会返回边界错误。

## 用例 08：自动路由

1. 打开扩展并聚焦受控 Chromium 页面，调用 `mouse_status`，预期 `environment=browser`。
2. 将焦点切到记事本，再调用 `mouse_status`，预期 `environment=desktop`。
3. 不修改任何工具参数。

## 用例 09：单击重试与连续失败停止

在测试环境注入一个前两次必然抛错、第三次成功的点击驱动，确认首次操作最终成功，后续失败计数清零。

再注入连续三个操作全部失败的驱动，确认第三次失败后 `mouse_stop` 被自动触发，队列清空，后续任务返回取消。

## 用例 10：Windows 真鼠标最小验证

1. 将 `MOUSE_MCP_ENV=desktop` 仅用于隔离测试。
2. 打开空白记事本。
3. 调用 `mouse_position` 验证坐标读取。
4. 调用 `computer_observe` 验证全屏截图、任务栏和窗口矩形。
5. 先只测试小距离移动。
6. 人工确认轨迹、多显示器边界、ESC 和坐标缩放。

预期：

- 光标平滑移动。
- 不离开虚拟屏幕。
- 截图包含整个桌面。
- ESC 立即停止。

## 用例 11：MCP 宿主兼容

运行：

```powershell
python tests/e2e_stdio.py
```

预期：

- 服务名 `openmouse-mcp`。
- 工具数量 11。
- `mouse_status` 可调用。
- Agent 断开后 MCP 子进程退出。

## 用例 12：云端 Playwright 与 HTTP 鉴权

运行：

```powershell
python tests/e2e_cloud.py
python tests/e2e_cloud_http.py
```

预期：

- `environment=cloud`。
- `browser_open` 打开测试页。
- Playwright 点击被标记为可信事件。
- `/healthz` 无鉴权返回 200。
- 无 Authorization 的 MCP 请求返回 401。
- 正确 Bearer Token 能连接并调用 `computer_observe`。

## 用例 13：任务栏视觉操作

1. 让 Agent 调用 `computer_observe`。
2. 确认返回 `desktop_context.taskbars[0].rect`。
3. 从截图中识别一个明确的测试应用图标。
4. 仅在人工监督下点击并再次观察活动窗口。

预期：

- 截图和任务栏矩形使用同一物理像素坐标。
- 点击后活动窗口或任务栏状态发生预期变化。
- 误点或焦点异常时 ESC 能停止。

## 用例 14：Codex 原生发现与调用

```powershell
codex mcp get openmouse --json
```

新开 Codex 会话并发送：

```text
先 tool_search 搜索 openmouse computer_observe mouse_status，然后只调用 mouse_status，不要移动鼠标。
```

预期：

- `openmouse` 已启用。
- Agent 通过 `tool_search` 发现 MCP 工具。
- MCP 工具调用事件显示 `server=openmouse`。
- 返回 `environment=desktop`（本地 Windows 前台不是受控浏览器时）。

## 验收记录模板

```text
日期：
Windows 版本：
浏览器版本：
MCP 宿主：
模型：
测试环境：browser / desktop / cloud
用例：
工具结果：
截图路径：
是否触发确认：
是否触发 ESC：
残余风险：
```
