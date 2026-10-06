$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $ProjectPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $ProjectPython)) { throw 'Python du projet absent.' }
    function Invoke-ProjectPython {
        & $ProjectPython @args
        if ($LASTEXITCODE -ne 0) { throw 'Workflow interrompu. Consulter le message affiche.' }
    }
    Invoke-ProjectPython -m unittest discover -s tests -v
    Invoke-ProjectPython scripts\test_workflow_integration.py
    Invoke-ProjectPython scripts\workflow.py setup
    Invoke-ProjectPython scripts\workflow.py sync --actor Ilyass
    Invoke-ProjectPython scripts\workflow.py list
    Write-Host 'WORKFLOW DEMO TERMINE - LOT001 et LOT003 doivent etre listes.'
} finally {
    Pop-Location
}
