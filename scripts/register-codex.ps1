param(
  [string]$Name = "openmouse"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$TokenFile = Join-Path $Root ".runtime\browser-token.txt"
$SourcePath = Join-Path $Root "src"
$CodexConfig = Join-Path $HOME ".codex\config.toml"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "Run scripts\install.ps1 before registering OpenMouse with Codex."
}
if (-not (Test-Path -LiteralPath $TokenFile)) {
  throw "Browser token file is missing. Run scripts\install.ps1 again."
}
if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
  throw "codex is not on PATH."
}
if (Test-Path -LiteralPath $CodexConfig) {
  $Backup = "$CodexConfig.openmouse-backup"
  Copy-Item -LiteralPath $CodexConfig -Destination $Backup -Force
}

$PreviousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
  $Existing = & codex mcp get $Name --json 2>&1 | Out-String
  if ($LASTEXITCODE -eq 0) {
    & codex mcp remove $Name | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "Could not replace the existing Codex MCP entry '$Name'."
    }
  }

  & codex mcp add `
    --env "PYTHONPATH=$SourcePath" `
    --env "MOUSE_MCP_ENV=auto" `
    --env "MOUSE_MCP_CLOUD_BROWSER=off" `
    --env "MOUSE_MCP_TOKEN_FILE=$TokenFile" `
    $Name `
    -- $Python -m mouse_mcp
  if ($LASTEXITCODE -ne 0) {
    throw "codex mcp add failed."
  }

  & codex mcp get $Name --json
  if ($LASTEXITCODE -ne 0) {
    throw "Codex could not read the registered OpenMouse MCP entry."
  }
} finally {
  $ErrorActionPreference = $PreviousPreference
}

Write-Host ""
Write-Host "OpenMouse is registered with Codex as '$Name'."
& (Join-Path $PSScriptRoot "install-codex-skill.ps1")
Write-Host "Restart Codex or start a new thread to load the MCP tools."
