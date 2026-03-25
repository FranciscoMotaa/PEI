"""
train.py — Treino do modelo de classificação de tráfego IoT
============================================================
Carrega o dataset gerado pelo generate_dataset.py (ou TON_IoT como fallback),
treina um Random Forest e guarda o modelo em disco para o server.py.

Uso local:
    # Com dataset próprio (recomendado):
    python train.py --csv ./data/self_generated.csv --out ./data/model.joblib

    # Com TON_IoT como fallback:
    python train.py --csv ./data/train_test_network.csv --out ./data/model.joblib
"""

import argparse
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

# ── Paths padrão ──────────────────────────────────────────────────────────────
DEFAULT_CSV   = os.getenv("DATASET_PATH", "/app/data/self_generated.csv")
DEFAULT_MODEL = os.getenv("MODEL_PATH",   "/app/data/model.joblib")

# Features derivadas das janelas de mensagens MQTT (calculadas pelo servidor)
FEATURE_COLS = ["num_packets", "avg_size", "std_size", "avg_iat", "total_bytes"]
LABEL_COL    = "traffic_class"   # para self_generated.csv
LABEL_COL_FALLBACK = "type"      # para TON_IoT CSV


def detect_label_col(df: pd.DataFrame) -> str:
    """Detecta automaticamente qual coluna de label usar."""
    if LABEL_COL in df.columns:
        return LABEL_COL
    elif LABEL_COL_FALLBACK in df.columns:
        print(f"[TRAIN] Aviso: a usar coluna '{LABEL_COL_FALLBACK}' (TON_IoT). "
              f"Para usar dados próprios, corre primeiro: python generate_dataset.py")
        return LABEL_COL_FALLBACK
    else:
        raise ValueError(f"Nenhuma coluna de label encontrada. Esperado: '{LABEL_COL}' ou '{LABEL_COL_FALLBACK}'")


def load_and_prepare(csv_path: str) -> tuple:
    """Carrega o CSV e prepara X, y."""
    print(f"[TRAIN] A carregar dataset: {csv_path}")
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"[TRAIN] {len(df):,} registos carregados.")

    label_col = detect_label_col(df)

    # Para TON_IoT precisamos de derivar as features; para self_generated já existem
    if label_col == LABEL_COL_FALLBACK:
        df["num_packets"] = df["src_pkts"] + df["dst_pkts"]
        df["total_bytes"] = df["src_bytes"] + df["dst_bytes"]
        df["avg_size"]    = df["total_bytes"] / df["num_packets"].replace(0, 1)
        df["avg_iat"]     = df["duration"] / (df["num_packets"] - 1).replace(0, 1)
        global_cv = df["src_bytes"].std() / (df["src_bytes"].mean() + 1e-9)
        df["std_size"]    = df["avg_size"] * global_cv

    print(f"[TRAIN] Distribuição de classes:\n{df[label_col].value_counts()}\n")

    df_clean = df[FEATURE_COLS + [label_col]].dropna()
    df_clean = df_clean[np.isfinite(df_clean[FEATURE_COLS]).all(axis=1)]
    print(f"[TRAIN] {len(df_clean):,} registos válidos após limpeza.")

    X = df_clean[FEATURE_COLS].values
    y = df_clean[label_col].values
    return X, y


def train(X, y) -> RandomForestClassifier:
    """Treina o Random Forest e imprime métricas de avaliação."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"[TRAIN] Treino: {len(X_train):,} | Teste: {len(X_test):,}")
    print(f"[TRAIN] Classes: {sorted(set(y))}\n")

    clf = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    # ── Avaliação ────────────────────────────────────────────────────
    y_pred = clf.predict(X_test)
    print("[TRAIN] ── Relatório de Classificação ──────────────────────")
    print(classification_report(y_test, y_pred))

    # ── Feature Importance ───────────────────────────────────────────
    ranked = sorted(zip(FEATURE_COLS, clf.feature_importances_), key=lambda x: x[1], reverse=True)
    print("[TRAIN] ── Importância das Features (maior → menor) ────────")
    for feat, imp in ranked:
        bar = "█" * int(imp * 50)
        print(f"  {feat:<20} {imp:.4f}  {bar}")
    print()

    return clf


def save_model(clf, model_path: str):
    """Guarda o modelo em disco."""
    os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
    joblib.dump({
        "model":    clf,
        "features": FEATURE_COLS,
        "classes":  list(clf.classes_),
    }, model_path)
    print(f"[TRAIN] Modelo guardado em: {model_path}")


def main():
    parser = argparse.ArgumentParser(description="Treinar modelo de classificação IoT")
    parser.add_argument("--csv", default=DEFAULT_CSV,   help="Caminho para o CSV de treino")
    parser.add_argument("--out", default=DEFAULT_MODEL, help="Caminho para guardar o modelo (.joblib)")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"[TRAIN] ERRO: ficheiro CSV não encontrado: {args.csv}")
        print("[TRAIN] Corre primeiro: python generate_dataset.py")
        sys.exit(1)

    X, y = load_and_prepare(args.csv)
    clf  = train(X, y)
    save_model(clf, args.out)
    print("[TRAIN] Concluído!")


if __name__ == "__main__":
    main()
