FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Bump the date to invalidate this layer: CI's layer cache otherwise pins
# `apt-get upgrade` to whenever the layer was last built, so OS security
# patches (e.g. openssl deb13u2) never land in the scanned image.
ARG APT_SNAPSHOT=2026-06-10
RUN echo "apt snapshot: ${APT_SNAPSHOT}" \
 && apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    # WeasyPrint runtime (ADR-016): Pango/HarfBuzz do text layout, the
    # libjpeg/openjp2 pair lets embedded logos render, fonts-dejavu-core
    # provides actual glyphs (without a font the PDF renders blank text),
    # shared-mime-info lets WeasyPrint sniff embedded image types.
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    libjpeg62-turbo libopenjp2-7 shared-mime-info fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system app && useradd --system --gid app --home /app appuser

COPY requirements.txt .
RUN pip install --upgrade pip==26.1 && pip install -r requirements.txt

COPY . .
RUN chown -R appuser:app /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT:-8000}/health" || exit 1

# Boot: wait briefly for the platform's private network to come up, run
# migrations (retrying until the DB is reachable — Railway's private mesh
# takes a few seconds at container start, so a connect on the very first
# tick times out), then exec the API. `${PORT:-8000}` lets the platform
# (Railway/Fly/etc.) inject the listen port while defaulting to 8000 for
# local `docker run`. In docker-compose the service `command:` overrides
# this CMD, so the compose flow is unchanged.
CMD ["sh", "-c", "echo 'boot: waiting for private network'; sleep 8; n=0; until alembic upgrade head; do n=$((n+1)); if [ $n -ge 12 ]; then echo 'migrations failed after retries'; exit 1; fi; echo \"db not ready, retry $n\"; sleep 5; done; exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
