$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $ProjectPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $ProjectPython)) { throw 'Python du projet absent.' }
    function Invoke-ProjectPython {
        & $ProjectPython @args
        if ($LASTEXITCODE -ne 0) { throw 'Mise a jour interrompue. Consulter le message affiche.' }
    }
    Invoke-ProjectPython -m unittest discover -s tests -v
    Invoke-ProjectPython scripts\test_interface_ui.py
    Write-Host 'Nouvelle interface sur http://127.0.0.1:8501 - compte existant conserve.'
    Invoke-ProjectPython -m streamlit run ui\app.py --global.developmentMode false --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false --theme.base light --theme.primaryColor '#087f72' --theme.backgroundColor '#f4f7f5' --theme.secondaryBackgroundColor '#ffffff' --theme.textColor '#142d3c'
} finally {
    Pop-Location
}
