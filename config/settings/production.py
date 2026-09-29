from .base import *  # noqa
import environ

env = environ.Env()

DEBUG = False
if SECRET_KEY == "unsafe-dev-key-override-in-env" or len(SECRET_KEY) < 32:
    raise RuntimeError("DJANGO_SECRET_KEY must be a strong production secret.")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")

DATABASES["default"] = env.db("DATABASE_URL")

STORAGES = {
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
    "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
}
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default=None)
AWS_DEFAULT_ACL = "private"
AWS_QUERYSTRING_AUTH = True
AWS_S3_FILE_OVERWRITE = False

# Full hardening per Phase 0 Section 14
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.common.logging.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        send_default_pii=False,
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.05),
        environment=env("SENTRY_ENVIRONMENT", default="production"),
    )
