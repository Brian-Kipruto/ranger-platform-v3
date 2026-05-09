# 01 — System Preparation

**Date completed:** 2026-05-09
**Machine:** Ubuntu 22.04.5 LTS (`Kipruto`, x86_64)
**Goal:** Get a fresh Ubuntu machine ready to build R.A.N.G.E.R. V3 — install Python 3.11, Node.js 20, Docker, set up GitHub SSH auth, scaffold the project repo.

This doc is the "from zero to first commit" guide. If you ever need to set up a new dev machine, follow it top to bottom.

---

## Contents

1. [Verify baseline system](#1-verify-baseline-system)
2. [Install Python 3.11](#2-install-python-311)
3. [Install system build dependencies](#3-install-system-build-dependencies)
4. [Disable native PostgreSQL (we use Docker)](#4-disable-native-postgresql-we-use-docker)
5. [Install Node.js 20](#5-install-nodejs-20)
6. [Install Docker](#6-install-docker)
7. [Set up GitHub SSH authentication](#7-set-up-github-ssh-authentication)
8. [Configure git identity](#8-configure-git-identity)
9. [Clone the repo and scaffold the project](#9-clone-the-repo-and-scaffold-the-project)
10. [First commit and push](#10-first-commit-and-push)

---

## 1. Verify baseline system

Before installing anything, confirm what's already on the machine.

```bash
lsb_release -a
python3 --version
git --version
```

**Expected:**
- Ubuntu 22.04.x LTS (jammy)
- Python 3.10.x (the system default — we'll add 3.11 alongside it, not replace)
- git 2.34+

> **Important:** Don't replace the system `python3`. Ubuntu 22.04's system tools depend on 3.10. We install 3.11 as a parallel command (`python3.11`) and use it explicitly only for our project's virtualenv.

---

## 2. Install Python 3.11

Ubuntu 22.04's default Python is 3.10. R.A.N.G.E.R. V3 requires 3.11+ for better async performance with Channels/Daphne. We use the **deadsnakes PPA** — a well-maintained third-party repo that publishes newer Python versions for older Ubuntu releases.

```bash
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

**What each package is for:**
- `python3.11` — the interpreter
- `python3.11-venv` — the `venv` module (needed to create virtual environments)
- `python3.11-dev` — Python C headers (needed when pip installs packages with C extensions, e.g. `psycopg`)

**Verify:**

```bash
python3.11 --version
# Expected: Python 3.11.x (we got 3.11.15)
```

`python3` still points to 3.10. That's intentional — leave it that way.

---

## 3. Install system build dependencies

Packages needed to compile Python C extensions (Pillow, psycopg) and run general builds:

```bash
sudo apt update
sudo apt install -y \
  build-essential \
  libpq-dev \
  curl \
  ca-certificates \
  gnupg \
  lsb-release
```

**What each is for:**
- `build-essential` — gcc, make, etc. (needed by pip when compiling C extensions)
- `libpq-dev` — PostgreSQL C client library headers (needed by `psycopg`)
- `curl`, `ca-certificates`, `gnupg`, `lsb-release` — needed to add Docker's apt repo securely

**Verify:**

```bash
gcc --version       # Expected: gcc 11.4.0
pg_config --version # Expected: PostgreSQL 14.x
```

> **Note:** If you also installed `postgresql` and `postgresql-contrib` (which install a native Postgres server), see section 4 below to disable it. We're running Postgres in Docker, not natively.

---

## 4. Disable native PostgreSQL (we use Docker)

If you accidentally installed the `postgresql` package (which auto-starts a Postgres 14 server on port 5432), it will conflict with our Docker Postgres on the same port. Disable it.

See [ADR 0001](../decisions/0001-postgres-in-docker-not-native.md) for the full reasoning.

```bash
sudo systemctl stop postgresql
sudo systemctl disable postgresql
```

**Verify port 5432 is free:**

```bash
sudo ss -tlnp | grep 5432
# Expected: empty output (no process listening on 5432)
```

If the command prints a line, native Postgres is still running. Re-check the stop command output for errors.

---

## 5. Install Node.js 20

Ubuntu's apt repo only ships Node 12, which is ancient. We use **NodeSource** — the official Node.js team's apt repo.

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

**What this does:** the `setup_20.x` script adds NodeSource's signed apt repo to your system. Then `apt install nodejs` pulls Node 20 from it. `npm` ships bundled with Node, so no separate install needed.

**Verify:**

```bash
node --version  # Expected: v20.x.x (we got v20.20.2)
npm --version   # Expected: 10.x.x (we got 10.8.2)
```

---

## 6. Install Docker

We use Docker for **stateful services** — Postgres and Redis — but run Django and React natively for fast hot-reload during development. This is the standard pro setup. See [ADR 0001](../decisions/0001-postgres-in-docker-not-native.md) for why.

### 6.1. Add Docker's apt repo

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

### 6.2. Install Docker packages

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

**What each is:**
- `docker-ce` — the Docker daemon (Community Edition)
- `docker-ce-cli` — the `docker` command
- `containerd.io` — the underlying container runtime
- `docker-buildx-plugin` — multi-platform image builder (used by `docker build`)
- `docker-compose-plugin` — provides `docker compose` (note: NOT `docker-compose` with a hyphen — that's the legacy v1 command)

### 6.3. Add yourself to the docker group

By default, `docker` requires `sudo`. Adding your user to the `docker` group lets you run docker commands without it.

```bash
sudo usermod -aG docker $USER
newgrp docker
```

`newgrp docker` applies the group change to your **current shell session** without needing to log out and back in. New terminals will already have the group.

> **Security note:** Members of the `docker` group can effectively get root access on the host, since they can mount any host directory inside a container. Only add trusted users.

### 6.4. Verify

```bash
docker --version          # Expected: Docker version 29.x or later
docker compose version    # Expected: Docker Compose version v5.x or later
docker run --rm hello-world
```

The `hello-world` test pulls a tiny image from Docker Hub, runs it, and prints a "Hello from Docker!" message. If you see that message, Docker is fully working.

---

## 7. Set up GitHub SSH authentication

We use **SSH keys** rather than HTTPS+token. SSH is more secure (no token to leak), and once set up you never type a password to push.

### 7.1. Generate the key

```bash
ssh-keygen -t ed25519 -C "brian-ranger-v3-ubuntu"
```

Three prompts:

1. **File path** → press Enter (accepts default `~/.ssh/id_ed25519`)
2. **Passphrase** → press Enter (no passphrase) for a personal dev machine. Set one only if multiple people share the machine.
3. **Confirm passphrase** → repeat or Enter

> **Why ed25519?** Modern, fast, smaller keys than RSA, and considered cryptographically stronger. GitHub fully supports it.

### 7.2. Copy the public key

```bash
cat ~/.ssh/id_ed25519.pub
```

This prints **one line** starting with `ssh-ed25519 AAAA...`. Copy the whole line.

> **Critical:** copy `id_ed25519.pub` (public key, safe to share). NEVER share `id_ed25519` (private key — leaking it lets anyone push to your repos).

### 7.3. Add the public key to GitHub

1. github.com → profile picture → **Settings**
2. Left sidebar → **SSH and GPG keys**
3. Click **New SSH key**
4. **Title:** something descriptive (e.g. `Ubuntu Kipruto - RANGER V3`)
5. **Key type:** Authentication Key
6. **Key:** paste the line from step 7.2
7. Click **Add SSH key**

### 7.4. Test the connection

```bash
ssh -T git@github.com
```

First connection prompts you to verify GitHub's host fingerprint. The legitimate ed25519 fingerprint is:

```
SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU
```

If what you see matches, type `yes` and Enter.

**Expected success message:**

```
Hi Brian-Kipruto! You've successfully authenticated, but GitHub does not provide shell access.
```

The "does not provide shell access" line is **not an error** — it's GitHub confirming auth works.

---

## 8. Configure git identity

Set globally so every repo on this machine attributes commits to you correctly.

```bash
git config --global user.name "Brian Kipruto"
git config --global user.email "bryanrutto4@gmail.com"
git config --global init.defaultBranch main
```

> Use the **same email tied to your GitHub account** so commits are attributed to your GitHub profile (with the green dots on your contribution graph).

The `init.defaultBranch main` setting makes new repos start on `main` instead of the legacy `master`.

**Verify:**

```bash
git config --global user.name      # Expected: Brian Kipruto
git config --global user.email     # Expected: your email
```

---

## 9. Clone the repo and scaffold the project

### 9.1. Create an empty GitHub repo

On github.com:
1. **+** (top right) → **New repository**
2. Name: `ranger-platform-v3`
3. Description: "Robot-as-a-Service platform for autonomous environmental reconnaissance"
4. Visibility: **Private** (recommended for early-stage work)
5. **Leave everything else unchecked** — no README, no `.gitignore`, no license. We add those locally in step 9.4+.
6. Click **Create repository**

Copy the **SSH** clone URL (NOT HTTPS). It looks like:

```
git@github.com:Brian-Kipruto/ranger-platform-v3.git
```

### 9.2. Clone locally

```bash
mkdir -p ~/projects
cd ~/projects
git clone git@github.com:Brian-Kipruto/ranger-platform-v3.git
cd ranger-platform-v3
```

You'll see a warning: `warning: You appear to have cloned an empty repository.` That's expected — the repo *is* empty.

**Verify:**

```bash
pwd                # Expected: /home/brian/projects/ranger-platform-v3
git remote -v      # Expected: origin git@github.com:Brian-Kipruto/ranger-platform-v3.git
```

### 9.3. Create top-level directory structure

```bash
mkdir -p ranger_backend ranger_frontend nginx .github/workflows
```

These directories are empty for now. Git doesn't track empty directories — they'll get tracked once we put files in them.

### 9.4. Create `.gitignore`

The `.gitignore` lists files git should never track. We exclude secrets, build artifacts, IDE configs, and OS junk.

The full content is committed at the project root. Key patterns:

- `.env` is ignored, but `!.env.example` exempts the template file (the `!` negates ignore)
- `__pycache__/` and `*.py[cod]` cover Python bytecode
- `.venv/` keeps the virtualenv out of git (it gets recreated per machine)
- `node_modules/` is ignored because it's huge and reproducible from `package-lock.json`
- `media/` and `staticfiles/` are user uploads and collected static — never commit these
- `postgres_data/` and `redis_data/` are Docker volume mounts (database files, would corrupt if committed)

### 9.5. Create `.env.example`

This is a **template** that documents what environment variables exist, without containing real secrets. Anyone setting up a fresh checkout copies this to `.env` and fills in real values.

> **Heredoc tip:** when using `cat > file << 'EOF'`, putting single quotes around the delimiter (`'EOF'`) prevents the shell from expanding `$VARIABLE` references inside the content. Without quotes, the shell would substitute their values.

### 9.6. Create `README.md`

Top-level README at the project root. Describes the stack, links to docs, gives quick-start commands.

---

## 10. First commit and push

```bash
git add .gitignore .env.example README.md
git commit -m "chore: initial project skeleton, gitignore, env example, readme"
git branch -M main
git push -u origin main
```

**Flag explanations:**
- `-M main` renames the current branch to `main` (defensive — should already be `main` from step 8's global config)
- `-u origin main` sets upstream tracking, so future pushes can just be `git push` (no `origin main` needed)

**Expected push output:**

```
Enumerating objects: 5, done.
Counting objects: 100% (5/5), done.
...
To github.com:Brian-Kipruto/ranger-platform-v3.git
 * [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
```

**Verify on GitHub:** open `https://github.com/Brian-Kipruto/ranger-platform-v3`. You should see:
- The README rendered on the front page
- `.env.example` and `.gitignore` in the file list
- "1 commit" near the top

---

## End state

After completing all sections, the machine is ready to:

- Run Python 3.11 virtualenvs for the Django backend
- Run Node 20 / npm 10 for the React frontend
- Run Docker containers for Postgres + Redis
- Push to GitHub via SSH without password prompts

The repo `~/projects/ranger-platform-v3/` exists with one commit on `main`, mirrored to GitHub.

**Next:** `02-services.md` (TBD) — Postgres + Redis via docker-compose.

---

## Reference: what's installed

| Tool | Version | Path |
|------|---------|------|
| Ubuntu | 22.04.5 LTS | host OS |
| Python (system) | 3.10.12 | `/usr/bin/python3` |
| Python (project) | 3.11.15 | `/usr/bin/python3.11` |
| Node.js | 20.20.2 | `/usr/bin/node` |
| npm | 10.8.2 | `/usr/bin/npm` |
| Docker | 29.4.3 | `/usr/bin/docker` |
| Docker Compose | v5.1.3 | plugin |
| git | 2.34.1 | `/usr/bin/git` |
| gcc | 11.4.0 | `/usr/bin/gcc` |
| PostgreSQL client | 14.22 | `pg_config` (server disabled) |

---

## Things that went wrong (and how we fixed them)

### Issue: `postgresql` package was installed alongside Docker plan

**Symptom:** Native Postgres 14 was installed and auto-started, occupying port 5432, which would conflict with our Docker Postgres 16.

**Cause:** `postgresql` and `postgresql-contrib` were included in an early version of the system-package install list. They auto-start as a systemd service.

**Fix:** stopped and disabled the native service:

```bash
sudo systemctl stop postgresql
sudo systemctl disable postgresql
```

**Prevention:** when running Docker for stateful services, don't install the native equivalents. The build dependency (`libpq-dev`) is still needed (for `psycopg`) but the server (`postgresql`) is not.

See [ADR 0001](../decisions/0001-postgres-in-docker-not-native.md) for the full architecture decision.

---

*Document last updated: 2026-05-09*