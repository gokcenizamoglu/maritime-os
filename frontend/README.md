# MaritimeOS Frontend

Next.js (App Router, TypeScript, Tailwind CSS) frontend for MaritimeOS.
Part of the [MaritimeOS monorepo](../README.md) — see the root README
for the overall project and how this fits with `backend/`.

## Getting started

```bash
npm install
cp .env.example .env.local   # then set NEXT_PUBLIC_API_BASE_URL if it differs
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Yes | Base URL of the backend API (see `backend/`), e.g. `http://localhost:8000/api`. Read in `src/lib/api/config.ts` — never hardcoded in application code. |

## Structure

```
src/
├── app/         App Router routes, layout, global styles
├── components/  Shared, reusable UI building blocks
├── features/    Domain feature modules (empty for now — see features/README.md)
├── lib/api/     API base URL config + typed URL helper (no auth/fetch wrapper yet)
├── types/       Shared TypeScript types
└── config/      App-wide constants
```

## Scripts

- `npm run dev` — start the dev server
- `npm run build` — production build
- `npm run lint` — ESLint
