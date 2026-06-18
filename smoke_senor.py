#!/usr/bin/env python3 
""" 
Simple Smoke Detection using ADS1115 Channel 0 
""" 
 
import time 
import board 
import busio 
import adafruit_ads1x15.ads1115 as ADS 
from adafruit_ads1x15.analog_in import AnalogIn 
 
SMOKE_THRESHOLD = 1.5 
 
def main(): 
    i2c = busio.I2C(board.SCL, board.SDA) 
    ads = ADS.ADS1115(i2c, address=0x48) 
    smoke_sensor = AnalogIn(ads, 0) 
     
    print("Smoke Detection Ready") 
     
    try: 
        while True: 
            voltage = max(0, smoke_sensor.voltage) 
            raw_value = max(0, smoke_sensor.value) 
             
            if voltage >= SMOKE_THRESHOLD: 
                print(f"SMOKE DETECTED! {voltage:.3f}V (Raw: {raw_value})") 
            else: 
                print(f"OK - {voltage:.3f}V (Raw: {raw_value})") 
             
            time.sleep(0.5) 
             
    except KeyboardInterrupt: 
        print("\nStopped") 
 
if __name__ == "__main__": 
    main() 