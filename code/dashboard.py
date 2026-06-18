#!/usr/bin/env python3 
""" 
Snake Robot Professional Dashboard 
Enhanced UI with real-time monitoring, optimized camera performance, and JSON 
data logging 
With TTL Serial Communication to ESP32 
""" 
 
import io 
import socketserver 
from http import server 
from threading import Condition, Lock, Thread 
import time 
import json 
from collections import deque 
from datetime import datetime 
import board 
import busio 
import adafruit_ads1x15.ads1115 as ADS 
from adafruit_ads1x15.analog_in import AnalogIn 
import RPi.GPIO as GPIO 
import signal 
import sys 
import os 
import serial 
 
# BME280 imports 
import smbus2 
import bme280 
 
# Camera imports 
try: 
    from picamera2 import Picamera2 
    from picamera2.encoders import JpegEncoder 
    from picamera2.outputs import FileOutput 
    USE_PICAMERA2 = True 
    print("Using picamera2") 
except ImportError: 
    USE_PICAMERA2 = False 
    try: 
        import picamera 
        print("Using legacy picamera") 
    except ImportError: 
        print("ERROR: No camera library found. Continuing with sensors only.") 
 
# ===== SERIAL/TTL CONFIGURATION ===== 
SERIAL_PORT = '/dev/serial/by-id/usb-Prolific_Technology_Inc._USB
Serial_Controller-if00-port0'  # Default Raspberry Pi serial port (GPIO 14/15) 
BAUD_RATE = 9600  # Match this with your ESP32 baud rate 
serial_connection = None 
 
# ===== GPIO PIN CONFIGURATION ===== 
FLAME_SENSOR_PIN = 22 
ULTRASONIC_TRIG = 6 
ULTRASONIC_ECHO = 5 
 
# ===== BME280 CONFIGURATION ===== 
BME280_ADDRESS = 0x76 
 
# ===== JSON DATA FILE ===== 
JSON_DATA_FILE = "data.json" 
JSON_UPDATE_INTERVAL = 2  # seconds 
 
# ===== GLOBAL STATE ===== 
streaming_active = False 
streaming_lock = Lock() 
sensor_data = { 
    'smoke': 0, 
    'flame': False, 
    'temperature': 0, 
    'humidity': 0, 
    'pressure': 0, 
    'distance': -1, 
    'object_detected': False 
} 
sensor_history = { 
    'smoke': deque(maxlen=60), 
    'temperature': deque(maxlen=60), 
    'humidity': deque(maxlen=60), 
    'distance': deque(maxlen=60), 
    'timestamps': deque(maxlen=60) 
} 
 
# Global for cleanup 
camera_obj = None 
 
# ===== SERIAL COMMUNICATION SETUP ===== 
def setup_serial(): 
    """Initialize serial communication with ESP32""" 
    global serial_connection 
    try: 
        serial_connection = serial.Serial( 
            port=SERIAL_PORT, 
            baudrate=BAUD_RATE, 
            timeout=1, 
            bytesize=serial.EIGHTBITS, 
            parity=serial.PARITY_NONE, 
            stopbits=serial.STOPBITS_ONE 
        ) 
        print(f"OK Serial port {SERIAL_PORT} initialized at {BAUD_RATE} baud") 
        time.sleep(2)  # Wait for connection to stabilize 
        return True 
    except Exception as e: 
        print(f"WARNING Serial initialization failed: {e}") 
        print("   Robot control commands will be logged but not sent") 
        return False 
 
def send_serial_command(command): 
    """Send command to ESP32 via serial""" 
    global serial_connection 
    try: 
        if serial_connection and serial_connection.is_open: 
            # Send command as string followed by newline 
            serial_connection.write(f"{command}\n".encode()) 
            serial_connection.flush() 
            print(f">> Sent to ESP32: {command}") 
            return True 
        else: 
            print(f"WARNING Serial not available. Command: {command}") 
            return False 
    except Exception as e: 
        print(f"ERROR Serial send error: {e}") 
        return False 
 
# ===== SENSOR SETUP ===== 
def setup_sensors(): 
    global ads, smoke_channel, bme_bus, bme_calibration_params 
     
    GPIO.setmode(GPIO.BCM) 
    GPIO.setwarnings(False) 
    GPIO.setup(FLAME_SENSOR_PIN, GPIO.IN) 
    GPIO.setup(ULTRASONIC_TRIG, GPIO.OUT) 
    GPIO.setup(ULTRASONIC_ECHO, GPIO.IN) 
     
    i2c = busio.I2C(board.SCL, board.SDA) 
    ads = ADS.ADS1115(i2c) 
    smoke_channel = AnalogIn(ads, 0) 
     
    bme_bus = smbus2.SMBus(1) 
    bme_calibration_params = bme280.load_calibration_params(bme_bus, 
BME280_ADDRESS) 
     
    print("? All sensors initialized successfully") 
 
def read_ultrasonic(): 
    """Read distance from ultrasonic sensor with improved accuracy""" 
    try: 
        GPIO.output(ULTRASONIC_TRIG, True) 
        time.sleep(0.00001) 
        GPIO.output(ULTRASONIC_TRIG, False) 
         
        pulse_start = time.time() 
        timeout = pulse_start + 0.1 
        while GPIO.input(ULTRASONIC_ECHO) == 0: 
            if time.time() > timeout: 
                return -1 
            pulse_start = time.time() 
         
        pulse_end = time.time() 
        timeout = pulse_end + 0.1 
        while GPIO.input(ULTRASONIC_ECHO) == 1: 
            if time.time() > timeout: 
                return -1 
            pulse_end = time.time() 
         
        pulse_duration = pulse_end - pulse_start 
        distance = pulse_duration * 17150 
        distance = round(distance, 2) 
         
        if distance > 400 or distance < 2: 
            return -1 
        return distance 
    except: 
        return -1 
 
def write_json_data(): 
    """Write current sensor data to JSON file""" 
    try: 
        current_time = time.time() 
        timestamp_readable = 
datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S') 
         
        json_data = { 
            "smoke": round(sensor_data['smoke'], 2), 
            "flame": sensor_data['flame'], 
            "temperature": round(sensor_data['temperature'], 2), 
            "humidity": round(sensor_data['humidity'], 2), 
            "pressure": round(sensor_data['pressure'], 2), 
            "distance": round(sensor_data['distance'], 2) if 
sensor_data['distance'] > 0 else -1, 
            "object_detected": sensor_data['object_detected'], 
            "timestamp": round(current_time, 3), 
            "timestamp_readable": timestamp_readable 
        } 
         
        with open(JSON_DATA_FILE, 'w') as f: 
            json.dump(json_data, f, indent=2) 
             
    except Exception as e: 
        print(f"JSON write error: {e}") 
 
def json_writing_loop(): 
    """Continuously write sensor data to JSON file every 2 seconds""" 
    while True: 
        try: 
            write_json_data() 
            time.sleep(JSON_UPDATE_INTERVAL) 
        except Exception as e: 
            print(f"JSON loop error: {e}") 
            time.sleep(JSON_UPDATE_INTERVAL) 
 
def predict_hazard(): 
    """Simple hazard prediction based on sensor values""" 
    smoke = sensor_data['smoke'] 
    temp = sensor_data['temperature'] 
    humidity = sensor_data['humidity'] 
    flame = sensor_data['flame'] 
 
    risk = 0 
 
    # Smoke contribution 
    if smoke > 50: 
        risk += 40 
    elif smoke > 30: 
        risk += 20 
 
    # Temperature contribution 
    if temp > 50: 
        risk += 30 
    elif temp > 35: 
        risk += 15 
 
    # Humidity contribution 
    if humidity < 30: 
        risk += 10 
 
    # Flame detection (highest priority) 
    if flame: 
        risk += 50 
 
    return min(risk, 100)  # Cap at 100% 
 
def sensor_reading_loop(): 
    """Continuously read sensors""" 
    global sensor_data, sensor_history 
     
    while True: 
        try: 
            smoke_voltage = smoke_channel.voltage 
            smoke_value = (smoke_voltage / 3.3) * 100 
             
            flame_detected = GPIO.input(FLAME_SENSOR_PIN) == 0 
             
            bme_data = bme280.sample(bme_bus, BME280_ADDRESS, 
bme_calibration_params) 
            temperature = round(bme_data.temperature, 1) 
            humidity = round(bme_data.humidity, 1) 
            pressure = round(bme_data.pressure, 1) 
             
            distance = read_ultrasonic() 
            object_detected = 0 < distance < 100 
             
            sensor_data = { 
                'smoke': round(smoke_value, 1), 
                'flame': flame_detected, 
                'temperature': temperature, 
                'humidity': humidity, 
                'pressure': pressure, 
                'distance': distance, 
                'object_detected': object_detected 
            } 
 
sensor_data['hazard'] = predict_hazard() 
             
            current_time = time.time() 
            sensor_history['smoke'].append(smoke_value) 
            sensor_history['temperature'].append(temperature) 
            sensor_history['humidity'].append(humidity) 
            sensor_history['distance'].append(distance if distance > 0 else 
0) 
            sensor_history['timestamps'].append(current_time) 
             
        except Exception as e: 
            print(f"Sensor read error: {e}") 
         
        time.sleep(0.5) 
 
PAGE = """\ 
<html> 
<head> 
<meta charset="UTF-8"> 
<title>Snake Robot Professional Dashboard</title> 
<meta name="viewport" content="width=device-width, initial-scale=1.0"> 
<script 
src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></s
cript> 
<style> 
:root { 
    --primary: #667eea; 
    --primary-dark: #5568d3; 
    --secondary: #764ba2; 
    --success: #10b981; 
    --warning: #f59e0b; 
    --danger: #ef4444; 
    --dark: #1f2937; 
    --gray: #6b7280; 
    --light-gray: #f3f4f6; 
} 
 
* { 
    margin: 0; 
    padding: 0; 
    box-sizing: border-box; 
} 
 
body { 
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans
serif; 
    background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 
100%); 
    min-height: 100vh; 
    padding: 15px; 
    color: var(--dark); 
} 
 
.dashboard { 
    max-width: 1800px; 
    margin: 0 auto; 
} 
 
.header { 
    background: rgba(255,255,255,0.98); 
    border-radius: 20px; 
    padding: 20px 30px; 
    margin-bottom: 20px; 
    box-shadow: 0 10px 40px rgba(0,0,0,0.15); 
    display: flex; 
    justify-content: space-between; 
    align-items: center; 
    flex-wrap: wrap; 
    gap: 20px; 
} 
 
.header h1 { 
    font-size: 2em; 
    background: linear-gradient(135deg, var(--primary), var(--secondary)); 
    -webkit-background-clip: text; 
    -webkit-text-fill-color: transparent; 
    font-weight: 800; 
    display: flex; 
    align-items: center; 
    gap: 12px; 
} 
 
.timestamp { 
    font-size: 0.9em; 
    color: var(--gray); 
    font-weight: 500; 
} 
 
.json-status { 
    background: linear-gradient(135deg, var(--success), #059669); 
    color: white; 
    padding: 8px 16px; 
    border-radius: 20px; 
    font-size: 0.85em; 
    font-weight: 600; 
    display: flex; 
    align-items: center; 
    gap: 8px; 
} 
 
.json-status::before { 
    content: '?'; 
    animation: pulse 2s infinite; 
} 
 
.card { 
    background: rgba(255,255,255,0.98); 
    border-radius: 20px; 
    padding: 25px; 
    box-shadow: 0 10px 40px rgba(0,0,0,0.15); 
    transition: all 0.3s ease; 
    margin-bottom: 20px; 
} 
 
.card:hover { 
    transform: translateY(-5px); 
    box-shadow: 0 15px 50px rgba(0,0,0,0.2); 
} 
 
.card-header { 
    display: flex; 
    justify-content: space-between; 
    align-items: center; 
    margin-bottom: 20px; 
    padding-bottom: 15px; 
    border-bottom: 3px solid var(--primary); 
} 
 
.card-title { 
    font-size: 1.3em; 
    font-weight: 700; 
    display: flex; 
    align-items: center; 
    gap: 10px; 
    color: var(--dark); 
} 
 
.controls { 
    display: flex; 
    gap: 12px; 
    flex-wrap: wrap; 
    align-items: center; 
} 
 
.stream-status { 
    padding: 10px 20px; 
    border-radius: 25px; 
    font-weight: 700; 
    display: flex; 
    align-items: center; 
    gap: 10px; 
    font-size: 0.95em; 
} 
 
.stream-status.active { 
    background: var(--success); 
    color: white; 
} 
 
.stream-status.inactive { 
    background: var(--gray); 
    color: white; 
} 
 
.status-dot { 
    width: 10px; 
    height: 10px; 
    border-radius: 50%; 
    background: white; 
    animation: pulse 2s infinite; 
} 
 
@keyframes pulse { 
    0%, 100% { opacity: 1; transform: scale(1); } 
    50% { opacity: 0.5; transform: scale(0.85); } 
} 
 
button { 
    padding: 12px 24px; 
    border: none; 
    border-radius: 12px; 
    cursor: pointer; 
    font-weight: 700; 
    font-size: 0.95em; 
    transition: all 0.3s ease; 
    box-shadow: 0 4px 15px rgba(0,0,0,0.2); 
    text-transform: uppercase; 
    letter-spacing: 0.5px; 
} 
 
button:hover:not(:disabled) { 
    transform: translateY(-2px); 
    box-shadow: 0 6px 20px rgba(0,0,0,0.3); 
} 
 
.btn-start { 
    background: linear-gradient(135deg, var(--success), #059669); 
    color: white; 
} 
 
.btn-stop { 
    background: linear-gradient(135deg, var(--danger), #dc2626); 
    color: white; 
} 
 
button:disabled { 
    opacity: 0.5; 
    cursor: not-allowed; 
    transform: none; 
} 
 
.stream-container { 
    background: #000; 
    border-radius: 15px; 
    overflow: hidden; 
    min-height: 360px; 
    display: flex; 
    align-items: center; 
    justify-content: center; 
    box-shadow: inset 0 4px 15px rgba(0,0,0,0.6); 
} 
 
.stream-container img { 
    width: 100%; 
    height: auto; 
    display: block; 
} 
 
.no-stream { 
    color: #9ca3af; 
    font-size: 1.1em; 
    text-align: center; 
    padding: 20px; 
} 
 
.robot-controls { 
    background: rgba(255,255,255,0.98); 
    border-radius: 20px; 
    padding: 25px; 
    box-shadow: 0 10px 40px rgba(0,0,0,0.15); 
    margin-bottom: 20px; 
} 
 
.control-grid { 
    display: grid; 
    grid-template-columns: repeat(4, 1fr); 
    gap: 12px; 
    margin-top: 20px; 
} 
 
.control-btn { 
    padding: 18px 12px; 
    font-size: 0.85em; 
    border-radius: 12px; 
    display: flex; 
    flex-direction: column; 
    align-items: center; 
    justify-content: center; 
    gap: 8px; 
    transition: all 0.2s ease; 
    min-height: 85px; 
} 
 
.control-btn:hover:not(:disabled) { 
    transform: translateY(-3px) scale(1.02); 
} 
 
.btn-cmd-1 { background: linear-gradient(135deg, #10b981, #059669); color: 
white; } 
.btn-cmd-2 { background: linear-gradient(135deg, #3b82f6, #2563eb); color: 
white; } 
.btn-cmd-3 { background: linear-gradient(135deg, #8b5cf6, #7c3aed); color: 
white; } 
.btn-cmd-4 { background: linear-gradient(135deg, #f59e0b, #d97706); color: 
white; } 
.btn-cmd-5 { background: linear-gradient(135deg, #f59e0b, #d97706); color: 
white; } 
.btn-cmd-6 { background: linear-gradient(135deg, #ef4444, #dc2626); color: 
white; } 
.btn-cmd-7 { background: linear-gradient(135deg, #6b7280, #4b5563); color: 
white; } 
.btn-cmd-8 { background: linear-gradient(135deg, #667eea, #5568d3); color: 
white; } 
 
.cmd-icon { 
    font-size: 1.5em; 
} 
 
.cmd-label { 
    font-size: 0.9em; 
    font-weight: 700; 
    text-align: center; 
    line-height: 1.2; 
} 
 
.main-grid { 
    display: grid; 
    grid-template-columns: 2fr 1fr; 
    gap: 20px; 
    margin-bottom: 20px; 
} 
 
.distance-monitor { 
    background: linear-gradient(135deg, rgba(139,92,246,0.1), 
rgba(124,58,237,0.1)); 
    border-radius: 15px; 
    padding: 25px; 
    text-align: center; 
} 
 
.distance-value-xl { 
    font-size: 4.5em; 
    font-weight: 900; 
    background: linear-gradient(135deg, var(--primary), var(--secondary)); 
    -webkit-background-clip: text; 
    -webkit-text-fill-color: transparent; 
    line-height: 1; 
    margin: 15px 0; 
} 
 
.distance-unit { 
    font-size: 0.4em; 
    color: var(--gray); 
    font-weight: 600; 
} 
 
.object-indicator { 
    width: 140px; 
    height: 140px; 
    border-radius: 50%; 
    margin: 0 auto 20px; 
    display: flex; 
    align-items: center; 
    justify-content: center; 
    font-size: 2em; 
    font-weight: 900; 
    transition: all 0.3s ease; 
    color: white; 
    text-shadow: 2px 2px 8px rgba(0,0,0,0.3); 
} 
 
.object-detected { 
    background: linear-gradient(135deg, var(--danger), #dc2626); 
    animation: danger-pulse 0.6s infinite; 
} 
 
.no-object { 
    background: linear-gradient(135deg, var(--success), #059669); 
} 
 
@keyframes danger-pulse { 
    0%, 100% { transform: scale(1); } 
    50% { transform: scale(1.08); } 
} 
 
.sensor-grid { 
    display: grid; 
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); 
    gap: 20px; 
} 
 
.sensor-card { 
    background: rgba(255,255,255,0.98); 
    border-radius: 20px; 
    padding: 25px; 
    box-shadow: 0 10px 40px rgba(0,0,0,0.15); 
    transition: all 0.3s ease; 
} 
 
.sensor-value { 
    font-size: 3.5em; 
    font-weight: 900; 
    background: linear-gradient(135deg, var(--primary), var(--secondary)); 
    -webkit-background-clip: text; 
    -webkit-text-fill-color: transparent; 
    margin: 15px 0; 
    line-height: 1; 
} 
 
.sensor-label { 
    color: var(--gray); 
    font-size: 0.9em; 
    font-weight: 600; 
    text-transform: uppercase; 
    letter-spacing: 1px; 
} 
 
.alert { 
    background: linear-gradient(135deg, #fee, #fdd); 
    border: 3px solid var(--danger); 
    color: #b91c1c; 
    padding: 15px 20px; 
    border-radius: 12px; 
    font-weight: 700; 
    margin-top: 15px; 
    animation: blink 1s infinite; 
    text-align: center; 
} 
 
@keyframes blink { 
    0%, 100% { opacity: 1; } 
    50% { opacity: 0.6; } 
} 
 
.chart-container { 
    position: relative; 
    height: 180px; 
    margin-top: 20px; 
    background: rgba(102,126,234,0.03); 
    border-radius: 12px; 
    padding: 15px; 
} 
 
@media (max-width: 1200px) { 
    .main-grid { 
        grid-template-columns: 1fr; 
    } 
    .control-grid { 
        grid-template-columns: repeat(2, 1fr); 
    } 
} 
 
@media (max-width: 768px) { 
    .header h1 { 
        font-size: 1.5em; 
    } 
    .control-grid { 
        grid-template-columns: repeat(2, 1fr); 
    } 
    .sensor-value { 
        font-size: 2.5em; 
    } 
} 
</style> 
</head> 
<body> 
<div class="dashboard"> 
    <div class="header"> 
        <h1>Snake Robot Control Center</h1> 
        <div style="display: flex; gap: 15px; align-items: center; flex-wrap: 
wrap;"> 
            <div class="json-status">JSON Logging Active</div> 
            <div class="timestamp" id="timestamp">Loading...</div> 
        </div> 
    </div> 
     
    <div class="robot-controls"> 
        <h2 style="margin-bottom: 15px; color: var(--dark); text-align: 
center;">Robot Control Commands</h2> 
        <div class="control-grid"> 
            <button class="control-btn btn-cmd-1" onclick="sendCommand('1')"> 
                <div class="cmd-icon">ON</div> 
                <div class="cmd-label">Turn ON</div> 
            </button> 
            <button class="control-btn btn-cmd-2" onclick="sendCommand('2')"> 
                <div class="cmd-icon">~~~</div> 
                <div class="cmd-label">Serpentine</div> 
            </button> 
            <button class="control-btn btn-cmd-3" onclick="sendCommand('3')"> 
                <div class="cmd-icon">UP</div> 
                <div class="cmd-label">Uplifting</div> 
            </button> 
            <button class="control-btn btn-cmd-4" onclick="sendCommand('4')"> 
                <div class="cmd-icon">&lt;</div> 
                <div class="cmd-label">Turn Left</div> 
            </button> 
            <button class="control-btn btn-cmd-5" onclick="sendCommand('5')"> 
                <div class="cmd-icon">&gt;</div> 
                <div class="cmd-label">Turn Right</div> 
            </button> 
            <button class="control-btn btn-cmd-6" onclick="sendCommand('6')"> 
                <div class="cmd-icon">STOP</div> 
                <div class="cmd-label">Stop</div> 
            </button> 
            <button class="control-btn btn-cmd-7" onclick="sendCommand('7')"> 
                <div class="cmd-icon">OFF</div> 
                <div class="cmd-label">Turn OFF</div> 
            </button> 
            <button class="control-btn btn-cmd-8" onclick="sendCommand('8')"> 
                <div class="cmd-icon">RST</div> 
                <div class="cmd-label">Reset Position</div> 
            </button> 
        </div> 
    </div> 
     
    <div class="main-grid"> 
        <div class="card"> 
            <div class="card-header"> 
                <div class="card-title">Live Camera Feed</div> 
            </div> 
            <div class="controls"> 
                <div class="stream-status inactive" id="status"> 
                    <span class="status-dot"></span> 
                    <span id="status-text">Stream Inactive</span> 
                </div> 
                <button class="btn-start" id="startBtn" 
onclick="startStream()">Start</button> 
                <button class="btn-stop" id="stopBtn" onclick="stopStream()" 
disabled>Stop</button> 
            </div> 
            <div class="stream-container"> 
                <div class="no-stream" id="noStream">Click "Start" to begin 
video feed</div> 
                <img id="streamImg" style="display:none;" alt="Camera Stream" 
/> 
            </div> 
        </div> 
         
        <div class="card"> 
            <div class="card-header"> 
                <div class="card-title">Distance Monitor</div> 
            </div> 
            <div class="distance-monitor"> 
                <div id="objectIndicator" class="object-indicator no
object">CLEAR</div> 
                <div class="distance-value-xl" id="distanceValueLarge"> 
                    --<span class="distance-unit">cm</span> 
                </div> 
                <div class="chart-container"> 
                    <canvas id="distanceChart"></canvas> 
                </div> 
            </div> 
        </div> 
    </div> 
     
    <div class="sensor-grid"> 
        <div class="sensor-card"> 
            <div class="card-header"> 
                <div class="card-title">Smoke Sensor</div> 
            </div> 
            <div class="sensor-value" id="smokeValue">0%</div> 
            <div class="sensor-label">Gas Concentration</div> 
            <div id="smokeAlert" style="display:none;" class="alert">ALERT: 
SMOKE DETECTED!</div> 
            <div class="chart-container"> 
                <canvas id="smokeChart"></canvas> 
            </div> 
        </div> 
         
        <div class="sensor-card"> 
            <div class="card-header"> 
                <div class="card-title">Flame Sensor</div> 
            </div> 
            <div class="sensor-value" id="flameValue" style="color: var(-
success);">Safe</div> 
            <div class="sensor-label">Fire Detection Status</div> 
            <div id="flameAlert" style="display:none;" class="alert">ALERT: 
FLAME DETECTED!</div> 
        </div> 
         
        <div class="sensor-card"> 
            <div class="card-header"> 
                <div class="card-title">Temperature</div> 
            </div> 
             
            <div class="sensor-value" id="tempValue">--&deg;C</div> 
            <div class="sensor-label">Current Temperature</div> 
            <div class="chart-container"> 
                <canvas id="tempChart"></canvas> 
            </div> 
        </div> 
         
        <div class="sensor-card"> 
            <div class="card-header"> 
                <div class="card-title">Humidity</div> 
            </div> 
            <div class="sensor-value" id="humidityValue">--%</div> 
            <div class="sensor-label">Relative Humidity</div> 
            <div class="chart-container"> 
                <canvas id="humidityChart"></canvas> 
            </div> 
        </div> 
         
        <div class="sensor-card"> 
            <div class="card-header"> 
                <div class="card-title">Pressure</div> 
            </div> 
            <div class="sensor-value" id="pressureValue">--</div> 
            <div class="sensor-label">Atmospheric Pressure (hPa)</div> 
        </div> 
    </div> 
</div> 
<div class="sensor-card"> 
    <div class="card-header"> 
        <div class="card-title">Environmental Hazard Forecast</div> 
    </div> 
 
    <div class="sensor-value" id="hazardProbability">--%</div> 
 
    <div class="sensor-label"> 
        Predicted Risk Level (Next 30 Minutes) 
    </div> 
 
    <div style="margin-top:15px; font-size:1.2em; font-weight:700;"> 
        Status: <span id="hazardStatus">Analyzing...</span> 
    </div> 
 
</div> 
 
<script> 
let streamActive = false; 
let charts = {}; 
 
function updateTimestamp() { 
    const now = new Date(); 
    document.getElementById('timestamp').textContent =  
        now.toLocaleString('en-US', {  
            weekday: 'short',  
            year: 'numeric',  
            month: 'short',  
            day: 'numeric',  
            hour: '2-digit',  
            minute: '2-digit', 
            second: '2-digit' 
        }); 
} 
 
function initCharts() { 
    const chartConfig = { 
        type: 'line', 
        options: { 
            responsive: true, 
            maintainAspectRatio: false, 
            plugins: {  
                legend: { display: false }, 
                tooltip: {  
                    enabled: true, 
                    backgroundColor: 'rgba(0,0,0,0.8)', 
                    padding: 12 
                } 
            }, 
            scales: { 
                x: { display: false }, 
                y: {  
                    beginAtZero: true, 
                    grid: { color: 'rgba(0,0,0,0.06)' } 
                } 
            }, 
            elements: { 
                point: { radius: 0 }, 
                line: { tension: 0.4, borderWidth: 3 } 
            } 
        } 
    }; 
     
    charts.smoke = new Chart(document.getElementById('smokeChart'), { 
        ...chartConfig, 
        data: {  
            labels: [],  
            datasets: [{  
                data: [],  
                borderColor: '#ef4444',  
                backgroundColor: 'rgba(239, 68, 68, 0.15)', 
                fill: true 
            }]  
        } 
    }); 
     
    charts.temp = new Chart(document.getElementById('tempChart'), { 
        ...chartConfig, 
        data: {  
            labels: [],  
            datasets: [{  
                data: [],  
                borderColor: '#f59e0b', 
                backgroundColor: 'rgba(245, 158, 11, 0.15)', 
                fill: true 
            }]  
        } 
    }); 
     
    charts.humidity = new Chart(document.getElementById('humidityChart'), { 
        ...chartConfig, 
        data: {  
            labels: [],  
            datasets: [{  
                data: [],  
                borderColor: '#3b82f6', 
                backgroundColor: 'rgba(59, 130, 246, 0.15)', 
                fill: true 
            }]  
        } 
    }); 
     
    charts.distance = new Chart(document.getElementById('distanceChart'), { 
        ...chartConfig, 
        data: {  
            labels: [],  
            datasets: [{  
                data: [],  
                borderColor: '#8b5cf6', 
                backgroundColor: 'rgba(139, 92, 246, 0.15)', 
                fill: true 
            }]  
        } 
    }); 
} 
 
async function sendCommand(command) { 
    try { 
        const response = await fetch('/control', { 
            method: 'POST', 
            headers: {'Content-Type': 'application/json'}, 
            body: JSON.stringify({action: command}) 
        }); 
        const data = await response.json(); 
        if (data.success) { 
            console.log(`Command ${command} sent successfully`); 
            // Visual feedback 
            const btn = event.target.closest('button'); 
            if (btn) { 
                btn.style.transform = 'scale(0.95)'; 
                setTimeout(() => btn.style.transform = '', 200); 
            } 
        } 
    } catch (error) { 
        console.error(`Failed to send command ${command}:`, error); 
    } 
} 
 
async function startStream() { 
    try { 
        const response = await fetch('/control', { 
            method: 'POST', 
            headers: {'Content-Type': 'application/json'}, 
            body: JSON.stringify({action: 'start'}) 
        }); 
        const data = await response.json(); 
        if (data.success) { 
            streamActive = true; 
            updateCameraUI(); 
            document.getElementById('streamImg').src = '/stream.mjpg?' + 
Date.now(); 
        } 
    } catch (error) { 
        console.error('Failed to start stream:', error); 
    } 
} 
 
async function stopStream() { 
    try { 
        const response = await fetch('/control', { 
            method: 'POST', 
            headers: {'Content-Type': 'application/json'}, 
            body: JSON.stringify({action: 'stop'}) 
        }); 
        const data = await response.json(); 
        if (data.success) { 
            streamActive = false; 
            updateCameraUI(); 
            document.getElementById('streamImg').src = ''; 
        } 
    } catch (error) { 
        console.error('Failed to stop stream:', error); 
    } 
} 
 
function updateCameraUI() { 
    const status = document.getElementById('status'); 
    const statusText = document.getElementById('status-text'); 
    const startBtn = document.getElementById('startBtn'); 
    const stopBtn = document.getElementById('stopBtn'); 
    const streamImg = document.getElementById('streamImg'); 
    const noStream = document.getElementById('noStream'); 
     
    if (streamActive) { 
        status.className = 'stream-status active'; 
        statusText.textContent = 'Stream Active'; 
        startBtn.disabled = true; 
        stopBtn.disabled = false; 
        streamImg.style.display = 'block'; 
        noStream.style.display = 'none'; 
    } else { 
        status.className = 'stream-status inactive'; 
        statusText.textContent = 'Stream Inactive'; 
        startBtn.disabled = false; 
        stopBtn.disabled = true; 
        streamImg.style.display = 'none'; 
        noStream.style.display = 'block'; 
    } 
} 
 
async function updateSensors() { 
    try { 
        const response = await fetch('/sensors'); 
        const data = await response.json(); 
         
        document.getElementById('smokeValue').textContent = 
data.current.smoke.toFixed(1) + '%'; 
        document.getElementById('smokeAlert').style.display = 
data.current.smoke > 50 ? 'block' : 'none'; 
         
        const flameValue = document.getElementById('flameValue'); 
        const flameAlert = document.getElementById('flameAlert'); 
         
        if (data.current.flame) { 
            flameValue.textContent = 'FIRE!'; 
            flameValue.style.background = 'linear-gradient(135deg, #ef4444, 
#dc2626)'; 
            flameValue.style.webkitBackgroundClip = 'text'; 
            flameValue.style.webkitTextFillColor = 'transparent'; 
            flameAlert.style.display = 'block'; 
        } else { 
            flameValue.textContent = 'Safe'; 
            flameValue.style.background = 'linear-gradient(135deg, #10b981, 
#059669)'; 
            flameValue.style.webkitBackgroundClip = 'text'; 
            flameValue.style.webkitTextFillColor = 'transparent'; 
            flameAlert.style.display = 'none'; 
        } 
         
        document.getElementById('tempValue').textContent = 
data.current.temperature + '\u00B0C'; 
 
        document.getElementById('humidityValue').textContent = 
data.current.humidity + '%'; 
        document.getElementById('pressureValue').textContent = 
data.current.pressure + ' hPa'; 
        document.getElementById('hazardValue').textContent = data.hazard + 
'%'; 
        const hazardEl = document.getElementById('hazardValue'); 
hazardEl.textContent = data.hazard + '%'; 
 
if (data.hazard > 70) { 
    hazardEl.style.color = 'red'; 
} else if (data.hazard > 40) { 
    hazardEl.style.color = 'orange'; 
} else { 
    hazardEl.style.color = 'green'; 
} 
         
        const indicator = document.getElementById('objectIndicator'); 
        const distValue = document.getElementById('distanceValueLarge'); 
         
        if (data.current.object_detected) { 
            indicator.className = 'object-indicator object-detected'; 
            indicator.textContent = 'STOP'; 
            const dist = data.current.distance.toFixed(1); 
            distValue.innerHTML = dist + '<span class="distance
unit">cm</span>'; 
        } else if (data.current.distance > 0) { 
            indicator.className = 'object-indicator no-object'; 
            indicator.textContent = 'CLEAR'; 
            const dist = data.current.distance.toFixed(1); 
            distValue.innerHTML = dist + '<span class="distance
unit">cm</span>'; 
        } else { 
            indicator.className = 'object-indicator no-object'; 
            indicator.textContent = 'OK'; 
            distValue.innerHTML = '--<span class="distance-unit">cm</span>'; 
        } 
         
        updateChart(charts.smoke, data.history.smoke); 
        updateChart(charts.temp, data.history.temperature); 
        updateChart(charts.humidity, data.history.humidity); 
        updateChart(charts.distance, data.history.distance); 
         
    } catch (error) { 
        console.error('Sensor update failed:', error); 
    } 
} 
 
function updateChart(chart, data) { 
    chart.data.labels = data.map((_, i) => i); 
    chart.data.datasets[0].data = data; 
    chart.update('none'); 
} 
 
initCharts(); 
updateTimestamp(); 
setInterval(updateTimestamp, 1000); 
updateSensors(); 
setInterval(updateSensors, 500); 
</script> 
</body> 
</html> 
""" 
 
# ===== STREAMING OUTPUT ===== 
class StreamingOutput(io.BufferedIOBase): 
    def __init__(self): 
        self.frame = None 
        self.condition = Condition() 
 
    def write(self, buf): 
        with self.condition: 
            self.frame = buf 
            self.condition.notify_all() 
 
# ===== HTTP HANDLERS ===== 
class StreamingHandler(server.BaseHTTPRequestHandler): 
    def do_GET(self): 
        if self.path == '/': 
            self.send_response(200) 
            self.send_header('Content-Type', 'text/html') 
            self.send_header('Content-Length', len(PAGE)) 
            self.end_headers() 
            self.wfile.write(PAGE.encode('utf-8')) 
             
        elif self.path.startswith('/stream.mjpg'): 
            global streaming_active 
            with streaming_lock: 
                if not streaming_active: 
                    self.send_error(503, "Stream not active") 
                    return 
             
            self.send_response(200) 
            self.send_header('Age', 0) 
            self.send_header('Cache-Control', 'no-cache, private') 
            self.send_header('Pragma', 'no-cache') 
            self.send_header('Content-Type', 'multipart/x-mixed-replace; 
boundary=FRAME') 
            self.end_headers() 
             
            try: 
                while streaming_active: 
                    with output.condition: 
                        output.condition.wait() 
                        frame = output.frame 
                     
                    self.wfile.write(b'--FRAME\r\n') 
                    self.send_header('Content-Type', 'image/jpeg') 
                    self.send_header('Content-Length', len(frame)) 
                    self.end_headers() 
                    self.wfile.write(frame) 
                    self.wfile.write(b'\r\n') 
            except Exception as e: 
                print(f'Streaming error: {e}') 
                 
        elif self.path == '/sensors': 
            self.send_response(200) 
            self.send_header('Content-Type', 'application/json') 
            self.end_headers() 
             
            response = { 
    'current': sensor_data, 
    'history': { 
        'smoke': list(sensor_history['smoke']), 
        'temperature': list(sensor_history['temperature']), 
        'humidity': list(sensor_history['humidity']), 
        'distance': list(sensor_history['distance']) 
    }, 
    'hazard': sensor_data.get('hazard', 0)   # ADD THIS 
} 
            self.wfile.write(json.dumps(response).encode('utf-8')) 
        else: 
            self.send_error(404) 
     
    def do_POST(self): 
        global streaming_active, camera_obj 
        if self.path == '/control': 
            content_length = int(self.headers['Content-Length']) 
            post_data = self.rfile.read(content_length) 
            data = json.loads(post_data.decode('utf-8')) 
             
            action = data.get('action', '') 
             
            # Handle robot commands 1-8 
            if action in ['1', '2', '3', '4', '5', '6', '7', '8']: 
                success = send_serial_command(action) 
                result = {'success': success, 'message': f'Command {action} 
sent to ESP32'} 
                 
            elif action == 'start': 
                with streaming_lock: 
                    if not streaming_active: 
                        try: 
                            if USE_PICAMERA2 and camera_obj: 
                                camera_obj.start_recording(JpegEncoder(), 
FileOutput(output)) 
                            elif 'camera' in globals() and camera_obj: 
                                camera_obj.start_recording(output, 
format='mjpeg') 
                            streaming_active = True 
                            result = {'success': True} 
                        except Exception as e: 
                            result = {'success': False, 'error': str(e)} 
                    else: 
                        result = {'success': True, 'message': 'Already 
streaming'} 
                         
            elif action == 'stop': 
                with streaming_lock: 
                    if streaming_active: 
                        try: 
                            if USE_PICAMERA2 and camera_obj: 
                                camera_obj.stop_recording() 
                            elif 'camera' in globals() and camera_obj: 
                                camera_obj.stop_recording() 
                            streaming_active = False 
                            result = {'success': True} 
                        except Exception as e: 
                            result = {'success': False, 'error': str(e)} 
                    else: 
                        result = {'success': True, 'message': 'Already stopped'} 
            else: 
                result = {'success': False, 'error': 'Invalid action'} 
             
            self.send_response(200) 
            self.send_header('Content-Type', 'application/json') 
            self.end_headers() 
            self.wfile.write(json.dumps(result).encode('utf-8')) 
        else: 
            self.send_error(404) 
 
class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer): 
    allow_reuse_address = True 
    daemon_threads = True 
 
def signal_handler(sig, frame): 
    print("\nShutting down gracefully...") 
    global streaming_active, camera_obj, serial_connection 
     
    with streaming_lock: 
        if streaming_active: 
            try: 
                if USE_PICAMERA2 and camera_obj: 
                    camera_obj.stop_recording() 
                elif 'camera' in globals() and camera_obj: 
                    camera_obj.stop_recording() 
                streaming_active = False 
            except Exception as e: 
                print(f"Error stopping camera: {e}") 
     
    if serial_connection and serial_connection.is_open: 
        serial_connection.close() 
        print("OK Serial connection closed") 
     
    GPIO.cleanup() 
    print("OK Shutdown complete") 
    sys.exit(0) 
 
# ===== MAIN ===== 
if __name__ == '__main__': 
    signal.signal(signal.SIGINT, signal_handler) 
     
    os.system('pkill -f libcamera || true') 
    os.system('pkill -f picamera || true') 
    os.system('sudo lsof -ti:8000 | xargs -r sudo kill -9 || true') 
     
    print("="*70) 
    print("INITIALIZING SNAKE ROBOT DASHBOARD") 
    print("="*70) 
     
    setup_sensors() 
    serial_ready = setup_serial() 
     
    sensor_thread = Thread(target=sensor_reading_loop, daemon=True) 
    sensor_thread.start() 
    print("OK Sensor monitoring started") 
     
    json_thread = Thread(target=json_writing_loop, daemon=True) 
    json_thread.start() 
    print(f"OK JSON data logging started (updates every 
{JSON_UPDATE_INTERVAL}s)") 
     
    output = StreamingOutput() 
    camera_available = False 
     
    if USE_PICAMERA2: 
        try: 
            camera_obj = Picamera2() 
            config = camera_obj.create_video_configuration( 
                main={"size": (480, 360)}, 
                controls={"FrameRate": 20} 
            ) 
            camera_obj.configure(config) 
            camera_available = True 
            print("OK Camera configured (480x360 @ 20fps)") 
        except Exception as e: 
            print(f"WARNING Camera initialization failed: {e}") 
            camera_available = False 
            camera_obj = None 
     
    httpd = None 
    try: 
        address = ('', 8000) 
        httpd = StreamingServer(address, StreamingHandler) 
        print("\n" + "="*70) 
        print("SNAKE ROBOT PROFESSIONAL DASHBOARD - ONLINE") 
        print("="*70) 
        print("Dashboard URL: http://<your-raspberry-pi-ip>:8000") 
        print("Real-time sensor monitoring active") 
        if camera_available: 
            print("Optimized camera streaming (480x360 @ 20fps)") 
        if serial_ready: 
            print(f"Serial communication ready (Port: {SERIAL_PORT} @ 
{BAUD_RATE} baud)") 
        else: 
            print("WARNING Serial not available - commands will be logged 
only") 
        print(f"JSON logging: {JSON_DATA_FILE} (every 
{JSON_UPDATE_INTERVAL}s)") 
        print("Press Ctrl+C to stop the server") 
        print("="*70 + "\n") 
        httpd.serve_forever() 
    except KeyboardInterrupt: 
        print("\n\nShutting down dashboard...") 
    except Exception as e: 
        print(f"Server error: {e}") 
    finally: 
        if httpd: 
            httpd.server_close() 
        if serial_connection and serial_connection.is_open: 
            serial_connection.close() 
        GPIO.cleanup() 
        if camera_obj: 
            try: 
                with streaming_lock: 
                    if streaming_active: 
                        if USE_PICAMERA2: 
                            camera_obj.stop_recording() 
                        else: 
                            camera_obj.stop_recording() 
                        streaming_active = False 
                if USE_PICAMERA2: 
                    camera_obj.stop() 
                else: 
                    camera_obj.close() 
            except Exception as e: 
                print(f"WARNING Final camera cleanup error: {e}") 
        print("OK Dashboard stopped successfully") 
