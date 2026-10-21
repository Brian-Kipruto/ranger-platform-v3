# 041 — Firewall unit `active`, rules gone after a reboot

*Date: 2026-10-20*

---

## What we saw

After installing `ranger-firewall.service` and rebooting: `systemctl is-active
ranger-firewall` → `active`, it started before NetworkManager — and `iptables -L
INPUT` was empty and `RANGER_PORTS` didn't exist. `stack_up.sh`'s check
(`systemctl is-active`) would have started rosbridge unprotected.

## The cause

`netfilter-persistent.service` (enabled on this image) runs at ~25 s and restores
`/etc/iptables/rules.v4` with `iptables-restore`, which **replaces the whole filter
table**. Our oneshot had run at ~16 s; its rules were wiped 9 s later, and a oneshot
stays `active` after it exits.

## The fix

- `After=netfilter-persistent.service` (still `Before=network-pre.target`). After
  reboot: netfilter-persistent 25.19 s → ranger-firewall 25.64 s → NetworkManager
  44.75 s, `RULES_IN_PLACE`.
- `ranger-firewall check` (the INPUT jump and the final REJECT, IPv4 and IPv6) run by
  `stack_up.sh` through `sudo -n` (sudoers allows exactly that command). The stack
  checks the rules, not the unit. Sandbox: after an `iptables-restore` like
  netfilter-persistent's, `check` fails.

## Prevention

- A oneshot's `active` says it ran, not that its effect is still there. Check effects.
- Before adding boot-time firewall rules, list what else manages them:
  `systemctl list-unit-files | grep -iE 'iptables|netfilter|ufw|nftables'`.
