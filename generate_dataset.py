"""
generate_dataset.py — Gera dataset de treino a partir dos dispositivos IoT reais
=================================================================================
Lê a base de dados SQLite do sistema, mapeia device_id → classe de tráfego,
e augmenta com amostras sintéticas realistas se necessário.

Uso:
    python generate_dataset.py --db ./data/iot_traffic.db --out ./data/self_generated.csv
"""

import argparse
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

# Mapeamento device_id / IP → classe de tráfego
DEVICE_CLASS_MAP = {
    # Suporte aos IPs reais fixados no docker-compose
    "172.20.0.10": "telemetry",
    "172.20.0.11": "event_driven",
    "172.20.0.12": "firmware",
    # Passado (legado se existir BD antiga)
    "device1": "telemetry",
    "device2": "event_driven",
    "device3": "firmware",
}

FEATURE_COLS = ["num_packets", "avg_size", "std_size", "avg_iat", "total_bytes"]
LABEL_COL    = "traffic_class"
MIN_SAMPLES  = 500   # mínimo por classe para treino fiável


def read_from_db(db_path: str) -> pd.DataFrame:
    """Lê as classificações da BD e mapeia device_id para classe."""
    conn = sqlite3.connect(db_path)
    
    # Verifica primeiro se a tabela existe (o ficheiro pode ter sido criado vazio pelo dashboard)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='classifications'")
    if not cursor.fetchone():
        print("[GEN] Tabela 'classifications' não existe na BD. A gerar apenas dados sintéticos...")
        conn.close()
        return pd.DataFrame(columns=FEATURE_COLS + [LABEL_COL])

    df = pd.read_sql("SELECT device_id, num_packets, avg_size, std_size, avg_iat, total_bytes FROM classifications", conn)
    conn.close()

    df[LABEL_COL] = df["device_id"].map(DEVICE_CLASS_MAP)
    df = df.dropna(subset=[LABEL_COL])  # remove device_ids desconhecidos
    print(f"[GEN] BD: {len(df)} registos encontrados.")
    print(f"[GEN] Distribuição atual:\n{df[LABEL_COL].value_counts()}\n")
    return df[FEATURE_COLS + [LABEL_COL]]


def generate_synthetic(traffic_class: str, n: int) -> pd.DataFrame:
    """
    Gera n amostras sintéticas realistas para cada classe.
    Distribuições baseadas nos padrões reais dos dispositivos.
    """
    rng = np.random.default_rng(42)
    rows = []

    if traffic_class == "telemetry":
        # device1: envio a cada ~5s. Com ACKs TCP/TLS as médias na rede descem.
        for _ in range(n):
            num_pkts   = rng.integers(15, 30)
            avg_size   = rng.uniform(140, 160)
            std_size   = rng.uniform(50, 150)
            avg_iat    = rng.uniform(1.8, 2.5)
            total_b    = int(num_pkts * avg_size)
            rows.append([num_pkts, avg_size, std_size, avg_iat, total_b, "telemetry"])

    elif traffic_class == "event_driven":
        # device2: bursts aleatórios, mas features similares à telemetria só que mais irregulares
        for _ in range(n):
            num_pkts   = rng.integers(15, 60)
            avg_size   = rng.uniform(130, 250)
            std_size   = rng.uniform(100, 300)
            avg_iat    = rng.exponential(scale=2.5)
            total_b    = int(num_pkts * avg_size)
            rows.append([num_pkts, avg_size, std_size, avg_iat, total_b, "event_driven"])

    elif traffic_class == "firmware":
        # device3: chunks TCP (MTU ~1500 ou TLS ~600), fluxo intenso
        for _ in range(n):
            num_pkts   = rng.integers(20, 300)
            avg_size   = rng.uniform(500, 650)          
            std_size   = rng.uniform(50, 120)           
            avg_iat    = rng.uniform(0.010, 1.80)      
            total_b    = int(num_pkts * avg_size)
            rows.append([num_pkts, avg_size, std_size, avg_iat, total_b, "firmware"])

    return pd.DataFrame(rows, columns=FEATURE_COLS + [LABEL_COL])


def build_dataset(df_real: pd.DataFrame) -> pd.DataFrame:
    """Combina dados reais com sintéticos para atingir MIN_SAMPLES por classe."""
    frames = [df_real]

    for cls in DEVICE_CLASS_MAP.values():
        real_count = len(df_real[df_real[LABEL_COL] == cls])
        needed = max(0, MIN_SAMPLES - real_count)
        if needed > 0:
            print(f"[GEN] '{cls}': {real_count} reais + {needed} sintéticos = {real_count + needed}")
            frames.append(generate_synthetic(cls, needed))
        else:
            print(f"[GEN] '{cls}': {real_count} reais (suficiente)")

    combined = pd.concat(frames, ignore_index=True).sample(frac=1, random_state=42)
    print(f"\n[GEN] Dataset final: {len(combined)} registos.")
    print(f"[GEN] Classes:\n{combined[LABEL_COL].value_counts()}\n")
    return combined


def main():
    parser = argparse.ArgumentParser(description="Gerar dataset de treino a partir da BD IoT")
    parser.add_argument("--db",  default="./data/iot_traffic.db",   help="Caminho para a BD SQLite")
    parser.add_argument("--out", default="./data/self_generated.csv", help="Caminho do CSV de saída")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"[GEN] BD não encontrada: {args.db}")
        print("[GEN] Certifica-te que o sistema está a correr e já gerou classificações.")
        print("[GEN] A gerar dataset puramente sintético como fallback...")
        df_real = pd.DataFrame(columns=FEATURE_COLS + [LABEL_COL])
    else:
        df_real = read_from_db(args.db)

    df_final = build_dataset(df_real)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    df_final.to_csv(args.out, index=False)
    print(f"[GEN] Guardado em: {args.out}")
    print("[GEN] Agora corre:")
    print(f"       python ai-server/train.py --csv {args.out} --out ./data/model.joblib")


if __name__ == "__main__":
    main()
