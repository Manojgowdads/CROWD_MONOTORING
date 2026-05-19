import paho.mqtt.client as mqtt
import json

MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_TOPIC = "crowd_monitoring/telemetry/manoj"

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✅ Connected to MQTT Broker ({MQTT_BROKER})")
        client.subscribe(MQTT_TOPIC)
        print(f"📡 Subscribed to topic: {MQTT_TOPIC}")
        print("⏳ Waiting for IoT telemetry from Edge Server...\n")
    else:
        print(f"❌ Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        print("="*50)
        print("📥 [IoT NODE RECEIVED TELEMETRY]")
        print(f"👥 Crowd Count: {payload.get('count')}")
        print(f"📊 Density Level: {payload.get('density')}")
        print(f"⚙️ Hardware Status: {payload.get('actuation')}")
        if payload.get('alert'):
            print(f"🚨 ALERT TRIGGERED: {payload.get('alert')}")
        print("="*50)
    except Exception as e:
        print(f"[RAW MESSAGE] {msg.payload.decode()}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

print("Initializing External IoT Node...")
try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print("\nDisconnecting...")
    client.disconnect()
