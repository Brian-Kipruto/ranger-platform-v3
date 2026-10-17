// ─── RANGER V3 START: 14-ppm-probe ───
// Bench probe for the FS-X6B PPM output on D3 (INT1). Feature 14, 5a.
// Prints CH1-CH6 at 10 Hz and LOST/BACK transitions. Never drives motors:
// all BTS7960 enables held LOW, all PWM pins held LOW.

const uint8_t PPM_PIN = 3;              // INT1
const unsigned long SYNC_US = 3000;     // gap longer than this = frame start
const unsigned long LOST_US = 100000;   // no complete frame for 100 ms = LOST
const uint8_t MAX_CH = 8;

const uint8_t MOTOR_PINS[] = {4, 5, 6, 7, 8, 9, 10, 11};  // EN + PWM, both drivers

volatile uint16_t chan[MAX_CH];         // last complete frame
volatile uint8_t chanCount = 0;         // channels in last complete frame
volatile uint32_t frames = 0;
volatile unsigned long lastFrameUs = 0;

uint16_t buf[MAX_CH];                   // ISR-only working buffer
uint8_t idx = 0;
unsigned long lastEdgeUs = 0;

void ppmIsr() {
  unsigned long now = micros();
  unsigned long d = now - lastEdgeUs;
  lastEdgeUs = now;
  if (d > SYNC_US) {
    if (idx >= 6) {
      for (uint8_t i = 0; i < idx; i++) chan[i] = buf[i];
      chanCount = idx;
      frames++;
      lastFrameUs = now;
    }
    idx = 0;
  } else if (idx < MAX_CH) {
    buf[idx++] = (uint16_t)d;
  }
}

bool lost = true;
unsigned long lastPrintMs = 0;

void setup() {
  for (uint8_t i = 0; i < sizeof(MOTOR_PINS); i++) {
    pinMode(MOTOR_PINS[i], OUTPUT);
    digitalWrite(MOTOR_PINS[i], LOW);
  }
  Serial.begin(115200);
  pinMode(PPM_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(PPM_PIN), ppmIsr, RISING);
  Serial.println(F("ppm_probe ready"));
}

void loop() {
  uint16_t c[MAX_CH];
  uint8_t n;
  uint32_t f;
  unsigned long lf;
  noInterrupts();
  for (uint8_t i = 0; i < MAX_CH; i++) c[i] = chan[i];
  n = chanCount;
  f = frames;
  lf = lastFrameUs;
  interrupts();

  unsigned long age = micros() - lf;
  bool nowLost = (f == 0) || (age > LOST_US);

  if (nowLost && !lost) {
    Serial.print(F("LOST ms=")); Serial.print(millis());
    Serial.print(F(" since_last_frame_ms=")); Serial.println(age / 1000);
  } else if (!nowLost && lost) {
    Serial.print(F("BACK ms=")); Serial.println(millis());
  }
  lost = nowLost;

  if (millis() - lastPrintMs >= 100) {
    lastPrintMs = millis();
    if (lost) {
      Serial.print(F("LOST frames=")); Serial.println(f);
    } else {
      for (uint8_t i = 0; i < 6; i++) {
        Serial.print(F("CH")); Serial.print(i + 1); Serial.print('=');
        Serial.print(c[i]); Serial.print(' ');
      }
      Serial.print(F("nch=")); Serial.print(n);
      Serial.print(F(" frames=")); Serial.println(f);
    }
  }
}
// ─── RANGER V3 END: 14-ppm-probe ───
