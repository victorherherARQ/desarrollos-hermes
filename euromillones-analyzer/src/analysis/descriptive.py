"""Analisis descriptivo de los sorteos."""
import pandas as pd
import numpy as np
from scipy import stats


def to_dataframe(sorteos: list[dict]) -> pd.DataFrame:
    """Convierte lista de dicts a DataFrame con columna 'nums' (lista)."""
    df = pd.DataFrame(sorteos).copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["nums"] = df.apply(
        lambda r: sorted([r["n1"], r["n2"], r["n3"], r["n4"], r["n5"]]),
        axis=1,
    )
    df["stars"] = df.apply(
        lambda r: sorted([r["e1"], r["e2"]]), axis=1
    )
    df["suma"] = df["n1"] + df["n2"] + df["n3"] + df["n4"] + df["n5"]
    df["pares"] = df["nums"].apply(lambda ns: sum(1 for n in ns if n % 2 == 0))
    df["altos"] = df["nums"].apply(lambda ns: sum(1 for n in ns if n > 25))
    df["consecutivos"] = df["nums"].apply(_count_consecutive)
    return df


def _count_consecutive(nums: list[int]) -> int:
    """Cuenta cuantos pares consecutivos hay (ej: [3,4,7,8,15] -> 2)."""
    s = sorted(nums)
    return sum(1 for i in range(len(s) - 1) if s[i + 1] == s[i] + 1)


def freq_numeros(df: pd.DataFrame) -> pd.Series:
    """Frecuencia absoluta de cada numero (1-50)."""
    nums_flat = [n for ns in df["nums"] for n in ns]
    return pd.Series(nums_flat).value_counts().sort_index()


def freq_estrellas(df: pd.DataFrame) -> pd.Series:
    """Frecuencia absoluta de cada estrella (1-12)."""
    stars_flat = [e for es in df["stars"] for e in es]
    return pd.Series(stars_flat).value_counts().sort_index()


def test_chi_cuadrado_numeros(df: pd.DataFrame) -> pd.DataFrame:
    """Test chi-cuadrado de cada numero vs distribucion uniforme esperada."""
    n = len(df)
    freq_obs = freq_numeros(df)
    freq_esp = n * 5 / 50  # cada numero deberia salir ~5/50 = 10% de las veces
    results = []
    for num in range(1, 51):
        obs = freq_obs.get(num, 0)
        # chi² = (obs-esp)^2 / esp
        chi2 = (obs - freq_esp) ** 2 / freq_esp
        p_value = 1 - stats.chi2.cdf(chi2, df=1)
        results.append({
            "numero": num,
            "observado": obs,
            "esperado": freq_esp,
            "desviacion_%": (obs - freq_esp) / freq_esp * 100,
            "chi2": chi2,
            "p_value": p_value,
        })
    return pd.DataFrame(results)


def test_chi_cuadrado_estrellas(df: pd.DataFrame) -> pd.DataFrame:
    """Test chi-cuadrado de cada estrella vs distribucion uniforme esperada."""
    n = len(df)
    freq_obs = freq_estrellas(df)
    freq_esp = n * 2 / 12
    results = []
    for star in range(1, 13):
        obs = freq_obs.get(star, 0)
        chi2 = (obs - freq_esp) ** 2 / freq_esp
        p_value = 1 - stats.chi2.cdf(chi2, df=1)
        results.append({
            "estrella": star,
            "observado": obs,
            "esperado": freq_esp,
            "desviacion_%": (obs - freq_esp) / freq_esp * 100,
            "chi2": chi2,
            "p_value": p_value,
        })
    return pd.DataFrame(results)


def estadisticas_suma(df: pd.DataFrame) -> dict:
    """Estadisticas basicas de la suma de los 5 numeros."""
    return {
        "n": len(df),
        "min": int(df["suma"].min()),
        "max": int(df["suma"].max()),
        "media": float(df["suma"].mean()),
        "mediana": float(df["suma"].median()),
        "std": float(df["suma"].std()),
        "teorica_min": 1 + 2 + 3 + 4 + 5,
        "teorica_max": 46 + 47 + 48 + 49 + 50,
        "teorica_media": (1 + 50) / 2 * 5,
    }


def distribucion_paridad(df: pd.DataFrame) -> pd.DataFrame:
    """Frecuencia de combinaciones pares/impares (0/5 a 5/5)."""
    return df["pares"].value_counts().sort_index().reset_index()


def distribucion_altos_bajos(df: pd.DataFrame) -> pd.DataFrame:
    """Frecuencia de combinaciones altos (>25) / bajos (<=25)."""
    return df["altos"].value_counts().sort_index().reset_index()


def distribucion_consecutivos(df: pd.DataFrame) -> pd.DataFrame:
    """Frecuencia de numero de pares consecutivos en el sorteo."""
    return df["consecutivos"].value_counts().sort_index().reset_index()
