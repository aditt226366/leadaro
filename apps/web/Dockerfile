# leadaro-web — Next.js dashboard (apps/web).
#
# Build context is the REPO ROOT (not apps/web) so `npm ci` can resolve from
# apps/web/package-lock.json while still being invoked the same way Fly/Teploy
# expect — set "Working directory" to apps/web when configuring the platform
# app, or build with `docker build -f apps/web/Dockerfile .` from repo root.
#
# NEXT_PUBLIC_API_URL is a client-side var: Next.js bakes it into the JS
# bundle at `next build` time, not read at container start. It MUST be passed
# as a build ARG (see fly.toml's [build.args]), not just a runtime env var, or
# the deployed dashboard will call localhost:8000 forever regardless of what
# you set afterward.

FROM node:20-slim AS deps
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM node:20-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web/ .

ARG NEXT_PUBLIC_API_URL
ARG API_BASE_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV API_BASE_URL=${API_BASE_URL}
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# API_BASE_URL is also read server-side (next.config.js rewrites()) at
# request time, so it needs to survive into the runtime image too.
ARG API_BASE_URL
ENV API_BASE_URL=${API_BASE_URL}

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

ENV PORT=3000
EXPOSE 3000

CMD ["node", "server.js"]
