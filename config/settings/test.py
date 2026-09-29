"""
Settings used only when running pytest (see pytest.ini: DJANGO_SETTINGS_MODULE).

Uses SQLite in-memory by default for fast local test runs. This is a
deliberate, scoped exception to Phase 0 Section 2 ("avoid SQLite even for
dev") — the codebase uses no Postgres-only features (checked: only
`JSONField`, which Django supports identically on both backends), and a
disk-less in-memory DB keeps the suite fast enough to run on every commit.

For CI, prefer running against a real Postgres service container instead
(set DATABASE_URL to point at it before invoking pytest) so migrations and
any future Postgres-specific constraints get exercised for real — this
file falls back to SQLite only when DATABASE_URL isn't set.
"""
from .base import *  # noqa
import environ

env = environ.Env()

DEBUG = False
SECRET_KEY = "test-suite-secret-key-not-for-production"
ALLOWED_HOSTS = ["*"]

DATABASES["default"] = env.db(
    "DATABASE_URL", default="sqlite:///:memory:"
)

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed, tests only
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
