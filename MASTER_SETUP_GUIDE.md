# BookPilot Master Setup Guide

This is the consolidated master release. Phase 53 is the authoritative source; older Phase 36-48 archives were compared only to detect missing files. No older source file was allowed to overwrite a newer implementation.

## 1. Local installation

Requirements: Python 3.12, PostgreSQL 16, Redis 7 and a current browser.

```bash
python -m venv .venv
```

Activate the environment, then:

```bash
pip install -r requirements/dev.txt
cp .env.example .env
docker compose up -d
python manage.py migrate
python manage.py seed_platform
python manage.py createsuperuser
python manage.py runserver
```

The supplied Docker PostgreSQL port is `5433`; when using it, set `DATABASE_URL=postgres://postgres:postgres@localhost:5433/saas_platform` in `.env`.

## 2. Verification

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
```

The updated master package was verified locally with 330 passing tests. PostgreSQL CI is included and remains mandatory before production release.

## 3. First platform setup

Use `http://127.0.0.1:8000/platform/` for normal SaaS owner operations. Open
**Platform Setup** to manage modules, business types, default module bundles,
users, support tickets, audit history, plans and integration status. The
`/admin/` URL is reserved for technical backend maintenance.

1. Sign in with the platform administrator account.
2. Create pricing plans and assign permitted modules and limits.
3. Register the first client and owner.
4. Assign only the modules included in the client's plan.
5. Complete the tenant onboarding checklist: profile, accounting, branch, products, team, tax and opening balances.
6. Create a pilot branch, products and representative transactions before importing real data.

## 4. Production configuration

Use `requirements/production.txt` and `config.settings.production` or the supplied Render blueprint. Configure unique secrets outside the ZIP/repository:

- strong `DJANGO_SECRET_KEY`;
- PostgreSQL and Redis connection URLs;
- allowed hosts and trusted HTTPS origins;
- private S3-compatible media storage;
- SMTP email credentials;
- Stripe or Razorpay credentials and webhook secrets, if enabled;
- monitoring DSN and scheduled backups.

Never place real credentials in `.env.example`, source control or a file sent to customers.

## 5. Required release gate

- PostgreSQL test suite and migration test pass;
- tenant-isolation and permissions UAT pass;
- invoice, purchase, return, POS, payroll and reports reconcile;
- backup restoration is demonstrated;
- payment webhooks are tested in provider sandbox mode;
- country-specific tax, privacy, invoicing and commercial terms are reviewed by qualified professionals;
- one pilot customer completes end-to-end UAT before wider rollout.
