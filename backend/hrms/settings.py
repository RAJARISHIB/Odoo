"""
Django settings for the HRMS Portal API.

Persistence is MongoDB via mongoengine, so the Django ORM / migrations stack is
intentionally not used.  `DATABASES` is left empty and the contrib apps that
require a relational backend (admin, auth, sessions, contenttypes) are not
installed.  Password hashing still works because `django.contrib.auth.hashers`
is a standalone utility module.
"""
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

from core.env import env_bool, env_int, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env_str("DJANGO_SECRET_KEY", "dev-insecure-django-secret-key")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "corsheaders",
    "core",
    "apps.users",
    "apps.organization",
    "apps.attendance",
    "apps.leaves",
    "apps.teams",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "core.middleware.RequestContextMiddleware",
    "core.middleware.ExceptionHandlerMiddleware",
]

ROOT_URLCONF = "hrms.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

WSGI_APPLICATION = "hrms.wsgi.application"
ASGI_APPLICATION = "hrms.asgi.application"

# No relational database - see module docstring.
DATABASES = {}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded files (company logos, avatars).  A plain directory so it can be
# mounted as a Docker volume; only the public URL is stored in Mongo.
MEDIA_URL = "/media/"
# Public origin of this API.  Uploaded files are stored with a relative path so
# the database stays portable, and serialised as absolute URLs so the Angular
# app (served from another origin) can load them.
API_PUBLIC_URL = env_str("API_PUBLIC_URL", "http://localhost:8000")
MEDIA_ROOT = env_str("MEDIA_ROOT", str(BASE_DIR / "media"))

# Where the Angular app lives.  Hitting the API root in a browser redirects
# here, so "localhost:8000" lands on the sign-in page instead of a 404.
FRONTEND_URL = env_str("FRONTEND_URL", "http://localhost:4200")
FRONTEND_LOGIN_PATH = env_str("FRONTEND_LOGIN_PATH", "/auth/login")

# Uploads are small images; cap the request body accordingly.
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# MongoDB (mongoengine)
# ---------------------------------------------------------------------------
MONGO = {
    "URI": env_str("MONGO_URI", "mongodb://localhost:27017"),
    "DB_NAME": env_str("MONGO_DB_NAME", "hrms"),
}

# ---------------------------------------------------------------------------
# Auth / JWT.  JWT_SECRET must match the Express WSS server so it can verify
# the same access tokens on the websocket handshake.
# ---------------------------------------------------------------------------
JWT = {
    "SECRET": env_str("JWT_SECRET", "change-me-in-production-super-secret"),
    "ALGORITHM": env_str("JWT_ALGORITHM", "HS256"),
    "ISSUER": "hrms-api",
    "ACCESS_TTL": timedelta(minutes=env_int("JWT_ACCESS_TTL_MIN", 60)),
    "REFRESH_TTL": timedelta(days=env_int("JWT_REFRESH_TTL_DAYS", 7)),
}

# ---------------------------------------------------------------------------
# Realtime (Express WSS) - Django pushes messages here over internal HTTP.
# ---------------------------------------------------------------------------
REALTIME = {
    "HTTP_URL": env_str("REALTIME_HTTP_URL", "http://localhost:4000"),
    "INTERNAL_API_KEY": env_str("INTERNAL_API_KEY", "change-me-internal-service-key"),
    "TIMEOUT_SECONDS": env_int("REALTIME_TIMEOUT_SECONDS", 5),
    "ENABLED": env_bool("REALTIME_ENABLED", True),
}

# ---------------------------------------------------------------------------
# API conventions
# ---------------------------------------------------------------------------
API = {
    "DEFAULT_PAGE_SIZE": env_int("API_DEFAULT_PAGE_SIZE", 20),
    "MAX_PAGE_SIZE": env_int("API_MAX_PAGE_SIZE", 100),
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", ["http://localhost:4200"])
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "origin",
    "user-agent",
    "x-request-id",
]

# ---------------------------------------------------------------------------
# Transport / browser security.  HTTPS-only settings are gated behind DEBUG so
# local development over plain http keeps working; a real deployment must run
# with DJANGO_DEBUG=False behind TLS.
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 0 if DEBUG else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if not DEBUG else None

# ---------------------------------------------------------------------------
# Email (password reset / verification).  Defaults to printing to the console
# in development; set EMAIL_HOST + credentials in .env to send real mail.
# ---------------------------------------------------------------------------
EMAIL_HOST = env_str("EMAIL_HOST", "")
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = env_int("EMAIL_PORT", 587)
    EMAIL_HOST_USER = env_str("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", "no-reply@dayflow.local")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
