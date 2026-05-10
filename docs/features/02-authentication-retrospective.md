# Feature 02 Retrospective — Authentication

> Period: 2026-05-10. Sessions: 1. Branch: `feat/auth`.

## What worked

**Specs before code, with explicit design decisions.** Walking through the seven design questions (refresh token storage, blacklist on logout, login response shape, /me payload fields, validation library, ProtectedRoute redirect behavior, permission-gating scope) before writing any code locked in choices that would have been painful to change mid-build. Especially refresh-storage — the cookie path got 70% of the security and operational discipline of the feature.

**Backend tests written end-of-backend, not after frontend.** 19 tests landed in one push at Checkpoint 4. Locking down the backend contract before touching the frontend meant frontend bugs couldn't accidentally drag the backend along — every "is the backend wrong?" question got answered by re-running tests, in 3 seconds, instead of a multi-step manual test loop.

**Marker convention paid for itself.** When the cookie-helpers / refresh-views markers got nested wrong, `grep -n "RANGER V3" views.py` made the issue visible in 6 lines. Catching it before commit kept the diff readable.

**Slow on the security-critical bits.** Checkpoint 3 (httpOnly cookie + logout blacklist) and Checkpoint 7 (refresh interceptor) each got their own dedicated checkpoint with explicit "this is the most error-prone step" framing. Both surfaced real bugs (Secure-flag-in-dev, multi-instance Zustand) that would have been embarrassing if shipped.

## What was hard

**Vite dev mode multi-instance bug.** Easily the most painful hour of the feature. Curl tests passed. Backend tests passed. `tsc --noEmit` passed. `npm run build` passed. The only signal was "the UI behaves wrong" in a way that looked like the catch block wasn't running. Diagnostic logs revealed `clear()` was running but on a different store instance than the one being inspected. Took building a script to compare module identities (`m1.useAuthStore === m2.useAuthStore`) before the cause was visible. Lesson written up in `troubleshooting/010`.

**The `Secure` flag bug almost shipped.** `REFRESH_COOKIE = {"secure": not DEBUG, ...}` in `base.py` is wrong because `base.py` evaluates before `development.py` overrides `DEBUG`. curl ignored it; the bug would have only manifested in real browsers. Catching it pre-Checkpoint 6 saved a bad debugging session. Pattern to watch for: anything in `base.py` that references `DEBUG` or other env-dependent values via a baked-in expression.

**Curl's silence flag (`-s`) hid login failures.** `ACCESS=$(curl -s ... | jq -r .access)` returned `"null"` when login failed (jq's behavior on missing field), then "ACCESS got assigned, must have worked" — but `${#ACCESS}` was 4, not 200+. Lost ~10 minutes before noticing. Lesson: don't add `-s` until the command is known to work.

**Paste artifacts in long terminal output.** A few times, terminal output ran together (next prompt eating end of curl response, paged diffs duplicated, brackets in placeholders surviving the paste). None of these were code bugs but they cost minutes each. For complex command output, `| tail -N` and `| jq` are nicer than scrollback wrangling.

## What to do differently next time

**Schedule a dedicated tidy step instead of mid-checkpoint refactor offers.** Twice during the build I offered "you can move imports to the top if you want" as an optional refactor mid-checkpoint. This produced a duplicate-imports mess in `views.py` because the offer was applied AND the original local imports stayed. Cleaner: each checkpoint gets one source-of-truth instruction, and a dedicated cleanup checkpoint runs at end of the feature.

**Browser-based testing earlier.** Cookie security flags only matter to real browsers; curl ignores `Secure`. The Secure-flag bug was caught proactively only because Checkpoint 6 was framed as browser-based. Future features touching cookies should plan a real-browser test no later than the second checkpoint that introduces a new cookie-related behavior.

**Capture session-restart gotchas early.** Two of the troubleshooting entries (`006`, `007`) are about fresh-terminal state — Postgres not running, virtualenv not active. Both are obvious in hindsight. Worth adding to the README's "starting a session" section so future sessions don't rediscover them.

**Pre-write the troubleshooting docs as we hit the bugs.** I noted the bugs as they happened but only wrote the docs at the end. When the bug is fresh, the symptom-cause-fix narrative is cleaner. Quick scratchpad notes during the build, formal docs at end.

## Numbers

- 11 checkpoints across one session
- 2 functional commits + 1 docs commit
- 19 backend tests, all green, ~3.3s runtime
- 5 distinct bugs caught (none shipped): self-referential URL include, refresh cookie Secure-in-dev, duplicate imports, mis-nested markers, Vite multi-instance store
- Frontend bundle grew from 232KB → 368KB (+135KB) for react-router + react-hook-form + zod. Within budget for now; code-splitting per-route becomes important when Phase 2 adds Three.js/MapLibre.

## Carry-forwards for the next feature

- Three-terminal dev workflow (docker, runserver, vite) is the new norm
- `python manage.py test <app> -v 2 2>&1 | tail -5` is a good "did I break tests" smoke test
- Static imports only for any module holding singleton state — Zustand stores especially
- Conventional commits (`feat(scope):`, `docs:`) feel right; keep them