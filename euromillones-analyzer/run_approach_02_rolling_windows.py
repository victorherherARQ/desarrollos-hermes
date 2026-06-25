"""Acercamiento 2: Ventanas moviles (rolling window).

Para cada ventana de N sorteos consecutivos, calcula la frecuencia
de cada elemento. Asi detectamos:
- Si hay regimenes cambiantes
- Si los 'calientes' se mantienen o rotan
- Donde ocurren los cambios estructurales

Estrategia:
- Window size: 200 sorteos (~2 anios)
- Step: 50 sorteos (~6 meses)
- Para cada ventana: chi² por elemento, buscar si hay cambios
"""
import sys
sys.path.insert(0, '.')
import json
import pandas as pd
import numpy as np
from scipy import stats

from src.db.repository import SorteoRepository
from src.analysis.descriptive import to_dataframe


WINDOW = 200
STEP = 50


def chi2_en_ventana(df_win: pd.DataFrame, elemento: str = "numero") -> dict:
    """Chi² para una ventana."""
    n = len(df_win)
    if n < WINDOW:
        return None
    if elemento == "numero":
        flat = pd.Series([x for ns in df_win["nums"] for x in ns])
        max_e = 50
        per = 5
    else:
        flat = pd.Series([e for es in df_win["stars"] for e in es])
        max_e = 12
        per = 2
    freq = flat.value_counts()
    esp = n * per / max_e
    max_dev = 0
    max_dev_elem = None
    max_dev_chi2 = 0
    for i in range(1, max_e + 1):
        obs = freq.get(i, 0)
        dev = (obs - esp) / esp * 100 if esp > 0 else 0
        chi2 = (obs - esp) ** 2 / esp if esp > 0 else 0
        if abs(dev) > abs(max_dev):
            max_dev = dev
            max_dev_elem = i
            max_dev_chi2 = chi2
    return {
        "max_desviacion_%": max_dev,
        "max_desv_elemento": max_dev_elem,
        "max_chi2": max_dev_chi2,
    }


def main():
    repo = SorteoRepository('data/euromillones.db')
    sorteos = repo.get_all()
    df = to_dataframe(sorteos).reset_index(drop=True)
    print(f"Total sorteos: {len(df)}")
    print(f"Ventana: {WINDOW} sorteos, step: {STEP}")
    print()

    # Calcular ventanas
    ventanas = []
    for start in range(0, len(df) - WINDOW + 1, STEP):
        end = start + WINDOW
        df_win = df.iloc[start:end]
        ventana_info = {
            "indice_inicio": start,
            "indice_fin": end - 1,
            "fecha_inicio": df_win["fecha"].iloc[0].date().isoformat(),
            "fecha_fin": df_win["fecha"].iloc[-1].date().isoformat(),
            "n_sorteos": len(df_win),
        }
        ch_n = chi2_en_ventana(df_win, "numero")
        ch_e = chi2_en_ventana(df_win, "estrella")
        if ch_n:
            ventana_info.update({
                "num_max_desv_%": ch_n["max_desviacion_%"],
                "num_max_desv_elem": ch_n["max_desv_elemento"],
                "num_max_chi2": ch_n["max_chi2"],
            })
        if ch_e:
            ventana_info.update({
                "star_max_desv_%": ch_e["max_desviacion_%"],
                "star_max_desv_elem": ch_e["max_desv_elemento"],
                "star_max_chi2": ch_e["max_chi2"],
            })
        ventanas.append(ventana_info)

    df_vent = pd.DataFrame(ventanas)
    print(f"Total ventanas analizadas: {len(df_vent)}")
    print()
    print("=== VENTANAS CON MAYOR DESVIACION EN NUMEROS ===")
    top_n = df_vent.nlargest(5, "num_max_chi2")
    print(top_n[["fecha_inicio", "fecha_fin", "num_max_desv_elem",
                  "num_max_desv_%", "num_max_chi2"]].to_string(index=False))
    print()
    print("=== VENTANAS CON MAYOR DESVIACION EN ESTRELLAS ===")
    top_e = df_vent.nlargest(5, "star_max_chi2")
    print(top_e[["fecha_inicio", "fecha_fin", "star_max_desv_elem",
                  "star_max_desv_%", "star_max_chi2"]].to_string(index=False))

    # Test de cambio estructural (CUSUM simplificado):
    # ¿La suma media cambia a lo largo del tiempo?
    print("\n" + "=" * 70)
    print("EVOLUCION DE LA SUMA MEDIA POR VENTANA")
    print("=" * 70)
    sumas = []
    for start in range(0, len(df) - WINDOW + 1, STEP):
        end = start + WINDOW
        sumas.append({
            "fecha": df.iloc[start]["fecha"].date().isoformat(),
            "suma_media": float(df.iloc[start:end]["suma"].mean()),
            "suma_std": float(df.iloc[start:end]["suma"].std()),
        })
    df_sumas = pd.DataFrame(sumas)
    print(f"Suma media global: {df['suma'].mean():.2f}")
    print(f"Rango de sumas medias por ventana: {df_sumas['suma_media'].min():.2f} - {df_sumas['suma_media'].max():.2f}")
    print(f"Desviacion estandar entre ventanas: {df_sumas['suma_media'].std():.2f}")

    # Test estadistico: la suma media cambia entre la primera mitad y la segunda mitad?
    mitad = len(sumas) // 2
    primera = [s["suma_media"] for s in sumas[:mitad]]
    segunda = [s["suma_media"] for s in sumas[mitad:]]
    t, p = stats.ttest_ind(primera, segunda)
    print(f"\nT-test primera mitad vs segunda mitad: t={t:.3f}, p={p:.4f}")
    print(f"Diferencia significativa: {p < 0.05}")

    # Guardar
    output = {
        "metodologia": f"Ventanas moviles de {WINDOW} sorteos con step {STEP}. "
                        "Para cada ventana: max desviacion chi² por numero y estrella. "
                        "Ademas: evolucion de suma media y t-test primera vs segunda mitad.",
        "n_ventanas": len(ventanas),
        "ventanas_top_numeros": top_n.to_dict(orient='records'),
        "ventanas_top_estrellas": top_e.to_dict(orient='records'),
        "suma_media_global": float(df["suma"].mean()),
        "rango_sumas_ventanas": [float(df_sumas["suma_media"].min()), float(df_sumas["suma_media"].max())],
        "t_test_primera_vs_segunda_mitad": {
            "t_stat": float(t),
            "p_value": float(p),
            "significativo": p < 0.05,
        },
    }
    with open('reports/informes/informe_02_ventanas_moviles.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[OK] Guardado en reports/informes/informe_02_ventanas_moviles.json")


if __name__ == "__main__":
    main()
