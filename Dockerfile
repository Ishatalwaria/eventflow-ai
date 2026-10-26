FROM python:3.14.9-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY config ./config
COPY apps ./apps
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --upgrade pip \
    && python -m pip install . \
    && python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip /usr/local/bin/pip* /tmp/pip-* /root/.cache/pip

RUN groupadd --system --gid 10001 eventflow \
    && useradd --system --uid 10001 --gid eventflow --home-dir /app eventflow
USER 10001:10001

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "30"]
