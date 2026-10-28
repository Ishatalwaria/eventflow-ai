import re

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

if KAFKA_SECURITY_PROTOCOL not in {"SSL", "SASL_SSL"}:  # noqa: F405
    raise RuntimeError("Production Kafka connections must use SSL or SASL_SSL")
if KAFKA_SECURITY_PROTOCOL == "SASL_SSL" and not all(  # noqa: F405
    [KAFKA_SASL_MECHANISM, KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD]  # noqa: F405
):
    raise RuntimeError("Production SASL_SSL Kafka requires mechanism, username, and password")
if not RABBITMQ_USE_TLS:  # noqa: F405
    raise RuntimeError("Production RabbitMQ connections must use TLS")
if RABBITMQ_USERNAME.lower() == "guest" or len(RABBITMQ_PASSWORD) < 24:  # noqa: F405
    raise RuntimeError("Production RabbitMQ requires a dedicated user and strong password")


def _is_local_host(host):
    return host.lower().strip("[]") in {"localhost", "127.0.0.1", "::1"}


if _is_local_host(RABBITMQ_HOST):  # noqa: F405
    raise RuntimeError("Production RabbitMQ must use a non-local host")

kafka_hosts = []
for server in KAFKA_BOOTSTRAP_SERVERS.split(","):  # noqa: F405
    match = re.fullmatch(r"\s*(\[[0-9a-fA-F:]+\]|[^:\s,]+):(\d{1,5})\s*", server)
    if match is None or int(match.group(2)) > 65535:
        raise RuntimeError("KAFKA_BOOTSTRAP_SERVERS must be a comma-separated host:port list")
    kafka_hosts.append(match.group(1).strip("[]"))
if any(_is_local_host(host) for host in kafka_hosts):
    raise RuntimeError("Production Kafka must use non-local broker hosts")

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
