"""
Collectors: real-time system metrics.
- CPU, RAM, swap, disk, load, network
- CPU temperature (graceful fallback if not available in WSL)
- Top N processes by CPU/RAM
- Docker container stats (if docker socket is mounted)
"""
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

import psutil

# Optional: docker
try:
    import docker  # type: ignore
    _docker_client: Optional["docker.DockerClient"] = None

    def _get_docker():
        global _docker_client
        if _docker_client is None:
            _docker_client = docker.from_env()
        return _docker_client
except Exception:
    _get_docker = None  # type: ignore


# ============================================================
# CPU
# ============================================================
_prev_cpu = None


def cpu_metrics() -> dict:
    """Sample CPU% deltatime; requires a tiny sleep to be accurate."""
    global _prev_cpu
    pct = psutil.cpu_percent(interval=None)
    freq = psutil.cpu_freq()
    count = psutil.cpu_count(logical=True) or 1
    _prev_cpu = pct
    return {
        "cpu_percent": pct,
        "cpu_freq_mhz": (freq.current if freq else 0.0),
        "cpu_count": count,
    }


# ============================================================
# RAM / Swap
# ============================================================
def mem_metrics() -> dict:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        "ram_used_gb": round(vm.used / 1024**3, 2),
        "ram_total_gb": round(vm.total / 1024**3, 2),
        "ram_percent": vm.percent,
        "swap_used_gb": round(sw.used / 1024**3, 2),
        "swap_percent": sw.percent,
    }


# ============================================================
# Disk (root partition)
# ============================================================
def disk_metrics(path: str = "/") -> dict:
    du = psutil.disk_usage(path)
    return {
        "disk_used_gb": round(du.used / 1024**3, 2),
        "disk_total_gb": round(du.total / 1024**3, 2),
        "disk_percent": du.percent,
    }


# ============================================================
# Load average
# ============================================================
def load_metrics() -> dict:
    try:
        l1, l5, l15 = psutil.getloadavg()
    except Exception:
        l1 = l5 = l15 = 0.0
    return {"load1": l1, "load5": l5, "load15": l15}


# ============================================================
# Network counters (cumulative MB)
# ============================================================
def net_metrics() -> dict:
    counters = psutil.net_io_counters()
    return {
        "net_rx_mb": round(counters.bytes_recv / 1024**2, 2),
        "net_tx_mb": round(counters.bytes_sent / 1024**2, 2),
    }


# ============================================================
# Temperature (graceful fallback for WSL)
# ============================================================
def temp_cpu_c() -> Optional[float]:
    """
    Try several sources in order. Returns None if unavailable (e.g. WSL2).
    """
    # 1) psutil (works on Linux when /sys/class/thermal is populated)
    try:
        temps = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}
        for key, entries in temps.items():
            for e in entries:
                if e.current and e.current > 0:
                    return float(e.current)
    except Exception:
        pass

    # 2) /sys/class/thermal/thermal_zone*/temp (direct)
    try:
        tz = Path("/sys/class/thermal")
        if tz.exists():
            best = None
            for f in tz.glob("thermal_zone*/temp"):
                try:
                    raw = int(f.read_text().strip())
                    if raw > 1000:    # millidegrees → divide
                        raw = raw // 1000
                    if raw > 0 and (best is None or raw > best):
                        best = raw
                except Exception:
                    continue
            if best is not None:
                return float(best)
    except Exception:
        pass

    # 3) lm-sensors command
    if shutil.which("sensors"):
        try:
            out = subprocess.run(
                ["sensors", "-u"], capture_output=True, text=True, timeout=3
            ).stdout
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("temp") and "_input" in line:
                    try:
                        val = float(line.split(":")[1].strip())
                        if val > 0:
                            return val
                    except Exception:
                        continue
        except Exception:
            pass

    return None


# ============================================================
# Top processes
# ============================================================
def top_processes(n: int = 10) -> list[dict]:
    procs = []
    for p in psutil.process_iter(attrs=["pid", "name", "username"]):
        try:
            cpu = p.cpu_percent(interval=None)
            mem = p.memory_info().rss / 1024**2
            procs.append({
                "pid": p.info["pid"],
                "name": (p.info["name"] or "")[:40],
                "user": (p.info.get("username") or "")[:20],
                "cpu_pct": cpu,
                "ram_mb": round(mem, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # Need a second sample for accurate CPU%
    time.sleep(0.2)
    # Re-read CPU% (interval=None after first call returns deltas)
    for p, prev in zip(procs, procs):
        try:
            proc = psutil.Process(prev["pid"])
            prev["cpu_pct"] = proc.cpu_percent(interval=None)
        except Exception:
            pass
    procs.sort(key=lambda x: x["cpu_pct"], reverse=True)
    return procs[:n]


# ============================================================
# Docker containers
# ============================================================
def docker_containers() -> list[dict]:
    if _get_docker is None:
        return []
    try:
        client = _get_docker()
        out = []
        for c in client.containers.list(all=False):
            stats = c.stats(stream=False)
            try:
                cpu_delta = (
                    stats["cpu_stats"]["cpu_usage"]["total_usage"]
                    - stats["precpu_stats"]["cpu_usage"]["total_usage"]
                )
                sys_delta = (
                    stats["cpu_stats"]["system_cpu_usage"]
                    - stats["precpu_stats"]["system_cpu_usage"]
                )
                ncpu = stats["cpu_stats"].get("online_cpus", 1)
                cpu_pct = (cpu_delta / sys_delta) * ncpu * 100.0 if sys_delta else 0.0
            except Exception:
                cpu_pct = 0.0
            try:
                mem_mb = stats["memory_stats"]["usage"] / 1024**2
            except Exception:
                mem_mb = 0.0
            out.append({
                "name": c.name,
                "cpu_pct": round(cpu_pct, 1),
                "ram_mb": round(mem_mb, 1),
            })
        return out
    except Exception:
        return []


# ============================================================
# Aggregator
# ============================================================
def collect_all() -> dict:
    m = {}
    m.update(cpu_metrics())
    m.update(mem_metrics())
    m.update(disk_metrics())
    m.update(load_metrics())
    m.update(net_metrics())
    m["temp_cpu_c"] = temp_cpu_c()
    return m
