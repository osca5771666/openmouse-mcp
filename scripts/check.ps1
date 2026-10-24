param(
  [switch]$BrowserE2E,
  [switch]$CloudE2E,
  [switch]$CloudHttpE2E,
  [switch]$PluginE2E,
  [switch]$StdioE2E
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  $Python = "python"
}

Push-Location $Root
try {
  $env:PYTHONPATH = Join-Path $Root "src"
  & $Python -m compileall -q src
  & $Python -m pytest
  node --test browser-extension/tests/humanize.test.mjs
  if ($BrowserE2E) {
    & $Python tests/e2e_browser.py
  }
  if ($CloudE2E) {
    & $Python tests/e2e_cloud.py
  }
  if ($CloudHttpE2E) {
    & $Python tests/e2e_cloud_http.py
  }
  if ($PluginE2E) {
    & $Python tests/e2e_plugin.py
  }
  if ($StdioE2E) {
    & $Python tests/e2e_stdio.py
  }
} finally {
  Pop-Location
}
