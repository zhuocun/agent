import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Generated istanbul coverage output (pnpm coverage:report).
    "coverage/**",
    // Generated Playwright HTML report (pnpm test:e2e). Both are gitignored;
    // linting the bundled report makes `pnpm lint` fail after an e2e run.
    "playwright-report/**",
  ]),
]);

export default eslintConfig;
