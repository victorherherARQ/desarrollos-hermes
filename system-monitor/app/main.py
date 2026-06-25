"""
System Monitor - main FastAPI app.
- Background scheduler snapshots metrics every N seconds
- REST API for current state, history, top processes, docker stats
- Web UI at /
- Prometheus metrics at /metrics
"""
import json
import logging
import os
import time
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

import collectors
import db
import windows_collector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("system-monitor")

# ============================================================
# Config
# ============================================================
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", "60"))
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "30"))
PORT = int(os.environ.get("PORT", "8500"))

# ============================================================
# App
# ============================================================
app = FastAPI(title="System Monitor", version="1.0")
app.mount("/static", StaticFiles(directory="/app/static"), name="static")


@app.on_event("startup")
def on_start():
    db.init_db()
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(snapshot, "interval", seconds=SCRAPE_INTERVAL, id="snapshot", max_instances=1)
    sched.add_job(prune, "cron", hour=4, id="prune")
    sched.start()
    log.info(f"Scheduler started: scrape every {SCRAPE_INTERVAL}s, retention {RETENTION_DAYS}d")
    # Initial sample
    snapshot()


def snapshot():
    try:
        m = collectors.collect_all()
        # Enrich with Windows Agent (real temp + real LAN)
        if windows_collector.available():
            t = windows_collector.cpu_temp_c()
            if t is not None:
                m["temp_cpu_c"] = t
        db.insert_sample(m)
        cs = collectors.docker_containers()
        if cs:
            db.insert_containers(cs)
    except Exception as e:
        log.exception(f"snapshot error: {e}")


def prune():
    try:
        db.prune(RETENTION_DAYS)
        log.info("prune done")
    except Exception as e:
        log.exception(f"prune error: {e}")


# ============================================================
# API
# ============================================================
@app.get("/api/health")
def health():
    return {"status": "ok", "time": time.time()}


@app.get("/api/current")
def current():
    sample = db.latest_sample()
    if not sample:
        snapshot()
        sample = db.latest_sample()
    if not sample:
        return JSONResponse({"error": "no data yet"}, status_code=503)
    d = dict(sample)
    d["containers"] = [dict(c) for c in db.latest_containers()]
    d["top_processes"] = collectors.top_processes(10)
    return d


@app.get("/api/history")
def history(hours: int = Query(24, ge=1, le=24 * 30)):
    rows = db.samples_since(hours * 3600)
    return [dict(r) for r in rows]


@app.get("/api/containers")
def containers():
    return [dict(c) for c in db.latest_containers()]


@app.get("/api/windows")
def windows_status():
    """Status of the Windows-side hardware agent (if reachable)."""
    return windows_collector.status()


@app.get("/api/report")
def report(hours: int = Query(24, ge=1, le=24 * 30)):
    """Generate a textual summary report."""
    samples = db.samples_since(hours * 3600)
    if not samples:
        return {"error": "no data"}

    def _stats(key, fmt=lambda v: v):
        vals = [s[key] for s in samples if s[key] is not None]
        if not vals:
            return None
        return {
            "min": fmt(min(vals)),
            "max": fmt(max(vals)),
            "avg": fmt(sum(vals) / len(vals)),
        }

    cpu = _stats("cpu_percent", lambda v: round(v, 1))
    ram = _stats("ram_percent", lambda v: round(v, 1))
    disk = _stats("disk_percent", lambda v: round(v, 1))
    load = _stats("load1", lambda v: round(v, 2))
    temp = _stats("temp_cpu_c", lambda v: round(v, 1))
    rx = _stats("net_rx_mb")
    tx = _stats("net_tx_mb")

    return {
        "period_hours": hours,
        "sample_count": len(samples),
        "from_ts": samples[0]["ts"],
        "to_ts": samples[-1]["ts"],
        "cpu_percent": cpu,
        "ram_percent": ram,
        "disk_percent": disk,
        "load1": load,
        "temp_cpu_c": temp,
        "net_rx_mb_delta": round(rx["max"] - rx["min"], 2) if rx else None,
        "net_tx_mb_delta": round(tx["max"] - tx["min"], 2) if tx else None,
    }


@app.get("/metrics")
def prometheus():
    sample = db.latest_sample()
    if not sample:
        return generate_latest()
    out = []
    out.append(f'system_cpu_percent {sample["cpu_percent"]}')
    out.append(f'system_ram_percent {sample["ram_percent"]}')
    out.append(f'system_disk_percent {sample["disk_percent"]}')
    out.append(f'system_load1 {sample["load1"]}')
    if sample["temp_cpu_c"] is not None:
        out.append(f'system_cpu_temp_c {sample["temp_cpu_c"]}')
    return generate_latest() if False else __import__("prometheus_client").client.CollectorRegistry()


# ============================================================
# UI
# ============================================================
@app.get("/", response_class=HTMLResponse)
def index():
    return open("/app/static/index.html").read()
