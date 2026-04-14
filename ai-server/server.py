import os
import sqlite3
import time
import socket
import struct
import threading

import joblib
import numpy as np
from nfstream import NFStreamer

DB_PATH           = os.getenv("DB_PATH",           "/app/data/iot_traffic.db")
MODEL_PATH        = os.getenv("MODEL_PATH",        "/app/data/model.joblib")
BINARY_MODEL_PATH = os.getenv("BINARY_MODEL_PATH", "/app/data/binary_model.joblib")

# IPs fixos no docker-compose, assim identificamos o dispositivo sem precisar de decifrar nada
IP_CLASS_MAP = {
    os.getenv("IP_DEVICE1", "172.20.0.10"): os.getenv("CLASS_DEVICE1", "telemetry"),
    os.getenv("IP_DEVICE2", "172.20.0.11"): os.getenv("CLASS_DEVICE2", "event_driven"),
    os.getenv("IP_DEVICE3", "172.20.0.12"): os.getenv("CLASS_DEVICE3", "firmware"),
}
BROKER_IP = os.getenv("BROKER_IP", "172.20.0.2")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS classifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   REAL,
            device_id   TEXT,
            predicted   TEXT,
            confidence  REAL,
            num_packets INTEGER,
            avg_size    REAL,
            std_size    REAL,
            avg_iat     REAL,
            total_bytes INTEGER
        )
    """)
    # tabela para o terminal live do dashboard
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_packets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   REAL,
            src_ip      TEXT,
            dst_ip      TEXT,
            size        INTEGER,
            payload_hex TEXT,
            src_port    INTEGER,
            dst_port    INTEGER,
            ttl         INTEGER
        )
    """)
    # caso a tabela já existisse sem estas colunas (versão antiga)
    for col in ["payload_hex TEXT", "src_port INTEGER", "dst_port INTEGER", "ttl INTEGER"]:
        try:
            conn.execute(f"ALTER TABLE raw_packets ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()
    print("[DB] ok")


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
        features["std_size"], features["avg_iat"],
        features["total_bytes"]
    ))
    conn.commit()
    conn.close()


# esta thread corre em paralelo e captura os pacotes raw para mostrar no terminal do dashboard
# nao interfere com o nfstream, é só para visualizacao
def raw_sniffer():
    try:
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0003))
    except Exception as e:
        print(f"[SNIFFER] nao foi possivel abrir raw socket: {e}")
        return

    last_cleanup = time.time()

    while True:
        try:
            packet, _ = s.recvfrom(65535)
            eth_header = packet[:14]
            eth = struct.unpack('!6s6sH', eth_header)
            eth_protocol = socket.ntohs(eth[2])

            if eth_protocol == 8:  # so IPv4
                ip_header = packet[14:34]
                iph = struct.unpack('!BBHHHBBH4s4s', ip_header)
                protocol = iph[6]
                ttl = iph[5]

                if protocol == 6:  # so TCP
                    s_addr = socket.inet_ntoa(iph[8])
                    d_addr = socket.inet_ntoa(iph[9])

                    if s_addr == BROKER_IP or d_addr == BROKER_IP:
                        size = len(packet)
                        if size > 66:
                            ihl = (iph[0] & 0xF) * 4
                            tcp_header = packet[14+ihl:14+ihl+20]
                            if len(tcp_header) == 20:
                                tcph = struct.unpack('!HHLLBBHHH', tcp_header)
                                src_port = tcph[0]
                                dst_port = tcph[1]
                                tcph_length = tcph[4] >> 4
                                h_size = 14 + ihl + tcph_length * 4
                                data = packet[h_size:]

                                if len(data) > 0:
                                    raw_hex = data[:256].hex()
                                    hex_str = " ".join([raw_hex[i:i+4] for i in range(0, len(raw_hex), 4)])
                                else:
                                    hex_str = "sem payload"

                                conn = sqlite3.connect(DB_PATH, timeout=5)
                                conn.execute(
                                    "INSERT INTO raw_packets (timestamp, src_ip, dst_ip, size, payload_hex, src_port, dst_port, ttl) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                    (time.time(), s_addr, d_addr, size, hex_str, src_port, dst_port, ttl)
                                )
                                conn.commit()
                                conn.close()

            # limpar de vez em quando para nao encher o disco
            now = time.time()
            if now - last_cleanup > 10:
                conn = sqlite3.connect(DB_PATH, timeout=5)
                conn.execute("DELETE FROM raw_packets WHERE id NOT IN (SELECT id FROM raw_packets ORDER BY id DESC LIMIT 300)")
                conn.commit()
                conn.close()
                last_cleanup = now

        except Exception:
            pass


def load_model(path, label):
    if not os.path.exists(path):
        print(f"[AI] modelo nao encontrado: {path}")
        return None
    bundle = joblib.load(path)
    clf = bundle["model"]
    print(f"[AI] {label} carregado -> classes: {list(clf.classes_)}")
    return clf


def run(clf, clf_bin=None):
    print("[NFStream] a iniciar captura em eth0 (porta 8883)...")

    # active_timeout=10s significa que a cada 10s temos uma amostra por dispositivo
    # experimentei com 5s mas havia demasiado ruido nas features
    streamer = NFStreamer(
        source="eth0",
        bpf_filter="tcp port 8883",
        statistical_analysis=True,
        active_timeout=10
    )

    for flow in streamer:
        src_ip = flow.src_ip
        dst_ip = flow.dst_ip

        # so nos interessa trafego dos dispositivos para o broker
        if src_ip not in IP_CLASS_MAP or dst_ip != BROKER_IP:
            continue

        features = {
            "num_packets": flow.bidirectional_packets,
            "avg_size":    flow.bidirectional_mean_ps,
            "std_size":    flow.bidirectional_stddev_ps,
            "avg_iat":     flow.bidirectional_mean_piat_ms / 1000.0,
            "total_bytes": flow.bidirectional_bytes,
        }

        X = [[
            features["num_packets"],
            features["avg_size"],
            features["std_size"],
            features["avg_iat"],
            features["total_bytes"],
        ]]

        predicted  = clf.predict(X)[0]
        proba      = clf.predict_proba(X)[0]
        confidence = round(float(max(proba)) * 100, 1)

        enc_label = clf_bin.predict(X)[0] if clf_bin else "N/A"

        print(f"[AI] {src_ip} -> {predicted} ({confidence}%) | enc={enc_label} | "
              f"pkts={features['num_packets']} avg_size={features['avg_size']:.0f}B "
              f"iat={features['avg_iat']:.3f}s bytes={features['total_bytes']}")

        save_classification(src_ip, predicted, confidence, features)


# --- main ---
print("[SERVER] a arrancar...")

init_db()

clf     = load_model(MODEL_PATH, "modelo principal")
clf_bin = load_model(BINARY_MODEL_PATH, "modelo binario")

if clf is None:
    print("[SERVER] ERRO: modelo nao encontrado. Tens de treinar primeiro:")
    print("  python generate_dataset.py")
    print("  python ai-server/train.py --csv ./data/self_generated.csv --out ./data/model.joblib")
    exit(1)

threading.Thread(target=raw_sniffer, daemon=True).start()
run(clf, clf_bin)
