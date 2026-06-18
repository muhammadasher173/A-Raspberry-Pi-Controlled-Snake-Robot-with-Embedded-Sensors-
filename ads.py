#!/usr/bin/env python3 
""" 
ADS1115 ADC Reader with Automatic Address Detection 
Reads analog values from all 4 channels of the ADS1115 
""" 
 
import time 
import board 
import busio 
import adafruit_ads1x15.ads1115 as ADS 
from adafruit_ads1x15.analog_in import AnalogIn 
 
def scan_i2c_bus(i2c): 
    """Scan I2C bus for devices and return list of addresses""" 
    print("Scanning I2C bus...") 
    devices = [] 
    for addr in range(0x08, 0x78):  # Valid I2C address range 
        try: 
            while not i2c.try_lock(): 
                pass 
            i2c.writeto(addr, b'') 
            devices.append(addr) 
            print(f"  Found device at: 0x{addr:02X}") 
        except: 
            pass 
        finally: 
            i2c.unlock() 
    return devices 
 
def find_ads1115(devices): 
    """Find ADS1115 device from list of I2C addresses""" 
    # Common ADS1115 addresses: 0x48, 0x49, 0x4A, 0x4B 
    ads_addresses = [0x48, 0x49, 0x4A, 0x4B] 
     
    for addr in ads_addresses: 
        if addr in devices: 
            return addr 
     
    # If no common address found, return first device 
    return devices[0] if devices else None 
 
def main(): 
    print("=" * 50) 
    print("ADS1115 ADC Reader with Address Detection") 
    print("=" * 50) 
     
    # Initialize I2C bus 
    i2c = busio.I2C(board.SCL, board.SDA) 
     
    # Scan for devices 
    devices = scan_i2c_bus(i2c) 
     
    if not devices: 
        print("\nERROR: No I2C devices found!") 
        print("Check your connections:") 
        print("  - VDD -> 3.3V or 5V") 
        print("  - GND -> Ground") 
        print("  - SCL -> GPIO 3 (SCL)") 
        print("  - SDA -> GPIO 2 (SDA)") 
        return 
     
    # Find ADS1115 
    ads_addr = find_ads1115(devices) 
    print(f"\nUsing ADS1115 at address: 0x{ads_addr:02X}") 
     
    # Create ADS1115 object 
    ads = ADS.ADS1115(i2c, address=ads_addr) 
     
    # Set gain (adjust based on your voltage range) 
    # GAIN = 1: +/- 4.096V range 
    ads.gain = 1 
     
    # Create analog input channels (0, 1, 2, 3) 
    channels = [ 
        AnalogIn(ads, 0), 
        AnalogIn(ads, 1), 
        AnalogIn(ads, 2), 
        AnalogIn(ads, 3) 
    ] 
     
    print(f"\nGain: {ads.gain} (+/- 4.096V range)") 
    print("\nReading analog values... (Press Ctrl+C to stop)\n") 
     
    try: 
        while True: 
            print("-" * 50) 
            print(f"Timestamp: {time.strftime('%H:%M:%S')}") 
             
            for i, channel in enumerate(channels): 
                voltage = channel.voltage 
                raw_value = channel.value 
                 
                print(f"Channel A{i}: {voltage:>6.3f} V  (Raw: 
{raw_value:>5d})") 
             
            print() 
            time.sleep(1)  # Read every second 
             
    except KeyboardInterrupt: 
        print("\n\nProgram stopped by user") 
 
if __name__ == "__main__": 
    main()