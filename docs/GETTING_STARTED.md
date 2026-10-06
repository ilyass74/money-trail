# Windows setup

Use PowerShell in the repository root. Prerequisites: Docker Desktop with Linux containers and Python with the Windows `py` launcher. Use an isolated virtual environment. Dependency versions are pinned in the repository's requirements files.

## New local demo installation

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prepare.ps1
docker compose up -d --wait postgres
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dbt.txt -r requirements-ui.txt -r requirements-operations.txt
.\.venv\Scripts\python.exe .\scripts\import_data.py setup
.\.venv\Scripts\python.exe .\scripts\import_data.py import
.\.venv\Scripts\python.exe .\scripts\run_dbt.py build
.\.venv\Scripts\python.exe .\scripts\interface_setup.py --username analyst --role analyst
.\.venv\Scripts\python.exe .\scripts\interface_setup.py --username reviewer --role reviewer
.\.venv\Scripts\python.exe .\scripts\interface_setup.py --username admin --role admin
.\.venv\Scripts\python.exe -m streamlit run .\ui\app.py --server.address 127.0.0.1
```

`prepare.ps1` generates local configuration when absent. Passwords for application accounts are entered at hidden prompts, not placed in commands. Creating an account whose username already exists preserves its password and role. Keep the terminal running and open http://127.0.0.1:8501.

This sequence is grounded in the provided scripts; the new-install sequence was not rerun from a clean Windows machine during documentation preparation. Earlier local validations are described in [VALIDATION.md](VALIDATION.md).

## Existing installation

Do not recreate your environment or reimport the demo just to start the UI:

```powershell
cd "$HOME\Documents\money-trail"
docker compose up -d --wait postgres
.\.venv\Scripts\python.exe -m streamlit run .\ui\app.py --server.address 127.0.0.1
```

For the themed launcher with interface tests, use `scripts/refresh_interface.ps1`.

## Troubleshooting

- **Connection refused:** confirm that the Streamlit terminal is still running. The app and Odoo use different ports: normally 8501 and 8069.
- **No results:** select the intended publication, remove filters and return to page 1. A successful source import still needs a successful dbt publication.
- **No review cases:** an administrator can synchronize anomaly cases from the case page. This does not extract new Odoo data.
- **No pending decisions:** submit a proposal from a case under review. A comment alone is not a proposal.
- **No approval button:** use a reviewer account distinct from the proposer. Admin is not a financial approval role.
- **Odoo authentication fails:** confirm the local instance and database; an odoo.com password reset is separate from a local account.

To stop PostgreSQL without deleting its persistent volume, use `docker compose stop`. Do not use volume deletion as a routine restart procedure.
