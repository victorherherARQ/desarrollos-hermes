"""Detector de patrones sobre los resultados historicos.

Tipos de patrones:
1. Frecuencia simple (numeros/estrellas calientes/frios)
2. Pares correlacionados (numeros que salen juntos)
3. Anti-frecuencia (rachas sin salir)
4. Patrones temporales (cambios por epoca)
5. Patrones de suma
6. Paridad/composicion
7. Por dia de semana (martes vs viernes)
8. Auto-correlacion temporal
"""
import pandas as pd
import numpy as np
from scipy import stats
from collections import Counter
from itertools import combinations


def _flatten_nums(df: pd.DataFrame) -> pd.Series:
    """Todos los numeros sorteados como Serie."""
    return pd.Series([n for ns in df["nums"] for n in ns])


def _flatten_stars(df: pd.DataFrame) -> pd.Series:
    """Todas las estrellas sorteadas como Serie."""
    return pd.Series([e for es in df["stars"] for e in es])


def patron_frecuencia(df: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    """Patron: cada numero/estrella es significativamente mas/menos frecuente.

    Devuelve DataFrame con elementos que tienen p < alpha (sin correccion).
    """
    n = len(df)
    results = []

    # Numeros
    flat = _flatten_nums(df)
    freq_obs = flat.value_counts()
    freq_esp = n * 5 / 50
    for num in range(1, 51):
        obs = freq_obs.get(num, 0)
        chi2 = (obs - freq_esp) ** 2 / freq_esp
        p = 1 - stats.chi2.cdf(chi2, df=1)
        results.append({
            "tipo": "numero", "elemento": num, "observado": obs, "esperado": freq_esp,
            "desviacion_%": (obs - freq_esp) / freq_esp * 100,
            "chi2": chi2, "p_value": p,
        })

    # Estrellas
    flat = _flatten_stars(df)
    freq_obs = flat.value_counts()
    freq_esp = n * 2 / 12
    for star in range(1, 13):
        obs = freq_obs.get(star, 0)
        chi2 = (obs - freq_esp) ** 2 / freq_esp
        p = 1 - stats.chi2.cdf(chi2, df=1)
        results.append({
            "tipo": "estrella", "elemento": star, "observado": obs, "esperado": freq_esp,
            "desviacion_%": (obs - freq_esp) / freq_esp * 100,
            "chi2": chi2, "p_value": p,
        })

    df_pat = pd.DataFrame(results)
    return df_pat[df_pat["p_value"] < alpha].sort_values("p_value")


def patron_pares_correlacionados(df: pd.DataFrame, min_support: int = 5,
                                   min_lift: float = 1.5) -> pd.DataFrame:
    """Patron: pares de numeros que salen juntos mas de lo esperado.

    lift = P(A,B) / (P(A) * P(B))
    lift > 1.5 -> correlacion positiva
    """
    n = len(df)
    # Contar apariciones individuales
    flat = _flatten_nums(df)
    freq_individual = flat.value_counts().to_dict()
    # Contar co-apariciones
    cooc = Counter()
    for ns in df["nums"]:
        for a, b in combinations(sorted(ns), 2):
            cooc[(a, b)] += 1
    # Calcular lift
    results = []
    for (a, b), count_ab in cooc.items():
        if count_ab < min_support:
            continue
        p_a = freq_individual[a] / (n * 5)
        p_b = freq_individual[b] / (n * 5)
        p_ab = count_ab / n
        lift = p_ab / (p_a * p_b)
        if lift >= min_lift:
            results.append({
                "num_a": a, "num_b": b, "count": count_ab,
                "support_%": count_ab / n * 100,
                "lift": lift,
            })
    return pd.DataFrame(results).sort_values("lift", ascending=False)


def patron_rachas_negativas(df: pd.DataFrame) -> pd.DataFrame:
    """Patron: numeros/estrellas con rachas negativas anomalas (no salen en N sorteos).

    Para cada numero, miramos el ultimo sorteo en que salio.
    Calculamos cuanto tiempo lleva sin salir.
    Comparamos con la distribucion esperada (inversa del ratio de salida).
    """
    n_total = len(df)
    results = []
    last_n = df.tail(1).iloc[0]

    for num in range(1, 51):
        apariciones = df["nums"].apply(lambda ns: num in ns)
        if not apariciones.any():
            continue
        ultima_pos = apariciones[apariciones].index[-1]
        # Numero de sorteos desde la ultima aparicion (incluyendo el actual)
        sorteos_desde = n_total - ultima_pos - 1
        # Ratio historico de aparicion (cada X sorteos sale)
        freq = apariciones.sum() / n_total
        sorteos_esperados = 1 / freq if freq > 0 else float('inf')
        ratio = sorteos_desde / sorteos_esperados if sorteos_esperados > 0 else 0
        results.append({
            "tipo": "numero", "elemento": num,
            "ultima_aparicion": df.iloc[ultima_pos]["fecha"].date() if ultima_pos < n_total else None,
            "sorteos_sin_salir": sorteos_desde,
            "sorteos_esperados_entre_apariciones": sorteos_esperados,
            "ratio": ratio,
        })
    return pd.DataFrame(results).sort_values("ratio", ascending=False)


def patron_por_dia_semana(df: pd.DataFrame) -> dict:
    """Patron: hay diferencias significativas entre sorteos del martes y viernes?"""
    martes = df[df["dia_semana"] == "martes"]
    viernes = df[df["dia_semana"] == "viernes"]
    if len(martes) == 0 or len(viernes) == 0:
        return {"error": "Datos insuficientes"}

    # Comparar suma media
    t_stat, p_suma = stats.ttest_ind(martes["suma"], viernes["suma"])
    return {
        "n_martes": len(martes),
        "n_viernes": len(viernes),
        "suma_media_martes": float(martes["suma"].mean()),
        "suma_media_viernes": float(viernes["suma"].mean()),
        "t_stat_suma": t_stat,
        "p_value_suma": p_suma,
        "significativo_suma": p_suma < 0.05,
    }


def patron_autocorrelacion(df: pd.DataFrame) -> dict:
    """Test de rachas: el sorteo N predice el N+1?"""
    # Test simple: la suma del sorteo N es independiente de la del N+1
    sumas = df["suma"].values
    if len(sumas) < 10:
        return {"error": "Datos insuficientes"}
    # Autocorrelacion lag-1
    acf1 = np.corrcoef(sumas[:-1], sumas[1:])[0, 1]
    return {
        "autocorrelacion_suma_lag1": acf1,
        "interpretacion": "positivo = memoria, 0 = azar, negativo = anti-memoria",
    }
