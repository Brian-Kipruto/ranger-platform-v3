#!/usr/bin/env bash
# ─── RANGER V3 START: 14-launcher ───
# PC: stop the bench. Ctrl-C to every process first (uno_bridge sends M,0,0 and
# the relay a zero on a clean exit), then the sessions go.
#   PC tmux session ranger-pc (scripts/ranger_up.sh)
#   Orin tmux session ranger (stack_up.sh) — skipped with --pc-only
# Usage: scripts/ranger_down.sh [--pc-only] [--pause]
#   ORIN_HOST overrides the Orin address; otherwise the tether, then the Wi-Fi
#   address, whichever answers (4d: the tether may be unplugged).
set -uo pipefail

ORIN=""
PC_ONLY=0
PAUSE=0
for a in "$@"; do
  case "$a" in
    --pc-only) PC_ONLY=1 ;;
    --pause) PAUSE=1 ;;
    *) echo "usage: $0 [--pc-only] [--pause]" >&2; exit 2 ;;
  esac
done

# interrupt <ssh-prefix...>: Ctrl-C every pane of the session, wait, kill it
stop_session() {  # stop_session <label> <session> [ssh target]
  local label=$1 session=$2 target=${3:-}
  local run=(bash -c)
  [ -n "$target" ] && run=(ssh -o BatchMode=yes -o ConnectTimeout=5 "$target")
  if ! "${run[@]}" "tmux has-session -t $session 2>/dev/null"; then
    echo "   ok: $label: not running"
    return 0
  fi
  "${run[@]}" "for p in \$(tmux list-panes -s -t $session -F '#{pane_id}'); do tmux send-keys -t \$p C-c; done"
  sleep 3
  "${run[@]}" "tmux kill-session -t $session 2>/dev/null" || true
  echo "   ok: $label: stopped"
}

stop_session "PC services (ranger-pc)" ranger-pc
if [ "$PC_ONLY" = 0 ]; then
  for h in ${ORIN_HOST:-192.168.55.1 192.168.0.50}; do
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "brian@$h" true 2>/dev/null; then ORIN="brian@$h"; break; fi
  done
  if [ -n "$ORIN" ]; then
    stop_session "Orin stack (ranger)" ranger "$ORIN"
  else
    echo "   WARN: Orin unreachable on ${ORIN_HOST:-192.168.55.1 or 192.168.0.50} — its stack (if any) is still running" >&2
  fi
fi
echo "   Docker (Postgres + Redis) left running."
if [ "$PAUSE" = 1 ]; then echo; read -rp "Enter to close " _ || true; fi
# ─── RANGER V3 END: 14-launcher ───
