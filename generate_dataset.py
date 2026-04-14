"""
Gera o dataset de treino a partir de capturas pcap.

Usa o NFStream para extrair as features dos fluxos (mesmo active_timeout=10s
que o servidor usa em producao, para garantir consistencia).

Se o pcap tiver poucas amostras de alguma classe, gera dados sinteticos
com base nas medias observadas para chegar ao minimo de 500 por classe.

Uso:
    python generate_dataset.py
    python generate_dataset.py --pcap ./captures/iot_session.pcap --out ./data/self_generated.csv
"""

import argparse
import os

import numpy as np
import pandas as pd
from nfstream import NFStreamer

FEATURES    = ["num_packets", "avg_size", "std_size", "avg_iat", "total_bytes"]
LABEL       = "traffic_class"
MIN_SAMPLES = 500

# mapeamento IP -> classe (tem de coincidir com o docker-compose)
IP_MAP = {
    "172.20.0.10": "telemetry",
    "172.20.0.11": "event_driven",
    "172.20.0.12": "firmware",
}
BROKER = "172.20.0.2"


def extrair_pcap(pcap_path):
    if not os.path.exists(pcap_path):
        print(f"pcap nao encontrado: {pcap_path}")
        return pd.DataFrame(columns=FEATURES + [LABEL])

    print(f"a processar {pcap_path} com NFStream...")
    streamer = NFStreamer(
        source=pcap_path,
        bpf_filter="tcp port 8883",
        statistical_analysis=True,
        active_timeout=10
    )

    rows = []
    for flow in streamer:
        if flow.src_ip not in IP_MAP or flow.dst_ip != BROKER:
            continue
        rows.append([
            flow.bidirectional_packets,
            flow.bidirectional_mean_ps,
            flow.bidirectional_stddev_ps,
            flow.bidirectional_mean_piat_ms / 1000.0,
            flow.bidirectional_bytes,
            IP_MAP[flow.src_ip]
        ])

    df = pd.DataFrame(rows, columns=FEATURES + [LABEL])
    df = df.fillna(0)
    print(f"{len(df)} fluxos extraidos")
    return df


def gerar_sinteticos(classe, n, dados_reais):
    """
    Gera n amostras sinteticas para uma classe.
    Se houver dados reais usa as medias deles, senao usa valores tipicos
    que observei durante os testes.
    """
    rng = np.random.default_rng(seed=42)
    rows = []

    if len(dados_reais) > 0:
        m_pkts = max(2, dados_reais["num_packets"].mean())
        m_size = dados_reais["avg_size"].mean()
        m_std  = dados_reais["std_size"].mean()
        m_iat  = dados_reais["avg_iat"].mean()
    else:
        # valores aproximados baseados no que vi nos logs do servidor
        if classe == "telemetry":
            m_pkts, m_size, m_std, m_iat = 20, 160, 50, 1.0
        elif classe == "event_driven":
            m_pkts, m_size, m_std, m_iat = 10, 200, 100, 2.5
        else:
            m_pkts, m_size, m_std, m_iat = 100, 600, 60, 0.05

    for _ in range(n):
        pkts  = int(max(2, rng.normal(m_pkts, m_pkts * 0.2)))
        size  = max(50, rng.normal(m_size, 20))
        std   = max(0, rng.normal(m_std, 15))
        iat   = max(0.001, rng.normal(m_iat, m_iat * 0.2))
        total = int(pkts * size)
        rows.append([pkts, size, std, iat, total, classe])

    return pd.DataFrame(rows, columns=FEATURES + [LABEL])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pcap", default="./captures/iot_session.pcap")
    parser.add_argument("--out",  default="./data/self_generated.csv")
    args = parser.parse_args()

    df_real = extrair_pcap(args.pcap)

    if not df_real.empty:
        print(f"\ndistribuicao antes do aumento:\n{df_real[LABEL].value_counts()}\n")

    frames = [df_real]
    for cls in ["telemetry", "event_driven", "firmware"]:
        sub = df_real[df_real[LABEL] == cls]
        n = len(sub)
        if n < MIN_SAMPLES:
            falta = MIN_SAMPLES - n
            print(f"classe '{cls}': {n} reais, a gerar mais {falta} sinteticos")
            frames.append(gerar_sinteticos(cls, falta, sub))
        else:
            print(f"classe '{cls}': {n} amostras (ok)")

    df_final = pd.concat(frames, ignore_index=True)
    print(f"\ndataset final:\n{df_final[LABEL].value_counts()}")

    df_final.to_csv(args.out, index=False)
    print(f"\nguardado em {args.out}")


if __name__ == "__main__":
    main()
