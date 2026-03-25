#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import ssl, os, time, json, csv

BROKER     = os.getenv("BROKER_HOST", "broker")
PORT       = int(os.getenv("BROKER_PORT", 8883))
DEVICE_ID  = os.getenv("DEVICE_ID", "device1")
CA         = "/app/certs/ca.crt"
TOPIC      = f"iot/{DEVICE_ID}/telemetry"

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
print(f"[{DEVICE_ID}] Conectado. A enviar telemetria periódica para '{TOPIC}'")

# Envia leituras lidas do ficheiro de dados real do dataset
DATASET_PATH = "/app/data/iot_telemetry_data.csv"

# Se o dataset não existir, espera um pouco para dar tempo de ser criado pelo utilizador/script
while not os.path.exists(DATASET_PATH):
    print(f"[{DEVICE_ID}] A aguardar dataset em {DATASET_PATH}...")
    time.sleep(5)

print(f"[{DEVICE_ID}] A iniciar streaming a partir do dataset: {DATASET_PATH}")

while True:
    with open(DATASET_PATH, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            payload = json.dumps({
                "device_id":   DEVICE_ID,
                "type":        "telemetry",
                "temperature": float(row["temp"]),
                "humidity":    float(row["humidity"]),
                "co":          float(row["co"]),
                "smoke":       float(row["smoke"]),
                "light":       row["light"] == "true",
                "ts":          float(row["ts"])
            })
            client.publish(TOPIC, payload, qos=1)
            print(f"[{DEVICE_ID}] Enviado (dataset real): temp={row['temp']}°C, hum={row['humidity']}%")
            time.sleep(5)   # intervalo fixo → IAT regular → fácil de classificar

EOF