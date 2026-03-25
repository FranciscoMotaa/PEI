"""
server.py — Analisador Passivo de Tráfego IoT (Transport Layer)
================================================================
Lê metadados de pacotes TCP gerados pelo tshark (sem decifrar o payload TLS).
Identifica dispositivos pelo ip.src (visível nos headers IP sem decifrar).
Classifica fluxos baseado em:
  - frame.len    → tamanho do pacote IP (inclui headers TCP+IP, não o payload MQTT)
  - IAT          → inter-arrival time entre pacotes consecutivos do mesmo fluxo
  - ip.src       → identifica o dispositivo (sem decifrar)

Filosofia: observador passivo que só vê o que está disponível na camada de rede/transporte.
"""

import os
import sqlite3
import time
import csv
from collections import defaultdict

import joblib
import numpy as np

# ── Configuração ──────────────────────────────────────────────────────────────
FLOW_FIELDS  = os.getenv("FLOW_FIELDS",  "/captures/flow_fields.csv")
DB_PATH      = os.getenv("DB_PATH",      "/app/data/iot_traffic.db")
MODEL_PATH   = os.getenv("MODEL_PATH",   "/app/data/model.joblib")
BINARY_MODEL_PATH = os.getenv("BINARY_MODEL_PATH", "/app/data/binary_model.joblib")

# Mapeamento IP → classe de tráfego (configurável por variáveis de ambiente)
# O IP é visível nos headers IP sem decifrar o payload TLS.
IP_CLASS_MAP = {
    os.getenv("IP_DEVICE1", "172.20.0.10"): os.getenv("CLASS_DEVICE1", "telemetry"),
    os.getenv("IP_DEVICE2", "172.20.0.11"): os.getenv("CLASS_DEVICE2", "event_driven"),
    os.getenv("IP_DEVICE3", "172.20.0.12"): os.getenv("CLASS_DEVICE3", "firmware"),
}
BROKER_IP = os.getenv("BROKER_IP", "172.20.0.2")

WINDOW_SIZE  = 20    # pacotes por janela de classificação
WINDOW_SLIDE = 10    # slide da janela (overlap de 50%)

# ── Base de dados ─────────────────────────────────────────────────────────────
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS classifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   REAL,
            device_id   TEXT,    -- ip.src do dispositivo
            predicted   TEXT,    -- classe de tráfego (telemetry/event_driven/firmware)
            confidence  REAL,
            num_packets INTEGER, -- pacotes na janela
            avg_size    REAL,    -- média de frame.len (bytes, camada IP)
            std_size    REAL,    -- desvio padrão de frame.len
            avg_iat     REAL,    -- média de inter-arrival time (segundos)
            total_bytes INTEGER  -- soma de frame.len na janela
        )
    """)
    conn.commit()
    conn.close()
    print("[DB] Base de dados inicializada.")


def save_classification(device_ip, predicted, confidence, features):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO classifications
        (timestamp, device_id, predicted, confidence,
         num_packets, avg_size, std_size, avg_iat, total_bytes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        time.time(), device_ip, predicted, confidence,
        features["num_packets"], features["avg_size"],
        features["std_size"],    features["avg_iat"],
        features["total_bytes"]
    ))
    conn.commit()
    conn.close()


# ── Modelos ───────────────────────────────────────────────────────────────────
def load_model(path, name):
    if not os.path.exists(path):
        print(f"[AI] {name} não encontrado: {path} — a saltar.")
        return None
    bundle = joblib.load(path)
    clf    = bundle["model"]
    print(f"[AI] {name} carregado. Classes: {bundle.get('classes', list(clf.classes_))}")
    return clf


# ── Extração de features (transporte — sem decifrar) ─────────────────────────
def extract_features(packets: list) -> dict:
    """
    Extrai features da camada de transporte.
    - sizes: frame.len (tamanho do pacote IP, visível sem decifrar)
    - iats:  inter-arrival times calculados dos timestamps de chegada
    Nunca acede ao conteúdo do payload TLS/MQTT.
    """
    sizes = [p["size"] for p in packets]
    times = [p["ts"]   for p in packets]

    iats = [times[i+1] - times[i]
            for i in range(len(times)-1)] if len(times) > 1 else [0]

    return {
        "num_packets": len(packets),
        "avg_size":    float(np.mean(sizes)),
        "std_size":    float(np.std(sizes)),
        "avg_iat":     float(np.mean(iats)),
        "total_bytes": int(np.sum(sizes)),
    }


# ── Janelas por fluxo ─────────────────────────────────────────────────────────
flow_windows = defaultdict(list)   # ip.src → lista de pacotes


def classify_flow(src_ip, clf, clf_bin=None):
    """Classifica quando a janela de WINDOW_SIZE pacotes estiver cheia."""
    packets = flow_windows[src_ip]
    if len(packets) < WINDOW_SIZE:
        return

    features = extract_features(packets)
    X = [[
        features["num_packets"],
        features["avg_size"],
        features["std_size"],
        features["avg_iat"],
        features["total_bytes"],
    ]]

    # Classificação de comportamento (telemetry / event_driven / firmware)
    predicted  = clf.predict(X)[0]
    proba      = clf.predict_proba(X)[0]
    confidence = round(float(max(proba)) * 100, 1)

    # Classificação binária (Encrypted / Non-Encrypted)
    enc_label = clf_bin.predict(X)[0] if clf_bin else "N/A"

    device_label = IP_CLASS_MAP.get(src_ip, src_ip)
    print(f"[AI] {src_ip} ({device_label}) → {predicted} ({confidence}%) | {enc_label} | "
          f"pkts={features['num_packets']} "
          f"avg_size={features['avg_size']:.0f}B "
          f"avg_iat={features['avg_iat']:.3f}s "
          f"total={features['total_bytes']}B")

    save_classification(src_ip, predicted, confidence, features)

    # Sliding window
    flow_windows[src_ip] = packets[WINDOW_SLIDE:]


# ── Leitura do ficheiro de campos tshark ─────────────────────────────────────
def tail_flow_fields(path: str):
    """
    Lê o ficheiro CSV gerado pelo tshark linha a linha, em modo tail.
    Cada linha contém: frame.time_epoch, frame.len, ip.src, ip.dst
    """
    print(f"[CAPTURE] A aguardar ficheiro de campos: {path}")
    while not os.path.exists(path):
        time.sleep(2)
    print(f"[CAPTURE] Ficheiro encontrado. A processar metadados de pacotes...")

    with open(path, "r") as f:
        reader = csv.DictReader(f)
        # Vai para o fim do ficheiro e lê novas linhas
        f.seek(0, 2)   # seek to end

        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue

            # Parse da linha CSV
            try:
                parts = line.strip().split(",")
                if len(parts) < 4:
                    continue
                ts      = float(parts[0])
                size    = int(parts[1])
                src_ip  = parts[2].strip()
                dst_ip  = parts[3].strip()
            except (ValueError, IndexError):
                continue   # linha de header ou malformada

            # Filtrar: só pacotes de dispositivos conhecidos → broker
            if src_ip not in IP_CLASS_MAP:
                continue
            if dst_ip != BROKER_IP:
                continue

            # Acumula pacote na janela do dispositivo (identificado por ip.src)
            flow_windows[src_ip].append({"ts": ts, "size": size})
            classify_flow(src_ip, clf, clf_bin)


# ── Main ──────────────────────────────────────────────────────────────────────
print("[SERVER] A iniciar Analisador Passivo IoT (Transport Layer)...")
print(f"[SERVER] Mapeamento IP→Classe: {IP_CLASS_MAP}")
print(f"[SERVER] Janela: {WINDOW_SIZE} pacotes | Slide: {WINDOW_SLIDE}")

init_db()
clf     = load_model(MODEL_PATH,        "Modelo de tráfego")
clf_bin = load_model(BINARY_MODEL_PATH, "Modelo binário (Encrypted/Non-Encrypted)")

if clf is None:
    print("[SERVER] ERRO: modelo principal não encontrado. Corre:")
    print("  python generate_dataset.py")
    print("  python ai-server/train.py --csv ./data/self_generated.csv --out ./data/model.joblib")
    exit(1)

tail_flow_fields(FLOW_FIELDS)