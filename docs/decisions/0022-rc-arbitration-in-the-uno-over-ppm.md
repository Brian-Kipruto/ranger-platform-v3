# ADR-0022: RC arbitration lives in the Uno, RC arrives over PPM, PPM is filtered

- **Status:** Accepted (proven on wheels, on blocks)
- **Date:** 2026-10-19
- **Feature:** F14 (Drive and Video), checkpoint 5a
- **Related:** ADR-0023 (teleop path), ADR-0021 (the Uno's serial port has one owner), TS-036

## Context

The 6WD's Uno drives two BTS7960 drivers and must obey two masters: the operator's
FS-i6X transmitter (FS-X6B receiver) and the console via the Orin. Whoever decides
between them must keep working when everything above it has crashed. The receiver
offers PPM and i-BUS connectors; it has no per-channel PWM pins.

## Decision 1 — Arbitration is in the Uno's firmware

`drive_logic.h` selects a mode on every loop:

| Mode | When | Motors |
|---|---|---|
| `X` | boot lock (first 3 s), or RC link lost | stopped |
| `R` | RC link alive, SwA (CH6) ≤ 1700 µs | RC sticks |
| `N` | RC alive, SwA > 1700 µs, an `M` line ≤ 250 ms old | the Orin's `M,<l>,<r>` |
| `W` | RC alive, SwA > 1700 µs, no fresh `M` | stopped |

Network driving therefore needs the RC link **alive** and the switch **in NET**:
the transmitter is a consent switch and a kill switch that no software above the
Uno can override. RC link lost (no valid frame for 100 ms) → `X`. The receiver has
no failsafe set on the TX on purpose: it goes silent on link loss, and silence is
the detector.

`M` lines out of range are **rejected, not clamped**. The Uno reports
`S,<ms>,<mode>,<rc_ok>,<left>,<right>,<m_age_ms>,<rc_age_ms>,<ppm_rejected>,<ppm_glitches>,<ppm_disagreed>`
every second and on every mode change.

## Decision 2 — RC over PPM on D3 (INT1)

- **i-BUS rejected:** the Uno has one hardware UART and it is the Orin link;
  IBusBM needs hardware serial.
- **Per-channel PWM rejected:** the X6B has no PWM outputs.
- **PPM:** one interrupt pin, all 8 channels.

## Decision 3 — PPM has no checksum, so frames must earn trust

- a pin-level spike check in the ISR and a 700 µs minimum edge spacing
- exactly 8 channels, each within 800–2200 µs
- **two-frame agreement:** a frame is used only if every channel is within ±100 µs
  of the previous frame (rest jitter is about ±16 µs)

Two-frame agreement was added after a corrupted **in-range** frame commanded a full
pivot during full reverse on the bench: range checks alone can't catch a plausible
wrong value. The counters in `S` make the filter's work visible.

## Rejected — a 250 ms RC-loss timeout

Tried so the robot would ride through motor noise (TS-036). It didn't help — the
noise is near-continuous above PWM ~200 — and it costs 150 ms on every real TX-loss
stop. Kept 100 ms.

## Consequences

- The robot stops without the Orin, the PC, the network or the console.
- Motor brush noise above ~100 PWM causes RC dropouts (stops, never commands) until
  the motor capacitors are in; `uno_bridge` caps at `max_pwm` 120 meanwhile.
- `cmd_vel` is normalised (ADR-0023), so the PWM cap lives in one place.
