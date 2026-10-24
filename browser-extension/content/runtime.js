(() => {
  "use strict";

  if (globalThis.__openMouseMcpInstalled) {
    return;
  }
  globalThis.__openMouseMcpInstalled = true;

  const { clamp, createTrajectory, randomBetween } = globalThis.MouseMcpHumanize;
  const state = {
    x: Math.max(0, window.innerWidth / 2),
    y: Math.max(0, window.innerHeight / 2),
    epoch: 0,
    activeDrag: null,
    cursorVisible: true,
  };

  const overlayHost = document.createElement("div");
  overlayHost.setAttribute("data-openmouse-cursor", "true");
  Object.assign(overlayHost.style, {
    position: "fixed",
    inset: "0",
    width: "0",
    height: "0",
    pointerEvents: "none",
    zIndex: "2147483647",
    overflow: "visible",
  });
  const shadow = overlayHost.attachShadow({ mode: "closed" });
  const cursor = document.createElement("div");
  cursor.setAttribute("aria-hidden", "true");
  Object.assign(cursor.style, {
    position: "fixed",
    left: "0",
    top: "0",
    width: "20px",
    height: "20px",
    borderRadius: "50%",
    border: "2px solid #ff5a36",
    background:
      "radial-gradient(circle at center, #ff5a36 0 2px, transparent 3px)",
    boxShadow: "0 0 0 1px rgba(255,255,255,.85), 0 1px 5px rgba(0,0,0,.35)",
    transform: `translate(${state.x - 10}px, ${state.y - 10}px)`,
    transition: "opacity 80ms linear",
    willChange: "transform",
  });
  shadow.appendChild(cursor);
  const appendOverlay = () => {
    if (document.documentElement && !overlayHost.isConnected) {
      document.documentElement.appendChild(overlayHost);
    }
  };
  appendOverlay();

  const sleep = (milliseconds) =>
    new Promise((resolve) => window.setTimeout(resolve, milliseconds));

  const finiteCoordinate = (value, fallback) => {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  };

  const assertInsideViewport = (x, y) => {
    const width = Math.max(0, window.innerWidth - 1);
    const height = Math.max(0, window.innerHeight - 1);
    if (
      !Number.isFinite(Number(x)) ||
      !Number.isFinite(Number(y)) ||
      Number(x) < 0 ||
      Number(y) < 0 ||
      Number(x) > width ||
      Number(y) > height
    ) {
      const error = new Error(
        `Target (${x}, ${y}) is outside the viewport bounds 0..${width}, 0..${height}.`,
      );
      error.code = "BOUNDARY_VIOLATION";
      throw error;
    }
  };

  const updateCursor = (x, y) => {
    state.x = clamp(x, 0, Math.max(0, window.innerWidth - 1));
    state.y = clamp(y, 0, Math.max(0, window.innerHeight - 1));
    cursor.style.transform = `translate(${state.x - 10}px, ${state.y - 10}px)`;
  };

  const setCursorVisible = (visible) => {
    state.cursorVisible = Boolean(visible);
    cursor.style.display = state.cursorVisible ? "block" : "none";
    cursor.style.opacity = state.cursorVisible ? "1" : "0";
    return new Promise((resolve) => {
      window.setTimeout(
        () => resolve({ visible: state.cursorVisible }),
        state.cursorVisible ? 32 : 100,
      );
    });
  };

  const throwIfCancelled = (epoch) => {
    if (epoch !== state.epoch) {
      const error = new Error("Mouse action cancelled.");
      error.code = "CANCELLED";
      throw error;
    }
  };

  const moveTo = async (targetX, targetY, onFrame) => {
    const epoch = state.epoch;
    const clamped = {
      x: clamp(
        finiteCoordinate(targetX, state.x),
        0,
        Math.max(0, window.innerWidth - 1),
      ),
      y: clamp(
        finiteCoordinate(targetY, state.y),
        0,
        Math.max(0, window.innerHeight - 1),
      ),
    };
    const start = { x: state.x, y: state.y };
    const trajectory = createTrajectory(start, clamped);
    for (const step of trajectory) {
      throwIfCancelled(epoch);
      if (step.delay > 0) {
        await sleep(step.delay * 1000);
      }
      throwIfCancelled(epoch);
      updateCursor(step.point.x, step.point.y);
      if (onFrame) {
        onFrame({ x: state.x, y: state.y });
      }
    }
    return {
      x: Math.round(state.x),
      y: Math.round(state.y),
      clamped:
        Math.round(clamped.x) !== Math.round(Number(targetX)) ||
        Math.round(clamped.y) !== Math.round(Number(targetY)),
    };
  };

  const elementAt = (x, y) =>
    document.elementFromPoint(
      clamp(Math.round(x), 0, Math.max(0, window.innerWidth - 1)),
      clamp(Math.round(y), 0, Math.max(0, window.innerHeight - 1)),
    );

  const riskPattern =
    /删除|永久删除|抹除|清空|格式化|恢复出厂|批量提交|全部提交|提交全部|关闭全部|全部关闭|关闭所有|批量删除|批量关闭|覆盖全部|注销账户|\bdelete\b|\bpermanent(?:ly)? delete\b|\berase\b|\bformat\b|\bremove all\b|\bclear all\b|\bsubmit all\b|\bbulk submit\b|\bclose all\b|\bdelete all\b|\bwipe\b|\boverwrite all\b|\bdeactivate account\b/i;

  const describeElement = (element) => {
    if (!element) {
      return "";
    }
    const semantic = element.closest(
      "button, a, input, textarea, select, [role='button'], [role='link'], [role='menuitem']",
    );
    const node = semantic || element;
    return [
      node.innerText,
      node.textContent,
      node.getAttribute?.("aria-label"),
      node.getAttribute?.("title"),
      node.getAttribute?.("name"),
      node.getAttribute?.("value"),
      node.getAttribute?.("data-openmouse-risk"),
    ]
      .filter(Boolean)
      .join(" ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 600);
  };

  const detectRisk = (element, params) => {
    const evidence = [];
    const elementRisk = element?.closest?.("[data-openmouse-risk='high']");
    if (elementRisk) {
      evidence.push("target is marked data-openmouse-risk=high");
    }
    const combined = [
      describeElement(element),
      String(params.intent || ""),
      String(params.target_description || ""),
    ]
      .filter(Boolean)
      .join(" | ");
    const match = combined.match(riskPattern);
    if (match) {
      const start = Math.max(0, (match.index || 0) - 24);
      evidence.push(combined.slice(start, start + 180).trim());
    }
    const form = element?.closest?.("form");
    if (
      form &&
      (element?.matches?.("[type='submit'], button:not([type])") ||
        element?.closest?.("[type='submit'], button:not([type])")) &&
      form.querySelectorAll("input, select, textarea").length >= 10
    ) {
      evidence.push("submit control belongs to a form with 10 or more fields");
    }
    return [...new Set(evidence)];
  };

  const mouseEventOptions = (button, buttons, detail) => ({
    bubbles: true,
    cancelable: true,
    composed: true,
    view: window,
    clientX: state.x,
    clientY: state.y,
    screenX: window.screenX + state.x,
    screenY: window.screenY + state.y,
    button,
    buttons,
    detail,
    pointerId: 1,
    pointerType: "mouse",
    isPrimary: true,
  });

  const fireMouseSequence = (target, button, detail) => {
    if (!target) {
      throw new Error("No DOM element exists at the requested browser coordinate.");
    }
    const buttonCode = button === "right" ? 2 : 0;
    const downButtons = button === "right" ? 2 : 1;
    target.dispatchEvent(
      new PointerEvent(
        "pointerdown",
        mouseEventOptions(buttonCode, downButtons, detail),
      ),
    );
    target.dispatchEvent(
      new MouseEvent(
        "mousedown",
        mouseEventOptions(buttonCode, downButtons, detail),
      ),
    );
    target.dispatchEvent(
      new PointerEvent("pointerup", mouseEventOptions(buttonCode, 0, detail)),
    );
    target.dispatchEvent(
      new MouseEvent("mouseup", mouseEventOptions(buttonCode, 0, detail)),
    );
    if (button === "right") {
      target.dispatchEvent(
        new MouseEvent(
          "contextmenu",
          mouseEventOptions(buttonCode, 0, detail),
        ),
      );
    } else {
      const nativeTarget = target.closest?.(
        "a[href], button, input, label, summary, option",
      );
      if (nativeTarget && typeof nativeTarget.click === "function") {
        nativeTarget.click();
      } else {
        target.dispatchEvent(
          new MouseEvent("click", mouseEventOptions(buttonCode, 0, detail)),
        );
      }
    }
  };

  const click = async (params) => {
    if (params.x !== null && params.x !== undefined) {
      assertInsideViewport(params.x, params.y);
      await moveTo(params.x, params.y);
    }
    const target = elementAt(state.x, state.y);
    const evidence = detectRisk(target, params);
    if (evidence.length && !params.risk_approved) {
      return {
        blocked: true,
        message: "High-risk browser target detected before dispatch.",
        evidence,
      };
    }
    const button = params.button === "right" ? "right" : "left";
    const clicks = Number(params.clicks) === 2 ? 2 : 1;
    for (let count = 1; count <= clicks; count += 1) {
      fireMouseSequence(target, button, count);
      if (count < clicks) {
        await sleep(randomBetween(70, 145));
      }
    }
    if (clicks === 2) {
      target.dispatchEvent(
        new MouseEvent("dblclick", mouseEventOptions(0, 0, 2)),
      );
    }
    return {
      x: Math.round(state.x),
      y: Math.round(state.y),
      button,
      clicks,
      target: describeElement(target).slice(0, 200),
      trusted_events: false,
      warning:
        button === "right"
          ? "Synthetic contextmenu events may not open native browser menus."
          : undefined,
    };
  };

  const dispatchDragMove = (x, y, button) => {
    const target = elementAt(x, y);
    if (!target) {
      return;
    }
    const buttonCode = button === "right" ? 2 : 0;
    const buttons = button === "right" ? 2 : 1;
    target.dispatchEvent(
      new PointerEvent("pointermove", mouseEventOptions(buttonCode, buttons, 0)),
    );
    target.dispatchEvent(
      new MouseEvent("mousemove", mouseEventOptions(buttonCode, buttons, 0)),
    );
  };

  const releaseDrag = () => {
    const drag = state.activeDrag;
    if (!drag) {
      return;
    }
    state.activeDrag = null;
    const target = drag.lastTarget || elementAt(state.x, state.y);
    if (!target) {
      return;
    }
    const buttonCode = drag.button === "right" ? 2 : 0;
    target.dispatchEvent(
      new PointerEvent("pointerup", mouseEventOptions(buttonCode, 0, 0)),
    );
    target.dispatchEvent(
      new MouseEvent("mouseup", mouseEventOptions(buttonCode, 0, 0)),
    );
  };

  const trySelectText = (from, to) => {
    if (
      typeof document.caretRangeFromPoint !== "function" ||
      !window.getSelection
    ) {
      return false;
    }
    const start = document.caretRangeFromPoint(from.x, from.y);
    const end = document.caretRangeFromPoint(to.x, to.y);
    if (!start || !end) {
      return false;
    }
    const selection = window.getSelection();
    if (!selection) {
      return false;
    }
    try {
      selection.setBaseAndExtent(
        start.startContainer,
        start.startOffset,
        end.startContainer,
        end.startOffset,
      );
      return !selection.isCollapsed;
    } catch (_error) {
      return false;
    }
  };

  const drag = async (params) => {
    assertInsideViewport(params.from_x, params.from_y);
    assertInsideViewport(params.to_x, params.to_y);
    const risk = detectRisk(elementAt(params.from_x, params.from_y), params);
    if (risk.length && !params.risk_approved) {
      return {
        blocked: true,
        message: "High-risk browser drag detected before dispatch.",
        evidence: risk,
      };
    }
    await moveTo(params.from_x, params.from_y);
    const startTarget = elementAt(state.x, state.y);
    if (!startTarget) {
      throw new Error("No DOM element exists at the drag start coordinate.");
    }
    const button = params.button === "right" ? "right" : "left";
    const buttonCode = button === "right" ? 2 : 0;
    const buttons = button === "right" ? 2 : 1;
    startTarget.dispatchEvent(
      new PointerEvent("pointerdown", mouseEventOptions(buttonCode, buttons, 0)),
    );
    startTarget.dispatchEvent(
      new MouseEvent("mousedown", mouseEventOptions(buttonCode, buttons, 0)),
    );
    state.activeDrag = { button, lastTarget: startTarget };
    const from = { x: state.x, y: state.y };
    try {
      const result = await moveTo(params.to_x, params.to_y, (point) => {
        dispatchDragMove(point.x, point.y, button);
        if (state.activeDrag) {
          state.activeDrag.lastTarget =
            elementAt(point.x, point.y) || state.activeDrag.lastTarget;
        }
      });
      releaseDrag();
      const canSelectText = !startTarget.closest?.(
        "canvas, input, textarea, select, button, a",
      );
      const selected =
        canSelectText &&
        trySelectText(from, { x: state.x, y: state.y });
      return {
        from: {
          x: Math.round(from.x),
          y: Math.round(from.y),
        },
        to: { x: Math.round(result.x), y: Math.round(result.y) },
        button,
        text_selected: selected,
        clamped: result.clamped,
      };
    } finally {
      releaseDrag();
    }
  };

  const isScrollable = (element) => {
    if (!element || element === document.documentElement || element === document.body) {
      return false;
    }
    const style = getComputedStyle(element);
    return (
      ["auto", "scroll"].includes(style.overflowY) &&
      element.scrollHeight > element.clientHeight + 1
    );
  };

  const scroll = async (params) => {
    if (params.x !== null && params.x !== undefined) {
      assertInsideViewport(params.x, params.y);
      await moveTo(params.x, params.y);
    }
    const target = elementAt(state.x, state.y);
    const risk = detectRisk(target, params);
    if (risk.length && !params.risk_approved) {
      return {
        blocked: true,
        message: "High-risk browser scroll target detected before dispatch.",
        evidence: risk,
      };
    }
    const direction = params.direction === "up" ? "up" : "down";
    const clicks = clamp(Number(params.clicks) || 3, 1, 20);
    const deltaY = (direction === "down" ? 1 : -1) * clicks * 110;
    const wheel = new WheelEvent("wheel", {
      bubbles: true,
      cancelable: true,
      composed: true,
      clientX: state.x,
      clientY: state.y,
      deltaY,
      deltaMode: 0,
    });
    const notPrevented = target?.dispatchEvent(wheel) ?? true;
    let scrolledElement = "window";
    if (notPrevented) {
      let scrollTarget = target;
      while (scrollTarget && !isScrollable(scrollTarget)) {
        scrollTarget = scrollTarget.parentElement;
      }
      if (scrollTarget) {
        scrollTarget.scrollBy({ top: deltaY, behavior: "smooth" });
        scrolledElement = describeElement(scrollTarget).slice(0, 120) || "element";
      } else {
        window.scrollBy({ top: deltaY, behavior: "smooth" });
      }
    }
    return {
      direction,
      clicks,
      delta_y: deltaY,
      scrolled_element: scrolledElement,
      page_scroll_y: window.scrollY,
    };
  };

  const viewport = () => ({
    width: window.innerWidth,
    height: window.innerHeight,
    device_pixel_ratio: window.devicePixelRatio || 1,
    scroll_x: window.scrollX,
    scroll_y: window.scrollY,
  });

  const abort = () => {
    state.epoch += 1;
    releaseDrag();
    return { stopped: true };
  };

  const handleCommand = async (command) => {
    const action = command.action;
    const params = command.params || {};
    if (action === "stop") {
      return abort();
    }
    if (action === "move") {
      return moveTo(params.x, params.y);
    }
    if (action === "click") {
      return click(params);
    }
    if (action === "drag") {
      return drag(params);
    }
    if (action === "scroll") {
      return scroll(params);
    }
    if (action === "position") {
      return {
        x: Math.round(state.x),
        y: Math.round(state.y),
        ...viewport(),
      };
    }
    if (action === "viewport") {
      return viewport();
    }
    if (action === "cursor_visibility") {
      return setCursorVisible(params.visible);
    }
    throw new Error(`Unsupported browser mouse action: ${action}`);
  };

  document.addEventListener(
    "keydown",
    (event) => {
      if (event.key !== "Escape") {
        return;
      }
      abort();
      try {
        chrome.runtime.sendMessage({
          type: "OPENMOUSE_EMERGENCY_STOP",
          reason: "browser_escape_key",
        });
      } catch (_error) {
        // The page-level abort still succeeds when the extension context is gone.
      }
    },
    true,
  );

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "OPENMOUSE_COMMAND") {
      return false;
    }
    handleCommand(message.command)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) =>
        sendResponse({
          ok: false,
          error: error?.message || String(error),
          code: error?.code || "BROWSER_ACTION_FAILED",
        }),
      );
    return true;
  });

  globalThis.__openMouseMcp = {
    abort,
    handleCommand,
    viewport,
  };
})();
