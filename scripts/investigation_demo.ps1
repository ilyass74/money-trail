$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $ProjectPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $ProjectPython)) { throw 'Python du projet absent.' }
    function Invoke-ProjectPython {
        & $ProjectPython @args
        if ($LASTEXITCODE -ne 0) { throw 'Investigation interrompue. Consulter le message affiche.' }
    }
    Invoke-ProjectPython -m unittest discover -s tests -v
    Invoke-ProjectPython scripts\investigate.py settlement LOT001
    Invoke-ProjectPython scripts\investigate.py settlement LOT003
    Invoke-ProjectPython scripts\investigate.py all --export
    Write-Host 'INVESTIGATION DEMO TERMINEE - 5 dossiers de reference doivent etre exportes.'
} finally {
    Pop-Location
}
