#!/usr/bin/env bash
# ─── RANGER V3 START: dev-scripts ───
# Orin: start the robot stack in one tmux session, one window per process,
# in the order F08 requires, then check /fix is publishing.
#
#   sim : socat pty pair → gps_node on /tmp/gps_sim → rosbridge → nmea_sim (last)
#   live: gps_node on the FTDI by-id port → rosbridge
#
# Deploy (from the PC, repo root):
#   scp robot/tools/stack_up.sh brian@192.168.55.1:~/ranger/
# Run (on the Orin):
#   ~/ranger/stack_up.sh [sim|live] [--fresh]   default: sim
#     --fresh  kill any running session and stray stack processes first
#   Normally started for you by scripts/dev_up.sh on the PC, over ssh.
#   tmux attach -t ranger                 Ctrl-b n / p to switch windows, Ctrl-b d to detach
#   tmux kill-session -t ranger           stop everything
#
# Clock first: run scripts/dev_up.sh on the PC before this (TS-029).
set -euo pipefail

MODE="${1:-sim}"
FRESH="${2:-}"
SESSION=ranger
DIR="$HOME/ranger"
GPS_PORT_LIVE=/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_AZ6YQ8AI-if00-port0
ROS_SETUP=/opt/ros/humble/setup.bash

STARTED=0
# Print a window's last lines, so a failure reported over ssh carries its own evidence.
dump() {  # dump <window>...
  for w in "$@"; do
    printf -- '--- last lines of window "%s" ---\n' "$w" >&2
    tmux capture-pane -p -t "$SESSION:$w" -S -25 2>/dev/null | sed '/^$/d' >&2 || true
  done
}
# Keep a session that started but is unhealthy: windows stay for diagnosis,
# and the marker makes scripts/dev_up.sh restart it fresh next time.
fail_kept() {  # fail_kept <message> <window>...
  local msg=$1; shift
  dump "$@"
  tmux set-environment -t "$SESSION" RANGER_MODE failed
  STARTED=0
  fail "$msg — session left up: tmux attach -t $SESSION"
}
# A failure after the session exists must not leave a half-built session
# behind: scripts/dev_up.sh would read its RANGER_MODE as "already running".
fail() {
  printf 'FAIL: %s\n' "$*" >&2
  [ "$STARTED" = 1 ] && tmux kill-session -t "$SESSION" 2>/dev/null
  exit 1
}

case "$MODE" in
  sim|live) ;;
  *) fail "usage: $0 [sim|live] [--fresh]" ;;
esac
case "$FRESH" in
  ""|--fresh) ;;
  *) fail "usage: $0 [sim|live] [--fresh]" ;;
esac
command -v tmux >/dev/null || fail "tmux not installed: sudo apt install tmux"
[ -f "$DIR/gps_node.py" ] || fail "$DIR/gps_node.py missing — scp robot/gps_node.py from the PC"
# Preflight everything before touching the running stack.
if [ "$MODE" = sim ]; then
  [ -f "$DIR/nmea_sim.py" ] || fail "$DIR/nmea_sim.py missing — scp robot/tools/nmea_sim.py from the PC"
else
  [ -e "$GPS_PORT_LIVE" ] || fail "no GPS at $GPS_PORT_LIVE — FTDI cable plugged in?"
fi
if [ "$FRESH" = --fresh ]; then
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  # [x] pattern so pkill never matches a shell whose argv contains the name
  pkill -f '[g]ps_node.py' 2>/dev/null || true
  pkill -f '[n]mea_sim.py' 2>/dev/null || true
  pkill -f '[r]osbridge_websocket' 2>/dev/null || true
  pkill -x socat 2>/dev/null || true
  rm -f /tmp/gps_sim /tmp/gps_feed
  sleep 2
fi
if tmux has-session -t "$SESSION" 2>/dev/null; then
  fail "session '$SESSION' already running. Attach: tmux attach -t $SESSION · stop: tmux kill-session -t $SESSION"
fi

# Each window keeps a shell after its process exits, so a crash stays readable.
win() {  # win <name> <command>
  tmux new-window -t "$SESSION" -n "$1" "bash -c 'source $ROS_SETUP; $2; echo; echo \"[$1 exited]\"; exec bash'"
}

tmux new-session -d -s "$SESSION" -n shell
STARTED=1
tmux set-environment -t "$SESSION" RANGER_MODE "$MODE"   # read by scripts/dev_up.sh

if [ "$MODE" = sim ]; then
  win socat "socat -d -d pty,raw,echo=0,link=/tmp/gps_sim pty,raw,echo=0,link=/tmp/gps_feed"
  for _ in $(seq 20); do [ -e /tmp/gps_sim ] && break; sleep 0.25; done
  [ -e /tmp/gps_sim ] || fail_kept "socat did not create /tmp/gps_sim" socat
  win gps "python3 $DIR/gps_node.py --ros-args -p port:=/tmp/gps_sim"
else
  win gps "python3 $DIR/gps_node.py --ros-args -p port:=$GPS_PORT_LIVE"
fi

win rosbridge "ros2 launch rosbridge_server rosbridge_websocket_launch.xml"
port_open() { timeout 1 bash -c '</dev/tcp/127.0.0.1/9090' 2>/dev/null; }
for _ in $(seq 120); do port_open && break; sleep 0.5; done
port_open || fail_kept "rosbridge not listening on :9090 after 60 s" rosbridge

if [ "$MODE" = sim ]; then
  win nmea_sim "python3 $DIR/nmea_sim.py /tmp/gps_feed"   # LAST
fi

# /fix check. Live publishes no-fix messages too, so this proves the pipe, not a fix.
# The type is given explicitly: without it, `ros2 topic echo` exits at once
# if discovery hasn't resolved /fix's type yet, instead of waiting.
set +u
# shellcheck disable=SC1090
source "$ROS_SETUP"
set -u
ros2 daemon stop >/dev/null 2>&1 || true   # stale discovery cache after a clock step
got_fix=0
for _ in $(seq 6); do
  if timeout 5 ros2 topic echo --once /fix sensor_msgs/msg/NavSatFix >/dev/null 2>&1; then
    got_fix=1; break
  fi
done
if [ "$got_fix" = 1 ]; then
  echo "ok: /fix publishing · mode=$MODE · rosbridge :9090 · tmux attach -t $SESSION"
else
  if [ "$MODE" = sim ]; then
    fail_kept "no /fix within 30 s" gps nmea_sim
  else
    fail_kept "no /fix within 30 s" gps
  fi
fi
# ─── RANGER V3 END: dev-scripts ───
