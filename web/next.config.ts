import path from "node:path";

import type { NextConfig } from "next";

const BE_ORIGIN =
  process.env.BE_ORIGIN ?? "https://olune-agent-server.fly.dev";

// Test-only E2E coverage. When COVERAGE=1 the FE is built with `next … --webpack`
// (see playwright.config.ts) and we append a `babel-plugin-istanbul` pass that
// instruments our own `src/**` modules. `enforce: "post"` runs istanbul AFTER
// Next's SWC loader, so babel only ever sees already-compiled JS (no TS/JSX
// parsing) and the emitted source maps point back at the original files. The
// instrumented modules register counters on `window.__coverage__`, which the
// Playwright coverage fixture drains after every test.
//
// This block is fully gated: with COVERAGE unset there is no `webpack` key, so
// the normal `next dev`/`next build` keep using Turbopack untouched and no
// instrumentation can leak into a production build.
const COVERAGE = process.env.COVERAGE === "1";

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

  ...(COVERAGE
    ? {
        // Loosely typed: NextConfig types the webpack config as `any`, and the
        // `webpack` package ships no types here. We only touch module.rules.
        webpack(config: { module?: { rules?: unknown[] } }) {
          config.module = config.module ?? {};
          config.module.rules = config.module.rules ?? [];
          config.module.rules.push({
            test: /\.(?:jsx?|tsx?)$/,
            include: path.resolve(__dirname, "src"),
            exclude: /node_modules/,
            enforce: "post",
            use: {
              loader: "babel-loader",
              options: {
                babelrc: false,
                configFile: false,
                // istanbul reads source maps from the prior (SWC) loader, so
                // its counts map back to the original TS/TSX sources.
                sourceMaps: true,
                plugins: ["babel-plugin-istanbul"],
              },
            },
          });
          return config;
        },
      }
    : {}),
};

export default nextConfig;
