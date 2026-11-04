"""Shared P0 settings. PostgreSQL is the only supported database."""
import os
from pathlib import Path

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY; use DJANGO_DEBUG=true only locally.")
    SECRET_KEY = "local-development-only-not-for-deployment-" * 2
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "django.contrib.messages", "django.contrib.staticfiles", "django.contrib.postgres",
    "accounts", "marketplace", "risk", "buyer_app", "seller_app", "admin_app",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"],
              "APP_DIRS": True, "OPTIONS": {"context_processors": [
                  "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
                  "django.contrib.messages.context_processors.messages",
              ]}}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": os.getenv("PGDATABASE", "secondhand_fraud"),
                         "USER": os.getenv("PGUSER", "secondhand_web_login"), "PASSWORD": os.getenv("PGPASSWORD", ""),
                         "HOST": os.getenv("PGHOST", "localhost"), "PORT": os.getenv("PGPORT", "5432"),
                         "CONN_MAX_AGE": 0, "OPTIONS": {"connect_timeout": 5}}}
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailBackend"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.BCryptSHA256PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator", "OPTIONS": {"user_attributes": ["email", "full_name"]}},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en"
TIME_ZONE = os.getenv("MARKETPLACE_TIMEZONE", "Asia/Shanghai")
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "runtime" / "static"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = Path(os.getenv("PUBLIC_MEDIA_ROOT", str(BASE_DIR / "media" / "public")))
PRIVATE_MEDIA_ROOT = Path(os.getenv("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "media" / "private")))
ARTIFACT_ROOT = Path(os.getenv("ARTIFACT_ROOT", str(BASE_DIR / "artifacts")))
MEDIA_URL = "/listing-media/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/buyer-app/login/"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 32 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
FILE_UPLOAD_HANDLERS = ["marketplace.uploads.BoundedUploadHandler", "django.core.files.uploadhandler.MemoryFileUploadHandler", "django.core.files.uploadhandler.TemporaryFileUploadHandler"]
DATA_UPLOAD_MAX_NUMBER_FILES = 6
UPLOAD_MAX_BYTES = min(int(os.getenv("UPLOAD_MAX_BYTES", "5242880")), 5242880)
UPLOAD_MAX_PIXELS = int(os.getenv("UPLOAD_MAX_PIXELS", "40000000"))
MARKETPLACE_CURRENCY = os.getenv("MARKETPLACE_CURRENCY", "USD")
DEMO_LOCATIONS = os.getenv("DEMO_LOCATIONS", "Shanghai,Beijing,Guangzhou,Shenzhen,Hangzhou").split(",")
RATE_LIMITS = {"login": (10, 900), "registration": (5, 3600), "message": (30, 60), "listing": (20, 3600), "report": (5, 3600)}
for _name, (_count, _period) in list(RATE_LIMITS.items()):
    RATE_LIMITS[_name] = (int(os.getenv(f"RATE_{_name.upper()}_COUNT", str(_count))), _period)
LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")}}
