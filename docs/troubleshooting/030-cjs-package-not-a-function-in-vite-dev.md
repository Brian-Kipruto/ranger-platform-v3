# 030 — `useWebSocket is not a function` in Vite dev, clean in `npm run build`

*Date: 2026-10-06*

---

## What we saw

The Dashboard rendered a blank page under `npm run dev`:

```
Uncaught TypeError: useWebSocket is not a function
    at LiveFeed (LiveFeed.tsx:35:26)
```

`tsc -b` and `npm run build` were both clean, and had been run before handing
the files over.

## The cause

`react-use-websocket@4.13.0` ships CommonJS only (`"main": "./dist/index.js"`, no
`"module"`, no `"exports"`), with the hook on `exports.default` behind
`__esModule`. Vite's dev pre-bundle and the production bundler interop that
default differently: production resolves `import useWebSocket from …` to the
function; the dev pre-bundle handed back the module object.

Type-checking can't see it — the `.d.ts` declares a default export, which is
true.

## The fix

Dropped the package. `LiveFeed.tsx` uses the browser's `WebSocket` in a
`useEffect` (~50 lines: subprotocols, close-code handling, capped backoff). The
token became an effect dependency, which also removed the need to remount the
component to change `protocols` — the library did not reconnect when
`protocols` changed. Package removed from `package.json` in the same feature.

## Prevention

- A clean build does not prove the dev server works. For frontend changes, load
  the page under `npm run dev` before calling it verified.
- Check a new dependency's `package.json`: CJS-only with a `default` export is a
  dev/prod interop risk under Vite.
- Related: TS-010 — another dev-only Vite module-resolution difference.
