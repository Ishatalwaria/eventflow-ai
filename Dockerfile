FROM python:3.12.15-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=60 \
    PIP_RETRIES=5

WORKDIR /app
ENV PATH="/app/.venv/bin:${PATH}" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md manage.py ./
RUN uv sync --frozen --no-dev --no-install-project
COPY config ./config
COPY apps ./apps
RUN uv sync --frozen --no-dev

RUN groupadd --system --gid 10001 eventflow \
    && useradd --system --uid 10001 --gid eventflow --home-dir /app eventflow \
    && mkdir -p /tmp/eventflow-prometheus \
    && chown -R 10001:10001 /tmp/eventflow-prometheus
USER 10001:10001

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health/ready', timeout=3).read()"
CMD ["gunicorn", "config.wsgi:application", "--config", "config/gunicorn.conf.py", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
