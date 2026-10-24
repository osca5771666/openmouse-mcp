param(
  [string]$SkillRoot = "$HOME\.codex\skills"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $ProjectRoot "codex\openmouse-computer-use"
$Destination = Join-Path $SkillRoot "openmouse-computer-use"

if (-not (Test-Path -LiteralPath (Join-Path $Source "SKILL.md"))) {
  throw "The OpenMouse Codex skill source is missing."
}

New-Item -ItemType Directory -Force -Path $SkillRoot | Out-Null
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
Copy-Item -LiteralPath (Join-Path $Source "SKILL.md") -Destination $Destination -Force
New-Item -ItemType Directory -Force -Path (Join-Path $Destination "agents") | Out-Null
Copy-Item `
  -LiteralPath (Join-Path $Source "agents\openai.yaml") `
  -Destination (Join-Path $Destination "agents\openai.yaml") `
  -Force

Write-Host "Installed Codex skill: $Destination"
