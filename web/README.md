This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Tests

End-to-end Playwright suite under `web/tests/e2e/`. Boots the real FastAPI BE
(uvicorn, `PROVIDER_BACKEND=fake`) and the real Next.js dev server together,
then drives Chromium against the FE on `http://localhost:3000` while the BE
runs on `http://localhost:8000`.

Prereqs (first run only):

- Python 3.11 + [uv](https://docs.astral.sh/uv/) on PATH so the `webServer`
  config can launch uvicorn from `../api/`.
- One-time browser install:

  ```bash
  pnpm test:e2e:install
  ```

Run the suite:

```bash
pnpm test:e2e          # headless
pnpm test:e2e:ui       # interactive runner
```

The BE uses an ephemeral SQLite at
`test-results/.playwright-db/test.sqlite3` for tests — your `api/dev.sqlite3`
is never touched. Playwright's `globalSetup` mints the file and creates the
schema via `python -m app.scripts.init_test_db`; `globalTeardown` removes it.

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
