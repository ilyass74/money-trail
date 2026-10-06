$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $ProjectPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $ProjectPython)) { throw 'Python du projet absent.' }
    function Invoke-ProjectPython {
        & $ProjectPython @args
        if ($LASTEXITCODE -ne 0) { throw 'Etape interrompue. Lire le rapport et les journaux avant de continuer.' }
    }
    Invoke-ProjectPython -m pip install -r requirements-dbt.txt -r requirements-ui.txt
    Write-Host 'RECETTE COMPLETE - tests uniquement dans des bases temporaires.'
    Write-Host 'Les builds volontairement invalides doivent echouer ; leurs tests doivent reussir.'
    Invoke-ProjectPython scripts\acceptance.py run --database
    Write-Host 'Publication du dernier snapshot du projet apres validation de tous les tests.'
    Invoke-ProjectPython scripts\run_dbt.py build
    Write-Host 'PUBLICATION DEMO TERMINEE - PUBLICATION_PUBLISHED doit apparaitre ci-dessus.'
    Write-Host 'Relancer ensuite scripts\refresh_interface.ps1 avec le compte existant.'
} finally {
    Pop-Location
}
