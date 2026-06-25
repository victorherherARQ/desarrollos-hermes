"""Backtesting riguroso de patrones detectados.

Estrategia:
1. Split temporal: train (2004-2020) -> encontrar patrones
2. Test (2021-2026) -> validar que los patrones se cumplen

Tipos de hipotesis:
A. "El numero X sale mas que el promedio": ¿en test sale mas?
B. "El numero X no sale": ¿en test sale menos?
C. "Los pares correlacionados X-Y": ¿se mantienen en test?
D. "Rachas negativas se rompen": ¿los numeros en racha acaban saliendo?
"""
import pandas as pd
import numpy as np
from scipy import stats
from .descriptive import test_chi_cuadrado_numeros, test_chi_cuadrado_estrellas
from .statistics import bonferroni, fdr_bh, holm


def split_temporal(df: pd.DataFrame, year_split: int = 2021) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split por anio."""
    train = df[df["fecha"].dt.year < year_split].copy()
    test = df[df["fecha"].dt.year >= year_split].copy()
    return train, test


def backtest_frecuencia(df_train: pd.DataFrame, df_test: pd.DataFrame,
                         elementos_train_sig: list[dict]) -> pd.DataFrame:
    """Para cada elemento significativo en train, ¿se confirma en test?

    elementos_train_sig: lista de dicts con {tipo, elemento, esperado, desviacion_%}
    """
    n_train = len(df_train)
    n_test = len(df_test)
    results = []

    # Frecuencias en test
    test_flat_nums = pd.Series([n for ns in df_test["nums"] for n in ns])
    test_freq_nums = test_flat_nums.value_counts().to_dict()
    test_flat_stars = pd.Series([e for es in df_test["stars"] for e in es])
    test_freq_stars = test_flat_stars.value_counts().to_dict()

    for elem in elementos_train_sig:
        if elem["tipo"] == "numero":
            obs_test = test_freq_nums.get(elem["elemento"], 0)
            esp_test = n_test * 5 / 50
        else:
            obs_test = test_freq_stars.get(elem["elemento"], 0)
            esp_test = n_test * 2 / 12
        chi2 = (obs_test - esp_test) ** 2 / esp_test if esp_test > 0 else 0
        p_test = 1 - stats.chi2.cdf(chi2, df=1)
        results.append({
            "tipo": elem["tipo"],
            "elemento": elem["elemento"],
            "desviacion_train_%": elem["desviacion_%"],
            "observado_test": obs_test,
            "esperado_test": esp_test,
            "desviacion_test_%": (obs_test - esp_test) / esp_test * 100 if esp_test > 0 else 0,
            "p_test": p_test,
            "se_confirma_direccion": (elem["desviacion_%"] > 0 and obs_test > esp_test) or
                                       (elem["desviacion_%"] < 0 and obs_test < esp_test),
        })
    return pd.DataFrame(results)


def backtest_completo(df: pd.DataFrame, year_split: int = 2021) -> dict:
    """Backtesting completo: detecta patrones en train, valida en test.

    Devuelve un dict con:
    - patrones_train: lista de elementos significativos en train (p<0.05 sin correccion)
    - backtest: resultados de validacion en test
    - supervivientes_bonferroni: cuantos sobreviven tras Bonferroni
    - supervivientes_fdr: cuantos sobreviven tras FDR
    """
    df_train, df_test = split_temporal(df, year_split)
    print(f"Train: {len(df_train)} sorteos ({df_train['fecha'].min().date()} - {df_train['fecha'].max().date()})")
    print(f"Test:  {len(df_test)} sorteos ({df_test['fecha'].min().date()} - {df_test['fecha'].max().date()})")

    # 1. Detectar patrones en train
    chi_n_train = test_chi_cuadrado_numeros(df_train)
    chi_e_train = test_chi_cuadrado_estrellas(df_train)

    # Combinar todos los p-values
    p_values_train = list(chi_n_train["p_value"]) + list(chi_e_train["p_value"])
    significativos_idx = [i for i, p in enumerate(p_values_train) if p < 0.05]

    print(f"\nPatron significativos en train (p<0.05 sin correccion): {len(significativos_idx)}")
    print(f"  Esperados por azar: ~5% de {len(p_values_train)} = {len(p_values_train)*0.05:.1f}")

    # 2. Aplicar correcciones
    bonf_rejected = bonferroni(p_values_train, alpha=0.05)
    fdr_rejected = fdr_bh(p_values_train, alpha=0.05)
    holm_rejected = holm(p_values_train, alpha=0.05)

    n_bonf = sum(bonf_rejected)
    n_fdr = sum(fdr_rejected)
    n_holm = sum(holm_rejected)
    print(f"\nTras correccion:")
    print(f"  Bonferroni: {n_bonf} sobreviven")
    print(f"  FDR (BH): {n_fdr} sobreviven")
    print(f"  Holm: {n_holm} sobreviven")

    # 3. Listar supervivientes
    supervivientes = []
    all_elements = (
        [{"tipo": "numero", "elemento": r["numero"], "p_train": r["p_value"],
          "desviacion_%": r["desviacion_%"]} for _, r in chi_n_train.iterrows()] +
        [{"tipo": "estrella", "elemento": r["estrella"], "p_train": r["p_value"],
          "desviacion_%": r["desviacion_%"]} for _, r in chi_e_train.iterrows()]
    )
    for i, elem in enumerate(all_elements):
        if bonf_rejected[i]:
            supervivientes.append({**elem, "correccion": "bonferroni"})
        elif fdr_rejected[i]:
            supervivientes.append({**elem, "correccion": "fdr_bh"})
        elif holm_rejected[i]:
            supervivientes.append({**elem, "correccion": "holm"})

    print(f"\nSupervivientes:")
    for s in supervivientes:
        print(f"  {s['tipo']:10s} {s['elemento']:2}: desv_train={s['desviacion_%']:+.1f}% p_train={s['p_train']:.2e} via {s['correccion']}")

    # 4. Validar supervivientes en test
    if supervivientes:
        backtest_df = backtest_frecuencia(df_train, df_test, supervivientes)
        print(f"\n=== VALIDACION EN TEST ===")
        for _, r in backtest_df.iterrows():
            print(f"  {r['tipo']:10s} {r['elemento']:2}: "
                  f"train desv={r['desviacion_train_%']:+.1f}% -> test desv={r['desviacion_test_%']:+.1f}% "
                  f"p_test={r['p_test']:.3f} "
                  f"{'CONFIRMADO' if r['se_confirma_direccion'] else 'NO CONFIRMADO'}")
    else:
        backtest_df = pd.DataFrame()

    return {
        "n_train": len(df_train),
        "n_test": len(df_test),
        "year_split": year_split,
        "patrones_train_sin_correccion": len(significativos_idx),
        "n_bonferroni": n_bonf,
        "n_fdr": n_fdr,
        "n_holm": n_holm,
        "supervivientes": supervivientes,
        "backtest_df": backtest_df,
    }


def walk_forward_validation(df: pd.DataFrame, year_split: int = 2021,
                              window_years: int = 2) -> pd.DataFrame:
    """Validacion walk-forward: reentrena y valida en ventanas solapadas.

    Para cada anio del test:
    - Train: todo hasta inicio de ese anio
    - Test: ese anio
    Mide si los patrones sobreviven.
    """
    years_test = sorted(df[df["fecha"].dt.year >= year_split]["fecha"].dt.year.unique())
    results = []

    for year in years_test:
        train = df[df["fecha"].dt.year < year]
        test_year = df[df["fecha"].dt.year == year]
        if len(train) < 100 or len(test_year) < 5:
            continue

        # Detectar numeros frios en train (bottom 5)
        flat = pd.Series([n for ns in train["nums"] for n in ns])
        freq = flat.value_counts().sort_values()
        top_frios = freq.head(5).index.tolist()

        # Ver en test: salieron los frios?
        test_flat = pd.Series([n for ns in test_year["nums"] for n in ns])
        test_freq = test_flat.value_counts().to_dict()
        for frio in top_frios:
            obs = test_freq.get(frio, 0)
            esp = len(test_year) * 5 / 50
            chi2 = (obs - esp) ** 2 / esp if esp > 0 else 0
            p = 1 - stats.chi2.cdf(chi2, df=1)
            results.append({
                "year": year,
                "elemento": frio,
                "obs_test": obs,
                "esp_test": esp,
                "p_test": p,
                "sigue_frio": obs < esp,
            })
    return pd.DataFrame(results)
