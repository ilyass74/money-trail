# Contributing

Use a branch and describe the problem, changed behavior and validation scope. Reproduce issues with synthetic data. Keep changes to financial rules separate from cosmetic interface edits when practical.

Add meaningful regression cases when changing amount signs, states, dates, allocations, coverage, publication or permissions. Preserve Decimal/NUMERIC semantics, source provenance and separation between financial status and case progress.

Run the relevant tests listed in docs/VALIDATION.md. A green mocked-interface test is not proof of a successful live Odoo or PostgreSQL integration. Document what you actually verified.

Never include real exports, credentials, backups or private evidence in a contribution.
