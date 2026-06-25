"""Ejecuta el analisis descriptivo del notebook 01.
Se ejecuta desde la raiz del proyecto: PYTHONPATH=. python3 run_phase3.py
"""
import sys
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from src.db.repository import SorteoRepository
from src.analysis.descriptive import (
    to_dataframe, freq_numeros, freq_estrellas,
    test_chi_cuadrado_numeros, test_chi_cuadrado_estrellas,
    distribucion_paridad, distribucion_altos_bajos, distribucion_consecutivos,
    estadisticas_suma,
)
from src.viz.heatmaps import heatmap_frecuencias_numeros, heatmap_frecuencias_estrellas


def main():
    print("=" * 60)
    print("FASE 3: ANALISIS DESCRIPTIVO")
    print("=" * 60)

    repo = SorteoRepository('data/euromillones.db')
    sorteos = repo.get_all()
    df = to_dataframe(sorteos)
    print(f"\nTotal sorteos: {len(df)}")
    print(f"Rango fechas: {df['fecha'].min()} -> {df['fecha'].max()}")

    print("\n--- ESTADISTICAS SUMA ---")
    stats_suma = estadisticas_suma(df)
    for k, v in stats_suma.items():
        print(f"  {k}: {v}")

    chi_n = test_chi_cuadrado_numeros(df)
    print("\n--- CHI² TOP 15 NUMEROS ---")
    top_chi = chi_n.sort_values('chi2', ascending=False).head(15)
    print(top_chi.to_string(index=False))

    chi_e = test_chi_cuadrado_estrellas(df)
    print("\n--- CHI² ESTRELLAS ---")
    print(chi_e.to_string(index=False))

    print("\n--- PARIDAD ---")
    print(distribucion_paridad(df).to_string(index=False))
    print("\n--- ALTOS/BAJOS ---")
    print(distribucion_altos_bajos(df).to_string(index=False))
    print("\n--- CONSECUTIVOS ---")
    print(distribucion_consecutivos(df).to_string(index=False))

    print("\nGenerando graficos...")
    os.makedirs('reports/graficos', exist_ok=True)

    fig, ax = plt.subplots(figsize=(14, 4))
    freq_n = freq_numeros(df)
    heatmap_frecuencias_numeros(freq_n.to_dict(), ax=ax,
                                  titulo="Frecuencia numeros (1-50)")
    plt.tight_layout()
    plt.savefig('reports/graficos/01_heatmap_numeros.png', dpi=80, bbox_inches='tight')
    plt.close()

    fig, ax = plt.subplots(figsize=(10, 4))
    freq_e = freq_estrellas(df)
    heatmap_frecuencias_estrellas(freq_e.to_dict(), ax=ax,
                                    titulo="Frecuencia estrellas (1-12)")
    plt.tight_layout()
    plt.savefig('reports/graficos/02_heatmap_estrellas.png', dpi=80, bbox_inches='tight')
    plt.close()

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    ax = axes[0]
    colors = ['red' if p < 0.05 else 'gray' for p in chi_n['p_value']]
    ax.bar(chi_n['numero'], chi_n['desviacion_%'], color=colors)
    ax.axhline(0, color='black', linewidth=0.5)
    ax.set_xlabel('Numero'); ax.set_ylabel('Desviacion (%)')
    ax.set_title('Desviacion por numero (rojo = p<0.05)'); ax.grid(True, alpha=0.3)
    ax = axes[1]
    colors = ['red' if p < 0.05 else 'gray' for p in chi_e['p_value']]
    ax.bar(chi_e['estrella'], chi_e['desviacion_%'], color=colors)
    ax.axhline(0, color='black', linewidth=0.5)
    ax.set_xlabel('Estrella'); ax.set_ylabel('Desviacion (%)')
    ax.set_title('Desviacion por estrella (rojo = p<0.05)'); ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('reports/graficos/03_desviaciones.png', dpi=80, bbox_inches='tight')
    plt.close()

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    dp = distribucion_paridad(df)
    axes[0,0].bar(dp['pares'], dp['count'], color='steelblue')
    axes[0,0].set_xlabel('Numero de pares'); axes[0,0].set_ylabel('Cantidad')
    axes[0,0].set_title('Distribucion de paridad'); axes[0,0].grid(True, alpha=0.3)
    da = distribucion_altos_bajos(df)
    axes[0,1].bar(da['altos'], da['count'], color='darkorange')
    axes[0,1].set_xlabel('Numero de altos (>25)'); axes[0,1].set_ylabel('Cantidad')
    axes[0,1].set_title('Distribucion altos/bajos'); axes[0,1].grid(True, alpha=0.3)
    dc = distribucion_consecutivos(df)
    axes[1,0].bar(dc['consecutivos'], dc['count'], color='green')
    axes[1,0].set_xlabel('Pares consecutivos'); axes[1,0].set_ylabel('Cantidad')
    axes[1,0].set_title('Consecutivos por sorteo'); axes[1,0].grid(True, alpha=0.3)
    axes[1,1].hist(df['suma'], bins=40, color='purple', alpha=0.7, edgecolor='black')
    axes[1,1].axvline(127.5, color='red', linestyle='--', label='Media teorica (127.5)')
    axes[1,1].set_xlabel('Suma de los 5 numeros'); axes[1,1].set_ylabel('Cantidad')
    axes[1,1].set_title('Distribucion de la suma'); axes[1,1].legend()
    axes[1,1].grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('reports/graficos/04_distribuciones.png', dpi=80, bbox_inches='tight')
    plt.close()

    print(f"\n[OK] 4 graficos en reports/graficos/")
    for f in sorted(os.listdir('reports/graficos')):
        size = os.path.getsize(f'reports/graficos/{f}')
        print(f"  {f}: {size/1024:.1f} KB")


if __name__ == "__main__":
    main()
