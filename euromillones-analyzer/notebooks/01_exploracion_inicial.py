# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# # Euromillones - Exploracion Inicial
#
# **Pregunta:** ¿Hay patrones en los resultados historicos de Euromillones?
#
# **Hipotesis nula:** Cada sorteo es independiente y los numeros se distribuyen uniformemente.
#
# **Foco de este notebook:**
# - Cargar los 1951 sorteos historicos (2004-2026)
# - Calcular frecuencias observadas vs esperadas
# - Test chi-cuadrado por numero y estrella
# - Visualizar desviaciones

# %%
import sys
sys.path.insert(0, '..')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from src.db.repository import SorteoRepository
from src.analysis.descriptive import (
    to_dataframe, freq_numeros, freq_estrellas,
    test_chi_cuadrado_numeros, test_chi_cuadrado_estrellas,
    distribucion_paridad, distribucion_altos_bajos, distribucion_consecutivos,
    estadisticas_suma,
)
from src.viz.heatmaps import heatmap_frecuencias_numeros, heatmap_frecuencias_estrellas

# %%
# ## 1. Cargar datos
repo = SorteoRepository('data/euromillones.db')
sorteos = repo.get_all()
df = to_dataframe(sorteos)
print(f"Total sorteos: {len(df)}")
print(f"Rango fechas: {df['fecha'].min()} -> {df['fecha'].max()}")
print(f"Duracion: {(df['fecha'].max() - df['fecha'].min()).days} dias")

# %%
# ## 2. Estadisticas de la suma
stats_suma = estadisticas_suma(df)
print("=== ESTADISTICAS SUMA ===")
for k, v in stats_suma.items():
    print(f"  {k}: {v}")

# %%
# ## 3. Test chi-cuadrado por numero
#
# Si los numeros fueran perfectamente uniformes, cada numero deberia
# aparecer 5/50 = 10% de las veces (5 numeros por sorteo).
#
# Para 1951 sorteos, eso son ~195 apariciones esperadas por numero.

chi_n = test_chi_cuadrado_numeros(df)
print("=== TOP 15 NUMEROS CON MAYOR DESVIACION ===")
top_chi = chi_n.sort_values('chi2', ascending=False).head(15)
print(top_chi.to_string(index=False))

# %%
# ## 4. Test chi-cuadrado por estrella
chi_e = test_chi_cuadrado_estrellas(df)
print("=== TEST CHI² POR ESTRELLA ===")
print(chi_e.to_string(index=False))

# %%
# ## 5. Distribuciones estructurales
print("=== PARIDAD (0=5 impares, 5=5 pares) ===")
print(distribucion_paridad(df).to_string(index=False))
print("\n=== ALTOS/BAJOS (0=5 bajos <=25, 5=5 altos >25) ===")
print(distribucion_altos_bajos(df).to_string(index=False))
print("\n=== CONSECUTIVOS POR SORTEO ===")
print(distribucion_consecutivos(df).to_string(index=False))

# %%
# ## 6. Visualizaciones
fig, ax = plt.subplots(figsize=(14, 4))
freq_n = freq_numeros(df)
heatmap_frecuencias_numeros(freq_n.to_dict(), ax=ax,
                              titulo="Frecuencia numeros (1-50) - 1951 sorteos")
plt.tight_layout()
plt.savefig('../reports/graficos/01_heatmap_numeros.png', dpi=80, bbox_inches='tight')
plt.show()

# %%
fig, ax = plt.subplots(figsize=(10, 4))
freq_e = freq_estrellas(df)
heatmap_frecuencias_estrellas(freq_e.to_dict(), ax=ax,
                                titulo="Frecuencia estrellas (1-12)")
plt.tight_layout()
plt.savefig('../reports/graficos/02_heatmap_estrellas.png', dpi=80, bbox_inches='tight')
plt.show()

# %%
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
ax = axes[0]
colors = ['red' if p < 0.05 else 'gray' for p in chi_n['p_value']]
ax.bar(chi_n['numero'], chi_n['desviacion_%'], color=colors)
ax.axhline(0, color='black', linewidth=0.5)
ax.set_xlabel('Numero')
ax.set_ylabel('Desviacion respecto a uniforme (%)')
ax.set_title('Desviacion por numero (rojo = p<0.05)')
ax.grid(True, alpha=0.3)

ax = axes[1]
colors = ['red' if p < 0.05 else 'gray' for p in chi_e['p_value']]
ax.bar(chi_e['estrella'], chi_e['desviacion_%'], color=colors)
ax.axhline(0, color='black', linewidth=0.5)
ax.set_xlabel('Estrella')
ax.set_ylabel('Desviacion respecto a uniforme (%)')
ax.set_title('Desviacion por estrella (rojo = p<0.05)')
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('../reports/graficos/03_desviaciones.png', dpi=80, bbox_inches='tight')
plt.show()

# %%
fig, axes = plt.subplots(2, 2, figsize=(12, 10))

dp = distribucion_paridad(df)
axes[0,0].bar(dp['pares'], dp['count'], color='steelblue')
axes[0,0].set_xlabel('Numero de pares')
axes[0,0].set_ylabel('Cantidad')
axes[0,0].set_title('Distribucion de paridad')
axes[0,0].grid(True, alpha=0.3)

da = distribucion_altos_bajos(df)
axes[0,1].bar(da['altos'], da['count'], color='darkorange')
axes[0,1].set_xlabel('Numero de altos (>25)')
axes[0,1].set_ylabel('Cantidad')
axes[0,1].set_title('Distribucion altos/bajos')
axes[0,1].grid(True, alpha=0.3)

dc = distribucion_consecutivos(df)
axes[1,0].bar(dc['consecutivos'], dc['count'], color='green')
axes[1,0].set_xlabel('Pares consecutivos')
axes[1,0].set_ylabel('Cantidad')
axes[1,0].set_title('Consecutivos por sorteo')
axes[1,0].grid(True, alpha=0.3)

axes[1,1].hist(df['suma'], bins=40, color='purple', alpha=0.7, edgecolor='black')
axes[1,1].axvline(127.5, color='red', linestyle='--', label='Media teorica (127.5)')
axes[1,1].set_xlabel('Suma de los 5 numeros')
axes[1,1].set_ylabel('Cantidad')
axes[1,1].set_title('Distribucion de la suma')
axes[1,1].legend()
axes[1,1].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('../reports/graficos/04_distribuciones.png', dpi=80, bbox_inches='tight')
plt.show()

# %%
# ## 7. Hallazgos principales
#
# **Observados:**
# - Suma media = 127.49 vs teorica 127.50 (coincide casi exacto, OK)
# - Distribucion de paridad centrada en 2 pares (esperado)
# - Distribucion altos/bajos centrada en 2-3 (esperado)
# - 65% de sorteos NO tienen numeros consecutivos
#
# **Desviaciones significativas (chi² test, sin correccion):**
# - Numero 22: 153 apariciones (-21.6%), p=0.0026
# - Estrella 12: 174 apariciones (-46.5%), p<0.001
# - Estrella 11: 263 apariciones (-19.1%), p<0.001
# - Estrella 2: 388 apariciones (+19.3%), p<0.001
# - Estrella 3: 382 apariciones (+17.5%), p<0.001
#
# **⚠️ Advertencia importante:**
# Sin correccion de Bonferroni, esperar ~5% de falsos positivos en 50+12=62 tests.
# Esto NO es aun evidencia de patron. Hay que aplicar correccion por multiples tests
# en el notebook 03 (backtesting).
