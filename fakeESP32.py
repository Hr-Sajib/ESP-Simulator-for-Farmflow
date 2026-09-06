"""
Stand-in for the ESP32 nodes.

It speaks exactly what the real firmware speaks: the same JSON keys, on the
same `sensors/data` topic, identifying itself with the same kind of hardware
label. The backend resolves that label to a field through the device registry,
so nothing here needs to know a field id — swapping this process for a real
node changes nothing on the server.
"""

from flask import Flask, jsonify
import json
import math
import random
import time
import paho.mqtt.client as mqtt
from threading import Thread
import certifi
from dotenv import load_dotenv
import os
from datetime import datetime, timezone

load_dotenv()

# Loopback by default so running this on a laptop does not expose it to the
# local network. In a container it has to bind every interface, or nothing
# outside the container — including the reverse proxy — can reach it.
HOST = os.getenv("SENSORS_HOST", "127.0.0.1")
PORT = int(os.getenv("SENSORS_PORT", "5200"))

MQTT_BROKER = "c29162f3d8f24ad1ae54157ddb08596c.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = os.getenv("HIVE_USERNAME")
MQTT_PASSWORD = os.getenv("HIVE_PASSWORD")

if not MQTT_USERNAME or not MQTT_PASSWORD:
    raise ValueError("Missing MQTT credentials in .env file")

# The topic the firmware publishes on. Identity comes from the payload, not the
# topic, so one topic serves every node.
TOPIC = "sensors/data"

# Dhaka is UTC+6; the daily cycle below is built around local solar noon.
TZ_OFFSET_HOURS = 6

# One entry per physical node. `fieldId` here is the hardware label the node
# was flashed with — the server maps it to a real field via IField.deviceId,
# which is what `npm run link:device` records.
NODES = [
    {"farmerId": "fr1", "fieldId": "fd1", "profile": "greenhouse"},
    {"farmerId": "fr1", "fieldId": "fd2", "profile": "net_house"},
    {"farmerId": "fr1", "fieldId": "fd3", "profile": "open_field"},
    {"farmerId": "fr1", "fieldId": "fd4", "profile": "greenhouse"},
]

PUBLISH_INTERVAL_SECONDS = 5

latest_sensor_values = {}

# Soil dries down between waterings rather than jumping about at random, so the
# 24h chart shows a slope a farmer could actually act on.
soil_state = {node["fieldId"]: random.uniform(45.0, 70.0) for node in NODES}

# How each environment behaves. A net house is cooler and brighter than a
# greenhouse; an open field swings widest and gets full sun.
PROFILES = {
    "greenhouse": {"temp_base": 26.0, "temp_swing": 6.0, "hum_base": 70.0, "light_peak": 12000.0},
    "net_house":  {"temp_base": 24.0, "temp_swing": 7.0, "hum_base": 65.0, "light_peak": 26000.0},
    "open_field": {"temp_base": 23.0, "temp_swing": 9.0, "hum_base": 60.0, "light_peak": 42000.0},
}


def daylight_fraction(now):
    """0 at night, peaking at 1 around local noon."""
    local_hour = (now.hour + now.minute / 60.0 + TZ_OFFSET_HOURS) % 24
    if local_hour < 6 or local_hour > 18:
        return 0.0
    # Half a sine over the twelve daylight hours.
    return math.sin((local_hour - 6) / 12 * math.pi)


def generate_sensor_values(node):
    """Readings that follow the time of day, so charts have a shape."""
    now = datetime.now(timezone.utc)
    sun = daylight_fraction(now)
    profile = PROFILES[node["profile"]]

    temperature = profile["temp_base"] + profile["temp_swing"] * sun + random.uniform(-0.4, 0.4)
    # Humidity moves against temperature — warm air holds more before saturating.
    humidity = profile["hum_base"] - 18.0 * sun + random.uniform(-1.5, 1.5)
    light = profile["light_peak"] * sun + random.uniform(0, 40)

    # Soil dries faster in the sun, and is topped up when it runs low.
    field_id = node["fieldId"]
    soil_state[field_id] -= (0.05 + 0.25 * sun)
    if soil_state[field_id] < 30.0:
        soil_state[field_id] = random.uniform(68.0, 78.0)
    soil = soil_state[field_id] + random.uniform(-0.3, 0.3)

    return {
        "temperature": round(temperature, 2),
        "humidity": round(max(0.0, min(100.0, humidity)), 2),
        "soil_moisture": round(max(0.0, min(100.0, soil)), 2),
        "light_intensity": round(max(0.0, light), 2),
        "farmerId": node["farmerId"],
        "fieldId": field_id,
        "timeStamp": now.isoformat(),
    }


def sensor_publisher_loop(node, interval):
    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.tls_set(ca_certs=certifi.where())

    # Without a network loop paho never sends a keepalive, so the broker drops
    # the connection after a minute of quiet and every publish afterwards goes
    # into a dead socket — silently, with no error and no reconnect. That is
    # what made this process look alive for hours while nothing arrived.
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()

    while True:
        sensor_data = generate_sensor_values(node)
        # Real JSON, not a Python dict repr — the firmware sends JSON, and the
        # backend should not have to repair quotes to read a message.
        client.publish(TOPIC, json.dumps(sensor_data), qos=1)
        print(f"[{node['farmerId']}-{node['fieldId']}] -> {TOPIC}: {sensor_data}", flush=True)
        latest_sensor_values[f"{node['farmerId']}_{node['fieldId']}"] = sensor_data
        time.sleep(interval)


app = Flask(__name__)


@app.route('/values/json', methods=['GET'])
def get_sensor_values_json():
    if latest_sensor_values:
        return jsonify(latest_sensor_values)
    return {"error": "No data available"}, 404


if __name__ == "__main__":
    for node in NODES:
        Thread(
            target=sensor_publisher_loop,
            args=(node, PUBLISH_INTERVAL_SECONDS),
            daemon=True,
        ).start()

    app.run(host=HOST, port=PORT)
