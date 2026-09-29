"""
Base settings shared across all environments.
Environment-specific overrides live in dev.py / render.py / production.py.
"""
from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
# .env is read explicitly by each environment file (dev.py reads it; production
# relies on real environment variables injected by the host, not a file).

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-dev-key-override-in-env")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",

    # shared utilities (Phase 18) — validators, permission classes; no models
    "apps.common",
    "apps.webapp",

    # platform / core apps — Foundation (Phase 2)
    "apps.accounts",
    "apps.tenants",
    "apps.modules",
    "apps.subscriptions",

    # core operations (Phase 3) — order matches the dependency graph in Phase 1 Section 13
    "apps.accounting",
    "apps.customers",
    "apps.suppliers",
    "apps.inventory",
    "apps.sales",
    "apps.purchases",
    "apps.expenses",
    "apps.employees",
    "apps.audit",
    "apps.reports",
    "apps.platform_admin",
    "apps.notifications",
    "apps.banking",
    "apps.collections",
    "apps.crm",
    "apps.analytics",

    # vertical modules (Phase 3) — Gym is the proof-of-concept
    "apps.verticals.gym",
    "apps.verticals.textile",
    "apps.verticals.spa",
    "apps.verticals.construction",
    "apps.verticals.mobile_shop",
    "apps.verticals.vehicle_wash",
    "apps.verticals.sports_shop",
    "apps.verticals.cycle_shop",
    "apps.verticals.saloon",
    "apps.verticals.beauty_parlour",
    "apps.verticals.medical_shop",
    "apps.verticals.protein_shop",
    "apps.verticals.restaurant",
]

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "webapp:login"
LOGIN_REDIRECT_URL = "webapp:dashboard"
LOGOUT_REDIRECT_URL = "webapp:login"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.RequestContextMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # --- custom, ordered deliberately ---
    "apps.tenants.middleware.ActiveCompanyMiddleware",       # resolves request.company / request.role
    "apps.subscriptions.middleware.SubscriptionGuardMiddleware",  # blocks routes once subscription expired
    # -------------------------------------
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.tenants.context_processors.active_company",
                "apps.webapp.context_processors.user_companies",
                "apps.webapp.context_processors.enabled_features",
                "apps.webapp.context_processors.active_business_profile",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("REDIS_URL", default="redis://localhost:6379/0")]},
    }
}

DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://postgres:postgres@localhost:5432/bookpilot")
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Argon2 first, per Phase 0 Section 14 (security architecture)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Qatar"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    # Phase 18 (Section 27 "Rate limiting"). "login" is the scope set via
    # throttle_scope on SecureTokenObtainPairView; anon/user are the
    # platform-wide defaults for every other endpoint.
    "DEFAULT_THROTTLE_RATES": {
        "login": "5/min",
        "anon": "60/min",
        "user": "1000/day",
    },
}

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "same-origin"

# Phase 18 (Section 27 "Login attempt protection") — used by
# apps.accounts.services.is_locked_out / record_attempt.
LOGIN_LOCKOUT_THRESHOLD = env.int("LOGIN_LOCKOUT_THRESHOLD", default=5)
LOGIN_LOCKOUT_WINDOW_MINUTES = env.int("LOGIN_LOCKOUT_WINDOW_MINUTES", default=15)

# --- Celery ---
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@bookpilot.local")
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# --- Security defaults (tightened further in production.py) ---
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# --- Payments ---
# GCC countries use the manual bank-transfer billing flow (Stripe doesn't
# operate as a merchant-account country there yet); everyone else gets a
# Stripe Checkout "Pay with Card" option on the Billing page.
GCC_COUNTRIES = ["Qatar", "UAE", "United Arab Emirates", "Saudi Arabia", "Oman", "Kuwait", "Bahrain"]

STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")

# Razorpay handles India specifically (UPI / PhonePe / Google Pay / cards) —
# far better UPI success rates and a friendlier checkout for Indian
# customers than routing India through Stripe.
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")

# Encrypts payment credentials saved from Platform Admin. Set a separate,
# long random value in production. SECRET_KEY is a backwards-compatible
# fallback so the settings screen remains usable before this is configured.
PAYMENT_CREDENTIALS_ENCRYPTION_KEY = env(
    "PAYMENT_CREDENTIALS_ENCRYPTION_KEY", default=SECRET_KEY,
)
