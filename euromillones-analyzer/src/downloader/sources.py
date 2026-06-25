"""Validador de sorteos de Euromillones."""
from datetime import date


class ValidationError(ValueError):
    pass


def validar_sorteo(
    fecha,
    n1: int, n2: int, n3: int, n4: int, n5: int,
    e1: int, e2: int,
    numero_min: int = 1, numero_max: int = 50,
    estrella_min: int = 1, estrella_max: int = 12,
) -> dict:
    """Valida un sorteo. Devuelve dict normalizado o lanza ValidationError."""
    nums = [n1, n2, n3, n4, n5]
    estrellas = [e1, e2]

    # Tipos
    for n in nums:
        if not isinstance(n, int):
            raise ValidationError(f"Numero no es int: {n!r}")
    for e in estrellas:
        if not isinstance(e, int):
            raise ValidationError(f"Estrella no es int: {e!r}")

    # Fechas
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha)
    if not isinstance(fecha, date):
        raise ValidationError(f"Fecha invalida: {fecha!r}")
    if fecha < date(2004, 2, 13):
        raise ValidationError(f"Fecha anterior al inicio del juego: {fecha}")
    if fecha > date.today():
        raise ValidationError(f"Fecha futura: {fecha}")

    # Rangos
    for n in nums:
        if not (numero_min <= n <= numero_max):
            raise ValidationError(
                f"Numero fuera de rango [{numero_min}, {numero_max}]: {n}"
            )
    for e in estrellas:
        if not (estrella_min <= e <= estrella_max):
            raise ValidationError(
                f"Estrella fuera de rango [{estrella_min}, {estrella_max}]: {e}"
            )

    # Sin repetidos en numeros
    if len(set(nums)) != 5:
        raise ValidationError(f"Numeros repetidos en sorteo: {nums}")

    # Sin repetidos en estrellas
    if len(set(estrellas)) != 2:
        raise ValidationError(f"Estrellas repetidas: {estrellas}")

    nums_sorted = sorted(nums)
    estrellas_sorted = sorted(estrellas)
    return {
        "fecha": fecha.isoformat(),
        "n1": nums_sorted[0], "n2": nums_sorted[1], "n3": nums_sorted[2],
        "n4": nums_sorted[3], "n5": nums_sorted[4],
        "e1": estrellas_sorted[0], "e2": estrellas_sorted[1],
    }
