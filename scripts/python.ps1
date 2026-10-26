param([switch]$Bootstrap, [Parameter(ValueFromRemainingArguments=$true)][string[]]$CommandArgs)
$ErrorActionPreference = 'Stop'
$runtimePath = $env:HARNESS_RUNTIME_DIR
if (-not $runtimePath) { $runtimePath = Join-Path $env:LOCALAPPDATA 'harness/runtime' }
$env:HARNESS_RUNTIME_DIR = $runtimePath
$env:PATH = "$runtimePath/bin;$runtimePath/node;$env:PATH"
$candidates = @()
if ($env:HARNESS_PYTHON) { $candidates += $env:HARNESS_PYTHON }
$pointerPath = Join-Path $runtimePath 'python-path.txt'
if (Test-Path -LiteralPath $pointerPath) { $candidates += (Get-Content -LiteralPath $pointerPath -Raw).Trim() }
$candidates += @('python', 'python3', 'py')
foreach ($candidate in $candidates) {
    $resolved = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue
    if (-not $resolved -or $resolved.Source -like '*\Microsoft\WindowsApps\*') { continue }
    $prefix = @()
    if ($resolved.Name -eq 'py.exe') { $prefix = @('-3') }
    try {
        & $resolved.Source @prefix -c 'import sys;sys.exit(sys.version_info < (3,11))' 2>$null
        if ($LASTEXITCODE -eq 0) {
            & $resolved.Source @prefix -X utf8 @CommandArgs
            exit $LASTEXITCODE
        }
    } catch { continue }
}
if (-not $Bootstrap) {
    Write-Error 'Python 3.11+ is missing. Install native Python, set HARNESS_PYTHON, or run install.ps1 to provision a user-local runtime.'
    exit 1
}
if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'Native bootstrap currently supports Windows x64.' }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Force -Path "$runtimePath/bin" | Out-Null
if (-not (Get-Command uv -CommandType Application -ErrorAction SilentlyContinue)) {
    & "$PSScriptRoot/uv.ps1" -Destination "$runtimePath/bin"
}
$env:UV_PYTHON_INSTALL_DIR = "$runtimePath/python"
$env:UV_CACHE_DIR = "$runtimePath/uv-cache"
& uv python install --no-bin --no-registry 3.12
if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
$pythonPath = & uv python find --managed-python 3.12
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonPath)) { throw 'Managed Python was not found.' }
[IO.File]::WriteAllText($pointerPath, $pythonPath)
& $pythonPath -X utf8 @CommandArgs
exit $LASTEXITCODE
