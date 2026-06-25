"""Heatmaps de frecuencia."""
import matplotlib.pyplot as plt
import numpy as np


def heatmap_frecuencias_numeros(freq: dict, ax=None, titulo: str = ""):
    """Heatmap 5x10 de numeros 1-50."""
    grid = np.zeros((5, 10))
    for n in range(1, 51):
        row = (n - 1) // 10
        col = (n - 1) % 10
        grid[row, col] = freq.get(n, 0)

    if ax is None:
        fig, ax = plt.subplots(figsize=(12, 3))

    im = ax.imshow(grid, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(10))
    ax.set_yticks(range(5))
    ax.set_xticklabels([str(c * 10 + 1) for c in range(10)])
    ax.set_yticklabels([str(r * 10 + 1) for r in range(5)])
    ax.set_title(titulo)

    for r in range(5):
        for c in range(10):
            num = r * 10 + c + 1
            ax.text(c, r, f"{num}\n{int(grid[r,c])}", ha="center", va="center", fontsize=8)

    plt.colorbar(im, ax=ax, label="Frecuencia")
    return ax


def heatmap_frecuencias_estrellas(freq: dict, ax=None, titulo: str = ""):
    """Heatmap 2x6 de estrellas 1-12."""
    grid = np.zeros((2, 6))
    for n in range(1, 13):
        row = (n - 1) // 6
        col = (n - 1) % 6
        grid[row, col] = freq.get(n, 0)

    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 3))

    im = ax.imshow(grid, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(6))
    ax.set_yticks(range(2))
    ax.set_xticklabels([str(c * 6 + 1) for c in range(6)])
    ax.set_yticklabels(["1-6", "7-12"])
    ax.set_title(titulo)

    for r in range(2):
        for c in range(6):
            num = r * 6 + c + 1
            ax.text(c, r, f"{num}\n{int(grid[r,c])}", ha="center", va="center", fontsize=10)

    plt.colorbar(im, ax=ax, label="Frecuencia")
    return ax
