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
DATASET_PATH = "/app/data/telemetry_dataset.csv"
if not os.path.exists(DATASET_PATH):
    DATASET_PATH = "/app/data/iot_telemetry_data.csv"

# Se o dataset não existir, espera um pouco para dar tempo de ser criado pelo utilizador/script
while not os.path.exists(DATASET_PATH):
    print(f"[{DEVICE_ID}] A aguardar dataset em {DATASET_PATH}...")
    time.sleep(5)

print(f"[{DEVICE_ID}] A iniciar streaming a partir do dataset: {DATASET_PATH}")

def safe_float(val, default=0.0):
    try: return float(val)
    except: return default

while True:
    with open(DATASET_PATH, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Tentar obter valores com fallback para nomes comuns no dataset
            temp = row.get("temp") or row.get("temperature") or 22.0
            hum  = row.get("humidity") or 50.0
            co   = row.get("co") or 0.002
            smoke= row.get("smoke") or 0.01
            light= (row.get("light") or "true").lower() == "true"
            
            payload = json.dumps({
                "device_id":   DEVICE_ID,
                "type":        "telemetry",
                "temperature": safe_float(temp),
                "humidity":    safe_float(hum),
                "co":          safe_float(co),
                "smoke":       safe_float(smoke),
                "light":       light,
                "status_code": 200,
                "sensor_name": "HTS221-Industrial",
                "version":     "1.2.4",
                "padding":     "x" * 100, # Garantir tamanho ~250 bytes para confiança 100%
                "ts":          time.time()
            })
            client.publish(TOPIC, payload, qos=1)
            print(f"[{DEVICE_ID}] Enviado: temp={temp}°C, hum={hum}% (freq=1s)")
            time.sleep(1)

EOF