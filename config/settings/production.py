from .base import *  # noqa: F403

DEBUG = False
if not SECRET_KEY:  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY must be set in production")
if len(SECRET_KEY) < 50 or "local-only" in SECRET_KEY:  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY must be a unique, strong production secret")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:  # noqa: F405
    raise RuntimeError("ALLOWED_HOSTS must contain explicit production hostnames")

# Production must use a managed/private PostgreSQL endpoint with TLS. Credentials
# should come from a deployment secret manager, never from this repository.
if not env("DATABASE_URL", default=""):  # noqa: F405
    raise RuntimeError("DATABASE_URL must be provided in production")
database = DATABASES["default"]  # noqa: F405
if database["ENGINE"] != "django.db.backends.postgresql":
    raise RuntimeError("Production DATABASE_URL must use PostgreSQL")
database_host = database.get("HOST", "").lower()
if database_host in {"localhost", "127.0.0.1", "::1"}:
    raise RuntimeError("Production DATABASE_URL must use a non-local PostgreSQL host")
database_options = database.setdefault("OPTIONS", {})
sslmode = database_options.setdefault("sslmode", "require")
if sslmode not in {"require", "verify-ca", "verify-full"}:
    raise RuntimeError("Production PostgreSQL connections must require TLS")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
