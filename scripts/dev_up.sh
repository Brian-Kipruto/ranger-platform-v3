#!/usr/bin/env bash
# ─── RANGER V3 START: dev-scripts ───
# PC: bring up everything the live console needs, then print the three
# commands you run and watch yourself (runserver, ros_ingest, npm run dev).
#
# Order matters (F09 retrospective: setup cost more than code):
#   1. Orin reachable, key-based ssh       (no password prompt → exact clock)
#   2. Orin internet, only if it's missing (jetson-internet.sh isn't run twice;
#      usb only — over wifi the stack doesn't need the Orin online)
#   3. Orin clock synced to chrony on this PC, within 0.5 s (F12; ADR-0015
#      skew guard). Checked, not set: --set-clock is the opt-in fallback.
#   4. Postgres + Redis healthy            (docker compose --wait)
#   5. Orin stack running in the requested mode, started over ssh in tmux
#      (survives this script exiting); restarted fresh if the clock jumped
#      or the mode differs. rosbridge :9090 checked from the PC.
#
# Usage: scripts/dev_up.sh [sim|live] [nairobi|rabat] [usb|wifi] [--set-clock]
#        default: sim nairobi usb  (from anywhere)
#   site: in sim, where nmea_sim puts the fix; in both modes, the --region the
#   printed ros_ingest command uses (nairobi -> kenya, the default). F11.
#   link: usb = tether at 192.168.55.1; wifi = the Orin's reservation on our
#   travel router (ORIN_WIFI_HOST below). ORIN_HOST in the environment wins. F12.
#   --set-clock: set the Orin's clock from the PC with sudo (TS-029) instead of
#   requiring NTP sync. Fallback only; it hides a broken time server.
# Orin windows: ssh -t brian@192.168.55.1 tmux attach -t ranger
set -euo pipefail

# ─── RANGER V3 START: 12-field-time ───
USAGE="usage: $0 [sim|live] [nairobi|rabat] [usb|wifi] [--set-clock]"
usage() { echo "$USAGE" >&2; exit 2; }
SET_CLOCK=0
POS=()
for a in "$@"; do
  case "$a" in
    --set-clock) SET_CLOCK=1 ;;
    -*) usage ;;
    *) POS+=("$a") ;;
  esac
done
[ "${#POS[@]}" -le 3 ] || usage
MODE="${POS[0]:-sim}"
SITE="${POS[1]:-nairobi}"
LINK="${POS[2]:-usb}"
# The Orin's address on each link. Set ORIN_WIFI_HOST once, to the Orin's DHCP
# reservation on the travel router (F12 4d).
ORIN_USB_HOST=192.168.55.1
ORIN_WIFI_HOST=""
case "$LINK" in
  usb)  DEFAULT_HOST="$ORIN_USB_HOST" ;;
  wifi) DEFAULT_HOST="$ORIN_WIFI_HOST" ;;
  *) usage ;;
esac
ORIN_HOST="${ORIN_HOST:-$DEFAULT_HOST}"
[ -n "$ORIN_HOST" ] || { echo "wifi: ORIN_WIFI_HOST is not set in $0 — set it to the Orin's router reservation (F12 4d), or export ORIN_HOST" >&2; exit 2; }
# ─── RANGER V3 END: 12-field-time ───
# ─── RANGER V3 START: 11-ingest-region ───
case "$MODE" in sim|live) ;; *) usage ;; esac
case "$SITE" in nairobi|rabat) ;; *) usage ;; esac
# Must match the RANGER_MODE marker stack_up.sh writes.
if [ "$MODE" = sim ]; then WANT="sim:$SITE"; STACK_ARGS="sim --fresh --site $SITE"
else WANT=live; STACK_ARGS="live --fresh"; fi
INGEST="python manage.py ros_ingest"
[ "$MODE" = live ] && INGEST="$INGEST --source live"
[ "$SITE" = rabat ] && INGEST="$INGEST --region rabat"
# ─── RANGER V3 END: 11-ingest-region ───
[ "$ORIN_HOST" != "$ORIN_USB_HOST" ] && INGEST="$INGEST --host $ORIN_HOST"   # F12
ORIN="brian@${ORIN_HOST}"
MAX_OFFSET_S=0.5
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

step() { printf '\n── %s\n' "$*"; }
ok()   { printf '   ok: %s\n' "$*"; }
warn() { printf '   WARN: %s\n' "$*" >&2; }
fail() { printf '   FAIL: %s\n' "$*" >&2; exit 1; }

# Orin − PC in seconds, bracketed by two PC reads (TS-029).
# F12: over a reused ssh connection, so the bracket is one round trip, not a
# handshake — over wifi a handshake alone could exceed the 0.5 s limit.
SSH_MUX=(-o BatchMode=yes -o ControlMaster=auto -o "ControlPath=/tmp/ranger-ssh-%r@%h:%p" -o ControlPersist=60)
measure_offset() {
  local t0 r t1
  ssh "${SSH_MUX[@]}" "$ORIN" true
  t0=$(date +%s.%N)
  r=$(ssh "${SSH_MUX[@]}" "$ORIN" date +%s.%N)
  t1=$(date +%s.%N)
  python3 -c "print(f'{$r - ($t0 + $t1) / 2:+.2f}')"
}

within() {  # within <offset> <limit>
  python3 -c "import sys; sys.exit(0 if abs(float('$1')) <= float('$2') else 1)"
}

step "1/5 Orin reachable"
if [ "$LINK" = wifi ]; then hint="Orin not on the router? Check its reservation and that it auto-joined."
else hint="USB tether down? Replug, wait ~20 s."; fi
ping -c 1 -W 2 "$ORIN_HOST" >/dev/null \
  || fail "no reply from $ORIN_HOST ($LINK) — $hint"
ssh -o BatchMode=yes -o ConnectTimeout=5 "$ORIN" true 2>/dev/null \
  || fail "key-based ssh not set up. Run once: ssh-copy-id $ORIN"
ok "ping + key-based ssh"

step "2/5 Orin internet"
# Route and name are separate faults (TS-025): the NAT script fixes routing
# only, so only a routing failure triggers it — never re-run it for DNS.
orin_ping() { ssh -o BatchMode=yes "$ORIN" "ping -c 1 -W 3 $1" >/dev/null 2>&1; }
if [ "$LINK" = wifi ]; then
  ok "skipped (wifi: the stack and its clock don't need the Orin online — F12)"
elif orin_ping 1.1.1.1; then
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
if [ "$LINK" = wifi ]; then :
elif orin_ping google.com; then
  ok "DNS resolves"
else
  warn "routing works but DNS doesn't (TS-025). Not needed: the clock comes from this PC by IP (F12)."
fi

step "3/5 Orin clock"
clock_jumped=0
# ─── RANGER V3 START: 12-field-time ───
# Check, don't fix: the Orin takes time only from chrony on this PC. If it
# isn't synced, force one fresh attempt — after failed attempts timesyncd backs
# off for minutes (TS-033). Setting the clock by hand is opt-in (--set-clock),
# so a broken time server can't hide behind it on the way to the field.
orin_synced() {
  [ "$(ssh -o BatchMode=yes "$ORIN" timedatectl show -p NTPSynchronized --value 2>/dev/null)" = yes ]
}
if [ "$SET_CLOCK" = 0 ]; then
  systemctl is-active --quiet chrony \
    || fail "chrony is not running on this PC — the Orin's only time source. sudo systemctl start chrony"
  if ! orin_synced; then
    echo "   Orin not synced to the PC — forcing a fresh NTP attempt"
    ssh -o BatchMode=yes "$ORIN" "sudo -n /usr/bin/systemctl restart systemd-timesyncd" \
      || fail "can't restart timesyncd on the Orin without a password — install robot/config/sudoers-ranger-timesync (F12)"
    for _ in $(seq 30); do orin_synced && break; sleep 2; done
    orin_synced \
      || fail "Orin still not synced after 60 s — ssh $ORIN timedatectl timesync-status. Last resort: add --set-clock"
    clock_jumped=1
  fi
  offset=$(measure_offset)
  within "$offset" "$MAX_OFFSET_S" || fail "Orin reports synced but orin − pc = ${offset} s"
  ok "orin − pc = ${offset} s · synced to $(ssh -o BatchMode=yes "$ORIN" timedatectl show-timesync -p ServerAddress --value 2>/dev/null)"
else
warn "--set-clock: bypassing the time server (TS-029 fallback). Fix chrony before the field."
# ─── RANGER V3 END: 12-field-time ───
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
fi  # 12-field-time: end --set-clock

step "4/5 Postgres + Redis"
(cd "$REPO" && docker compose up -d --wait) >/dev/null \
  || fail "docker compose did not reach healthy — docker compose ps / logs"
[ "$(docker exec ranger_redis redis-cli ping)" = "PONG" ] || fail "redis did not answer PONG"
ok "ranger_postgres + ranger_redis healthy"

step "5/5 Orin stack (${WANT})"
# Empty = no session; "unknown" = a session not started by stack_up.sh (no marker).
running_mode=$(ssh -o BatchMode=yes "$ORIN" \
  "tmux has-session -t ranger 2>/dev/null && { tmux show-environment -t ranger RANGER_MODE 2>/dev/null | cut -d= -f2 | grep . || echo unknown; }" || true)
if [ "$running_mode" = "$WANT" ] && [ "$clock_jumped" = 0 ]; then
  ok "already running (${WANT}) — leaving it"
else
  if [ "$clock_jumped" = 1 ]; then why="clock was stepped"
  elif [ "$running_mode" = unknown ]; then why="a session exists with no mode marker"
  elif [ "$running_mode" = failed ]; then why="last start failed"
  elif [ -n "$running_mode" ]; then why="running ${running_mode}, want ${WANT}"
  else why="not running"; fi
  echo "   starting fresh (${why})"
  ssh -o BatchMode=yes "$ORIN" "\$HOME/ranger/stack_up.sh ${STACK_ARGS}" \
    || fail "stack_up.sh failed — ssh -t $ORIN tmux attach -t ranger"
fi
timeout 3 bash -c "</dev/tcp/${ORIN_HOST}/9090" 2>/dev/null \
  || fail "${ORIN_HOST}:9090 not reachable from the PC"
ok "rosbridge ${ORIN_HOST}:9090 reachable"

cat <<NEXT

── Ready. Three terminals, venv active (source ${REPO}/.venv/bin/activate):
   T1  cd ${REPO}/ranger_backend && python manage.py runserver      # banner: Daphne
   T2  cd ${REPO}/ranger_backend && ${INGEST}
   T3  cd ${REPO}/ranger_frontend && npm run dev                    # http://localhost:5173
NEXT
# ─── RANGER V3 END: dev-scripts ───
