from .base import *  # noqa
import environ

env = environ.Env()

DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[".onrender.com"])

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["https://*.onrender.com"])

DATABASES["default"] = env.db("DATABASE_URL")

# WhiteNoise for static files on Render (Phase 0 Section 12)
MIDDLEWARE.insert(MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}

# Persistent media is strongly recommended for a live SaaS deployment.
# Render's local filesystem is ephemeral, so with USE_S3=False uploads
# (company logos etc.) are lost on every restart/deploy. USE_S3=False is
# allowed so a first free-tier deploy can come up before a bucket exists;
# switch it on (and set the AWS_* variables) before real customers use it.
if env.bool("USE_S3", default=True):
    STORAGES["default"] = {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"}
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default=None)
    AWS_DEFAULT_ACL = "private"
    AWS_QUERYSTRING_AUTH = True
    AWS_S3_FILE_OVERWRITE = False
    # backups live in the same bucket under a private prefix, never with public URLs
    STORAGES["backups"] = {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
                           "OPTIONS": {"location": "private-backups", "default_acl": "private", "querystring_auth": True}}
else:
    import warnings
    warnings.warn("USE_S3 is off: uploaded media is stored on Render's ephemeral disk and will be lost on redeploy.")

# Without a Celery worker service (Render's free plan has none), run tasks
# inline in the web process so notifications are still delivered.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Errors (with tracebacks) go to the Render log; without this Django only prints them when DEBUG is on.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}

SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:  # optional error alerts: set SENTRY_DSN in Render's environment
    import sentry_sdk
    sentry_sdk.init(dsn=SENTRY_DSN, send_default_pii=False,
                    traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
                    environment=env("SENTRY_ENVIRONMENT", default="render"))
