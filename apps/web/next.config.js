/** @type {import('next').NextConfig} */
module.exports = {
  reactStrictMode: true,
  // Minimal self-contained server bundle for Docker (official Next.js Docker
  // pattern) — traces only the deps actually used instead of shipping the
  // whole node_modules tree into the image.
  output: "standalone",
  // NOTE: /api/* is proxied to the backend by app/api/[...path]/route.ts, which
  // reads API_BASE_URL at REQUEST time. A rewrite here would bake the target at
  // build time (breaks on Teploy, which can't inject build args), so it's gone.
};
