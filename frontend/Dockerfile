# syntax=docker/dockerfile:1

# =============================================================================
# Multi-stage build for the Next.js frontend.
#
#   deps    → installs ALL deps (incl. dev). docker-compose targets THIS stage
#             for local dev (compose `target: deps`), so `npm run dev` over the
#             bind mount has its toolchain + node_modules.
#   builder → produces the standalone production build (.next/standalone).
#   runner  → DEFAULT (final) stage: slim runtime with only the traced
#             production output. `docker build ./frontend` and the CI Trivy
#             scan get THIS image — the dev-only toolchain (playwright, vitest,
#             eslint and their node-tar/glob/cross-spawn transitives, TD-44)
#             is simply not present, so those HIGH CVEs disappear.
# =============================================================================

# ---- deps -------------------------------------------------------------------
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# ---- builder ----------------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app

# NEXT_PUBLIC_* are inlined into the browser bundle at build time, so they must
# be present during `next build`. Override per environment, e.g.:
#   docker build ./frontend \
#     --build-arg NEXT_PUBLIC_API_URL=https://api.crm.example.com \
#     --build-arg NEXT_PUBLIC_SENTRY_DSN=https://...ingest.sentry.io/...
ARG NEXT_PUBLIC_API_URL=http://localhost:8001
ARG NEXT_PUBLIC_DEFAULT_LOCALE=pt
ARG NEXT_PUBLIC_SENTRY_DSN=
ARG NEXT_PUBLIC_SENTRY_ENVIRONMENT=production
ARG NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE=0.1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_DEFAULT_LOCALE=$NEXT_PUBLIC_DEFAULT_LOCALE \
    NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN \
    NEXT_PUBLIC_SENTRY_ENVIRONMENT=$NEXT_PUBLIC_SENTRY_ENVIRONMENT \
    NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE=$NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE \
    NEXT_TELEMETRY_DISABLED=1

# node_modules from the deps stage (clean, linux). .dockerignore keeps the
# host's node_modules/.next out of the context so `COPY . .` can't clobber it.
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---- runner -----------------------------------------------------------------
FROM node:20-alpine AS runner
WORKDIR /app

# Patch base-image OS CVEs (mirrors the backend Dockerfile's apt upgrade) and
# add a non-root user to run the server.
RUN apk upgrade --no-cache \
 && addgroup -S app && adduser -S appuser -G app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Standalone output bundles server.js + a minimal traced node_modules. The
# `static` and `public` folders are NOT included by standalone — copy them in.
COPY --from=builder --chown=appuser:app /app/.next/standalone ./
COPY --from=builder --chown=appuser:app /app/.next/static ./.next/static
COPY --from=builder --chown=appuser:app /app/public ./public

USER appuser
EXPOSE 3000

# Liveness: anything < 500 (incl. the `/` → locale redirect) means the Next
# server is up. Only 5xx / connection-refused is unhealthy. Node is in-image,
# so no extra tool is needed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "require('http').get('http://127.0.0.1:3000/',r=>process.exit(r.statusCode<500?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "server.js"]
