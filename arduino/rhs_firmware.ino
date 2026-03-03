#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// Declare analog input pins
const int PT1Pin = A0;
const int PT2Pin = A1;
const int FRPin = A2;
// const int POTPin = A3;
// Declare digital input pins
const int Tin = 2;
// Declare analog output pins
const int FPin = 12;
const int SPin = 13;
// Declare sensor limits
const float SRMax = 921.6;
const float SRMin = 102.4;
const int PTMax = 5;
const int FRMax = 50;
const int FRMin = 2;
// Set baudRate and conversions
const int baudRate = 31250;
const float mmHg = 51.715;
const float mL = 16.6667;
// Declare sensor reading variables
float PT1 = 0.0;
float PT2 = 0.0;
int FR = 0;
int BPM = 130;
int readDelay = 0;
// Declare temperature variables
float VT1 = 0.0;
float VT2 = 0.0;
float AT1 = 0.0;
unsigned long lastTempRead = 0;

// Temperature sensor setup
OneWire oneWire(Tin);
DallasTemperature sensors(&oneWire);
DeviceAddress sensor1, sensor2, sensor3;

LiquidCrystal_I2C lcd(0x3F, 16, 2);

void setup()
{
    Serial.begin(baudRate);
    Wire.setClock(400000);
    lcd.init();
    lcd.clear();
    lcd.backlight();
    pinMode(SPin, OUTPUT);
    pinMode(FPin, OUTPUT);

    sensors.begin();
    sensors.setWaitForConversion(false);
    if (!sensors.getAddress(sensor1, 0))
    {
        Serial.println("Sensor 1 not found!");
    }
    if (!sensors.getAddress(sensor2, 1))
    {
        Serial.println("Sensor 2 not found!");
    }
    if (!sensors.getAddress(sensor3, 2))
    {
        Serial.println("Sensor 3 not found!");
    }

    // Initial temperature read so values aren't zero at startup
    sensors.requestTemperatures();
    delay(100);
    VT1 = sensors.getTempC(sensor3);
    VT2 = sensors.getTempC(sensor2);
    AT1 = sensors.getTempC(sensor1);
    lastTempRead = millis();
}

void loop()
{
    // Update temperatures every 500ms, non-blocking
    if (millis() - lastTempRead > 500)
    {
        sensors.requestTemperatures();
        VT1 = sensors.getTempC(sensor3);
        VT2 = sensors.getTempC(sensor2);
        AT1 = sensors.getTempC(sensor1);
        lastTempRead = millis();
    }

    digitalWrite(FPin, HIGH);
    digitalWrite(SPin, HIGH);

    for (int readCount = 0; readCount < 10; readCount++)
    {
        unsigned long iterStart = millis();

        PT1 = analogRead(PT1Pin);
        PT2 = analogRead(PT2Pin);
        FR = analogRead(FRPin);

        PT1 = abs(((PT1 - SRMin) * PTMax) / (SRMax - SRMin)) * mmHg;
        PT2 = abs(((PT2 - SRMin) * PTMax) / (SRMax - SRMin)) * mmHg;
        FR = (abs((((FR - SRMin) * (FRMax - FRMin)) / (SRMax - SRMin))) + FRMin) * mL;

        Serial.print(PT1);
        Serial.print(" ");
        Serial.print(PT2);
        Serial.print(" ");
        Serial.print(FR);
        Serial.print(" ");
        Serial.print(BPM);
        Serial.print(" ");
        Serial.print(VT1);
        Serial.print(" ");
        Serial.print(VT2);
        Serial.print(" ");
        Serial.print(AT1);
        Serial.println();

        readDelay = abs(30.0 / BPM) * 1000;
        readDelay = 0.1 * readDelay;

        unsigned long iterElapsed = millis() - iterStart;
        int adjustedDelay = readDelay - (int)iterElapsed;
        if (readCount < 9 && adjustedDelay > 0)
        {
            delay(adjustedDelay);
        }
    }

    digitalWrite(SPin, LOW);

    // lcd.clear();
    // lcd.setCursor(0,0);
    // lcd.print("P1:"); lcd.print(PT1);
    // lcd.print(" HR"); lcd.print(BPM);
    // lcd.setCursor(0,1);
    // lcd.print("P2:"); lcd.print(PT2);
    // lcd.print(" FR"); lcd.print(FR);

    for (int readCount = 0; readCount < 10; readCount++)
    {
        unsigned long iterStart = millis();

        PT1 = analogRead(PT1Pin);
        PT2 = analogRead(PT2Pin);
        FR = analogRead(FRPin);

        PT1 = abs(((PT1 - SRMin) * PTMax) / (SRMax - SRMin)) * mmHg;
        PT2 = abs(((PT2 - SRMin) * PTMax) / (SRMax - SRMin)) * mmHg;
        FR = (abs((((FR - SRMin) * (FRMax - FRMin)) / (SRMax - SRMin))) + FRMin) * mL;
        if (FR > 500.0)
        {
            FR = 0.0;
        }

        Serial.print(PT1);
        Serial.print(" ");
        Serial.print(PT2);
        Serial.print(" ");
        Serial.print(FR);
        Serial.print(" ");
        Serial.print(BPM);
        Serial.print(" ");
        Serial.print(VT1);
        Serial.print(" ");
        Serial.print(VT2);
        Serial.print(" ");
        Serial.print(AT1);
        Serial.println();

        readDelay = abs(30.0 / BPM) * 1000;
        readDelay = 0.1 * readDelay;

        unsigned long iterElapsed = millis() - iterStart;
        int adjustedDelay = readDelay - (int)iterElapsed;
        if (readCount < 9 && adjustedDelay > 0)
        {
            delay(adjustedDelay);
        }
    }
}