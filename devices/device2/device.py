#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import ssl, os, time, random, json, csv

BROKER     = os.getenv("BROKER_HOST", "broker")
PORT       = int(os.getenv("BROKER_PORT", 8883))
DEVICE_ID  = os.getenv("DEVICE_ID", "device2")
CA         = "/app/certs/ca.crt"
TOPIC      = f"iot/{DEVICE_ID}/events"

EVENTS = ["motion_detected", "door_opened", "alarm_triggered",
          "button_pressed", "temperature_spike", "intrusion_alert"]

def connect():
    c = mqtt.Client(client_id=DEVICE_ID, protocol=mqtt.MQTTv5)
    c.tls_set(ca_certs=CA, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    c.tls_insecure_set(True)
    c.connect(BROKER, PORT, keepalive=60)
    c.loop_start()
    return c

print(f"[{DEVICE_ID}] A aguardar broker...")
time.sleep(6)

client = connect()
print(f"[{DEVICE_ID}] Conectado. A enviar eventos aleatórios para '{TOPIC}'")

# Eventos lidos a partir do dataset real
DATASET_PATH = "/app/data/iot_telemetry_data.csv"

# Se o dataset não existir, espera um pouco
while not os.path.exists(DATASET_PATH):
    print(f"[{DEVICE_ID}] A aguardar dataset em {DATASET_PATH}...")
    time.sleep(5)

print(f"[{DEVICE_ID}] A iniciar streaming de eventos do dataset: {DATASET_PATH}")

while True:
    with open(DATASET_PATH, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Seleciona apenas as linhas que assinalam eventos (ex: motion = true)
            # Para o dataset continuar a gerar, se não houver motion true, inventamos uns de vez em quando
            is_motion = (row.get("motion", "false").lower() == "true")
            is_light_change = (row.get("light", "false").lower() == "true" and random.random() < 0.1)
            
            if not is_motion and not is_light_change:
                continue

            # Mantemos um delay adaptativo para simulação da demo ser rápida
            wait = random.expovariate(1 / 8)
            time.sleep(max(1, min(wait, 30)))
            
            burst_size = random.randint(1, 3)
            event_type = "motion_detected" if is_motion else "light_switch"

            for _ in range(burst_size):
                payload = json.dumps({
                    "device_id": DEVICE_ID,
                    "type":      "event_driven",
                    "event":     event_type,
                    "ts":        float(row["ts"]),
                    "source":    "user_dataset"
                })
                client.publish(TOPIC, payload, qos=1)
                print(f"[{DEVICE_ID}] Evento (dataset): {event_type} (burst={burst_size})")
                if burst_size > 1:
                    time.sleep(0.1)  # pequeno delay dentro do burst