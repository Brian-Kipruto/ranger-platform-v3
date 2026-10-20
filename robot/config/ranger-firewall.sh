#!/bin/bash
# ─── RANGER V3 START: 14-firewall ───
# Orin: only the console PC may reach rosbridge (:9090 — drive commands and
# telemetry; rosbridge has no auth) and web_video_server (:8080 — the feed is
# unauthenticated by design, F14 ADR). Everyone else on the network gets a TCP
# reset. The Orin itself (loopback and its own addresses) is always allowed:
# stack_up.sh checks its own ports.
#
# Installed as /usr/local/sbin/ranger-firewall, run by ranger-firewall.service
# at boot (robot/config/). See docs/features/14-*.md for install and proof.
#   ranger-firewall start | stop | status | check
#   check: exit 0 only if the INPUT jump and the chain's final REJECT are in
#   place for IPv4 and IPv6 — the rules themselves, not the service state.
#   stack_up.sh runs it via sudo -n (robot/config/sudoers-ranger-firewall).
set -euo pipefail

PORTS=9090,8080
CHAIN=RANGER_PORTS
# The console PC, by address: on the USB tether, and on the house Wi-Fi (router
# reservation, F14 4d). The venue network adds its address in Pass 8.
ALLOW=(192.168.55.100 192.168.0.102)

apply() {  # apply <iptables|ip6tables> [allowed source...]
  local ipt=$1; shift
  "$ipt" -N "$CHAIN" 2>/dev/null || "$ipt" -F "$CHAIN"
  "$ipt" -A "$CHAIN" -i lo -j ACCEPT
  "$ipt" -A "$CHAIN" -m addrtype --src-type LOCAL -j ACCEPT
  local a
  for a in "$@"; do "$ipt" -A "$CHAIN" -s "$a" -j ACCEPT; done
  "$ipt" -A "$CHAIN" -p tcp -j REJECT --reject-with tcp-reset
  "$ipt" -C INPUT -p tcp -m multiport --dports "$PORTS" -j "$CHAIN" 2>/dev/null \
    || "$ipt" -I INPUT 1 -p tcp -m multiport --dports "$PORTS" -j "$CHAIN"
}

remove() {  # remove <iptables|ip6tables>
  local ipt=$1
  while "$ipt" -D INPUT -p tcp -m multiport --dports "$PORTS" -j "$CHAIN" 2>/dev/null; do :; done
  "$ipt" -F "$CHAIN" 2>/dev/null || true
  "$ipt" -X "$CHAIN" 2>/dev/null || true
}

check() {  # check <iptables|ip6tables>
  local ipt=$1
  "$ipt" -C INPUT -p tcp -m multiport --dports "$PORTS" -j "$CHAIN" 2>/dev/null \
    && "$ipt" -C "$CHAIN" -p tcp -j REJECT --reject-with tcp-reset 2>/dev/null
}

case "${1:-start}" in
  start)  apply iptables "${ALLOW[@]}"; apply ip6tables ;;   # IPv6: no peer allowed
  stop)   remove iptables; remove ip6tables ;;
  status) iptables -S "$CHAIN"; ip6tables -S "$CHAIN" ;;
  check)  check iptables && check ip6tables ;;
  *) echo "usage: $0 start|stop|status|check" >&2; exit 2 ;;
esac
# ─── RANGER V3 END: 14-firewall ───
