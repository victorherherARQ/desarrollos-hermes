# Kagent — Solo.io AI Agent Framework

## ⚠️ Estado: Parcialmente instalable en MiniPC

**kagent-controller NO puede desplegarse completamente** en el MiniPC por las limitaciones del API server de k3s.

## Qué es kagent

Framework de agentes AI de **Solo.io** (Linux Foundation) para Kubernetes.

- Extiende Kubernetes con CRDs: `Agent`, `SandboxAgent`, `ToolRegistration`, etc.
- Modelo de agentes: define tools, pipes, harnesses
- Integrado con MCP (Model Context Protocol)
- Repo: https://github.com/kagent-dev/kagent

## Arquitectura

```
Agent (CRD)
├── Spec: modelo, tools, system prompt
├── Status: phase, results, logs
│
├── Harness (link a SandboxAgent)
│   └── SandboxAgent (CRD) — define runtime environment
│
└── ToolRegistration (CRD) — herramientas disponibles
```

## Provider de LLM

kagent soporta providers fijos:
- `OpenAI`, `Anthropic`, `Ollama`, `Gemini`, `AzureOpenAI`
- ❌ **MiniMax NO es first-class** — no hay enum para MiniMax

**Solución conocida**: Usar `OpenAI` provider con `Endpoint` apuntando a MiniMax (OpenAI-compatible).

## Limitaciones en MiniPC

### Problema: CRDs demasiado grandes

| CRD | Tamaño | Límite k8s | Resultado |
|-----|--------|------------|-----------|
| `agents.kagent.dev` | **939 KB** | 262 KB | ❌ Blocked |
| `sandboxagents.kagent.dev` | **808 KB** | 262 KB | ❌ Blocked |

El campo `metadata.annotations` en CRDs tiene límite de 262 KB en k8s.
Los schemas de OpenAPI en estos CRDs generan annotations > 800 KB.

### Soluciones

1. **k3s/k3d en producción real**: Los CRDs caben en EKS/GKE con límites mayores
2. **Modificar los CRDs**: Truncar descripciones de schemas (requiere esfuerzo significativo)
3. **Docker standalone**: Desplegar kagent como container sin k8s CRDs

## CRDs que SÍ se pueden instalar (6/8)

```
agentharnesses.kagent.dev ✅
toolregistrations.kagent.dev ✅
resolvedtoolpipes.kagent.dev ✅
resolvedagentpipes.kagent.dev ✅
registeredagentpipes.kagent.dev ✅
resolvedtoolinvocations.kagent.dev ✅
```

## Comparativa con agentgateway

| Aspecto | kagent | agentgateway |
|---------|--------|-------------|
| Paradigma | Kubernetes CRD-native | Gateway REST |
| Instalación | Helm + k8s CRDs | Binary standalone |
| Complejidad | Alta (CRDs + controller) | Baja |
| LLM providers | Enum fijo (no MiniMax first-class) | Custom (cualquier OpenAI-compatible) |
| MiniPC compatible | ❌ (CRDs grandes) | ✅ |
| Flexibilidad | ✅ CRDs descriptivos | ✅ YAML config |
| MCP support | ✅ | ✅ |
| Horizonte | Enterprise multi-agent | Ligero, PoC, local |

## Recomendación

Para el MiniPC: **usar agentgateway** (ya funcionando).
Para producción cloud: **evaluar kagent** con cluster que soporte CRDs grandes.

## Enlaces

- Repo: https://github.com/kagent-dev/kagent
- Helm charts OCI: `ghcr.io/kagent-io/helm-charts/*`
- Docs: https://solo.io/docs/kagent
