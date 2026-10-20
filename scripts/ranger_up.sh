#!/usr/bin/env bash
# ─── RANGER V3 START: 14-launcher ───
# PC: the whole bench in one command (or one click, scripts/desktop/).
#   1. scripts/dev_up.sh with the same arguments (Orin clock, Postgres + Redis,
#      Orin stack with drive + video); stops here if that fails
#   2. a fresh PC tmux session "ranger-pc": runserver, ros_ingest, relay
#      (drive only), vite. Recreated every time, so Vite rereads .env and the
#      ingest and relay connect to the stack as it is now
#   3. waits for Django :8000 and Vite :5173, checks no window died, opens
#      Mission Control
#
# Usage: scripts/ranger_up.sh [dev_up.sh arguments] [--pause]
#        default: sim nairobi usb, drive + video
#   --pause  wait for Enter before exiting (the dock icon uses it so the
#            terminal stays readable)
# Logs:  tmux attach -t ranger-pc     Ctrl-b n / p switch windows, Ctrl-b d detach
# Stop:  scripts/ranger_down.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION=ranger-pc
VENV="$REPO/.venv/bin/activate"
MISSION_URL=http://localhost:5173/mission

PAUSE=0
ARGS=()
for a in "$@"; do
  if [ "$a" = --pause ]; then PAUSE=1; else ARGS+=("$a"); fi
done
CMDS=""
finish() {
  local rc=$?
  [ -n "$CMDS" ] && rm -f "$CMDS"
  if [ "$PAUSE" = 1 ]; then echo; read -rp "Enter to close " _ || true; fi
  exit "$rc"
}
trap finish EXIT

fail() { printf '   FAIL: %s\n' "$*" >&2; exit 1; }
ok()   { printf '   ok: %s\n' "$*"; }

command -v tmux >/dev/null || fail "tmux not installed: sudo apt install tmux"
command -v curl >/dev/null || fail "curl not installed: sudo apt install curl"
[ -f "$VENV" ] || fail "$VENV missing — the venv lives at the repo root"

CMDS=$(mktemp)
RANGER_CMDS_FILE="$CMDS" "$REPO/scripts/dev_up.sh" "${ARGS[@]}" || fail "dev_up.sh failed (above)"
# shellcheck disable=SC1090
source "$CMDS"   # INGEST, RELAY, DRIVE, VIDEO_URL, ROBOT_ID, built by dev_up.sh

printf '\n── PC services (tmux session %s)\n' "$SESSION"
tmux kill-session -t "$SESSION" 2>/dev/null && sleep 2 || true
# A hand-started runserver or vite would take the port and our window would die.
listening() { timeout 1 bash -c "</dev/tcp/127.0.0.1/$1" 2>/dev/null; }
for port in 8000 5173; do
  if listening "$port"; then
    fail "port $port already in use — a hand-started runserver / npm run dev? Stop it and rerun."
  fi
done

# A service that exits leaves <name>.exited here; tmux can't tell (the window's
# bash stays the foreground process either way).
STATE="/tmp/ranger-pc-$(id -un)"
win() {  # win <name> <dir> <command>: like stack_up.sh, a dead window keeps its log and a shell
  local cmd="cd $2 && source $VENV && $3; echo \$? > $STATE/$1.exited; echo; echo \"[$1 exited]\"; exec bash"
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux new-window -t "$SESSION" -n "$1" "bash -c '$cmd'"
  else
    tmux new-session -d -s "$SESSION" -n "$1" "bash -c '$cmd'"
  fi
}
rm -rf "$STATE" && mkdir -p "$STATE"
win runserver "$REPO/ranger_backend" "python manage.py runserver"
win ingest "$REPO/ranger_backend" "$INGEST"
[ "$DRIVE" = 1 ] && win relay "$REPO/ranger_backend" "$RELAY"
# The video URL follows the link (usb/wifi); variables already in the
# environment beat .env in Vite, so .env stays the default for a hand-run Vite.
win vite "$REPO/ranger_frontend" "VITE_VIDEO_SERVER_URL=$VIDEO_URL VITE_VIDEO_ROBOT_ID=$ROBOT_ID npm run dev"

answers() { [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$1")" != 000 ]; }
for name_url in "Django|http://127.0.0.1:8000/" "Vite|http://localhost:5173/"; do
  name=${name_url%%|*}; url=${name_url#*|}; up=0
  for _ in $(seq 60); do answers "$url" && { up=1; break; }; sleep 1; done
  [ "$up" = 1 ] || fail "$name not answering at $url after 60 s — tmux attach -t $SESSION"
  ok "$name up ($url)"
done
sleep 3   # ingest and relay fail fast when they can't connect; give them the chance
dead=$(cd "$STATE" && for f in *.exited; do [ -e "$f" ] && printf '%s ' "${f%.exited}"; done; true)
[ -z "$dead" ] || fail "window(s) exited: ${dead}— tmux attach -t $SESSION"
ok "windows running: $(tmux list-windows -t "$SESSION" -F '#{window_name}' | tr '\n' ' ')"

if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v xdg-open >/dev/null; then
  xdg-open "$MISSION_URL" >/dev/null 2>&1 &
  ok "opened $MISSION_URL"
else
  ok "open $MISSION_URL"
fi
printf '\n── Up. Logs: tmux attach -t %s · stop: scripts/ranger_down.sh\n' "$SESSION"
[ "$DRIVE" = 1 ] && echo "   Drive: wheels on blocks until 4d; TX on, SwA in NET to drive."
true
# ─── RANGER V3 END: 14-launcher ───
