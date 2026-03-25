# traffic_generator.py
import paho.mqtt.client as mqtt
import time, random, json, threading, ssl

BROKER = "localhost"
PORT   = 8883
CA     = "ca.crt"

def make_client(client_id):
    c = mqtt.Client(client_id=client_id)
    c.tls_set(ca_certs=CA, tls_version=ssl.PROTOCOL_TLS)
    c.connect(BROKER, PORT)
    return c

# ── Classe 1: Telemetria Periódica ──────────────────────────
def periodic_telemetry(duration=120, interval=5):
    c = make_client("sensor-temp")
    for _ in range(duration // interval):
        payload = json.dumps({"temp": round(random.uniform(18, 28), 2),
                              "hum":  round(random.uniform(40, 80), 1)})
        c.publish("iot/telemetry", payload)
        time.sleep(interval)          

# ── Classe 2: Event-Driven ──────────────────────────────────
def event_driven(duration=120):
    c = make_client("sensor-motion")
    t = 0
    while t < duration:
        wait = random.expovariate(1/15)   # Eventos aleatórios (média 15s)
        time.sleep(wait)
        t += wait
        payload = json.dumps({"event": "motion", "zone": random.randint(1,5),
                              "intensity": random.random()})
        c.publish("iot/events", payload)  # Bursts irregulares

# ── Classe 3: Firmware Update ───────────────────────────────
def firmware_update():
    c = make_client("device-fw")
    chunk_size = 1024
    fw_data = "X" * (50 * 1024)   # Simula 50KB de firmware
    for i in range(0, len(fw_data), chunk_size):
        chunk = fw_data[i:i+chunk_size]
        c.publish("iot/firmware", chunk)
        time.sleep(0.05)           # Transferência contínua → fluxo longo

# ── Lançar as 3 threads em simultâneo ───────────────────────
threads = [
    threading.Thread(target=periodic_telemetry),
    threading.Thread(target=event_driven),
    threading.Thread(target=firmware_update),
]
for t in threads: t.start()
for t in threads: t.join()