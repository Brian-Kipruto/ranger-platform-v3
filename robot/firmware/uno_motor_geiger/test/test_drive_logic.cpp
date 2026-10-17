// ─── RANGER V3 START: 14-uno-drive ───
// Host tests for drive_logic.h. Build and run:
//   g++ -std=c++11 -Wall -Wextra -Werror -o /tmp/test_drive_logic test_drive_logic.cpp
//   /tmp/test_drive_logic
#include <cstdio>
#include "../drive_logic.h"

using namespace drive;

static int failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond); failures++; } } while (0)

static const uint32_t T = 10000;  // well past the boot lock

static void test_boot_lock() {
  // Everything says drive, but the boot lock wins.
  CHECK(selectMode(0, true, 2000, true, 0) == MODE_X);
  CHECK(selectMode(BOOT_LOCK_MS - 1, true, 2000, true, 0) == MODE_X);
  CHECK(selectMode(BOOT_LOCK_MS - 1, true, 1000, true, 0) == MODE_X);
  CHECK(selectMode(BOOT_LOCK_MS, true, 1000, true, 0) == MODE_R);
}

static void test_rc_lost_stops_both_modes() {
  CHECK(selectMode(T, false, 1000, true, 0) == MODE_X);  // RC position
  CHECK(selectMode(T, false, 2000, true, 0) == MODE_X);  // NET position, fresh M
}

static void test_switch_threshold() {
  CHECK(selectMode(T, true, 1000, true, 0) == MODE_R);
  CHECK(selectMode(T, true, 1508, true, 0) == MODE_R);   // transition frame seen on the bench
  CHECK(selectMode(T, true, NET_SWITCH_US, true, 0) == MODE_R);
  CHECK(selectMode(T, true, NET_SWITCH_US + 1, true, 0) == MODE_N);
  CHECK(selectMode(T, true, 2000, true, 0) == MODE_N);
}

static void test_net_watchdog() {
  CHECK(selectMode(T, true, 2000, true, M_STALE_MS) == MODE_N);
  CHECK(selectMode(T, true, 2000, true, M_STALE_MS + 1) == MODE_W);
  CHECK(selectMode(T, true, 2000, false, 0) == MODE_W);  // never received an M
}

static void test_rc_mode_ignores_m() {
  // M freshness is irrelevant in RC mode: the result is R either way.
  CHECK(selectMode(T, true, 1000, true, 0) == MODE_R);
  CHECK(selectMode(T, true, 1000, false, 0) == MODE_R);
}

static void test_parse_valid() {
  int l = 99, r = 99;
  CHECK(parseM("M,0,0", &l, &r) && l == 0 && r == 0);
  CHECK(parseM("M,100,-100", &l, &r) && l == 100 && r == -100);
  CHECK(parseM("M,255,-255", &l, &r) && l == 255 && r == -255);
  CHECK(parseM("M,-255,255", &l, &r) && l == -255 && r == 255);
}

static void test_parse_rejects_and_leaves_outputs() {
  const char *bad[] = {
    "", "M", "M,", "M,1", "M,1,", "M,,1", "M,1,,", "M,1,2,3", "M,256,0", "M,0,-256",
    "M,a,2", "M,1,b", "M,1,2 ", "X,1,2", "m,1,2", "M;1;2", "M,1.5,2", "M,99999999999,0",
  };
  for (unsigned i = 0; i < sizeof(bad) / sizeof(bad[0]); i++) {
    int l = 7, r = 7;
    bool ok = parseM(bad[i], &l, &r);
    if (ok || l != 7 || r != 7) {
      std::printf("FAIL parse accepted or wrote on \"%s\"\n", bad[i]);
      failures++;
    }
  }
}

static void test_rc_mix_unchanged_behaviour() {
  RcMixState st = {false, 0};
  int l, r;
  rcMix(1500, 1500, 1000, T, &st, &l, &r);
  CHECK(l == 0 && r == 0);                                   // centred
  rcMix(1590, 1410, 1000, T, &st, &l, &r);
  CHECK(l == 0 && r == 0);                                   // inside deadband
  rcMix(1410, 1590, 1000, T, &st, &l, &r);
  CHECK(l == 0 && r == 0);                                   // inside deadband, other edges
  rcMix(1616, 1564, 1000, T, &st, &l, &r);
  CHECK(l != 0 || r != 0);                                   // the pre-trim CH1 offset did creep
  rcMix(1500, 2000, 1000, T, &st, &l, &r);
  CHECK(l == 255 && r == 255);                               // full forward
  rcMix(1500, 1000, 1000, T, &st, &l, &r);
  CHECK(l == -255 && r == -255);                             // full reverse
  rcMix(2000, 2000, 1000, T, &st, &l, &r);
  CHECK(l == 255 && r == 0);                                 // forward + right, clamped

  // Steer only: pivot for the first second, then tank.
  st = RcMixState{false, 0};
  rcMix(2000, 1500, 1000, T, &st, &l, &r);
  CHECK(l == 255 && r == 0);
  rcMix(2000, 1500, 1000, T + PROLONGED_MS, &st, &l, &r);
  CHECK(l == 255 && r == 0);
  rcMix(2000, 1500, 1000, T + PROLONGED_MS + 1, &st, &l, &r);
  CHECK(l == 255 && r == -255);
  st = RcMixState{false, 0};
  rcMix(1000, 1500, 1000, T, &st, &l, &r);
  CHECK(l == 0 && r == 255);                                 // left pivot

  // Invert dial flips steering.
  st = RcMixState{false, 0};
  rcMix(2000, 1500, 2000, T, &st, &l, &r);
  CHECK(l == 0 && r == 255);
}

// ─── PPM decoder ───
static const uint16_t FRAME_A[PPM_CHANNELS] = {1500, 1500, 1440, 1500, 1450, 1000, 1500, 1500};
static const uint16_t FRAME_B[PPM_CHANNELS] = {2000, 1000, 1440, 1500, 1450, 2000, 1500, 1500};
// The bench corruption (2026-10-17): in range, 8 channels, but CH1/CH2 boundary shifted.
static const uint16_t FRAME_BOGUS[PPM_CHANNELS] = {1000, 1500, 1440, 1500, 1450, 1000, 1500, 1500};

// Edge stream helpers. start() emits the edge that ends a frame gap; feedFrame() emits one
// edge per channel, then the gap, then the next gap-ending edge, which evaluates the frame.
static void start(PpmDecoder *d, uint32_t *t) { ppmEdge(d, *t, true); }
static void feedFrame(PpmDecoder *d, uint32_t *t, const uint16_t *ch, uint8_t n) {
  for (uint8_t i = 0; i < n; i++) { *t += ch[i]; ppmEdge(d, *t, true); }
  *t += 8000;
  ppmEdge(d, *t, true);
}

static bool chanEq(const PpmDecoder &d, const uint16_t *ch) {
  for (uint8_t i = 0; i < PPM_CHANNELS; i++) if (d.chan[i] != ch[i]) return false;
  return true;
}

static void test_ppm_needs_two_agreeing_frames() {
  PpmDecoder d = {}; uint32_t t = 100000; start(&d, &t);
  feedFrame(&d, &t, FRAME_A, 8);
  CHECK(d.frames == 0);                         // first frame alone is never published
  feedFrame(&d, &t, FRAME_A, 8);
  CHECK(d.frames == 1 && chanEq(d, FRAME_A) && d.lastFrameUs == t);
  CHECK(d.rejected == 0 && d.glitches == 0 && d.disagreed == 1);
}

static void test_ppm_jump_takes_two_frames() {
  PpmDecoder d = {}; uint32_t t = 100000; start(&d, &t);
  feedFrame(&d, &t, FRAME_A, 8); feedFrame(&d, &t, FRAME_A, 8);
  feedFrame(&d, &t, FRAME_B, 8);
  CHECK(d.frames == 1 && chanEq(d, FRAME_A));   // B disagrees with A: held
  feedFrame(&d, &t, FRAME_B, 8);
  CHECK(d.frames == 2 && chanEq(d, FRAME_B));
}

static void test_ppm_agreement_tolerance() {
  PpmDecoder d = {}; uint32_t t = 100000; start(&d, &t);
  uint16_t a[8], b[8], c[8];
  for (int i = 0; i < 8; i++) { a[i] = FRAME_A[i]; b[i] = FRAME_A[i]; c[i] = FRAME_A[i]; }
  b[0] = a[0] + PPM_AGREE_US;                   // inclusive bound: publishes
  c[0] = b[0] + PPM_AGREE_US + 1;               // one past: held
  feedFrame(&d, &t, a, 8); feedFrame(&d, &t, b, 8);
  CHECK(d.frames == 1 && d.chan[0] == b[0]);
  feedFrame(&d, &t, c, 8);
  CHECK(d.frames == 1 && d.chan[0] == b[0]);
  b[3] = a[3] - PPM_AGREE_US - 1;               // negative direction, another channel
  feedFrame(&d, &t, a, 8); feedFrame(&d, &t, a, 8); feedFrame(&d, &t, b, 8);
  CHECK(d.chan[3] == a[3]);
}

static void test_ppm_bench_corruption_never_published() {
  // Steady A, one in-range corrupted frame, steady A again.
  PpmDecoder d = {}; uint32_t t = 100000; start(&d, &t);
  for (int i = 0; i < 3; i++) feedFrame(&d, &t, FRAME_A, 8);
  feedFrame(&d, &t, FRAME_BOGUS, 8);
  for (int i = 0; i < 3; i++) {
    feedFrame(&d, &t, FRAME_A, 8);
    CHECK(chanEq(d, FRAME_A));
  }
  CHECK(chanEq(d, FRAME_A) && d.disagreed == 3);   // first A, BOGUS, A after BOGUS
}

static void test_ppm_invalid_frame_breaks_the_pair() {
  PpmDecoder d = {}; uint32_t t = 100000; start(&d, &t);
  uint16_t lo[8] = {1500, 750, 1500, 1500, 1500, 1500, 1500, 1500};
  feedFrame(&d, &t, FRAME_A, 8); feedFrame(&d, &t, FRAME_A, 8);
  uint32_t before = d.frames;
  feedFrame(&d, &t, FRAME_A, 6);                // partial (seen after reconnect)
  feedFrame(&d, &t, FRAME_A, 8);
  CHECK(d.frames == before);                    // A after a partial has no valid partner
  feedFrame(&d, &t, lo, 8);                     // out of range
  feedFrame(&d, &t, FRAME_A, 8);
  CHECK(d.frames == before);
  feedFrame(&d, &t, FRAME_A, 8);
  CHECK(d.frames == before + 1);
  CHECK(d.rejected == 2);
}

static void test_ppm_count_and_range() {
  PpmDecoder d = {}; uint32_t t = 100000; start(&d, &t);
  uint16_t nine[9] = {1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500};
  uint16_t hi[8] = {1500, 1500, 1500, 1500, 1500, 2250, 1500, 1500};
  feedFrame(&d, &t, nine, 9); feedFrame(&d, &t, nine, 9);
  feedFrame(&d, &t, hi, 8); feedFrame(&d, &t, hi, 8);
  CHECK(d.frames == 0 && d.rejected == 4);
  uint16_t edge[8] = {800, 2200, 1500, 1500, 1500, 1500, 1500, 1500};
  feedFrame(&d, &t, edge, 8); feedFrame(&d, &t, edge, 8);
  CHECK(d.frames == 1 && d.chan[0] == 800 && d.chan[1] == 2200);   // bounds inclusive
}

static void test_ppm_spikes_ignored() {
  // Short spikes in every channel of two frames: pin already low (brush-noise type) or
  // < 700 us after a real edge. Both frames decode exactly.
  PpmDecoder d = {}; uint32_t t = 100000; start(&d, &t);
  for (int f = 0; f < 2; f++) {
    for (uint8_t i = 0; i < PPM_CHANNELS; i++) {
      ppmEdge(&d, t + 300, false);
      ppmEdge(&d, t + 50, true);
      ppmEdge(&d, t + FRAME_B[i] - 20, false);
      t += FRAME_B[i];
      ppmEdge(&d, t, true);
    }
    t += 8000;
    ppmEdge(&d, t, true);
  }
  CHECK(d.frames == 1 && chanEq(d, FRAME_B) && d.rejected == 0 && d.glitches == 48);
}

static void test_ppm_fuzz_never_publishes_out_of_range() {
  PpmDecoder d = {}; uint32_t t = 100000; start(&d, &t);
  uint32_t seed = 12345;
  for (int i = 0; i < 400000; i++) {
    seed = seed * 1103515245u + 12345u;
    t += 1 + (seed >> 8) % 4000;
    bool level = ((seed >> 4) & 3) != 0;
    if (ppmEdge(&d, t, level)) {
      for (uint8_t c = 0; c < PPM_CHANNELS; c++) {
        if (d.chan[c] < PPM_CH_MIN_US || d.chan[c] > PPM_CH_MAX_US) {
          std::printf("FAIL fuzz published ch%u=%u\n", c + 1, d.chan[c]); failures++; return;
        }
      }
    }
  }
  CHECK(d.rejected > 0 && d.glitches > 0 && d.disagreed > 0);
}

static void test_ppm_spike_storm_recovers() {
  // A high spike in a frame gap looks like a 9th channel; that frame and its partner are
  // lost, clean frames afterwards publish.
  PpmDecoder d = {}; uint32_t t = 100000; start(&d, &t);
  for (uint8_t i = 0; i < PPM_CHANNELS; i++) { t += FRAME_A[i]; ppmEdge(&d, t, true); }
  ppmEdge(&d, t + 1000, true);
  t += 8000; ppmEdge(&d, t, true);
  CHECK(d.rejected == 1);
  feedFrame(&d, &t, FRAME_A, 8);
  feedFrame(&d, &t, FRAME_A, 8);
  CHECK(chanEq(d, FRAME_A) && d.lastFrameUs == t && d.frames == 1);
}

int main() {
  test_ppm_needs_two_agreeing_frames();
  test_ppm_jump_takes_two_frames();
  test_ppm_agreement_tolerance();
  test_ppm_bench_corruption_never_published();
  test_ppm_invalid_frame_breaks_the_pair();
  test_ppm_count_and_range();
  test_ppm_spikes_ignored();
  test_ppm_fuzz_never_publishes_out_of_range();
  test_ppm_spike_storm_recovers();
  test_boot_lock();
  test_rc_lost_stops_both_modes();
  test_switch_threshold();
  test_net_watchdog();
  test_rc_mode_ignores_m();
  test_parse_valid();
  test_parse_rejects_and_leaves_outputs();
  test_rc_mix_unchanged_behaviour();
  if (failures) { std::printf("%d FAILED\n", failures); return 1; }
  std::printf("all drive_logic tests passed\n");
  return 0;
}
// ─── RANGER V3 END: 14-uno-drive ───
