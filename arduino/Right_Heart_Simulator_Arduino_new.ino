#include <Wire.h> //enables communication with i2c devices
#include <LiquidCrystal_I2C.h> //enables interface with LCD screens

// Declare analog input pins
const int PT1Pin = A0; //analog input pin for pressure transducer 1
const int PT2Pin = A1; //analog input pin for pressure transducer 2
const int FRPin = A2; //analog input pin for flowrate meter
// const int POTPin = A3; //analog pin for potentiometer
// Declare analog output pins 
const int FPin = 12; //analog output pin for fan
const int SPin = 13; //analog output pin for solenoid
// Declare sensor limits
const float SRMax = 921.6; //analog input maximum reading
const float SRMin = 102.4; //analog input minimum reading
const int PTMax = 10; //max value for pressure transducer
const float BPMMax = 180.0; //max value for bpm
const int FRMax = 50; //max value for flowrate meter
const int FRMin = 2; //min value for flowrate meter
// const int POTMax = 960; //max digital reading of potentiometer
// const int POTMin = 70; //min digital reading of potentiometer
// Set baudRate and conversions
const int baudRate = 31250; //baud rate for serial output
const float mmHg = 51.715; //conversion for psi to mmHg
const float mL = 16.6667; //conversion for L/min to mL/s
// Declare sensor reading variables
float PT1 = 0.0; //variable for pressure transducer 1 reading
float PT2 = 0.0; //variable for pressure transducer 2 reading
int FR = 0; //variable for flowrate meter reading
int BPM = 170; //variable for BPM of solenoid
int readDelay = 0; //variable for delay

LiquidCrystal_I2C lcd(0x3F, 16, 2); //LCD I2C initiaition (address, numColumns, numRows)

void setup() {
  Serial.begin(baudRate); //initilize serial output
  Wire.setClock(400000);
  lcd.init(); //initialize LCD screen
  lcd.clear(); //clear LCD screen
  lcd.backlight(); //enable LCD backlight
  pinMode(SPin, OUTPUT); //enable solenoid output pin
  pinMode(FPin, OUTPUT); //enable fan output pin
}

void loop() {
  // Turn on fan and open solenoid
  digitalWrite(FPin, HIGH); //turn on fan
  digitalWrite(SPin, HIGH); //open solenoid valve
  // Sensor read loop
  for (int readCount = 0; readCount < 10; readCount++) {
    // Read all sensors (potentiometer for BPM, PT 1, PT 2, FR)
    // BPM = analogRead(POTPin); //analog input reading for bpm of solenoid
    PT1 = analogRead(PT1Pin); //analog input reading for pressure transducer 1
    PT2 = analogRead(PT2Pin); //analog input reading for pressure transducer 2
    FR = analogRead(FRPin);   // analog input reading for flowrate meter
    // Translate analog readings to digital value for output
    // BPM = ((BPM - POTMin)*BPMMax)/(POTMax-POTMin);                   //convert BPM value
    PT1 = abs(((PT1 - SRMin)*PTMax)/(SRMax-SRMin))*mmHg;             //convert pressure tranducer 1 value
    PT2 = abs(((PT2 - SRMin)*PTMax)/(SRMax-SRMin))*mmHg;             //convert pressure transducer 2 value
    FR = (abs((((FR-SRMin)*(FRMax-FRMin))/(SRMax-SRMin)))+FRMin)*mL; //convert flowrate meter value
    if (FR > 500.0) {
      FR = 0.0;      
    } 
    // Serial output
    Serial.print(PT1);
    Serial.print(" ");
    Serial.print(PT2);
    Serial.print(" ");
    Serial.print(FR);
    Serial.print(" ");
    Serial.print(BPM);
    Serial.println();
    // Determine delay and delay
    readDelay = abs(30.0/BPM)*1000; //calculate readDelay from BPM
    readDelay = 0.1*readDelay; //reduce delay by a factor of 5
    if (readCount<9){       
      delay(readDelay); // delay
      }
  }
  // Close solenoid
  digitalWrite(SPin, LOW); //close valve
  // Output to LCD Screen
  lcd.clear(); //clear LCD screen
  lcd.setCursor(0,0);
  lcd.print("P1:"); 
  lcd.print(PT1);
  lcd.print(" HR");
  lcd.print(BPM);
  lcd.setCursor(0,1);
  lcd.print("P2:");
  lcd.print(PT2);
  lcd.print(" FR");
  lcd.print(FR);
  for (int readCount = 0; readCount < 10; readCount++) {
    // Read all sensors (potentiometer for BPM, PT 1, PT 2, FR)
    // BPM = analogRead(POTPin); //analog input reading for bpm of solenoid
    PT1 = analogRead(PT1Pin); //analog input reading for pressure transducer 1
    PT2 = analogRead(PT2Pin); //analog input reading for pressure transducer 2
    FR = analogRead(FRPin); // analog input reading for flowrate meter
    // Translate analog readings to digital value for output
    // BPM = ((BPM - POTMin)*BPMMax)/(POTMax-POTMin); //convert BPM value
    PT1 = abs(((PT1 - SRMin)*PTMax)/(SRMax-SRMin))*mmHg; //convert pressure tranducer 1 value
    PT2 = abs(((PT2 - SRMin)*PTMax)/(SRMax-SRMin))*mmHg; //convert pressure transducer 2 value
    FR = (abs((((FR-SRMin)*(FRMax-FRMin))/(SRMax-SRMin)))+FRMin)*mL; //convert flowrate meter value
    if (FR > 500.0) {
      FR = 0.0;
    } 
    // Serial output
    Serial.print(PT1);
    Serial.print(" ");
    Serial.print(PT2);
    Serial.print(" ");
    Serial.print(FR);
    Serial.print(" ");
    Serial.print(BPM);
    Serial.println();
    // Determine delay and delay
    readDelay = abs(30.0/BPM)*1000; //calculate readDelay from BPM
    readDelay = 0.1*readDelay; //reduce delay by a factor of 5    
    if (readCount<9){       
      delay(readDelay); // delay
      }
  }
}
