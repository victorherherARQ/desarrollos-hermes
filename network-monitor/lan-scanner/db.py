"""
LAN Scanner — componente "Fing" del stack.
Descubre dispositivos en la LAN vía ARP, hace nmap para hostname/vendor,
speedtest para medir up/down, expone API REST y UI web.
"""
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

DB_PATH = Path(os.environ.get("DB_PATH", "/app/data/scanner.db"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("lan-scanner")


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Crea las tablas si no existen."""
    with get_conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                mac TEXT PRIMARY KEY,
                ip TEXT,
                hostname TEXT,
                vendor TEXT,
                first_seen DATETIME NOT NULL,
                last_seen DATETIME NOT NULL,
                last_changed_ip DATETIME,
                is_online INTEGER NOT NULL DEFAULT 0,
                times_seen INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_devices_last_seen ON devices(last_seen);
            CREATE INDEX IF NOT EXISTS idx_devices_ip ON devices(ip);

            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at DATETIME NOT NULL,
                finished_at DATETIME,
                devices_found INTEGER NOT NULL DEFAULT 0,
                new_devices INTEGER NOT NULL DEFAULT 0,
                scan_type TEXT NOT NULL  -- 'arp' | 'nmap' | 'speedtest'
            );

            CREATE TABLE IF NOT EXISTS speedtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                download_bps REAL NOT NULL,
                upload_bps REAL NOT NULL,
                ping_ms REAL NOT NULL,
                server TEXT,
                isp TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_speedtest_timestamp
                ON speedtest_results(timestamp);
        """)
    log.info("DB inicializada en %s", DB_PATH)


def upsert_device(mac: str, ip: str, hostname: str = None,
                  vendor: str = None) -> tuple[bool, bool]:
    """
    Inserta o actualiza un dispositivo.
    Devuelve (es_nuevo, ip_cambio).
    """
    now = datetime.utcnow().isoformat(timespec="seconds")
    is_new = False
    ip_changed = False
    with get_conn() as c:
        row = c.execute(
            "SELECT ip, is_online FROM devices WHERE mac=?", (mac,)
        ).fetchone()
        if row is None:
            c.execute(
                """INSERT INTO devices
                   (mac, ip, hostname, vendor, first_seen, last_seen,
                    last_changed_ip, is_online, times_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1)""",
                (mac, ip, hostname, vendor, now, now, now if ip else None),
            )
            is_new = True
            log.info("NUEVO dispositivo: %s (%s) vendor=%s", mac, ip, vendor)
        else:
            updates = {"last_seen": now, "is_online": 1, "times_seen": row["times_seen"] + 1}
            if ip and row["ip"] != ip:
                updates["ip"] = ip
                updates["last_changed_ip"] = now
                ip_changed = True
            if hostname and not row["hostname"]:
                updates["hostname"] = hostname
            if vendor and not row["vendor"]:
                updates["vendor"] = vendor
            set_clause = ", ".join(f"{k}=?" for k in updates)
            c.execute(
                f"UPDATE devices SET {set_clause} WHERE mac=?",
                (*updates.values(), mac),
            )
    return is_new, ip_changed


def mark_offline_older_than(minutes: int = 10) -> int:
    """Marca como offline los que no se han visto en X minutos."""
    cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    with get_conn() as c:
        cur = c.execute(
            "UPDATE devices SET is_online=0 WHERE last_seen < ? AND is_online=1",
            (cutoff,),
        )
        return cur.rowcount


def get_all_devices(only_online: bool = False) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM devices ORDER BY is_online DESC, ip"
        ).fetchall() if not only_online else c.execute(
            "SELECT * FROM devices WHERE is_online=1 ORDER BY ip"
        ).fetchall()
        return [dict(r) for r in rows]


def get_device(mac: str) -> dict | None:
    with get_conn() as c:
        r = c.execute("SELECT * FROM devices WHERE mac=?", (mac,)).fetchone()
        return dict(r) if r else None


def get_new_devices_since(since: datetime) -> list[dict]:
    iso = since.isoformat(timespec="seconds")
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM devices WHERE first_seen >= ? ORDER BY first_seen DESC",
            (iso,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_speedtest_history(days: int = 7) -> list[dict]:
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds")
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM speedtest_results WHERE timestamp >= ? ORDER BY timestamp ASC",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_speedtest(download_bps: float, upload_bps: float,
                   ping_ms: float, server: str = None, isp: str = None) -> int:
    with get_conn() as c:
        cur = c.execute(
            """INSERT INTO speedtest_results
               (timestamp, download_bps, upload_bps, ping_ms, server, isp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (datetime.utcnow().isoformat(timespec="seconds"),
             download_bps, upload_bps, ping_ms, server, isp),
        )
        return cur.lastrowid


def get_stats() -> dict:
    """Métricas para Prometheus."""
    with get_conn() as c:
        total = c.execute("SELECT COUNT(*) AS n FROM devices").fetchone()["n"]
        online = c.execute("SELECT COUNT(*) AS n FROM devices WHERE is_online=1").fetchone()["n"]
        return {"total": total, "online": online}
