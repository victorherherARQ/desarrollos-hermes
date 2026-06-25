"""Acercamiento 6: Analisis bayesiano.

Probabilidad a posteriori de cada numero/estrella despues de observar
los 1951 sorteos, con prior uniforme.

Usando beta-binomial conjugado:
  Prior: Beta(1, 1) = uniforme
  Likelihood: numero aparece k veces en n sorteos (probabilidad por sorteo = 0.1)
  Posterior: Beta(1+k, 1+n-k)

Resultado: la distribucion a posteriori esta MUY concentrada en 0.1
porque tenemos muchos datos. Esto es la base formal de por que
'no hay patron': con 1951 observaciones, solo desviaciones extremas
mueven la aguja.
"""
import sys
sys.path.insert(0, '.')
import json
import pandas as pd
import numpy as np
from scipy import stats

from src.db.repository import SorteoRepository
from src.analysis.descriptive import to_dataframe


def beta_binomial_posterior(num: int, k: int, n: int) -> dict:
    """Posterior Beta(1+k, 1+n-k) sobre p(numero aparece en un sorteo).

    H0: p = 0.1 (uniforme: 5 nums / 50 posibles)
    """
    alpha = 1 + k
    beta = 1 + (n - k)
    # Media y moda
    mean = alpha / (alpha + beta)
    mode = (alpha - 1) / (alpha + beta - 2) if alpha > 1 and beta > 1 else None
    # Intervalo de credibilidad 95%
    ci_low = stats.beta.ppf(0.025, alpha, beta)
    ci_high = stats.beta.ppf(0.975, alpha, beta)
    # Probabilidad de que p > 0.1 (sesgo positivo)
    prob_mayor = 1 - stats.beta.cdf(0.1, alpha, beta)
    # Probabilidad de que p < 0.1 (sesgo negativo)
    prob_menor = stats.beta.cdf(0.1, alpha, beta)
    return {
        "elemento": num,
        "k": k, "n": n,
        "alpha": alpha, "beta_param": beta,
        "mean": float(mean),
        "mode": float(mode) if mode is not None else None,
        "ci_95_low": float(ci_low),
        "ci_95_high": float(ci_high),
        "prob_p_mayor_0.1": float(prob_mayor),
        "prob_p_menor_0.1": float(prob_menor),
        "sesgo": "positivo" if prob_mayor > 0.95 else ("negativo" if prob_menor > 0.95 else "neutro"),
    }


def main():
    repo = SorteoRepository('data/euromillones.db')
    sorteos = repo.get_all()
    df = to_dataframe(sorteos)
    n = len(df)
    print(f"Total sorteos: {n}\n")

    # Para numeros: prob esperada = 5/50 = 0.1
    print("=" * 70)
    print(f"POSTERIOR BAYESIANO PARA NUMEROS (esperado: p=0.1, n_sorteos={n})")
    print("=" * 70)
    flat = pd.Series([x for ns in df["nums"] for x in ns])
    freq = flat.value_counts().to_dict()
    results_n = []
    for num in range(1, 51):
        k = freq.get(num, 0)
        results_n.append(beta_binomial_posterior(num, k, n))
    df_post_n = pd.DataFrame(results_n)
    # Ordenar por prob_mayor o prob_menor (los mas desviados)
    df_post_n["max_desv_prob"] = df_post_n[["prob_p_mayor_0.1", "prob_p_menor_0.1"]].max(axis=1)
    df_post_n_sorted = df_post_n.sort_values("max_desv_prob", ascending=False)
    print("\nTop 10 numeros con posterior mas desviada de uniforme:")
    print(df_post_n_sorted.head(10)[["elemento", "k", "mean", "ci_95_low", "ci_95_high",
                                       "prob_p_mayor_0.1", "prob_p_menor_0.1", "sesgo"]].to_string(index=False))
    sesgados = df_post_n_sorted[df_post_n_sorted["sesgo"] != "neutro"]
    print(f"\nNumeros con sesgo creible (prob>0.95): {len(sesgados)}")
    if len(sesgados) > 0:
        print(sesgados[["elemento", "k", "mean", "sesgo", "max_desv_prob"]].to_string(index=False))

    # Para estrellas: prob esperada = 2/12 = 0.1667
    print("\n" + "=" * 70)
    print(f"POSTERIOR BAYESIANO PARA ESTRELLAS (esperado: p=0.1667, n_sorteos={n})")
    print("=" * 70)
    flat_e = pd.Series([e for es in df["stars"] for e in es])
    freq_e = flat_e.value_counts().to_dict()
    results_e = []
    for star in range(1, 13):
        k = freq_e.get(star, 0)
        results_e.append(beta_binomial_posterior(star, k, n))
    df_post_e = pd.DataFrame(results_e)
    df_post_e["max_desv_prob"] = df_post_e[["prob_p_mayor_0.1", "prob_p_menor_0.1"]].max(axis=1)
    df_post_e_sorted = df_post_e.sort_values("max_desv_prob", ascending=False)
    print("\nEstrellas ordenadas por desviacion posterior:")
    print(df_post_e_sorted[["elemento", "k", "mean", "ci_95_low", "ci_95_high",
                              "prob_p_mayor_0.1", "prob_p_menor_0.1", "sesgo"]].to_string(index=False))

    # Comparacion con backtest split 2021
    print("\n" + "=" * 70)
    print("VALIDACION BAYESIANA: posterior con train (2004-2020)")
    print("=" * 70)
    df_train = df[df["fecha"].dt.year < 2021]
    n_train = len(df_train)
    flat_t = pd.Series([x for ns in df_train["nums"] for x in ns])
    freq_t = flat_t.value_counts().to_dict()
    # Estrellas train
    flat_te = pd.Series([e for es in df_train["stars"] for e in es])
    freq_te = flat_te.value_counts().to_dict()

    # Top 5 con sesgo en train
    train_post_n = []
    for num in range(1, 51):
        k = freq_t.get(num, 0)
        r = beta_binomial_posterior(num, k, n_train)
        r["max_desv_prob"] = max(r["prob_p_mayor_0.1"], r["prob_p_menor_0.1"])
        train_post_n.append(r)
    df_train_post = pd.DataFrame(train_post_n).sort_values("max_desv_prob", ascending=False)
    top5_train = df_train_post.head(5)
    print("\nTop 5 numeros sesgados en train (2004-2020):")
    print(top5_train[["elemento", "k", "mean", "sesgo", "max_desv_prob"]].to_string(index=False))

    # Ver en test si esos numeros confirman
    print("\nFrecuencia observada en TEST (2021-2026) para esos 5 numeros:")
    df_test = df[df["fecha"].dt.year >= 2021]
    n_test = len(df_test)
    flat_test = pd.Series([x for ns in df_test["nums"] for x in ns])
    freq_test = flat_test.value_counts().to_dict()
    for _, r in top5_train.iterrows():
        num = r["elemento"]
        k_test = freq_test.get(num, 0)
        obs_test = k_test
        esp_test = n_test * 5 / 50
        print(f"  Num {num}: esperado={esp_test:.1f}, observado={obs_test}, "
              f"desv={(obs_test-esp_test)/esp_test*100:+.1f}%")

    # Guardar
    output = {
        "metodologia": "Beta-binomial conjugado con prior Beta(1,1). "
                        "Posterior de p(numero aparece en un sorteo) tras n observaciones. "
                        "Validacion: posterior train vs observado test.",
        "posterior_numeros_total": df_post_n_sorted.to_dict(orient='records'),
        "posterior_estrellas_total": df_post_e_sorted.to_dict(orient='records'),
        "sesgo_creible_numeros_total": sesgados.to_dict(orient='records') if len(sesgados) > 0 else [],
        "validacion_train_top5": {
            "top5_train": top5_train[["elemento", "k", "mean", "sesgo"]].to_dict(orient='records'),
            "frecuencia_test": [
                {"elemento": r["elemento"], "obs_test": freq_test.get(r["elemento"], 0)}
                for _, r in top5_train.iterrows()
            ],
        },
    }
    with open('reports/informes/informe_06_bayesiano.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[OK] Guardado en reports/informes/informe_06_bayesiano.json")


if __name__ == "__main__":
    main()
