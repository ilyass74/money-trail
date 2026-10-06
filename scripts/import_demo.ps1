$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) {
        throw 'Configuration .env absente. Lancer scripts/prepare.ps1.'
    }
    $script:moneyTrailPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $script:moneyTrailPython)) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv .venv
        } elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv .venv
        } else {
            throw 'Python est introuvable. Installer Python 3.10 ou plus recent.'
        }
        if ($LASTEXITCODE -ne 0) { throw 'Creation du venv impossible.' }
    }
    function Invoke-ProjectPython {
        param([string[]]$PythonArgs)
        & $script:moneyTrailPython @PythonArgs
        if ($LASTEXITCODE -ne 0) {
            throw 'Etape en echec. Le script arrete le traitement ici.'
        }
    }
    Invoke-ProjectPython -PythonArgs @('-c','import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)')
    Invoke-ProjectPython -PythonArgs @('-m','pip','install','-r','requirements-import.txt')
    Invoke-ProjectPython -PythonArgs @('-m','unittest','discover','-s','tests','-v')
    Invoke-ProjectPython -PythonArgs @('scripts/test_import_integration.py')
    Invoke-ProjectPython -PythonArgs @('scripts/import_data.py','setup')
    Invoke-ProjectPython -PythonArgs @('scripts/import_data.py','import')
    Invoke-ProjectPython -PythonArgs @('scripts/import_data.py','import')
    Invoke-ProjectPython -PythonArgs @('scripts/import_data.py','inspect')
    Write-Host 'IMPORT DEMO TERMINE - les resultats affiches doivent etre verifies.'
} finally {
    Pop-Location
}
