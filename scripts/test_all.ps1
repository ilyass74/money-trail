$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $ProjectPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $ProjectPython)) { throw 'Python du projet absent. Lancer import_demo.ps1.' }
    & $ProjectPython -m pip install -r requirements-dbt.txt -r requirements-ui.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependances non installees. Recette interrompue.' }
    Write-Host 'RECETTE MONEY TRAIL - bases temporaires, donnees et comptes existants conserves.'
    Write-Host 'Les builds volontairement invalides doivent echouer ; les tests de rejet doivent reussir.'
    & $ProjectPython scripts\acceptance.py run --database
    if ($LASTEXITCODE -ne 0) { throw 'Recette en echec ou incomplete. Consulter le report.md et les journaux dans reports.' }
    Write-Host 'Tests executes termines. Lire report.md : les fonctions absentes du MVP restent signalees.'
} finally {
    Pop-Location
}
