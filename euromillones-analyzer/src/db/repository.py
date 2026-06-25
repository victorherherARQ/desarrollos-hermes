"""Repository SQLite para sorteos de Euromillones."""
import sqlite3
from pathlib import Path
from datetime import date, datetime
from typing import Optional
import yaml


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


class SorteoRepository:
    """Acceso a la DB de sorteos."""

    def __init__(self, db_path: str = "data/euromillones.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path) as f:
            schema = f.read()
        with self._connect() as conn:
            conn.executescript(schema)

    def insert_sorteo(
        self,
        fecha: date,
        n1: int, n2: int, n3: int, n4: int, n5: int,
        e1: int, e2: int,
        fuente: str = "github:daowa89",
    ) -> Optional[int]:
        """Inserta un sorteo. Si la fecha ya existe, no hace nada."""
        nums = sorted([n1, n2, n3, n4, n5])
        n1, n2, n3, n4, n5 = nums
        estrellas = sorted([e1, e2])
        e1, e2 = estrellas
        suma = n1 + n2 + n3 + n4 + n5
        dia_semana = ["lunes", "martes", "miercoles", "jueves",
                       "viernes", "sabado", "domingo"][fecha.weekday()]

        with self._connect() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO sorteos
                (fecha, dia_semana, n1, n2, n3, n4, n5, e1, e2, suma, fuente)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (fecha.isoformat(), dia_semana,
                 n1, n2, n3, n4, n5, e1, e2, suma, fuente)
            )
            if cur.lastrowid == 0 and cur.rowcount == 0:
                return None
            return cur.lastrowid

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM sorteos").fetchone()[0]

    def get_all(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM sorteos ORDER BY fecha").fetchall()
            return [dict(r) for r in rows]

    def get_date_range(self) -> tuple[Optional[date], Optional[date]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MIN(fecha) AS mn, MAX(fecha) AS mx FROM sorteos"
            ).fetchone()
            mn = date.fromisoformat(row["mn"]) if row["mn"] else None
            mx = date.fromisoformat(row["mx"]) if row["mx"] else None
            return mn, mx

    def get_train_test_split(self, train_until_year: int):
        """Devuelve (train, test) spliteados por año."""
        all_data = self.get_all()
        train = [r for r in all_data if int(r["fecha"][:4]) < train_until_year]
        test = [r for r in all_data if int(r["fecha"][:4]) >= train_until_year]
        return train, test

    def get_freq_numeros(self) -> dict[int, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM v_freq_numeros").fetchall()
            return {r["num"]: r["frecuencia"] for r in rows}

    def get_freq_estrellas(self) -> dict[int, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM v_freq_estrellas").fetchall()
            return {r["num"]: r["frecuencia"] for r in rows}

    def get_last_n_sorteos(self, n: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sorteos ORDER BY fecha DESC LIMIT ?", (n,)
            ).fetchall()
            return [dict(r) for r in rows]
