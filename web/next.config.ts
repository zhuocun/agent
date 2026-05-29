import type { NextConfig } from "next";

const BE_ORIGIN =
  process.env.BE_ORIGIN ?? "https://olune-agent-server.fly.dev";

const nextConfig: NextConfig = {
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
