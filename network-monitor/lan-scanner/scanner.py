"""
Scanners: ARP (rápido) + nmap (hostname/vendor) + speedtest.
"""
import logging
import re
import subprocess
import time
from typing import Iterator

log = logging.getLogger("scanner")

# --- MAC vendor lookup (OUI) ---
# Lista reducida de los vendors más comunes. Para uno real, descargar
# el IEEE OUI file (~5MB) y guardarlo en /app/data/oui.txt.
# Por ahora usamos nmap que ya incluye su propio mapeo.
import nmap  # python-nmap


# ============================================================
# ARP scan (rápido, cada 5 min)
# ============================================================
def arp_scan(subnet: str) -> list[tuple[str, str]]:
    """
    Devuelve lista de (ip, mac) usando arp-scan o scapy como fallback.
    """
    log.info("ARP scan en %s", subnet)
    try:
        # arp-scan es el más rápido y fiable
        proc = subprocess.run(
            ["arp-scan", "--localnet", "-q", "-I", "auto"],
            capture_output=True, text=True, timeout=60,
        )
        results = []
        for line in proc.stdout.splitlines():
            # Formato: "192.168.1.1\t00:11:22:33:44:55\tVendor Name"
            m = re.match(r"^(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F:]{17})\s*(.*)?$", line)
            if m:
                results.append((m.group(1), m.group(2).lower(), m.group(3).strip() or None))
        log.info("ARP scan: %d dispositivos", len(results))
        return results
    except FileNotFoundError:
        log.warning("arp-scan no disponible, usando scapy")
        return _arp_scapy(subnet)
    except subprocess.TimeoutExpired:
        log.error("ARP scan timeout")
        return []


def _arp_scapy(subnet: str) -> list[tuple[str, str]]:
    """Fallback con scapy."""
    try:
        from scapy.all import ARP, Ether, srp
        pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=subnet)
        ans, _ = srp(pkt, timeout=5, verbose=False)
        return [(rcv.psrc, rcv.hwsrc.lower(), None) for _, rcv in ans]
    except Exception as e:
        log.error("scapy ARP falló: %s", e)
        return []


# ============================================================
# NMAP scan (cada hora, hostname + vendor + OS)
# ============================================================
_nm = nmap.PortScanner()


def nmap_enrich(devices: list[dict]) -> dict[str, dict]:
    """
    Para una lista de dispositivos {mac, ip}, devuelve {mac: {hostname, vendor, os}}.
    """
    if not devices:
        return {}

    ips = [d["ip"] for d in devices if d.get("ip")]
    if not ips:
        return {}

    log.info("nmap scan: %d hosts", len(ips))
    try:
        _nm.scan(hosts=" ".join(ips), arguments="-sn -T4")
    except Exception as e:
        log.error("nmap falló: %s", e)
        return {}

    enriched = {}
    for dev in devices:
        ip = dev.get("ip")
        if not ip or ip not in _nm.all_hosts():
            continue
        host = _nm[ip]
        hostname = None
        if "hostnames" in host and host["hostnames"]:
            arr = host["hostnames"]
            if isinstance(arr, list) and arr:
                hostname = arr[0].get("name") if isinstance(arr[0], dict) else arr[0]
        vendor = host.get("vendor", "")
        if vendor == "":
            vendor = None
        os_match = None
        if "osmatch" in host and host["osmatch"]:
            os_match = host["osmatch"][0].get("name")
        enriched[dev["mac"]] = {
            "hostname": hostname,
            "vendor": vendor,
            "os": os_match,
        }
    return enriched


# ============================================================
# Speedtest (cada 30 min)
# ============================================================
def run_speedtest() -> dict | None:
    """
    Ejecuta un test de velocidad. Devuelve {download_bps, upload_bps, ping_ms, server, isp}.
    """
    import speedtest
    log.info("Speedtest...")
    try:
        st = speedtest.Speedtest(timeout=60)
        st.get_best_server()
        download_bps = st.download()  # bits/seg
        upload_bps = st.upload()
        ping_ms = st.results.ping
        server = st.results.server.get("name") if st.results.server else None
        isp = st.results.client.get("isp") if st.results.client else None
        log.info(
            "Speedtest: ↓%.1f Mbps ↑%.1f Mbps ping=%.0fms",
            download_bps / 1e6, upload_bps / 1e6, ping_ms,
        )
        return {
            "download_bps": download_bps,
            "upload_bps": upload_bps,
            "ping_ms": ping_ms,
            "server": server,
            "isp": isp,
        }
    except Exception as e:
        log.error("Speedtest falló: %s", e)
        return None
