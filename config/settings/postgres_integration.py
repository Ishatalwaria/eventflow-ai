"""PostgreSQL-backed settings for integration tests requiring real concurrency."""

import os

os.environ.setdefault("POSTGRES_PASSWORD", "test-only-placeholder")

from .base import *  # noqa: F403

if not env("EVENTFLOW_TEST_DATABASE_URL", default=""):  # noqa: F405
    raise RuntimeError(
        "EVENTFLOW_TEST_DATABASE_URL must point to a dedicated test database and role"
    )

test_database = env.db_url("EVENTFLOW_TEST_DATABASE_URL")  # noqa: F405
test_database["CONN_MAX_AGE"] = 0
test_database["CONN_HEALTH_CHECKS"] = False
test_database.setdefault("OPTIONS", {}).update(
    {
        "connect_timeout": env("DATABASE_CONNECT_TIMEOUT"),  # noqa: F405
        "options": f"-c statement_timeout={env('DATABASE_STATEMENT_TIMEOUT_MS')}",  # noqa: F405
    }
)
DATABASES = {"default": test_database}
