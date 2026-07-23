# leadaro-web — Next.js dashboard (apps/web).
#
# Build CONTEXT is apps/web itself (Fly "Working directory" = apps/web), so all
# COPY paths are relative to apps/web — NOT apps/web/... (that was the first
# failure: context=apps/web made `COPY apps/web/...` look for apps/web/apps/web).
# To reproduce the Fly build locally:  cd apps/web && docker build .
#
# NEXT_PUBLIC_API_URL is a client-side var: Next.js bakes it into the JS bundle
# at `next build` time, not read at container start. It MUST be passed as a
# build ARG (see fly.toml [build.args]), not just a runtime env var, or the
# deployed dashboard will call localhost:8000 forever.

FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

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

# API_BASE_URL is also read server-side (next.config.js rewrites()) at request
# time, so it needs to survive into the runtime image too.
ARG API_BASE_URL
ENV API_BASE_URL=${API_BASE_URL}

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

ENV PORT=3000
EXPOSE 3000

CMD ["node", "server.js"]
