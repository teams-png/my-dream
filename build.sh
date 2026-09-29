#!/usr/bin/env bash
# Render "Build Command" — set this exact command in the Render dashboard,
# or let render.yaml's buildCommand run it automatically (Phase 1 Section 31).
set -o errexit

pip install -r requirements/production.txt

python manage.py collectstatic --no-input
python manage.py migrate
python manage.py seed_platform   # idempotent — safe to run on every deploy (Phase 0's own docstring)
python manage.py ensure_platform_admin   # no-op unless PLATFORM_ADMIN_EMAIL/PASSWORD are set
