from picamera2 import Picamera2, Preview 
from time import sleep 
# Initialize camera 
picam2 = Picamera2() 
# Start a preview window 
picam2.start_preview(Preview.QTGL)  # Opens a live preview 
picam2.start() 
print("?? Preview started... Capturing image in 5 seconds.") 
sleep(5) 
# Capture image 
filename = "captured_image.jpg" 
picam2.capture_file(filename) 
print(f"? Image saved as {filename}") 
# Stop camera 
picam2.stop()