$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $ProjectPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $ProjectPython)) { throw 'Python du projet absent.' }
    function Invoke-ProjectPython {
        & $ProjectPython @args
        if ($LASTEXITCODE -ne 0) { throw 'Interface interrompue. Consulter le message affiche.' }
    }
    Invoke-ProjectPython -m pip install -r requirements-ui.txt
    Invoke-ProjectPython -m unittest discover -s tests -v
    Invoke-ProjectPython scripts\test_interface_ui.py
    Invoke-ProjectPython scripts\test_interface_integration.py
    Invoke-ProjectPython scripts\interface_setup.py
    Write-Host 'Interface disponible sur http://127.0.0.1:8501 - garder cette fenetre ouverte.'
    Invoke-ProjectPython -m streamlit run ui\app.py --global.developmentMode false --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false --theme.base light --theme.primaryColor '#008879' --theme.backgroundColor '#f6f7fb' --theme.secondaryBackgroundColor '#ffffff' --theme.textColor '#16253b'
} finally {
    Pop-Location
}
