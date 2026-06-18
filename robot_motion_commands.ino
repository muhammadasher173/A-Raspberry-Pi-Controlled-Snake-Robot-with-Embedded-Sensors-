#include <ESP32Servo.h> 
// ========== PIN CONFIGURATION ========== 
const int motorPins[7] = {17, 26, 23, 21, 19, 25, 16}; // M0 to M6 pins 
// ========== SERVO OBJECTS ========== 
Servo motors[7]; 
// ========== MOTOR ANGLES ========== 
int angles[7] = {115, 63, 93, 120, 115, 100, 120}; // Initial angles (M6 is 
camera at 120°) 
int serpentineAngles[7] = {125, 63, 90, 120, 90, 100, 120}; 
float offsets[7] = {115, 63, 93, 120, 115, 100, 120}; // Motion centers 
// ========== MOTION PARAMETERS ========== 
float timeVar = 0; 
const float frequency = 0.5; 
const float serpAmplitude = 15.0; 
const float upliftingHeadAmp = 25.0; 
const float upliftingTailAmp = 15.0; 
// ========== MOTION STATE ========== 
bool robotOn = false; 
bool serpentineMode = false; 
bool upliftingMode = false; 
bool motionDelayActive = false; 
bool turningLeft = false; 
bool turningRight = false; 
float turnBias = 0.0; 
 
// ========== TIMING VARIABLES ========== 
unsigned long previousMillis = 0; 
unsigned long motionStartTime = 0; 
const unsigned long motionStartDelay = 1000;  // Changed to 1 second 
const unsigned long LOOP_INTERVAL = 20; 
unsigned long lastLoopTime = 0; 
 
String robotCommand = "stop"; 
 
// ========== SETUP ========== 
void setup() { 
  // Initialize USB Serial 
  Serial.begin(115200); 
  while (!Serial && millis() < 3000) { 
    ; // Wait for USB Serial to connect (max 3 seconds) 
  } 
   
  // Initialize TTL Serial2 (RX=5, TX=18) 
  Serial2.begin(9600, SERIAL_8N1, 5, 18); 
   
  // Small delay for serial to stabilize 
  delay(100); 
   
  // Attach all servos 
  for(int i = 0; i < 7; i++) { 
    motors[i].attach(motorPins[i]); 
    motors[i].write(angles[i]); 
  } 
   
  printWelcomeMessage(); 
   
  // Confirm both serials are active 
  Serial.println("USB Serial ready on 115200 baud"); 
  Serial2.println("TTL Serial2 ready on 9600 baud"); 
} 
 
void printWelcomeMessage() { 
  String message = "\n========== Snake Robot Dual Serial Control 
==========\n"; 
  message += "USB Serial: 115200 baud | TTL Serial2: 9600 baud (RX=5, 
TX=18)\n"; 
  message += "Commands:\n"; 
  message += "1 - Turn Robot ON\n"; 
  message += "2 - Serpentine Movement\n"; 
  message += "3 - Uplifting Movement\n"; 
  message += "4 - Turn Left\n"; 
  message += "5 - Turn Right\n"; 
  message += "6 - Stop Movement\n"; 
  message += "7 - Turn Robot OFF\n"; 
  message += "8 - Reset to Initial Position\n"; 
  message += "=====================================================\n"; 
   
  Serial.println(message); 
  Serial2.println(message); 
} 
 
// ========== MAIN LOOP ========== 
void loop() { 
  unsigned long currentTime = millis(); 
   
  // Process serial commands from both interfaces 
  processSerialCommand(); 
   
  // Handle motion delay 
  if (motionDelayActive) { 
    if (currentTime - motionStartTime >= motionStartDelay) { 
      motionDelayActive = false; 
      sendToBoth("Motion started."); 
    } else { 
      return; 
    } 
  } 
   
  // Execute movements at specified intervals 
  if (currentTime - lastLoopTime >= LOOP_INTERVAL) { 
    lastLoopTime = currentTime; 
     
    if (serpentineMode) serpentineMotion(); 
    if (upliftingMode) upliftingMotion(); 
  } 
} 
 
// ========== DUAL SERIAL HELPER ========== 
void sendToBoth(String message) { 
  Serial.println(message); 
  Serial2.println(message); 
} 
 
// ========== COMMAND HANDLER ========== 
void handleCommand(char command) { 
  switch (command) { 
    case '1': 
      toggleRobot(true); 
      break; 
    case '2': 
      serpentineMovement(); 
      break; 
    case '3': 
      upliftingMovement(); 
      break; 
    case '4': 
      turnLeft(); 
      break; 
    case '5': 
      turnRight(); 
      break; 
    case '6': 
      stopMoving(); 
      break; 
    case '7': 
      toggleRobot(false); 
      break; 
    case '8': 
      resetToInitialPosition(); 
      break; 
    default: 
      // Ignore unknown commands 
      break; 
  } 
} 
 
// ========== ROBOT CONTROL FUNCTIONS ========== 
void toggleRobot(bool on) { 
  robotOn = on; 
  sendToBoth("Robot power: " + String(on ? "ON" : "OFF")); 
   
  if (!on) { 
    stopMoving(); 
    robotCommand = "stop"; 
     
    // Detach servos to save power 
    for(int i = 0; i < 7; i++) motors[i].detach(); 
  } else { 
    // Reattach servos when turning ON 
    for(int i = 0; i < 7; i++) { 
      motors[i].attach(motorPins[i]); 
      motors[i].write(angles[i]); 
    } 
  } 
} 
 
void serpentineMovement() { 
  if (!robotOn) { 
    sendToBoth("Error: Robot is OFF. Send '1' to turn ON first."); 
    return; 
  } 
   
  serpentineMode = true; 
  upliftingMode = false; 
  motionStartTime = millis(); 
  motionDelayActive = true; 
  timeVar = 0; 
   
  // Move to initial position first 
  sendToBoth("Moving to initial position..."); 
  for (int i = 0; i < 7; i++) { 
    motors[i].write(angles[i]); 
  } 
   
  // Wait a moment for servos to reach position 
  delay(500); 
   
  // Set serpentine-specific angles for uplifting motors (0, 2, 4, 6) 
  motors[0].write(serpentineAngles[0]); 
  motors[2].write(serpentineAngles[2]); 
  motors[4].write(serpentineAngles[4]); 
  motors[6].write(serpentineAngles[6]); 
   
  // Update offsets 
  offsets[0] = serpentineAngles[0]; 
  offsets[2] = serpentineAngles[2]; 
  offsets[4] = serpentineAngles[4]; 
  offsets[6] = serpentineAngles[6]; 
  offsets[1] = angles[1]; 
  offsets[3] = angles[3]; 
  offsets[5] = angles[5]; 
   
  sendToBoth("Serpentine mode activated. Starting in 1 second..."); 
} 
 
void upliftingMovement() { 
  if (!robotOn) { 
    sendToBoth("Error: Robot is OFF. Send '1' to turn ON first."); 
    return; 
  } 
   
  upliftingMode = true; 
  serpentineMode = false; 
  motionStartTime = millis(); 
  motionDelayActive = true; 
  timeVar = 0; 
   
  // Move to initial position first 
  sendToBoth("Moving to initial position..."); 
  for (int i = 0; i < 7; i++) { 
    motors[i].write(angles[i]); 
    offsets[i] = angles[i]; 
  } 
   
  sendToBoth("Uplifting mode activated. Starting in 1 second..."); 
} 
 
void turnLeft() { 
  if (!robotOn) { 
    sendToBoth("Error: Robot is OFF. Send '1' to turn ON first."); 
    return; 
  } 
   
  sendToBoth("Turning left - serpentine with left bias"); 
   
  serpentineMode = true; 
  upliftingMode = false; 
  turningLeft = true; 
  turningRight = false; 
  turnBias = -20.0; 
  motionStartTime = millis(); 
  motionDelayActive = true; 
  timeVar = 0; 
   
  // Move to initial position first 
  sendToBoth("Moving to initial position..."); 
  for (int i = 0; i < 7; i++) { 
    motors[i].write(angles[i]); 
  } 
   
  // Wait a moment for servos to reach position 
  delay(500); 
   
  // Set serpentine angles for uplifting motors (0, 2, 4, 6) 
  motors[0].write(serpentineAngles[0]); 
  motors[2].write(serpentineAngles[2]); 
  motors[4].write(serpentineAngles[4]); 
  motors[6].write(serpentineAngles[6]); 
   
  offsets[0] = serpentineAngles[0]; 
  offsets[2] = serpentineAngles[2]; 
  offsets[4] = serpentineAngles[4]; 
  offsets[6] = serpentineAngles[6]; 
  offsets[1] = angles[1]; 
  offsets[3] = angles[3]; 
  offsets[5] = angles[5]; 
   
  robotCommand = "left"; 
  sendToBoth("Starting left turn in 1 second..."); 
} 
 
void turnRight() { 
  if (!robotOn) { 
    sendToBoth("Error: Robot is OFF. Send '1' to turn ON first."); 
    return; 
  } 
   
  sendToBoth("Turning right - serpentine with right bias"); 
   
  serpentineMode = true; 
  upliftingMode = false; 
  turningLeft = false; 
  turningRight = true; 
  turnBias = 20.0; 
  motionStartTime = millis(); 
  motionDelayActive = true; 
  timeVar = 0; 
   
  // Move to initial position first 
  sendToBoth("Moving to initial position..."); 
  for (int i = 0; i < 7; i++) { 
    motors[i].write(angles[i]); 
  } 
   
  // Wait a moment for servos to reach position 
  delay(500); 
   
  // Set serpentine angles for uplifting motors (0, 2, 4, 6) 
  motors[0].write(serpentineAngles[0]); 
  motors[2].write(serpentineAngles[2]); 
  motors[4].write(serpentineAngles[4]); 
  motors[6].write(serpentineAngles[6]); 
   
  offsets[0] = serpentineAngles[0]; 
  offsets[2] = serpentineAngles[2]; 
  offsets[4] = serpentineAngles[4]; 
  offsets[6] = serpentineAngles[6]; 
  offsets[1] = angles[1]; 
  offsets[3] = angles[3]; 
  offsets[5] = angles[5]; 
   
  robotCommand = "right"; 
  sendToBoth("Starting right turn in 1 second..."); 
} 
 
void stopMoving() { 
  sendToBoth("Stopping all movement"); 
   
  serpentineMode = false; 
  upliftingMode = false; 
  motionDelayActive = false; 
  turningLeft = false; 
  turningRight = false; 
  turnBias = 0.0; 
} 
 
void resetToInitialPosition() { 
  if (!robotOn) { 
    sendToBoth("Error: Robot is OFF. Send '1' to turn ON first."); 
    return; 
  } 
   
  sendToBoth("Resetting to initial positions"); 
   
  stopMoving(); 
   
  for (int i = 0; i < 7; i++) { 
    motors[i].write(angles[i]); 
    offsets[i] = angles[i]; 
  } 
   
  sendToBoth("Reset complete"); 
} 
 
// ========== MOTION FUNCTIONS ========== 
void serpentineMotion() { 
  unsigned long currentMillis = millis(); 
   
  if (currentMillis - previousMillis >= 20) { 
    previousMillis = currentMillis; 
     
    // Apply turn bias 
    float bias1 = turningLeft ? turnBias * 0.5 : (turningRight ? turnBias * 
0.5 : 0); 
    float bias3 = turningLeft ? turnBias * 0.7 : (turningRight ? turnBias * 
0.7 : 0); 
    float bias5 = turningLeft ? turnBias * 1.0 : (turningRight ? turnBias * 
1.0 : 0); 
    float bias6 = turningLeft ? turnBias * 1.2 : (turningRight ? turnBias * 
1.2 : 0); 
     
    // Move serpentine motors (1, 3, 5, 6) in wave pattern 
    motors[1].write(constrain(offsets[1] + serpAmplitude * sin(timeVar + 0) 
+ bias1, 0, 180)); 
    motors[3].write(constrain(offsets[3] + serpAmplitude * sin(timeVar + PI 
/ 3) + bias3, 0, 180)); 
    motors[5].write(constrain(offsets[5] + serpAmplitude * sin(timeVar + 2 * 
PI / 3) + bias5, 0, 180)); 
    motors[6].write(constrain(offsets[6] + serpAmplitude * sin(timeVar + PI) 
+ bias6, 0, 180)); 
     
    timeVar += (2 * PI * frequency * 20 / 1000.0); 
  } 
} 
 
void upliftingMotion() { 
  unsigned long currentMillis = millis(); 
   
  if (currentMillis - previousMillis >= 20) { 
    previousMillis = currentMillis; 
     
    // Move uplifting motors (0, 2, 4) in wave pattern - Motor 6 stays fixed 
    float angle0 = upliftingHeadAmp * sin(timeVar) + offsets[0] + 10; 
    float angle2 = upliftingTailAmp * sin(timeVar + PI / 3) + offsets[2]; 
    float angle4 = upliftingTailAmp * sin(timeVar + 2 * PI / 3) + 
offsets[4]; 
     
    motors[0].write(constrain(angle0, 40, 160)); 
    motors[2].write(constrain(angle2, 30, 150)); 
    motors[4].write(constrain(angle4, 30, 150)); 
    // Motor 6 stays at offsets[6] - no movement 
     
    timeVar += (2 * PI * frequency * 20 / 1000.0); 
  } 
} 
 
// ========== SERIAL COMMAND FUNCTIONS ========== 
void processSerialCommand() { 
  // -------- USB SERIAL ------- 
  if (Serial.available()) { 
    char cmd = Serial.read(); 
    if (cmd == '\n' || cmd == '\r') return;  // ignore noise 
    handleCommand(cmd); 
  } 
   
  // -------- TTL SERIAL2 ------- 
  if (Serial2.available()) { 
    char cmd = Serial2.read(); 
    if (cmd == '\n' || cmd == '\r') return;  // ignore noise 
    handleCommand(cmd); 
  } 
} 
 
void showHelp() { 
  printWelcomeMessage(); 
}