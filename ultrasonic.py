import RPi.GPIO as GPIO 
import time 
# GPIO pin assignments 
TRIG = 6  # Trigger pin 
ECHO = 5  # Echo pin 
# Setup 
GPIO.setmode(GPIO.BCM) 
GPIO.setup(TRIG, GPIO.OUT) 
GPIO.setup(ECHO, GPIO.IN) 
def measure_distance(): 
""" 
Measure distance using HC-SR04 ultrasonic sensor 
Returns distance in centimeters 
""" 
# Ensure trigger is low 
GPIO.output(TRIG, False) 
time.sleep(0.1) 
# Send 10us pulse to trigger 
    GPIO.output(TRIG, True) 
    time.sleep(0.00001)  # 10 microseconds 
    GPIO.output(TRIG, False) 
     
    # Wait for echo to start 
    pulse_start = time.time() 
    timeout = pulse_start + 0.1  # 100ms timeout 
     
    while GPIO.input(ECHO) == 0: 
        pulse_start = time.time() 
        if pulse_start > timeout: 
            return None 
     
    # Wait for echo to end 
    pulse_end = time.time() 
    timeout = pulse_end + 0.1 
     
    while GPIO.input(ECHO) == 1: 
        pulse_end = time.time() 
        if pulse_end > timeout: 
            return None 
     
    # Calculate distance 
    pulse_duration = pulse_end - pulse_start 
    distance = pulse_duration * 17150  # Speed of sound = 34300 cm/s (divide 
by 2) 
    distance = round(distance, 2) 
     
    return distance 
 
try: 
    print("Ultrasonic Sensor Distance Measurement") 
    print("Press Ctrl+C to stop") 
    print("-" * 40) 
     
    while True: 
        dist = measure_distance() 
         
        if dist is not None: 
            print(f"Distance: {dist} cm") 
        else: 
            print("Measurement timeout - object too far or sensor error") 
         
        time.sleep(1)  # Wait 1 second between measurements 
 
except KeyboardInterrupt: 
    print("\nMeasurement stopped by user") 
 
finally: 
    GPIO.cleanup() 
    print("GPIO cleanup complete") 