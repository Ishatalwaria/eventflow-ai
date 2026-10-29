FROM python:3.12.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=60 \
    PIP_RETRIES=5

WORKDIR /app
COPY pyproject.toml README.md manage.py ./
COPY config ./config
COPY apps ./apps
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip \
    && python -m pip install .

RUN groupadd --system --gid 10001 eventflow \
    && useradd --system --uid 10001 --gid eventflow --home-dir /app eventflow
USER 10001:10001

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
