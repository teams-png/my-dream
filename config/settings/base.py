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
    "drf_spectacular",
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
    "apps.finance",
    "apps.industry",

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
    "apps.webapp.site_middleware.CustomDomainMiddleware",  # client websites on their own domains
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.RequestContextMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # --- custom, ordered deliberately ---
    "apps.tenants.middleware.ActiveCompanyMiddleware",       # resolves request.company / request.role
    "apps.subscriptions.middleware.SubscriptionGuardMiddleware",  # blocks routes once subscription expired
    "apps.webapp.role_access.RoleAccessMiddleware",          # pages each role may open (needs request.role)
    "apps.industry.demo_guard.DemoGuardMiddleware",           # the public demo businesses can't reach outside
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
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.tenants.context_processors.active_company",
                "apps.webapp.context_processors.user_companies",
                "apps.webapp.context_processors.enabled_features",
                "apps.webapp.context_processors.active_business_profile",
                "apps.webapp.context_processors.form_samples",
                "apps.webapp.context_processors.support_badges",
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

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("ar", "العربية"),
    ("ml", "മലയാളം"),
    ("hi", "हिन्दी"),
    ("ur", "اردو"),
    ("ta", "தமிழ்"),
    ("bn", "বাংলা"),
    ("ne", "नेपाली"),
    ("fil", "Filipino"),
    ("fr", "Français"),
    ("es", "Español"),
    ("tr", "Türkçe"),
    ("zh-hans", "简体中文"),
]
# Django has no built-in entry for Filipino; add it so language info lookups work.
from django.conf.locale import LANG_INFO  # noqa: E402
LANG_INFO.setdefault("fil", {"bidi": False, "code": "fil", "name": "Filipino", "name_local": "Filipino"})
LOCALE_PATHS = [BASE_DIR / "locale"]
# Keep "." as the decimal separator in every language: prices are also read
# by JavaScript and printed on receipts.
FORMAT_MODULE_PATH = ["config.formats"]
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
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
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
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)  # seconds; a dead mail server must not hang a page
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
# Shared secret for POST /cron/daily/ (the nightly GitHub Action sends it as X-Cron-Key).
CRON_SECRET = env("CRON_SECRET", default="")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")

# Razorpay handles India specifically (UPI / PhonePe / Google Pay / cards) —
# far better UPI success rates and a friendlier checkout for Indian
# customers than routing India through Stripe.
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")

# SkipCash handles Qatar (QAR cards, Apple Pay, Google Pay). Keys come from
# the SkipCash merchant portal; they can also be saved (encrypted) under
# Platform → Setup → Payment gateways, which takes precedence.
SKIPCASH_CLIENT_ID = env("SKIPCASH_CLIENT_ID", default="")
SKIPCASH_KEY_ID = env("SKIPCASH_KEY_ID", default="")
SKIPCASH_KEY_SECRET = env("SKIPCASH_KEY_SECRET", default="")
SKIPCASH_WEBHOOK_KEY = env("SKIPCASH_WEBHOOK_KEY", default="")
SKIPCASH_TEST_MODE = env.bool("SKIPCASH_TEST_MODE", default=True)

# Display-only exchange rates (units of each currency per 1 QAR) used to
# show visitors outside Qatar an estimate of the QAR price. Example:
# DISPLAY_FX_PER_QAR='{"GBP": "0.21", "EUR": "0.24"}'. Customers are always
# charged in QAR (or INR for India).
DISPLAY_FX_PER_QAR = env.json("DISPLAY_FX_PER_QAR", default={})

# Encrypts payment credentials saved from Platform Admin. Set a separate,
# long random value in production. SECRET_KEY is a backwards-compatible
# fallback so the settings screen remains usable before this is configured.
PAYMENT_CREDENTIALS_ENCRYPTION_KEY = env(
    "PAYMENT_CREDENTIALS_ENCRYPTION_KEY", default=SECRET_KEY,
)

# --- Public website ---
# Self-service sign-up with a free trial. Set PUBLIC_SIGNUP_ENABLED=False to
# accept new clients only through Platform Admin -> Add new client.
PUBLIC_SIGNUP_ENABLED = env.bool("PUBLIC_SIGNUP_ENABLED", default=True)
SIGNUP_LIMIT_PER_IP_PER_HOUR = env.int("SIGNUP_LIMIT_PER_IP_PER_HOUR", default=5)
# Sign-up sends a one-time code and makes the account only once it is typed (apps/accounts/signup_otp.py).
# "email" (default, needs a mail server), "sms" (Twilio Verify, needs the three TWILIO_* values), "" = off.
# The app's public address, for links in emails sent by daily jobs (Render sets RENDER_EXTERNAL_URL itself).
SITE_URL = env("SITE_URL", default=env("RENDER_EXTERNAL_URL", default=""))
SIGNUP_OTP = env("SIGNUP_OTP", default="email")
SIGNUP_OTP_SENDS_PER_HOUR = env.int("SIGNUP_OTP_SENDS_PER_HOUR", default=5)  # per address/number and per network
TWILIO_ACCOUNT_SID = env("TWILIO_ACCOUNT_SID", default="")
TWILIO_AUTH_TOKEN = env("TWILIO_AUTH_TOKEN", default="")
TWILIO_VERIFY_SERVICE_SID = env("TWILIO_VERIFY_SERVICE_SID", default="")
PHONE_OTP_CHANNEL = env("PHONE_OTP_CHANNEL", default="sms")  # or "whatsapp" once Twilio has a WhatsApp sender

# Shown on the user guide (/guide/) and the Terms, Privacy and Refund pages.
SUPPORT_EMAIL = env("SUPPORT_EMAIL", default="")
SUPPORT_WHATSAPP = env("SUPPORT_WHATSAPP", default="+91 98475 54224")  # WhatsApp and phone
LEGAL_COMPANY_NAME = env("LEGAL_COMPANY_NAME", default="Ajwaaz")
LEGAL_COMPANY_ADDRESS = env("LEGAL_COMPANY_ADDRESS", default="")
LEGAL_CR_NUMBER = env("LEGAL_CR_NUMBER", default="")
LEGAL_COUNTRY = env("LEGAL_COUNTRY", default="Qatar")
LEGAL_UPDATED = env("LEGAL_UPDATED", default="5 October 2026")

SPECTACULAR_SETTINGS = {
    "TITLE": "BookPilot API",
    "DESCRIPTION": "REST API for BookPilot. Sign in at /api/accounts/login/ to get a JWT access token "
                   "(send 'otp' too when two-step login is on), then send 'Authorization: Bearer <token>'. "
                   "Every request is scoped to your active business.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    "COMPONENT_SPLIT_REQUEST": True,
    # Older APIViews without serializers are still listed; hide the generator noise.
    "DISABLE_ERRORS_AND_WARNINGS": True,
    "ENABLE_DJANGO_DEPLOY_CHECK": False,
}

# Automatic daily backups (apps.tenants.backups). Without a "backups" storage the files go to this
# private folder, which is never served to the web.
BACKUP_ROOT = env("BACKUP_ROOT", default=str(BASE_DIR / "backups"))
BACKUP_TOKEN_KEY = env("BACKUP_TOKEN_KEY", default="")
# Optional: lets owners copy backups to their own Google Drive (Google Cloud OAuth client, Drive API on)
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID", default="")
GOOGLE_OAUTH_CLIENT_SECRET = env("GOOGLE_OAUTH_CLIENT_SECRET", default="")
