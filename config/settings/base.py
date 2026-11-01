from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DATABASE_CONNECT_TIMEOUT=(int, 3),
    DATABASE_STATEMENT_TIMEOUT_MS=(int, 3000),
    DATABASE_CONN_MAX_AGE=(int, 60),
    LOG_LEVEL=(str, "INFO"),
    METRICS_TOKEN=(str, ""),
    METRICS_PORT=(int, 0),
    WORKER_METRICS_URLS=(list, []),
    PROMETHEUS_MULTIPROC_DIR=(str, ""),
    KAFKA_BOOTSTRAP_SERVERS=(str, "127.0.0.1:29092"),
    KAFKA_CONSUMER_GROUP=(str, "eventflow.kafka-to-rabbit.v1"),
    KAFKA_SECURITY_PROTOCOL=(str, "PLAINTEXT"),
    KAFKA_SASL_MECHANISM=(str, ""),
    KAFKA_SASL_USERNAME=(str, ""),
    KAFKA_SASL_PASSWORD=(str, ""),
    KAFKA_SSL_CA_LOCATION=(str, ""),
    RABBITMQ_HOST=(str, "localhost"),
    RABBITMQ_PORT=(int, 5672),
    RABBITMQ_USERNAME=(str, "eventflow-local"),
    RABBITMQ_PASSWORD=(str, ""),
    RABBITMQ_VHOST=(str, "/"),
    RABBITMQ_USE_TLS=(bool, False),
    RABBITMQ_CA_CERT=(str, ""),
    BROKER_CONNECT_TIMEOUT=(int, 5),
    OUTBOX_MAX_ATTEMPTS=(int, 12),
    OUTBOX_LEASE_SECONDS=(int, 60),
    OUTBOX_ALERT_AGE_SECONDS=(int, 300),
    WORKER_MAX_ATTEMPTS=(int, 3),
    CLICKHOUSE_HOST=(str, "localhost"),
    CLICKHOUSE_PORT=(int, 8123),
    CLICKHOUSE_DATABASE=(str, "eventflow"),
    CLICKHOUSE_USERNAME=(str, "eventflow"),
    CLICKHOUSE_PASSWORD=(str, ""),
    CLICKHOUSE_SECURE=(bool, False),
    CLICKHOUSE_CONNECT_TIMEOUT=(float, 3.0),
    CLICKHOUSE_SEND_RECEIVE_TIMEOUT=(float, 5.0),
    INCIDENT_LLM_PROVIDER=(str, "mock"),
    OPENAI_API_KEY=(str, ""),
    OPENAI_MODEL=(str, "gpt-4.1-mini"),
    GEMINI_API_KEY=(str, ""),
    GEMINI_MODEL=(str, "gemini-3.5-flash-lite"),
    GEMINI_FALLBACK_MODEL=(str, "gemini-3.5-flash-lite"),
    INCIDENT_LLM_TIMEOUT_SECONDS=(float, 45.0),
    INCIDENT_LLM_MAX_OUTPUT_TOKENS=(int, 1200),
    INCIDENT_LLM_MAX_ATTEMPTS=(int, 2),
    INCIDENT_LLM_RETRY_DELAY_SECONDS=(float, 0.25),
    INCIDENT_SUMMARY_RATE_LIMIT=(int, 5),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.common.apps.CommonConfig",
    "apps.events.apps.EventsConfig",
    "apps.workflows.apps.WorkflowsConfig",
    "apps.processing.apps.ProcessingConfig",
    "apps.incidents.apps.IncidentsConfig",
    "apps.analytics.apps.AnalyticsConfig",
]

MIDDLEWARE = [
    "apps.common.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if env("DATABASE_URL", default=""):
    default_database = env.db_url("DATABASE_URL", engine="django.db.backends.postgresql")
else:
    default_database = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="eventflow"),
        "USER": env("POSTGRES_USER", default="eventflow-user"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env("POSTGRES_PORT", default="5432"),
    }

default_database["CONN_MAX_AGE"] = env("DATABASE_CONN_MAX_AGE")
default_database["CONN_HEALTH_CHECKS"] = True
default_database.setdefault("OPTIONS", {}).update(
    {
        "connect_timeout": env("DATABASE_CONNECT_TIMEOUT"),
        "options": f"-c statement_timeout={env('DATABASE_STATEMENT_TIMEOUT_MS')}",
    }
)
DATABASES = {"default": default_database}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.common.authentication.APIClientAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.BoundedPageNumberPagination",
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {"incident-summary": "5/hour"},
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
}
EVENT_MAX_REQUEST_BYTES = 262_144
EVENT_BATCH_MAX_SIZE = 50
KAFKA_BOOTSTRAP_SERVERS = env("KAFKA_BOOTSTRAP_SERVERS")
KAFKA_DOMAIN_TOPIC = "eventflow.domain.events.v1"
KAFKA_LIFECYCLE_TOPIC = "eventflow.workflow.lifecycle.v1"
KAFKA_CONSUMER_GROUP = env("KAFKA_CONSUMER_GROUP")
KAFKA_SECURITY_PROTOCOL = env("KAFKA_SECURITY_PROTOCOL").upper()
KAFKA_SASL_MECHANISM = env("KAFKA_SASL_MECHANISM")
KAFKA_SASL_USERNAME = env("KAFKA_SASL_USERNAME")
KAFKA_SASL_PASSWORD = env("KAFKA_SASL_PASSWORD")
KAFKA_SSL_CA_LOCATION = env("KAFKA_SSL_CA_LOCATION")
BROKER_CONNECT_TIMEOUT = env("BROKER_CONNECT_TIMEOUT")
RABBITMQ_HOST = env("RABBITMQ_HOST")
RABBITMQ_PORT = env("RABBITMQ_PORT")
RABBITMQ_USERNAME = env("RABBITMQ_USERNAME")
RABBITMQ_PASSWORD = env("RABBITMQ_PASSWORD")
RABBITMQ_VHOST = env("RABBITMQ_VHOST")
RABBITMQ_USE_TLS = env("RABBITMQ_USE_TLS")
RABBITMQ_CA_CERT = env("RABBITMQ_CA_CERT")
OUTBOX_MAX_ATTEMPTS = env("OUTBOX_MAX_ATTEMPTS")
OUTBOX_LEASE_SECONDS = env("OUTBOX_LEASE_SECONDS")
OUTBOX_ALERT_AGE_SECONDS = env("OUTBOX_ALERT_AGE_SECONDS")
WORKER_MAX_ATTEMPTS = env("WORKER_MAX_ATTEMPTS")
WORKER_RETRY_DELAYS_SECONDS = (5, 30)
CLICKHOUSE_HOST = env("CLICKHOUSE_HOST")
CLICKHOUSE_PORT = env("CLICKHOUSE_PORT")
CLICKHOUSE_DATABASE = env("CLICKHOUSE_DATABASE")
CLICKHOUSE_USERNAME = env("CLICKHOUSE_USERNAME")
CLICKHOUSE_PASSWORD = env("CLICKHOUSE_PASSWORD")
CLICKHOUSE_SECURE = env("CLICKHOUSE_SECURE")
CLICKHOUSE_CONNECT_TIMEOUT = env("CLICKHOUSE_CONNECT_TIMEOUT")
CLICKHOUSE_SEND_RECEIVE_TIMEOUT = env("CLICKHOUSE_SEND_RECEIVE_TIMEOUT")
INCIDENT_LLM_PROVIDER = env("INCIDENT_LLM_PROVIDER").lower()
OPENAI_API_KEY = env("OPENAI_API_KEY")
OPENAI_MODEL = env("OPENAI_MODEL")
GEMINI_API_KEY = env("GEMINI_API_KEY")
GEMINI_MODEL = env("GEMINI_MODEL")
GEMINI_FALLBACK_MODEL = env("GEMINI_FALLBACK_MODEL")
INCIDENT_LLM_TIMEOUT_SECONDS = env("INCIDENT_LLM_TIMEOUT_SECONDS")
INCIDENT_LLM_MAX_OUTPUT_TOKENS = env("INCIDENT_LLM_MAX_OUTPUT_TOKENS")
INCIDENT_LLM_MAX_ATTEMPTS = env("INCIDENT_LLM_MAX_ATTEMPTS")
INCIDENT_LLM_RETRY_DELAY_SECONDS = env("INCIDENT_LLM_RETRY_DELAY_SECONDS")
INCIDENT_SUMMARY_RATE_LIMIT = env("INCIDENT_SUMMARY_RATE_LIMIT")
if not 1 <= INCIDENT_LLM_TIMEOUT_SECONDS <= 60:
    raise RuntimeError("INCIDENT_LLM_TIMEOUT_SECONDS must be between 1 and 60")
if not 1 <= INCIDENT_LLM_MAX_OUTPUT_TOKENS <= 4000:
    raise RuntimeError("INCIDENT_LLM_MAX_OUTPUT_TOKENS must be between 1 and 4000")
if not 1 <= INCIDENT_LLM_MAX_ATTEMPTS <= 3:
    raise RuntimeError("INCIDENT_LLM_MAX_ATTEMPTS must be between 1 and 3")
if not 0 <= INCIDENT_LLM_RETRY_DELAY_SECONDS <= 2:
    raise RuntimeError("INCIDENT_LLM_RETRY_DELAY_SECONDS must be between 0 and 2")
if not 1 <= INCIDENT_SUMMARY_RATE_LIMIT <= 100:
    raise RuntimeError("INCIDENT_SUMMARY_RATE_LIMIT must be between 1 and 100")
incident_retry_budget = INCIDENT_LLM_TIMEOUT_SECONDS * INCIDENT_LLM_MAX_ATTEMPTS + sum(
    min(INCIDENT_LLM_RETRY_DELAY_SECONDS * (2**attempt), 2.0)
    for attempt in range(INCIDENT_LLM_MAX_ATTEMPTS - 1)
)
if incident_retry_budget > 100:
    raise RuntimeError(
        "Configured incident provider timeout and retry budget must not exceed 100 seconds"
    )
ANALYTICS_RETRY_MAX_SECONDS = 30
OUTBOX_RETRY_BASE_SECONDS = 2
OUTBOX_RETRY_MAX_SECONDS = 300
SPECTACULAR_SETTINGS = {
    "TITLE": "EventFlow AI API",
    "DESCRIPTION": "Event-driven workflow and operational intelligence platform.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "apps.common.schema.add_api_error_envelopes",
    ],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"structured": {"()": "config.logging.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "structured"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL")},
}
METRICS_TOKEN = env("METRICS_TOKEN")
METRICS_PORT = env("METRICS_PORT")
WORKER_METRICS_URLS = env("WORKER_METRICS_URLS")
PROMETHEUS_MULTIPROC_DIR = env("PROMETHEUS_MULTIPROC_DIR")
