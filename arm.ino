#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

const uint8_t SERVO_COUNT = 6;
const uint8_t servoChannel[SERVO_COUNT] = {0, 1, 2, 3, 4, 5};

// Change these if some servos are mounted in reverse direction
const bool invertDir[SERVO_COUNT] = {
  false, false, false, false, false, false
};

// Per-servo angle limits
const int minAngle[SERVO_COUNT] = {0, 0, 0, 0, 0, 0};
const int maxAngle[SERVO_COUNT] = {180, 180, 180, 180, 180, 180};

// Per-servo pulse limits for PCA9685
// You may need to tune these a little for your servos
const uint16_t minPulse[SERVO_COUNT] = {110, 110, 110, 110, 110, 110};
const uint16_t maxPulse[SERVO_COUNT] = {510, 510, 510, 510, 510, 510};

// Safe home position
int homeAngle[SERVO_COUNT] = {90, 90, 90, 90, 90, 90};
int currentAngle[SERVO_COUNT] = {90, 90, 90, 90, 90, 90};

char inputBuffer[100];
uint8_t inputPos = 0;

uint16_t angleToPulse(uint8_t idx, int angle) {
  angle = constrain(angle, minAngle[idx], maxAngle[idx]);

  if (invertDir[idx]) {
    angle = maxAngle[idx] - (angle - minAngle[idx]);
  }

  return map(angle, minAngle[idx], maxAngle[idx], minPulse[idx], maxPulse[idx]);
}

void writeServo(uint8_t idx, int angle) {
  angle = constrain(angle, minAngle[idx], maxAngle[idx]);
  currentAngle[idx] = angle;
  uint16_t pulse = angleToPulse(idx, angle);
  pca.setPWM(servoChannel[idx], 0, pulse);
}

void writeAllServos(const int angles[SERVO_COUNT]) {
  for (uint8_t i = 0; i < SERVO_COUNT; i++) {
    writeServo(i, angles[i]);
  }
}

void goHome() {
  writeAllServos(homeAngle);
}

void sendOk() {
  Serial.println("OK");
}

void sendError(const char* msg) {
  Serial.print("ERR,");
  Serial.println(msg);
}

void parseCommand(char* line) {
  // Command format examples:
  // ALL,90,90,90,90,90,90
  // SET,2,135
  // HOME
  // STOP
  // STATUS

  if (strncmp(line, "ALL,", 4) == 0) {
    int values[SERVO_COUNT];
    uint8_t count = 0;

    char* token = strtok(line + 4, ",");
    while (token != NULL && count < SERVO_COUNT) {
      values[count++] = atoi(token);
      token = strtok(NULL, ",");
    }

    if (count != SERVO_COUNT) {
      sendError("BAD_ALL");
      return;
    }

    writeAllServos(values);
    sendOk();
    return;
  }

  if (strncmp(line, "SET,", 4) == 0) {
    char* token = strtok(line + 4, ",");
    if (token == NULL) {
      sendError("BAD_SET_CH");
      return;
    }
    int ch = atoi(token);

    token = strtok(NULL, ",");
    if (token == NULL) {
      sendError("BAD_SET_ANGLE");
      return;
    }
    int angle = atoi(token);

    if (ch < 0 || ch >= SERVO_COUNT) {
      sendError("SET_RANGE");
      return;
    }

    writeServo((uint8_t)ch, angle);
    sendOk();
    return;
  }

  if (strcmp(line, "HOME") == 0) {
    goHome();
    sendOk();
    return;
  }

  if (strcmp(line, "STOP") == 0) {
    goHome();
    sendOk();
    return;
  }

  if (strcmp(line, "STATUS") == 0) {
    Serial.print("ANGLES,");
    for (uint8_t i = 0; i < SERVO_COUNT; i++) {
      Serial.print(currentAngle[i]);
      if (i < SERVO_COUNT - 1) {
        Serial.print(",");
      }
    }
    Serial.println();
    return;
  }

  sendError("UNKNOWN_CMD");
}

void setup() {
  Serial.begin(115200);
  Wire.begin();

  pca.begin();
  pca.setPWMFreq(50); // standard servo frequency
  delay(500);

  goHome();
  Serial.println("READY");
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\r') {
      continue;
    }

    if (c == '\n') {
      inputBuffer[inputPos] = '\0';
      if (inputPos > 0) {
        parseCommand(inputBuffer);
      }
      inputPos = 0;
      continue;
    }

    if (inputPos < sizeof(inputBuffer) - 1) {
      inputBuffer[inputPos++] = c;
    } else {
      inputPos = 0;
      sendError("LINE_TOO_LONG");
    }
  }
}