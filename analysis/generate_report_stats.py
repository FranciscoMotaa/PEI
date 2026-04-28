"""
Gera todas as estatisticas necessarias para o relatorio tecnico.
Corre este script depois de treinar o modelo e ter o dataset gerado.

Uso:
    python analysis/generate_report_stats.py
"""

import os
import warnings
warnings.filterwarnings("ignore")

import joblib
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score, classification_report,
    confusion_matrix
)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier

CSV_PATH   = "./data/self_generated.csv"
MODEL_PATH = "./data/model.joblib"
FEATURES   = ["num_packets", "avg_size", "std_size", "avg_iat", "std_iat", "total_bytes"]
LABEL      = "traffic_class"

SEP = "=" * 65


def section(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def load():
    df = pd.read_csv(CSV_PATH)
    # usar apenas colunas que existem
    feats = [f for f in FEATURES if f in df.columns]
    X = df[feats].values
    y = df[LABEL].values
    return df, X, y, feats


def dataset_stats(df, feats):
    section("1. DATASET — ESTATISTICAS GERAIS")
    print(f"  Total de amostras : {len(df)}")
    print(f"  Features          : {feats}")
    print(f"\n  Distribuicao por classe:")
    for cls, n in df[LABEL].value_counts().items():
        print(f"    {cls:<20} {n} amostras")

    section("2. ESTATISTICAS POR CLASSE (media ± desvio padrao)")
    for cls in sorted(df[LABEL].unique()):
        sub = df[df[LABEL] == cls][feats]
        print(f"\n  {cls.upper()}")
        for f in feats:
            print(f"    {f:<20} {sub[f].mean():.4f} ± {sub[f].std():.4f}"
                  f"   [min={sub[f].min():.3f}, max={sub[f].max():.3f}]")


def anova_tests(df, feats):
    section("3. ANOVA — SEPARABILIDADE ESTATISTICA")
    print(f"  {'Feature':<20} {'F-statistic':>14} {'p-value':>12}  Resultado")
    print(f"  {'-'*60}")
    for feat in feats:
        groups = [df[df[LABEL] == cls][feat].dropna().values
                  for cls in df[LABEL].unique()]
        F, p = stats.f_oneway(*groups)
        sig = "SIGNIFICATIVO" if p < 0.05 else "nao significativo"
        print(f"  {feat:<20} {F:>14.2f} {p:>12.2e}  {sig}")


def model_comparison(X, y, feats):
    section("4. COMPARACAO DE MODELOS")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    models = {
        "Decision Tree":  DecisionTreeClassifier(random_state=42),
        "k-NN (k=5)":     KNeighborsClassifier(n_neighbors=5),
        "Naive Bayes":    GaussianNB(),
        "Random Forest":  RandomForestClassifier(
            n_estimators=200, class_weight="balanced",
            random_state=42, n_jobs=-1
        ),
    }

    print(f"  {'Modelo':<20} {'Acc. teste':>12} {'CV F1 (5-fold)':>16}")
    print(f"  {'-'*52}")
    for name, clf in models.items():
        clf.fit(X_train, y_train)
        acc = accuracy_score(y_test, clf.predict(X_test))
        cv  = cross_val_score(clf, X, y, cv=5, scoring="f1_weighted").mean()
        print(f"  {name:<20} {acc*100:>11.1f}% {cv*100:>15.1f}%")

    return X_train, X_test, y_train, y_test


def rf_detailed(X_train, X_test, y_train, y_test, feats):
    section("5. RANDOM FOREST — RESULTADOS DETALHADOS")

    clf = RandomForestClassifier(
        n_estimators=200, class_weight="balanced",
        random_state=42, n_jobs=-1
    )
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    print(f"  Accuracy: {accuracy_score(y_test, y_pred)*100:.2f}%\n")
    print(classification_report(y_test, y_pred, digits=4))

    print("  Matriz de confusao:")
    cm = confusion_matrix(y_test, y_pred, labels=clf.classes_)
    print(f"  Classes: {list(clf.classes_)}")
    for row, cls in zip(cm, clf.classes_):
        print(f"    {cls:<15} {list(row)}")

    section("6. IMPORTANCIA DAS FEATURES (Gini)")
    print(f"  {'Feature':<20} {'Importancia':>12}  Barra")
    print(f"  {'-'*55}")
    pairs = sorted(zip(feats, clf.feature_importances_), key=lambda x: x[1], reverse=True)
    for f, imp in pairs:
        bar = "█" * int(imp * 60)
        print(f"  {f:<20} {imp:>12.4f}  {bar}")

    section("7. IMPORTANCIA POR PERMUTACAO (mais fiavel)")
    perm = permutation_importance(clf, X_test, y_test, n_repeats=30,
                                  random_state=42, n_jobs=-1)
    print(f"  {'Feature':<20} {'Media':>10} {'Std':>8}  Barra")
    print(f"  {'-'*55}")
    order = np.argsort(perm.importances_mean)[::-1]
    for i in order:
        bar = "█" * int(perm.importances_mean[i] * 80)
        print(f"  {feats[i]:<20} {perm.importances_mean[i]:>10.4f}"
              f" {perm.importances_std[i]:>8.4f}  {bar}")

    section("8. IMPACTO DE REMOVER CADA FEATURE")
    base = accuracy_score(y_test, clf.predict(X_test))
    print(f"  Accuracy base: {base*100:.2f}%\n")
    print(f"  {'Feature removida':<20} {'Queda accuracy':>16}  Impacto")
    print(f"  {'-'*55}")
    for i, feat in enumerate(feats):
        X_masked = X_test.copy()
        X_masked[:, i] = X_train[:, i].mean()
        drop = base - accuracy_score(y_test, clf.predict(X_masked))
        bar = "█" * int(drop * 400)
        print(f"  {feat:<20} {drop*100:>15.2f}%  {bar}")

    return clf


def correlations(df, feats):
    section("9. CORRELACAO ENTRE FEATURES")
    corr = df[feats].corr()
    print(f"  {'':20}", end="")
    for f in feats:
        print(f"  {f[:8]:>8}", end="")
    print()
    for f1 in feats:
        print(f"  {f1:<20}", end="")
        for f2 in feats:
            v = corr.loc[f1, f2]
            print(f"  {v:>8.3f}", end="")
        print()


def per_class_separability(df, feats):
    section("10. SEPARABILIDADE ENTRE PARES DE CLASSES")
    classes = sorted(df[LABEL].unique())
    for i, c1 in enumerate(classes):
        for c2 in classes[i+1:]:
            print(f"\n  {c1} vs {c2}:")
            s1 = df[df[LABEL] == c1][feats]
            s2 = df[df[LABEL] == c2][feats]
            for feat in feats:
                t, p = stats.ttest_ind(s1[feat], s2[feat])
                diff = abs(s1[feat].mean() - s2[feat].mean())
                pooled_std = (s1[feat].std() + s2[feat].std()) / 2
                cohen_d = diff / (pooled_std + 1e-9)
                print(f"    {feat:<20} diff={diff:>10.3f}  Cohen d={cohen_d:>6.2f}"
                      f"  p={p:.2e}  {'***' if p < 0.001 else '**' if p < 0.01 else '*'}")


def main():
    print("\nA gerar estatisticas para o relatorio...")
    print(f"Dataset: {CSV_PATH}")
    print(f"Modelo:  {MODEL_PATH}")

    df, X, y, feats = load()

    dataset_stats(df, feats)
    anova_tests(df, feats)
    X_train, X_test, y_train, y_test = model_comparison(X, y, feats)
    clf = rf_detailed(X_train, X_test, y_train, y_test, feats)
    correlations(df, feats)
    per_class_separability(df, feats)

    print(f"\n{SEP}")
    print("  CONCLUIDO")
    print(SEP)
    print("\nCopia estes numeros para o relatorio.")
    print("Guarda o output: python analysis/generate_report_stats.py > report_stats.txt\n")


if __name__ == "__main__":
    main()
