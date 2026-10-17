import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
env_file = BASE_DIR / ".env"
if env_file.exists():
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-this-before-deploying")
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in {"true", "1", "yes"}
if not DEBUG and (not SECRET_KEY or SECRET_KEY == "dev-only-change-this-before-deploying"):
    raise RuntimeError("Set DJANGO_SECRET_KEY before running with DEBUG=False.")
configured_hosts = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_hostname and render_hostname not in configured_hosts:
    configured_hosts.append(render_hostname)
if not DEBUG and not configured_hosts:
    raise RuntimeError("Set DJANGO_ALLOWED_HOSTS or deploy on a host that supplies RENDER_EXTERNAL_HOSTNAME.")
ALLOWED_HOSTS = configured_hosts or ["127.0.0.1", "localhost"]

def env_bool(name, default="False"):
    return os.environ.get(name, default).strip().lower() in {"true", "1", "yes"}

CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]
render_external_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
if render_external_url and render_external_url not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(render_external_url)
AI_REQUESTS_PER_MINUTE = max(1, int(os.environ.get("AI_REQUESTS_PER_MINUTE", "10")))
AI_REQUESTS_PER_DAY = max(1, int(os.environ.get("AI_REQUESTS_PER_DAY", "100")))
OPENAI_MAX_OUTPUT_TOKENS = max(100, int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "700")))
LOGIN_RATE_LIMIT_ATTEMPTS = max(3, int(os.environ.get("LOGIN_RATE_LIMIT_ATTEMPTS", "8")))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = max(60, int(os.environ.get("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "900")))

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "finance.apps.FinanceConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "finance.context_processors.nav_active",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DEBUG and not DATABASE_URL:
    raise RuntimeError("Set DATABASE_URL to a managed PostgreSQL database before deploying.")
if DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://"):
    from urllib.parse import unquote, urlparse
    db_url = urlparse(DATABASE_URL)
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(db_url.path.lstrip("/")), "USER": unquote(db_url.username or ""), "PASSWORD": unquote(db_url.password or ""),
        "HOST": db_url.hostname or "", "PORT": db_url.port or 5432,
        "CONN_MAX_AGE": max(0, int(os.environ.get("DB_CONN_MAX_AGE", "60"))),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"sslmode": "require"} if not DEBUG else {},
    }}
elif not DEBUG:
    raise RuntimeError("Production requires PostgreSQL. SQLite is supported for local development only.")
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "Asia/Shanghai")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
PASSWORD_RESET_TIMEOUT = 3600
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend" if os.environ.get("EMAIL_HOST", "").strip() else "django.core.mail.backends.console.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "").strip()
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", "True")
EMAIL_TIMEOUT = max(1, int(os.environ.get("EMAIL_TIMEOUT", "10")))
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Nibi <no-reply@example.com>")
if not DEBUG and (not EMAIL_HOST or not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD):
    raise RuntimeError("Configure authenticated SMTP settings before production use so users can reset passwords.")
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = max(300, int(os.environ.get("SESSION_COOKIE_AGE", "3600")))
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
DATA_UPLOAD_MAX_MEMORY_SIZE = max(65536, int(os.environ.get("DATA_UPLOAD_MAX_MEMORY_SIZE", str(2_621_440))))
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "finance": {"handlers": ["console"], "level": os.environ.get("APP_LOG_LEVEL", "INFO"), "propagate": False},
    },
}
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = max(0, int(os.environ.get("DJANGO_HSTS_SECONDS", "3600")))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS")
    SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD")
    SECURE_REFERRER_POLICY = "same-origin"
    if os.environ.get("RENDER"):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    proxy_ssl_header = os.environ.get("DJANGO_SECURE_PROXY_SSL_HEADER", "").strip()
    if proxy_ssl_header:
        header, separator, value = proxy_ssl_header.partition(",")
        if not separator or not header.strip() or not value.strip():
            raise RuntimeError("DJANGO_SECURE_PROXY_SSL_HEADER must be formatted as HEADER,value.")
        SECURE_PROXY_SSL_HEADER = (header.strip(), value.strip())

SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
if SENTRY_DSN:
    import sentry_sdk

    def _sanitize_sentry_event(event, hint):
        request_data = event.get("request")
        if request_data:
            request_data["url"] = "[redacted]"
            for key in ("query_string", "data", "cookies", "headers", "env"):
                request_data.pop(key, None)
        event.pop("user", None)
        return event

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production" if not DEBUG else "development"),
        release=os.environ.get("SENTRY_RELEASE") or None,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        traces_sample_rate=0.0,
        before_send=_sanitize_sentry_event,
    )
