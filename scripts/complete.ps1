param([switch]$Benchmark)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $ProjectPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $ProjectPython)) { throw 'Environnement Python absent : executer scripts\prepare.ps1 et les etapes initiales.' }
    function Invoke-ProjectPython {
        & $ProjectPython @args
        if ($LASTEXITCODE -ne 0) { throw 'Etape refusee. Lire le journal et le rapport ; la publication precedente reste conservee.' }
    }
    Invoke-ProjectPython -m pip install -r requirements-dbt.txt -r requirements-ui.txt -r requirements-operations.txt
    Invoke-ProjectPython scripts\acceptance.py run --database
    Invoke-ProjectPython scripts\run_dbt.py build
    if ($Benchmark) { Invoke-ProjectPython scripts\benchmark.py }
    Write-Host 'MISE_A_JOUR_VALIDEE_POUR_LES_TESTS_EXECUTES'
    Write-Host 'Lire le rapport : connexion Odoo reelle, OIDC, cloud et parcours utilisateur restent soumis a leur propre recette.'
    Write-Host 'Relancer : powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh_interface.ps1'
} finally { Pop-Location }
