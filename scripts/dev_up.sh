#!/usr/bin/env bash
# ─── RANGER V3 START: dev-scripts ───
# PC: bring up everything the live console needs, then print the three
# commands you run and watch yourself (runserver, ros_ingest, npm run dev).
#
# Order matters (F09 retrospective: setup cost more than code):
#   1. Orin reachable, key-based ssh       (no password prompt → exact clock)
#   2. Orin internet, only if it's missing (jetson-internet.sh isn't run twice)
#   3. Orin clock within 0.5 s of the PC   (TS-025, TS-029; ADR-0015 skew guard)
#   4. Postgres + Redis healthy            (docker compose --wait)
#   5. Orin stack running in the requested mode, started over ssh in tmux
#      (survives this script exiting); restarted fresh if the clock jumped
#      or the mode differs. rosbridge :9090 checked from the PC.
#
# Usage: scripts/dev_up.sh [sim|live]   default: sim  (from anywhere)
# Orin windows: ssh -t brian@192.168.55.1 tmux attach -t ranger
set -euo pipefail

MODE="${1:-sim}"
case "$MODE" in sim|live) ;; *) echo "usage: $0 [sim|live]" >&2; exit 2 ;; esac
ORIN_HOST="${ORIN_HOST:-192.168.55.1}"
ORIN="brian@${ORIN_HOST}"
MAX_OFFSET_S=0.5
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

step() { printf '\n── %s\n' "$*"; }
ok()   { printf '   ok: %s\n' "$*"; }
warn() { printf '   WARN: %s\n' "$*" >&2; }
fail() { printf '   FAIL: %s\n' "$*" >&2; exit 1; }

# Orin − PC in seconds, bracketed by two PC reads (TS-029).
measure_offset() {
  local t0 r t1
  t0=$(date +%s.%N)
  r=$(ssh -o BatchMode=yes "$ORIN" date +%s.%N)
  t1=$(date +%s.%N)
  python3 -c "print(f'{$r - ($t0 + $t1) / 2:+.2f}')"
}

within() {  # within <offset> <limit>
  python3 -c "import sys; sys.exit(0 if abs(float('$1')) <= float('$2') else 1)"
}

step "1/5 Orin reachable"
ping -c 1 -W 2 "$ORIN_HOST" >/dev/null \
  || fail "no reply from $ORIN_HOST — USB tether down? Replug, wait ~20 s."
ssh -o BatchMode=yes -o ConnectTimeout=5 "$ORIN" true 2>/dev/null \
  || fail "key-based ssh not set up. Run once: ssh-copy-id $ORIN"
ok "ping + key-based ssh"

step "2/5 Orin internet"
# Route and name are separate faults (TS-025): the NAT script fixes routing
# only, so only a routing failure triggers it — never re-run it for DNS.
orin_ping() { ssh -o BatchMode=yes "$ORIN" "ping -c 1 -W 3 $1" >/dev/null 2>&1; }
if orin_ping 1.1.1.1; then
  ok "NAT up (1.1.1.1 reachable)"
else
  echo "   Orin can't reach 1.1.1.1; running ~/jetson-internet.sh (sudo)"
  bash ~/jetson-internet.sh
  if orin_ping 1.1.1.1; then
    ok "NAT up"
  else
    warn "still no route to 1.1.1.1. Not needed for the stack; continuing."
  fi
fi
if orin_ping google.com; then
  ok "DNS resolves"
else
  warn "routing works but DNS doesn't (TS-025: /etc/resolv.conf). NTP can't sync; step 3 covers the clock."
fi

step "3/5 Orin clock"
clock_jumped=0
offset=$(measure_offset)
if within "$offset" "$MAX_OFFSET_S"; then
  ok "orin − pc = ${offset} s"
else
  echo "   orin − pc = ${offset} s — setting it from the PC (TS-029; Orin sudo password)"
  # PC timestamp taken now; the sudo wait is timed on the Orin's monotonic clock.
  ssh -t "$ORIN" "u0=\$(cut -d' ' -f1 /proc/uptime); sudo -v; u1=\$(cut -d' ' -f1 /proc/uptime); sudo date -s @\$(python3 -c \"print($(date +%s.%N)+\$u1-\$u0)\") >/dev/null"
  offset=$(measure_offset)
  within "$offset" "$MAX_OFFSET_S" \
    || fail "still orin − pc = ${offset} s after setting it"
  ok "orin − pc = ${offset} s"
  clock_jumped=1
fi

step "4/5 Postgres + Redis"
(cd "$REPO" && docker compose up -d --wait) >/dev/null \
  || fail "docker compose did not reach healthy — docker compose ps / logs"
[ "$(docker exec ranger_redis redis-cli ping)" = "PONG" ] || fail "redis did not answer PONG"
ok "ranger_postgres + ranger_redis healthy"

step "5/5 Orin stack (${MODE})"
# Empty = no session; "unknown" = a session not started by stack_up.sh (no marker).
running_mode=$(ssh -o BatchMode=yes "$ORIN" \
  "tmux has-session -t ranger 2>/dev/null && { tmux show-environment -t ranger RANGER_MODE 2>/dev/null | cut -d= -f2 | grep . || echo unknown; }" || true)
if [ "$running_mode" = "$MODE" ] && [ "$clock_jumped" = 0 ]; then
  ok "already running (${MODE}) — leaving it"
else
  if [ "$clock_jumped" = 1 ]; then why="clock was stepped"
  elif [ "$running_mode" = unknown ]; then why="a session exists with no mode marker"
  elif [ "$running_mode" = failed ]; then why="last start failed"
  elif [ -n "$running_mode" ]; then why="running ${running_mode}, want ${MODE}"
  else why="not running"; fi
  echo "   starting fresh (${why})"
  ssh -o BatchMode=yes "$ORIN" "\$HOME/ranger/stack_up.sh ${MODE} --fresh" \
    || fail "stack_up.sh failed — ssh -t $ORIN tmux attach -t ranger"
fi
timeout 3 bash -c "</dev/tcp/${ORIN_HOST}/9090" 2>/dev/null \
  || fail "${ORIN_HOST}:9090 not reachable from the PC"
ok "rosbridge ${ORIN_HOST}:9090 reachable"

cat <<NEXT

── Ready. Three terminals, venv active (source ${REPO}/.venv/bin/activate):
   T1  cd ${REPO}/ranger_backend && python manage.py runserver      # banner: Daphne
   T2  cd ${REPO}/ranger_backend && python manage.py ros_ingest     # add --source live ONLY for the real GPS
   T3  cd ${REPO}/ranger_frontend && npm run dev                    # http://localhost:5173
NEXT
# ─── RANGER V3 END: dev-scripts ───
