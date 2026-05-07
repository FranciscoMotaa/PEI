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
DATASET_PATH = "/app/data/events_dataset.csv"
if not os.path.exists(DATASET_PATH):
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
            is_motion = (row.get("motion") or row.get("smoke") or "false").lower() == "true"
            is_light_change = (row.get("light") or "false").lower() == "true" and random.random() < 0.1
            
            if not is_motion and not is_light_change:
                # Se o dataset for muito grande e sem eventos, força um evento de vez em quando
                if random.random() > 0.95:
                    is_motion = True
                else:
                    continue

            # Mantemos um delay adaptativo para simulação da demo ser rápida
            # Média de 4 segundos entre eventos para garantir captura estável
            wait = random.expovariate(1 / 4)
            time.sleep(max(1, min(wait, 20)))
            
            burst_size = random.randint(1, 3)
            event_type = "motion_detected" if is_motion else "light_switch"

            for _ in range(burst_size):
                payload = json.dumps({
                    "id": DEVICE_ID,
                    "ev": event_type,
                    "ts": int(time.time())
                }) # Reduzido para ~100 bytes para confiança 100%
                client.publish(TOPIC, payload, qos=1)
                print(f"[{DEVICE_ID}] Evento (dataset): {event_type} (freq_media=4s)")
                if burst_size > 1:
                    time.sleep(0.1)  # pequeno delay dentro do burst