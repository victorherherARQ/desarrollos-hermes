FROM python:3.11-slim

# Dependencias de sistema: nmap, arp-scan, libpcap para scapy
RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
    arp-scan \
    libpcap-dev \
    gcc \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Crear directorio de datos
RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
