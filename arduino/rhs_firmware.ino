#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ============================================================
// PIN ASSIGNMENTS
// ============================================================
const int PT1Pin  = A3;       // Pressure sensor 1
const int PT2Pin  = A1;       // Pressure sensor 2
const int Tin     = 2;        // OneWire temperature bus
const int FlowPin = 3;        // Turbine flow sensor (interrupt 1)
const int FPin    = 12;       // Fan
const int SPin    = 13;       // Solenoid

// ============================================================
// PRESSURE SENSOR CONSTANTS
// ============================================================
const float SRMax          = 1024.0;
const float PT1_zero       = 197.0;   // Measured open-air ADC for PT1
const float PT2_zero       = 186.0;   // Measured open-air ADC for PT2
const float PT1_correction = -1.0;    
const float PT2_correction = -1.0;    
const int   PTMax          = 5;
const float mmHg           = 51.715;

// ============================================================
// FLOW SENSOR CONSTANTS — Gems FT-110 173940-C
// ============================================================
const float K_FACTOR            = 1000.0;  // pulses per litre
const float FLOW_MAX_ML_S       = 416.7;   // 25 LPM = 416.7 mL/s (sensor max)
const float FLOW_ZERO_THRESHOLD = 5.0;     // anything below this treated as zero

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
// FLOW RATE CALCULATION
// ============================================================
float calculateFlowRate(unsigned long windowMs) {
    static unsigned long lastCalcTime = 0;
    static float lastFR = 0.0;

    unsigned long now = millis();
    unsigned long interval = now - lastCalcTime;

    if (interval < windowMs) {
        return lastFR;
    }

    noInterrupts();
    unsigned long counts = pulseCount;
    pulseCount = 0;
    interrupts();

    lastCalcTime = now;

    if (counts == 0) {
        lastFR = 0.0;
        return 0.0;
    }

    float newFR = (counts * 1000000.0) / (K_FACTOR * (float)interval);

    if (newFR > FLOW_MAX_ML_S) {
        lastFR = 0.0;
        return 0.0;
    }

    if (newFR < FLOW_ZERO_THRESHOLD) {
        lastFR = 0.0;
        return 0.0;
    }

    lastFR = newFR;
    return newFR;
}

// ============================================================
// PRESSURE READ HELPER
// 8-sample average per channel, hardcoded per-channel zero,
// per-channel correction, clamp negatives to zero
// ============================================================
void readPressure() {
    float raw1 = 0, raw2 = 0;
    for (int i = 0; i < 8; i++) {
        raw1 += analogRead(PT1Pin);
        raw2 += analogRead(PT2Pin);
        delay(1);
    }
    raw1 /= 8.0;
    raw2 /= 8.0;

    PT1 = ((raw1 - PT1_zero) * PTMax) / (SRMax - PT1_zero) * mmHg + PT1_correction;
    PT2 = ((raw2 - PT2_zero) * PTMax) / (SRMax - PT2_zero) * mmHg + PT2_correction;

    if (PT1 < 0) PT1 = 0;
    if (PT2 < 0) PT2 = 0;
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

    pinMode(FlowPin, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(FlowPin), flowPulseISR, FALLING);

    sensors.begin();
    sensors.setWaitForConversion(false);
    if (!sensors.getAddress(sensor1, 0)) { Serial.println("Sensor 1 not found!"); }
    if (!sensors.getAddress(sensor2, 1)) { Serial.println("Sensor 2 not found!"); }
    if (!sensors.getAddress(sensor3, 2)) { Serial.println("Sensor 3 not found!"); }

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

    unsigned long phaseDuration = (unsigned long)(abs(30000.0 / BPM));
    readDelay = (int)(phaseDuration * 0.1);

    // ── SOLENOID OPEN PHASE ──────────────────────────────────
    digitalWrite(FPin, HIGH);
    digitalWrite(SPin, HIGH);

    for (int readCount = 0; readCount < 10; readCount++) {
        unsigned long iterStart = millis();

        readPressure();
        FR = calculateFlowRate(150);
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
        FR = calculateFlowRate(150);
        printSerial();

        unsigned long iterElapsed = millis() - iterStart;
        int adjustedDelay = readDelay - (int)iterElapsed;
        if (readCount < 9 && adjustedDelay > 0) delay(adjustedDelay);
    }
}