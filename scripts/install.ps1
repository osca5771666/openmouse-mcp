param(
  [string]$PythonLauncher = "python",
  [string]$IndexUrl = "https://pypi.org/simple"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$RuntimeDir = Join-Path $Root ".runtime"
$TokenFile = Join-Path $RuntimeDir "browser-token.txt"

Push-Location $Root
try {
  if (-not (Get-Command $PythonLauncher -ErrorAction SilentlyContinue)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
      $PythonLauncher = "py"
    } else {
      throw "No Python launcher found. Install Python 3.10 or newer."
    }
  }

  if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $PythonLauncher -m venv --system-site-packages $Venv
    if ($LASTEXITCODE -ne 0) {
      throw "Could not create the project virtual environment."
    }
  }

  $env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
  & $VenvPython -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('setuptools') else 1)"
  if ($LASTEXITCODE -ne 0) {
    $ResolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    $ResolvedVenv = (Resolve-Path -LiteralPath $Venv).Path
    $RequiredPrefix = $ResolvedRoot.TrimEnd('\') + '\'
    if (-not $ResolvedVenv.StartsWith($RequiredPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to recreate a virtual environment outside the project: $ResolvedVenv"
    }
    Write-Host "Rebuilding .venv with the selected Python distribution."
    Remove-Item -LiteralPath $ResolvedVenv -Recurse -Force
    & $PythonLauncher -m venv --system-site-packages $Venv
    if ($LASTEXITCODE -ne 0) {
      throw "Could not rebuild the project virtual environment."
    }
  }

  & $VenvPython -m pip install --no-build-isolation --no-deps -e .
  if ($LASTEXITCODE -ne 0) {
    throw "Editable install failed. Ensure setuptools is available in the base Python."
  }

  & $VenvPython -c "import importlib.util,sys; names=['mcp','websockets','psutil','PIL','pyautogui','pynput','mouse_mcp']; missing=[name for name in names if importlib.util.find_spec(name) is None]; print('missing: ' + ', '.join(missing) if missing else 'dependencies: ok'); sys.exit(1 if missing else 0)"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing missing runtime dependencies from $IndexUrl"
    & $VenvPython -m pip install --index-url $IndexUrl -e .
    if ($LASTEXITCODE -ne 0) {
      throw "Dependency installation failed."
    }
  }

  New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
  if (-not (Test-Path -LiteralPath $TokenFile)) {
    $Bytes = New-Object byte[] 32
    $Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
      $Rng.GetBytes($Bytes)
    } finally {
      $Rng.Dispose()
    }
    $Token = -join ($Bytes | ForEach-Object { $_.ToString("x2") })
    Set-Content -LiteralPath $TokenFile -Value $Token -NoNewline -Encoding ascii
  }

  $ConfiguredToken = Get-Content -LiteralPath $TokenFile -Raw
  Write-Host ""
  Write-Host "OpenMouse MCP installed."
  Write-Host "Python: $VenvPython"
  Write-Host "Browser token: $ConfiguredToken"
  Write-Host ""
  Write-Host "Load browser-extension in chrome://extensions and paste this token there."
  Write-Host "Run diagnose with:"
  Write-Host "  & '$VenvPython' -m mouse_mcp --diagnose"
} finally {
  Pop-Location
}
