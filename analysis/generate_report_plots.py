"""
Gera os plots com fundo branco para incluir no relatorio PDF.
Usa o mesmo dataset e modelo que o exploratory_analysis.py mas com tema claro.

Uso:
    python analysis/generate_report_plots.py
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

FEATURES = ["num_packets", "avg_size", "std_size", "avg_iat", "std_iat", "total_bytes"]
LABEL    = "traffic_class"

CORES = {
    "telemetry":    "#2563eb",
    "event_driven": "#d97706",
    "firmware":     "#7c3aed",
}

# tema claro para o relatorio
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor":   "white",
    "axes.edgecolor":   "#333333",
    "axes.labelcolor":  "#333333",
    "xtick.color":      "#333333",
    "ytick.color":      "#333333",
    "text.color":       "#333333",
    "grid.color":       "#e0e0e0",
    "grid.linestyle":   "--",
    "grid.linewidth":   0.5,
    "font.size":        10,
})
sns.set_theme(style="whitegrid", palette=list(CORES.values()))


def carregar(csv_path):
    df = pd.read_csv(csv_path)
    # usar apenas features que existem no CSV
    feats = [f for f in FEATURES if f in df.columns]
    print(f"{len(df)} amostras, features: {feats}")
    return df, feats


def plot_distribuicao(df, pasta):
    counts = df[LABEL].value_counts()
    fig, ax = plt.subplots(figsize=(6, 3.5))
    barras = ax.bar(counts.index, counts.values,
                    color=[CORES.get(c, "#666") for c in counts.index],
                    edgecolor="#333", linewidth=0.5)
    for b, v in zip(barras, counts.values):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 20,
                str(v), ha="center", va="bottom", fontsize=9)
    ax.set_title("Distribuição de Classes no Dataset")
    ax.set_xlabel("Classe de Tráfego")
    ax.set_ylabel("Número de Amostras")
    ax.set_ylim(0, counts.max() * 1.12)
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "01_class_distribution.png"), dpi=200)
    plt.close()
    print("  01_class_distribution.png")


def plot_boxplots(df, feats, pasta):
    n = len(feats)
    cols = 3
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(14, 4 * rows))
    axes = axes.flatten()

    for i, feat in enumerate(feats):
        ax = axes[i]
        dados = [df[df[LABEL] == cls][feat].dropna().values for cls in CORES]
        bp = ax.boxplot(dados, patch_artist=True,
                        medianprops=dict(color="#111", linewidth=1.5))
        for patch, cor in zip(bp["boxes"], CORES.values()):
            patch.set_facecolor(cor)
            patch.set_alpha(0.6)
        ax.set_xticklabels(list(CORES.keys()), fontsize=9)
        ax.set_title(feat, fontsize=11)
        ax.grid(True, alpha=0.3)

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle("Distribuição das Features por Classe", fontsize=13, y=1.01)
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "02_feature_boxplots.png"), dpi=200, bbox_inches="tight")
    plt.close()
    print("  02_feature_boxplots.png")


def plot_correlacao(df, feats, pasta):
    corr = df[feats].corr()
    fig, ax = plt.subplots(figsize=(7, 5.5))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdBu_r",
                linewidths=0.5, ax=ax, vmin=-1, vmax=1,
                annot_kws={"size": 9})
    ax.set_title("Matriz de Correlação entre Features")
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "03_correlation_heatmap.png"), dpi=200)
    plt.close()
    print("  03_correlation_heatmap.png")


def plot_pca(df, feats, pasta):
    X = df[feats].values
    y = df[LABEL].values

    pca = PCA(n_components=2, random_state=42)
    Xp = pca.fit_transform(X)
    var = pca.explained_variance_ratio_

    fig, ax = plt.subplots(figsize=(7, 5.5))
    for cls, cor in CORES.items():
        mask = y == cls
        ax.scatter(Xp[mask, 0], Xp[mask, 1], c=cor, label=cls, alpha=0.5, s=12, edgecolors="none")

    ax.set_xlabel(f"PC1 ({var[0]*100:.1f}% variância)")
    ax.set_ylabel(f"PC2 ({var[1]*100:.1f}% variância)")
    ax.set_title("Projeção PCA 2D — Separabilidade das Classes")
    ax.legend(framealpha=0.9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "04_pca_2d.png"), dpi=200)
    plt.close()
    print("  04_pca_2d.png")


def plot_importancia(model_path, feats, pasta):
    if not os.path.exists(model_path):
        print("  modelo nao encontrado, a saltar feature importance")
        return

    bundle = joblib.load(model_path)
    clf = bundle["model"]
    model_feats = bundle.get("features", feats)
    imp = clf.feature_importances_
    ordem = np.argsort(imp)[::-1]

    fig, ax = plt.subplots(figsize=(7, 4))
    colors = ["#2563eb" if i == ordem[0] else "#64748b" for i in range(len(model_feats))]
    ax.bar(range(len(model_feats)), imp[ordem],
           color=[colors[i] for i in ordem], edgecolor="#333", linewidth=0.5)
    ax.set_xticks(range(len(model_feats)))
    ax.set_xticklabels([model_feats[i] for i in ordem], rotation=20, ha="right")
    ax.set_title("Importância das Features (Gini — Random Forest)")
    ax.set_ylabel("Importância Média")
    ax.grid(True, axis="y", alpha=0.3)

    for i, idx in enumerate(ordem):
        ax.text(i, imp[idx] + 0.005, f"{imp[idx]:.3f}", ha="center", fontsize=8)

    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "05_feature_importance.png"), dpi=200)
    plt.close()
    print("  05_feature_importance.png")


def plot_confusao(df, feats, model_path, pasta):
    if not os.path.exists(model_path):
        print("  modelo nao encontrado, a saltar matriz de confusao")
        return

    bundle = joblib.load(model_path)
    clf = bundle["model"]
    model_feats = bundle.get("features", feats)

    X = df[model_feats].values
    y = df[LABEL].values
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    y_pred = clf.predict(X_test)

    cm = confusion_matrix(y_test, y_pred, labels=clf.classes_)
    fig, ax = plt.subplots(figsize=(6, 5))
    ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=clf.classes_).plot(
        ax=ax, cmap="Blues", colorbar=True)
    ax.set_title("Matriz de Confusão (conjunto de teste 20%)")
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "06_confusion_matrix.png"), dpi=200)
    plt.close()
    print("  06_confusion_matrix.png")


def plot_iat(df, pasta):
    iat_col = "avg_iat"
    if iat_col not in df.columns:
        print("  avg_iat nao disponivel, a saltar")
        return

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for cls, cor in CORES.items():
        dados = df[df[LABEL] == cls][iat_col].dropna()
        dados.clip(upper=dados.quantile(0.95)).plot.kde(ax=ax, label=cls, color=cor, linewidth=2)

    ax.set_xlabel("avg_iat (segundos)")
    ax.set_ylabel("Densidade")
    ax.set_title("Distribuição do Inter-Arrival Time por Classe")
    ax.legend(framealpha=0.9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(pasta, "07_iat_distribution.png"), dpi=200)
    plt.close()
    print("  07_iat_distribution.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv",   default="./data/self_generated.csv")
    parser.add_argument("--model", default="./data/model.joblib")
    parser.add_argument("--out",   default="./analysis/plots")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    df, feats = carregar(args.csv)

    print("a gerar plots com fundo branco para o relatorio...")
    plot_distribuicao(df, args.out)
    plot_boxplots(df, feats, args.out)
    plot_correlacao(df, feats, args.out)
    plot_pca(df, feats, args.out)
    plot_iat(df, args.out)
    plot_importancia(args.model, feats, args.out)
    plot_confusao(df, feats, args.model, args.out)

    print(f"\npronto. plots em {args.out}/")


if __name__ == "__main__":
    main()
