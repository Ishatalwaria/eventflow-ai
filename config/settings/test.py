import os

os.environ.setdefault("POSTGRES_PASSWORD", "test-only-placeholder")

from .base import *  # noqa: F403

# Keep the default test suite isolated from a developer's PostgreSQL database.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
# Automated tests must never depend on an external provider or consume API quota,
# even when a developer's .env selects the live provider for local development.
INCIDENT_LLM_PROVIDER = "mock"
OPENAI_API_KEY = ""
GEMINI_API_KEY = ""
INCIDENT_SUMMARY_RATE_LIMIT = 5
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
