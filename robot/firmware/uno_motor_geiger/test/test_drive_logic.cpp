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

int main() {
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
