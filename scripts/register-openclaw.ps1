param(
  [string]$Name = "openmouse-mcp"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "Run scripts\install.ps1 before registering the MCP server."
}

$OpenClaw = Get-Command openclaw -ErrorAction SilentlyContinue
if (-not $OpenClaw) {
  throw "openclaw is not on PATH."
}

function Invoke-OpenClaw {
  param([string[]]$Arguments)
  $PreviousPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $Output = & openclaw @Arguments 2>&1 | Out-String
    return [pscustomobject]@{
      Output = $Output
      ExitCode = $LASTEXITCODE
    }
  } finally {
    $ErrorActionPreference = $PreviousPreference
  }
}

$HelpResult = Invoke-OpenClaw @("--help")
if ($HelpResult.ExitCode -ne 0 -or $HelpResult.Output -notmatch "(?m)^\s*mcp\s") {
  throw "This OpenClaw build does not expose the MCP host. Upgrade OpenClaw or use another MCP-capable Agent."
}

$AddResult = Invoke-OpenClaw @(
  "mcp", "add", $Name,
  "--command", $Python,
  "--arg", "-m",
  "--arg", "mouse_mcp",
  "--cwd", $Root
)
$AddResult.Output | Write-Host
if ($AddResult.ExitCode -ne 0) {
  throw "openclaw mcp add failed."
}

$DoctorResult = Invoke-OpenClaw @("mcp", "doctor", $Name, "--probe")
$DoctorResult.Output | Write-Host
if ($DoctorResult.ExitCode -ne 0) {
  throw "openclaw mcp doctor failed."
}
