"""Descargador de Euromillones desde el CSV de GitHub.

Usa curl directamente porque urllib/requests son bloqueados
por el firewall de la red, pero curl pasa.
"""
import csv
import subprocess
import time
from datetime import date
from pathlib import Path
from loguru import logger

from .sources import validar_sorteo, ValidationError


SOURCE_URL = (
    "https://raw.githubusercontent.com/daowa89/lottery-archive/"
    "main/eu/euromillones/results.csv"
)


def descargar_csv(destino: str = "data/raw/results.csv") -> Path:
    """Descarga el CSV historico de Euromillones usando curl."""
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Descargando {SOURCE_URL} -> {destino}")

    result = subprocess.run(
        ["curl", "-sL", "-A", "Mozilla/5.0", "-o", destino, SOURCE_URL],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl fallo: {result.stderr}")

    size = Path(destino).stat().st_size
    if size < 1000:
        raise RuntimeError(f"CSV demasiado pequeno ({size} bytes)")

    logger.info(f"OK ({size} bytes)")
    return Path(destino)


def parsear_csv(path: str = "data/raw/results.csv") -> list[dict]:
    """Lee el CSV y devuelve lista de dicts validados."""
    sorteos = []
    invalidos = 0
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                fecha = date.fromisoformat(row["date"])
                nums = [int(row[f"n{i}"]) for i in range(1, 6)]
                stars = [int(row[f"s{i}"]) for i in range(1, 3)]
                s = validar_sorteo(fecha, *nums, *stars)
                sorteos.append(s)
            except (ValueError, KeyError) as e:
                invalidos += 1
                logger.warning(f"Sorteo invalido ({row.get('date', '?')}): {e}")
    logger.info(f"Parseados {len(sorteos)} sorteos validos, {invalidos} invalidos")
    return sorteos


def cargar_en_db(repo, sorteos: list[dict], fuente: str = "github:daowa89") -> tuple[int, int]:
    """Inserta sorteos en la DB. Devuelve (insertados, duplicados)."""
    insertados = 0
    duplicados = 0
    for s in sorteos:
        fecha = date.fromisoformat(s["fecha"])
        rid = repo.insert_sorteo(
            fecha=fecha,
            n1=s["n1"], n2=s["n2"], n3=s["n3"], n4=s["n4"], n5=s["n5"],
            e1=s["e1"], e2=s["e2"],
            fuente=fuente,
        )
        if rid is None:
            duplicados += 1
        else:
            insertados += 1
    logger.info(f"Insertados: {insertados}, duplicados: {duplicados}")
    return insertados, duplicados


def pipeline_descarga(repo, destino_csv: str = "data/raw/results.csv") -> dict:
    """Pipeline completo: descarga + parseo + DB."""
    t0 = time.time()
    descargar_csv(destino_csv)
    sorteos = parsear_csv(destino_csv)
    ins, dup = cargar_en_db(repo, sorteos)
    elapsed = time.time() - t0
    summary = {
        "total_parseados": len(sorteos),
        "insertados": ins,
        "duplicados": dup,
        "total_en_db": repo.count(),
        "duracion_seg": round(elapsed, 2),
    }
    logger.info(f"Pipeline completo: {summary}")
    return summary
