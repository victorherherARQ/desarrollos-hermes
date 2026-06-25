"""
FastAPI app del LAN Scanner.
- GET  /api/health         → healthcheck
- GET  /api/devices        → lista todos los dispositivos
- GET  /api/devices/online → solo online
- GET  /api/devices/new    → nuevos en las últimas 24h
- GET  /api/speedtest      → histórico
- GET  /api/stats          → contadores (total, online)
- GET  /metrics            → Prometheus
- GET  /                   → UI web (static/index.html)
"""
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST

import db
import scanner
import windows_arp

log = logging.getLogger("app")

# ============================================================
# Config
# ============================================================
SCAN_SUBNET = os.environ.get("SCAN_SUBNET", "192.168.1.0/24")
SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL_SECONDS", "300"))
SPEEDTEST_INTERVAL = int(os.environ.get("SPEEDTEST_INTERVAL_MINUTES", "30"))
STATIC_DIR = Path(__file__).parent / "static"

# ============================================================
# Prometheus metrics
# ============================================================
m_devices_total = Gauge("lan_scanner_devices_total", "Total dispositivos descubiertos")
m_devices_online = Gauge("lan_scanner_devices_online", "Dispositivos online")
m_download_bps = Gauge("lan_scanner_download_bps", "Última descarga (bps)")
m_upload_bps = Gauge("lan_scanner_upload_bps", "Última subida (bps)")
m_ping_ms = Gauge("lan_scanner_ping_ms", "Último ping (ms)")

# ============================================================
# App
# ============================================================
app = FastAPI(title="Network Monitor — LAN Scanner", version="1.0.0")
scheduler = AsyncIOScheduler()


# ============================================================
# Background jobs
# ============================================================
def job_arp_scan():
    """Escaneo ARP rápido."""
    results = scanner.arp_scan(SCAN_SUBNET)
    for ip, mac, vendor in results:
        db.upsert_device(mac, ip, vendor=vendor)
    offline = db.mark_offline_older_than(minutes=15)
    if offline:
        log.info("%d dispositivos marcados offline", offline)
    _refresh_metrics()


def job_nmap_enrich():
    """Enriquece con hostname/vendor/OS."""
    devices = db.get_all_devices(only_online=True)
    enriched = scanner.nmap_enrich(devices)
    for mac, info in enriched.items():
        # Update only if missing
        current = db.get_device(mac)
        if current and (not current.get("hostname") or not current.get("vendor")):
            db.upsert_device(
                mac, current["ip"],
                hostname=info.get("hostname") or current.get("hostname"),
                vendor=info.get("vendor") or current.get("vendor"),
            )


def job_speedtest():
    """Mide velocidad de internet."""
    result = scanner.run_speedtest()
    if result:
        db.save_speedtest(**result)
        m_download_bps.set(result["download_bps"])
        m_upload_bps.set(result["upload_bps"])
        m_ping_ms.set(result["ping_ms"])


def _refresh_metrics():
    stats = db.get_stats()
    m_devices_total.set(stats["total"])
    m_devices_online.set(stats["online"])


@app.on_event("startup")
def startup():
    db.init_db()
    # Primer escaneo inmediato (en background)
    scheduler.add_job(job_arp_scan, "interval",
                      seconds=SCAN_INTERVAL, id="arp",
                      next_run_time=datetime.utcnow())
    scheduler.add_job(job_nmap_enrich, "interval", hours=1, id="nmap")
    scheduler.add_job(job_speedtest, "interval",
                      minutes=SPEEDTEST_INTERVAL, id="speedtest",
                      next_run_time=datetime.utcnow() + timedelta(minutes=2))
    # Refresco de métricas cada 30s
    scheduler.add_job(_refresh_metrics, "interval", seconds=30, id="metrics")
    scheduler.start()
    log.info("Scheduler arrancado. Subnet=%s, ARP=%ds, speedtest=%dmin",
             SCAN_SUBNET, SCAN_INTERVAL, SPEEDTEST_INTERVAL)


# ============================================================
# API endpoints
# ============================================================
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/api/devices")
def list_devices(only_online: bool = False):
    return db.get_all_devices(only_online=only_online)


@app.get("/api/devices/new")
def new_devices(hours: int = 24):
    since = datetime.utcnow() - timedelta(hours=hours)
    return db.get_new_devices_since(since)


@app.get("/api/arp/windows")
def arp_from_windows():
    """Returns the ARP table of the Windows host (the real LAN devices,
    not just the WSL NAT gateway). Requires the Windows Agent running on
    the host at WINDOWS_AGENT_URL (default http://172.29.48.1:8765)."""
    return {
        "windows_agent_available": windows_arp.available(),
        "windows_agent_url": os.environ.get("WINDOWS_AGENT_URL", "http://172.29.48.1:8765"),
        "devices": windows_arp.fetch_arp(),
    }


@app.get("/api/speedtest")
def speedtest_history(days: int = 7):
    return db.get_speedtest_history(days)


@app.get("/api/stats")
def stats():
    return db.get_stats()


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


# ============================================================
# UI estática
# ============================================================
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    index_html = STATIC_DIR / "index.html"
    if index_html.exists():
        return FileResponse(index_html)
    return {"message": "UI no encontrada. Visita /docs para la API."}
