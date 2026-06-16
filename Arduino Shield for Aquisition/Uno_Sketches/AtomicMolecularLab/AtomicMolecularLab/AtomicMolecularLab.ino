#define precisionVref 1.024
const int MAX_MEASUREMENTS = 200;  // Adjustable maximum number of measurements for averaging

// Pin definitions
const int backLightPin = 3;       // PWM output for backlight
const int backLightSwitchPin = 2; // Switch pin for backlight toggle
const int softSerialTxPin = A1;   // TX pin for SoftwareSerial
const int softSerialRxPin = A0;   // RX pin for SoftwareSerial
int analogReadPin = A2;           // Pin for analog read

//Pulse Train Detection
#define TIMEOUT_THRESHOLD 1000   // Timeout in microseconds, adjust as needed
#define PIN_TO_POLL 11          // Pin for detecting the pulse train
unsigned long lastPulseTime = 0;    // Stores the last pulse time
unsigned long currentTime = 0;      // To store the current time
bool pulseActive = false;           // Keeps track if pulse is detected
bool lastPinState = HIGH;           // To detect changes in pin state
bool trig = false;                  // Free run if false, triggered if true

// Voltage reference
double referenceVoltage = precisionVref;

// Debounce and delay
const int debounceTime = 100;     // Debounce time in ms
long acquisitionDelay = 25;       // Acquisition delay in ms

// Control flags
bool run = false;
bool precisionRef = true;
bool echoEnabled = false;

// Serial settings
char softwareSerialTerminator = '\r';
char hardwareSerialTerminator = '\n';
String serialBuffer = "";

// Measurement-related variables
int numMeasurementsToAverage = 1;  // Default to 1 measurement for averaging
long measurementSum = 0;           // Store sum of raw ADC measurements (as integers)
int measurements[MAX_MEASUREMENTS];  // Array to store raw ADC measurements
int measurementIndex = 0;          // Current index in the measurement array

// Timing constants
const int ADC_MAX_VALUE = 1023;    // Max value for ADC
const unsigned long LOW_TIME_MICROS = 600;  // Low time duration for pulses
const unsigned long HIGH_TIME_MICROS = 200; // High time duration for pulses

#include <SoftwareSerial.h>
SoftwareSerial mySerial(softSerialTxPin, softSerialRxPin);  // Software serial on specified pins

// Setup function
void setup() {
  // Initialize hardware serial
  Serial.begin(115200);
  Serial.println("Modern Lab Data Aquistion Shield");

  // Initialize software serial
  mySerial.begin(9600);

  // Set up pin modes
  analogReference(EXTERNAL);
  pinMode(backLightSwitchPin, INPUT_PULLUP);
  pinMode(analogReadPin, INPUT);
  pinMode(PIN_TO_POLL, INPUT);
  pinMode(backLightPin, OUTPUT);

}

// Function to measure analog value (raw 10-bit ADC result)
int measureRaw() {
  return analogRead(analogReadPin);
}

// Function to output pulses on step pin
void outputPulses(int pulseCount) {
  for (int i = 0; i < pulseCount; i++) {
    // Set pin to output low (ground)
    digitalWrite(PIN_TO_POLL, LOW);
    pinMode(PIN_TO_POLL, OUTPUT);
    delayMicroseconds(LOW_TIME_MICROS);  // Low time duration

    // Set pin back to high impedance (input mode)
    pinMode(PIN_TO_POLL, INPUT);
    delayMicroseconds(HIGH_TIME_MICROS);  // High time duration
  }
}

// Function to handle steps and pulses
void steps(int steps) {
  for(int i = 0; i < steps; ++i) {
    Serial.println(1);
    outputPulses(6);
  }
  Serial.println(0);
}

// Function to convert raw ADC value to scaled voltage
double convertToVoltage(int rawValue) {
  double scalingFactor = precisionRef ? referenceVoltage : 5.0;
  return (rawValue / (double)ADC_MAX_VALUE) * scalingFactor;
}

// Function to print command list
void printCommandList() {
  const char* commands[][2] = {
    {"delay:", "Sets the acquisition delay in seconds"},
    {"LF", "Sets the software serial terminator to line feed"},
    {"CR", "Sets the software serial terminator to carriage return"},
    {"atod", "Conducts an analog read and sends the result"},
    {"read", "Conducts a measurement and sends the result"},
    {"run", "Starts continuous measurements"},
    {"stop", "Stops continuous measurements"},
    {"Vref", "Sets precisionRef to true and uses external reference voltage"},
    {"10x", "Sets gain to 10x"},
    {"1x", "Sets gain to 1x"},
    {"PwrRef", "Sets precisionRef to false and uses internal 5V reference"},
    {"baud:", "Sets the software serial baud rate to the specified value"},
    {"echo on", "Enables echoing of received commands back to hardware serial"},
    {"echo off", "Disables echoing of received commands back to hardware serial"},
    {"idn?", "Prints this list of commands and descriptions"},
    {"<integer>", "Outputs specified number of pulses on step pin"}
  };

  for (int i = 0; i < sizeof(commands) / sizeof(commands[0]); i++) {
    Serial.print(commands[i][0]);
    Serial.print(" ");
    Serial.println(commands[i][1]);
  }

  Serial.print(hardwareSerialTerminator);
}

// Function to perform multiple measurements and return the average (as voltage)
double acquireMeasurementAverage() {
  measurementSum = 0;  // Reset the sum
  for (int i = 0; i < numMeasurementsToAverage; i++) {
    int rawMeasurement = measureRaw();  // Get the raw ADC measurement
    measurementSum += rawMeasurement;   // Accumulate the sum
  }

  // Calculate and return the average voltage
  double averageRaw = (double)measurementSum / numMeasurementsToAverage;
  return convertToVoltage(averageRaw);
}

// Function to handle the read command, taking the average of set number of measurements
void handleReadCommand() {
  double averageMeasurement = acquireMeasurementAverage();

  Serial.print(millis());
  Serial.print(" ");
  Serial.print(averageMeasurement * 1000, 2);  // Print in millivolts
  Serial.print(hardwareSerialTerminator);
}

// Modify the parse function to call handleReadCommand for the "read" command
void parse(String buffer) {
  buffer.trim(); // Remove any leading or trailing whitespace

  if (buffer.startsWith("avg:")) {
    String numberStr = buffer.substring(4);  // Get the number part after avg
    numberStr.trim();
    int num = numberStr.toInt();  // Convert to an integer
    if (num >= 1 && num <= MAX_MEASUREMENTS) {  // Use MAX_MEASUREMENTS for validation
      numMeasurementsToAverage = num;
      measurementSum = 0;  // Reset the sum and index
      measurementIndex = 0;
      for (int i = 0; i < numMeasurementsToAverage; i++) {
        measurements[i] = 0;  // Reset the measurement array
      }
      Serial.print("Averaging ");
      Serial.print(numMeasurementsToAverage);
      Serial.println(" measurements");
    } else {
      Serial.println("Invalid number for avg, must be between 1 and " + String(MAX_MEASUREMENTS));
    }
  } else if (buffer.startsWith("delay:")) {
    String numberStr = buffer.substring(6);
    numberStr.trim();
    float seconds = numberStr.toFloat();
    acquisitionDelay = (long)(seconds * 1000);
  } else if (buffer == "LF") {
    softwareSerialTerminator = '\n';
  } else if (buffer == "CR") {
    softwareSerialTerminator = '\r';
  } else if (buffer == "atod") {
    int analogValue = analogRead(analogReadPin);
    Serial.print(analogValue);
    Serial.print(hardwareSerialTerminator);
  } else if (buffer == "read") {
    handleReadCommand();  // Updated to take multiple measurements and return the average
  } else if (buffer == "run") {
    run = true;
  } else if (buffer == "stop") {
    run = false;
  } else if (buffer == "Vref") {
    precisionRef = true;
    analogReference(EXTERNAL);
    Serial.println("Vref");
  } else if (buffer == "PwrRef") {
    precisionRef = false;
    analogReference(DEFAULT);
    Serial.println("PwrRef");
  } else if (buffer == "idn?") {
    printCommandList();
  } else if (buffer.startsWith("baud:")) {
    String baudStr = buffer.substring(5);
    baudStr.trim();
    int baudRate = baudStr.toInt();
    mySerial.end();
    mySerial.begin(baudRate);
  } else if (buffer == "echo on") {
    echoEnabled = true;
  } else if (buffer == "echo off") {
    echoEnabled = false;
  } else if (buffer == "10x") {
    analogReadPin = A3;
    Serial.println("Gain 10x");
  } else if (buffer == "1x") {
    analogReadPin = A2;
    Serial.println("Gain 1x");

  // **New part for handling trig commands**
  } else if (buffer == "trig:1") {
    trig = true;  // Set the global variable trig to true
  } else if (buffer == "trig:0") {
    trig = false;  // Set the global variable trig to false
  } else if (buffer == "trig") {
    trig = !trig;  // Toggle the trig value
  } else if(buffer.toInt() > 0) { // Check if the buffer is an integer
        int stepCount = buffer.toInt();
      if (stepCount > 0) {
      steps(stepCount);
      }
    } 
  else mySerial.print(buffer + softwareSerialTerminator);


  if (echoEnabled) {
    Serial.print(buffer);
    Serial.print(hardwareSerialTerminator);
  }
}


// Function to perform a single measurement and output result
void acquireMeasurement() {
  int rawMeasurement = measureRaw();  // Get the raw ADC measurement

  // Update the running sum and replace the oldest measurement
  measurementSum -= measurements[measurementIndex];  // Subtract the old value
  measurements[measurementIndex] = rawMeasurement;   // Store new measurement
  measurementSum += rawMeasurement;  // Add the new value

  // Update the index in a circular manner
  measurementIndex = (measurementIndex + 1) % numMeasurementsToAverage;

  // Calculate the running average
  double runningAverage = (double)measurementSum / numMeasurementsToAverage;
  double scaledAverage = convertToVoltage(runningAverage);

  Serial.print(millis());
  Serial.print(" ");
  Serial.print(scaledAverage * 1000, 2);  // Print in millivolts
  Serial.print(hardwareSerialTerminator);

  delay(acquisitionDelay);
}

bool runCheck() {
  // Read the current pin state (HIGH or LOW)
  bool currentPinState = digitalRead(PIN_TO_POLL);
  currentTime = micros();  // Get the current time

  // Detect the falling edge (HIGH to LOW transition)
  if (lastPinState == HIGH && currentPinState == LOW) {
    pulseActive = true;    // Pulse detected
    lastPulseTime = currentTime;  // Record the time of the falling edge
  }

  // Update lastPinState for the next loop iteration
  lastPinState = currentPinState;

  // If a pulse was detected, check for pulse train timeout
  if (pulseActive) {
    // Check if the time since the last pulse exceeds the threshold
    if (currentTime - lastPulseTime > TIMEOUT_THRESHOLD) {
      // Handle the pulse train stopped case
      pulseActive = false;  // Reset pulse detection
    }
  }

  if(run) {
    if(!trig) return true;
    else if(pulseActive) return true;
    else return false;
  }
  else return false;
}


// Function to handle runtime operations
void runTime() {

  if (runCheck()) acquireMeasurement();

  // Read data from hardware serial
  while (Serial.available()) {
    char c = Serial.read();
    if (c == hardwareSerialTerminator) {
      parse(serialBuffer);
      serialBuffer = "";
    } else {
      serialBuffer += c;
    }
  }

  // Read data from software serial
  while (mySerial.available()) {
    char c = mySerial.read();
    if (c == softwareSerialTerminator) {
      Serial.print(hardwareSerialTerminator);
    } else {
      Serial.print(c);
    }
  }
}

// Main loop
void loop() {
  runTime();

  // Toggle backlight when the switch is pressed
  if (!digitalRead(backLightSwitchPin)) {
    digitalWrite(backLightPin, !digitalRead(backLightPin));
    while (!digitalRead(backLightSwitchPin)) runTime();  // Wait for button release
  }
}
