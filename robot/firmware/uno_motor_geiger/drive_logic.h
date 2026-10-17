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

// ─── PPM decoder ───
// Called from the D3 rising-edge ISR with micros(). Pure, so the noise handling is
// host-testable. Under motor load the PPM wire picks up spikes (bench, 2026-10-17):
//  - a rising edge whose pin is already low again when the ISR samples it (levelHigh false)
//    was a spike shorter than the ISR latency, and is ignored; real PPM edges stay high for
//    hundreds of microseconds;
//  - an edge less than PPM_MIN_EDGE_US after the last accepted edge is a glitch and is
//    ignored without moving lastEdgeUs, so the real edge timing survives a spike;
//  - a frame is a candidate only if it has exactly PPM_CHANNELS intervals and every one is
//    within [PPM_CH_MIN_US, PPM_CH_MAX_US]; anything else is counted as rejected;
//  - a candidate is published only if every channel is within PPM_AGREE_US of the
//    immediately preceding candidate; otherwise it is counted as disagreed.
// PPM has no checksum. On the bench (motors on, 2026-10-17) a corrupted frame passed the
// count and range checks and commanded a full pivot during full reverse. With the agreement
// check a wrong command needs two consecutive, near-identical corruptions; anything that does
// pass is within PPM_AGREE_US of the previous frame (about 64 PWM, one frame). Corruption
// otherwise only costs fresh frames, i.e. a stop after RC_LOST_MS.
// Readers outside the ISR copy chan/frames/lastFrameUs with interrupts off.
const uint8_t PPM_CHANNELS = 8;          // FS-X6B PPM frame
const uint32_t PPM_SYNC_US = 3000;       // interval longer than this = frame gap
const uint32_t PPM_MIN_EDGE_US = 700;    // real channels are ~1000-2000 us
const uint16_t PPM_CH_MIN_US = 800;
const uint16_t PPM_CH_MAX_US = 2200;
const uint16_t PPM_AGREE_US = 100;       // jitter at rest is about +-16 us

struct PpmDecoder {
  uint32_t lastEdgeUs;
  uint8_t idx;
  uint16_t buf[PPM_CHANNELS];
  uint16_t chan[PPM_CHANNELS];           // last published frame
  uint32_t frames;                       // published frames
  uint32_t lastFrameUs;
  uint32_t rejected;                     // frames discarded (wrong count or out of range)
  uint32_t glitches;                     // edges ignored as spikes
  uint16_t prev[PPM_CHANNELS];           // previous candidate frame
  bool prevValid;
  uint32_t disagreed;                    // candidates discarded by the agreement check
};

// Returns true when this edge published a frame.
inline bool ppmEdge(PpmDecoder *d, uint32_t nowUs, bool levelHigh) {
  if (!levelHigh) {
    d->glitches++;
    return false;
  }
  uint32_t dt = nowUs - d->lastEdgeUs;
  if (dt < PPM_MIN_EDGE_US) {
    d->glitches++;
    return false;
  }
  d->lastEdgeUs = nowUs;
  if (dt > PPM_SYNC_US) {
    bool published = false;
    if (d->idx == PPM_CHANNELS) {
      bool inRange = true;
      for (uint8_t i = 0; i < PPM_CHANNELS; i++) {
        if (d->buf[i] < PPM_CH_MIN_US || d->buf[i] > PPM_CH_MAX_US) inRange = false;
      }
      if (inRange) {
        bool agree = d->prevValid;
        for (uint8_t i = 0; i < PPM_CHANNELS && agree; i++) {
          int32_t diff = (int32_t)d->buf[i] - (int32_t)d->prev[i];
          if (diff < -(int32_t)PPM_AGREE_US || diff > (int32_t)PPM_AGREE_US) agree = false;
        }
        for (uint8_t i = 0; i < PPM_CHANNELS; i++) d->prev[i] = d->buf[i];
        d->prevValid = true;
        if (agree) {
          for (uint8_t i = 0; i < PPM_CHANNELS; i++) d->chan[i] = d->buf[i];
          d->frames++;
          d->lastFrameUs = nowUs;
          published = true;
        } else {
          d->disagreed++;
        }
      } else {
        d->rejected++;
        d->prevValid = false;
      }
    } else if (d->idx != 0) {
      d->rejected++;
      d->prevValid = false;
    }
    d->idx = 0;
    return published;
  }
  if (d->idx < PPM_CHANNELS) {
    d->buf[d->idx++] = (uint16_t)dt;
  } else {
    d->idx = PPM_CHANNELS + 1;             // too many intervals: frame will be rejected
  }
  return false;
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
