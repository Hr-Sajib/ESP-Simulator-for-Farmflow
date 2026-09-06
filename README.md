# 🛰️ FarmFlow ESP-Simulator

**A drop-in stand-in for FarmFlow's ESP32 field nodes.** It speaks the exact protocol the real firmware speaks — same JSON keys, same MQTT topic, same hardware-label identity — so the backend, dashboard and demo environment work end-to-end with zero physical hardware.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/MQTT-660066?style=for-the-badge&logo=mqtt&logoColor=white" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" />
</p>

<p align="center">
  <img src="https://i.ibb.co.com/LhhFxWFD/github-banner-hardware-farmflow.jpg" width="49%" alt="FarmFlow hardware" />
  <img src="https://arbora-bucket.s3.us-east-2.amazonaws.com/system+assets/IMAGE+2026-09-05+22%3A26%3A38.jpg" width="49%" alt="FarmFlow dashboard" />
</p>

---

## ✨ Features

**Advanced**
- 🌦️ **Physically plausible telemetry** — readings follow a real solar-noon daylight curve (Dhaka, UTC+6): light and temperature rise and fall with the sun, humidity moves *against* temperature, and soil dries down between waterings instead of jumping randomly, so a 24h chart shows a slope worth reading.
- 🏡 **Multiple environment profiles** — greenhouse, net-house and open-field nodes each get their own temperature swing, humidity baseline and light ceiling, simulating a real mixed-crop farm from one process.
- 🔁 **Protocol-identical to real hardware** — publishes the same payload shape and hardware-label identity (`farmerId`/`fieldId`) as the frozen ESP32 firmware; the backend's device registry can't tell a simulated node from a real one.
- 💓 **Keepalive-aware MQTT client** — an explicit network loop and reconnect backoff, because a client that never sends a keepalive gets silently dropped by the broker after a minute and then publishes into a dead socket with no error at all (a real bug this simulator hit and fixed).
- 🌐 **Production WSGI, not Flask's dev server** — served through Waitress so one slow client on `/values/json` can't stall the sensor-publishing threads sharing the process.

**Also included:** live `/values/json` endpoint for the latest reading per node, actuator command listener (servo / stepper / motor) mirrored from the real firmware's topic.

---

## 🏗️ Architecture

```
 4 simulated nodes ──MQTT (TLS, QoS 1)──▶  HiveMQ Cloud  ──▶  FarmFlow API
 (greenhouse ×2,          topic: sensors/data                  │
  net_house,               commands: commands/{farmer}/{field} │
  open_field)                                                  ▼
                                                          MongoDB + dashboard
```

Each simulated node stands in for the real hardware setup: an **ESP32** with two **DHT11** sensors, two **BH1750** light sensors, two capacitive soil-moisture probes, and a **servo + stepper + DC motor** for shade, venting and irrigation. Swapping this process for the real firmware changes nothing on the server — identity resolution happens entirely on the backend via the device registry.

---

## 🔒 Security (deployment)

Runs on the same hardened, Cloudflare-fronted infrastructure as the rest of FarmFlow — see the [API's security section](https://github.com/Hr-Sajib/FarmFlow-AppServer#-security-deployment) for the full picture. Specific to this service:

- ➤ Binds to **loopback by default**; only opens to all interfaces inside its own container, where Caddy is the only thing that can reach it.
- ➤ Runs as a **non-root user** (`sensors`) inside a minimal Python-slim image, with `cap_drop: ALL` and `no-new-privileges`.
- ➤ MQTT credentials load from environment/`.env`, never hardcoded — the process refuses to start without them.
- ➤ Deploys through the same **Tailscale-authenticated, push-to-deploy CI** as the rest of the stack — no exposed SSH, no manual server access.
- ➤ Credentials file removed from version control history after an early commit accidentally tracked it.

---

## 🆕 Recent changes

- Moved the publish cadence to **two seconds** to match the live dashboard's real-time feel.
- Switched from Flask's development server to **Waitress**, a production-grade pure-Python WSGI server.
- Added a **push-to-deploy** GitHub Actions workflow over Tailscale.
- Fixed a silent-drop bug: added an explicit MQTT network loop + reconnect backoff so the broker's keepalive timeout can't kill publishing without an error.

---

## 🚀 Running it

**Locally:**
```bash
pip install -r requirements.txt
cp .env.example .env   # fill in HIVE_USERNAME / HIVE_PASSWORD
python fakeESP32.py    # publishes on 127.0.0.1:5200
```

**Containerized:**
```bash
docker compose up --build
```

| Endpoint | Purpose |
|---|---|
| `GET /values/json` | Latest reading published by each simulated node |

## 🧭 Known gaps

- Node topology (4 fixed nodes / profiles) is hardcoded rather than configurable — fine for a demo fleet, would want a config file for a larger one.
- No automated tests; correctness is verified by watching the live dashboard receive plausible data.
