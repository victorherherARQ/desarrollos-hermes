# MiniPC Docs — Victor's Home Lab

Documentación del MiniPC (portátil AMD Ryzen 7 5825U) como entorno de desarrollo y PoC para IA agent.

## Índice

```
minipc-docs/
├── README.md              ← Este archivo
├── hardware/
│   └── SPEC.md            ← Especificaciones hardware completas
├── k8s/
│   └── SETUP.md           ← Cluster k3s (k3d) — setup y comandos
├── kagent/
│   ├── README.md          ← Visión general de kagent (solo.io)
│   └── SETUP.md           ← Intento de deployment + limitaciones
└── agentgateway/
│   └── SETUP.md           ← agentgateway standalone ✅ funcionando
└── providers/
    └── MODELS.md          ← Modelos LLM: MiniMax + Ollama local
```

## Arquitectura

```
┌──────────────────────────────────────────────────────────────┐
│  MiniPC (AMD Ryzen 7 5825U / 16 GB RAM / Vega 8)          │
│  WSL2 Ubuntu 24.04                                         │
│                                                              │
│  ┌────────────────────┐  ┌──────────────────────────────┐  │
│  │  k3d cluster       │  │  Docker containers (18)      │  │
│  │  k3s v1.35.5       │  │                              │  │
│  │                    │  │  • agentgateway :4000  ✅    │  │
│  │  API: localhost:6550│  │  • ciba-keycloak :8181 ✅   │  │
│  │  Ingress: :9080     │  │  • ciba-oauth2-client :8081 ✅│  │
│  │                    │  │  • ciba-resource-server :8082 ✅│  │
│  │  6 CRDs instalados  │  │  • *arr media stack         │  │
│  │  2 CRDs bloqueados  │  │  • k3d loadbalancer        │  │
│  └────────────────────┘  └──────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  LLM Providers                                         │  │
│  │  • MiniMax-Text-01 (cloud, API) ✅                  │  │
│  │  • Ollama :11434 ✅                                  │  │
│  │    - qwen3:8b (Q4_K_M, 5.0 GB) ⚠️ RAM              │  │
│  │    - llama3:latest (4.7 GB) ⚠️ RAM                   │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## Estado de componentes

| Componente | Estado | Ubicación |
|------------|--------|-----------|
| k3d cluster `minipc` | ✅ UP | k8s API :6550 |
| kagent-controller | ⚠️ Parcial | Solo 6/8 CRDs |
| **agentgateway v1.4.1** | ✅ Funcional | :4000 con MiniMax + Ollama |
| CIBA OAuth2 stack | ✅ Funcional | :8181, :8081, :8082 |
| Ollama service | ✅ UP | :11434 |
| qwen3:8b (Ollama) | ⚠️ Instalado | Requiere liberar RAM |
| llama3:latest (Ollama) | ⚠️ Instalado | Requiere liberar RAM |

## Quick commands

```bash
# agentgateway — funcionando con MiniMax
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"minimax","messages":[{"role":"user","content":"Di hola"}],"max_tokens":30}'

# kubectl con cluster minipc
export KUBECONFIG=~/.kube/config
kubectl --kubeconfig=$KUBECONFIG get nodes

# Ollama modelos
ollama list

# Ver containers activos
docker ps --format "{{.Names}}\t{{.Ports}}" | grep -v k3d-

# Liberar RAM (parar media stack)
docker stop plex-server radarr sonarr lidarr bazarr jackett transmission
```

## Autor

Victor — MiniPC PoC environment
Última actualización: 2026-08-02
