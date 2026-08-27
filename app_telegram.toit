import dhtxx
import gpio
import gpio.pwm
import http
import net
import encoding.json

// ============================================================================
// GPIO PIN CONFIGURATION
// ============================================================================
PIN-DHT-TOP        ::= 4
PIN-HEATER-TOP     ::= 15
PIN-FAN-TOP-PWM    ::= 19
PIN-FAN-TOP-RELAY  ::= 18  // Relay control for Top Fan 12V power

PIN-DHT-BOTTOM     ::= 5
PIN-HEATER-BOTTOM  ::= 16
PIN-FAN-BOTTOM-PWM ::= 20

PIN-BUZZER         ::= 17

SERVER-IP          ::= "10.40.157.176"
SERVER-PORT        ::= 5080

TEMP-MAX-LIMIT     ::= 60.0
TEMP-MIN-LIMIT     ::= 55.0
HUMID-MAX-SAFE     ::= 70.0

compute-fan-speed temp/float humidity/float -> float:
  if temp >= TEMP-MAX-LIMIT:
    return 1.0 
  if humidity >= HUMID-MAX-SAFE:
    return 0.85
  if humidity > 50.0:
    return 0.30 + ((humidity - 50.0) / (HUMID-MAX-SAFE - 50.0)) * 0.40
  return 0.0

main:
  heater-top    := gpio.Pin PIN-HEATER-TOP    --output
  heater-bottom := gpio.Pin PIN-HEATER-BOTTOM --output
  buzzer        := gpio.Pin PIN-BUZZER        --output
  fan-top-relay := gpio.Pin PIN-FAN-TOP-RELAY --output

  heater-top.set 0
  heater-bottom.set 0
  buzzer.set 0
  fan-top-relay.set 0

  pwm-gen := pwm.Pwm --frequency=25_000
  pwm-fan-top    := pwm-gen.start (gpio.Pin PIN-FAN-TOP-PWM)
  pwm-fan-bottom := pwm-gen.start (gpio.Pin PIN-FAN-BOTTOM-PWM)

  pwm-fan-top.set-duty-factor 0.0
  pwm-fan-bottom.set-duty-factor 0.0

  sensor-top    := dhtxx.Dht11 PIN-DHT-TOP
  sensor-bottom := dhtxx.Dht11 PIN-DHT-BOTTOM
  sleep --ms=500

  network := net.open

  top-heater-on := false
  bot-heater-on := false
  fan-top-duty  := 0.0
  fan-bot-duty  := 0.0
  buzzer-on     := false

  is-batch-active  := false
  process-complete := false

  // Safety interlock state flags (True = Allowed, False = User Forced Off)
  allow-h-top := true
  allow-h-bot := true
  allow-f-top := true
  allow-f-bot := true

  while true:
    // 1. Read Sensors
    read-top := sensor-top.read
    read-bottom := sensor-bottom.read

    t-top := 0.0
    h-top := 0.0
    if read-top != null:
      t-top = read-top.temperature.to-float
      h-top = read-top.humidity.to-float

    t-bot := 0.0
    h-bot := 0.0
    if read-bottom != null:
      t-bot = read-bottom.temperature.to-float
      h-bot = read-bottom.humidity.to-float

    // 2. Hardware Safety Alarm
    buzzer-on = (t-top > (TEMP-MAX-LIMIT + 3.0) or t-bot > (TEMP-MAX-LIMIT + 3.0))
    buzzer.set (buzzer-on ? 1 : 0)

    // 3. Actuator Logic Evaluation
    if is-batch-active and not process-complete and not buzzer-on:
      // Automatic Closed-Loop with User Safety Interlock Overrides
      // --- Top Tier ---
      if t-top >= TEMP-MAX-LIMIT:
        top-heater-on = false
      else if t-top < TEMP-MIN-LIMIT and t-top > 0.0:
        top-heater-on = true

      // Enforce user safety switch for top heater
      if not allow-h-top:
        top-heater-on = false

      fan-top-duty = allow-f-top ? (compute-fan-speed t-top h-top) : 0.0
      fan-top-relay.set (fan-top-duty > 0.0 ? 1 : 0)

      // --- Bottom Tier ---
      if t-bot >= TEMP-MAX-LIMIT:
        bot-heater-on = false
      else if t-bot < TEMP-MIN-LIMIT and t-bot > 0.0:
        bot-heater-on = true

      // Enforce user safety switch for bottom heater
      if not allow-h-bot:
        bot-heater-on = false

      fan-bot-duty = allow-f-bot ? (compute-fan-speed t-bot h-bot) : 0.0

    else:
      // Hard Shut-Off (Idle, Completed, or Emergency)
      top-heater-on = false
      bot-heater-on = false
      fan-top-duty  = 0.0
      fan-bot-duty  = 0.0
      fan-top-relay.set 0

    // Apply to Physical Hardware Pins
    heater-top.set (top-heater-on ? 1 : 0)
    heater-bottom.set (bot-heater-on ? 1 : 0)
    pwm-fan-top.set-duty-factor fan-top-duty
    pwm-fan-bottom.set-duty-factor fan-bot-duty

    // 4. Send Fresh Telemetry & Receive Interlock Status from Flask
    payload := {
      "top_tier": {
        "temp": t-top,
        "humidity": h-top,
        "heater": top-heater-on,
        "fan_speed": (fan-top-duty * 100.0).to-int
      },
      "bottom_tier": {
        "temp": t-bot,
        "humidity": h-bot,
        "heater": bot-heater-on,
        "fan_speed": (fan-bot-duty * 100.0).to-int
      },
      "safety": {"buzzer": buzzer-on}
    }

    ex := catch:
      client := http.Client network
      try:
        response := client.post-json
          --host=SERVER-IP
          --port=SERVER-PORT
          --path="/api/telemetry"
          payload
        if response != null:
          bytes := response.body.read-all
          if bytes.size > 0:
            decoded := json.decode bytes
            if decoded is Map:
              is-batch-active = (decoded.get "is_active") == true
              process-complete = (decoded.get "stop_curing") == true

              locks := decoded.get "interlocks"
              if locks is Map:
                allow-h-top = (locks.get "heater_top") == true
                allow-h-bot = (locks.get "heater_bottom") == true
                allow-f-top = (locks.get "fan_top") == true
                allow-f-bot = (locks.get "fan_bottom") == true
      finally:
        client.close

    if ex != null:
      print "Network Telemetry Error: $ex"

    sleep --ms=2000