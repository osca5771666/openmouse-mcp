const DEFAULT_SERVER_URL = "ws://127.0.0.1:8765";
const DEFAULT_TOKEN = "local-dev-token";
const CONTENT_FILES = [
  "content/humanize.js",
  "content/runtime.js",
  "content/content.js",
];

let socket = null;
let reconnectTimer = null;
let heartbeatTimer = null;
let reconnectDelay = 1000;
let connected = false;
let commandQueue = Promise.resolve();

const setBadge = (text, color) => {
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color });
};

const storageValues = async () => {
  const values = await chrome.storage.local.get(["serverUrl", "token"]);
  return {
    serverUrl: values.serverUrl || DEFAULT_SERVER_URL,
    token: values.token || DEFAULT_TOKEN,
  };
};

const sendJson = (payload) => {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    throw new Error("OpenMouse bridge is not connected.");
  }
  socket.send(JSON.stringify(payload));
};

const scheduleReconnect = () => {
  if (reconnectTimer) {
    return;
  }
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, reconnectDelay);
  reconnectDelay = Math.min(10000, reconnectDelay * 1.7);
};

const connect = async () => {
  if (
    socket &&
    (socket.readyState === WebSocket.OPEN ||
      socket.readyState === WebSocket.CONNECTING)
  ) {
    return;
  }
  const { serverUrl, token } = await storageValues();
  try {
    socket = new WebSocket(serverUrl);
  } catch (_error) {
    scheduleReconnect();
    return;
  }

  socket.addEventListener("open", () => {
    sendJson({
      type: "hello",
      token,
      client_id: `chromium-${crypto.randomUUID()}`,
      version: "1.0.1",
      user_agent: navigator.userAgent,
    });
  });

  socket.addEventListener("message", (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch (_error) {
      return;
    }
    if (message.type === "hello_ack") {
      connected = true;
      reconnectDelay = 1000;
      setBadge("ON", "#18794e");
      startHeartbeat();
      sendHeartbeat();
      return;
    }
    if (message.type === "hello_error") {
      setBadge("ERR", "#b42318");
      connected = false;
      return;
    }
    if (message.type === "stop") {
      broadcastStop(message.reason || "server_stop");
      return;
    }
    if (message.type === "command") {
      commandQueue = commandQueue
        .then(() => executeCommand(message))
        .catch((error) => {
          sendResponse(message.id, false, null, error?.message || String(error));
        });
    }
  });

  socket.addEventListener("close", () => {
    connected = false;
    stopHeartbeat();
    setBadge("", "#000000");
    scheduleReconnect();
  });

  socket.addEventListener("error", () => {
    try {
      socket.close();
    } catch (_error) {
      scheduleReconnect();
    }
  });
};

const startHeartbeat = () => {
  stopHeartbeat();
  heartbeatTimer = setInterval(sendHeartbeat, 1000);
};

const stopHeartbeat = () => {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
};

const activeTabContext = async () => {
  const [tab] = await chrome.tabs.query({
    active: true,
    lastFocusedWindow: true,
  });
  let browserWindow = null;
  try {
    browserWindow = await chrome.windows.getLastFocused({ populate: false });
  } catch (_error) {
    browserWindow = null;
  }
  return {
    tab,
    focused: Boolean(browserWindow?.focused),
    windowId: browserWindow?.id ?? tab?.windowId ?? null,
  };
};

const sendHeartbeat = async () => {
  if (!connected) {
    return;
  }
  try {
    const { tab, focused, windowId } = await activeTabContext();
    let viewport = {
      width: 0,
      height: 0,
      device_pixel_ratio: 1,
      scroll_x: 0,
      scroll_y: 0,
    };
    if (tab?.id && /^https?:/i.test(tab.url || "")) {
      try {
        const response = await sendToTab(tab.id, {
          action: "viewport",
          params: {},
        });
        if (response?.ok) {
          viewport = response.result;
        }
      } catch (_error) {
        // Heartbeats still describe the tab when a restricted page cannot answer.
      }
    }
    sendJson({
      type: "heartbeat",
      focused,
      window_id: windowId,
      tab_id: tab?.id ?? null,
      url: tab?.url || "",
      title: tab?.title || "",
      viewport,
    });
  } catch (_error) {
    // A later heartbeat will retry without tearing down the bridge.
  }
};

const sendResponse = (id, ok, result, error) => {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  sendJson({
    type: "response",
    id,
    ok,
    result: ok ? result || {} : undefined,
    error: ok ? undefined : error,
  });
};

const executeCommand = async (message) => {
  try {
    let result;
    if (message.action === "screenshot") {
      result = await captureScreenshot();
    } else if (message.action === "stop") {
      await broadcastStop(message.params?.reason || "server_stop");
      result = { stopped: true };
    } else {
      const { tab } = await activeTabContext();
      if (!tab?.id) {
        throw new Error("No active browser tab is available.");
      }
      if (!/^https?:/i.test(tab.url || "")) {
        throw new Error("The active tab is a restricted browser page.");
      }
      const response = await sendToTab(tab.id, {
        action: message.action,
        params: message.params || {},
      });
      if (!response?.ok) {
        throw new Error(response?.error || "Browser content script rejected the action.");
      }
      result = response.result;
    }
    sendResponse(message.id, true, result);
  } catch (error) {
    sendResponse(message.id, false, null, error?.message || String(error));
  }
};

const sendToTab = async (tabId, command) => {
  const message = { type: "OPENMOUSE_COMMAND", command };
  try {
    return await chrome.tabs.sendMessage(tabId, message);
  } catch (_error) {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: CONTENT_FILES,
    });
    return await chrome.tabs.sendMessage(tabId, message);
  }
};

const broadcastStop = async (reason) => {
  try {
    const tabs = await chrome.tabs.query({});
    await Promise.allSettled(
      tabs
        .filter((tab) => tab.id && /^https?:/i.test(tab.url || ""))
        .map((tab) =>
          chrome.tabs.sendMessage(tab.id, {
            type: "OPENMOUSE_COMMAND",
            command: { action: "stop", params: { reason } },
          }),
        ),
    );
  } catch (_error) {
    // The server-side queue has already been cleared.
  }
};

const hideCursor = async (tabId) => {
  try {
    await sendToTab(tabId, {
      action: "cursor_visibility",
      params: { visible: false },
    });
  } catch (_error) {
    // Screenshot capture can proceed without the optional cursor overlay.
  }
};

const showCursor = async (tabId) => {
  try {
    await sendToTab(tabId, {
      action: "cursor_visibility",
      params: { visible: true },
    });
  } catch (_error) {
    // The overlay returns with the next injected runtime.
  }
};

const captureScreenshot = async () => {
  const { tab, windowId } = await activeTabContext();
  if (!tab?.id || !windowId) {
    throw new Error("No active browser tab is available for capture.");
  }
  if (!/^https?:/i.test(tab.url || "")) {
    throw new Error("The active tab cannot be captured because it is a restricted page.");
  }
  let viewport = {
    width: tab.width || 0,
    height: tab.height || 0,
    device_pixel_ratio: 1,
    scroll_x: 0,
    scroll_y: 0,
  };
  try {
    const response = await sendToTab(tab.id, {
      action: "viewport",
      params: {},
    });
    if (response?.ok) {
      viewport = response.result;
    }
  } catch (_error) {
    // Use tab dimensions as a fallback.
  }
  await hideCursor(tab.id);
  let dataUrl;
  try {
    dataUrl = await chrome.tabs.captureVisibleTab(windowId, { format: "png" });
  } finally {
    await showCursor(tab.id);
  }
  let imageWidth = 0;
  let imageHeight = 0;
  try {
    const blob = await (await fetch(dataUrl)).blob();
    const bitmap = await createImageBitmap(blob);
    imageWidth = bitmap.width;
    imageHeight = bitmap.height;
    bitmap.close();
  } catch (_error) {
    // The image itself is still valid if dimensions cannot be decoded.
  }
  return {
    data_url: dataUrl,
    format: "png",
    image_width: imageWidth,
    image_height: imageHeight,
    viewport_width: viewport.width,
    viewport_height: viewport.height,
    device_pixel_ratio: viewport.device_pixel_ratio,
    scroll_x: viewport.scroll_x,
    scroll_y: viewport.scroll_y,
    coordinate_space:
      "CSS viewport pixels; scale screenshot pixels by viewport_width/image_width and viewport_height/image_height",
    url: tab.url,
    title: tab.title,
  };
};

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type !== "OPENMOUSE_EMERGENCY_STOP") {
    return false;
  }
  if (connected) {
    sendJson({
      type: "emergency_stop",
      reason: message.reason || "browser_escape_key",
    });
  }
  broadcastStop(message.reason || "browser_escape_key");
  return false;
});

chrome.action.onClicked.addListener(() => {
  chrome.runtime.openOptionsPage();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "openmouse-keepalive") {
    connect();
    sendHeartbeat();
  }
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local" || (!changes.serverUrl && !changes.token)) {
    return;
  }
  connected = false;
  stopHeartbeat();
  if (socket) {
    try {
      socket.close();
    } catch (_error) {
      // The reconnect path handles a socket already closing.
    }
  }
  socket = null;
  connect();
});

chrome.runtime.onInstalled.addListener(async () => {
  const current = await chrome.storage.local.get(["serverUrl", "token"]);
  await chrome.storage.local.set({
    serverUrl: current.serverUrl || DEFAULT_SERVER_URL,
    token: current.token || DEFAULT_TOKEN,
  });
  await chrome.alarms.create("openmouse-keepalive", {
    periodInMinutes: 0.5,
  });
  connect();
});

chrome.runtime.onStartup.addListener(() => {
  connect();
});

connect();
