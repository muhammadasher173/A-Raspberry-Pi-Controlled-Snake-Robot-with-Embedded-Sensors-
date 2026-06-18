from flask import Flask, render_template, Response, request, jsonify 
from picamera2 import Picamera2 
from picamera2.encoders import JpegEncoder 
from picamera2.outputs import FileOutput 
import io 
import threading 
from datetime import datetime 
 
app = Flask(__name__) 
 
# Initialize camera 
picam2 = Picamera2() 
config = picam2.create_video_configuration(main={"size": (640, 480)}) 
picam2.configure(config) 
 
# Streaming output class 
class StreamingOutput(io.BufferedIOBase): 
    def __init__(self): 
        self.frame = None 
        self.condition = threading.Condition() 
 
    def write(self, buf): 
        with self.condition: 
            self.frame = buf 
            self.condition.notify_all() 
 
output = StreamingOutput() 
picam2.start() 
 
def generate_frames(): 
    """Generate frames for video streaming""" 
    while True: 
        with output.condition: 
            output.condition.wait() 
            frame = output.frame 
        yield (b'--frame\r\n' 
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n') 
 
@app.route('/') 
def index(): 
    """Render the main page""" 
    return render_template('index.html') 
 
@app.route('/video_feed') 
def video_feed(): 
    """Video streaming route""" 
    return Response(generate_frames(), 
                    mimetype='multipart/x-mixed-replace; boundary=frame') 
 
@app.route('/capture', methods=['POST']) 
def capture_image(): 
    """Capture a still image""" 
    try: 
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") 
        filename = f"capture_{timestamp}.jpg" 
        picam2.capture_file(filename) 
        return jsonify({"status": "success", "filename": filename}) 
    except Exception as e: 
        return jsonify({"status": "error", "message": str(e)}) 
 
@app.route('/start_recording', methods=['POST']) 
def start_recording(): 
    """Start video recording""" 
    try: 
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") 
        filename = f"video_{timestamp}.h264" 
        encoder = JpegEncoder() 
        picam2.start_recording(encoder, filename) 
        return jsonify({"status": "success", "filename": filename}) 
    except Exception as e: 
        return jsonify({"status": "error", "message": str(e)}) 
 
@app.route('/stop_recording', methods=['POST']) 
def stop_recording(): 
    """Stop video recording""" 
    try: 
        picam2.stop_recording() 
        return jsonify({"status": "success"}) 
    except Exception as e: 
return jsonify({"status": "error", "message": str(e)}) 
if __name__ == '__main__': 
# Start streaming encoder 
encoder = JpegEncoder() 
picam2.start_recording(encoder, FileOutput(output)) 
# Run Flask app 
app.run(host='0.0.0.0', port=5000, threaded=True, debug=False) 
