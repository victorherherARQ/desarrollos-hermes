"""Acercamiento 1: Segmentacion por anios.

Divide los 1951 sorteos en bloques de 4-5 anios y mide la frecuencia
de cada numero/estrella por bloque. Si hay cambios significativos
entre bloques, sugiere que el comportamiento del bombo ha cambiado.

Bloques:
  - 2004-2008 (periodo fundacional)
  - 2009-2013 (antes del cambio de reglas 2011)
  - 2014-2018 (periodo estable)
  - 2019-2023 (periodo COVID, cambio cap 2020)
  - 2024-2026 (periodo reciente, datos parciales)
"""
import sys
sys.path.insert(0, '.')
import json
import pandas as pd
import numpy as np
from scipy import stats

from src.db.repository import SorteoRepository
from src.analysis.descriptive import to_dataframe


BLOQUES = [
    ("2004-2008", 2004, 2008),
    ("2009-2013", 2009, 2013),
    ("2014-2018", 2014, 2018),
    ("2019-2023", 2019, 2023),
    ("2024-2026", 2024, 2026),
]


def chi2_bloque(bloque_df: pd.DataFrame, elemento: str = "numero") -> dict:
    """Chi² global de cada elemento vs uniforme dentro del bloque."""
    n = len(bloque_df)
    if n < 10:
        return {"n": n, "skip": True}
    if elemento == "numero":
        flat = pd.Series([x for ns in bloque_df["nums"] for x in ns])
        max_e = 50
        per_sorteo = 5
    else:
        flat = pd.Series([e for es in bloque_df["stars"] for e in es])
        max_e = 12
        per_sorteo = 2
    freq_obs = flat.value_counts()
    freq_esp = n * per_sorteo / max_e
    results = []
    for i in range(1, max_e + 1):
        obs = freq_obs.get(i, 0)
        chi2 = (obs - freq_esp) ** 2 / freq_esp if freq_esp > 0 else 0
        p = 1 - stats.chi2.cdf(chi2, df=1)
        results.append({
            "elemento": i,
            "observado": obs,
            "esperado": freq_esp,
            "desviacion_%": (obs - freq_esp) / freq_esp * 100 if freq_esp > 0 else 0,
            "chi2": chi2,
            "p_value": p,
        })
    return {
        "n": n,
        "skip": False,
        "resultados": pd.DataFrame(results),
    }


def test_homogeneidad_entre_bloques(bloque_dfs: list[pd.DataFrame], elemento: str) -> dict:
    """Test chi² de homogeneidad: ¿la distribucion cambia entre bloques?

    Hipotesis nula: la distribucion es la misma en todos los bloques.
    Si rechazamos H0, hay evidencia de cambio de regimen.
    """
    if elemento == "numero":
        max_e = 50
    else:
        max_e = 12

    # Construir tabla de contingencia: filas=elementos, columnas=bloques
    tabla = []
    for i in range(1, max_e + 1):
        fila = []
        for bloque_df in bloque_dfs:
            if elemento == "numero":
                flat = pd.Series([x for ns in bloque_df["nums"] for x in ns])
            else:
                flat = pd.Series([e for es in bloque_df["stars"] for e in es])
            obs = (flat == i).sum()
            fila.append(obs)
        tabla.append(fila)
    tabla = np.array(tabla)

    # Aplicar chi² de homogeneidad
    try:
        chi2, p, dof, expected = stats.chi2_contingency(tabla)
        return {
            "chi2": float(chi2),
            "p_value": float(p),
            "dof": int(dof),
            "significativo_p005": p < 0.005,  # mas estricto por multiples tests
            "significativo_p001": p < 0.001,
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    repo = SorteoRepository('data/euromillones.db')
    sorteos = repo.get_all()
    df = to_dataframe(sorteos)
    print(f"Total sorteos cargados: {len(df)}")
    print(f"Rango: {df['fecha'].min().date()} -> {df['fecha'].max().date()}")
    print()

    # Construir bloques
    bloques_df = {}
    for nombre, ini, fin in BLOQUES:
        bloque = df[(df["fecha"].dt.year >= ini) & (df["fecha"].dt.year <= fin)].copy()
        bloques_df[nombre] = bloque
        print(f"Bloque {nombre}: {len(bloque)} sorteos "
              f"({bloque['fecha'].min().date() if len(bloque) else 'N/A'} - "
              f"{bloque['fecha'].max().date() if len(bloque) else 'N/A'})")

    # Para cada bloque: top 5 elementos desviados
    print("\n" + "=" * 70)
    print("TOP 5 DESVIACIONES POR BLOQUE")
    print("=" * 70)
    summary_por_bloque = {}
    for nombre, bloque in bloques_df.items():
        chi_n = chi2_bloque(bloque, "numero")
        chi_e = chi2_bloque(bloque, "estrella")
        if chi_n.get("skip") or chi_e.get("skip"):
            continue
        top_n = chi_n["resultados"].sort_values("chi2", ascending=False).head(5)
        top_e = chi_e["resultados"].sort_values("chi2", ascending=False).head(5)
        print(f"\n--- BLOQUE {nombre} (n={len(bloque)}) ---")
        print("TOP 5 NUMEROS:")
        print(top_n.to_string(index=False))
        print("TOP 5 ESTRELLAS:")
        print(top_e.to_string(index=False))
        summary_por_bloque[nombre] = {
            "n": len(bloque),
            "top_numeros": top_n.to_dict(orient='records'),
            "top_estrellas": top_e.to_dict(orient='records'),
        }

    # Test de homogeneidad entre bloques
    print("\n" + "=" * 70)
    print("TEST DE HOMOGENEIDAD ENTRE BLOQUES")
    print("Pregunta: ¿cambia la distribucion de frecuencias entre bloques?")
    print("=" * 70)
    bloques_validos = [bloques_df[n] for n, _, _ in BLOQUES if len(bloques_df[n]) >= 10]
    hom_n = test_homogeneidad_entre_bloques(bloques_validos, "numero")
    hom_e = test_homogeneidad_entre_bloques(bloques_validos, "estrella")
    print(f"\nNumeros: chi²={hom_n.get('chi2', 'N/A'):.2f}, p={hom_n.get('p_value', 'N/A'):.4e}, "
          f"dof={hom_n.get('dof')}, significativo(p<0.001): {hom_n.get('significativo_p001')}")
    print(f"Estrellas: chi²={hom_e.get('chi2', 'N/A'):.2f}, p={hom_e.get('p_value', 'N/A'):.4e}, "
          f"dof={hom_e.get('dof')}, significativo(p<0.001): {hom_e.get('significativo_p001')}")

    # Test adicional: comparar bloque mas reciente vs resto
    print("\n" + "=" * 70)
    print("BLOQUE 2024-2026 vs RESTO (test de cambio de regimen reciente)")
    print("=" * 70)
    reciente = bloques_df["2024-2026"]
    resto = df[df["fecha"].dt.year < 2024].copy()
    if len(reciente) > 10:
        for elem in ["numero", "estrella"]:
            tabla = []
            for i in range(1, (50 if elem == "numero" else 12) + 1):
                if elem == "numero":
                    obs_reciente = sum(i in ns for ns in reciente["nums"])
                    obs_resto = sum(i in ns for ns in resto["nums"])
                else:
                    obs_reciente = sum(i in es for es in reciente["stars"])
                    obs_resto = sum(i in es for es in resto["stars"])
                tabla.append([obs_reciente, obs_resto])
            chi2, p, dof, _ = stats.chi2_contingency(np.array(tabla))
            print(f"  {elem}: chi²={chi2:.2f}, p={p:.4e}, dof={dof}")

    # Guardar resultados
    output = {
        "metodologia": "Segmentacion en 5 bloques temporales. Para cada bloque: chi² por elemento. Ademas: test de homogeneidad chi² entre todos los bloques, y test 2024-2026 vs resto.",
        "bloques": BLOQUES,
        "summary_por_bloque": summary_por_bloque,
        "homogeneidad_numeros": hom_n,
        "homogeneidad_estrellas": hom_e,
    }
    with open('reports/informes/informe_01_segmentacion_anual.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[OK] Guardado en reports/informes/informe_01_segmentacion_anual.json")


if __name__ == "__main__":
    main()
