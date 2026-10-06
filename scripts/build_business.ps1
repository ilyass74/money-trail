$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $ProjectPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $ProjectPython)) { throw 'Python du projet absent. Lancer import_demo.ps1.' }
    function Invoke-ProjectPython {
        & $ProjectPython @args
        if ($LASTEXITCODE -ne 0) { throw 'Etape interrompue. Corriger le message affiche avant de continuer.' }
    }
    Invoke-ProjectPython -m pip install -r requirements-dbt.txt
    Invoke-ProjectPython scripts\run_dbt.py parse
    Invoke-ProjectPython scripts\test_dbt_integration.py
    Invoke-ProjectPython scripts\run_dbt.py build
    Write-Host 'MOTEUR METIER TERMINE - REFERENCE_RESULTS_OK doit apparaitre ci-dessus.'
} finally {
    Pop-Location
}
