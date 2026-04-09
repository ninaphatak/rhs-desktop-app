#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ============================================================
// PIN ASSIGNMENTS
// ============================================================
const int PT1Pin  = A0;       // Pressure sensor 1
const int PT2Pin  = A1;       // Pressure sensor 2
const int Tin     = 2;        // OneWire temperature bus
const int FlowPin = 3;        // Turbine flow sensor (interrupt 1)
const int FPin    = 12;       // Fan
const int SPin    = 13;       // Solenoid

// ============================================================
// PRESSURE SENSOR CONSTANTS
// ============================================================
const float SRMax = 921.6;
const float SRMin = 102.4;
const int   PTMax = 10;
const float mmHg  = 51.715;

// ============================================================
// FLOW SENSOR CONSTANTS — Gems FT-110 173940-C
// ============================================================
const float K_FACTOR        = 1000.0;  // pulses per litre
const float FLOW_MAX_ML_S   = 416.7;   // 25 LPM = 416.7 mL/s (sensor max)
const float FLOW_ZERO_THRESHOLD = 5.0; // anything below this treated as zero
                                        // eliminates turbine spin-down residual

// ============================================================
// FLOW STATE
// ============================================================
volatile unsigned long pulseCount = 0;
float FR = 0.0;  // mL/s

// ============================================================
// GENERAL VARIABLES
// ============================================================
const int baudRate = 31250;

float PT1 = 0.0;
float PT2 = 0.0;
int   BPM = 80;
int   readDelay = 0;

float VT1 = 0.0;
float VT2 = 0.0;
float AT1 = 0.0;
unsigned long lastTempRead = 0;

// ============================================================
// SENSOR OBJECTS
// ============================================================
OneWire oneWire(Tin);
DallasTemperature sensors(&oneWire);
DeviceAddress sensor1, sensor2, sensor3;
LiquidCrystal_I2C lcd(0x3F, 16, 2);

// ============================================================
// INTERRUPT SERVICE ROUTINE
// ============================================================
void flowPulseISR() {
    pulseCount++;
}

// ============================================================
// FLOW RATE CALCULATION — BPM-synced rolling window
//
// Derivation:
//   Flow (mL/s) = (counts / K_FACTOR) / (interval / 1000)
//               = (counts * 1,000,000) / (K_FACTOR * interval_ms)
//
//   1,000,000 = ms->s (x1000) combined with L->mL (x1000)
//
// Zero threshold eliminates turbine spin-down residual pulses
// that cause false low readings during the closed phase.
// ============================================================
float calculateFlowRate(unsigned long windowMs) {
    static unsigned long lastCalcTime = 0;
    static float lastFR = 0.0;

    unsigned long now = millis();
    unsigned long interval = now - lastCalcTime;

    // Not enough time elapsed — return last stable value
    if (interval < windowMs) {
        return lastFR;
    }

    // Atomically read and reset pulse count
    noInterrupts();
    unsigned long counts = pulseCount;
    pulseCount = 0;
    interrupts();

    lastCalcTime = now;

    // No pulses — flow is zero
    if (counts == 0) {
        lastFR = 0.0;
        return 0.0;
    }

    float newFR = (counts * 1000000.0) / (K_FACTOR * (float)interval);

    // Above sensor max — likely noise, discard
    if (newFR > FLOW_MAX_ML_S) {
        lastFR = 0.0;
        return 0.0;
    }

    // Below zero threshold — turbine spin-down, treat as zero
    if (newFR < FLOW_ZERO_THRESHOLD) {
        lastFR = 0.0;
        return 0.0;
    }

    lastFR = newFR;
    return newFR;
}

// ============================================================
// PRESSURE READ HELPER
// ============================================================
void readPressure() {
    PT1 = analogRead(PT1Pin);
    PT2 = analogRead(PT2Pin);
    PT1 = abs(((PT1 - SRMin) * PTMax) / (SRMax - SRMin)) * mmHg;
    PT2 = abs(((PT2 - SRMin) * PTMax) / (SRMax - SRMin)) * mmHg;
}

// ============================================================
// SERIAL PRINT HELPER
// ============================================================
void printSerial() {
    Serial.print(PT1);  Serial.print(" ");
    Serial.print(PT2);  Serial.print(" ");
    Serial.print(FR);   Serial.print(" ");
    Serial.print(BPM);  Serial.print(" ");
    Serial.print(VT1);  Serial.print(" ");
    Serial.print(VT2);  Serial.print(" ");
    Serial.print(AT1);  Serial.println();
}

// ============================================================
// SETUP
// ============================================================
void setup() {
    Serial.begin(baudRate);
    Wire.setClock(400000);

    lcd.init();
    lcd.clear();
    lcd.backlight();

    pinMode(SPin, OUTPUT);
    pinMode(FPin, OUTPUT);

    // Flow sensor — external 10kΩ pull-up to +5V required on D3
    pinMode(FlowPin, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(FlowPin), flowPulseISR, FALLING);

    // Temperature sensors
    sensors.begin();
    sensors.setWaitForConversion(false);
    if (!sensors.getAddress(sensor1, 0)) { Serial.println("Sensor 1 not found!"); }
    if (!sensors.getAddress(sensor2, 1)) { Serial.println("Sensor 2 not found!"); }
    if (!sensors.getAddress(sensor3, 2)) { Serial.println("Sensor 3 not found!"); }

    // Initial temperature read so values aren't zero at startup
    sensors.requestTemperatures();
    delay(100);
    VT1 = sensors.getTempC(sensor3);
    VT2 = sensors.getTempC(sensor2);
    AT1 = sensors.getTempC(sensor1);
    lastTempRead = millis();
}

// ============================================================
// MAIN LOOP
// ============================================================
void loop() {
    // Non-blocking temperature update every 500ms
    if (millis() - lastTempRead > 500) {
        sensors.requestTemperatures();
        VT1 = sensors.getTempC(sensor3);
        VT2 = sensors.getTempC(sensor2);
        AT1 = sensors.getTempC(sensor1);
        lastTempRead = millis();
    }

    // Calculate phase duration and read delay from BPM
    // At BPM=80: phaseDuration = 375ms, readDelay = 37ms
    unsigned long phaseDuration = (unsigned long)(abs(30000.0 / BPM));
    readDelay = (int)(phaseDuration * 0.1);

    // ── SOLENOID OPEN PHASE ──────────────────────────────────
    digitalWrite(FPin, HIGH);
    digitalWrite(SPin, HIGH);

    for (int readCount = 0; readCount < 10; readCount++) {
        unsigned long iterStart = millis();

        readPressure();
        FR = calculateFlowRate(phaseDuration);
        printSerial();

        unsigned long iterElapsed = millis() - iterStart;
        int adjustedDelay = readDelay - (int)iterElapsed;
        if (readCount < 9 && adjustedDelay > 0) delay(adjustedDelay);
    }

    // ── SOLENOID CLOSED PHASE ────────────────────────────────
    digitalWrite(SPin, LOW);

    for (int readCount = 0; readCount < 10; readCount++) {
        unsigned long iterStart = millis();

        readPressure();
        FR = calculateFlowRate(phaseDuration);
        printSerial();

        unsigned long iterElapsed = millis() - iterStart;
        int adjustedDelay = readDelay - (int)iterElapsed;
        if (readCount < 9 && adjustedDelay > 0) delay(adjustedDelay);
    }
}