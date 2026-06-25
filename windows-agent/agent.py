"""
Windows-side hardware agent.

Reads data Windows can see but WSL2 cannot:
  - CPU temperature (WMI MSAcpi_ThermalZoneTemperature)
  - CPU name, freq, cores
  - RAM (WMI)
  - Network ARP table (the real LAN 192.168.x.x devices)
  - Network interfaces (ipconfig)
  - GPU (WMI Win32_VideoController)
  - Per-process CPU/RAM

Exposes them over HTTP so the WSL stacks (system-monitor, network-monitor)
can consume them.

Run:  python agent.py
Endpoint:  http://<windows-ip>:8765/
"""
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("agent")

PORT = int(os.environ.get("AGENT_PORT", "8765"))
ALLOW_BIND = os.environ.get("AGENT_BIND", "0.0.0.0")  # 0.0.0.0 to accept from WSL

# ============================================================
# Hardware readers
# ============================================================
def _run_ps(ps_script: str) -> str:
    """Run a PowerShell snippet and return stdout."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip()
    except Exception as e:
        return f"ERR: {e}"


def read_cpu_temp_c() -> Optional[float]:
    """Try WMI thermal zone, then OpenHardwareMonitor if installed."""
    # Method 1: WMI MSAcpi_ThermalZoneTemperature (works on most systems)
    out = _run_ps("""
$temps = Get-WmiObject -Namespace "root/wmi" -Class "MSAcpi_ThermalZoneTemperature" -ErrorAction SilentlyContinue
foreach ($t in $temps) {
  $c = ($t.CurrentTemperature - 2732) / 10.0
  if ($c -gt 0 -and $c -lt 110) { Write-Output $c; break }
}
""")
    if out and not out.startswith("ERR"):
        try:
            v = float(out.splitlines()[0])
            if v > 0:
                return v
        except Exception:
            pass

    # Method 2: OpenHardwareMonitor WMI (if user installs it)
    out = _run_ps("""
$cpu = Get-WmiObject -Namespace "root\\OpenHardwareMonitor" -Class "Sensor" -ErrorAction SilentlyContinue |
       Where-Object { $_.SensorType -eq 'Temperature' -and $_.Name -match 'CPU' } |
       Select-Object -First 1 -ExpandProperty Value
if ($cpu) { Write-Output $cpu }
""")
    if out and not out.startswith("ERR"):
        try:
            v = float(out.splitlines()[0])
            if v > 0:
                return v
        except Exception:
            pass

    return None


def read_cpu_info() -> dict:
    out = _run_ps("""
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$obj = @{
  name  = $cpu.Name
  cores = $cpu.NumberOfCores
  threads = $cpu.NumberOfLogicalProcessors
  max_mhz = $cpu.MaxClockSpeed
  load_pct = (Get-CimInstance Win32_Processor).LoadPercentage | Measure-Object -Average | Select-Object -ExpandProperty Average
}
$obj | ConvertTo-Json
""")
    try:
        d = json.loads(out)
        return {
            "name": (d.get("name") or "").strip(),
            "cores_physical": int(d.get("cores") or 0),
            "cores_logical": int(d.get("threads") or 0),
            "max_mhz": float(d.get("max_mhz") or 0),
            "load_pct": float(d.get("load_pct") or 0),
        }
    except Exception:
        return {}


def read_memory() -> dict:
    out = _run_ps("""
$os = Get-CimInstance Win32_OperatingSystem
$obj = @{
  total_gb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
  free_gb  = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
}
$obj | ConvertTo-Json
""")
    try:
        d = json.loads(out)
        total = float(d.get("total_gb") or 0)
        free = float(d.get("free_gb") or 0)
        return {
            "ram_total_gb": total,
            "ram_free_gb": free,
            "ram_used_gb": round(total - free, 2),
            "ram_percent": round((total - free) / total * 100, 1) if total else 0,
        }
    except Exception:
        return {}


def read_gpu() -> list[dict]:
    out = _run_ps("""
$gpus = Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM, DriverVersion
$gpus | ConvertTo-Json
""")
    try:
        arr = json.loads(out)
        if isinstance(arr, dict):
            arr = [arr]
        return [
            {
                "name": g.get("Name"),
                "vram_mb": int(g.get("AdapterRAM") or 0) // (1024 * 1024),
                "driver": g.get("DriverVersion"),
            }
            for g in arr
        ]
    except Exception:
        return []


def read_top_processes(n: int = 10) -> list[dict]:
    ps = (
        "$procs = Get-Process | Sort-Object -Property CPU -Descending | "
        "Select-Object -First " + str(n) + " Id,ProcessName,CPU,WS "
        "| ConvertTo-Json"
    )
    out = _run_ps(ps)
    try:
        arr = json.loads(out)
        if isinstance(arr, dict):
            arr = [arr]
        return [
            {
                "pid": p.get("Id"),
                "name": p.get("ProcessName"),
                "cpu_sec": round(float(p.get("CPU") or 0), 1),
                "ram_mb": round(int(p.get("WS") or 0) / 1024 / 1024, 1),
                "user": p.get("User"),
            }
            for p in arr
        ]
    except Exception:
        return []


def read_arp_table() -> list[dict]:
    """arp -a gives the real LAN devices that WSL cannot see."""
    out = _run_ps("arp -a")
    if not out or out.startswith("ERR"):
        return []
    devices = []
    for line in out.splitlines():
        line = line.strip()
        # Format:  192.168.1.1       00-11-22-33-44-55     dynamic
        parts = line.split()
        if len(parts) < 3:
            continue
        ip = parts[0]
        mac = parts[1].replace("-", ":")
        kind = parts[2] if len(parts) > 2 else ""
        if not ip.count(".") == 3:
            continue
        if not mac.count(":") == 5:
            continue
        if ip.startswith("224.") or ip.startswith("239."):
            continue
        devices.append({"ip": ip, "mac": mac.lower(), "type": kind})
    return devices


def read_interfaces() -> list[dict]:
    out = _run_ps("Get-NetIPAddress -AddressFamily IPv4 | Select-Object IPAddress,InterfaceAlias,InterfaceIndex | ConvertTo-Json")
    try:
        arr = json.loads(out)
        if isinstance(arr, dict):
            arr = [arr]
        return [{"ip": g.get("IPAddress"), "iface": g.get("InterfaceAlias"), "idx": g.get("InterfaceIndex")} for g in arr]
    except Exception:
        return []


def read_hostname() -> str:
    return platform.node()


# ============================================================
# HTTP server
# ============================================================
def collect() -> dict:
    return {
        "agent": "windows-agent",
        "version": "1.0",
        "hostname": read_hostname(),
        "timestamp": time.time(),
        "cpu": read_cpu_info(),
        "temp_cpu_c": read_cpu_temp_c(),
        "memory": read_memory(),
        "gpu": read_gpu(),
        "top_processes": read_top_processes(15),
        "arp": read_arp_table(),
        "interfaces": read_interfaces(),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.debug("HTTP %s", fmt % args)

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.url_path()
        log.info("GET %s from %s", path, self.client_address[0])
        try:
            if path == "/" or path == "/index.html":
                return self._send(200, _index_html(), "text/html")
            if path == "/health":
                return self._send(200, json.dumps({"ok": True, "ts": time.time()}))
            if path == "/all":
                return self._send(200, json.dumps(collect(), default=str))
            if path == "/temp":
                return self._send(200, json.dumps({"temp_cpu_c": read_cpu_temp_c(), "ts": time.time()}))
            if path == "/cpu":
                return self._send(200, json.dumps({**read_cpu_info(), "temp_cpu_c": read_cpu_temp_c()}, default=str))
            if path == "/memory":
                return self._send(200, json.dumps(read_memory()))
            if path == "/gpu":
                return self._send(200, json.dumps(read_gpu()))
            if path == "/processes":
                return self._send(200, json.dumps(read_top_processes(20)))
            if path == "/arp":
                return self._send(200, json.dumps(read_arp_table()))
            if path == "/interfaces":
                return self._send(200, json.dumps(read_interfaces()))
            if path == "/metrics":
                return self._send(200, _prometheus(collect()), "text/plain")
            return self._send(404, json.dumps({"error": "not found"}))
        except Exception as e:
            log.exception("handler error")
            return self._send(500, json.dumps({"error": str(e)}))

    def url_path(self):
        return self.path.split("?")[0] or "/"


def _prometheus(data: dict) -> str:
    out = []
    if data.get("temp_cpu_c") is not None:
        out.append(f'windows_cpu_temp_c {data["temp_cpu_c"]}')
    cpu = data.get("cpu") or {}
    if cpu:
        out.append(f'windows_cpu_load_pct {cpu.get("load_pct", 0)}')
    mem = data.get("memory") or {}
    if mem:
        out.append(f'windows_ram_percent {mem.get("ram_percent", 0)}')
    arp = data.get("arp") or []
    out.append(f'windows_arp_devices {len(arp)}')
    return "\n".join(out) + "\n"


def _index_html() -> str:
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Windows Agent</title>
<style>body{font-family:sans-serif;max-width:800px;margin:2rem auto;padding:1rem;background:#0f1419;color:#e6edf3}
a{color:#58a6ff}h1{margin-bottom:.5rem}code{background:#161b22;padding:2px 6px;border-radius:4px}
ul{line-height:1.8}</style></head>
<body><h1>🪟 Windows Agent</h1>
<p>Publica datos de hardware de Windows para los stacks de WSL.</p>
<h2>Endpoints</h2>
<ul>
<li><a href="/all">/all</a> &mdash; todo en JSON</li>
<li><a href="/temp">/temp</a> &mdash; temperatura CPU</li>
<li><a href="/cpu">/cpu</a> &mdash; info CPU + temp</li>
<li><a href="/memory">/memory</a> &mdash; RAM</li>
<li><a href="/gpu">/gpu</a> &mdash; GPUs</li>
<li><a href="/processes">/processes</a> &mdash; top procesos</li>
<li><a href="/arp">/arp</a> &mdash; tabla ARP (LAN real)</li>
<li><a href="/interfaces">/interfaces</a> &mdash; interfaces de red</li>
<li><a href="/metrics">/metrics</a> &mdash; Prometheus</li>
</ul>
<p>Hostname: <code>%s</code> &middot; Port: <code>%d</code></p>
</body></html>""" % (read_hostname(), PORT)


# ============================================================
# Main
# ============================================================
def main():
    log.info("=" * 60)
    log.info("Windows Agent starting on %s:%d", ALLOW_BIND, PORT)
    log.info("Hostname: %s", read_hostname())
    log.info("=" * 60)
    server = ThreadingHTTPServer((ALLOW_BIND, PORT), Handler)
    log.info("Endpoints ready:")
    log.info("  http://localhost:%d/   (local Windows)", PORT)
    log.info("  http://<windows-ip>:%d/   (from WSL/LAN)", PORT)
    log.info("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
