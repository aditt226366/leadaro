/** @type {import('next').NextConfig} */
module.exports = {
  reactStrictMode: true,
  // Minimal self-contained server bundle for Docker (official Next.js Docker
  // pattern) — traces only the deps actually used instead of shipping the
  // whole node_modules tree into the image.
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_BASE_URL || "http://localhost:8000"}/:path*`,
      },
    ];
  },
};
