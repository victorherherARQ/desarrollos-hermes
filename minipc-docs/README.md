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

## Stack actual

```
┌──────────────────────────────────────────────────────────┐
│  MiniPC (AMD Ryzen 7 5825U / 16 GB RAM / Vega 8)       │
│                                                          │
│  ┌────────────────┐    ┌─────────────────────────────┐ │
│  │  k3d cluster   │    │  Docker containers          │ │
│  │  (k3s v1.35)   │    │                             │ │
│  │                 │    │  • ciba-keycloak :8181       │ │
│  │  6 CRDs ✅      │    │  • ciba-oauth2-client :8081 │ │
│  │  2 CRDs ❌      │    │  • ciba-resource-server :8082│ │
│  └────────────────┘    │  • agentgateway :4000 ✅     │ │
│                         └─────────────────────────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  LLM Providers                                     │   │
│  │  • MiniMax-Text-01 (cloud, API) ✅               │   │
│  │  • Ollama + llama3:8B (local) ✅                │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

## Estado de componentes

| Componente | Estado | Ubicación |
|---|---|---|
| k3d cluster `minipc` | ✅ UP | k8s :6550 |
| kagent-controller | ⚠️ Parcial | Solo CRDs soportados |
| agentgateway | ✅ Funcional | :4000 (MiniMax) |
| CIBA OAuth2 stack | ✅ Funcional | :8181, :8081, :8082 |
| Ollama | ✅ Instalado | :11434 |
| Modelos LLM | 🔄 Investigación | Qwen3 8B pendiente |

## Comandos rápidos

```bash
# Cluster k3d
/tmp/k3d cluster list

# kubectl con el cluster minipc
export KUBECONFIG=~/.kube/config
kubectl --kubeconfig=$KUBECONFIG get nodes

# agentgateway (funcionando)
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"minimax","messages":[{"role":"user","content":"test"}],"max_tokens":10}'

# Ver containers activos
docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}"
```

## Autor

Victor — MiniPC PoC environment  
Última actualización: 2026-08-01
