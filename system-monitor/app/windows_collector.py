"""
windows_collector.py — additional collector that calls the Windows Agent
running on the host. Provides data WSL2 cannot see:
  - CPU temperature
  - Real LAN devices (via ARP table)
  - Windows host CPU load (not the WSL namespace)
"""
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Optional

log = logging.getLogger("windows-agent-client")

# Default: Windows host IP visible from WSL. Override with WINDOWS_AGENT_URL env var.
WINDOWS_AGENT_URL = os.environ.get("WINDOWS_AGENT_URL", "http://172.29.48.1:8765")
TIMEOUT = int(os.environ.get("WINDOWS_AGENT_TIMEOUT", "5"))

_cache = {}
_cache_ttl = 10  # seconds


def _get(path: str) -> Optional[dict]:
    """GET a JSON endpoint from the Windows agent, with small cache."""
    now = time.time()
    if path in _cache and now - _cache[path][0] < _cache_ttl:
        return _cache[path][1]

    url = f"{WINDOWS_AGENT_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        _cache[path] = (now, data)
        return data
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        log.debug("windows-agent %s failed: %s", path, e)
        return None


def available() -> bool:
    return _get("/health") is not None


def cpu_temp_c() -> Optional[float]:
    """Returns real CPU temperature from Windows, or None if agent not reachable."""
    d = _get("/temp")
    if d:
        return d.get("temp_cpu_c")
    return None


def windows_cpu_load_pct() -> Optional[float]:
    """Real CPU load as seen by the Windows host (not the WSL VM)."""
    d = _get("/cpu")
    if d:
        return d.get("load_pct")
    return None


def arp_devices() -> list[dict]:
    """Returns the Windows host's ARP table — the real LAN devices."""
    d = _get("/arp")
    if d is None:
        return []
    return d


def gpu_info() -> list[dict]:
    d = _get("/gpu")
    return d or []


def status() -> dict:
    """Returns a full status dict from the agent."""
    return {
        "agent_url": WINDOWS_AGENT_URL,
        "available": available(),
        "temp_cpu_c": cpu_temp_c(),
        "windows_cpu_load_pct": windows_cpu_load_pct(),
        "arp_devices": arp_devices(),
        "gpu_info": gpu_info(),
    }
