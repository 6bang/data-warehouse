import os
import secrets
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "").strip()
ALLOWED_HOSTS = [item.strip() for item in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]" if DEBUG else "").split(",") if item.strip()]
if not DEBUG:
    if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("django-insecure-"):
        raise ImproperlyConfigured("Production requires a strong, explicit DJANGO_SECRET_KEY (at least 50 characters).")
    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        raise ImproperlyConfigured("Production requires explicit DJANGO_ALLOWED_HOSTS without '*'.")
# A fresh development process never shares a published signing key. Set a stable
# key in .env to preserve login tokens across restarts.
SECRET_KEY = SECRET_KEY or secrets.token_urlsafe(64)
INTEGRATION_ENCRYPTION_KEY = os.getenv("INTEGRATION_ENCRYPTION_KEY", "").strip()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "django_filters",
    "rest_framework",
    "drf_spectacular",
    "apps.warehouse",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

DB_ENGINE = os.getenv("DB_ENGINE", "sqlite")
if DB_ENGINE == "sqlite":
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.getenv("SQLITE_PATH", str(BASE_DIR / "db.sqlite3"))}}
elif DB_ENGINE == "mysql":
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("MYSQL_DATABASE", "commerce_warehouse"),
        "USER": os.getenv("MYSQL_USER", "commerce"),
        "PASSWORD": os.getenv("MYSQL_PASSWORD", ""),
        "HOST": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "PORT": os.getenv("MYSQL_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
    }}
else:
    raise ImproperlyConfigured("DB_ENGINE must be 'sqlite' or 'mysql'.")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = [item.strip() for item in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if item.strip()]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "apps.warehouse.pagination.WarehousePagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.warehouse.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SPECTACULAR_SETTINGS = {"TITLE": "经营数据云仓 API", "VERSION": "0.1.0", "SERVE_INCLUDE_SCHEMA": False}

AI_API_BASE_URL = os.getenv("AI_API_BASE_URL", "")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-5-mini")
LARK_CLI_BIN = os.getenv("LARK_CLI_BIN", "lark-cli")

# Feishu OAuth login.  Keep the App Secret in the encrypted FeishuIntegration
# record; only the redirect URI, tenant allowlist and minimal user scopes live
# in environment configuration.
FEISHU_OAUTH_REDIRECT_URI = os.getenv("FEISHU_OAUTH_REDIRECT_URI", "")
FEISHU_ALLOWED_TENANT_KEYS = os.getenv("FEISHU_ALLOWED_TENANT_KEYS", "")
FEISHU_OAUTH_SCOPES = os.getenv("FEISHU_OAUTH_SCOPES", "")
