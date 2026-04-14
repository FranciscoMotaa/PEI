"""
Testa a robustez do classificador sob diferentes condicoes de rede.

Aplica delay e perda de pacotes a cada dispositivo via tc netem (Docker SDK),
espera que o ai-server produza classificacoes e regista como a confianca varia.

Pré-requisitos:
    - sistema a correr: docker compose up -d --build
    - pip install docker pandas matplotlib

Uso:
    python analysis/robustness_experiment.py --duration 30
    python analysis/robustness_experiment.py --offline
"""

import argparse
import os
import sqlite3
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

try:
    import docker as docker_sdk
    docker_client = docker_sdk.from_env()
except Exception as e:
    docker_client = None
    print(f"docker nao disponivel: {e}")
    print("a correr em modo offline")

# cenarios de teste - comecei com poucos e fui adicionando
CENARIOS = [
    {"label": "Baseline",    "delay_ms": 0,   "loss_pct": 0},
    {"label": "Delay 50ms",  "delay_ms": 50,  "loss_pct": 0},
    {"label": "Delay 200ms", "delay_ms": 200, "loss_pct": 0},
    {"label": "Delay 500ms", "delay_ms": 500, "loss_pct": 0},
    {"label": "Loss 5%",     "delay_ms": 0,   "loss_pct": 5},
    {"label": "Loss 20%",    "delay_ms": 0,   "loss_pct": 20},
    {"label": "Delay+Loss",  "delay_ms": 200, "loss_pct": 10},
]

DISPOSITIVOS = ["iot-device-1", "iot-device-2", "iot-device-3"]

CORES = {
    "telemetry":    "#3fb950",
    "event_driven": "#ffa657",
    "firmware":     "#d2a8ff",
}


def aplicar_netem(device, delay_ms, loss_pct):
    if not docker_client:
        return
    try:
        c = docker_client.containers.get(device)
        if delay_ms == 0 and loss_pct == 0:
            c.exec_run("tc qdisc del dev eth0 root netem", privileged=True)
        else:
            check  = c.exec_run("tc qdisc show dev eth0")
            action = "change" if b"netem" in check.output else "add"
            c.exec_run(f"tc qdisc {action} dev eth0 root netem delay {delay_ms}ms loss {loss_pct}%",
                       privileged=True)
    except Exception as e:
        print(f"  aviso ({device}): {e}")


def reset_rede():
    for d in DISPOSITIVOS:
        aplicar_netem(d, 0, 0)


def recolher_dados(db_path, desde, duracao):
    fim = desde + duracao
    espera = fim - time.time()
    if espera > 0:
        print(f"  a aguardar {espera:.0f}s...")
        time.sleep(espera)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT device_id, predicted, confidence, avg_iat, avg_size, num_packets
        FROM classifications
        WHERE timestamp >= ? AND timestamp <= ?
    """, (desde, fim)).fetchall()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows])


def correr_experimento(db_path, duracao, pasta):
    os.makedirs(pasta, exist_ok=True)
    resultados = []

    print(f"\na iniciar: {len(CENARIOS)} cenarios x {duracao}s cada\n")

    for c in CENARIOS:
        label    = c["label"]
        delay_ms = c["delay_ms"]
        loss_pct = c["loss_pct"]

        print(f"cenario: {label}")
        for d in DISPOSITIVOS:
            aplicar_netem(d, delay_ms, loss_pct)

        time.sleep(3)
        desde = time.time()
        df = recolher_dados(db_path, desde, duracao)

        if df.empty:
            print("  sem dados")
            continue

        for cls in df["predicted"].unique():
            sub = df[df["predicted"] == cls]
            resultados.append({
                "cenario":        label,
                "delay_ms":       delay_ms,
                "loss_pct":       loss_pct,
                "classe":         cls,
                "n":              len(sub),
                "conf_media":     sub["confidence"].mean(),
                "conf_std":       sub["confidence"].std(),
                "iat_medio":      sub["avg_iat"].mean(),
                "size_medio":     sub["avg_size"].mean(),
            })
            print(f"  {cls}: n={len(sub)}, conf={sub['confidence'].mean():.1f}%")

    reset_rede()
    print("\nrede restaurada")

    if not resultados:
        print("sem resultados")
        return pd.DataFrame()

    df_res = pd.DataFrame(resultados)
    df_res.to_csv(os.path.join(pasta, "robustness_results.csv"), index=False)
    print(f"resultados guardados")
    return df_res


def plot_por_cenario(df, pasta):
    classes   = df["classe"].unique()
    cenarios  = df["cenario"].unique()

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")

    x = range(len(cenarios))
    w = 0.25
    offsets = [-w, 0, w]

    for i, cls in enumerate(classes):
        sub = df[df["classe"] == cls].set_index("cenario").reindex(cenarios)
        cor = CORES.get(cls, "#8b949e")
        ax.bar([xi + offsets[i % 3] for xi in x],
               sub["conf_media"].fillna(0),
               width=w * 0.9, label=cls, color=cor, alpha=0.85, edgecolor="#30363d")
        ax.errorbar([xi + offsets[i % 3] for xi in x],
                    sub["conf_media"].fillna(0),
                    yerr=sub["conf_std"].fillna(0),
                    fmt="none", color="#fff", capsize=3, linewidth=1, alpha=0.5)

    ax.set_xticks(list(x))
    ax.set_xticklabels(cenarios, rotation=25, ha="right", color="#8b949e", fontsize=9)
    ax.set_ylabel("Confianca Media (%)", color="#8b949e")
    ax.set_title("Confianca por Cenario de Rede", color="#e6edf3")
    ax.set_ylim(0, 110)
    ax.axhline(y=80, color="#f85149", linestyle="--", linewidth=1, alpha=0.6, label="limiar 80%")
    ax.tick_params(colors="#8b949e")
    ax.legend(facecolor="#21262d", edgecolor="#30363d", labelcolor="#e6edf3")
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "08_robustness_confidence.png"), dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print("guardado: 08_robustness_confidence.png")


def plot_vs_delay(df, pasta):
    df2 = df[df["loss_pct"] == 0].copy()
    if df2.empty:
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")

    for cls in df2["classe"].unique():
        sub = df2[df2["classe"] == cls].sort_values("delay_ms")
        cor = CORES.get(cls, "#8b949e")
        ax.plot(sub["delay_ms"], sub["conf_media"], marker="o", label=cls, color=cor, linewidth=2)
        ax.fill_between(sub["delay_ms"],
                        sub["conf_media"] - sub["conf_std"].fillna(0),
                        sub["conf_media"] + sub["conf_std"].fillna(0),
                        alpha=0.15, color=cor)

    ax.set_xlabel("Delay (ms)", color="#8b949e")
    ax.set_ylabel("Confianca Media (%)", color="#8b949e")
    ax.set_title("Impacto do Delay na Classificacao", color="#e6edf3")
    ax.tick_params(colors="#8b949e")
    ax.legend(facecolor="#21262d", edgecolor="#30363d", labelcolor="#e6edf3")
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "09_confidence_vs_delay.png"), dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print("guardado: 09_confidence_vs_delay.png")


def plot_vs_loss(df, pasta):
    df2 = df[df["delay_ms"] == 0].copy()
    if df2.empty:
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")

    for cls in df2["classe"].unique():
        sub = df2[df2["classe"] == cls].sort_values("loss_pct")
        cor = CORES.get(cls, "#8b949e")
        ax.plot(sub["loss_pct"], sub["conf_media"], marker="s", label=cls, color=cor, linewidth=2)

    ax.set_xlabel("Perda de Pacotes (%)", color="#8b949e")
    ax.set_ylabel("Confianca Media (%)", color="#8b949e")
    ax.set_title("Impacto da Perda de Pacotes na Classificacao", color="#e6edf3")
    ax.tick_params(colors="#8b949e")
    ax.legend(facecolor="#21262d", edgecolor="#30363d", labelcolor="#e6edf3")
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "10_confidence_vs_loss.png"), dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print("guardado: 10_confidence_vs_loss.png")


def modo_offline(db_path, pasta):
    print("modo offline - a analisar dados existentes na BD...")
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM classifications ORDER BY timestamp", conn)
    conn.close()

    if df.empty:
        print("BD vazia, nao ha dados para analisar")
        return

    df["ts"] = pd.to_datetime(df["timestamp"], unit="s")

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")

    for cls, cor in CORES.items():
        sub = df[df["predicted"] == cls]
        if not sub.empty:
            ax.scatter(sub["ts"], sub["confidence"], c=cor, label=cls, alpha=0.5, s=15)

    ax.set_xlabel("Tempo", color="#8b949e")
    ax.set_ylabel("Confianca (%)", color="#8b949e")
    ax.set_title("Confianca ao Longo do Tempo", color="#e6edf3")
    ax.tick_params(colors="#8b949e")
    ax.legend(facecolor="#21262d", edgecolor="#30363d", labelcolor="#e6edf3")
    plt.xticks(rotation=20)
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "08_confidence_over_time.png"), dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print("guardado: 08_confidence_over_time.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db",       default="./data/iot_traffic.db")
    parser.add_argument("--out",      default="./analysis/plots")
    parser.add_argument("--duration", type=int, default=30, help="segundos por cenario")
    parser.add_argument("--offline",  action="store_true", help="analisa dados existentes sem aplicar degradacao")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    if args.offline or not docker_client:
        modo_offline(args.db, args.out)
        return

    if not os.path.exists(args.db):
        print(f"BD nao encontrada: {args.db}")
        print("corre primeiro: docker compose up -d --build")
        return

    df = correr_experimento(args.db, args.duration, args.out)

    if not df.empty:
        plot_por_cenario(df, args.out)
        plot_vs_delay(df, args.out)
        plot_vs_loss(df, args.out)
        print(f"\npronto. graficos em {args.out}/")


if __name__ == "__main__":
    main()
