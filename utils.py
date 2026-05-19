import cv2
import numpy as np
from ultralytics import YOLO
import math
import time
import random
from collections import deque

def load_model(model_name='yolov8n.pt'):
    model = YOLO(model_name)
    return model

def process_image(model, image, conf_threshold=0.3):
    results = model.predict(image, conf=conf_threshold, classes=[0])
    annotated_frame = results[0].plot()
    person_count = len(results[0].boxes)
    return annotated_frame, person_count

def determine_crowd_density(count, max_capacity=30):
    low_threshold = max_capacity * 0.33
    high_threshold = max_capacity * 0.80
    if count < low_threshold:
        return "Low"
    elif count < high_threshold:
        return "Medium"
    else:
        return "High"

# --- Advanced Features ---

def calculate_distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def ccw(A, B, C):
    return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])

def intersect(A, B, C, D):
    return ccw(A,C,D) != ccw(B,C,D) and ccw(A,B,C) != ccw(A,B,D)

class TrackerState:
    def __init__(self):
        self.heatmap_obj = None
        self.track_history = {} 
        self.first_seen = {}    
        self.crossed_in = set()
        self.crossed_out = set()
        self.last_email_sent = 0
        self.demographics_cache = {} 

def extract_demographics(person_img, track_id, cache):
    if track_id in cache:
        return cache[track_id]
    
    # Using Track ID for persistent simulation (doesn't flip-flop)
    random.seed(track_id)
    age = random.randint(19, 45) # Typical expo attendee age range
    
    # Biasing 80% Male / 20% Female for tech expo environment simulation
    gender = "M" if random.random() < 0.8 else "F"
    
    cache[track_id] = (age, gender)
    return cache[track_id]

def get_homography_matrix(frame_shape):
    """Calculates perspective transform matrix for Bird's Eye View."""
    h, w = frame_shape[:2]
    # Source points (Trapezoid representing floor)
    src_pts = np.float32([[w*0.1, h*0.9], [w*0.9, h*0.9], [w*0.7, h*0.3], [w*0.3, h*0.3]])
    # Destination points (Rectangle representing minimap)
    dst_pts = np.float32([[0, 400], [400, 400], [400, 0], [0, 0]])
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    return M, src_pts

def calculate_evacuation_path(frame_shape, centers):
    """Simple BFS pathfinding avoiding dense clusters."""
    h, w = frame_shape[:2]
    grid_size = 20
    cell_h, cell_w = h // grid_size, w // grid_size
    
    # Create grid (0 = safe, 1 = obstacle/crowd)
    grid = np.zeros((grid_size, grid_size), dtype=np.int8)
    
    # Map people to grid and inflate obstacles slightly
    for cx, cy in centers:
        gx, gy = cx // cell_w, cy // cell_h
        if 0 <= gx < grid_size and 0 <= gy < grid_size:
            grid[gy, gx] = 1
            # Inflate crowd radius
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    if 0 <= gy+dy < grid_size and 0 <= gx+dx < grid_size:
                        grid[gy+dy, gx+dx] = 1

    # BFS from bottom-center to top-center (Exit)
    start = (grid_size - 1, grid_size // 2)
    end = (0, grid_size // 2)
    
    queue = deque([start])
    came_from = {start: None}
    
    while queue:
        current = queue.popleft()
        if current == end:
            break
        
        for dy, dx in [(-1,0), (1,0), (0,-1), (0,1), (-1,-1), (-1,1), (1,-1), (1,1)]:
            ny, nx = current[0] + dy, current[1] + dx
            if 0 <= ny < grid_size and 0 <= nx < grid_size:
                if grid[ny, nx] == 0 and (ny, nx) not in came_from:
                    queue.append((ny, nx))
                    came_from[(ny, nx)] = current
                    
    # Reconstruct path
    path = []
    if end in came_from:
        curr = end
        while curr is not None:
            # Convert grid coordinate back to pixel coordinate
            px, py = int(curr[1] * cell_w + cell_w/2), int(curr[0] * cell_h + cell_h/2)
            path.append((px, py))
            curr = came_from[curr]
    return path

def process_advanced_frame(
    model, 
    frame, 
    state: TrackerState, 
    conf_threshold=0.3, 
    enable_heatmap=False, 
    enable_zone=False, 
    enable_proximity=False,
    enable_crossing=False,
    enable_loitering=False,
    enable_panic=False,
    enable_gender=False,
    enable_birdseye=False,
    enable_evacuation=False,
    zone_polygon=None,
    crossing_line=None
):
    results = model.track(frame, conf=conf_threshold, classes=[0], persist=True, tracker="bytetrack.yaml", verbose=False)
    
    # Base annotated frame
    annotated_frame = results[0].plot() if not (enable_proximity or enable_crossing or enable_gender or enable_birdseye or enable_evacuation) else frame.copy()
    
    boxes = results[0].boxes.xyxy.cpu().numpy() if results[0].boxes is not None else []
    track_ids = results[0].boxes.id.int().cpu().tolist() if results[0].boxes is not None and results[0].boxes.id is not None else []
    
    centers = []
    current_ids = set(track_ids)
    loitering_alerts = []
    high_speed_count = 0
    
    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = map(int, box)
        center_x = int((x1 + x2) / 2)
        center_y = int(y2)  # Use bottom center for better homography mapping
        centers.append((center_x, center_y))
        
        if i < len(track_ids):
            tid = track_ids[i]
            
            # Gender Detection (Simulated)
            if enable_gender:
                _, gender = extract_demographics(None, tid, state.demographics_cache)
                cv2.putText(annotated_frame, f"GENDER: {gender}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            
            # Loitering
            if enable_loitering:
                if tid not in state.first_seen:
                    state.first_seen[tid] = time.time()
                else:
                    duration = time.time() - state.first_seen[tid]
                    if duration > 10: 
                        loitering_alerts.append(tid)
                        cv2.putText(annotated_frame, f"LOITERING", (x1, max(y1 - 30, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            # Movement & Panic
            if tid not in state.track_history:
                state.track_history[tid] = []
            
            if enable_panic and len(state.track_history[tid]) > 0:
                prev_pt = state.track_history[tid][-1]
                pixel_speed = calculate_distance(prev_pt, (center_x, center_y))
                if pixel_speed > 30:
                    high_speed_count += 1
                    cv2.putText(annotated_frame, "RUNNING!", (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            state.track_history[tid].append((center_x, center_y))
            if len(state.track_history[tid]) > 30:
                state.track_history[tid].pop(0)
                
            pts = state.track_history[tid]
            
            if enable_crossing or enable_panic:
                for pt in pts:
                    cv2.circle(annotated_frame, pt, 2, (0, 255, 255), -1)
            
            # Line Crossing
            if enable_crossing and crossing_line is not None and len(pts) >= 2:
                p1, p2 = pts[-2], pts[-1]
                L1, L2 = crossing_line
                if intersect(p1, p2, L1, L2):
                    if p2[1] > p1[1]:
                        if tid not in state.crossed_in and tid not in state.crossed_out:
                            state.crossed_in.add(tid)
                    else:
                        if tid not in state.crossed_in and tid not in state.crossed_out:
                            state.crossed_out.add(tid)

    for tid in list(state.first_seen.keys()):
        if tid not in current_ids:
            del state.first_seen[tid]
            if tid in state.track_history:
                del state.track_history[tid]

    count = len(centers)
    is_panic = False
    
    if enable_panic and high_speed_count >= 2:
        is_panic = True
        cv2.putText(annotated_frame, "!!! PANIC DETECTED !!!", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 5)

    # Base Box Drawing (if custom drawing enabled)
    if enable_gender or enable_crossing or enable_proximity or enable_birdseye or enable_evacuation:
        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = map(int, box)
            color = (0, 255, 0)
            if enable_loitering and i < len(track_ids) and track_ids[i] in loitering_alerts:
                color = (0, 0, 255)
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)

    # Bird's Eye View Minimap
    minimap_img = None
    if enable_birdseye:
        minimap_img = np.zeros((400, 400, 3), dtype=np.uint8)
        cv2.putText(minimap_img, "2D RADAR MAP", (120, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        M, src_pts = get_homography_matrix(frame.shape)
        # Draw perspective bounds on main frame
        cv2.polylines(annotated_frame, [np.int32(src_pts)], isClosed=True, color=(255, 255, 0), thickness=2)
        
        if len(centers) > 0:
            pts_array = np.array([centers], dtype=np.float32)
            transformed_pts = cv2.perspectiveTransform(pts_array, M)[0]
            
            for pt in transformed_pts:
                mx, my = int(pt[0]), int(pt[1])
                if 0 <= mx < 400 and 0 <= my < 400:
                    cv2.circle(minimap_img, (mx, my), 6, (0, 255, 0), -1)
                    cv2.circle(minimap_img, (mx, my), 15, (0, 255, 0), 1)

    # Evacuation Routing
    if enable_evacuation:
        path = calculate_evacuation_path(frame.shape, centers)
        cv2.putText(annotated_frame, "EXIT", (frame.shape[1]//2 - 30, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 3)
        if len(path) > 1:
            for i in range(len(path)-1):
                cv2.line(annotated_frame, path[i], path[i+1], (0, 255, 0), 4)
            # Draw glowing effect
            for i in range(len(path)-1):
                cv2.line(annotated_frame, path[i], path[i+1], (100, 255, 100), 2)

    # Draw Line
    if enable_crossing and crossing_line is not None:
        cv2.line(annotated_frame, crossing_line[0], crossing_line[1], (0, 255, 0), 2)
        cv2.putText(annotated_frame, f"IN: {len(state.crossed_in)}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(annotated_frame, f"OUT: {len(state.crossed_out)}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    return annotated_frame, count, state, len(loitering_alerts) > 0, is_panic, minimap_img

def send_alert_notification(subject, message):
    print(f"\n[URGENT ALERT SENT] {subject}\n{message}\n")
