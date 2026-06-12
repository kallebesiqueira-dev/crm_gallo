# syntax=docker/dockerfile:1

# =============================================================================
# Multi-stage build for the Next.js frontend.
#
#   deps    → installs ALL deps (incl. dev). Shared base for dev + builder.
#   dev     → deps + app source + `npm run dev`. docker-compose targets THIS.
#             Local dev bind-mounts the source over it (live reload); CI e2e
#             runs the BAKED source with no bind mount (see
#             docker-compose.ci.yml), so the source must be in the image.
#   builder → produces the standalone production build (.next/standalone).
#   runner  → DEFAULT (final) stage: slim runtime with only the traced
#             production output. `docker build ./frontend` and the CI Trivy
#             scan get THIS image — no dev toolchain, and the esbuild Go
#             binary is stripped (see below).
# =============================================================================

# ---- deps -------------------------------------------------------------------
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# ---- dev --------------------------------------------------------------------
# Mirrors the original dev image: source baked in + `npm run dev`. Runs as a
# non-root user that owns /app, so `next dev` can write /app/.next even when
# the CI e2e job drops the bind mount.
FROM deps AS dev
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup -S app && adduser -S appuser -G app
COPY . .
# .next must exist (and be appuser-owned) IN the image: compose mounts an
# anonymous volume at /app/.next, and Docker takes the mountpoint's ownership
# from the image — without this, the volume comes up root-owned and `next dev`
# crash-loops on EACCES.
RUN mkdir -p /app/.next && chown -R appuser:app /app
USER appuser
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ---- builder ----------------------------------------------------------------
FROM deps AS builder
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
# Cloudflare Turnstile site key (public) — must be inlined at build time so the
# register widget can render; without it the widget is a no-op.
ARG NEXT_PUBLIC_TURNSTILE_SITE_KEY=
# PostHog product analytics (EU cloud by default). Empty key ⇒ analytics off,
# so the bundle builds + runs identically until a key is supplied at build time.
ARG NEXT_PUBLIC_POSTHOG_KEY=
ARG NEXT_PUBLIC_POSTHOG_HOST=https://eu.i.posthog.com
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_DEFAULT_LOCALE=$NEXT_PUBLIC_DEFAULT_LOCALE \
    NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN \
    NEXT_PUBLIC_SENTRY_ENVIRONMENT=$NEXT_PUBLIC_SENTRY_ENVIRONMENT \
    NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE=$NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE \
    NEXT_PUBLIC_TURNSTILE_SITE_KEY=$NEXT_PUBLIC_TURNSTILE_SITE_KEY \
    NEXT_PUBLIC_POSTHOG_KEY=$NEXT_PUBLIC_POSTHOG_KEY \
    NEXT_PUBLIC_POSTHOG_HOST=$NEXT_PUBLIC_POSTHOG_HOST \
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
# add a non-root user to run the server. `apk upgrade --no-cache` fetches a
# fresh index and pulls patched packages (e.g. openssl/libcrypto3/libssl3
# 3.5.7-r0 for CVE-2026-45447, PKCS7_verify use-after-free). Bump APK_REFRESH
# to bust the buildx GHA layer cache when a newly-published base CVE fix needs
# pulling — otherwise the cached `apk upgrade` layer serves a stale package set
# and Trivy flags an already-fixed CVE. (Runtime-reachable libs are upgraded,
# never added to .trivyignore — see that file's policy.)
ARG APK_REFRESH=2026-06-11
RUN echo "apk refresh ${APK_REFRESH}" \
 && apk upgrade --no-cache \
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

# esbuild ships a prebuilt Go binary (built with an old Go toolchain, so Trivy
# flags ~18 Go-stdlib HIGH/CRITICAL CVEs against it). It is a build-time tool
# that the production server (`node server.js`) never invokes, yet next's
# dependency trace copies it into the standalone bundle. Drop it so the runtime
# image carries no Go binary and the Trivy gate stays clean.
RUN rm -rf node_modules/@esbuild node_modules/esbuild

USER appuser
EXPOSE 3000

# Liveness: anything < 500 (incl. the `/` → locale redirect) means the Next
# server is up. Only 5xx / connection-refused is unhealthy. Node is in-image,
# so no extra tool is needed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "require('http').get('http://127.0.0.1:3000/',r=>process.exit(r.statusCode<500?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "server.js"]
