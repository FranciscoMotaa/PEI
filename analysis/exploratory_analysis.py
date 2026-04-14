"""
Analise exploratoria do dataset de trafego IoT encriptado.

Gera varios graficos para perceber como as features se distribuem por classe
e avalia o modelo treinado com matriz de confusao e importancia das features.

Uso:
    python analysis/exploratory_analysis.py
    python analysis/exploratory_analysis.py --csv data/self_generated.csv --model data/model.joblib --out analysis/plots
"""

import argparse
import os

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay
from sklearn.model_selection import train_test_split

FEATURES  = ["num_packets", "avg_size", "std_size", "avg_iat", "total_bytes"]
LABEL     = "traffic_class"

# cores para cada classe - escolhi estas para ficarem visiveis no fundo escuro
CORES = {
    "telemetry":    "#3fb950",
    "event_driven": "#ffa657",
    "firmware":     "#d2a8ff",
}


def carregar(csv_path):
    df = pd.read_csv(csv_path)
    print(f"{len(df)} amostras")
    print(df[LABEL].value_counts())
    print()
    return df


def grafico_distribuicao(df, pasta):
    counts = df[LABEL].value_counts()
    fig, ax = plt.subplots(figsize=(7, 4))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")

    barras = ax.bar(counts.index, counts.values,
                    color=[CORES.get(c, "#8b949e") for c in counts.index],
                    edgecolor="#30363d")
    for b, v in zip(barras, counts.values):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 5,
                str(v), ha="center", va="bottom", fontsize=10, color="#e6edf3")

    ax.set_title("Distribuicao de Classes", color="#e6edf3")
    ax.set_xlabel("Classe", color="#8b949e")
    ax.set_ylabel("Amostras", color="#8b949e")
    ax.tick_params(colors="#8b949e")
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "01_class_distribution.png"), dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print("guardado: 01_class_distribution.png")


def grafico_boxplots(df, pasta):
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    axes = axes.flatten()
    fig.patch.set_facecolor("#0d1117")

    for i, feat in enumerate(FEATURES):
        ax = axes[i]
        ax.set_facecolor("#161b22")
        dados = [df[df[LABEL] == cls][feat].dropna().values for cls in CORES]
        bp = ax.boxplot(dados, patch_artist=True, medianprops=dict(color="#fff", linewidth=2))
        for patch, cor in zip(bp["boxes"], CORES.values()):
            patch.set_facecolor(cor)
            patch.set_alpha(0.7)
        ax.set_xticklabels(list(CORES.keys()), color="#8b949e", fontsize=9)
        ax.set_title(feat, color="#e6edf3", fontsize=10)
        ax.tick_params(colors="#8b949e")

    axes[-1].set_visible(False)
    fig.suptitle("Features por Classe de Trafego", color="#e6edf3", fontsize=13)
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "02_feature_boxplots.png"), dpi=150,
                facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    print("guardado: 02_feature_boxplots.png")


def grafico_correlacao(df, pasta):
    corr = df[FEATURES].corr()
    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm",
                linewidths=0.5, ax=ax, annot_kws={"size": 9, "color": "#e6edf3"})
    ax.set_title("Correlacao entre Features", color="#e6edf3")
    ax.tick_params(colors="#8b949e")
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "03_correlation_heatmap.png"), dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print("guardado: 03_correlation_heatmap.png")


def grafico_pca(df, pasta):
    X = df[FEATURES].values
    y = df[LABEL].values

    pca = PCA(n_components=2, random_state=42)
    Xp  = pca.fit_transform(X)
    var = pca.explained_variance_ratio_

    fig, ax = plt.subplots(figsize=(8, 6))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")

    for cls, cor in CORES.items():
        mask = y == cls
        ax.scatter(Xp[mask, 0], Xp[mask, 1], c=cor, label=cls, alpha=0.6, s=20)

    ax.set_xlabel(f"PC1 ({var[0]*100:.1f}% variancia)", color="#8b949e")
    ax.set_ylabel(f"PC2 ({var[1]*100:.1f}% variancia)", color="#8b949e")
    ax.set_title("PCA 2D - separabilidade das classes", color="#e6edf3")
    ax.tick_params(colors="#8b949e")
    ax.legend(facecolor="#21262d", edgecolor="#30363d", labelcolor="#e6edf3")
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "04_pca_2d.png"), dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print("guardado: 04_pca_2d.png")


def grafico_importancia(model_path, pasta):
    if not os.path.exists(model_path):
        print("modelo nao encontrado, a saltar importancia das features")
        return

    bundle = joblib.load(model_path)
    clf    = bundle["model"]
    feats  = bundle.get("features", FEATURES)
    imp    = clf.feature_importances_
    ordem  = np.argsort(imp)[::-1]

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")

    cores_barras = ["#3fb950" if i == 0 else "#79c0ff" for i in range(len(feats))]
    ax.bar(range(len(feats)), imp[ordem],
           color=[cores_barras[i] for i in ordem], edgecolor="#30363d")
    ax.set_xticks(range(len(feats)))
    ax.set_xticklabels([feats[i] for i in ordem], rotation=20, ha="right", color="#8b949e")
    ax.set_title("Importancia das Features (Random Forest)", color="#e6edf3")
    ax.set_ylabel("Importancia media (Gini)", color="#8b949e")
    ax.tick_params(colors="#8b949e")
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "05_feature_importance.png"), dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print("guardado: 05_feature_importance.png")


def grafico_confusao(df, model_path, pasta):
    if not os.path.exists(model_path):
        print("modelo nao encontrado, a saltar matriz de confusao")
        return

    bundle = joblib.load(model_path)
    clf    = bundle["model"]

    X = df[FEATURES].values
    y = df[LABEL].values
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    y_pred = clf.predict(X_test)

    print("\nrelatório de classificacao (20% de teste):")
    print(classification_report(y_test, y_pred))

    cm = confusion_matrix(y_test, y_pred, labels=clf.classes_)
    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")
    ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=clf.classes_).plot(ax=ax, cmap="Blues")
    ax.set_title("Matriz de Confusao (teste 20%)", color="#e6edf3")
    ax.tick_params(colors="#8b949e")
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "06_confusion_matrix.png"), dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print("guardado: 06_confusion_matrix.png")


def grafico_iat(df, pasta):
    # o IAT e provavelmente a feature mais discriminante, vale a pena ver a distribuicao
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")

    for cls, cor in CORES.items():
        dados = df[df[LABEL] == cls]["avg_iat"].dropna()
        # clip nos 95% para nao distorcer o grafico com outliers
        dados.clip(upper=dados.quantile(0.95)).plot.kde(ax=ax, label=cls, color=cor, linewidth=2)

    ax.set_xlabel("avg_iat (segundos)", color="#8b949e")
    ax.set_ylabel("Densidade", color="#8b949e")
    ax.set_title("Distribuicao do IAT por Classe", color="#e6edf3")
    ax.tick_params(colors="#8b949e")
    ax.legend(facecolor="#21262d", edgecolor="#30363d", labelcolor="#e6edf3")
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "07_iat_distribution.png"), dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print("guardado: 07_iat_distribution.png")


def estatisticas(df):
    print("\n--- estatisticas por classe ---")
    for cls in df[LABEL].unique():
        sub = df[df[LABEL] == cls][FEATURES]
        print(f"\n{cls.upper()}")
        print(sub.describe().to_string())

    # ANOVA para confirmar que as features sao estatisticamente diferentes entre classes
    print("\n--- ANOVA (separabilidade) ---")
    for feat in FEATURES:
        grupos = [df[df[LABEL] == cls][feat].dropna().values for cls in df[LABEL].unique()]
        F, p = stats.f_oneway(*grupos)
        sig = "OK" if p < 0.05 else "NAO significativo"
        print(f"  {feat:<20} F={F:>10.2f}  p={p:.2e}  [{sig}]")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv",   default="./data/self_generated.csv")
    parser.add_argument("--model", default="./data/model.joblib")
    parser.add_argument("--out",   default="./analysis/plots")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    df = carregar(args.csv)
    estatisticas(df)

    grafico_distribuicao(df, args.out)
    grafico_boxplots(df, args.out)
    grafico_correlacao(df, args.out)
    grafico_pca(df, args.out)
    grafico_iat(df, args.out)
    grafico_importancia(args.model, args.out)
    grafico_confusao(df, args.model, args.out)

    print(f"\npronto. graficos em {args.out}/")


if __name__ == "__main__":
    main()
