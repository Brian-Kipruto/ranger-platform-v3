# Docker — `permission denied while trying to connect to the Docker API`

**First encountered:** 2026-05-09 (Checkpoint 2)
**Severity:** Blocks all `docker` and `docker compose` commands until fixed
**Frequency:** Always after first install if you don't fully log out before testing

---

## Symptom

Any `docker` command (including `docker ps`, `docker compose up`) fails with:

```
permission denied while trying to connect to the Docker API at unix:///var/run/docker.sock
```

Or with `docker compose up`:

```
unable to get image 'redis:7-alpine': permission denied while trying to connect to
the docker API at unix:///var/run/docker.sock
```

---

## Root cause

The Docker daemon listens on a Unix socket at `/var/run/docker.sock`. By default, only `root` and members of the `docker` group can read/write it.

When you run `sudo usermod -aG docker $USER`, your user IS added to the `docker` group at the system level — but **Linux only loads group memberships at login time**. Existing terminal sessions, VS Code processes, the desktop environment itself — all of them keep using the group set they had when *they* started.

So `groups` in your current shell shows the old set (no `docker`), and the docker socket rejects the connection.

---

## Diagnostic flow

Run these in order:

### 1. Confirm the group exists and you're in it at the system level

```bash
getent group docker
```

Expected:

```
docker:x:998:brian
```

The number after `:x:` (998 here) is the group ID, and the comma-separated list at the end is the members. If your username appears there, you're in the group at the system level — you just need to refresh your session.

If your username does NOT appear, the `usermod` command never ran successfully. Re-run:

```bash
sudo usermod -aG docker $USER
```

### 2. Confirm what your CURRENT shell thinks

```bash
groups
```

If `docker` doesn't appear in the output, your current shell still has the old group set. This is the normal case after a fresh install.

---

## Fix

### Best fix — full graphical logout

1. Save any open work
2. Top-right system menu → Log Out (NOT lock, NOT suspend)
3. Log back in at the GDM/login screen
4. Open a fresh terminal:

```bash
groups
# Expected: docker now appears in the list

docker ps
# Expected: empty table header, no error
```

This is the right fix. Once it's in, every new terminal works.

### Workaround — `newgrp docker` (per-terminal)

If you can't log out right now, in your current terminal:

```bash
newgrp docker
groups   # docker should now appear
docker ps   # should work
```

`newgrp` spawns a sub-shell with the new group active. **Limitation:** only this terminal. Every other terminal opened today still lacks docker access until full logout.

### Nuclear option — reboot

If logout/login doesn't take (rare, but happens on some Wayland sessions):

```bash
sudo reboot
```

Always works.

---

## Prevention

When you set up a new dev machine, after running `sudo usermod -aG docker $USER`:

1. Don't try to use docker in the same terminal session that ran the `usermod`
2. Log out fully and log back in BEFORE the first `docker` command
3. Run `groups` first to confirm `docker` is in the list

The `01-system-prep.md` setup guide has been updated to call this out explicitly in section 6.3.

---

## Why `sudo docker` "works" but is the wrong answer

Some online answers suggest just running `sudo docker compose up`. This works but is bad practice:

- **You'll forget the sudo at some point** and get the same error again
- **Files Docker creates will be owned by root** (mounted volumes, generated configs), causing permission issues later
- **It signals you don't understand the actual problem** — group membership

Use the proper group-based fix.

---

## Related

- [`docs/setup/01-system-prep.md`](../setup/01-system-prep.md) § 6.3 — Docker group setup
- [`docs/setup/02-services.md`](../setup/02-services.md) — Where this issue typically first hits

---

*Last updated: 2026-05-09*