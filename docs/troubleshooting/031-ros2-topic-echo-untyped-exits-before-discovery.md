# 031 — `ros2 topic echo` exits at once on a fresh stack: no type given, discovery not done

*Date: 2026-10-06*

---

## What we saw

`robot/tools/stack_up.sh` started socat, `gps_node`, rosbridge and `nmea_sim`,
confirmed rosbridge on `:9090`, then failed its health check:

```
FAIL: no /fix within 15 s — tmux attach -t ranger and check the gps window
```

Twice in a row. The stack itself was fine.

## The cause

The check was:

```bash
ros2 daemon stop
timeout 15 ros2 topic echo --once /fix
```

With no message type given, `ros2 topic echo` (Humble) must first learn
`/fix`'s type through discovery. Seconds after the publisher started and with a
freshly stopped daemon, discovery hadn't resolved it, and `echo` exits
immediately ("could not determine the type") rather than waiting. The 15 s
timeout never came into play.

The stubbed dry run passed because the stub's `ros2 topic echo` always
succeeded. The stub encoded the assumption the bug lived in.

## The fix

Give the type, so `echo` creates the subscription and waits; retry:

```bash
for _ in $(seq 6); do
  timeout 5 ros2 topic echo --once /fix sensor_msgs/msg/NavSatFix >/dev/null 2>&1 && { got_fix=1; break; }
done
```

First real run after the change: `ok: /fix publishing · mode=sim`.

Also changed: a failed check now leaves the tmux session up with
`RANGER_MODE=failed` instead of killing it, because the first version destroyed
the evidence. `scripts/dev_up.sh` reads the marker and restarts fresh.

## Prevention

- In scripts, always pass the message type to `ros2 topic echo`/`hz`.
- A health check that kills what it checks on failure leaves nothing to debug.
- A stub only proves the paths it doesn't fake.
