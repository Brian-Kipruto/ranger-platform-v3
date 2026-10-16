#include <IBusBM.h>

IBusBM IBus;

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

// --- Time-Delayed Turn Variables ---
unsigned long turnStartTime = 0;
bool isTurningInPlace = false;
const unsigned long prolongedDelay = 1000; 

// --- Safety Variables ---
unsigned long bootTime = 0;
const int deadbandMin = 1400; 
const int deadbandMax = 1600; 

void setup() {
  IBus.begin(Serial); 
  bootTime = millis();
  
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
}

void loop() {
  IBus.loop(); 

  // 3-Second Boot Lock
  if (millis() - bootTime < 3000) {
    driveMotors(0, 0);
    return; 
  }

  // --- Read Channels (0-indexed) ---
  int ch2 = IBus.readChannel(1); // Right Stick Up/Down (Throttle)
  int ch1 = IBus.readChannel(0); // Right Stick Left/Right (Steering)
  int ch5 = IBus.readChannel(4); // VrA or VrB Dial (Invert controls)

  if (ch2 == 0 || ch1 == 0) {
    driveMotors(0, 0);
    return;
  }

  // --- Mapping & Deadband ---
  int throttle = 0;
  if (ch2 > deadbandMax) throttle = map(ch2, deadbandMax, 2000, 0, 255);
  else if (ch2 < deadbandMin) throttle = map(ch2, deadbandMin, 1000, 0, -255);

  int steering = 0;
  if (ch1 > deadbandMax) steering = map(ch1, deadbandMax, 2000, 0, 255);
  else if (ch1 < deadbandMin) steering = map(ch1, deadbandMin, 1000, 0, -255);

  // --- INVERT STEERING LOGIC ---
  if (ch5 > 1500) {
    steering = -steering;
  }

  int leftSpeed = 0;
  int rightSpeed = 0;

  // --- Movement Logic ---
  if (abs(throttle) > 0) {
    leftSpeed = throttle + steering;
    rightSpeed = throttle - steering;
    isTurningInPlace = false; 
  } 
  else if (abs(steering) > 0) {
    if (!isTurningInPlace) {
      isTurningInPlace = true;
      turnStartTime = millis(); 
    }

    if (millis() - turnStartTime > prolongedDelay) {
      // Tank Turn
      leftSpeed = steering;
      rightSpeed = -steering;
    } else {
      // Pivot Turn
      if (steering > 0) {
        leftSpeed = steering;
        rightSpeed = 0;
      } else {
        leftSpeed = 0;
        rightSpeed = abs(steering); 
      }
    }
  } 
  else {
    isTurningInPlace = false;
    leftSpeed = 0;
    rightSpeed = 0;
  }

  leftSpeed = constrain(leftSpeed, -255, 255);
  rightSpeed = constrain(rightSpeed, -255, 255);
  driveMotors(leftSpeed, rightSpeed);
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