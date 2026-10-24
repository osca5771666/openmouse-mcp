---
name: openmouse-computer-use
description: Control the local Windows desktop or an embedded cloud Chromium browser with visual mouse tools. Use when Codex needs to observe a screen, operate a taskbar or application window, click/drag/scroll a webpage, use screenshots for GUI grounding, control the real mouse, or automate computer-use workflows through the OpenMouse MCP server.
---

# OpenMouse Computer Use

Use the `openmouse` MCP server for visual GUI control. It exposes one interface for:

- Windows desktop: real mouse, taskbar, applications, terminals, and full-screen capture.
- Attached local Chromium: page-level virtual cursor and tab screenshot.
- Cloud Chromium: embedded Playwright browser with trusted browser input.

## Discover The Tools

Codex may defer MCP tools behind Tool Search. If `mcp__openmouse__*` is not already visible, call `tool_search` with a query such as:

```text
openmouse computer_observe mouse_status
```

Then call the discovered tools directly. Read `mouse_status` only when routing is unclear.

## Fast Path For URLs

When the request is simply to open a known website, do not call `computer_observe`, locate a taskbar icon, or click the address bar. Use `browser_open` once with the absolute URL. Pass `browser="edge"` or `browser="chrome"` only when the user named that browser.

When the request is to open a known local application, use `app_open` directly. It focuses an existing window or launches from an alias/Start Menu shortcut without visual taskbar search.

## Observe First

Call `computer_observe` before any visual action. It returns a PNG plus JSON containing:

- `environment`: `desktop`, `browser`, or `cloud`.
- Screenshot size, viewport size, and coordinate space.
- On Windows: active window, taskbar rectangles, monitors, and visible windows.
- On browsers: current URL, title, viewport, and scroll position.

Do not guess coordinates from memory. Use the current image and metadata.

## Desktop Workflow

1. Call `computer_observe`.
2. Identify the taskbar icon, window title, button, or text in the screenshot.
3. Use `desktop_context.taskbars[].rect` and `visible_windows[].rect` as anchors.
4. Call `mouse_move` or `mouse_click` with physical screenshot coordinates.
5. Call `computer_observe` again and verify the window, taskbar, or application state changed.
6. Re-observe after focus changes, animations, app launches, or window movement.

For taskbar operations, inspect the current taskbar screenshot before clicking. Do not rely on icon order or remembered positions.

## Browser Workflow

For an attached local browser, convert screenshot pixels to CSS viewport pixels:

```text
x_css = x_image * viewport_width / image_width
y_css = y_image * viewport_height / image_height
```

For the cloud browser, call `browser_open` with an absolute HTTP(S) URL, then use the same `computer_observe` and `mouse_*` tools. `browser_open` is valid only when routing is already `cloud`.

## Action Rules

- Every click, drag, and scroll must include a concrete `intent`.
- Include the visible label in `target_description`.
- Perform one meaningful GUI step, then observe again.
- Do not issue parallel mouse actions.
- Treat stale screenshots as invalid after navigation, scrolling, resizing, or focus changes.
- Use `mouse_stop` on ambiguity, unexpected focus, or possible misclick.
- Press ESC as the user-facing emergency stop.

## High-Risk Actions

Deleting data, closing many windows, bulk form submission, overwriting files, account deactivation, and similar actions require explicit user confirmation through the MCP elicitation flow.

Do not rephrase, split, or retry around a denied confirmation. Mark custom page controls with `data-openmouse-risk="high"` when building test surfaces.

## Common Failure Modes

- Mixed-DPI monitors can shift rectangles. Re-observe after crossing monitors.
- Browser screenshots may be scaled by device pixel ratio.
- Synthetic local-browser events can be ignored by sites requiring trusted input.
- Cloud Playwright input is trusted, but the cloud browser has its own isolated cookies and session.
- A window may move between screenshot capture and click. Re-observe before irreversible actions.

Report the environment, the observed target, the action, and the post-action verification.
