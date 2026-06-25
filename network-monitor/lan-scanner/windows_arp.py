"""
Windows ARP source — gets the REAL LAN devices from the Windows host.
This complements (or replaces) the WSL-side arp-scan, which only sees the
WSL NAT gateway because of Hyper-V network isolation.

The Windows host is the one that actually sees the 192.168.1.x LAN,
so its arp -a has the real device list.
"""
import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger("windows-arp")

WINDOWS_AGENT_URL = os.environ.get("WINDOWS_AGENT_URL", "http://172.29.48.1:8765")
TIMEOUT = int(os.environ.get("WINDOWS_AGENT_TIMEOUT", "5"))

_cache = {"ts": 0, "data": []}
_cache_ttl = 30


def fetch_arp() -> list[dict]:
    """Returns ARP entries from Windows host, or empty list on failure."""
    now = time.time()
    if now - _cache["ts"] < _cache_ttl and _cache["data"]:
        return _cache["data"]

    url = f"{WINDOWS_AGENT_URL}/arp"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            devices = json.loads(r.read().decode("utf-8"))
        _cache["ts"] = now
        _cache["data"] = devices
        log.info("windows-arp: got %d devices", len(devices))
        return devices
    except (urllib.error.URLError, OSError) as e:
        log.debug("windows-arp unreachable: %s", e)
        return []


def available() -> bool:
    url = f"{WINDOWS_AGENT_URL}/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False
