# 015 — Truncated paste masquerades as a "has no exported member" TS error

*Date: 2026-06-25*

---

## What we saw

After pasting a new component file (`ActiveAlerts.tsx`) into VS Code (F07 CP5),
the editor's Problems panel showed:

```
Module '"@/components/dashboard/ActiveAlerts"' has no exported member 'ActiveAlerts'. ts(2305)
```

…and every authenticated route rendered as a **blank white page** (not just the
dashboard — `/visualizations` too). The importing file (`DashboardPage.tsx`)
clearly did `import { ActiveAlerts }` and the file clearly was named
`ActiveAlerts.tsx`, so the error looked nonsensical.

## What caused it

The paste into the editor was **truncated** — the file on disk did not contain
the full content, so it was missing its `export function ActiveAlerts()`
declaration. With no export, the import resolved to a module with no matching
member, TypeScript errored, and because the failure was at module-load time the
whole route tree failed to render → blank white page across all routes that pull
in that module graph.

The misleading part: the same file in the authoring sandbox compiled cleanly and
DID export `ActiveAlerts`. So we had a state where "the sandbox says this file
exports X, the user's machine says it doesn't" — which is the signature of a
content mismatch (truncated/partial/wrong paste), not a logic bug.

This is distinct from troubleshooting 004 (heredoc wrapper leaking INTO a paste).
Here the problem is the opposite: content was LOST from the paste.

## How we fixed it

Re-paste the file in full. Verified by checking the export landed:

```bash
grep -n "export function ActiveAlerts" src/components/dashboard/ActiveAlerts.tsx
wc -l src/components/dashboard/ActiveAlerts.tsx   # expect ~70 lines, not near-0
```

Once the complete file was on disk, the module resolved, the error cleared, and
all routes rendered again.

## How to prevent it

- **After pasting any file longer than ~60 lines, confirm its exports landed**
  before running the app:
  ```bash
  grep -n "export" <file>
  wc -l <file>
  ```
  Compare the line count to what you expect.
- **Recognize the signature:** a `has no exported member` / `Cannot find module`
  error for a file you just pasted, especially paired with a blank-white route,
  almost always means the paste was incomplete — check the file's length and tail
  before debugging imports.
- This is a known risk of the "author elsewhere → paste into editor" workflow.
  Large single-file pastes are the highest risk; a quick `tail <file>` to confirm
  the closing lines (e.g. the trailing `// ─── RANGER V3 END … ───` marker) are
  present is a cheap guard.
- A blank-white SPA with no console error usually means a module-load/throw
  during import resolution — start by checking the most recently edited/pasted
  file, not the page you're looking at.