"""Acercamiento 4: Test de aleatoriedad formales.

Aplicamos tests estandar sobre los datos:
1. Test chi² omnibus (Pearson)
2. Kolmogorov-Smirnov contra uniforme
3. Test de Mann-Whitney para comparar mitades
4. Test de series (Bartels)
5. Test de entropia (Shannon)
6. Poker test (combinaciones de 5 numeros como 'mano')

La idea: si los datos son genuinamente aleatorios, TODOS estos
tests deben NO rechazar H0.
"""
import sys
sys.path.insert(0, '.')
import json
import pandas as pd
import numpy as np
from scipy import stats

from src.db.repository import SorteoRepository
from src.analysis.descriptive import to_dataframe


def chi2_omnibus(df: pd.DataFrame, elemento: str = "numero") -> dict:
    """Chi² omnibus: cada elemento vs uniforme."""
    if elemento == "numero":
        flat = pd.Series([x for ns in df["nums"] for x in ns])
        max_e = 50
        per = 5
    else:
        flat = pd.Series([e for es in df["stars"] for e in es])
        max_e = 12
        per = 2
    n = len(df)
    freq = flat.value_counts()
    esp = n * per / max_e
    chi2 = 0
    for i in range(1, max_e + 1):
        obs = freq.get(i, 0)
        chi2 += (obs - esp) ** 2 / esp
    p = 1 - stats.chi2.cdf(chi2, df=max_e - 1)
    return {
        "elemento": elemento,
        "chi2": float(chi2),
        "dof": max_e - 1,
        "p_value": float(p),
        "rechaza_aleatoriedad": p < 0.001,
    }


def ks_test_numeros(df: pd.DataFrame) -> dict:
    """Kolmogorov-Smirnov sobre los numeros vs uniforme [0,1]."""
    nums = []
    for ns in df["nums"]:
        for n in ns:
            # Transformar a [0, 1] asumiendo uniforme [1, 50]
            nums.append((n - 0.5) / 50)
    ks, p = stats.kstest(nums, 'uniform')
    return {
        "test": "KS contra uniforme",
        "ks_stat": float(ks),
        "p_value": float(p),
        "rechaza_aleatoriedad": p < 0.001,
    }


def ks_test_sumas(df: pd.DataFrame) -> dict:
    """KS sobre suma vs distribucion teorica (normal aprox).
    
    Suma de 5 uniformes [1,50] -> media 127.5, varianza 5 * (49^2/12 + ...) ~= 850.
    Aproximamos con normal.
    """
    sumas = df["suma"].values
    mu = sumas.mean()
    sigma = sumas.std()
    ks, p = stats.kstest(sumas, 'norm', args=(mu, sigma))
    return {
        "test": "KS suma vs normal",
        "ks_stat": float(ks),
        "p_value": float(p),
        "rechaza_aleatoriedad": p < 0.001,
    }


def mann_whitney_mitades(df: pd.DataFrame) -> dict:
    """Mann-Whitney U test: la suma de la primera mitad es igual a la segunda?"""
    sumas = df["suma"].values
    mitad = len(sumas) // 2
    u, p = stats.mannwhitneyu(sumas[:mitad], sumas[mitad:], alternative='two-sided')
    return {
        "test": "Mann-Whitney primera mitad vs segunda",
        "u_stat": float(u),
        "p_value": float(p),
        "rechaza_igualdad": p < 0.05,
    }


def bartels_test(df: pd.DataFrame) -> dict:
    """Bartels test de aleatoriedad sobre la suma."""
    s = df["suma"].values
    n = len(s)
    # Bartels: R = sum |x_{i+1} - x_i| / sum (x_i - media)^2
    diffs = np.abs(np.diff(s))
    sum_diffs = diffs.sum()
    desv = s - s.mean()
    sum_sq = (desv**2).sum()
    R = sum_diffs / sum_sq if sum_sq > 0 else 0
    # Bajo H0, R sigue una distribucion especifica
    # Aproximacion: Z = (R - 2) / sqrt(2/n)
    # Real Bartels usa tablas, pero esta aproximacion funciona
    z = (R - 2) * np.sqrt(n / 2)
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return {
        "test": "Bartels (variacion de runs)",
        "R_stat": float(R),
        "z_stat": float(z),
        "p_value": float(p),
        "rechaza_aleatoriedad": p < 0.05,
    }


def poker_test(df: pd.DataFrame) -> dict:
    """Poker test: clasifica cada combinacion de 5 numeros segun repeticiones.

    Categorias (de 5 numeros):
      - Todos distintos (12345): caso comun
      - Un par: 2 numeros iguales + 3 distintos (11234)
      - Dos pares: 2+2+1 (11223)
      - Trio: 3 iguales + 2 distintos (11123)
      - Full: 3+2 (11122)
      - Poker: 4 iguales + 1 distinto (11112)
      - Quintilla: 5 iguales (11111) -- no deberia pasar nunca

    Como los sorteos tienen 5 distintos por diseno, solo la primera
    categoria es valida. Pero podemos contar frecuencias de cada categoria
    entre sorteos.
    """
    categorias = []
    for ns in df["nums"]:
        from collections import Counter
        c = Counter(ns)
        nums_con_repes = sum(1 for v in c.values() if v > 1)
        if nums_con_repes == 0:
            categorias.append("5_distintos")
        elif nums_con_repes == 1:
            categorias.append("un_par")
        else:
            categorias.append("mas_repes")
    conteo = pd.Series(categorias).value_counts().to_dict()
    # H0: siempre debe haber 5_distintos (Euromillones no permite repetidos)
    total = sum(conteo.values())
    return {
        "test": "Poker (verifica no-repetidos)",
        "conteo_categorias": conteo,
        "total_sorteos": total,
        "interpretacion": "Todos los sorteos deben ser 5_distintos por diseno",
    }


def shannon_entropy(df: pd.DataFrame, elemento: str = "numero") -> dict:
    """Entropia de Shannon de la distribucion.
    
    H_max para uniforme sobre 50 elementos = log2(50) ≈ 5.64 bits
    Si la entropia observada es mucho menor, hay redundancia/orden.
    """
    if elemento == "numero":
        flat = pd.Series([x for ns in df["nums"] for x in ns])
        max_e = 50
    else:
        flat = pd.Series([e for es in df["stars"] for e in es])
        max_e = 12
    freq = flat.value_counts(normalize=True)
    # Filtrar ceros
    freq = freq[freq > 0]
    H = -float((freq * np.log2(freq)).sum())
    H_max = np.log2(max_e)
    eficiencia = H / H_max * 100
    return {
        "elemento": elemento,
        "H_observada_bits": H,
        "H_maxima_bits": float(H_max),
        "eficiencia_%": eficiencia,
        "interpretacion": "100% = totalmente aleatorio, <95% = estructura detectable",
    }


def main():
    repo = SorteoRepository('data/euromillones.db')
    sorteos = repo.get_all()
    df = to_dataframe(sorteos)
    print(f"Total sorteos: {len(df)}\n")

    # 1. Chi² omnibus
    print("=" * 70)
    print("TEST CHI² OMNIBUS (uniforme global)")
    print("=" * 70)
    chi_n = chi2_omnibus(df, "numero")
    chi_e = chi2_omnibus(df, "estrella")
    print(f"Numeros: chi²={chi_n['chi2']:.2f}, dof={chi_n['dof']}, "
          f"p={chi_n['p_value']:.4f}, rechaza(p<0.001): {chi_n['rechaza_aleatoriedad']}")
    print(f"Estrellas: chi²={chi_e['chi2']:.2f}, dof={chi_e['dof']}, "
          f"p={chi_e['p_value']:.4f}, rechaza(p<0.001): {chi_e['rechaza_aleatoriedad']}")

    # 2. KS test
    print("\n" + "=" * 70)
    print("KOLMOGOROV-SMIRNOV")
    print("=" * 70)
    ks_n = ks_test_numeros(df)
    print(f"Numeros vs uniforme: KS={ks_n['ks_stat']:.4f}, p={ks_n['p_value']:.4f}, "
          f"rechaza(p<0.001): {ks_n['rechaza_aleatoriedad']}")
    ks_s = ks_test_sumas(df)
    print(f"Sumas vs normal: KS={ks_s['ks_stat']:.4f}, p={ks_s['p_value']:.4f}, "
          f"rechaza(p<0.001): {ks_s['rechaza_aleatoriedad']}")

    # 3. Mann-Whitney
    print("\n" + "=" * 70)
    print("MANN-WHITNEY (primera mitad vs segunda mitad)")
    print("=" * 70)
    mw = mann_whitney_mitades(df)
    print(f"U={mw['u_stat']:.2f}, p={mw['p_value']:.4f}, "
          f"rechaza(p<0.05): {mw['rechaza_igualdad']}")

    # 4. Bartels
    print("\n" + "=" * 70)
    print("BARTELS TEST")
    print("=" * 70)
    bartels = bartels_test(df)
    print(f"R={bartels['R_stat']:.4f}, z={bartels['z_stat']:.2f}, "
          f"p={bartels['p_value']:.4f}, rechaza(p<0.05): {bartels['rechaza_aleatoriedad']}")

    # 5. Poker
    print("\n" + "=" * 70)
    print("POKER TEST")
    print("=" * 70)
    poker = poker_test(df)
    print(f"Categorias: {poker['conteo_categorias']}")

    # 6. Entropia
    print("\n" + "=" * 70)
    print("ENTROPIA DE SHANNON")
    print("=" * 70)
    ent_n = shannon_entropy(df, "numero")
    print(f"Numeros: H={ent_n['H_observada_bits']:.4f} bits / max {ent_n['H_maxima_bits']:.4f} bits = "
          f"{ent_n['eficiencia_%']:.2f}%")
    ent_e = shannon_entropy(df, "estrella")
    print(f"Estrellas: H={ent_e['H_observada_bits']:.4f} bits / max {ent_e['H_maxima_bits']:.4f} bits = "
          f"{ent_e['eficiencia_%']:.2f}%")

    # Resumen: ¿rechazan aleatoriedad?
    print("\n" + "=" * 70)
    print("VEREDICTO GLOBAL DE ALEATORIEDAD")
    print("=" * 70)
    rechazos = sum([
        chi_n['rechaza_aleatoriedad'],
        chi_e['rechaza_aleatoriedad'],
        ks_n['rechaza_aleatoriedad'],
        ks_s['rechaza_aleatoriedad'],
        mw['rechaza_igualdad'],
        bartels['rechaza_aleatoriedad'],
    ])
    total_tests = 6
    print(f"Tests que rechazan H0 (aleatoriedad): {rechazos} / {total_tests}")
    if rechazos == 0:
        print(">>> Los datos son consistentes con aleatoriedad genuina <<<")
    elif rechazos <= 1:
        print(">>> Datos CASI consistentes con aleatoriedad (1 falso positivo posible) <<<")
    else:
        print(">>> Hay evidencia de no-aleatoriedad <<<")

    # Guardar
    output = {
        "metodologia": "6 tests formales de aleatoriedad: chi² omnibus, KS contra uniforme y normal, "
                        "Mann-Whitney primera/segunda mitad, Bartels (variacion de runs), "
                        "Poker test (verifica no-repetidos), Entropia de Shannon.",
        "chi2_omnibus": {"numeros": chi_n, "estrellas": chi_e},
        "ks_test": ks_n,
        "ks_sumas": ks_s,
        "mann_whitney": mw,
        "bartels": bartels,
        "poker": poker,
        "shannon": {"numeros": ent_n, "estrellas": ent_e},
        "veredicto": {
            "tests_rechazan": rechazos,
            "total_tests": total_tests,
            "consistente_con_azar": rechazos == 0,
        },
    }
    with open('reports/informes/informe_04_aleatoriedad.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[OK] Guardado en reports/informes/informe_04_aleatoriedad.json")


if __name__ == "__main__":
    main()
