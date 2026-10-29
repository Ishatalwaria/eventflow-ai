from .base import *  # noqa: F403

DEBUG = env.bool("DEBUG", default=True)  # noqa: F405
SECRET_KEY = SECRET_KEY or "local-only-insecure-key-change-before-deploy"  # noqa: F405
# Local Swagger iteration allows more attempts; production keeps the base cap.
INCIDENT_SUMMARY_RATE_LIMIT = env.int("INCIDENT_SUMMARY_RATE_LIMIT", default=30)  # noqa: F405
if not 1 <= INCIDENT_SUMMARY_RATE_LIMIT <= 100:
    raise RuntimeError("INCIDENT_SUMMARY_RATE_LIMIT must be between 1 and 100")
