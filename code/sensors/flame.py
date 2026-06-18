import RPi.GPIO as GPIO 
import time 
# --- Configuration --- 
FLAME_SENSOR_PIN = 22  # Using GPIO 22 
# --- Setup --- 
GPIO.setmode(GPIO.BCM)  # Use Broadcom pin numbering 
GPIO.setup(FLAME_SENSOR_PIN, GPIO.IN) # Set the pin as an input 
print("Simple Real-Time Digital Read on GPIO 22. Press Ctrl+C to exit.") 
try: 
while True: 
# Read the current state of the pin 
pin_state = GPIO.input(FLAME_SENSOR_PIN) 
# Flame sensors are typically LOW when flame is detected 
if pin_state == GPIO.LOW: 
print("Status: LOW (Flame Detected)") 
else: 
print("Status: HIGH (Flame Clear)") 
# Wait a short time before reading again 
time.sleep(0.1)  
except KeyboardInterrupt: 
print("\nProgram shut down by user.") 
finally: 
# Clean up GPIO settings 
GPIO.cleanup() 
