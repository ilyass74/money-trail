# Validation evidence

Evidence below is scoped to specific observed runs. It is not a claim of complete scenario coverage or production readiness.

| Check | Observation | Evidence source |
|---|---|---|
| Local Odoo connection | Odoo 18.0-20250721 connection succeeded | Owner's Windows terminal output |
| Local Odoo import | 89 records imported; extraction reported zero quarantined rows | Owner's terminal output, 6 October 2026 |
| dbt publication | 18 models and 21 data tests completed; 18 invoice results, zero settlement results | Owner's build log, 6 October 2026 |
| Interface tests | 21 AppTest cases passed on Streamlit 1.64.0 | Interface verification run with mocked services |
| Browser navigation | Six sections opened in Chromium; mobile page had no document-level horizontal overflow in the tested scenario | Local browser verification with synthetic fixtures |

Private raw exports and full operational logs are not included in the public repository. The local integration observations are owner-reported evidence, not publicly reproducible records.

## Reproduce available checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe .\scripts\test_interface_ui.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_all.ps1
```

Read scripts before running integration checks; they require local PostgreSQL and temporary-database permissions. Reports are written locally and excluded from Git. Do not treat all discovery tests as PostgreSQL integration tests.

The GitHub preparation step checks documentation links and the files selected for publication. It does not rerun a clean Windows deployment, live Odoo authentication, bank integration, cloud deployment or the full accounting acceptance matrix.
