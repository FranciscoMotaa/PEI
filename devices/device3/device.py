#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import ssl, os, time, random, json

BROKER     = os.getenv("BROKER_HOST", "broker")
PORT       = int(os.getenv("BROKER_PORT", 8883))
DEVICE_ID  = os.getenv("DEVICE_ID", "device3")
CA         = "/app/certs/ca.crt"
TOPIC      = f"iot/{DEVICE_ID}/firmware"

def connect():
    c = mqtt.Client(client_id=DEVICE_ID, protocol=mqtt.MQTTv5)
    c.tls_set(ca_certs=CA, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    c.tls_insecure_set(True)
    c.connect(BROKER, PORT, keepalive=60)
    c.loop_start()
    return c

def send_firmware(client, version, size_kb):
    print(f"[{DEVICE_ID}] A iniciar firmware update v{version} ({size_kb}KB)...")

    # Notificação de início
    client.publish(TOPIC, json.dumps({
        "device_id": DEVICE_ID,
        "type":      "firmware",
        "phase":     "start",
        "version":   version,
        "size_kb":   size_kb,
        "ts":        time.time()
    }), qos=1)

    # Transferência em chunks — fluxo contínuo e longo
    # Features resultantes: alta contagem de bytes, duração longa, pacotes grandes
    chunk_size = 512
    total_bytes = size_kb * 1024
    data = bytes(random.getrandbits(8) for _ in range(total_bytes))
    chunks = [data[i:i+chunk_size] for i in range(0, total_bytes, chunk_size)]

    for idx, chunk in enumerate(chunks):
        client.publish(TOPIC, chunk, qos=1)
        if idx % 50 == 0:
            pct = int((idx / len(chunks)) * 100)
            print(f"[{DEVICE_ID}] Progresso: {pct}% ({idx}/{len(chunks)} chunks)")
        time.sleep(0.03)  # ~16 KB/s — transferência contínua

    # Notificação de fim
    client.publish(TOPIC, json.dumps({
        "device_id": DEVICE_ID,
        "type":      "firmware",
        "phase":     "complete",
        "version":   version,
        "ts":        time.time()
    }), qos=1)
    print(f"[{DEVICE_ID}] Firmware v{version} concluído!")

print(f"[{DEVICE_ID}] A aguardar broker...")
time.sleep(8)  # aguarda um pouco mais para os outros dispositivos arrancarem

client = connect()
fw_version = 1

# Envia firmware updates periodicamente (simula ciclo de atualizações)
while True:
    size = random.randint(40, 100)  # entre 40KB e 100KB
    send_firmware(client, f"2.{fw_version}.0", size)
    fw_version += 1
    print(f"[{DEVICE_ID}] Próximo update em 30s...")
    time.sleep(30)  # pausa entre updates
