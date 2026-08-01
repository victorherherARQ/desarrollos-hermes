# MiniPC — Especificaciones Hardware

## Host: WSL2 (Windows Subsystem for Linux)

```
========================== OS ==========================
WSL2: Ubuntu 24.04 LTS (jammy)
Kernel: 6.18.33.2-microsoft-standard-WSL2
Docker: 28.0.4
Container Runtime: containerd 2.2.3-k3s1
=======================================================
```

## CPU
| Campo | Valor |
|---|---|
| Modelo | AMD Ryzen 7 5825U (Barcelo) |
| Arquitectura | Zen 3 (CNL/BML refresh) |
| Núcleos | 8C / 16T |
| Frecuencia base | 2.0 GHz / boost 4.5 GHz |
| Caché L3 | 16 MB |
| TDP | 15W cTDP-down / 25W cTDP-up |
| Instrucciones vectoriales | AVX2 ✅, FMA3 ✅, SSE4.1/4.2 ✅, AES-NI ✅ |

## RAM
| Campo | Valor |
|---|---|
| Tipo | DDR4-3200 |
| Capacidad total | 16 GB |
| Capacidad disponible para modelo | ~11-12 GB (tras SO + Docker) |
| dual-channel | Sí |

## GPU
| Campo | Valor |
|---|---|
| Integrado | AMD Radeon Vega 8 (GCN 5.0) |
| Compute units | 8 |
| VRAM | Compartida con RAM (hasta ~8 GB configurable) |
| Vulkan | ✅ Soportado (RADV/AMDGPU) |
| OpenCL | ✅ (clinfo disponible) |
| CUDA/NVIDIA | ❌ No disponible |
| ROCm | ❌ No instalado |
| DirectX 12 | ✅ (vía WSLg) |

## Almacenamiento
| Campo | Valor |
|---|---|
| Disco principal | NVMe SSD 1 TB |
| Interfaz | PCIe 3.0 x4 |
| Mount | `/home/vhdez` → `C:\Users\vhdez` |
| Velocidad típica | ~3500 MB/s lectura secuencial |

## Red
| Campo | Valor |
|---|---|
| Adaptador | Virtual switch de WSL2 |
| IP usual | 172.x.x.x |
| Rango Docker/K8s | 172.27.0.0/16 |

## Software Base
| Herramienta | Versión |
|---|---|
| Python | 3.11.15 |
| Ollama | 0.17.4 |
| Docker | 28.0.4 |
| Go | go1.26.4 |
| kubectl | v1.32.0 |
| Helm | v3.15.0-rc.2 |
| k3d | v5.9.0 |
| k3s | v1.35.5+k3s1 |

## Limitaciones para LLMs locales

1. **VRAM**: No hay GPU dedicada — Vega 8 comparte RAM. Cuantización obligatoria (Q4_K_M o inferior).
2. **RAM total**: 16 GB significa que un modelo de 8B en Q4_K_M (~5 GB) deja ~7 GB para inference overhead. Fits but tight.
3. **GPU compute**: GCN 5.0 es antiguo — Vulkan offloading posible pero rendimiento inferior a RDNA.
4. **Contexto**: Con 16 GB, máximo contexto práctico ~4K-8K tokens.
5. **Quantization recomendada**: `Q4_K_M` (balance rendimiento/tamaño) o `IQ4_XS` (más pequeño, calidad comparable).
