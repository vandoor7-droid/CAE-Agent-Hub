#Requires -Version 5.1
param(
    [ValidateSet("grpc", "pid", "both")]
    [string]$Mode = "both",
    [string]$AedtRoot = "G:\ANSYS206\ANSYS Inc\v261\AnsysEM",
    [int]$Port = 50061
)

$ErrorActionPreference = "Stop"
$ModuleRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ModuleRoot ".venv\Scripts\python.exe"
$Runner = Join-Path $ModuleRoot "tests\live\run_acceptance.py"
$Artifacts = Join-Path $ModuleRoot "test-artifacts"
New-Item -ItemType Directory -Force -Path $Artifacts | Out-Null

$modes = if ($Mode -eq "both") { @("grpc", "pid") } else { @($Mode) }
foreach ($currentMode in $modes) {
    $resultPath = Join-Path $Artifacts "$currentMode-result.json"
    & $Python $Runner --mode $currentMode --aedt-root $AedtRoot --port $Port --result $resultPath
    if ($LASTEXITCODE -ne 0) { throw "$currentMode acceptance operations failed." }
    $result = Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json
    Write-Host "[AEDT MCP] $currentMode acceptance passed for PID $($result.session.pid)."
}
