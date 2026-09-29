from .base import *  # noqa
import environ

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

CORS_ALLOW_ALL_ORIGINS = True

# Postgres locally too (via Docker) — never SQLite, per Phase 0 Section 2
DATABASES["default"] = env.db("DATABASE_URL", default="postgres://postgres:postgres@localhost:5432/saas_platform")

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# --- sandbox sanity-check override only, not part of shipped settings ---
import os as _os
if _os.environ.get("SANDBOX_CHECK"):
    DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    # Local preview without Docker: kitchen updates stay in this process.
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    CELERY_TASK_ALWAYS_EAGER = True
