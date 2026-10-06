# Security and data handling

Do not publish `.env`, real Streamlit secrets, Odoo exports, database backups, authentication material or customer documents. The repository includes synthetic reference data only. Inspect staged files before pushing. `.gitignore` cannot protect secrets already committed.

The default local PostgreSQL service is intended for local access. Treat cloud exposure as a separate deployment and security task. Application roles are not interchangeable: an administrator cannot approve financial proposals, and reviewers cannot approve their own proposals.

Do not paste credentials or private financial records into public issues. Report a suspected vulnerability privately to the repository owner through an available private contact channel; remove sensitive details from public reproduction steps.
