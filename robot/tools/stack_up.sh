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
#   ~/ranger/stack_up.sh [sim|live] [--fresh] [--site nairobi|rabat]   default: sim, nairobi
#     --fresh  kill any running session and stray stack processes first
#     --site   where nmea_sim puts the fix (sim only; F11). Deploy nmea_sim.py with this.
#   Normally started for you by scripts/dev_up.sh on the PC, over ssh.
#   tmux attach -t ranger                 Ctrl-b n / p to switch windows, Ctrl-b d to detach
#   tmux kill-session -t ranger           stop everything
#
# Clock first: the Orin must be NTP-synced to the PC; this script checks and,
# if needed, forces one resync before starting anything (F12).
set -euo pipefail

MODE="${1:-sim}"
# ─── RANGER V3 START: 11-ingest-region ───
[ $# -gt 0 ] && shift
FRESH=""
SITE=nairobi
SITE_GIVEN=0
USAGE="usage: $0 [sim|live] [--fresh] [--site nairobi|rabat]"
# ─── RANGER V3 END: 11-ingest-region ───
SESSION=ranger
DIR="$HOME/ranger"
GPS_PORT_LIVE=/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_AZ6YQ8AI-if00-port0
ROS_SETUP=/opt/ros/humble/setup.bash

STARTED=0
# A failure after the session exists must not leave a half-built session
# behind: scripts/dev_up.sh would read its RANGER_MODE as "already running".
fail() {
  printf 'FAIL: %s\n' "$*" >&2
  [ "$STARTED" = 1 ] && tmux kill-session -t "$SESSION" 2>/dev/null
  exit 1
}

case "$MODE" in
  sim|live) ;;
  *) fail "$USAGE" ;;
esac
# ─── RANGER V3 START: 11-ingest-region ───
while [ $# -gt 0 ]; do
  case "$1" in
    --fresh) FRESH=--fresh ;;
    --site)  SITE="${2:-}"; SITE_GIVEN=1; [ $# -gt 1 ] && shift ;;
    *) fail "$USAGE" ;;
  esac
  shift
done
case "$SITE" in
  nairobi|rabat) ;;
  *) fail "$USAGE" ;;
esac
[ "$MODE" = live ] && [ "$SITE_GIVEN" = 1 ] && fail "--site is sim-only: live takes its position from the receiver"
# Marker read by scripts/dev_up.sh: a sim at another site must restart, not be kept.
if [ "$MODE" = sim ]; then MARK="sim:$SITE"; else MARK=live; fi
# ─── RANGER V3 END: 11-ingest-region ───
command -v tmux >/dev/null || fail "tmux not installed: sudo apt install tmux"
[ -f "$DIR/gps_node.py" ] || fail "$DIR/gps_node.py missing — scp robot/gps_node.py from the PC"
# Preflight everything before touching the running stack.
if [ "$MODE" = sim ]; then
  [ -f "$DIR/nmea_sim.py" ] || fail "$DIR/nmea_sim.py missing — scp robot/tools/nmea_sim.py from the PC"
  # ─── RANGER V3 START: 11-ingest-region ───
  # A pre-F11 copy has no --site and would die in its window, failing the /fix check late.
  # Static check, never `--help`: the old copy treats argv[1] as a path and writes forever.
  grep -q -- "'--site'" "$DIR/nmea_sim.py" \
    || fail "$DIR/nmea_sim.py is a stale copy (no --site) — scp robot/tools/nmea_sim.py from the PC"
  # ─── RANGER V3 END: 11-ingest-region ───
else
  [ -e "$GPS_PORT_LIVE" ] || fail "no GPS at $GPS_PORT_LIVE — FTDI cable plugged in?"
fi
# ─── RANGER V3 START: 12-field-time ───
# The clock before anything: rows stamped from a wrong clock are skipped as
# clock_skew (ADR-0015), and a clock step under running nodes stalls discovery.
# The Orin takes time only from the PC (robot/config/timesyncd-ranger.conf).
# After failed attempts timesyncd backs off for minutes (TS-033), so if it
# isn't synced, force a fresh attempt now instead of waiting it out.
TIME_WAIT_S="${RANGER_TIME_WAIT_S:-60}"
synced() { [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" = yes ]; }
if ! synced; then
  sudo -n /usr/bin/systemctl restart systemd-timesyncd 2>/dev/null \
    || fail "clock not synced, and timesyncd can't be restarted without a password — install robot/config/sudoers-ranger-timesync (F12)"
  for _ in $(seq "$TIME_WAIT_S"); do synced && break; sleep 1; done
  synced || fail "clock not synced to the PC after ${TIME_WAIT_S} s — is chrony running on the PC? (systemctl is-active chrony)"
  echo "ok: clock resynced from $(timedatectl show-timesync -p ServerAddress --value 2>/dev/null)"
fi
# ─── RANGER V3 END: 12-field-time ───
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
tmux set-environment -t "$SESSION" RANGER_MODE "$MARK"   # read by scripts/dev_up.sh (F11: sim:<site>)

if [ "$MODE" = sim ]; then
  win socat "socat -d -d pty,raw,echo=0,link=/tmp/gps_sim pty,raw,echo=0,link=/tmp/gps_feed"
  for _ in $(seq 20); do [ -e /tmp/gps_sim ] && break; sleep 0.25; done
  [ -e /tmp/gps_sim ] || fail "socat did not create /tmp/gps_sim — tmux attach -t $SESSION"
  win gps "python3 $DIR/gps_node.py --ros-args -p port:=/tmp/gps_sim"
else
  win gps "python3 $DIR/gps_node.py --ros-args -p port:=$GPS_PORT_LIVE"
fi

win rosbridge "ros2 launch rosbridge_server rosbridge_websocket_launch.xml"
port_open() { timeout 1 bash -c '</dev/tcp/127.0.0.1/9090' 2>/dev/null; }
for _ in $(seq 40); do port_open && break; sleep 0.5; done
port_open || fail "rosbridge not listening on :9090 after 20 s — tmux attach -t $SESSION"

if [ "$MODE" = sim ]; then
  win nmea_sim "python3 $DIR/nmea_sim.py /tmp/gps_feed --site $SITE"   # LAST (F11: --site)
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
  echo "ok: /fix publishing · mode=$MARK · rosbridge :9090 · tmux attach -t $SESSION"
else
  # Keep the windows for diagnosis; the marker makes dev_up.sh restart it fresh.
  tmux set-environment -t "$SESSION" RANGER_MODE failed
  STARTED=0
  fail "no /fix within 30 s — session left up for diagnosis: tmux attach -t $SESSION (gps, nmea_sim windows)"
fi
# ─── RANGER V3 END: dev-scripts ───
