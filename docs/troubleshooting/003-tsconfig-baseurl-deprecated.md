# TypeScript — `baseUrl` is deprecated in TS 6, removed in TS 7

**First encountered:** 2026-05-09 (Checkpoint 4)
**Severity:** Build error, blocks development
**Frequency:** Any new project on TypeScript 6.0+

---

## Symptom

Running `npx tsc -b --noEmit` after adding a path alias to `tsconfig.app.json`:

```
tsconfig.app.json:5:5 - error TS5101: Option 'baseUrl' is deprecated and will
stop functioning in TypeScript 7.0. Specify compilerOption
'"ignoreDeprecations": "6.0"' to silence this error.
  Visit https://aka.ms/ts6 for migration information.

5     "baseUrl": ".",
      ~~~~~~~~~

Found 1 error.
```

---

## Root cause

Old guides (and our initial setup recipe) included `baseUrl` alongside `paths` in tsconfig:

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

This was the standard pattern in TypeScript 4 and 5. In TypeScript 6, `baseUrl` is deprecated. In TypeScript 7, it will be removed.

The reason: `baseUrl` was originally there to specify a different root for module resolution (e.g. compile files from one directory while resolving imports from another). It caused subtle bugs with bundlers (Vite, webpack, esbuild) and was rarely used the way it was intended. Modern TypeScript resolves `paths` relative to the tsconfig file's location automatically.

---

## Fix

**Remove the `baseUrl` line entirely. Keep `paths`.**

Before:
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

After:
```json
{
  "compilerOptions": {
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

The relative path `./src/*` resolves correctly relative to wherever `tsconfig.app.json` lives — no `baseUrl` needed.

Verify:
```bash
npx tsc -b --noEmit   # should pass silently
```

---

## Why this works

Pre-TS 6 path resolution:
- `paths` patterns are interpreted relative to `baseUrl`
- If no `baseUrl`, the patterns won't resolve at all

Post-TS 6 path resolution:
- `paths` patterns are interpreted relative to the tsconfig file's directory
- `baseUrl` is no longer needed (and is deprecated when present)

So `"./src/*"` in TypeScript 6+ resolves to `<tsconfig-dir>/src/*` automatically. Cleaner, fewer moving parts, more aligned with how bundlers resolve.

---

## Don't use `ignoreDeprecations`

The error message suggests:
```json
"ignoreDeprecations": "6.0"
```

This silences the error but doesn't fix anything. When you upgrade to TypeScript 7, the option will be removed entirely and your build will break. Just delete `baseUrl` now.

---

## When you'd actually need `baseUrl`

Almost never in modern projects. The legitimate use cases are:

1. You're compiling files from outside your project root and need TypeScript to look up imports from a different location
2. You're using a non-standard module resolution scheme

For a normal web app, `paths` alone is enough.

---

## Related

- [TypeScript 6 release notes](https://www.typescriptlang.org/) — deprecation announcement
- [TS5101 error reference](https://aka.ms/ts6) — migration info
- [`docs/setup/04-frontend-scaffold.md`](../setup/04-frontend-scaffold.md) §3 — where the alias is configured

---

*Last updated: 2026-05-09*