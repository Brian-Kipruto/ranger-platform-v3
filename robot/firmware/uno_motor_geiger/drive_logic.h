// ─── RANGER V3 START: 14-uno-drive ───
// Pure drive logic for the 6WD Uno: no Arduino dependencies, so it is
// host-testable (test/test_drive_logic.cpp). Feature 14, 5a.
#pragma once
#include <stdint.h>
#include <stdlib.h>

namespace drive {

const long DEADBAND_MIN = 1400;           // unchanged from the RC-only firmware
const long DEADBAND_MAX = 1600;
const long NET_SWITCH_US = 1700;          // CH6 above this = NET; anything else = RC
const uint32_t RC_LOST_MS = 100;          // no complete PPM frame for this long = STOP
const uint32_t M_STALE_MS = 250;          // NET: no M line for longer than this = STOP
const uint32_t BOOT_LOCK_MS = 3000;       // unchanged: motors held at 0 after reset
const uint32_t PROLONGED_MS = 1000;       // unchanged: pivot turn -> tank turn
const int MAX_PWM = 255;

// X = stopped (boot lock or RC link lost), R = RC drives,
// N = network drives (fresh M), W = NET selected but M stale (stopped).
enum Mode { MODE_X = 'X', MODE_R = 'R', MODE_N = 'N', MODE_W = 'W' };

inline Mode selectMode(uint32_t nowMs, bool rcOk, long ch6,
                       bool mSeen, uint32_t mAgeMs) {
  if (nowMs < BOOT_LOCK_MS) return MODE_X;
  if (!rcOk) return MODE_X;
  if (ch6 > NET_SWITCH_US) {
    return (mSeen && mAgeMs <= M_STALE_MS) ? MODE_N : MODE_W;
  }
  return MODE_R;
}

// Strict parse of "M,<left>,<right>", each an integer in [-255, 255].
// Anything else is rejected (never clamped): a malformed line must not move motors.
inline bool parseM(const char *line, int *left, int *right) {
  if (line[0] != 'M' || line[1] != ',') return false;
  const char *p = line + 2;
  char *end;
  if (*p == '\0' || *p == ',') return false;
  long l = strtol(p, &end, 10);
  if (end == p || *end != ',') return false;
  p = end + 1;
  if (*p == '\0') return false;
  long r = strtol(p, &end, 10);
  if (end == p || *end != '\0') return false;
  if (l < -MAX_PWM || l > MAX_PWM || r < -MAX_PWM || r > MAX_PWM) return false;
  *left = (int)l;
  *right = (int)r;
  return true;
}

// Same formula as Arduino map().
inline long mapl(long x, long inMin, long inMax, long outMin, long outMax) {
  return (x - inMin) * (outMax - outMin) / (inMax - inMin) + outMin;
}

inline int clampPwm(long v) {
  return (int)(v < -MAX_PWM ? -MAX_PWM : (v > MAX_PWM ? MAX_PWM : v));
}

struct RcMixState {
  bool turningInPlace;
  uint32_t turnStartMs;
};

// The RC-only firmware's mixing, unchanged: deadband, invert dial on CH5,
// pivot turn for the first second of steer-only input, then tank turn.
inline void rcMix(long ch1, long ch2, long ch5, uint32_t nowMs,
                  RcMixState *st, int *leftOut, int *rightOut) {
  long throttle = 0;
  if (ch2 > DEADBAND_MAX) throttle = mapl(ch2, DEADBAND_MAX, 2000, 0, 255);
  else if (ch2 < DEADBAND_MIN) throttle = mapl(ch2, DEADBAND_MIN, 1000, 0, -255);

  long steering = 0;
  if (ch1 > DEADBAND_MAX) steering = mapl(ch1, DEADBAND_MAX, 2000, 0, 255);
  else if (ch1 < DEADBAND_MIN) steering = mapl(ch1, DEADBAND_MIN, 1000, 0, -255);

  if (ch5 > 1500) steering = -steering;

  long l = 0, r = 0;
  if (labs(throttle) > 0) {
    l = throttle + steering;
    r = throttle - steering;
    st->turningInPlace = false;
  } else if (labs(steering) > 0) {
    if (!st->turningInPlace) {
      st->turningInPlace = true;
      st->turnStartMs = nowMs;
    }
    if (nowMs - st->turnStartMs > PROLONGED_MS) {
      l = steering;
      r = -steering;
    } else if (steering > 0) {
      l = steering;
      r = 0;
    } else {
      l = 0;
      r = labs(steering);
    }
  } else {
    st->turningInPlace = false;
  }
  *leftOut = clampPwm(l);
  *rightOut = clampPwm(r);
}

}  // namespace drive
// ─── RANGER V3 END: 14-uno-drive ───
