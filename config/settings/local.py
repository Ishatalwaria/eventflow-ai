from .base import *  # noqa: F403

DEBUG = env.bool("DEBUG", default=True)  # noqa: F405
SECRET_KEY = SECRET_KEY or "local-only-insecure-key-change-before-deploy"  # noqa: F405
