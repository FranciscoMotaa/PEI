"""
Script de treino do modelo de classificacao de trafego IoT.

Uso:
    python train.py --csv ./data/self_generated.csv --out ./data/model.joblib

Tambem funciona com o dataset TON_IoT como fallback (as features sao derivadas):
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

DEFAULT_CSV   = os.getenv("DATASET_PATH", "/app/data/self_generated.csv")
DEFAULT_MODEL = os.getenv("MODEL_PATH",   "/app/data/model.joblib")

FEATURES = ["num_packets", "avg_size", "std_size", "avg_iat", "total_bytes"]
LABEL    = "traffic_class"
LABEL_TONIOT = "type"  # nome da coluna no dataset externo TON_IoT


def load_data(path):
    print(f"a carregar {path}...")
    df = pd.read_csv(path, low_memory=False)
    print(f"{len(df)} linhas")

    if LABEL in df.columns:
        label_col = LABEL
    elif LABEL_TONIOT in df.columns:
        # dataset externo - as features nao existem, temos de as calcular
        label_col = LABEL_TONIOT
        print("dataset TON_IoT detectado, a calcular features...")
        df["num_packets"] = df["src_pkts"] + df["dst_pkts"]
        df["total_bytes"] = df["src_bytes"] + df["dst_bytes"]
        df["avg_size"]    = df["total_bytes"] / df["num_packets"].replace(0, 1)
        df["avg_iat"]     = df["duration"] / (df["num_packets"] - 1).replace(0, 1)
        # std_size nao existe diretamente, aproximamos com o coeficiente de variacao
        cv = df["src_bytes"].std() / (df["src_bytes"].mean() + 1e-9)
        df["std_size"] = df["avg_size"] * cv
    else:
        print("ERRO: coluna de label nao encontrada no CSV")
        sys.exit(1)

    print(f"classes:\n{df[label_col].value_counts()}\n")

    df = df[FEATURES + [label_col]].dropna()
    df = df[np.isfinite(df[FEATURES]).all(axis=1)]
    print(f"{len(df)} amostras validas apos limpeza")

    return df[FEATURES].values, df[label_col].values


def treinar(X, y):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"treino={len(X_train)}, teste={len(X_test)}")

    # Random Forest com pesos balanceados porque as classes podem nao ser iguais
    clf = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    print(classification_report(y_test, y_pred))

    # ver quais features sao mais importantes
    print("importancia das features:")
    pairs = sorted(zip(FEATURES, clf.feature_importances_), key=lambda x: x[1], reverse=True)
    for nome, imp in pairs:
        print(f"  {nome:<20} {imp:.4f}  {'|' * int(imp * 50)}")

    return clf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=DEFAULT_CSV, help="caminho para o CSV de treino")
    parser.add_argument("--out", default=DEFAULT_MODEL, help="onde guardar o modelo")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"ficheiro nao encontrado: {args.csv}")
        print("corre primeiro: python generate_dataset.py")
        sys.exit(1)

    X, y = load_data(args.csv)
    clf  = treinar(X, y)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    joblib.dump({"model": clf, "features": FEATURES, "classes": list(clf.classes_)}, args.out)
    print(f"modelo guardado em {args.out}")


if __name__ == "__main__":
    main()
