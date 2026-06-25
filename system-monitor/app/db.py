"""
SQLite storage for system metrics.
Schema:
- samples: timestamp + cpu + ram + swap + disk + load + temps + network counters
- containers: timestamp + container stats from docker
"""
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

DB_PATH = Path("/data/system.db")


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS samples (
            ts INTEGER PRIMARY KEY,
            cpu_percent REAL,
            cpu_freq_mhz REAL,
            cpu_count INTEGER,
            ram_used_gb REAL,
            ram_total_gb REAL,
            ram_percent REAL,
            swap_used_gb REAL,
            swap_percent REAL,
            disk_used_gb REAL,
            disk_total_gb REAL,
            disk_percent REAL,
            load1 REAL,
            load5 REAL,
            load15 REAL,
            temp_cpu_c REAL,
            net_rx_mb REAL,
            net_tx_mb REAL
        );
        CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts);

        CREATE TABLE IF NOT EXISTS containers (
            ts INTEGER,
            name TEXT,
            cpu_pct REAL,
            ram_mb REAL,
            PRIMARY KEY (ts, name)
        );
        CREATE INDEX IF NOT EXISTS idx_containers_ts ON containers(ts);
        """)


def insert_sample(metrics: dict):
    with db() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO samples
        (ts, cpu_percent, cpu_freq_mhz, cpu_count,
         ram_used_gb, ram_total_gb, ram_percent,
         swap_used_gb, swap_percent,
         disk_used_gb, disk_total_gb, disk_percent,
         load1, load5, load15, temp_cpu_c,
         net_rx_mb, net_tx_mb)
        VALUES (:ts, :cpu_percent, :cpu_freq_mhz, :cpu_count,
                :ram_used_gb, :ram_total_gb, :ram_percent,
                :swap_used_gb, :swap_percent,
                :disk_used_gb, :disk_total_gb, :disk_percent,
                :load1, :load5, :load15, :temp_cpu_c,
                :net_rx_mb, :net_tx_mb)
        """, {**metrics, "ts": int(time.time())})


def insert_containers(samples: Iterable[dict]):
    ts = int(time.time())
    with db() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO containers (ts, name, cpu_pct, ram_mb) VALUES (?,?,?,?)",
            [(ts, s["name"], s["cpu_pct"], s["ram_mb"]) for s in samples]
        )


def latest_sample():
    with db() as conn:
        cur = conn.execute("SELECT * FROM samples ORDER BY ts DESC LIMIT 1")
        return cur.fetchone()


def samples_since(seconds: int):
    with db() as conn:
        cur = conn.execute(
            "SELECT * FROM samples WHERE ts >= ? ORDER BY ts ASC",
            (int(time.time()) - seconds,)
        )
        return cur.fetchall()


def latest_containers():
    with db() as conn:
        cur = conn.execute("""
        SELECT c.* FROM containers c
        JOIN (SELECT name, MAX(ts) AS mx FROM containers GROUP BY name) latest
          ON c.name = latest.name AND c.ts = latest.mx
        ORDER BY c.ram_mb DESC
        """)
        return cur.fetchall()


def prune(retention_days: int):
    cutoff = int(time.time()) - retention_days * 86400
    with db() as conn:
        conn.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
        conn.execute("DELETE FROM containers WHERE ts < ?", (cutoff,))
