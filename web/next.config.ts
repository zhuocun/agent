import type { NextConfig } from "next";

const BE_ORIGIN =
  process.env.BE_ORIGIN ?? "https://olune-agent-server.fly.dev";

const nextConfig: NextConfig = {
  // Production browser code calls same-origin /api/*. This server-side rewrite
  // forwards those requests to Fly while preserving first-party cookies on the
  // Vercel origin. For local proxy testing, set BE_ORIGIN=http://localhost:8000.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BE_ORIGIN}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
