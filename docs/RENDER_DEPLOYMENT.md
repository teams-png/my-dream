# Render Deployment (Phase 20 / Phase 1 Section 31)

## Quick start (free plan)

1. Render dashboard → **New > Blueprint** → pick this GitHub repo.
2. When asked, fill in `PLATFORM_ADMIN_EMAIL` and `PLATFORM_ADMIN_PASSWORD`
   (your platform-owner login; created once by `build.sh`).
3. Click **Apply**. After the build finishes, open the `bookpilot-web` URL.

Free-plan limits: the web service sleeps after ~15 min idle (first request
takes ~1 min), the free Postgres database expires after 30 days unless
upgraded, uploads are not persistent until `USE_S3=True` + `AWS_*` are set,
and Celery runs tasks inline because free plans have no background workers.
The full production setup is described below.

This guide deploys BookPilot with persistent database, Redis, background
workers and private object storage. Do not use local filesystem media in a
live deployment because Render service disks are ephemeral.

## 1. Push to GitHub

```bash
cd project-root
git init                      # skip if already a repo
git add .
git commit -m "Phase 20: Render deployment config"
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

`.gitignore` already excludes `.env`, `__pycache__/`, `*.pyc`, `media/`,
`staticfiles/` — double check `.env` is NOT in the commit before pushing
(Phase 1 Section 27: never commit real secrets).

## 2. Create the services on Render

**Option A — Blueprint (recommended):** in the Render dashboard, choose
**New > Blueprint**, point it at your GitHub repo. Render reads
`render.yaml` at the repo root and provisions all five services below in
one pass: the web service, two Celery workers (worker + beat), the
Postgres database, and Redis.

**Option B — manual:** create each service by hand using the same
settings `render.yaml` describes (useful if you're on a Render plan that
doesn't support Blueprints).

| Service | Type | Build Command | Start Command |
|---|---|---|---|
| bookpilot-web | Web Service | `./build.sh` | `daphne -b 0.0.0.0 -p $PORT config.asgi:application` |
| bookpilot-celery-worker | Background Worker | `pip install -r requirements/production.txt` | `celery -A config worker --loglevel=info` |
| bookpilot-celery-beat | Background Worker | `pip install -r requirements/production.txt` | `celery -A config beat --loglevel=info` |
| bookpilot-db | PostgreSQL | — | — |
| bookpilot-redis | Redis | — | — |

`build.sh` does three things every deploy: installs dependencies, runs
`collectstatic`, runs `migrate`, and runs `seed_platform` (idempotent —
safe to run every time, it only creates rows that don't exist yet).

## 3. Environment variables

Set these on **every** Python service (web, worker, beat) — Render's
"Environment Groups" feature lets you set them once and share across all
three, which avoids the `DJANGO_SECRET_KEY` mismatch that plain
`render.yaml` `sync: false` values leave you to fix by hand:

| Variable | Value | Notes |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.render` | Not `production` — that's Phase 21 |
| `DJANGO_SECRET_KEY` | (generate one, e.g. `python -c "import secrets; print(secrets.token_urlsafe(50))"`) | Same value on all three services |
| `PAYMENT_CREDENTIALS_ENCRYPTION_KEY` | separate generated secret | Back up securely; used to encrypt gateway keys saved in Platform Admin |
| `DJANGO_ALLOWED_HOSTS` | `.onrender.com` | Add your custom domain here later (step 6) |
| `CSRF_TRUSTED_ORIGINS` | `https://*.onrender.com` | Same |
| `DATABASE_URL` | (Render fills this in automatically if you used "fromDatabase" / linked the DB) | |
| `REDIS_URL` | (same — auto-filled if linked) | |
| `USE_S3` | `True` | Required for persistent media |
| `AWS_ACCESS_KEY_ID` | provider credential | Set on all three Python services |
| `AWS_SECRET_ACCESS_KEY` | provider credential | Set on all three Python services |
| `AWS_STORAGE_BUCKET_NAME` | private bucket name | Versioning and backups recommended |
| `AWS_S3_ENDPOINT_URL` | provider endpoint | Optional for AWS; required for most S3-compatible providers |

Never type real values for these into `render.yaml` itself — set them in
the Render dashboard's Environment tab, which is exactly what
`sync: false` / `generateValue: true` in the blueprint are telling Render
to prompt you for.

## 4. First deploy — migrations & superuser

`build.sh` already runs `migrate` and `seed_platform` automatically on
every deploy. You only need the Render **Shell** tab (on the web service)
once, to create your own platform superuser:

```bash
python manage.py createsuperuser
```

## 5. Verify

```bash
curl https://bookpilot-web.onrender.com/api/accounts/register/ -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"test@example.com","email":"test@example.com","password":"Testpass123!"}'
```

A `201` back means the web service, database, and migrations are all
working. Check the worker/beat logs in the Render dashboard to confirm
Celery connected to Redis (look for `celery@... ready`).

## 6. Custom domain & SSL

Render → your web service → **Settings > Custom Domains** → add your
domain, then create the CNAME record it shows you at your DNS provider.
Render issues and renews the SSL certificate automatically — no manual
`certbot` step at this stage (that's only needed for the VPS in Phase 21).
Once added, put the domain in `DJANGO_ALLOWED_HOSTS` and
`CSRF_TRUSTED_ORIGINS` alongside `.onrender.com` (don't replace it — keep
both while you're still testing on the `.onrender.com` URL too).

## 7. Persistent media verification

Upload a company logo, restart the web service, and confirm that the logo is
still available only to an authenticated user. Bucket access must remain
private; BookPilot uses signed object URLs. Enable bucket versioning and include
media restoration in the monthly restore drill.

## 8. Migrating off Render's Postgres later (Phase 21 preview)

When you move to the Cloud VPS: `pg_dump` the Render database, `pg_restore`
into the new VPS Postgres, then just change `DATABASE_URL` — no
application code changes needed, because every setting reads
`DATABASE_URL` through `env.db(...)` rather than hardcoding host/port
anywhere. Full steps are in the Phase 21 deployment doc.
