import type { NextConfig } from "next";

const BE_ORIGIN =
  process.env.BE_ORIGIN ?? "https://olune-agent-server.fly.dev";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=()",
  },
];

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
  async headers() {
    return [
      {
        // Apply security headers to all routes.
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
