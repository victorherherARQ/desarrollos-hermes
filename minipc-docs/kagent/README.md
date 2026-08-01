# Kagent — Solo.io AI Agent Framework

## ⚠️ Estado: CRDs no instalables en MiniPC

Los CRDs `agents.kagent.dev` (939 KB) y `sandboxagents.kagent.dev` (808 KB) superan el límite de 262 KB del API server de Kubernetes. **No se pueden instalar en kind ni k3d.**

## Alternativa: Docker standalone

kagent-controller puede ejecutarse como container Docker, ignorando la limitación de CRDs.

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                  kagent Controller                  │
│                                                      │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────┐ │
│  │  Agent CRD   │  │ ModelProvider  │  │ MCP Hub  │ │
│  │  (blocked!) │  │   Config       │  │          │ │
│  └──────────────┘  └───────────────┘  └──────────┘ │
│          ↓                  ↓               ↓       │
│  ┌─────────────────────────────────────────────────┐ │
│  │            k8s API / Docker runtime             │ │
│  └─────────────────────────────────────────────────┘ │
│                          ↓                          │
│  ┌──────────────┐  ┌───────────────┐               │
│  │  Agent Pod   │  │   LLM Provider │               │
│  │  (Harness)  │  │  (OpenAI/etc) │               │
│  └──────────────┘  └───────────────┘               │
└─────────────────────────────────────────────────────┘
```

## CRDs instalables (funcionan)

- ✅ `agentharnesses.kagent.dev` — Pod specs para agentes
- ✅ `memories.kagent.dev` — Gestión de memoria
- ✅ `modelconfigs.kagent.dev` — Config de modelos
- ✅ `modelproviderconfigs.kagent.dev` — Providers (OpenAI, Anthropic, Ollama...)
- ✅ `remotemcpservers.kagent.dev` — MCP servers remotos
- ✅ `toolservers.kagent.dev` — Servidores de herramientas

## CRDs bloqueados (too large)

- ❌ `agents.kagent.dev` — Agent orchestration
- ❌ `sandboxagents.kagent.dev` — Sandbox workload management

## Recursos

- Docs: https://kagent.dev/docs/getting-started/installation
- Helm chart: `oci://ghcr.io/kagent-io/helm-charts/kagent`
- Repo: https://github.com/kagent-dev/kagent
- Helm chart (CRDs): `oci://ghcr.io/kagent-io/helm-charts/kagent-crds`
