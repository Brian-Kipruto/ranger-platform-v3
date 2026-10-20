#!/usr/bin/env bash
# ─── RANGER V3 START: dev-scripts ───
# Orin: start the robot stack in one tmux session, one window per process,
# in the order F08 requires, then check /fix is publishing.
#
#   sim : socat pty pair → gps_node on /tmp/gps_sim → rosbridge → radiation_node
#         → sensor_sim → nmea_sim (last)
#   live: gps_node on the FTDI by-id port → rosbridge → radiation_node → imu_node
#   radiation_node runs count_source:=sim in BOTH modes until a GM tube works (F13).
#   imu_node (real 10-DOF board) runs in live mode only; sim mode uses sensor_sim.
#   F14 (both modes, after the sensors): uno_bridge (drive), the Gemini 2 colour
#   camera, web_video_server bound to --video-bind. --no-drive / --no-video skip them.
#
# Deploy (from the PC, repo root):
#   scp robot/tools/stack_up.sh brian@192.168.55.1:~/ranger/
#   F13: also robot/{radiation_node,sensor_sim,sensor_sources,imu_node,imu_math}.py
#   → ~/ranger/, robot/config/imu_mount.json → ~/ranger/config/, and
#   robot/ranger_msgs → ~/ranger/ws/src/, built with colcon (see the F13 doc).
# Run (on the Orin):
#   ~/ranger/stack_up.sh [sim|live] [--fresh] [--site nairobi|rabat]
#                        [--no-drive] [--no-video] [--video-bind <ip>]
#     default: sim, nairobi, drive + video on, video bound to 192.168.55.1
#     --fresh  kill any running session and stray stack processes first
#     --site   where nmea_sim puts the fix (sim only; F11). Deploy nmea_sim.py with this.
#     --no-drive / --no-video   F14: skip uno_bridge / camera + web_video_server
#     --video-bind  F14: the one address web_video_server listens on (the link the
#                   console uses; never 0.0.0.0 — the feed is unauthenticated, ADR)
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
USAGE="usage: $0 [sim|live] [--fresh] [--site nairobi|rabat] [--no-drive] [--no-video] [--video-bind <ip>]"
# ─── RANGER V3 END: 11-ingest-region ───
# ─── RANGER V3 START: 14-stack ───
DRIVE=1
VIDEO=1
VIDEO_BIND=192.168.55.1
UNO_PORT=/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_3433031323135171F0F0-if00
MAX_PWM=120   # until the motor-noise capacitors are in (F14 5a)
ORBBEC_SETUP="$HOME/ros2_ws/install/setup.bash"
ORBBEC_LAUNCH="$HOME/ros2_ws/install/orbbec_camera/share/orbbec_camera/launch/gemini2.launch.py"
COLOR_TOPIC=/camera/color/image_raw
# ─── RANGER V3 END: 14-stack ───
SESSION=ranger
DIR="$HOME/ranger"
GPS_PORT_LIVE=/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_AZ6YQ8AI-if00-port0
ROS_SETUP=/opt/ros/humble/setup.bash
# ─── RANGER V3 START: 13-sensor-sim ───
# ranger_msgs overlay. rosbridge needs it too, or it can't serialise the reading types.
OVERLAY="$DIR/ws/install/setup.bash"
# ─── RANGER V3 END: 13-sensor-sim ───

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
    --no-drive) DRIVE=0 ;;                                          # 14-stack
    --no-video) VIDEO=0 ;;                                          # 14-stack
    --video-bind) VIDEO_BIND="${2:-}"; [ $# -gt 1 ] && shift ;;    # 14-stack
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
# ─── RANGER V3 START: 14-stack ───
# The marker names the parts too, so dev_up.sh restarts a session that lacks one,
# and the video bind address, so switching usb <-> wifi rebinds the feed (4d).
[ "$DRIVE" = 1 ] && MARK="$MARK+drive"
[ "$VIDEO" = 1 ] && MARK="$MARK+video@$VIDEO_BIND"
if [ "$VIDEO" = 1 ]; then
  [[ "$VIDEO_BIND" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || fail "--video-bind needs an IPv4 address, got '$VIDEO_BIND'"
  [ "$VIDEO_BIND" != 0.0.0.0 ] || fail "--video-bind 0.0.0.0 would expose the unauthenticated feed on every interface"
fi
# ─── RANGER V3 END: 14-stack ───
# ─── RANGER V3 END: 11-ingest-region ───
command -v tmux >/dev/null || fail "tmux not installed: sudo apt install tmux"
[ -f "$DIR/gps_node.py" ] || fail "$DIR/gps_node.py missing — scp robot/gps_node.py from the PC"
# ─── RANGER V3 START: 13-sensor-sim ───
[ -f "$OVERLAY" ] || fail "$OVERLAY missing — build ranger_msgs: cd ~/ranger/ws && colcon build --packages-select ranger_msgs"
for f in radiation_node.py sensor_sources.py; do
  [ -f "$DIR/$f" ] || fail "$DIR/$f missing — scp robot/$f from the PC"
done
if [ "$MODE" = sim ]; then
  [ -f "$DIR/sensor_sim.py" ] || fail "$DIR/sensor_sim.py missing — scp robot/sensor_sim.py from the PC"
else
  for f in imu_node.py imu_math.py; do
    [ -f "$DIR/$f" ] || fail "$DIR/$f missing — scp robot/$f from the PC"
  done
  [ -f "$DIR/config/imu_mount.json" ] \
    || fail "$DIR/config/imu_mount.json missing — scp robot/config/imu_mount.json to ~/ranger/config/"
fi
# ─── RANGER V3 END: 13-sensor-sim ───
# ─── RANGER V3 START: 14-stack ───
# rosbridge has no auth and the feed none by design: never start them unless the
# firewall limits both ports to the console PC (F14 4d).
systemctl is-active --quiet ranger-firewall \
  || fail "ranger-firewall is not active — rosbridge and video would be open to the whole network. Install robot/config/ranger-firewall.{sh,service} (F14 4d)"
if [ "$DRIVE" = 1 ]; then
  for f in uno_bridge.py uno_protocol.py; do
    [ -f "$DIR/$f" ] || fail "$DIR/$f missing — scp robot/$f from the PC"
  done
  [ -e "$UNO_PORT" ] || fail "no Uno at $UNO_PORT — USB cable in? (or --no-drive)"
fi
if [ "$VIDEO" = 1 ]; then
  [ -f "$ORBBEC_SETUP" ] || fail "$ORBBEC_SETUP missing — OrbbecSDK_ROS2 not built in ~/ros2_ws (F14 install record)"
  [ -d /opt/ros/humble/share/web_video_server ] || fail "web_video_server not installed: sudo apt install ros-humble-web-video-server"
  # The upstream launch file shipped with a missing comma (F14 install record);
  # a re-pull without the patch fails here, not mid-start.
  python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$ORBBEC_LAUNCH" 2>/dev/null \
    || fail "$ORBBEC_LAUNCH doesn't parse — reapply the line-47 comma patch (F14 install record)"
  # grep without -q: under pipefail, -q exits early and lsusb's SIGPIPE fails the pipe
  lsusb | grep ' 2bc5:' >/dev/null || fail "no Orbbec camera on USB (2bc5) — plugged in? (or --no-video)"
fi
# ─── RANGER V3 END: 14-stack ───
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
  pkill -f '[r]adiation_node.py' 2>/dev/null || true   # 13-sensor-sim
  pkill -f '[s]ensor_sim.py' 2>/dev/null || true       # 13-sensor-sim
  pkill -f '[i]mu_node.py' 2>/dev/null || true         # 13-imu
  pkill -f '[u]no_bridge.py' 2>/dev/null || true       # 14-stack (it sends M,0,0 on exit)
  pkill -f '[w]eb_video_server' 2>/dev/null || true    # 14-stack
  pkill -f '[o]rbbec_camera gemini2' 2>/dev/null || true   # 14-stack: ros2 launch
  pkill -f '[c]amera_container' 2>/dev/null || true    # 14-stack: the driver process
  pkill -x socat 2>/dev/null || true
  rm -f /tmp/gps_sim /tmp/gps_feed
  sleep 2
fi
if tmux has-session -t "$SESSION" 2>/dev/null; then
  fail "session '$SESSION' already running. Attach: tmux attach -t $SESSION · stop: tmux kill-session -t $SESSION"
fi
# ─── RANGER V3 START: 14-stack ───
# A hand-started copy would hold the Uno port or :8080 and the window would die.
for p in '[u]no_bridge.py' '[w]eb_video_server' '[c]amera_container'; do
  if pgrep -f "$p" >/dev/null; then
    fail "${p//[\[\]]/} already running outside the stack — stop it, or rerun with --fresh"
  fi
done
# ─── RANGER V3 END: 14-stack ───

# Each window keeps a shell after its process exits, so a crash stays readable.
win() {  # win <name> <command>
  tmux new-window -t "$SESSION" -n "$1" "bash -c 'source $ROS_SETUP; source $OVERLAY; $2; echo; echo \"[$1 exited]\"; exec bash'"
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

# ─── RANGER V3 START: 13-sensor-sim ───
win radiation "cd $DIR && python3 radiation_node.py --ros-args -p count_source:=sim"
if [ "$MODE" = sim ]; then
  win sensor_sim "cd $DIR && python3 sensor_sim.py --ros-args -p site:=$SITE"
else
  win imu "cd $DIR && python3 imu_node.py"   # 13-imu: real 10-DOF board
fi
# ─── RANGER V3 END: 13-sensor-sim ───

if [ "$MODE" = sim ]; then
  win nmea_sim "python3 $DIR/nmea_sim.py /tmp/gps_feed --site $SITE"   # LAST (F11: --site)
fi

# ─── RANGER V3 START: 14-stack ───
# After the GPS chain (its order is F08's), started now so the camera's ~15 s
# boot overlaps the checks below. uno_bridge can't move the robot by starting:
# it drives only on fresh cmd_vel, and only with SwA in NET.
if [ "$DRIVE" = 1 ]; then
  win drive "cd $DIR && python3 uno_bridge.py --ros-args -p port:=$UNO_PORT -p max_pwm:=$MAX_PWM"
fi
if [ "$VIDEO" = 1 ]; then
  win camera "source $ORBBEC_SETUP; ros2 launch orbbec_camera gemini2.launch.py camera_name:=camera enable_color:=true color_width:=640 color_height:=480 color_fps:=30 color_format:=MJPG enable_depth:=false enable_ir:=false enable_point_cloud:=false enable_colored_point_cloud:=false enable_accel:=false enable_gyro:=false"
  win video "ros2 run web_video_server web_video_server --ros-args -p address:=$VIDEO_BIND -p port:=8080"
fi
# ─── RANGER V3 END: 14-stack ───

# /fix check. Live publishes no-fix messages too, so this proves the pipe, not a fix.
# The type is given explicitly: without it, `ros2 topic echo` exits at once
# if discovery hasn't resolved /fix's type yet, instead of waiting.
set +u
# shellcheck disable=SC1090
source "$ROS_SETUP"
# shellcheck disable=SC1090
source "$OVERLAY"   # 13-sensor-sim: echo needs the ranger_msgs types
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
# ─── RANGER V3 START: 13-sensor-sim ───
# Every reading topic this mode should carry must publish, or the stack fails
# the way a silent /fix does: session kept for diagnosis, marker says failed.
READINGS="/ranger/radiation:Radiation"
if [ "$MODE" = sim ]; then
  READINGS="$READINGS /ranger/air_quality:AirQuality /ranger/imu_baro:ImuBaro"
else
  READINGS="$READINGS /ranger/imu_baro:ImuBaro"   # 13-imu; air_quality when the SDS011 lands
fi
for r in $READINGS; do
  topic="${r%%:*}"; ok=0
  for _ in $(seq 3); do
    if timeout 5 ros2 topic echo --once "$topic" "ranger_msgs/msg/${r#*:}" >/dev/null 2>&1; then
      ok=1; break
    fi
  done
  if [ "$ok" = 0 ]; then
    tmux set-environment -t "$SESSION" RANGER_MODE failed
    STARTED=0
    fail "no $topic within 15 s — session left up: tmux attach -t $SESSION (radiation, sensor_sim/imu windows)"
  fi
done
echo "ok: readings publishing · $READINGS"
# ─── RANGER V3 END: 13-sensor-sim ───
# ─── RANGER V3 START: 14-stack ───
part_failed() {  # part_failed <message>
  tmux set-environment -t "$SESSION" RANGER_MODE failed
  STARTED=0
  fail "$1"
}
if [ "$DRIVE" = 1 ]; then
  # The Uno's S lines on /ranger/uno_status prove port + firmware + bridge, not just the node.
  ok=0
  for _ in $(seq 3); do
    if timeout 5 ros2 topic echo --once /ranger/uno_status std_msgs/msg/String >/dev/null 2>&1; then
      ok=1; break
    fi
  done
  [ "$ok" = 1 ] || part_failed "no /ranger/uno_status within 15 s — session left up: tmux attach -t $SESSION (drive window)"
  echo "ok: drive · uno_bridge talking to the Uno · max_pwm=$MAX_PWM"
fi
if [ "$VIDEO" = 1 ]; then
  # A completed /snapshot proves real frames end to end: the driver advertises
  # the topic but publishes nothing until something subscribes. Wait for the
  # publisher (camera boot is ~15 s) before probing, and keep probes few and
  # long: every abandoned /snapshot stays queued on web_video_server (F14 5b).
  ok=0
  for _ in $(seq 40); do
    ros2 topic info "$COLOR_TOPIC" 2>/dev/null | grep 'Publisher count: [1-9]' >/dev/null && { ok=1; break; }
    sleep 1
  done
  [ "$ok" = 1 ] || part_failed "no publisher on $COLOR_TOPIC within 40 s — session left up: tmux attach -t $SESSION (camera window)"
  ok=0
  for _ in $(seq 2); do
    if python3 -c "import urllib.request,sys; urllib.request.urlopen(sys.argv[1], timeout=10).read()" \
        "http://$VIDEO_BIND:8080/snapshot?topic=$COLOR_TOPIC&quality=50" >/dev/null 2>&1; then
      ok=1; break
    fi
  done
  [ "$ok" = 1 ] || part_failed "no camera frame from http://$VIDEO_BIND:8080 within 20 s — session left up: tmux attach -t $SESSION (camera, video windows)"
  echo "ok: video · frames at http://$VIDEO_BIND:8080 (bound to $VIDEO_BIND only)"
fi
echo "ok: stack up · mode=$MARK"
# ─── RANGER V3 END: 14-stack ───
# ─── RANGER V3 END: dev-scripts ───
