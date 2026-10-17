// ─── RANGER V3 START: 14-uno-drive ───
// 6WD Uno: motors (2x BTS7960), RC (FS-X6B PPM on D3), Orin serial (D0/D1).
// Arbitration lives here: RC link lost -> stop; SwA (CH6) selects RC or NET;
// in NET the Orin's M lines drive, with a 250 ms watchdog. Feature 14, 5a.
//
// Serial contract, 115200 baud, '\n'-terminated lines:
//   Orin -> Uno  M,<left>,<right>       signed PWM, each in [-255, 255]
//   Uno -> Orin  S,<ms>,<mode>,<rc_ok>,<left>,<right>,<m_age_ms>,<rc_age_ms>,<ppm_rejected>,<ppm_glitches>,<ppm_disagreed>
//                  every 1 s and immediately on a mode change;
//                  mode X|R|N|W (see drive_logic.h); ages are -1 if never seen;
//                  ppm_* counters are cumulative since boot
//   Uno -> Orin  G,<counts>             counts since the previous G, every 1 s,
//                  only when GEIGER_ENABLED (tube is dead: ADR-0021)
#include "drive_logic.h"

#define GEIGER_ENABLED 0

// --- BTS7960 Left Track ---
const int left_RPWM = 5;
const int left_LPWM = 6;
const int left_R_EN = 4;
const int left_L_EN = 7;

// --- BTS7960 Right Track ---
const int right_RPWM = 9;
const int right_LPWM = 10;
const int right_R_EN = 8;
const int right_L_EN = 11;

const uint8_t GEIGER_PIN = 2;               // INT0
const uint8_t PPM_PIN = 3;                  // INT1
const unsigned long REPORT_MS = 1000;

// ISR-owned; loop() copies it with interrupts off (cli() is a compiler memory barrier).
drive::PpmDecoder ppm = {};

volatile uint32_t geigerCount = 0;

void ppmIsr() {
  bool levelHigh = (PIND & _BV(PD3)) != 0;  // sample D3 first: a spike is already gone
  drive::ppmEdge(&ppm, micros(), levelHigh);
}

void geigerIsr() { geigerCount++; }

char lineBuf[24];
uint8_t lineLen = 0;
bool lineOverflow = false;

int mLeft = 0, mRight = 0;
bool mSeen = false;
unsigned long mLastMs = 0;

drive::RcMixState mix = {false, 0};
char lastMode = 0;
unsigned long lastReportMs = 0;

void readSerial(unsigned long nowMs) {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      lineBuf[lineLen] = '\0';
      int l, r;
      if (!lineOverflow && drive::parseM(lineBuf, &l, &r)) {
        mLeft = l;
        mRight = r;
        mSeen = true;
        mLastMs = nowMs;
      }
      lineLen = 0;
      lineOverflow = false;
    } else if (lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = c;
    } else {
      lineOverflow = true;
    }
  }
}

void driveMotors(int left, int right) {
  if (left > 0) {
    analogWrite(left_RPWM, left);
    analogWrite(left_LPWM, 0);
  } else if (left < 0) {
    analogWrite(left_RPWM, 0);
    analogWrite(left_LPWM, abs(left));
  } else {
    analogWrite(left_RPWM, 0);
    analogWrite(left_LPWM, 0);
  }

  if (right > 0) {
    analogWrite(right_RPWM, right);
    analogWrite(right_LPWM, 0);
  } else if (right < 0) {
    analogWrite(right_RPWM, 0);
    analogWrite(right_LPWM, abs(right));
  } else {
    analogWrite(right_RPWM, 0);
    analogWrite(right_LPWM, 0);
  }
}

void setup() {
  pinMode(left_RPWM, OUTPUT);
  pinMode(left_LPWM, OUTPUT);
  pinMode(right_RPWM, OUTPUT);
  pinMode(right_LPWM, OUTPUT);

  // SAFETY: Force PWM signals zero BEFORE waking up drivers
  analogWrite(left_RPWM, 0);
  analogWrite(left_LPWM, 0);
  analogWrite(right_RPWM, 0);
  analogWrite(right_LPWM, 0);

  pinMode(left_R_EN, OUTPUT);
  pinMode(left_L_EN, OUTPUT);
  pinMode(right_R_EN, OUTPUT);
  pinMode(right_L_EN, OUTPUT);

  digitalWrite(left_R_EN, HIGH);
  digitalWrite(left_L_EN, HIGH);
  digitalWrite(right_R_EN, HIGH);
  digitalWrite(right_L_EN, HIGH);

  Serial.begin(115200);
  pinMode(PPM_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(PPM_PIN), ppmIsr, RISING);
  pinMode(GEIGER_PIN, INPUT_PULLUP);
#if GEIGER_ENABLED
  attachInterrupt(digitalPinToInterrupt(GEIGER_PIN), geigerIsr, FALLING);
#endif
}

void loop() {
  unsigned long nowMs = millis();
  readSerial(nowMs);

  uint16_t ch[drive::PPM_CHANNELS];
  uint32_t frames, rejected, glitches, disagreed;
  unsigned long lastFrameUs;
  noInterrupts();
  for (uint8_t i = 0; i < drive::PPM_CHANNELS; i++) ch[i] = ppm.chan[i];
  frames = ppm.frames;
  lastFrameUs = ppm.lastFrameUs;
  rejected = ppm.rejected;
  glitches = ppm.glitches;
  disagreed = ppm.disagreed;
  interrupts();

  unsigned long rcAgeUs = micros() - lastFrameUs;
  bool rcOk = frames > 0 && rcAgeUs <= drive::RC_LOST_MS * 1000UL;
  unsigned long mAgeMs = nowMs - mLastMs;

  drive::Mode mode = drive::selectMode(nowMs, rcOk, ch[5], mSeen, mAgeMs);

  int left = 0, right = 0;
  if (mode == drive::MODE_R) {
    drive::rcMix(ch[0], ch[1], ch[4], nowMs, &mix, &left, &right);
  } else {
    mix.turningInPlace = false;
    if (mode == drive::MODE_N) {
      left = mLeft;
      right = mRight;
    }
  }
  driveMotors(left, right);

  bool periodic = nowMs - lastReportMs >= REPORT_MS;
  if ((char)mode != lastMode || periodic) {
    Serial.print(F("S,")); Serial.print(nowMs);
    Serial.print(','); Serial.print((char)mode);
    Serial.print(','); Serial.print(rcOk ? 1 : 0);
    Serial.print(','); Serial.print(left);
    Serial.print(','); Serial.print(right);
    Serial.print(','); Serial.print(mSeen ? (long)mAgeMs : -1L);
    Serial.print(','); Serial.print(frames > 0 ? (long)(rcAgeUs / 1000UL) : -1L);
    Serial.print(','); Serial.print(rejected);
    Serial.print(','); Serial.print(glitches);
    Serial.print(','); Serial.println(disagreed);
    lastMode = (char)mode;
  }
  if (periodic) {
    lastReportMs = nowMs;
#if GEIGER_ENABLED
    noInterrupts();
    uint32_t counts = geigerCount;
    geigerCount = 0;
    interrupts();
    Serial.print(F("G,")); Serial.println(counts);
#endif
  }
}
// ─── RANGER V3 END: 14-uno-drive ───
