"""
generate_dataset.py — Gera dataset de treino a partir de PCAPs usando NFStream
=================================================================================
Lê caputuras passadas (ex: iot_session.pcap) com a framework académica NFStream,
extrai as estatísticas oficias dos fluxos com um active_timeout idêntico ao 
servidor AI (10s), e combina com dados sintéticos gerados se existirem poucas amostras.
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd
from nfstream import NFStreamer

FEATURE_COLS = ["num_packets", "avg_size", "std_size", "avg_iat", "total_bytes"]
LABEL_COL    = "traffic_class"
MIN_SAMPLES  = 500

DEVICE_CLASS_MAP = {
    "172.20.0.10": "telemetry",
    "172.20.0.11": "event_driven",
    "172.20.0.12": "firmware",
}
BROKER_IP = "172.20.0.2"

def read_from_pcap(pcap_path: str) -> pd.DataFrame:
    print(f"[GEN] A analisar PCAP com NFStream: {pcap_path}")
    if not os.path.exists(pcap_path):
        print("[GEN] Ficheiro pcap não encontrado! Retornando vazio.")
        return pd.DataFrame(columns=FEATURE_COLS + [LABEL_COL])

    streamer = NFStreamer(source=pcap_path,
                          bpf_filter="tcp port 8883",
                          statistical_analysis=True,
                          active_timeout=10)
    rows = []
    
    for flow in streamer:
        src_ip = flow.src_ip
        dst_ip = flow.dst_ip
        
        # Filtro pacotes que não vão em direção ao broker
        if src_ip not in DEVICE_CLASS_MAP or dst_ip != BROKER_IP:
            continue
            
        traffic_class = DEVICE_CLASS_MAP[src_ip]
        
        # O NFStream pode devolver NaN se não houver pacotes suficientes para stdev, etc.
        rows.append([
            flow.bidirectional_packets,
            flow.bidirectional_mean_ps,
            flow.bidirectional_stddev_ps,
            flow.bidirectional_mean_piat_ms / 1000.0, # ms para segundos
            flow.bidirectional_bytes,
            traffic_class
        ])

    df = pd.DataFrame(rows, columns=FEATURE_COLS + [LABEL_COL])
    df = df.fillna(0) # Segurança para fluxos de apenas 1 pacote sem stdev
    print(f"[GEN] Ficheiro rendeu {len(df)} recortes de tráfego de 10s.")
    return df


def generate_synthetic(traffic_class: str, n: int, real_data: pd.DataFrame) -> pd.DataFrame:
    """Gera amostras artificiais com base nas características médias observadas dos routers."""
    rng = np.random.default_rng(42)
    rows = []
    
    # Se já tivermos dados reais, usamos a média. Se não, geramos por dedução.
    if len(real_data) > 0:
        base_num = max(2, real_data["num_packets"].mean())
        base_avg_size = real_data["avg_size"].mean()
        base_std_size = real_data["std_size"].mean()
        base_avg_iat = real_data["avg_iat"].mean()
    else:
        # Fallbacks genéricos caso PCAP não tenha classes completas
        if traffic_class == "telemetry":
            base_num, base_avg_size, base_std_size, base_avg_iat = 20, 160, 50, 1.0
        elif traffic_class == "event_driven":
            base_num, base_avg_size, base_std_size, base_avg_iat = 10, 200, 100, 2.5
        else:
            base_num, base_avg_size, base_std_size, base_avg_iat = 100, 600, 60, 0.05

    for _ in range(n):
        num_pkts = int(max(2, rng.normal(base_num, base_num * 0.2)))
        avg_size = max(50, rng.normal(base_avg_size, 20))
        std_size = max(0, rng.normal(base_std_size, 15))
        avg_iat  = max(0.001, rng.normal(base_avg_iat, base_avg_iat * 0.2))
        total_b  = int(num_pkts * avg_size)
        
        rows.append([num_pkts, avg_size, std_size, avg_iat, total_b, traffic_class])

    return pd.DataFrame(rows, columns=FEATURE_COLS + [LABEL_COL])


def build_dataset(df_real: pd.DataFrame) -> pd.DataFrame:
    frames = [df_real]
    for cls in ["telemetry", "event_driven", "firmware"]:
        real_cls = df_real[df_real[LABEL_COL] == cls]
        count = len(real_cls)
        
        if count < MIN_SAMPLES:
            needed = MIN_SAMPLES - count
            print(f"[GEN] Aumentar classe '{cls}': {count} reais + {needed} gerados abstratos = {MIN_SAMPLES}")
            df_syn = generate_synthetic(cls, needed, real_cls)
            frames.append(df_syn)
        else:
            print(f"[GEN] Classe '{cls}': {count} amostras puras.")

    df_final = pd.concat(frames, ignore_index=True)
    return df_final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pcap", default="./captures/iot_session.pcap", help="Ficheiro source")
    parser.add_argument("--out", default="./data/self_generated.csv", help="Saída de dataset")
    args = parser.parse_args()

    df_real = read_from_pcap(args.pcap)
    if not df_real.empty:
        print(f"[GEN] Total de recortes NFStream antes de aumento: \n{df_real[LABEL_COL].value_counts()}\n")

    df_final = build_dataset(df_real)
    print(f"\n[GEN] Tabela Resultante (NFStream): \n{df_final[LABEL_COL].value_counts()}")

    df_final.to_csv(args.out, index=False)
    print(f"\n[GEN] Terminado e exportado para: {args.out}")

if __name__ == "__main__":
    main()
