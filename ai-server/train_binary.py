"""
Treina o classificador binario: Encrypted vs Non-Encrypted

Dataset usado: "Binary -2DSCombined.csv"
As features sao as mesmas 5 que o servidor usa, mas o dataset tem nomes diferentes
por isso ha um mapeamento de colunas.

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

FEATURES  = ["num_packets", "avg_size", "std_size", "avg_iat", "std_iat", "total_bytes"]
LABEL_COL = "label"

# o dataset binario usa nomes de colunas diferentes, este mapa faz a conversao
COL_MAP = {
    "packets_count":       "num_packets",
    "payload_bytes_mean":  "avg_size",
    "payload_bytes_std":   "std_size",
    "total_payload_bytes": "total_bytes",
}

# possiveis nomes para a coluna de IAT (depende da versao do dataset)
IAT_COLS = ["fwd_iat_mean", "iat_mean", "flow_iat_mean", "active_mean"]


def encontrar_col_iat(colunas):
    for c in IAT_COLS:
        if c in colunas:
            return c
    # fallback: qualquer coluna com "iat" e "mean" no nome
    for c in colunas:
        if "iat" in c.lower() and "mean" in c.lower():
            return c
    return None


def load_data(path):
    print(f"a carregar {path}")
    df = pd.read_csv(path, low_memory=False)
    print(f"{len(df)} linhas, {df.shape[1]} colunas")
    print(f"labels:\n{df[LABEL_COL].value_counts()}\n")

    df = df.rename(columns={k: v for k, v in COL_MAP.items() if k in df.columns})

    col_iat = encontrar_col_iat(list(df.columns))
    if col_iat and col_iat not in FEATURES:
        df["avg_iat"] = df[col_iat]
        print(f"a usar '{col_iat}' como avg_iat")
    elif "avg_iat" not in df.columns:
        if "duration" in df.columns and "num_packets" in df.columns:
            df["avg_iat"] = df["duration"] / df["num_packets"].replace(0, 1)
            print("avg_iat calculado a partir de duration/num_packets")
        else:
            df["avg_iat"] = 0.0
            print("aviso: avg_iat nao disponivel, a usar 0")

    # std_iat - desvio padrao do IAT, util para distinguir trafego regular de irregular
    if "std_iat" not in df.columns:
        if col_iat and col_iat.replace("mean", "std") in df.columns:
            df["std_iat"] = df[col_iat.replace("mean", "std")]
        elif "avg_iat" in df.columns:
            df["std_iat"] = df["avg_iat"] * 0.3  # aproximacao
        else:
            df["std_iat"] = 0.0

    df = df[FEATURES + [LABEL_COL]].dropna()
    df = df[np.isfinite(df[FEATURES]).all(axis=1)]
    print(f"{len(df)} amostras validas")

    return df[FEATURES].values, df[LABEL_COL].values


def treinar(X, y):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"treino={len(X_train)}, teste={len(X_test)}\n")

    clf = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    print(classification_report(y_test, y_pred))

    cm = confusion_matrix(y_test, y_pred, labels=clf.classes_)
    print(f"matriz de confusao {list(clf.classes_)}:")
    print(cm, "\n")

    print("importancia das features:")
    for nome, imp in sorted(zip(FEATURES, clf.feature_importances_), key=lambda x: x[1], reverse=True):
        print(f"  {nome:<20} {imp:.4f}")

    return clf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=DEFAULT_CSV)
    parser.add_argument("--out", default=DEFAULT_MODEL)
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"ficheiro nao encontrado: {args.csv}")
        sys.exit(1)

    X, y = load_data(args.csv)
    clf  = treinar(X, y)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    joblib.dump({"model": clf, "features": FEATURES, "classes": list(clf.classes_)}, args.out)
    print(f"\nmodelo guardado em {args.out}")


if __name__ == "__main__":
    main()
