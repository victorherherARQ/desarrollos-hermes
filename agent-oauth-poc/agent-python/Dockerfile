# Imagen base ligera con Python 3.11
FROM python:3.11-slim

# Buenas prácticas: no generar .pyc y que stdout/stderr sean inmediatos
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LOG_LEVEL=INFO

WORKDIR /app

# Primero copiamos requirements para aprovechar la caché de capas de Docker
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Después el código
COPY . .

EXPOSE 8000

# uvicorn con 1 worker -- es un PoC
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7000"]