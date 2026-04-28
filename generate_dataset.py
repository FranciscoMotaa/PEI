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

FEATURES    = ["num_packets", "avg_size", "std_size", "avg_iat", "std_iat", "total_bytes"]
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
        if flow.bidirectional_packets < 3:
            continue
        std_iat = flow.bidirectional_stddev_piat_ms / 1000.0 if flow.bidirectional_stddev_piat_ms else 0.0
        rows.append([
            flow.bidirectional_packets,
            flow.bidirectional_mean_ps,
            flow.bidirectional_stddev_ps,
            flow.bidirectional_mean_piat_ms / 1000.0,
            std_iat,
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
        m_siat = dados_reais["std_iat"].mean() if "std_iat" in dados_reais.columns else m_iat * 0.3
    else:
        # valores aproximados baseados no que vi nos logs do servidor
        if classe == "telemetry":
            m_pkts, m_size, m_std, m_iat, m_siat = 20, 160, 50, 1.0, 0.1
        elif classe == "event_driven":
            m_pkts, m_size, m_std, m_iat, m_siat = 10, 200, 100, 2.5, 1.5
        else:
            m_pkts, m_size, m_std, m_iat, m_siat = 100, 600, 60, 0.05, 0.02

    for _ in range(n):
        pkts  = int(max(2, rng.normal(m_pkts, m_pkts * 0.2)))
        size  = max(50, rng.normal(m_size, 20))
        std   = max(0, rng.normal(m_std, 15))
        iat   = max(0.001, rng.normal(m_iat, m_iat * 0.2))
        siat  = max(0.0, rng.normal(m_siat, m_siat * 0.3))
        total = int(pkts * size)
        rows.append([pkts, size, std, iat, siat, total, classe])

    return pd.DataFrame(rows, columns=FEATURES + [LABEL])


def gerar_degradados(df_normal):
    """
    Gera amostras que simulam condicoes de rede degradadas (delay, perda de pacotes).
    Isto treina o modelo a reconhecer as classes mesmo quando as features estao distorcidas.

    Efeitos simulados:
    - perda de pacotes: reduz num_packets e total_bytes, aumenta avg_iat e std_iat
    - delay: aumenta avg_iat e std_iat mas mantem num_packets e total_bytes
    """
    rng = np.random.default_rng(seed=99)
    rows = []

    for _, row in df_normal.iterrows():
        classe = row[LABEL]

        # simular perda de pacotes (5% a 25%)
        for loss in [0.05, 0.10, 0.20, 0.25]:
            fator = 1.0 - loss
            pkts  = max(3, int(row["num_packets"] * fator * rng.uniform(0.9, 1.1)))
            total = int(row["total_bytes"] * fator * rng.uniform(0.9, 1.1))
            # perda de pacotes aumenta o IAT medio (ha mais gaps)
            iat   = row["avg_iat"] / fator * rng.uniform(0.95, 1.05)
            # e aumenta a variancia do IAT (os gaps ficam irregulares)
            siat  = row["std_iat"] * (1.0 + loss * 2) * rng.uniform(0.9, 1.1)
            rows.append([pkts, row["avg_size"], row["std_size"], iat, siat, total, classe])

        # simular delay adicional (50ms a 500ms)
        for delay_s in [0.05, 0.1, 0.2, 0.5]:
            iat  = row["avg_iat"] + delay_s * rng.uniform(0.8, 1.2)
            siat = row["std_iat"] + delay_s * 0.3 * rng.uniform(0.8, 1.2)
            rows.append([
                row["num_packets"], row["avg_size"], row["std_size"],
                iat, siat, row["total_bytes"], classe
            ])

    df_deg = pd.DataFrame(rows, columns=FEATURES + [LABEL])
    print(f"amostras degradadas geradas: {len(df_deg)}")
    return df_deg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pcap", default="./captures/iot_session.pcap")
    parser.add_argument("--out",  default="./data/self_generated.csv")
    parser.add_argument("--no-degraded", action="store_true",
                        help="nao incluir amostras degradadas no dataset")
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

    df_normal = pd.concat(frames, ignore_index=True)

    # adicionar amostras degradadas para o modelo aprender a classificar
    # mesmo quando a rede esta com delay ou perda de pacotes
    if not args.no_degraded:
        print("\na gerar amostras com condicoes de rede degradadas...")
        df_deg = gerar_degradados(df_normal)
        df_final = pd.concat([df_normal, df_deg], ignore_index=True)
    else:
        df_final = df_normal

    print(f"\ndataset final:\n{df_final[LABEL].value_counts()}")
    print(f"total: {len(df_final)} amostras")

    df_final.to_csv(args.out, index=False)
    print(f"\nguardado em {args.out}")


if __name__ == "__main__":
    main()
