"""Acercamiento 5: Entropia e Informacion Mutua.

Mide:
1. Entropia condicional de la suma dado el resultado anterior
2. Informacion mutua entre pares de numeros (¿saber uno reduce incertidumbre del otro?)
3. Informacion mutua suma_{t} vs suma_{t+1}
4. Entropia por dia de semana
"""
import sys
sys.path.insert(0, '.')
import json
import pandas as pd
import numpy as np
from scipy import stats
from itertools import combinations

from src.db.repository import SorteoRepository
from src.analysis.descriptive import to_dataframe


def entropy(probs: pd.Series) -> float:
    """Entropia de Shannon en bits. Solo considera p>0."""
    p = probs[probs > 0]
    return float(-(p * np.log2(p)).sum())


def info_mutua_conjunta(df: pd.DataFrame, num_a: int, num_b: int) -> dict:
    """Informacion mutua I(A;B) entre dos numeros.

    I(A;B) = H(A) + H(B) - H(A,B)
    Mide cuantos bits de informacion da saber A sobre B.
    """
    n = len(df)
    # P(A), P(B)
    pa = df["nums"].apply(lambda ns: num_a in ns).mean()
    pb = df["nums"].apply(lambda ns: num_b in ns).mean()
    pab = df["nums"].apply(lambda ns: num_a in ns and num_b in ns).mean()
    if pa == 0 or pb == 0 or pab == 0:
        return {"num_a": num_a, "num_b": num_b, "mi_bits": 0}
    # H(A), H(B), H(A,B)
    h_a = -(pa * np.log2(pa) + (1-pa) * np.log2(1-pa))
    h_b = -(pb * np.log2(pb) + (1-pb) * np.log2(1-pb))
    p_no_no = 1 - pa - pb + pab
    p_no_si = pa - pab
    p_si_no = pb - pab
    p_si_si = pab
    probs = pd.Series([p_no_no, p_no_si, p_si_no, p_si_si])
    h_ab = entropy(probs)
    mi = h_a + h_b - h_ab
    return {
        "num_a": num_a, "num_b": num_b,
        "p_a": float(pa), "p_b": float(pb), "p_ab": float(pab),
        "h_a_bits": float(h_a), "h_b_bits": float(h_b),
        "h_ab_bits": float(h_ab),
        "mi_bits": float(mi),
    }


def info_mutua_sumas_consecutivas(df: pd.DataFrame, n_bins: int = 10) -> dict:
    """I(suma_t ; suma_{t+1}) categorizadas en n_bins."""
    sumas = df["suma"].values
    s_t = pd.qcut(sumas[:-1], q=n_bins, labels=False, duplicates='drop')
    s_next = pd.qcut(sumas[1:], q=n_bins, labels=False, duplicates='drop')
    tabla = pd.crosstab(s_t, s_next)
    # MI de tabla de contingencia
    p_xy = tabla / tabla.sum().sum()
    p_x = p_xy.sum(axis=1)
    p_y = p_xy.sum(axis=0)
    # MI = sum p(x,y) log(p(x,y)/(p(x)*p(y)))
    mi = 0
    for x in p_xy.index:
        for y in p_xy.columns:
            if p_xy.loc[x, y] > 0:
                mi += p_xy.loc[x, y] * np.log2(p_xy.loc[x, y] / (p_x[x] * p_y[y]))
    return {
        "n_bins": n_bins,
        "mi_bits": float(mi),
        "interpretacion": "0 = independientes, >0 = memoria",
        "n_transiciones": int(tabla.sum().sum()),
    }


def entropia_por_dia_semana(df: pd.DataFrame) -> dict:
    """Entropia de la distribucion por dia de semana (martes vs viernes)."""
    results = {}
    for dia in df["dia_semana"].unique():
        sub = df[df["dia_semana"] == dia]
        if len(sub) < 10:
            continue
        nums = pd.Series([x for ns in sub["nums"] for x in ns])
        freq = nums.value_counts(normalize=True)
        results[dia] = {
            "n": len(sub),
            "entropia_bits": entropy(freq),
            "suma_media": float(sub["suma"].mean()),
        }
    return results


def main():
    repo = SorteoRepository('data/euromillones.db')
    sorteos = repo.get_all()
    df = to_dataframe(sorteos)
    print(f"Total sorteos: {len(df)}\n")

    # 1. Informacion mutua entre numeros (top 10 pares)
    print("=" * 70)
    print("INFORMACION MUTUA ENTRE PARES DE NUMEROS (top 10)")
    print("=" * 70)
    print("MI = 0 => independientes, MI > 0 => saber uno ayuda a predecir el otro")
    pares_mi = []
    # Para eficiencia, solo pares entre los 15 mas frecuentes
    flat = pd.Series([x for ns in df["nums"] for x in ns])
    top_nums = flat.value_counts().head(15).index.tolist()
    for a, b in combinations(top_nums, 2):
        mi = info_mutua_conjunta(df, a, b)
        pares_mi.append(mi)
    df_mi = pd.DataFrame(pares_mi).sort_values("mi_bits", ascending=False)
    print(df_mi.head(10).to_string(index=False))

    # MI media de los pares vs MI esperada bajo independencia
    mi_media = df_mi["mi_bits"].mean()
    print(f"\nMI media: {mi_media:.4f} bits (esperado ~0 bajo independencia)")

    # 2. I(suma_t ; suma_{t+1})
    print("\n" + "=" * 70)
    print("INFORMACION MUTUA ENTRE SUMAS CONSECUTIVAS")
    print("=" * 70)
    mi_sumas = info_mutua_sumas_consecutivas(df, n_bins=10)
    print(f"MI(suma_t ; suma_{{t+1}}) = {mi_sumas['mi_bits']:.4f} bits")
    print(f"Esperado bajo independencia: ~0 bits")

    # 3. Entropia por dia de semana
    print("\n" + "=" * 70)
    print("ENTROPIA POR DIA DE SEMANA")
    print("=" * 70)
    ent_dia = entropia_por_dia_semana(df)
    for dia, info in ent_dia.items():
        print(f"  {dia}: n={info['n']}, H={info['entropia_bits']:.4f} bits, "
              f"suma_media={info['suma_media']:.2f}")

    # 4. Entropia del sistema completo
    print("\n" + "=" * 70)
    print("ENTROPIA DEL SISTEMA COMPLETO")
    print("=" * 70)
    # Una "combinacion" completa = tupla ordenada de 5 numeros distintos + 2 estrellas
    # No podemos medir entropia directa, pero si combinatoria
    from math import comb, log2
    # Total combinaciones posibles de 5 nums de 50 y 2 estrellas de 12
    n_combinaciones = comb(50, 5) * comb(12, 2)
    h_total = log2(n_combinaciones)
    print(f"Combinaciones posibles: {n_combinaciones:,}")
    print(f"Entropia maxima del juego: {h_total:.4f} bits = {h_total/8:.2f} bytes")
    print(f"Sorteos observados: {len(df)}")
    print(f"Ratio cobertura: {len(df)/n_combinaciones*100:.6f}%")

    # Guardar
    output = {
        "metodologia": "Entropia de Shannon e informacion mutua entre numeros y sumas. "
                        "MI(A;B) mide dependencia estadistica.",
        "mi_entre_numeros_top10": df_mi.head(10).to_dict(orient='records'),
        "mi_media_pares": float(mi_media),
        "mi_sumas_consecutivas": mi_sumas,
        "entropia_por_dia": ent_dia,
        "entropia_sistema_completo": {
            "combinaciones_posibles": int(n_combinaciones),
            "bits_max": float(h_total),
        },
    }
    with open('reports/informes/informe_05_entropia_info_mutua.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[OK] Guardado en reports/informes/informe_05_entropia_info_mutua.json")


if __name__ == "__main__":
    main()
