FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY config ./config
COPY apps ./apps
RUN python -m pip install --upgrade pip && python -m pip install .

EXPOSE 8000
CMD ["sh", "-c", "python -m django migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 30"]
