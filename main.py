#!/usr/bin/env python3
"""
Advanced AR Duck Server with MediaPipe Hand Tracking
"""
import cv2
import numpy as np
import base64
import json
import time
import os
import sys
import threading
import mediapipe as mp
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

class AdvancedARDuck:
    def __init__(self):
        self.objects = []
        self.next_id = 1
        self.camera = None
        self.is_running = False
        self.current_frame = None
        self.frame_lock = threading.Lock()
        self.fps = 30
        self.frame_count = 0
        self.last_fps_time = time.time()
        
        # Initialize MediaPipe Hands
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        
        # Hand tracking with high accuracy
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.8,
            min_tracking_confidence=0.8,
            model_complexity=1
        )
        
        # Grab state
        self.grabbed_duck_id = None
        self.grab_start_time = None
        self.grab_distance = 0.0
        self.last_hand_positions = []  # For smoothing
        
        # Model path
        self.model_path = "mecha_duck.glb"
        self._check_model()
        
        self.setup_camera()
        print("✅ Advanced AR Duck Server with Hand Tracking Initialized")
    
    def _check_model(self):
        """Check if model exists"""
        if os.path.exists(self.model_path):
            print(f"✅ Model found: {self.model_path}")
        elif os.path.exists("assets/3d/mecha_duck.glb"):
            self.model_path = "assets/3d/mecha_duck.glb"
            print(f"✅ Model found: {self.model_path}")
        else:
            print(f"⚠️  Model not found: {self.model_path}")
            print("   Using advanced duck visualization")
    
    def setup_camera(self):
        """Setup camera"""
        try:
            self.camera = cv2.VideoCapture(0)
            if self.camera.isOpened():
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self.camera.set(cv2.CAP_PROP_FPS, 60)
                self.is_running = True
                threading.Thread(target=self.camera_loop, daemon=True).start()
                print("✅ Camera ready: 1280x720 @ 60fps")
                return
        except Exception as e:
            print(f"Camera error: {e}")
        
        print("⚠️  Using simulation mode")
        self.is_running = True
        threading.Thread(target=self.simulation_loop, daemon=True).start()
    
    def detect_hands_mediapipe(self, frame):
        """Detect hands using MediaPipe"""
        height, width = frame.shape[:2]
        
        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False
        
        # Process with MediaPipe
        results = self.hands.process(rgb_frame)
        
        rgb_frame.flags.writeable = True
        
        hand_positions = []
        hand_gestures = []
        hand_landmarks_list = []
        
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                # Get wrist position (landmark 0)
                wrist = hand_landmarks.landmark[0]
                wrist_x = wrist.x * width
                wrist_y = wrist.y * height
                
                # Get index finger tip (landmark 8)
                index_tip = hand_landmarks.landmark[8]
                index_x = index_tip.x * width
                index_y = index_tip.y * height
                
                # Get thumb tip (landmark 4)
                thumb_tip = hand_landmarks.landmark[4]
                thumb_x = thumb_tip.x * width
                thumb_y = thumb_tip.y * height
                
                # Calculate distance between thumb and index finger
                thumb_index_distance = np.sqrt((index_x - thumb_x)**2 + (index_y - thumb_y)**2)
                
                # Detect pinch gesture (grabbing)
                is_pinching = thumb_index_distance < 40  # Adjust threshold as needed
                
                # Use index finger for grabbing position
                grab_position = (index_x / width, index_y / height)
                
                # Detect if hand is open or closed
                # Calculate distances between fingertips and palm
                landmarks = hand_landmarks.landmark
                wrist_pos = np.array([wrist.x, wrist.y])
                
                # Get key landmarks
                thumb_tip_pos = np.array([landmarks[4].x, landmarks[4].y])
                index_tip_pos = np.array([landmarks[8].x, landmarks[8].y])
                middle_tip_pos = np.array([landmarks[12].x, landmarks[12].y])
                ring_tip_pos = np.array([landmarks[16].x, landmarks[16].y])
                pinky_tip_pos = np.array([landmarks[20].x, landmarks[20].y])
                
                # Calculate distances from wrist
                distances = [
                    np.linalg.norm(thumb_tip_pos - wrist_pos),
                    np.linalg.norm(index_tip_pos - wrist_pos),
                    np.linalg.norm(middle_tip_pos - wrist_pos),
                    np.linalg.norm(ring_tip_pos - wrist_pos),
                    np.linalg.norm(pinky_tip_pos - wrist_pos)
                ]
                
                avg_distance = np.mean(distances)
                
                if is_pinching:
                    hand_gesture = "pinch"
                elif avg_distance > 0.15:
                    hand_gesture = "open"
                else:
                    hand_gesture = "fist"
                
                hand_positions.append(grab_position)
                hand_gestures.append(hand_gesture)
                hand_landmarks_list.append(hand_landmarks)
        
        return hand_positions, hand_gestures, hand_landmarks_list
    
    def check_hand_near_duck(self, hand_pos, duck_pos, threshold=0.08):
        """Check if hand is near a duck (normalized coordinates)"""
        distance = np.sqrt((hand_pos[0] - duck_pos['x'])**2 + 
                          (hand_pos[1] - duck_pos['y'])**2)
        return distance < threshold, distance
    
    def draw_advanced_duck(self, frame, duck, is_grabbed=False):
        """Draw an advanced duck with 3D effects"""
        height, width = frame.shape[:2]
        
        pos = duck['position']
        scale = duck['scale']
        rotation = duck['rotation']['y']
        duck_id = duck['id']
        
        # Convert to pixel coordinates
        x = int(pos['x'] * width)
        y = int(pos['y'] * height)
        
        # Duck size
        size = int(60 * scale)
        
        # ====== 3D BODY ======
        # Main body (ellipse with gradient)
        for i in range(size, 0, -2):
            alpha = i / size
            color = (int(30 * alpha), int(165 * alpha), int(255 * alpha))
            cv2.ellipse(frame, (x, y), (i, i//2), 
                       np.degrees(rotation), 0, 360, color, -1)
        
        # ====== HEAD ======
        head_offset = int(size * 0.8)
        head_x = x + int(head_offset * np.cos(rotation))
        head_y = y + int(head_offset * np.sin(rotation))
        head_size = int(size * 0.7)
        
        # Head with 3D effect
        for i in range(head_size, 0, -2):
            alpha = i / head_size
            color = (int(30 * alpha), int(150 * alpha), int(240 * alpha))
            cv2.circle(frame, (head_x, head_y), i, color, -1)
        
        # ====== BEAK ======
        beak_length = int(size * 0.6)
        beak_x = head_x + int(head_size * 0.8 * np.cos(rotation))
        beak_y = head_y + int(head_size * 0.8 * np.sin(rotation))
        
        beak_points = np.array([
            [beak_x, beak_y],
            [int(beak_x + beak_length * np.cos(rotation + 0.3)), 
             int(beak_y + beak_length * np.sin(rotation + 0.3))],
            [int(beak_x + beak_length * np.cos(rotation - 0.3)), 
             int(beak_y + beak_length * np.sin(rotation - 0.3))]
        ])
        
        # Beak with gradient
        cv2.fillPoly(frame, [beak_points], (0, 100, 200))
        cv2.polylines(frame, [beak_points], True, (0, 80, 180), 2)
        
        # ====== EYES ======
        eye_size = int(size * 0.18)
        eye_offset = int(head_size * 0.4)
        eye_angle = 0.4
        
        # Left eye
        eye_x1 = head_x + int(eye_offset * np.cos(rotation + eye_angle))
        eye_y1 = head_y + int(eye_offset * np.sin(rotation + eye_angle))
        
        # Eye with reflection
        cv2.circle(frame, (eye_x1, eye_y1), eye_size, (255, 255, 100), -1)  # Yellow eye
        cv2.circle(frame, (eye_x1, eye_y1), eye_size//2, (50, 50, 50), -1)   # Iris
        cv2.circle(frame, (eye_x1 + eye_size//4, eye_y1 - eye_size//4), 
                  eye_size//4, (255, 255, 255), -1)  # Reflection
        
        # Right eye
        eye_x2 = head_x + int(eye_offset * np.cos(rotation - eye_angle))
        eye_y2 = head_y + int(eye_offset * np.sin(rotation - eye_angle))
        
        cv2.circle(frame, (eye_x2, eye_y2), eye_size, (255, 255, 100), -1)
        cv2.circle(frame, (eye_x2, eye_y2), eye_size//2, (50, 50, 50), -1)
        cv2.circle(frame, (eye_x2 + eye_size//4, eye_y2 - eye_size//4), 
                  eye_size//4, (255, 255, 255), -1)
        
        # ====== WINGS ======
        wing_length = int(size * 1.2)
        wing_height = int(size * 0.4)
        
        # Left wing
        wing_x1 = x - int(size * 0.5 * np.sin(rotation))
        wing_y1 = y + int(size * 0.5 * np.cos(rotation))
        cv2.ellipse(frame, (wing_x1, wing_y1), (wing_length//2, wing_height),
                   np.degrees(rotation) + 30, 0, 180, (0, 130, 220), -1)
        
        # Right wing
        wing_x2 = x + int(size * 0.5 * np.sin(rotation))
        wing_y2 = y - int(size * 0.5 * np.cos(rotation))
        cv2.ellipse(frame, (wing_x2, wing_y2), (wing_length//2, wing_height),
                   np.degrees(rotation) - 30, 0, 180, (0, 130, 220), -1)
        
        # ====== SHADOW ======
        shadow_y = y + size // 2
        shadow_height = size // 6
        cv2.ellipse(frame, (x, shadow_y), (size, shadow_height),
                   0, 0, 360, (30, 30, 30, 150), -1)
        
        # ====== GRAB INDICATOR ======
        if is_grabbed:
            # Glowing effect
            for i in range(5):
                radius = size + 15 + i * 3
                alpha = 0.5 - i * 0.1
                color = (0, 255, 255, int(255 * alpha))
                overlay = frame.copy()
                cv2.circle(overlay, (x, y), radius, (0, 255, 255), 3)
                cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
            
            cv2.putText(frame, "GRABBED!", (x - 40, y - size - 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 3)
            cv2.putText(frame, "MOVE HAND TO DRAG", (x - 70, y - size - 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        else:
            # Grab zone indicator (semi-transparent)
            cv2.circle(frame, (x, y), int(80 * scale), (255, 255, 255, 100), 
                      2, cv2.LINE_AA)
            
            # "Grab me" text
            cv2.putText(frame, "PINCH TO GRAB", (x - 50, y - size - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 255), 1)
        
        # ====== ID & INFO ======
        # ID with background
        cv2.rectangle(frame, (x - 35, y - size - 35), 
                     (x + 35, y - size - 5), (0, 0, 0, 150), -1)
        cv2.putText(frame, f"Duck #{duck_id}", (x - 30, y - size - 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Info panel
        info_y = y + size + 25
        cv2.rectangle(frame, (x - 60, info_y - 5), 
                     (x + 60, info_y + 45), (30, 30, 30, 200), -1)
        
        cv2.putText(frame, f"Scale: {scale:.1f}x", (x - 50, info_y + 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
        
        angle_deg = int(np.degrees(rotation) % 360)
        cv2.putText(frame, f"Rot: {angle_deg}°", (x - 50, info_y + 35),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
        
        return frame
    
    def process_frame_with_advanced_hands(self, frame):
        """Process frame with advanced hand tracking"""
        processed = frame.copy()
        height, width = processed.shape[:2]
        
        # Detect hands with MediaPipe
        hand_positions, hand_gestures, hand_landmarks = self.detect_hands_mediapipe(processed)
        
        # Draw hand landmarks
        if hand_landmarks:
            for landmarks in hand_landmarks:
                self.mp_drawing.draw_landmarks(
                    processed,
                    landmarks,
                    self.mp_hands.HAND_CONNECTIONS,
                    self.mp_drawing_styles.get_default_hand_landmarks_style(),
                    self.mp_drawing_styles.get_default_hand_connections_style()
                )
        
        # Handle duck grabbing logic
        current_time = time.time()
        
        if hand_positions and hand_gestures:
            primary_hand_pos = hand_positions[0]
            primary_gesture = hand_gestures[0]
            
            # Store for smoothing
            self.last_hand_positions.append(primary_hand_pos)
            if len(self.last_hand_positions) > 5:
                self.last_hand_positions.pop(0)
            
            # Smooth hand position
            if self.last_hand_positions:
                smooth_pos = np.mean(self.last_hand_positions, axis=0)
                primary_hand_pos = tuple(smooth_pos)
            
            # Visualize hand position
            hand_pixel_x = int(primary_hand_pos[0] * width)
            hand_pixel_y = int(primary_hand_pos[1] * height)
            
            # Draw hand center
            cv2.circle(processed, (hand_pixel_x, hand_pixel_y), 15, 
                      (0, 255, 0) if primary_gesture == "pinch" else (255, 255, 0), -1)
            cv2.circle(processed, (hand_pixel_x, hand_pixel_y), 15, (255, 255, 255), 2)
            
            # Draw gesture text
            cv2.putText(processed, f"Gesture: {primary_gesture}", 
                       (hand_pixel_x - 40, hand_pixel_y - 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, 
                       (0, 255, 0) if primary_gesture == "pinch" else (255, 255, 0), 2)
            
            # Handle grabbing logic
            if primary_gesture == "pinch":
                if self.grabbed_duck_id is None:
                    # Look for duck to grab
                    for duck in self.objects:
                        duck_pos = duck['position']
                        is_near, distance = self.check_hand_near_duck(primary_hand_pos, duck_pos)
                        
                        if is_near:
                            self.grabbed_duck_id = duck['id']
                            self.grab_start_time = current_time
                            self.grab_distance = distance
                            print(f"🖐️  PINCH! Grabbed Duck #{duck['id']}")
                            break
                else:
                    # Move grabbed duck with hand
                    for duck in self.objects:
                        if duck['id'] == self.grabbed_duck_id:
                            # Smooth movement
                            duck['position']['x'] = primary_hand_pos[0]
                            duck['position']['y'] = primary_hand_pos[1]
                            break
            else:
                # Release if not pinching
                if self.grabbed_duck_id is not None:
                    grab_duration = current_time - self.grab_start_time if self.grab_start_time else 0
                    print(f"🖐️  Released Duck #{self.grabbed_duck_id} after {grab_duration:.1f}s")
                    self.grabbed_duck_id = None
                    self.grab_start_time = None
        else:
            # No hand detected, release duck
            if self.grabbed_duck_id is not None:
                print(f"🖐️  Hand lost, released Duck #{self.grabbed_duck_id}")
                self.grabbed_duck_id = None
                self.grab_start_time = None
        
        # Draw all ducks
        for duck in self.objects:
            is_grabbed = (self.grabbed_duck_id == duck['id'])
            self.draw_advanced_duck(processed, duck, is_grabbed)
        
        # ====== UI OVERLAY ======
        # Top bar
        cv2.rectangle(processed, (0, 0), (width, 120), (0, 0, 0, 200), -1)
        
        # Title
        cv2.putText(processed, "ADVANCED AR DUCKS - HAND TRACKING", (20, 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        
        # Stats
        stats_text = f"Ducks: {len(self.objects)} | FPS: {self.fps:.1f} | "
        stats_text += f"Hands: {len(hand_positions)}"
        if self.grabbed_duck_id:
            stats_text += f" | GRABBED: Duck #{self.grabbed_duck_id}"
        
        cv2.putText(processed, stats_text, (20, 80),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 200), 2)
        
        # Instructions
        instructions = [
            "PINCH GESTURE (thumb + index) near duck to GRAB",
            "Move hand while pinching to DRAG duck",
            "Release pinch to DROP duck",
            "Tap in Flutter app to place new ducks"
        ]
        
        for i, instruction in enumerate(instructions):
            cv2.putText(processed, instruction, (20, 110 + i * 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 255), 1)
        
        # Grid for depth perception
        for i in range(0, width, 100):
            cv2.line(processed, (i, 0), (i, height), (50, 50, 50, 50), 1)
        for i in range(0, height, 100):
            cv2.line(processed, (0, i), (width, i), (50, 50, 50, 50), 1)
        
        return processed
    
    def camera_loop(self):
        """Camera processing loop"""
        while self.is_running and self.camera and self.camera.isOpened():
            try:
                ret, frame = self.camera.read()
                if ret and frame is not None:
                    # Flip horizontally for mirror effect
                    frame = cv2.flip(frame, 1)
                    
                    processed = self.process_frame_with_advanced_hands(frame)
                    
                    with self.frame_lock:
                        self.current_frame = processed
                    
                    # Calculate FPS
                    self.frame_count += 1
                    current_time = time.time()
                    if current_time - self.last_fps_time >= 1.0:
                        self.fps = self.frame_count / (current_time - self.last_fps_time)
                        self.frame_count = 0
                        self.last_fps_time = current_time
                
                time.sleep(0.016)  # ~60 FPS
                
            except Exception as e:
                print(f"Camera error: {e}")
                time.sleep(0.1)
    
    def simulation_loop(self):
        """Simulation mode"""
        width, height = 1280, 720
        
        while self.is_running:
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame[:] = (30, 30, 50)
            
            # Create fancy background
            for i in range(0, width, 50):
                cv2.line(frame, (i, 0), (i, height), (40, 40, 60), 1)
            for i in range(0, height, 50):
                cv2.line(frame, (0, i), (width, i), (40, 40, 60), 1)
            
            # Draw center crosshair
            cv2.drawMarker(frame, (width//2, height//2), (100, 100, 255), 
                          cv2.MARKER_CROSS, 40, 2)
            
            # Draw ducks
            for duck in self.objects:
                self.draw_advanced_duck(frame, duck, self.grabbed_duck_id == duck['id'])
            
            # Simulation overlay
            cv2.rectangle(frame, (0, 0), (width, 150), (0, 0, 0, 200), -1)
            cv2.putText(frame, "SIMULATION MODE - CAMERA NOT DETECTED", 
                       (width//2 - 250, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(frame, "Connect a camera for hand tracking", 
                       (width//2 - 200, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 100), 2)
            cv2.putText(frame, f"Ducks: {len(self.objects)}", 
                       (width//2 - 50, 130),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 200), 2)
            
            with self.frame_lock:
                self.current_frame = frame
            
            time.sleep(0.033)  # 30 FPS
    
    def add_duck(self, x, y, scale=0.5, rotation=0.0):
        """Add a duck"""
        duck = {
            'id': self.next_id,
            'position': {'x': x, 'y': y, 'z': 0},
            'rotation': {'x': 0, 'y': rotation, 'z': 0},
            'scale': scale,
            'model': self.model_path,
            'timestamp': time.time()
        }
        
        self.objects.append(duck)
        self.next_id += 1
        print(f"✅ Added Duck #{duck['id']} at ({x:.2f}, {y:.2f})")
        return duck
    
    def update_duck(self, duck_id, scale=None, rotation=None):
        """Update duck properties"""
        for duck in self.objects:
            if duck['id'] == duck_id:
                if scale is not None:
                    duck['scale'] = scale
                if rotation is not None:
                    duck['rotation']['y'] = rotation
                duck['timestamp'] = time.time()
                return True
        return False
    
    def delete_duck(self, duck_id):
        """Delete a duck"""
        self.objects = [d for d in self.objects if d['id'] != duck_id]
        if self.grabbed_duck_id == duck_id:
            self.grabbed_duck_id = None
        print(f"✅ Deleted Duck #{duck_id}")
        return True
    
    def clear_ducks(self):
        """Clear all ducks"""
        count = len(self.objects)
        self.objects.clear()
        self.grabbed_duck_id = None
        print(f"✅ Cleared {count} ducks")
        return count

# Initialize server
server = AdvancedARDuck()

@app.route('/')
def index():
    """Server status"""
    return jsonify({
        'status': 'running',
        'service': 'Advanced AR Duck Server',
        'version': '2.0',
        'features': ['hand_tracking', 'pinch_gesture', '3d_ducks', 'smooth_dragging'],
        'model': server.model_path,
        'ducks_count': len(server.objects),
        'grabbed_duck_id': server.grabbed_duck_id,
        'camera': server.camera is not None,
        'mode': 'Live Camera' if server.camera else 'Simulation',
        'fps': server.fps,
        'hand_tracking': True
    })

@app.route('/camera/frame', methods=['GET'])
def get_frame():
    """Get camera frame"""
    try:
        with server.frame_lock:
            if server.current_frame is None:
                frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                frame[:] = (30, 30, 50)
                cv2.putText(frame, "Initializing...", 
                           (1280//2 - 100, 720//2),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            else:
                frame = server.current_frame
        
        # Encode to JPEG with high quality
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
        _, buffer = cv2.imencode('.jpg', frame, encode_param)
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        
        return jsonify({
            'success': True,
            'frame': frame_base64,
            'objects': server.objects,
            'grabbed_duck_id': server.grabbed_duck_id,
            'fps': server.fps,
            'timestamp': time.time(),
            'resolution': '1280x720'
        })
    except Exception as e:
        print(f"Frame error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/ar/start', methods=['POST'])
def start_ar():
    """Start AR session"""
    server.is_running = True
    return jsonify({'success': True, 'message': 'AR session started'})

@app.route('/ar/stop', methods=['POST'])
def stop_ar():
    """Stop AR session"""
    server.is_running = False
    return jsonify({'success': True, 'message': 'AR session stopped'})

@app.route('/ar/tap', methods=['POST'])
def place_duck():
    """Place a duck at tap location"""
    try:
        data = request.json
        x = data.get('x', 0.5)
        y = data.get('y', 0.5)
        scale = data.get('scale', 0.5)
        rotation = data.get('rotation', {}).get('y', 0.0)
        
        duck = server.add_duck(x, y, scale, rotation)
        
        return jsonify({
            'success': True,
            'duck': duck,
            'message': f'Duck #{duck["id"]} placed successfully!'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/object/<int:obj_id>/update', methods=['POST'])
def update_duck(obj_id):
    """Update duck properties"""
    try:
        data = request.json
        scale = data.get('scale')
        rotation = data.get('rotation', {}).get('y')
        
        success = server.update_duck(obj_id, scale, rotation)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/object/<int:obj_id>', methods=['DELETE'])
def delete_duck(obj_id):
    """Delete duck"""
    success = server.delete_duck(obj_id)
    return jsonify({'success': success})

@app.route('/objects', methods=['GET'])
def get_objects():
    """Get all ducks"""
    return jsonify({'objects': server.objects})

@app.route('/objects/clear', methods=['POST'])
def clear_objects():
    """Clear all ducks"""
    count = server.clear_ducks()
    return jsonify({'success': True, 'count': count})

def get_local_ip():
    """Get local IP"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

if __name__ == '__main__':
    print("=" * 70)
    print("🤖 ADVANCED AR DUCK SERVER WITH HAND TRACKING")
    print("=" * 70)
    print("Features:")
    print("  • MediaPipe Hand Tracking (21 landmarks per hand)")
    print("  • Pinch gesture detection for grabbing")
    print("  • Smooth duck dragging with hand movement")
    print("  • 3D duck rendering with shadows and highlights")
    print("  • Real-time FPS counter")
    print("  • High-resolution 1280x720 output")
    
    local_ip = get_local_ip()
    port = 5000
    
    print(f"\n🌐 Server URL: http://{local_ip}:{port}")
    print(f"📱 Connect Flutter app to this URL")
    
    print("\n🎮 HOW TO GRAB & DRAG DUCKS:")
    print("   1. Show your HAND in camera")
    print("   2. Make a PINCH gesture (thumb + index finger together)")
    print("   3. Bring pinch near a duck (green circle appears)")
    print("   4. Duck will be GRABBED (turns yellow)")
    print("   5. Move your hand while pinching to DRAG duck")
    print("   6. Release pinch to DROP duck")
    
    print("\n📱 FLUTTER CONTROLS:")
    print("   • Tap anywhere to place new ducks")
    print("   • Adjust scale and rotation with sliders")
    print("   • Delete grabbed duck or clear all")
    
    print("\n⚙️  TECHNICAL:")
    print(f"   • Camera: {'Connected ✓' if server.camera else 'Simulation'}")
    print(f"   • Model: {server.model_path}")
    print(f"   • Resolution: 1280x720 @ 60fps target")
    print("=" * 70)
    print("\n🚀 Starting advanced server...")
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)