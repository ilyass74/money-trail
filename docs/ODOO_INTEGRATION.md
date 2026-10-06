# Local Odoo integration

The owner's local run used Odoo Community 18.0-20250721. The Odoo 18 connector is `scripts/odoo18_connect.py`. The project also contains an Odoo 19 extraction path; successful Odoo 18 execution does not validate every other version or deployment.

## Connect and extract

Replace `YOUR_DATABASE` with the database of the intended local instance. Credentials are requested interactively.

```powershell
.\.venv\Scripts\python.exe .\scripts\odoo18_connect.py --url http://127.0.0.1:8069 --database YOUR_DATABASE
$odooOutput = ".\data\odoo_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
.\.venv\Scripts\python.exe .\scripts\odoo18_connect.py --url http://127.0.0.1:8069 --database YOUR_DATABASE --company-id 1 --extract --output $odooOutput --import-bundles
```

Use the company ID returned for your authorized scope; do not assume it is always 1. After a successful import, copy its `batch_id`:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_dbt.py build --batch-id YOUR_BATCH_ID
```

Do not overwrite your local connector and normalization fixes with older milestone archives. Publication must use the latest working source code.

## Cases encountered during local validation

- Signed price fields on journal entries required distinguishing journal-entry validation from invoice-price validation. This is not permission to convert all accounting amounts to absolute values.
- Undated draft invoices required an explicit exclusion from publishable invoice results. Do not invent invoice dates to satisfy a check.
- Extraction, normalization, bundle conversion, import and publication are separate steps; a successful connection alone does not validate the entire flow.

## Boundaries

The connected invoice flow reads ERP records; it does not perform financial corrections in Odoo. The observed run published invoice results and no settlement results. Bank confirmation requires bank-originated inputs and verified matching; an ERP payment is not independent bank evidence.

Keep exports under `data/` excluded from Git. Never commit API keys, account passwords, private database names inside personal scripts, or raw customer/financial exports.
