# 010 — Vite dev mode dynamic imports created multiple Zustand store instances

**Date:** 2026-05-10
**Symptom seen during:** Auth feature, Checkpoint 7 (testing the refresh interceptor's failure path)

## Symptom

Test scenario: log in → delete refresh cookie via DevTools → wait for access token to expire → make an API call.

Expected: silent refresh attempts, fails (no cookie), interceptor's catch block calls `useAuthStore.getState().clear()`, store goes empty, caller sees the 401.

Actual:
- Network tab showed exactly the right requests (me/ 401, refresh/ 401, no retry)
- Console diagnostic confirmed `clear()` ran on the store the interceptor saw
- BUT `window.useAuthStore.getState()` afterwards still showed `user: {…}, isAuthenticated: true`

Two console.logs, both right after `clear()`:
- One inside the interceptor: `State cleared: {user: null, isAuthenticated: false, ...}`
- One in the test code: `Final state: {user: {…}, isAuthenticated: true, ...}`

Same store name. Different state.

## Diagnosis

Equality check from the browser console:

```javascript
const m1 = await import("/src/stores/authStore.ts")
const m3 = await import("/src/stores/authStore")   // no extension
console.log("m1 === window.useAuthStore?", m1.useAuthStore === window.useAuthStore)
console.log("m1 === m3?", m1.useAuthStore === m3.useAuthStore)
// Both: false
```

**Three different module specifiers, three different module instances.** Each one's `create((set, get) => ...)` ran independently and produced its own Zustand store with its own state.

Specifically:
- `App.tsx` originally exposed the store via a static import → instance A
- The interceptor used `await import("../stores/authStore")` → instance B
- A test snippet used `await import("/src/stores/authStore.ts")` → instance C

The interceptor cleared instance B. The window-attached one was instance A. The test inspected instance C. They never agreed.

## Cause

Vite dev mode resolves dynamic imports per-specifier rather than per-resolved-file. Production builds (Rollup via `vite build`) deduplicate, so this bug doesn't appear in production. **Dev-only.**

`tsc --noEmit` was clean. `npm run build` was clean. The bug only manifested at runtime in the dev server.

## Fix

Replace dynamic imports with static imports at the top of `client.ts`:

```typescript
import { useAuthStore } from "../stores/authStore"
import { refresh as apiRefresh } from "./auth"
```

This creates a circular import chain — `client.ts → authStore.ts → auth.ts → client.ts` — but it's a **lazy circular**: the imported values (`useAuthStore`, `apiRefresh`) are only used inside functions that run after all modules have loaded. JavaScript handles that fine.

After the fix, all references to the store resolve through the same Vite module and there's exactly one instance.

## Why dynamic imports were used in the first place

To dodge the circular import. Felt safer at the time. Wasn't.

The lesson: in Vite + Zustand specifically, **prefer static imports even with cycles**. Cycles are fine as long as the imported values are only read inside function bodies that run post-init.

## Prevention

For any Zustand store (or any module that holds singleton state):

1. Always import via the same path everywhere — pick the alias (`@/stores/authStore`) or the relative path (`../stores/authStore`) and stick to it project-wide.
2. Never use `await import()` for that module unless code-splitting is genuinely needed.
3. If you suspect this bug: in the browser console, do the equality check above. If two specifiers don't equal, you've reproduced it.

## Why curl/REST tests didn't catch it

curl tests hit the backend directly and don't exercise the frontend store at all. The bug lives entirely in browser-side module resolution. Backend test suite (19 tests) was useless for finding this.

Adding a "real browser, real interactivity" test step at the end of every frontend feature is the right defense. Auth feature got it as Checkpoint 9; future features should too.