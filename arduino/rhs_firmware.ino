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
const int Tin = 2; // Digital input pin for all temperature sensors
// Declare analog output pins
const int FPin = 12;
const int SPin = 13;
// Declare sensor limits
const float SRMax = 921.6;
const float SRMin = 102.4;
const int PTMax = 5;
// const float BPMMax = 180.0;
const int FRMax = 50;
const int FRMin = 2;
// const int POTMax = 960;
// const int POTMin = 70;
// Set baudRate and conversions
const int baudRate = 31250;
const float mmHg = 51.715;
const float mL = 16.6667;
// Declare sensor reading variables
float PT1 = 0.0;
float PT2 = 0.0;
int FR = 0;
int BPM = 60;
int readDelay = 0;
// Declare temperature variables
float VT1 = 0.0;
float VT2 = 0.0;
float AT1 = 0.0;

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

    // Initialize temperature sensors
    sensors.begin();
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
}

void loop()
{
    // Request temperature readings from all 3 sensors
    sensors.requestTemperatures();
    VT1 = sensors.getTempC(sensor1);
    VT2 = sensors.getTempC(sensor2);
    AT1 = sensors.getTempC(sensor3);

    // Turn on fan and open solenoid
    digitalWrite(FPin, HIGH);
    digitalWrite(SPin, HIGH);

    // Sensor read loop - solenoid open phase
    for (int readCount = 0; readCount < 10; readCount++)
    {
        // BPM = analogRead(POTPin);
        PT1 = analogRead(PT1Pin);
        PT2 = analogRead(PT2Pin);
        FR = analogRead(FRPin);

        // BPM = ((BPM - POTMin)*BPMMax)/(POTMax-POTMin);
        PT1 = abs(((PT1 - SRMin) * PTMax) / (SRMax - SRMin)) * mmHg;
        PT2 = abs(((PT2 - SRMin) * PTMax) / (SRMax - SRMin)) * mmHg;
        FR = (abs((((FR - SRMin) * (FRMax - FRMin)) / (SRMax - SRMin))) + FRMin) * mL;

        // Serial output (added T1, T2, T3)
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
        if (readCount < 9)
        {
            delay(readDelay);
        }
    }

    // Close solenoid
    digitalWrite(SPin, LOW);

    // Output to LCD Screen
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("P1:");
    lcd.print(PT1);
    lcd.print(" HR");
    lcd.print(BPM);
    lcd.setCursor(0, 1);
    lcd.print("P2:");
    lcd.print(PT2);
    lcd.print(" FR");
    lcd.print(FR);

    // Sensor read loop - solenoid closed phase
    for (int readCount = 0; readCount < 10; readCount++)
    {
        // BPM = analogRead(POTPin);
        PT1 = analogRead(PT1Pin);
        PT2 = analogRead(PT2Pin);
        FR = analogRead(FRPin);

        // BPM = ((BPM - POTMin)*BPMMax)/(POTMax-POTMin);
        PT1 = abs(((PT1 - SRMin) * PTMax) / (SRMax - SRMin)) * mmHg;
        PT2 = abs(((PT2 - SRMin) * PTMax) / (SRMax - SRMin)) * mmHg;
        FR = (abs((((FR - SRMin) * (FRMax - FRMin)) / (SRMax - SRMin))) + FRMin) * mL;
        if (FR > 500.0)
        {
            FR = 0.0;
        }

        // Serial output (added T1, T2, T3)
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
        if (readCount < 9)
        {
            delay(readDelay);
        }
    }
}