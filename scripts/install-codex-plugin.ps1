param(
  [string]$Repository = "osca5771666/openmouse-mcp",
  [string]$Ref = "main"
)

$ErrorActionPreference = "Stop"
$Codex = Get-Command codex -ErrorAction SilentlyContinue
if (-not $Codex) {
  throw "codex is not on PATH."
}

$PreviousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
  & codex plugin marketplace add $Repository --ref $Ref --json
  if ($LASTEXITCODE -ne 0) {
    throw "Could not add the OpenMouse plugin marketplace."
  }

  & codex plugin add openmouse@openmouse --json
  if ($LASTEXITCODE -ne 0) {
    throw "Could not install openmouse@openmouse."
  }

  & codex plugin list --json
  if ($LASTEXITCODE -ne 0) {
    throw "Could not verify the installed OpenMouse plugin."
  }
} finally {
  $ErrorActionPreference = $PreviousPreference
}

Write-Host ""
Write-Host "OpenMouse Codex plugin installed."
Write-Host "Start a new Codex thread to load the plugin MCP server and skill."
