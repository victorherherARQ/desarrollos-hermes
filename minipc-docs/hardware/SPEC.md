# MiniPC — Especificaciones Hardware

## Host: WSL2 (Windows Subsystem for Linux)

```
========================== OS ==========================
WSL2: Ubuntu 24.04 LTS (jammy)
Kernel: 6.18.33.2-microsoft-standard-WSL2
========================================================
```

## CPU

```
Processor: AMD Ryzen 7 5825U with Radeon Graphics
Cores: 8C/16T (Zen 3)
Base: 2.0 GHz / Boost: 4.5 GHz
Cache: L1 32KB(x8), L2 512KB(x8), L3 16MB
TDP: 15W cTDP (configurable)
```

## RAM

```
Total: 16 GB DDR4
Available en WSL2: ~4.7-5 GB (con 18 containers Docker activos)
                     ↑ Este límite condiciona qué modelos Ollama caben
```

### Implicación para Ollama

| Modelo | RAM necesaria | Cabe ahora? | Solución |
|--------|-------------|------------|----------|
| Qwen3 8B Q4_K_M | 5.3 GB | ❌ No (~4.7 GB disponible) | Parar containers Docker |
| Llama3 8B Q4_0 | 4.6 GB | ❌ No (~4.7 GB, muy justo) | Parar containers Docker |
| Phi-4 3.8B | 2.7 GB | ✅ Sí | Ninguna (cabe siempre) |

## GPU

```
Integrated: AMD Radeon Graphics (Vega 8)
Compute units: 8
VRAM: Comparte RAM del sistema (sin VRAM dedicada)
Vulkan: ✅ Soportado (AMDGPU driver)
```

### Relevancia

- Ollama puede usar GPU para inference si hay soporte Vulkan + compute
- Sin VRAM dedicada, los modelos grandes dependen de RAM compartida
- Vega 8 tiene ~2 GB de VRAM virtual como máximo

## Almacenamiento

```
Principal: NVMe 1TB (1.004.560.514.720 bytes / 931 GB)
Tipo: NVMe SSD (PCIe 3.0 x4)
Velocidad: ~2400 MB/s lectura secuencial
```

Modelos Ollama en `/usr/share/ollama/.ollama/models/`:

```
/dev/sda1 on /usr/share/ollama type ext4 (rw,relatime)
/dev/sda2 on / type ext4 (rw,relatime)
/dev/sda3 on /home type ext4 (rw,relatime)
/dev/sda4 on /mnt/c type ntfs (rw,noatime,...)
```

## Red

```
eth0: 172.29.51.138 (WSL2 NAT)
Gateway: 172.29.48.1
Docker bridge: 172.17.0.0/16
```

## Docker

```
18 containers activos incluyendo:
- Media stack (*arr): ~2-3 GB RAM
- CIBA OAuth2 stack: ~1 GB
- k3d cluster (server + lb): ~1 GB
- agent-oauth-poc: ~1 GB
- Redis + Romm: ~0.5 GB
- agentgateway: <0.1 GB
```

## WSL2 Configuration

```
~/.wslconfig (Windows):
[wsl2]
vmIdleTimeout=-1

# Para aumentar RAM disponible: ajustar memory= en .wslconfig
# Por defecto WSL2 usa 50% de RAM host o 8GB (el menor)
```

## Resumen para IA

| Recurso | Valor | Limitación |
|---------|-------|-----------|
| CPU | 8C/16T Zen3 | ✅ Excelente para inference |
| RAM total | 16 GB | ⚠️ Solo 4.7 GB libre |
| VRAM | ~2 GB (compartida) | ⚠️ Modelos pequeños |
| Almacenamiento | 931 GB NVMe | ✅ Modelos caben en disco |
| Vulkan/GPU | ✅ Soportado | Útil para Ollama |

**Conclusión**: Hardware bueno para CPU inference y pequeños modelos.
Modelos de 8B necesitan ~5.3 GB — viable parando containers Docker.
Para modelos de 70B+ haría falta más RAM (32+ GB).
