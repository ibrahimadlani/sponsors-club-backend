"""Django settings for core project."""

import importlib.util
import os
from pathlib import Path
from urllib.parse import urlparse

try:  # pragma: no cover - gracefully absent before first pip install
    import dj_database_url as _dj_db_url
except ImportError:  # pragma: no cover
    _dj_db_url = None  # type: ignore[assignment]

try:  # pragma: no cover - fallback path exercised only when dependency missing
    from dotenv import load_dotenv
except (
    ModuleNotFoundError,
    ImportError,
):  # pragma: no cover - lightweight shim for constrained envs

    def load_dotenv(*_args, **_kwargs):
        """Gracefully skip dotenv loading when the optional dependency is absent."""

        return False


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Populate os.environ from a local .env file when running in development or tests
# so that Stripe keys (and any other secrets) can be injected without relying on
# shell-level exports. load_dotenv is a no-op if the file is missing.
load_dotenv(BASE_DIR / ".env")


# ---------------------------------------------------------------------------
# Sentry — error tracking and performance APM
# ---------------------------------------------------------------------------
# No-op when SENTRY_DSN is absent (local dev, CI).  The import is deferred so
# the package is never required in environments where the DSN is unset.
_sentry_dsn = os.environ.get("SENTRY_DSN")
if _sentry_dsn:  # pragma: no cover
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[
            DjangoIntegration(
                transaction_style="url",   # Group transactions by URL pattern
                middleware_spans=True,     # Trace time spent in each middleware
                signals_spans=True,        # Trace Django signal handlers
                cache_spans=True,          # Trace cache hits/misses
            ),
            RedisIntegration(),
        ],
        # Adjust in production: 0.1 = sample 10 % of transactions for APM
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,  # Never forward PII — GDPR compliance
        environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
        release=os.environ.get("GIT_COMMIT_SHA", ""),
    )


# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------

# Any value other than "false", "0", or "no" (case-insensitive) keeps DEBUG on.
# Production deployments must set:  DJANGO_DEBUG=false
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() not in ("false", "0", "no")


# ---------------------------------------------------------------------------
# Secret key — must come from the environment in production
# ---------------------------------------------------------------------------

_secret_key = os.environ.get("DJANGO_SECRET_KEY")

if not _secret_key and not DEBUG:
    # Refuse to start in production without a real secret key — an insecure
    # key would compromise HMAC signatures, session tokens, and CSRF protection.
    raise RuntimeError(
        "DJANGO_SECRET_KEY is not set. In production (DJANGO_DEBUG=false) a "
        "cryptographically strong key is required.\n"
        "Generate one with:\n"
        "  python -c \"from django.core.management.utils import "
        "get_random_secret_key; print(get_random_secret_key())\""
    )

# Falls back to the insecure dev key only in local/test environments (DEBUG=True).
SECRET_KEY = (
    _secret_key
    or "django-insecure-d=twofy9rdp(@w6qc8aqwao2n9fm=3*@to!+yhw=rct1+bf1+0"
)


# ---------------------------------------------------------------------------
# Allowed hosts
# ---------------------------------------------------------------------------

# Base set always present (covers local dev and DRF's test client hostname).
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "rest_framework",
    "django_filters",
    "corsheaders",
    "django_prometheus",  # Exposes /metrics for Prometheus scraping
    "core.apps.CoreConfig",
    "analytics",
    "athletes",
    "contracts",
    "follows",
    "messaging",
    "notifications",
    "payments",
    "organisations",
    "users",
]

DRF_YASG_ENABLED = importlib.util.find_spec("drf_yasg") is not None
SWAGGER_USE_COMPAT_RENDERERS = False
if DRF_YASG_ENABLED:
    INSTALLED_APPS.append("drf_yasg")

MIDDLEWARE = [
    # django-prometheus: MUST be first to time the full request/response cycle
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # django-prometheus: MUST be last to record after all other middlewares
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "core.urls"

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
            ],
        },
    },
]

ASGI_APPLICATION = "core.asgi.application"
WSGI_APPLICATION = "core.wsgi.application"


# ---------------------------------------------------------------------------
# Database — 12-Factor style: DATABASE_URL drives everything in production
# ---------------------------------------------------------------------------

_database_url = os.environ.get("DATABASE_URL")

if _database_url and _dj_db_url is not None and not os.environ.get("PYTEST_CURRENT_TEST"):
    # Production / staging: parse e.g. postgres://user:pw@host:5432/dbname
    # conn_max_age=600  — keep connections alive 10 min; reduces per-request overhead.
    # conn_health_checks — validate stale connections before reuse (safe in containers).
    DATABASES = {
        "default": _dj_db_url.config(
            default=_database_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # Local development and CI fall back to SQLite (zero-config, no server needed).
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Ensure STATIC_ROOT exists so tests and local development do not emit warnings
# before collectstatic runs (the directory is ignored in git and backed by a
# Docker volume in containerised environments).
STATIC_ROOT.mkdir(parents=True, exist_ok=True)
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
}


_default_cors_origins = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
)
_env_cors_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

CORS_ALLOWED_ORIGINS = _env_cors_origins or list(_default_cors_origins)
CORS_ALLOW_CREDENTIALS = True

# CSRF trusted origins must match CORS origins for secure cross-origin requests
CSRF_TRUSTED_ORIGINS = list(CORS_ALLOWED_ORIGINS)

# Copy CORS hostnames into ALLOWED_HOSTS so websocket origin checks match.
_cors_hosts = {
    parsed.hostname
    for origin in CORS_ALLOWED_ORIGINS
    if origin and (parsed := urlparse(origin)).hostname
}

# Production domains/IPs — comma-separated, e.g. "api.example.com,10.0.0.5"
_env_allowed_hosts = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if h.strip()
]

ALLOWED_HOSTS = list({*ALLOWED_HOSTS, *(_cors_hosts or set()), *_env_allowed_hosts})


AUTH_USER_MODEL = "users.User"


STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLIC_KEY = os.environ.get("STRIPE_PUBLIC_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_API_VERSION = os.environ.get("STRIPE_API_VERSION", "2024-06-20")

# Amazon SES email delivery configuration. Credentials default to blank values so
# local development can rely on environment variables when available without
# breaking tests if they are absent.
AWS_SES_ACCESS_KEY_ID = os.environ.get("AWS_SES_ACCESS_KEY_ID", "")
AWS_SES_SECRET_ACCESS_KEY = os.environ.get("AWS_SES_SECRET_ACCESS_KEY", "")
AWS_SES_REGION_NAME = os.environ.get("AWS_SES_REGION_NAME", "eu-west-3")
AWS_SES_SOURCE_EMAIL = os.environ.get(
    "AWS_SES_SOURCE_EMAIL", "no-reply@sponsors-club.test"
)
AWS_SES_CONFIGURATION_SET = os.environ.get("AWS_SES_CONFIGURATION_SET", "")

# Verification links default to an empty template so deployments can customise
# the destination (e.g. web frontend or deep link) without code changes.
EMAIL_VERIFICATION_URL_TEMPLATE = os.environ.get(
    "EMAIL_VERIFICATION_URL_TEMPLATE",
    "",
)


if os.environ.get("REDIS_URL"):
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [os.environ["REDIS_URL"]]},
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }


# ---------------------------------------------------------------------------
# Production security settings — active only when DEBUG is False
# ---------------------------------------------------------------------------

if not DEBUG:
    # Redirect every plain-HTTP request to HTTPS at the Django layer.
    # If a reverse proxy (Nginx, AWS ALB) already enforces HTTPS and forwards
    # only HTTP internally, set SECURE_SSL_REDIRECT=false to avoid redirect
    # loops and rely on SECURE_PROXY_SSL_HEADER alone.
    SECURE_SSL_REDIRECT = (
        os.environ.get("SECURE_SSL_REDIRECT", "true").lower()
        not in ("false", "0", "no")
    )

    # Tell Django to trust the X-Forwarded-Proto header injected by the proxy
    # so that request.is_secure() returns True for HTTPS connections terminated
    # upstream (required whenever TLS is offloaded before reaching Gunicorn).
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    # Session and CSRF cookies are only sent over encrypted connections.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # HSTS: instruct browsers to enforce HTTPS for this origin for 2 years.
    # SECURE_HSTS_PRELOAD submits the domain to browser preload lists — only
    # enable after confirming every subdomain is also HTTPS-only.
    SECURE_HSTS_SECONDS = 63072000  # 2 years
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Prevent browsers from MIME-sniffing a response away from its declared
    # Content-Type (mitigates content-injection attacks).
    SECURE_CONTENT_TYPE_NOSNIFF = True

    # Limit referrer information sent cross-origin (privacy + information leak).
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

    # Deny embedding this app in <frame>/<iframe> from other origins (clickjacking).
    X_FRAME_OPTIONS = "DENY"
