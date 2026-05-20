
import streamlit as st
import sys
try:
    import cv2
except ImportError as e:
    st.error("🚨 OpenCV Installation Error 🚨")
    st.error(f"Exact Error: `{str(e)}`")
    st.info("Please take a screenshot of this error and send it to me. This will tell me exactly which Linux library Streamlit Cloud is missing.")
    st.stop()

import numpy as np
from PIL import Image
import tempfile
import time
import socket
import qrcode
import pandas as pd
import altair as alt
from fpdf import FPDF
import threading
from flask import Flask, jsonify
import paho.mqtt.publish as mqtt_publish
import json
import av
from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration


from utils import load_model, process_image, process_advanced_frame, determine_crowd_density, TrackerState, send_alert_notification
from database import log_data, get_all_data_as_df, register_user, verify_user, get_all_users_as_df
# --- V5 IoT API Setup ---
api_state = {
    "status": "active",
    "count": 0,
    "density": "Low",
    "actuation": "DOORS UNLOCKED",
    "alert": None
}

app_api = Flask(__name__)
@app_api.route('/api/status', methods=['GET'])
def get_status():
    return jsonify(api_state)

def run_api():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app_api.run(host='0.0.0.0', port=8502, debug=False, use_reloader=False)

if 'api_thread_started' not in st.session_state:
    t = threading.Thread(target=run_api, daemon=True)
    t.start()
    st.session_state['api_thread_started'] = True

# --- V5 MQTT Setup ---
MQTT_BROKER = "test.mosquitto.org"
MQTT_TOPIC = "crowd_monitoring/telemetry/manoj"

def publish_telemetry(state_dict):
    def publish_task():
        try:
            mqtt_publish.single(MQTT_TOPIC, payload=json.dumps(state_dict), hostname=MQTT_BROKER)
        except Exception as e:
            print(f"MQTT Error: {e}")
    threading.Thread(target=publish_task, daemon=True).start()

# Page Setup
st.set_page_config(
    page_title="AI Crowd Monitoring IoT Gateway",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main { background-color: #0E1117; }
    .stMetric { background-color: #1E2130; padding: 15px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    [data-testid="stMetricValue"] { color: #FFFFFF !important; font-weight: bold; }
    [data-testid="stMetricLabel"] { color: #A0AEC0 !important; }
    h1 { color: #00E5FF; font-family: 'Inter', sans-serif; }
    .actuation-box { padding: 20px; border-radius: 10px; text-align: center; font-weight: bold; font-size: 24px; margin-top: 20px; }
    .unlocked { background-color: #2e7d32; color: white; border: 2px solid #4caf50; }
    .locked { background-color: #c62828; color: white; border: 2px solid #f44336; animation: blinker 1s linear infinite; }
    @keyframes blinker { 50% { opacity: 0.5; } }
    </style>
""", unsafe_allow_html=True)

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ''

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def generate_qr(url):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img.convert('RGB')

def generate_pdf_report(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Crowd Monitoring System - Analytical Report", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Total Log Records: {len(df)}", ln=True)
    
    if not df.empty:
        max_count = df['person_count'].max()
        avg_count = int(df['person_count'].mean())
        pdf.cell(200, 10, txt=f"Peak Crowd Count: {max_count}", ln=True)
        pdf.cell(200, 10, txt=f"Average Crowd Count: {avg_count}", ln=True)
        
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, txt="Recent Activity Logs", ln=True)
        pdf.set_font("Arial", size=10)
        for i, row in df.head(20).iterrows():
            pdf.cell(200, 8, txt=f"{row['timestamp']} - Count: {row['person_count']} | Density: {row['density']}", ln=True)
    
    return pdf.output(dest='S').encode('latin-1')

def ring_buzzer():
    try:
        import winsound
        # Run in a separate thread so it doesn't block the video stream
        threading.Thread(target=winsound.Beep, args=(2000, 500), daemon=True).start()
    except ImportError:
        pass

# --- Authentication UI ---
if not st.session_state['logged_in']:
    st.title("👁️ AI Crowd Monitoring IoT Gateway")
    st.subheader("Secure Access Gateway")
    
    tab1, tab2 = st.tabs(["🔑 Login", "📝 Sign Up"])
    
    with tab1:
        st.info("💡 Pro-Tip: Default demo credentials are pre-filled for your convenience!")
        login_user = st.text_input("Username", value="admin", key="login_user")
        login_pass = st.text_input("Password", type="password", value="admin123", key="login_pass")
        if st.button("Login 🚀"):
            if verify_user(login_user, login_pass) or (login_user == "admin" and login_pass == "admin123"):
                st.session_state['logged_in'] = True
                st.session_state['username'] = login_user
                st.success("Access Granted! Loading system...")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Invalid credentials. If you are a new user, please Sign Up.")
                
    with tab2:
        st.info("Create a new secure account in the offline edge database.")
        reg_user = st.text_input("New Username", key="reg_user")
        reg_pass = st.text_input("New Password", type="password", key="reg_pass")
        reg_pass_conf = st.text_input("Confirm Password", type="password", key="reg_pass_conf")
        if st.button("Sign Up 📝"):
            if not reg_user or not reg_pass:
                st.error("Username and Password cannot be empty.")
            elif reg_pass != reg_pass_conf:
                st.error("Passwords do not match.")
            else:
                if register_user(reg_user, reg_pass):
                    st.success("Registration successful! You can now log in using the Login tab.")
                else:
                    st.error("Username already exists in edge database.")
else:
    # --- Main Dashboard ---
    st.sidebar.title(f"Welcome, {st.session_state['username']}!")
    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.session_state['username'] = ''
        st.rerun()

    st.title("👁️ AI Crowd Monitoring IoT Dashboard")
    st.markdown(f"**IoT Edge Server API Live At:** `http://{get_local_ip()}:8502/api/status`")

    # Sidebar Configuration
    st.sidebar.header("Configuration")
    model_options = {
        "YOLOv8 Nano (Fastest)": "yolov8n.pt", 
        "YOLOv8 Small (Balanced)": "yolov8s.pt",
        "YOLOv8 Medium (Accurate)": "yolov8m.pt"
    }
    selected_model_name = st.sidebar.selectbox("Select AI Model", list(model_options.keys()))
    conf_threshold = st.sidebar.slider("Confidence Threshold", 0.1, 1.0, 0.3, 0.05)
    max_capacity = st.sidebar.number_input("Max Capacity Limit", min_value=1, max_value=1000, value=30, step=1)
    
    app_mode = st.sidebar.radio("Input Mode", ["Image", "Video", "Desktop Camera (Local/Fast)", "Mobile Camera (Cloud/WebRTC)", "Multi-Camera Split", "Data Logs", "Mobile Access"])

    st.sidebar.markdown("---")
    st.sidebar.header("Stand-Out Features V6")
    enable_birdseye = st.sidebar.checkbox("🗺️ 3D Bird's-Eye Radar")
    enable_evacuation = st.sidebar.checkbox("🚪➡️🏃‍♂️ AI Evacuation Routing")

    st.sidebar.markdown("---")
    st.sidebar.header("Advanced Features")
    enable_heatmap = st.sidebar.checkbox("🌡️ Heatmap")
    enable_zone = st.sidebar.checkbox("🚧 Restricted Zone")
    enable_proximity = st.sidebar.checkbox("📏 Proximity Alerts")
    enable_crossing = st.sidebar.checkbox("🚶‍♂️ Line Crossing Counter")
    enable_loitering = st.sidebar.checkbox("⏳ Loitering Alerts")
    enable_panic = st.sidebar.checkbox("🏃‍♂️ Panic / Anomaly Detection")
    enable_gender = st.sidebar.checkbox("🚻 AI Gender Estimation")
    if enable_gender:
        st.sidebar.caption("⚠️ *Simulated for high-FPS demo purposes.*")

    st.sidebar.markdown("---")
    st.sidebar.header("IoT Protocols")
    enable_mqtt = st.sidebar.checkbox("📡 Publish to MQTT Broker", value=True)
    enable_logging = st.sidebar.checkbox("💾 Data Logging", value=True)
    enable_email_alerts = st.sidebar.checkbox("🚨 Email/SMS Alerts")

    @st.cache_resource
    def get_model(model_path):
        return load_model(model_path)

    model = get_model(model_options[selected_model_name])
    sample_zone = np.array([[100, 100], [500, 100], [400, 400], [200, 400]], np.int32)
    sample_crossing_line = ((100, 300), (500, 300))

    if app_mode == "Mobile Access":
        st.header("📱 Mobile Access")
        local_ip = get_local_ip()
        url = f"http://{local_ip}:8501"
        col1, col2 = st.columns([1, 2])
        with col1:
            st.image(generate_qr(url), caption=f"Scan to connect")
        with col2:
            st.write("Ensure your phone is on the same Wi-Fi. Scan the QR code to log in remotely.")

    elif app_mode == "Data Logs":
        st.header("Interactive Analytics & Reports 📈")
        df = get_all_data_as_df()
        
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Interactive Chart
            st.subheader("Crowd Trends Over Time")
            chart = alt.Chart(df).mark_area(opacity=0.5, color='#00E5FF').encode(
                x='timestamp:T',
                y='person_count:Q',
                tooltip=['timestamp', 'person_count', 'density']
            ).interactive()
            st.altair_chart(chart, use_container_width=True)

            # Export Section
            st.subheader("Generate Executive Reports")
            col1, col2 = st.columns(2)
            with col1:
                st.download_button("📥 Download Raw CSV", data=df.to_csv(index=False).encode('utf-8'), file_name='logs.csv', mime='text/csv')
            with col2:
                pdf_data = generate_pdf_report(df)
                st.download_button("📄 Download PDF Report", data=pdf_data, file_name='crowd_analytics_report.pdf', mime='application/pdf')

            st.dataframe(df, use_container_width=True)
        else:
            st.info("No data logged yet.")
            
        st.markdown("---")
        st.header("Registered Users Data 👥")
        users_df = get_all_users_as_df()
        
        if not users_df.empty:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.dataframe(users_df, use_container_width=True)
            with col2:
                st.download_button("📥 Download Users CSV", data=users_df.to_csv(index=False).encode('utf-8'), file_name='users_list.csv', mime='text/csv')
        else:
            st.info("No registered users found.")

    elif app_mode == "Multi-Camera Split":
        st.header("Multi-Camera Split-Screen Architecture 🎥🎥")
        st.info("Upload two different videos to simulate concurrent processing of two camera streams.")
        
        col_vid1, col_vid2 = st.columns(2)
        with col_vid1:
            vid1_file = st.file_uploader("Camera 1 Input", type=["mp4", "avi"])
        with col_vid2:
            vid2_file = st.file_uploader("Camera 2 Input", type=["mp4", "avi"])
            
        if vid1_file and vid2_file:
            if st.button("Start Split-Screen Analysis"):
                t1 = tempfile.NamedTemporaryFile(delete=False); t1.write(vid1_file.read())
                t2 = tempfile.NamedTemporaryFile(delete=False); t2.write(vid2_file.read())
                
                cap1 = cv2.VideoCapture(t1.name)
                cap2 = cv2.VideoCapture(t2.name)
                
                c1, c2 = st.columns(2)
                stf1, stf2 = c1.empty(), c2.empty()
                m1, m2 = c1.empty(), c2.empty()
                
                state1, state2 = TrackerState(), TrackerState()
                last_buzzer_time = 0
                count1, count2 = 0, 0
                
                while cap1.isOpened() or cap2.isOpened():
                    ret1, frame1 = cap1.read()
                    ret2, frame2 = cap2.read()
                    
                    if not ret1 and not ret2: break
                    
                    if ret1:
                        af1, count1, state1, loit1, panic1, mmap1 = process_advanced_frame(model, frame1, state1, conf_threshold, False, False, False, False, False, False, False, False, False)
                        stf1.image(cv2.cvtColor(af1, cv2.COLOR_BGR2RGB), use_column_width=True)
                        m1.metric("Cam 1 Count", count1)
                        
                    if ret2:
                        af2, count2, state2, loit2, panic2, mmap2 = process_advanced_frame(model, frame2, state2, conf_threshold, False, False, False, False, False, False, False, False, False)
                        stf2.image(cv2.cvtColor(af2, cv2.COLOR_BGR2RGB), use_column_width=True)
                        m2.metric("Cam 2 Count", count2)
                        
                    count1_val = count1 if ret1 else 0
                    count2_val = count2 if ret2 else 0
                    
                    if count1_val >= max_capacity or count2_val >= max_capacity or determine_crowd_density(count1_val, max_capacity) == "High" or determine_crowd_density(count2_val, max_capacity) == "High":
                        current_time = time.time()
                        if current_time - last_buzzer_time > 1.0:
                            ring_buzzer()
                            last_buzzer_time = current_time
                        
                cap1.release()
                cap2.release()

    elif app_mode in ["Video", "Desktop Camera (Local/Fast)"]:
        st.header(f"{app_mode} Analysis")
        
        cap = None
        if app_mode == "Video":
            uploaded_file = st.file_uploader("Upload Video", type=["mp4", "avi"])
            if uploaded_file is not None:
                tfile = tempfile.NamedTemporaryFile(delete=False) 
                tfile.write(uploaded_file.read())
                if st.button("Start Analysis"):
                    cap = cv2.VideoCapture(tfile.name)
        elif app_mode == "Desktop Camera (Local/Fast)":
            if st.checkbox("Run Webcam"):
                cap = cv2.VideoCapture(0)

        if cap is not None:
            col1, col2 = st.columns([2, 1])
            stframe = col1.empty()
            
            with col2:
                metric_placeholder = st.empty()
                actuation_placeholder = st.empty()
                radar_placeholder = st.empty()
            
            tracker_state = TrackerState()
            frame_count = 0
            last_buzzer_time = 0
            
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret: break
                
                frame = cv2.resize(frame, (640, 480))
                
                annotated_frame, count, tracker_state, is_loitering, is_panic, minimap_img = process_advanced_frame(
                    model, frame, tracker_state, conf_threshold,
                    enable_heatmap, enable_zone, enable_proximity,
                    enable_crossing, enable_loitering, enable_panic, enable_gender, enable_birdseye, enable_evacuation,
                    sample_zone, sample_crossing_line
                )
                density = determine_crowd_density(count, max_capacity)
                
                is_breach = False
                if enable_zone and count > 0:
                    is_breach = True
                
                actuation_status = "DOORS SECURELY LOCKED" if (is_panic or is_breach or density == "High") else "DOORS UNLOCKED"
                actuation_class = "locked" if actuation_status == "DOORS SECURELY LOCKED" else "unlocked"
                
                alert_msg = None
                if is_panic: alert_msg = "PANIC DETECTED"
                elif is_loitering: alert_msg = "LOITERING DETECTED"
                elif density == "High": alert_msg = "HIGH DENSITY"

                if count >= max_capacity or density == "High":
                    current_time = time.time()
                    if current_time - last_buzzer_time > 1.0:
                        ring_buzzer()
                        last_buzzer_time = current_time
                
                api_state["count"] = count
                api_state["density"] = density
                api_state["actuation"] = actuation_status
                api_state["alert"] = alert_msg

                if enable_mqtt and frame_count % 15 == 0:
                    publish_telemetry(api_state)

                if enable_email_alerts:
                    current_time = time.time()
                    if alert_msg and (current_time - tracker_state.last_email_sent > 30):
                        send_alert_notification("Security Alert", alert_msg)
                        tracker_state.last_email_sent = current_time
                        st.sidebar.error(f"🚨 ALERT SENT: {alert_msg}")

                if enable_logging and frame_count % 10 == 0:
                    log_data(count, density)
                
                if frame_count % 2 == 0:
                    annotated_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
                    stframe.image(annotated_frame, use_column_width=True)
                    
                    with metric_placeholder.container():
                        st.metric(label="Current Count", value=count)
                        density_color = "🟢" if density == "Low" else "🟡" if density == "Medium" else "🔴"
                        st.metric(label="Density", value=f"{density_color} {density}")
                        if enable_crossing:
                            st.metric(label="Footfall IN", value=len(tracker_state.crossed_in))
                            st.metric(label="Footfall OUT", value=len(tracker_state.crossed_out))
                        if is_loitering:
                            st.error("🚨 Loitering Detected!")
                        if is_panic:
                            st.error("🏃‍♂️🚨 PANIC DETECTED!")
                    
                    actuation_placeholder.markdown(f'<div class="actuation-box {actuation_class}">🔒 IoT ACTUATION:<br>{actuation_status}</div>', unsafe_allow_html=True)
                    
                    if enable_birdseye and minimap_img is not None:
                        radar_placeholder.image(minimap_img, use_column_width=True)
                    else:
                        radar_placeholder.empty()
                        
                frame_count += 1
                        
            cap.release()

    elif app_mode == "Mobile Camera (Cloud/WebRTC)":
        st.header("📱 Mobile Camera (Cloud WebRTC)")
        st.info("Ensure you are accessing this via HTTPS and grant camera permissions.")

        col1, col2 = st.columns([2, 1])
        with col2:
            metric_placeholder = st.empty()
            actuation_placeholder = st.empty()
            radar_placeholder = st.empty()

        class WebRTCProcessor:
            def __init__(self):
                self.tracker_state = TrackerState()
                self.frame_count = 0
                self.last_buzzer_time = 0
                
                self.conf_threshold = 0.3
                self.enable_heatmap = False
                self.enable_zone = False
                self.enable_proximity = False
                self.enable_crossing = False
                self.enable_loitering = False
                self.enable_panic = False
                self.enable_gender = False
                self.enable_birdseye = False
                self.enable_evacuation = False
                self.max_capacity = 30
                
                self.count = 0
                self.density = "Low"
                self.actuation_status = "DOORS UNLOCKED"
                self.is_loitering = False
                self.is_panic = False
                self.minimap_img = None

            def recv(self, frame):
                img = frame.to_ndarray(format="bgr24")
                img = cv2.resize(img, (640, 480))
                
                annotated_frame, self.count, self.tracker_state, self.is_loitering, self.is_panic, self.minimap_img = process_advanced_frame(
                    model, img, self.tracker_state, self.conf_threshold,
                    self.enable_heatmap, self.enable_zone, self.enable_proximity,
                    self.enable_crossing, self.enable_loitering, self.enable_panic, self.enable_gender, self.enable_birdseye, self.enable_evacuation,
                    sample_zone, sample_crossing_line
                )
                
                self.density = determine_crowd_density(self.count, self.max_capacity)
                
                is_breach = False
                if self.enable_zone and self.count > 0:
                    is_breach = True
                    
                self.actuation_status = "DOORS SECURELY LOCKED" if (self.is_panic or is_breach or self.density == "High") else "DOORS UNLOCKED"
                
                api_state["count"] = self.count
                api_state["density"] = self.density
                api_state["actuation"] = self.actuation_status
                
                alert_msg = None
                if self.is_panic: alert_msg = "PANIC DETECTED"
                elif self.is_loitering: alert_msg = "LOITERING DETECTED"
                elif self.density == "High": alert_msg = "HIGH DENSITY"
                api_state["alert"] = alert_msg
                
                if self.count >= self.max_capacity or self.density == "High":
                    current_time = time.time()
                    if current_time - self.last_buzzer_time > 1.0:
                        ring_buzzer()
                        self.last_buzzer_time = current_time

                if enable_mqtt and self.frame_count % 15 == 0:
                    publish_telemetry(api_state)

                if enable_logging and self.frame_count % 10 == 0:
                    log_data(self.count, self.density)
                    
                self.frame_count += 1
                
                # Burn basic metrics onto frame for zero-lag mobile feedback
                cv2.putText(annotated_frame, f"Count: {self.count} | Density: {self.density}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                
                return av.VideoFrame.from_ndarray(annotated_frame, format="bgr24")

        with col1:
            webrtc_ctx = webrtc_streamer(
                key="crowd-monitor-mobile",
                mode=WebRtcMode.SENDRECV,
                rtc_configuration=RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}),
                video_processor_factory=WebRTCProcessor,
                media_stream_constraints={"video": True, "audio": False},
                async_processing=True,
            )

        if webrtc_ctx.video_processor:
            webrtc_ctx.video_processor.conf_threshold = conf_threshold
            webrtc_ctx.video_processor.enable_heatmap = enable_heatmap
            webrtc_ctx.video_processor.enable_zone = enable_zone
            webrtc_ctx.video_processor.enable_proximity = enable_proximity
            webrtc_ctx.video_processor.enable_crossing = enable_crossing
            webrtc_ctx.video_processor.enable_loitering = enable_loitering
            webrtc_ctx.video_processor.enable_panic = enable_panic
            webrtc_ctx.video_processor.enable_gender = enable_gender
            webrtc_ctx.video_processor.enable_birdseye = enable_birdseye
            webrtc_ctx.video_processor.enable_evacuation = enable_evacuation
            webrtc_ctx.video_processor.max_capacity = max_capacity
            
            with metric_placeholder.container():
                st.metric(label="Current Count", value=webrtc_ctx.video_processor.count)
                density_color = "🟢" if webrtc_ctx.video_processor.density == "Low" else "🟡" if webrtc_ctx.video_processor.density == "Medium" else "🔴"
                st.metric(label="Density", value=f"{density_color} {webrtc_ctx.video_processor.density}")
                if enable_crossing:
                    st.metric(label="Footfall IN", value=len(webrtc_ctx.video_processor.tracker_state.crossed_in))
                    st.metric(label="Footfall OUT", value=len(webrtc_ctx.video_processor.tracker_state.crossed_out))
                if webrtc_ctx.video_processor.is_loitering:
                    st.error("🚨 Loitering Detected!")
                if webrtc_ctx.video_processor.is_panic:
                    st.error("🏃‍♂️🚨 PANIC DETECTED!")
            
            actuation_class = "locked" if webrtc_ctx.video_processor.actuation_status == "DOORS SECURELY LOCKED" else "unlocked"
            actuation_placeholder.markdown(f'<div class="actuation-box {actuation_class}">🔒 IoT ACTUATION:<br>{webrtc_ctx.video_processor.actuation_status}</div>', unsafe_allow_html=True)
            
            if enable_birdseye and webrtc_ctx.video_processor.minimap_img is not None:
                radar_placeholder.image(webrtc_ctx.video_processor.minimap_img, use_column_width=True)

            
    elif app_mode == "Image":
        st.header("Image Analysis")
        uploaded_file = st.file_uploader("Upload Image", type=["jpg", "png"])
        if uploaded_file is not None:
            image = Image.open(uploaded_file).convert('RGB')
            img_array = np.array(image)
            annotated_frame, count = process_image(model, img_array, conf_threshold)
            density = determine_crowd_density(count, max_capacity)
            
            # Trigger buzzer for maximum capacity or overload (High Density)
            if count >= max_capacity or density == "High":
                ring_buzzer()
                
            annotated_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
            st.image(annotated_frame, use_column_width=True)
            c1, c2 = st.columns(2)
            c1.metric("Total Count", count)
            c2.metric(label="Density", value=f"{'🟢' if density=='Low' else '🟡' if density=='Medium' else '🔴'} {density}")
