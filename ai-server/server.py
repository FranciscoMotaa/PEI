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
from collections import defaultdict

import joblib
import numpy as np
from nfstream import NFStreamer

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


# ── Análise Passiva com NFStream ──────────────────────────────────────────────
def start_nfstream(clf, clf_bin=None):
    """
    Usa a framework NFStream para capturar tráfego real-time na interface eth0.
    Agrupa os pacotes em fluxos ativos num timeout contínuo e gera features padrão.
    """
    print("[CAPTURE] A iniciar NFStreamer na interface eth0...")
    # active_timeout=10 significa que converte ligações longas MQTT em 
    # amostras independentes a cada 10 segundos!
    streamer = NFStreamer(source="eth0",
                          bpf_filter="tcp port 8883",
                          statistical_analysis=True,
                          active_timeout=10)

    for flow in streamer:
        src_ip = flow.src_ip
        dst_ip = flow.dst_ip

        # Filtrar: só pacotes de dispositivos conhecidos → broker
        if src_ip not in IP_CLASS_MAP or dst_ip != BROKER_IP:
            continue

        # Extrair features oficiais do NFStream
        features = {
            "num_packets": flow.bidirectional_packets,
            "avg_size":    flow.bidirectional_mean_ps,
            "std_size":    flow.bidirectional_stddev_ps,
            "avg_iat":     flow.bidirectional_mean_piat_ms / 1000.0, # ms para segundos
            "total_bytes": flow.bidirectional_bytes,
        }

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


# ── Main ──────────────────────────────────────────────────────────────────────
print("[SERVER] A iniciar Analisador Passivo IoT (NFStream Edition)...")
print(f"[SERVER] Mapeamento IP→Classe: {IP_CLASS_MAP}")

init_db()
clf     = load_model(MODEL_PATH,        "Modelo de tráfego")
clf_bin = load_model(BINARY_MODEL_PATH, "Modelo binário (Encrypted/Non-Encrypted)")

if clf is None:
    print("[SERVER] ERRO: modelo principal não encontrado. Corre:")
    print("  python generate_dataset.py")
    print("  python ai-server/train.py --csv ./data/self_generated.csv --out ./data/model.joblib")
    exit(1)

start_nfstream(clf, clf_bin)