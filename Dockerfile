# leadaro — ONE image, all 5 services. Teploy can only build the repo-root
# Dockerfile (no per-app Dockerfile path, no build args), so every Teploy app
# uses THIS file and picks its role at runtime with the SERVICE env var:
#
#   SERVICE=api        -> FastAPI backend        (services/api)      HTTP
#   SERVICE=web        -> Next.js dashboard      (apps/web)          HTTP
#   SERVICE=worker     -> LiveKit voice worker   (services/agent)    no HTTP -> Skip health check
#   SERVICE=dialer     -> outbound dialer loop   (services/agent)    no HTTP -> Skip health check
#   SERVICE=post_call  -> after-call + reaper    (services/agent)    no HTTP -> Skip health check
#
# The web talks to the API same-origin via app/api/[...path]/route.ts using the
# runtime API_BASE_URL env var, so nothing about the API URL is baked at build
# (which is why no build args are needed) and there is no CORS.

# ── stage 1: build the Next.js dashboard ────────────────────────────────────
FROM node:20-bookworm-slim AS webbuild
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── stage 2: final runtime — Python base + the Node binary for the web server ─
FROM python:3.12-slim-bookworm

# node (copied from the same debian-bookworm base, so it's binary-compatible)
# runs the Next standalone server; libgomp1 is needed by onnxruntime (silero
# VAD in the voice worker); ca-certificates for outbound TLS (Neon, Anthropic,
# and the web->API proxy over https).
COPY --from=webbuild /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 libstdc++6 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# python deps for the API and the agent workers (installed once, shared)
COPY services/api/requirements.txt services/api/requirements.txt
COPY services/agent/requirements.txt services/agent/requirements.txt
RUN pip install --no-cache-dir -r services/api/requirements.txt \
 && pip install --no-cache-dir -r services/agent/requirements.txt

# all python code — services/api and services/agent kept as siblings so the
# cross-directory imports (routers/calls.py -> agent/dialer.py -> api/db.py)
# resolve by real path exactly like the repo.
COPY services/ services/

# Next.js standalone output -> /app/web (server.js + traced node_modules)
COPY --from=webbuild /web/.next/standalone ./web/
COPY --from=webbuild /web/.next/static ./web/.next/static
COPY --from=webbuild /web/public ./web/public

# Teploy assigns the container port via $PORT (its edge exposes 3000); the HTTP
# services bind to it. Workers ignore it.
ENV PORT=3000
ENV SERVICE=api

CMD case "$SERVICE" in \
      api)       exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-3000}" --app-dir services/api ;; \
      web)       cd web && HOSTNAME=0.0.0.0 PORT="${PORT:-3000}" exec node server.js ;; \
      worker)    exec python services/agent/worker.py start ;; \
      dialer)    exec python services/agent/dialer.py ;; \
      post_call) exec python services/agent/post_call.py ;; \
      *) echo "SERVICE must be api|web|worker|dialer|post_call, got '$SERVICE'" >&2; exit 1 ;; \
    esac
