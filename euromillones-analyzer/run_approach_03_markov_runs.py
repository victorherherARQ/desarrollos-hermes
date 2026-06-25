"""Acercamiento 3: Memoria y rachas (Markov de orden 1 + test de rachas).

Hipotesis nula: los sorteos son independientes.
Si hay memoria, el sorteo N+1 deberia depender del N.

Probamos:
1. Test de rachas (runs test): ¿los sorteos 'calientes' y 'frios'
   se agrupan o se alternan aleatoriamente?
2. Markov orden 1 para la suma: P(suma_{t+1} | suma_t)
3. Correlacion entre el mismo numero apareciendo en N y N+k
"""
import sys
sys.path.insert(0, '.')
import json
import pandas as pd
import numpy as np
from scipy import stats

from src.db.repository import SorteoRepository
from src.analysis.descriptive import to_dataframe


def runs_test(valores: np.ndarray) -> dict:
    """Test de rachas sobre una secuencia binaria (1=aparece, 0=no).
    
    H0: la secuencia es aleatoria (rachas siguen distribucion esperada).
    """
    n = len(valores)
    n1 = int(valores.sum())  # numero de 1s
    n0 = n - n1
    if n1 == 0 or n0 == 0:
        return {"error": "Secuencia constante, no se puede aplicar"}
    
    # Contar rachas (runs)
    runs = 1
    for i in range(1, n):
        if valores[i] != valores[i-1]:
            runs += 1
    
    # Media y varianza bajo H0
    mu = (2 * n1 * n0) / n + 1
    var = (2 * n1 * n0 * (2 * n1 * n0 - n)) / (n**2 * (n - 1))
    if var <= 0:
        return {"error": "Varianza no positiva"}
    
    # Estadistico Z
    z = (runs - mu) / np.sqrt(var)
    p_dos_colas = 2 * (1 - stats.norm.cdf(abs(z)))
    return {
        "n_sorteos": n,
        "n_apariciones": n1,
        "n_rachas_observadas": runs,
        "n_rachas_esperadas": mu,
        "z_stat": float(z),
        "p_value": float(p_dos_colas),
        "hay_patron_rachas": p_dos_colas < 0.05,
        "interpretacion": "mas rachas=z<0 (alternancia), menos rachas=z>0 (agrupacion)"
    }


def autocorr_reaparicion(df: pd.DataFrame, lag: int = 1) -> dict:
    """Para cada numero, ¿es mas probable que aparezca en N+k si aparecio en N?"""
    n = len(df)
    elementos = list(range(1, 51))
    results = []
    for num in elementos:
        # Crear secuencia binaria
        seq = df["nums"].apply(lambda ns: int(num in ns)).values
        if seq.sum() < 5:
            continue
        # Probabilidad P(numero en t+lag | numero en t)
        # Correlacion: cov(seq[:-lag], seq[lag:]) / var(seq)
        if np.std(seq) == 0:
            continue
        ac = np.corrcoef(seq[:-lag], seq[lag:])[0, 1]
        results.append({
            "elemento": num,
            "apariciones": int(seq.sum()),
            "autocorr_lag1": float(ac) if not np.isnan(ac) else 0,
        })
    return pd.DataFrame(results)


def autocorr_suma(df: pd.DataFrame, max_lag: int = 10) -> pd.DataFrame:
    """Autocorrelacion de la suma hasta lag max_lag."""
    s = df["suma"].values
    s_mean = s.mean()
    s_var = ((s - s_mean)**2).sum()
    rows = []
    for lag in range(1, max_lag + 1):
        cov = ((s[:-lag] - s_mean) * (s[lag:] - s_mean)).sum()
        ac = cov / s_var
        # Test de Ljung-Box simplificado
        n = len(s)
        z = ac * np.sqrt(n - lag)
        p = 2 * (1 - stats.norm.cdf(abs(z)))
        rows.append({
            "lag": lag,
            "autocorrelacion": float(ac),
            "z_stat": float(z),
            "p_value": float(p),
            "significativo": p < 0.05,
        })
    return pd.DataFrame(rows)


def markov_suma(df: pd.DataFrame, n_bins: int = 5) -> dict:
    """Markov orden 1 sobre la suma categorizada en n_bins.
    
    H0: P(suma_{t+1} | suma_t) = P(suma_{t+1}) (independencia)
    Test: chi² de independencia entre estado actual y siguiente.
    """
    s = df["suma"].values
    # Categorizar: bajo, medio-bajo, medio, medio-alto, alto
    cats = pd.qcut(s, q=n_bins, labels=False, duplicates='drop')
    # Tabla de transicion
    tabla = np.zeros((n_bins, n_bins))
    for i in range(len(cats) - 1):
        tabla[cats[i], cats[i+1]] += 1
    # Chi² de independencia
    chi2, p, dof, expected = stats.chi2_contingency(tabla)
    return {
        "n_bins": n_bins,
        "n_transiciones": int(tabla.sum()),
        "chi2": float(chi2),
        "p_value": float(p),
        "dof": int(dof),
        "hay_memoria": p < 0.05,
        "matriz_transicion": tabla.tolist(),
    }


def main():
    repo = SorteoRepository('data/euromillones.db')
    sorteos = repo.get_all()
    df = to_dataframe(sorteos)
    print(f"Total sorteos: {len(df)}\n")

    # 1. Test de rachas para cada numero
    print("=" * 70)
    print("TEST DE RACHAS POR NUMERO (¿se agrupan o alternan?)")
    print("=" * 70)
    runs_results = []
    for num in range(1, 51):
        seq = df["nums"].apply(lambda ns: int(num in ns)).values
        r = runs_test(seq)
        if "error" not in r:
            r["elemento"] = num
            runs_results.append(r)
    df_runs = pd.DataFrame(runs_results)
    sig = df_runs[df_runs["p_value"] < 0.05]
    print(f"\nTotal numeros testados: {len(df_runs)}")
    print(f"Numeros con patron de rachas (p<0.05): {len(sig)}")
    print(f"Esperados por azar (5%): {len(df_runs)*0.05:.1f}")
    if len(sig) > 0:
        print("\nNumeros con rachas anomalas:")
        print(sig[["elemento", "n_rachas_observadas", "n_rachas_esperadas", "z_stat", "p_value"]].to_string(index=False))

    # 2. Autocorrelacion de la suma
    print("\n" + "=" * 70)
    print("AUTOCORRELACION DE LA SUMA (lags 1 a 10)")
    print("=" * 70)
    ac = autocorr_suma(df, max_lag=10)
    print(ac.to_string(index=False))
    sig_lags = ac[ac["significativo"]]
    print(f"\nLags significativos (p<0.05): {len(sig_lags)}")
    if len(sig_lags) > 0:
        print("Hay memoria en la suma: el resultado anterior influye en el siguiente")

    # 3. Autocorrelacion de cada numero con lag=1
    print("\n" + "=" * 70)
    print("AUTOCORRELACION POR NUMERO (lag=1)")
    print("=" * 70)
    df_ac = autocorr_reaparicion(df, lag=1)
    print(f"Autocorrelacion media: {df_ac['autocorr_lag1'].mean():.4f}")
    print(f"Autocorrelacion maxima: {df_ac['autocorr_lag1'].max():.4f}")
    print(f"Autocorrelacion minima: {df_ac['autocorr_lag1'].min():.4f}")
    # Cuantos tienen autocorrelacion positiva alta?
    top_ac = df_ac.nlargest(5, "autocorr_lag1")
    print("\nTop 5 numeros con mas autocorrelacion positiva (mas probable que se repita):")
    print(top_ac.to_string(index=False))
    bottom_ac = df_ac.nsmallest(5, "autocorr_lag1")
    print("\nTop 5 numeros con mas autocorrelacion negativa (alternancia):")
    print(bottom_ac.to_string(index=False))

    # 4. Markov sobre suma categorizada
    print("\n" + "=" * 70)
    print("MARKOV ORDEN 1 SOBRE LA SUMA (categorizada en 5 bins)")
    print("=" * 70)
    mk = markov_suma(df, n_bins=5)
    print(f"Chi² de independencia: {mk['chi2']:.2f}, p={mk['p_value']:.4f}")
    print(f"Hay memoria (p<0.05): {mk['hay_memoria']}")

    # Guardar
    output = {
        "metodologia": "Tres analisis de memoria: (1) runs test sobre secuencia binaria por numero, "
                        "(2) autocorrelacion de suma con lags 1-10, "
                        "(3) autocorrelacion binaria por numero en lag 1, "
                        "(4) Markov orden 1 sobre suma categorizada.",
        "runs_test": {
            "n_elementos_testeados": len(df_runs),
            "n_con_patron_p005": int(len(sig)),
            "elementos_significativos": sig.to_dict(orient='records') if len(sig) > 0 else [],
        },
        "autocorr_suma": ac.to_dict(orient='records'),
        "autocorr_por_numero": {
            "media": float(df_ac["autocorr_lag1"].mean()),
            "max": float(df_ac["autocorr_lag1"].max()),
            "min": float(df_ac["autocorr_lag1"].min()),
            "top5_positivo": top_ac.to_dict(orient='records'),
            "top5_negativo": bottom_ac.to_dict(orient='records'),
        },
        "markov_suma": {k: v for k, v in mk.items() if k != "matriz_transicion"},
    }
    with open('reports/informes/informe_03_markov_memoria.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[OK] Guardado en reports/informes/informe_03_markov_memoria.json")


if __name__ == "__main__":
    main()
