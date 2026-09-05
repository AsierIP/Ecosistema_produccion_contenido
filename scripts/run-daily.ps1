param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$ecosystemRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $ecosystemRoot
try {
    & $Python -m ecosystem daily
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Python -m ecosystem dashboard
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
