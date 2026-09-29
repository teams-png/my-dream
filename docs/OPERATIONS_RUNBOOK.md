# Operations Runbook

## Release procedure

1. Build an immutable release image and run `python manage.py check --deploy`.
2. Run the SQLite test suite, then the PostgreSQL CI suite.
3. Take and verify a database backup before migrations.
4. Run `python manage.py migrate --noinput` as a single controlled release step.
5. Deploy web and worker processes, then verify `/health/` and `/ready/`.
6. Monitor HTTP error rate, Celery failures, database saturation, and reconciliation alerts.

## Backup and restore

- PostgreSQL: encrypted daily full backups, point-in-time recovery/WAL archival, 30-day retention, and an off-account copy.
- Media: versioned object storage with lifecycle retention. Database and media backups must share a restore-point label.
- Secrets: never store credentials in backups or source control. Back up the secret-manager configuration separately.
- Restore test: monthly, restore the latest backup to an isolated environment, run migrations, `manage.py check`, readiness, tenant-count reconciliation, trial balance totals, and sampled attachment checks. Record recovery point and recovery time.

Example database operations (replace placeholders through the secret manager):

```bash
pg_dump --format=custom --no-owner --file=backup.dump "$DATABASE_URL"
createdb restored_test
pg_restore --no-owner --dbname="$RESTORE_DATABASE_URL" backup.dump
```

## Rollback

Application rollback uses the previous immutable image. Database rollback is allowed only for a migration explicitly marked reversible and tested against a copy of production data. For irreversible migrations, restore the pre-release backup and replay only validated business events.

## Incident response

- Preserve request IDs and timestamps; never copy tokens, passwords, identity documents, or full financial exports into tickets.
- For suspected tenant leakage, disable affected endpoints, preserve audit logs, rotate exposed credentials, and compare access logs using request/company correlation IDs.
- Notification failures are retried independently and never roll back financial transactions.
