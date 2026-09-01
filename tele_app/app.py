from flask import Flask, render_template, request, jsonify
from datetime import datetime
import threading
import time
import requests

app = Flask(__name__)

# --- Telegram Credentials ---
TELEGRAM_TOKEN = "Your_token"
TELEGRAM_CHAT_ID = "Your_ID"

from flask import Flask, render_template, request, jsonify
from datetime import datetime
import threading
import time
import requests



def send_telegram_msg(message: str, chat_id=TELEGRAM_CHAT_ID):
    if not TELEGRAM_TOKEN or "YOUR_" in TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[Telegram] Error: {e}")

# ==============================================================================
# 2. STATE MANAGEMENT
# ==============================================================================
drying_batch = {
    "weight_kg": 1.0,
    "start_time": datetime.now(),
    "duration_minutes": 25.0,
    "is_active": False,
    "is_complete": False,
    "milestones_hit": set(),
    "fault_alert_sent": False
}

# Safety Interlocks: True means enabled/allowed in auto mode, False forces OFF
interlocks = {
    "heater_top": True,
    "heater_bottom": True,
    "fan_top": True,
    "fan_bottom": True
}

chamber_state = {
    "top_tier": {"temp": 0.0, "humidity": 0.0, "heater": False, "fan_speed": 0},
    "bottom_tier": {"temp": 0.0, "humidity": 0.0, "heater": False, "fan_speed": 0},
    "safety": {"buzzer": False},
    "weight_kg": 1.0,
    "is_active": False,
    "is_complete": False,
    "progress_percent": 0.0,
    "remaining_time": "25:00",
    "duration_minutes": 25.0,
    "interlocks": interlocks,
    "last_updated": "Waiting..."
}

def format_status_snapshot():
    return (
        f"🔺 *Top Tier:* `{chamber_state['top_tier']['temp']:.1f}°C` | `{chamber_state['top_tier']['humidity']:.1f}%` (Fan: `{chamber_state['top_tier']['fan_speed']}%`)\n"
        f"🔻 *Bottom Tier:* `{chamber_state['bottom_tier']['temp']:.1f}°C` | `{chamber_state['bottom_tier']['humidity']:.1f}%` (Fan: `{chamber_state['bottom_tier']['fan_speed']}%`)\n"
    )

# ==============================================================================
# 3. HTTP API ROUTES
# ==============================================================================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/telemetry", methods=["POST"])
def receive_telemetry():
    global chamber_state, drying_batch, interlocks
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error"}), 400

    chamber_state["top_tier"] = data.get("top_tier", chamber_state["top_tier"])
    chamber_state["bottom_tier"] = data.get("bottom_tier", chamber_state["bottom_tier"])
    chamber_state["safety"] = data.get("safety", chamber_state["safety"])
    chamber_state["last_updated"] = datetime.now().strftime("%H:%M:%S")

    # Critical Alarm
    if chamber_state["safety"].get("buzzer", False) and not drying_batch["fault_alert_sent"]:
        drying_batch["fault_alert_sent"] = True
        send_telegram_msg("🚨 *EMERGENCY OVERHEAT ALERT (>63°C)!* Buzzer triggered.")[cite: 1, 2]
    elif not chamber_state["safety"].get("buzzer", False):
        drying_batch["fault_alert_sent"] = False

    # Timer Calculation
    if drying_batch["is_active"]:
        elapsed = (datetime.now() - drying_batch["start_time"]).total_seconds()
        total_seconds = drying_batch["duration_minutes"] * 60.0

        if elapsed >= total_seconds:
            drying_batch["is_complete"] = True
            drying_batch["is_active"] = False
            progress = 100.0
            remaining_str = "00:00 (Done)"
        else:
            progress = min(100.0, (elapsed / total_seconds) * 100.0)
            rem = max(0, int(total_seconds - elapsed))
            remaining_str = f"{rem // 60:02d}:{rem % 60:02d}"
    else:
        progress = 100.0 if drying_batch["is_complete"] else 0.0
        remaining_str = "00:00 (Complete)" if drying_batch["is_complete"] else "00:00 (Stopped)"

    chamber_state["is_active"] = drying_batch["is_active"]
    chamber_state["is_complete"] = drying_batch["is_complete"]
    chamber_state["progress_percent"] = round(progress, 1)
    chamber_state["remaining_time"] = remaining_str
    chamber_state["interlocks"] = interlocks

    # Milestone Notifications
    milestones = [
        (0, "🚀 *Cinnamon Drying Batch Started*"),
        (25, "📊 *Batch Progress: 25% Completed*"),
        (50, "📊 *Batch Progress: 50% Completed (Halfway)*"),
        (75, "📊 *Batch Progress: 75% Completed*"),
        (100, "🎉 *Cinnamon Curing 100% Complete!*")
    ]
    for stage, title in milestones:
        if stage not in drying_batch["milestones_hit"]:
            if (stage == 0 and drying_batch["is_active"]) or (progress >= stage and stage > 0):
                drying_batch["milestones_hit"].add(stage)
                msg = f"{title}\n⚖️ *Weight:* `{drying_batch['weight_kg']} kg` | ⏱ `{remaining_str}`\n{format_status_snapshot()}"
                if stage == 100:
                    msg += "\n✅ *All heaters and fans are completely powered down.*"
                send_telegram_msg(msg)

    # Return interlock permissions and active batch state to ESP32
    return jsonify({
        "status": "ok",
        "is_active": drying_batch["is_active"],
        "stop_curing": drying_batch["is_complete"],
        "interlocks": interlocks
    }), 200

@app.route("/api/data", methods=["GET"])
def get_data():
    return jsonify(chamber_state), 200

@app.route("/api/start-batch", methods=["POST"])
def start_batch():
    global drying_batch, interlocks
    payload = request.get_json(silent=True) or {}
    weight = float(payload.get("weight_kg", 1.0))
    duration = float(payload.get("duration_minutes", 25.0))

    # Reset all interlocks to allowed on start
    interlocks = {"heater_top": True, "heater_bottom": True, "fan_top": True, "fan_bottom": True}
    
    drying_batch["weight_kg"] = weight
    drying_batch["duration_minutes"] = duration
    drying_batch["start_time"] = datetime.now()
    drying_batch["is_active"] = True
    drying_batch["is_complete"] = False
    drying_batch["milestones_hit"] = set()
    drying_batch["fault_alert_sent"] = False

    chamber_state["weight_kg"] = weight
    chamber_state["duration_minutes"] = duration
    return jsonify({"status": "started"}), 200

@app.route("/api/stop-batch", methods=["POST"])
def stop_batch():
    global drying_batch
    drying_batch["is_active"] = False
    drying_batch["is_complete"] = False
    send_telegram_msg("🛑 *Emergency Stop Activated:* Batch process halted.")
    return jsonify({"status": "stopped"}), 200

@app.route("/api/toggle-interlock", methods=["POST"])
def toggle_interlock():
    """Toggles individual component safety permissions WITHOUT stopping the batch timer."""
    global interlocks
    payload = request.get_json(silent=True) or {}
    device = payload.get("device")
    state = payload.get("state")
    
    if device in interlocks and isinstance(state, bool):
        interlocks[device] = state
        return jsonify({"status": "updated", "interlocks": interlocks}), 200
    return jsonify({"status": "invalid device"}), 400

# Background Telegram Listener
def telegram_listener():
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=10"
            res = requests.get(url, timeout=15).json()
            if res.get("ok"):
                for item in res.get("result", []):
                    offset = item["update_id"] + 1
                    msg = item.get("message", {})
                    text = msg.get("text", "").strip()
                    chat_id = msg.get("chat", {}).get("id")

                    if not text or not chat_id:
                        continue

                    if text.startswith("/status"):
                        stat = (
                            "📊 *CinnaDry Live Status*\n"
                            "─────────────────────────\n"
                            f"⚡ *State:* `{'Active' if drying_batch['is_active'] else 'Idle / Stopped'}`\n"
                            f"⏳ *Progress:* `{chamber_state['progress_percent']}%` ({chamber_state['remaining_time']})\n\n"
                            f"{format_status_snapshot()}"
                        )
                        send_telegram_msg(stat, chat_id=chat_id)
                    elif text.startswith("/stop"):
                        drying_batch["is_active"] = False
                        send_telegram_msg("🛑 *Drying batch stopped via Telegram.*", chat_id=chat_id)
        except Exception:
            time.sleep(2)

if __name__ == "__main__":
    if TELEGRAM_TOKEN and "YOUR_" not in TELEGRAM_TOKEN:
        threading.Thread(target=telegram_listener, daemon=True).start()
    app.run(host="0.0.0.0", port=5080, debug=True)
