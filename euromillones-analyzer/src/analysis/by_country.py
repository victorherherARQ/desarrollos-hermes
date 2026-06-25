"""Analisis por periodos temporales (Euromillones es transnacional, no por pais).

Euromillones es un sorteo UNICO para 9 paises. Los numeros NO varian por pais.
Pero el juego ha cambiado reglas a lo largo del tiempo:
- 2004-02-13: inicio del juego
- 2011-05-10: se introdujo el limite de jackpot en EUR 190M (cap)
- 2020-02-04: cap elevado a EUR 200M
- 2022-03-15: se anade 'El Millon' (juego asociado espanol)

Estos cambios pueden afectar las distribuciones.
"""
import pandas as pd
from scipy import stats


PERIODOS = [
    ("inicio_juego", "2004-02-13", "2011-05-09", "Inicio del juego"),
    ("pre_cap", "2011-05-10", "2020-02-03", "Con cap de jackpot (190M)"),
    ("post_cap_200", "2020-02-04", "2026-12-31", "Con cap elevado (200M)"),
]


def asignar_periodo(fecha) -> str:
    """Asigna un periodo a una fecha."""
    for nombre, ini, fin, _ in PERIODOS:
        if pd.Timestamp(ini) <= fecha <= pd.Timestamp(fin):
            return nombre
    return "desconocido"


def analisis_por_periodo(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula estadisticas basicas por periodo."""
    df = df.copy()
    df["periodo"] = df["fecha"].apply(asignar_periodo)

    rows = []
    for periodo in df["periodo"].unique():
        sub = df[df["periodo"] == periodo]
        rows.append({
            "periodo": periodo,
            "n_sorteos": len(sub),
            "rango": f"{sub['fecha'].min().date()} - {sub['fecha'].max().date()}",
            "suma_media": sub["suma"].mean(),
            "suma_std": sub["suma"].std(),
            "pares_media": sub["pares"].mean(),
            "altos_media": sub["altos"].mean(),
        })
    return pd.DataFrame(rows)


def chi2_por_periodo(df: pd.DataFrame, elemento: str = "numero") -> pd.DataFrame:
    """Chi² de cada numero/estrella por periodo vs uniforme."""
    df = df.copy()
    df["periodo"] = df["fecha"].apply(asignar_periodo)

    rows = []
    max_n = 50 if elemento == "numero" else 12
    for periodo in df["periodo"].unique():
        sub = df[df["periodo"] == periodo]
        n = len(sub)
        freq_esp_por_elemento = n * (5 if elemento == "numero" else 2) / max_n
        # Flatten todos los numeros/estrellas sorteados en este periodo
        if elemento == "numero":
            flat = pd.Series([n for ns in sub["nums"] for n in ns])
        else:
            flat = pd.Series([e for es in sub["stars"] for e in es])
        freq_obs = flat.value_counts()
        for i in range(1, max_n + 1):
            obs = freq_obs.get(i, 0)
            chi2 = (obs - freq_esp_por_elemento) ** 2 / freq_esp_por_elemento
            p_value = 1 - stats.chi2.cdf(chi2, df=1)
            rows.append({
                "periodo": periodo,
                "elemento": i,
                "observado": obs,
                "esperado": freq_esp_por_elemento,
                "desviacion_%": (obs - freq_esp_por_elemento) / freq_esp_por_elemento * 100,
                "chi2": chi2,
                "p_value": p_value,
            })
    return pd.DataFrame(rows)
