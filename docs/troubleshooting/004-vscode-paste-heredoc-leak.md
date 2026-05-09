# Pasting from Chat — heredoc wrapper leaks into the file

**First encountered:** 2026-05-09 (Checkpoint 1, when filling in `docs/README.md`)
**Severity:** Files appear to work but contain extra junk lines
**Frequency:** Whenever copying code/markdown blocks out of chat into VS Code

---

## Symptom

After pasting content from chat into VS Code and saving, `git diff` shows unexpected lines at the top and bottom of the file:

```diff
+cat > docs/README.md << 'DOCS_README_EOF'
 # R.A.N.G.E.R. Platform V3 — Documentation
 ...
 *Last updated: 2026-05-09*
+DOCS_README_EOF
```

The file may also fail in subtle ways — for `.md` files it usually still renders OK because the wrapper lines are valid markdown text, but for source files it'll throw syntax errors.

---

## Root cause

Chat conversations sometimes wrap multi-line content in a heredoc command: