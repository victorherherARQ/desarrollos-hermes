"""Funciones estadisticas: correcciones por multiples tests."""
from statsmodels.stats.multitest import multipletests


def bonferroni(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Aplica correccion de Bonferroni a una lista de p-values."""
    if not p_values:
        return []
    _, p_corrected, _, _ = multipletests(p_values, alpha=alpha, method='bonferroni')
    return [p < alpha for p in p_corrected]


def fdr_bh(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Aplica FDR de Benjamini-Hochberg."""
    if not p_values:
        return []
    _, p_corrected, _, _ = multipletests(p_values, alpha=alpha, method='fdr_bh')
    return [p < alpha for p in p_corrected]


def holm(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Aplica metodo de Holm (mas potente que Bonferroni)."""
    if not p_values:
        return []
    _, p_corrected, _, _ = multipletests(p_values, alpha=alpha, method='holm')
    return [p < alpha for p in p_corrected]
