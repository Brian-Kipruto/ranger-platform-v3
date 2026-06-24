# 013 — Editor "Cannot find module" errors for files that exist (TS server cache)

> Feature 06. Severity: low (cosmetic; no build impact) but alarming.

## Symptom

After dropping new files into the repo (e.g. the `components/console/`
primitives, `config/demoAccounts.ts`), the VS Code Problems panel lit up with:

```
Cannot find module '@/components/console/MonoLabel' or its corresponding type declarations.  ts(2307)
Cannot find module '@/components/console/StatusDot' ...  ts(2307)
Cannot find module '@/config/demoAccounts' ...  ts(2307)
Parameter 'acct' implicitly has an 'any' type.  ts(7006)
```

— for files sitting *right there* in the file tree, with content, at the exact
paths the imports reference. A separate cosmetic warning also appeared:
`Unknown at rule @theme  css(unknownAtRules)` in `index.css`.

## Diagnosis

Two unrelated things, both harmless:

**1. The module errors are stale TS-server cache.** The editor's TypeScript
language server indexes files on a schedule; newly created files aren't always
picked up immediately, so imports of them resolve to "not found" until it
re-indexes. The proof it's phantom, not real: running the actual compiler on the
CLI —

```bash
npx tsc -b --force
```

— exits **clean** (no output) against the same files. The CLI compiler is
authoritative; the editor squiggles are not. The cascading `ts(7006)`
"implicitly any" error is downstream of the same cause: once the editor can't
resolve `demoAccounts`, it loses the `DemoAccount` type, so `acct` falls back to
`any`. Fix the resolution and it vanishes too.

**2. The `@theme` warning is the CSS language server, not TypeScript.** VS Code's
built-in CSS linter doesn't know Tailwind v4's `@theme` at-rule, so it flags it
as unknown. It's a lint warning with zero build impact — `vite build` compiles
`@theme` fine.

## Fix

**Module errors:** restart the TS server.

```
Ctrl+Shift+P → "TypeScript: Restart TS Server" → Enter
```

The module + implicit-any errors clear within a second or two. If they *don't*
clear after the restart, then it's real — but verify with `npx tsc -b --force`
first; if that's clean, the code is correct regardless of what the editor shows.

**The `@theme` lint warning** (optional — purely cosmetic): silence the CSS
linter's unknown-at-rule check in `.vscode/settings.json`:

```json
{ "css.lint.unknownAtRules": "ignore" }
```

## Prevention / rule of thumb

When new-file "Cannot find module" errors appear in the editor:

1. **Trust the CLI, not the squiggles.** Run `npx tsc -b --force`. Clean = the
   code is fine; the editor is just stale.
2. **Restart the TS server** as the reflex fix — it's the cure, not a workaround.
3. Don't start editing tsconfig paths / aliases chasing a phantom. The alias
   (`@/*`) is fine; the indexer is behind.

This is the frontend cousin of trusting `py_compile` / `manage.py shell -c` over
an editor's red underline. The standing handoff reminder already names this
failure mode ("stale editor TS-server cache can report phantom 'cannot find
module' — restart TS server; trust `tsc -b --force`"); this entry is the worked
example.

## Related docs

- `features/06-ui-retrofit.md` — the feature where this surfaced (twice)
- `troubleshooting/003-tsconfig-baseurl-deprecated.md` — a *real* path-resolution
  issue, for contrast (that one needed a config change; this one doesn't)