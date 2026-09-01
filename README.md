# CinnaDry: IoT-Based Dual-Tier Cinnamon Curing Controller

An automated, closed-loop microclimate dehydration chamber built on the ESP32-S2 running Toit. Regulates temperature and humidity independently across two drying racks using solid-state heating elements, variable 25 kHz PWM CPU exhaust fans, and a 12V power-cut relay, backed by a Flask web dashboard and Telegram bot milestone notifications.

---

## 1. Problem & Context

* **Crop Vulnerability:** Temperatures exceeding 60°C destroy delicate cinnamon essential and aetheric oils.
* **Spoilage Prevention:** Moisture content must be reduced below 50% rapidly to stop mold growth.
* **Thermal Stratification:** Traditional sheds overheat upper shelves while bottom shelves stay damp.
* **Solution:** Independent dual-tier closed-loop microclimate regulation.

---

## 2. Hardware Pinout

| Peripheral | Component | ESP32-S3 Pin | Purpose |
| :--- | :--- | :--- | :--- |
| **Top Sensor** | DHT11 | `GPIO 4` | Top-tier temperature & humidity sampling |
| **Top Heater** | SSR Module | `GPIO 15` | Switches top heating element |
| **Top Fan PWM** | 4-Pin CPU Fan | `GPIO 19` | 25 kHz PWM variable speed signal |
| **Top Fan Relay** | Relay Module | `GPIO 18` | 12V DC power cut-off for 0 RPM stop |
| **Bottom Sensor** | DHT11 | `GPIO 5` | Bottom-tier temperature & humidity sampling |
| **Bottom Heater** | SSR Module | `GPIO 16` | Switches bottom heating element |
| **Bottom Fan PWM** | 4-Pin CPU Fan | `GPIO 20` | 25 kHz PWM variable speed signal |
| **Safety Buzzer** | Active Buzzer | `GPIO 17` | Audible over-temperature alarm (>63°C) |

---

## 3. Core Control Logic

* **Temperature Hysteresis:** Maintained strictly between **55°C** (reheat trigger) and **60°C** (cutoff).
* **Proportional Fan PWM:**
  * `< 50% RH`: 0% speed (Relay cuts 12V power)
  * `50% - 70% RH`: Duty cycle scales from 30% to 70%
  * `≥ 70% RH` or `≥ 60°C`: Spools to 85%–100% for rapid exhaust
* **Emergency Alarm:** Temperature `> 63°C` activates the buzzer, cuts heaters, and dispatches an emergency Telegram alert.

---

## 4. Software & Interfaces

* **Batch Sizing:** Entering batch weight (kg) auto-calculates drying duration ($10\text{ min base} + 15\text{ min/kg}$) while remaining fully editable.
* **Web Dashboard:** Real-time dials, spinning PWM fan animations, glowing heater indicators, and safety interlock override switches.
* **Telegram Bot:**
  * Auto milestones sent at **0% (Start)**, **25%**, **50%**, **75%**, and **100% (Complete)**.
  * Interactive on-demand commands: `/status` and `/stop`.

---

## 5. Quickstart

### 1. Backend Setup and jag reference commands
```bash
pip install flask requests
python app.py

# Discover connected ESP32 devices on local network / USB
jag scan

# Check Jaguar CLI and device firmware versions
jag version

# Install required external package dependencies
jag pkg install [github.com/toitlang/pkg-dhtxx](https://github.com/toitlang/pkg-dhtxx)
jag pkg install [github.com/toitlang/pkg-http@v2](https://github.com/toitlang/pkg-http@v2)

# Run firmware live on the ESP32 (streaming serial logs to terminal)
jag run app.toit

# Flash firmware permanently to run as an autonomous background container
jag container install cinnadry app.toit

# List all active containers running on the ESP32
jag container list

# Remove/uninstall a running background container
jag container uninstall cinnadry
