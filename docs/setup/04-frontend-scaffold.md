# 04 — React + TypeScript + Vite Frontend Scaffold

**Date completed:** 2026-05-09
**Prerequisites:** [`03-backend-scaffold.md`](./03-backend-scaffold.md) (Django backend running on port 8000)
**Goal:** Set up a React 19 + TypeScript + Vite frontend with Tailwind v4, React Router, Zustand, and Axios. Vite dev server proxies API and WebSocket traffic to the Django backend.

The frontend is intentionally minimal at this stage — just enough to confirm the toolchain is wired correctly. Pages, panels, and stores get filled in feature by feature.

---

## Contents

1. [Scaffold Vite + React-TS](#1-scaffold-vite--react-ts)
2. [Install dependencies](#2-install-dependencies)
3. [Configuration files](#3-configuration-files)
4. [Project directory structure](#4-project-directory-structure)
5. [API client + auth store stubs](#5-api-client--auth-store-stubs)
6. [Placeholder home page](#6-placeholder-home-page)
7. [Smoke test](#7-smoke-test)
8. [Commit](#8-commit)

---

## 1. Scaffold Vite + React-TS

We let Vite create the project from scratch. The `--` separator passes flags to Vite (not npm):

```bash
cd ~/projects/ranger-platform-v3
rmdir ranger_frontend   # the empty directory created in checkpoint 1
npm create vite@latest ranger_frontend -- --template react-ts
cd ranger_frontend
npm install
```

Pinning the template (`react-ts`) bypasses Vite's interactive prompts, useful for reproducibility.

> **Vite versions evolve quickly.** As of this build, we got Vite 8.0.11. Earlier in 2026 you'd have gotten Vite 7. The setup pattern is stable across these but specifics (which `vite.config.ts` syntax works) may shift. Check the Vite changelog when you reset up.

### Versions installed (May 2026 baseline)

| Package | Version | Note |
|---|---|---|
| react | 19.2.6 | React 19 stable |
| typescript | 6.0.3 | TS 6 (deprecates `baseUrl`) |
| vite | 8.0.11 | Vite 8 |
| react-router-dom | 7.15.0 | V7 stable |
| zustand | 5.0.13 | V5 |
| tailwindcss | 4.3.0 | V4 (plugin-based, no PostCSS) |

---

## 2. Install dependencies

Project deps:

```bash
npm install \
  react-router-dom \
  zustand \
  axios \
  react-hook-form \
  zod \
  @hookform/resolvers \
  react-use-websocket \
  class-variance-authority \
  clsx \
  tailwind-merge \
  lucide-react \
  @radix-ui/react-slot
```

Dev deps:

```bash
npm install -D \
  tailwindcss \
  @tailwindcss/vite \
  @types/node
```

### Why each

- **react-router-dom** — page routing
- **zustand** — global state. Lighter than Redux, less ceremony than Context for non-trivial state.
- **axios** — HTTP client with global config (interceptors, base URL). Could use `fetch` but Axios's interceptors make JWT handling cleaner.
- **react-hook-form + zod** — form state and validation. Standard combo. Validates with TypeScript types end-to-end.
- **react-use-websocket** — React-friendly WebSocket hook with auto-reconnect.
- **class-variance-authority, clsx, tailwind-merge** — shadcn/ui dependencies; we install them now so adding shadcn components later is one command.
- **lucide-react** — icon library. Tree-shaken so unused icons don't ship.
- **@radix-ui/react-slot** — another shadcn/ui dependency.
- **tailwindcss + @tailwindcss/vite** — Tailwind v4. The new `@tailwindcss/vite` plugin replaces the v3 PostCSS pipeline.
- **@types/node** — needed for `import path from "node:path"` in `vite.config.ts`.

---

## 3. Configuration files

### `vite.config.ts`

Three things to configure:

1. **Plugins:** `react()` and `tailwindcss()`
2. **Path alias:** `@/*` → `./src/*` so imports look like `import { useAuthStore } from "@/stores/authStore"`
3. **Dev proxy:** forward `/api` → Django (HTTP) and `/ws` → Daphne (WebSocket). Means the React app calls `fetch("/api/...")` like it's same-origin; no CORS dance during dev.

The `import path from "node:path"` plus `path.resolve(__dirname, "./src")` makes the alias absolute, which Vite needs for production builds.

### `tsconfig.app.json` — the path alias

The alias has to be told to TypeScript too, otherwise the IDE complains about unresolved `@/...` imports.

In `tsconfig.app.json`'s `compilerOptions`, add:

```json
"paths": {
  "@/*": ["./src/*"]
}
```

**Do NOT add `baseUrl`** — it's deprecated in TypeScript 6 and will be removed in TS 7. Modern TS resolves `paths` relative to the tsconfig file's location automatically. See [`troubleshooting/003-tsconfig-baseurl-deprecated.md`](../troubleshooting/003-tsconfig-baseurl-deprecated.md).

The alias goes ONLY in `tsconfig.app.json`, not the root `tsconfig.json`. The root is a references file; `tsconfig.app.json` is what compiles your code.

### `src/index.css` — Tailwind v4 entry

Single line: `@import "tailwindcss";` — replaces v3's three `@tailwind` directives.

Plus a CSS variable for tenant theming (`--primary-theme-color`) and a dark slate-900 body background for the Foxglove-inspired aesthetic.

### Verify

```bash
npx tsc -b --noEmit
```

Should pass silently. Errors here usually mean the alias isn't reachable — double-check `tsconfig.app.json`.

---

## 4. Project directory structure

```
src/
├── api/             ← Axios clients (per domain)
├── components/
│   ├── ui/          ← shadcn primitives (button, dialog, etc.)
│   └── panels/      ← Foxglove-style panels (3D, image, plot, map, etc.)
├── pages/           ← top-level page components
├── stores/          ← Zustand stores
├── hooks/           ← custom React hooks
├── types/           ← shared TypeScript types
└── utils/           ← pure helper functions
```

Mirrors §10 of the V3 architecture doc. Created with one mkdir command:

```bash
cd src
mkdir -p api components/ui components/panels pages stores hooks types utils
```

Vite scaffolds an `assets/` directory too — fine, leave it. Used for SVGs that import as URL strings.

---

## 5. API client + auth store stubs

### `src/api/client.ts` — singleton Axios instance

```typescript
export const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("ranger_access_token")
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
```

The request interceptor attaches the JWT bearer token from localStorage to every request. The response interceptor is a stub for now — silent token refresh on 401 ships with the auth feature.

> **Why localStorage and not httpOnly cookie?** Tradeoffs. localStorage is vulnerable to XSS if a malicious script gets injected; httpOnly cookies are immune to XSS but vulnerable to CSRF (mitigatable). For a JWT-bearer-token API where the threat model is mainly external attackers and we have a strong CSP, localStorage is acceptable. Reconsider if XSS becomes a concern. Documented in the auth feature ADR (TBD).

### `src/stores/authStore.ts` — Zustand stub

A typed store with `user`, `accessToken`, `isAuthenticated`, `setTokens()`, `logout()`. The actual login API call is not here yet — that's the auth feature.

---

## 6. Placeholder home page

`src/pages/HomePage.tsx` — sky-blue heading, dark slate background, a checklist of what's done. Functional purpose: confirm Tailwind is wired (if classes apply visually, the v4 plugin pipeline works).

`src/App.tsx` — imports the page, sets up `BrowserRouter` with one route `/`.

`src/main.tsx` — boots `<App />` into `<div id="root">`.

`src/App.css` is deleted. Tailwind handles all styling.

---

## 7. Smoke test

```bash
npm run dev
```

Expected output ends with:
```
VITE v8.x.x ready in <ms>
➜  Local:   http://localhost:5173/
```

Visit `http://localhost:5173/`. Should see:
- Dark slate-900 background
- "R.A.N.G.E.R. Platform V3" in sky-blue, large bold (Tailwind class `text-sky-400`)
- Subtitle in muted grey
- A bordered slate-800 card with the phase 1 checklist

If the text is unstyled black-on-white, Tailwind isn't being applied. Check:
- `vite.config.ts` includes `tailwindcss()` in the plugins array
- `src/index.css` has `@import "tailwindcss";`
- `src/main.tsx` imports `./index.css`

---

## 8. Commit

```bash
cd ~/projects/ranger-platform-v3
git status
```

Important: confirm `node_modules/` does NOT appear. The Vite scaffold creates `ranger_frontend/.gitignore` which excludes it; combined with the project root `.gitignore`, you should be safe. If `node_modules/` shows up — stop, fix the gitignore, never commit it.

```bash
git add ranger_frontend/
git commit -m "feat: react 19 + typescript + vite + tailwind v4 frontend scaffold"
git push
```

---

## End state

- Vite 8 dev server runs on `http://localhost:5173`
- Proxies `/api/*` → `http://localhost:8000` (Django HTTP)
- Proxies `/ws/*` → `ws://localhost:8000` (Daphne WebSocket)
- React 19, TypeScript strict mode, Tailwind v4
- `@/*` import alias works
- Zustand auth store + Axios client are stub-wired

**Phase 1 complete.** Next: Feature 1 (auth flow — login, logout, JWT refresh).

---

## Things that went wrong

### 1. Vite/TypeScript versions newer than expected

The Vite template now installs Vite 8, TypeScript 6, React 19. None broke us, but the version mismatch with the V3 doc (which assumed Vite 5/TS 5/React 19) means future-you should re-verify if syntax has shifted further.

### 2. `tsconfig.json` with `baseUrl` failed in TS 6

`baseUrl` is deprecated. Drop it; TS 6+ resolves `paths` relative to tsconfig location.

Detail: [`troubleshooting/003-tsconfig-baseurl-deprecated.md`](../troubleshooting/003-tsconfig-baseurl-deprecated.md).

### 3. Pasting markdown content from chat into VS Code can include the heredoc wrapper

When copying a `cat > file << 'EOF' ... EOF` block from chat into VS Code, the wrapper lines often get included. Check first and last lines of the file after pasting.

Detail: [`troubleshooting/004-vscode-paste-heredoc-leak.md`](../troubleshooting/004-vscode-paste-heredoc-leak.md).

---

*Document last updated: 2026-05-09*