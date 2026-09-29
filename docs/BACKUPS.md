# Backups & data export

## 1. Business owners (in the app)
**Settings → Security & 2FA → Backup & export → Download all my data** gives the
owner a zip of every record of their business (one JSON file per table, plus
photos/logos if ticked). Passwords and 2FA secrets are never included. The
download is written to the audit log.

## 2. Platform owner (server)
```bash
python manage.py export_company_data --company <slug> --out exports/ --media
python manage.py export_company_data --company all            # every business
```
On Render, run it from the web service **Shell** (paid instances) or a one-off job.

## 3. Database backups (strongly recommended)
- **Render paid Postgres** keeps automatic daily backups with point-in-time
  recovery. The free database has **no backups and expires after 30 days**.
  Upgrade it before real customers use the system.
- Extra safety copy from any computer with PostgreSQL client tools:
  ```bash
  pg_dump "$DATABASE_URL" --format=custom --file=bookpilot-$(date +%F).dump
  pg_restore --clean --no-owner --dbname "$NEW_DATABASE_URL" bookpilot-YYYY-MM-DD.dump
  ```
- Uploaded files live in S3/R2 when `USE_S3=True`; turn on bucket versioning.
