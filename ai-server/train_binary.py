"""
train_binary.py — Treino do classificador binário Encrypted vs Non-Encrypted
=============================================================================
Usa o dataset Binary -2DSCombined.csv para treinar um modelo que detecta
se um fluxo de rede é encriptado ou não, com base apenas em features
observáveis sem inspecionar o payload.

Uso:
    python train_binary.py --csv "data/Binary -2DSCombined.csv" --out data/binary_model.joblib
"""

import argparse
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

DEFAULT_CSV   = os.getenv("BINARY_DATASET_PATH", "/app/data/Binary -2DSCombined.csv")
DEFAULT_MODEL = os.getenv("BINARY_MODEL_PATH",   "/app/data/binary_model.joblib")
LABEL_COL     = "label"   # valores: "Encrypted" / "Non-Encrypted"

# ── Features do dataset que coincidem com as 5 features do servidor ──────────
# Mapeamento: coluna CSV → feature do servidor
COL_MAP = {
    "packets_count":       "num_packets",
    "payload_bytes_mean":  "avg_size",
    "payload_bytes_std":   "std_size",
    "total_payload_bytes": "total_bytes",
}
# avg_iat: usamos fwd_iat_mean se existir, senão duration/packets_count
IAT_CANDIDATES = ["fwd_iat_mean", "iat_mean", "flow_iat_mean", "active_mean"]

FEATURE_COLS = ["num_packets", "avg_size", "std_size", "avg_iat", "total_bytes"]


def find_iat_col(df_cols: list) -> str | None:
    """Encontra a melhor coluna IAT disponível no dataset."""
    for c in IAT_CANDIDATES:
        if c in df_cols:
            return c
    # fallback: procura qualquer coluna com 'iat' no nome
    for c in df_cols:
        if "iat" in c.lower() and "mean" in c.lower():
            return c
    return None


def load_and_prepare(csv_path: str) -> tuple:
    """Carrega e prepara o dataset binário."""
    print(f"[BINARY] A carregar: {csv_path}")
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"[BINARY] {len(df):,} registos | {df.shape[1]} colunas")
    print(f"[BINARY] Labels:\n{df[LABEL_COL].value_counts()}\n")

    # ── Mapear colunas ────────────────────────────────────────────────
    rename = {k: v for k, v in COL_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    # IAT: tentar encontrar coluna de inter-arrival time
    iat_col = find_iat_col(list(df.columns))
    if iat_col and iat_col not in [v for v in COL_MAP.values()]:
        df["avg_iat"] = df[iat_col]
        print(f"[BINARY] A usar '{iat_col}' como avg_iat")
    elif "avg_iat" not in df.columns:
        # fallback: duration / packets
        if "duration" in df.columns and "num_packets" in df.columns:
            df["avg_iat"] = df["duration"] / df["num_packets"].replace(0, 1)
            print("[BINARY] A calcular avg_iat = duration / num_packets")
        else:
            df["avg_iat"] = 0.0
            print("[BINARY] Atenção: avg_iat não disponível, a usar 0")

    # ── Limpeza ──────────────────────────────────────────────────────
    df_clean = df[FEATURE_COLS + [LABEL_COL]].copy()
    df_clean = df_clean.dropna()
    df_clean = df_clean[np.isfinite(df_clean[FEATURE_COLS]).all(axis=1)]
    print(f"[BINARY] {len(df_clean):,} registos válidos após limpeza.")

    X = df_clean[FEATURE_COLS].values
    y = df_clean[LABEL_COL].values
    return X, y


def train(X, y) -> RandomForestClassifier:
    """Treina o classificador binário."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"[BINARY] Treino: {len(X_train):,} | Teste: {len(X_test):,}\n")

    clf = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    # ── Avaliação ─────────────────────────────────────────────────────
    y_pred = clf.predict(X_test)
    print("[BINARY] ── Relatório de Classificação ─────────────────────")
    print(classification_report(y_test, y_pred))

    print("[BINARY] ── Matriz de Confusão ──────────────────────────────")
    cm = confusion_matrix(y_test, y_pred, labels=clf.classes_)
    print(f"  Classes: {list(clf.classes_)}")
    print(f"  {cm}\n")

    # ── Feature Importance ────────────────────────────────────────────
    ranked = sorted(zip(FEATURE_COLS, clf.feature_importances_), key=lambda x: x[1], reverse=True)
    print("[BINARY] ── Importância das Features ────────────────────────")
    for feat, imp in ranked:
        bar = "█" * int(imp * 50)
        print(f"  {feat:<20} {imp:.4f}  {bar}")
    print()

    return clf


def save_model(clf, model_path: str):
    os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
    joblib.dump({
        "model":    clf,
        "features": FEATURE_COLS,
        "classes":  list(clf.classes_),
        "type":     "binary_encrypted",
    }, model_path)
    print(f"[BINARY] Modelo guardado em: {model_path}")


def main():
    parser = argparse.ArgumentParser(description="Treinar classificador binário Encrypted/Non-Encrypted")
    parser.add_argument("--csv", default=DEFAULT_CSV,   help="Caminho para o CSV binário")
    parser.add_argument("--out", default=DEFAULT_MODEL, help="Caminho para guardar o modelo")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"[BINARY] ERRO: Ficheiro não encontrado: {args.csv}")
        sys.exit(1)

    X, y = load_and_prepare(args.csv)
    clf  = train(X, y)
    save_model(clf, args.out)
    print("[BINARY] Concluído! O servidor pode agora classificar flows como Encrypted/Non-Encrypted.")


if __name__ == "__main__":
    main()
