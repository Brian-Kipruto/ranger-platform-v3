# 042 — A firewall test from the PC lets the "intruder" in

*Date: 2026-10-20*

---

## What we saw

To prove the firewall, the PC borrowed a second address (`sudo ip addr add
192.168.0.98/24 dev wlo1`) and ran `curl --interface 192.168.0.98` to the Orin's
`:8080` and `:9090`. With the firewall on, stopped and restored, the "intruder" got
through every time.

## The cause

The test, not the firewall. The Orin's counters showed the connection matched the
`192.168.0.102` ACCEPT rule, and `ss` showed the peer as `.102`. The PC has
`-A POSTROUTING -o wlo1 -j MASQUERADE` (from `jetson-internet.sh`, the NAT that gives
the Orin internet over the tether): every packet leaving `wlo1` is rewritten to the
interface's primary address. The rule was present **twice** — the script adds it on
each run. The sandbox test passed because it had no NAT.

## The fix

A real intruder: a phone on the house Wi-Fi. Firewall on → `:8080` and `:9090`
`ERR_CONNECTION_REFUSED`; stopped → the feed loads; restored → the open stream froze.

## Prevention

- Before trusting a negative network test, check where the packet's source is
  rewritten: `sudo iptables -t nat -S POSTROUTING`.
- Read the firewall's packet counters (`iptables -Z`, run the probe, `iptables -L -v`)
  to see which rule actually matched.
- Open item: scope `jetson-internet.sh` to `-s 192.168.55.0/24` and make it
  idempotent, or retire it.
