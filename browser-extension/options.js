const form = document.getElementById("settings-form");
const serverUrl = document.getElementById("server-url");
const token = document.getElementById("token");
const showToken = document.getElementById("show-token");
const status = document.getElementById("status");

const load = async () => {
  const values = await chrome.storage.local.get(["serverUrl", "token"]);
  serverUrl.value = values.serverUrl || "ws://127.0.0.1:8765";
  token.value = values.token || "local-dev-token";
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await chrome.storage.local.set({
    serverUrl: serverUrl.value.trim(),
    token: token.value.trim(),
  });
  status.textContent =
    "Saved. The background worker will reconnect with the new settings.";
});

showToken.addEventListener("click", () => {
  const visible = token.type === "text";
  token.type = visible ? "password" : "text";
  showToken.textContent = visible ? "Show token" : "Hide token";
});

load();
