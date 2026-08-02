# agentgateway — Standalone (Solo.io)

## Estado: ✅ Funcional

- **Versión**: v1.4.1
- **Puerto**: `:4000` (HTTP API)
- **Readiness**: `:19001`
- **Stats**: `:19002`
- **Providers configurados**: MiniMax + Ollama

## Qué es

Gateway de conectividad de agentes AI de la **Linux Foundation** (proyecto de solo.io).
Conecta agentes con LLMs locales o cloud, soportando MCP (Model Context Protocol).

- ⭐ 4.2k stars en GitHub
- Contributors: Cisco, AWS, Microsoft, Adobe, Salesforce, Bloomberg
- Repo: https://github.com/agentgateway/agentgateway

## Estructura del proyecto

```
agentgateway-poc/
├── agentgateway          # Binary v1.4.1
├── config.yaml          # Config con providers MiniMax + Ollama
├── start.sh             # Script de arranque (inyecta MINIMAX_API_KEY)
└── .gitignore
```

## Instalación

```bash
cd ~/desarrollos-hermes/agentgateway-poc

# Arrancar con start.sh (inyecta API key desde ~/.hermes/.env)
./start.sh

# O manualmente:
export MINIMAX_API_KEY=$(grep MINIMAX_API_KEY ~/.hermes/.env | cut -d= -f2)
./agentgateway -f config.yaml
```

## Endpoints

| Puerto | Servicio |
|--------|----------|
| `:4000` | Gateway API (chat completions) |
| `:19001` | Readiness probe |
| `:19002` | Stats/metrics |

## Verificación

```bash
# Health check
curl http://localhost:19001/ready

# Test MiniMax
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -d '{
    "model": "minimax",
    "messages": [{"role": "user", "content": "Di hola en una frase"}],
    "max_tokens": 50
  }'

# Test Ollama (requiere RAM libre > 5.3 GB)
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ollama-local" \
  -d '{
    "model": "ollama-qwen3",
    "messages": [{"role": "user", "content": "Di hola"}],
    "max_tokens": 50
  }'
```

## Configuración completa (`config.yaml`)

```yaml
# =============================================================================
# agentgateway PoC — MiniMax + Ollama providers (standalone)
# Solo.io AI Agent Infrastructure PoC
# =============================================================================

config:
  readinessAddr: 127.0.0.1:19001
  statsAddr: 127.0.0.1:19002

frontendPolicies:
  http:
    maxBufferSize: 20971520

llm:
  port: 4000
  models:
    - name: minimax
      provider:
        custom:
          formats:
            - type: completions
      params:
        apiKey: "${MINIMAX_API_KEY}"       # inyectado por start.sh
        baseUrl: "https://api.minimax.io/v1"
        model: "MiniMax-Text-01"

    - name: ollama-qwen3
      provider:
        custom:
          formats:
            - type: completions
      params:
        apiKey: "ollama-local"              # cualquier string (no usa auth)
        baseUrl: "http://localhost:11434/v1"
        model: "qwen3:8b"
```

## Proveedores LLM configurados

### MiniMax (cloud, recomendado para producción)
- **Modelo**: `MiniMax-Text-01`
- **API**: OpenAI-compatible (`/v1/chat/completions`)
- **Base URL**: `https://api.minimax.io/v1`
- **Auth**: Bearer token vía `${MINIMAX_API_KEY}`
- **Status**: ✅ Funcionando en `:4000`

### Ollama (local, requiere RAM)
- **Modelo**: `qwen3:8b` (Q4_K_M, ~5.3 GB VRAM)
- **API**: OpenAI-compatible (`http://localhost:11434/v1`)
- **Status**: ⚠️ Instalado pero requiere >5.3 GB RAM disponible

## Modelos Ollama disponibles

| Modelo | Tamaño | RAM necesaria | Estado |
|--------|--------|--------------|--------|
| `qwen3:8b` | 5.0 GB | 5.3 GB | ⚠️ Requiere liberar RAM |
| `llama3:latest` | 4.7 GB | 4.6 GB | ⚠️ Requiere RAM |

## Problema de RAM con Ollama

El MiniPC tiene **16 GB RAM** con WSL2, pero ~10 GB usados por Docker (18 containers).

```
MemAvailable: 4.7 GB
Qwen3 8B necesita: 5.3 GB
```

**Solución**: Parar containers no esenciales temporalmente para liberar RAM:

```bash
# Liberar ~2-3 GB parando media stack
docker stop plex-server radarr sonarr lidarr bazarr jackett transmission

# Luego funciona:
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer ollama-local" \
  -d '{"model": "ollama-qwen3", "messages": [{"role": "user", "content": "Di hola"}]}'
```

## Script de arranque (`start.sh`)

```bash
#!/bin/bash
# Carga MINIMAX_API_KEY desde ~/.hermes/.env y arranca agentgateway

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${HOME}/.hermes/.env"

if [ -f "$ENV_FILE" ]; then
    export $(grep MINIMAX_API_KEY "$ENV_FILE" | xargs)
fi

if [ -z "$MINIMAX_API_KEY" ]; then
    echo "ERROR: MINIMAX_API_KEY no encontrada en $ENV_FILE"
    exit 1
fi

# Reemplazar placeholder en config.yaml
sed -i "s|YOUR_...KEY|${MINIMAX_API_KEY}|" "${SCRIPT_DIR}/config.yaml"

echo "Iniciando agentgateway..."
"${SCRIPT_DIR}/agentgateway" -f "${SCRIPT_DIR}/config.yaml"
```

## Comparativa agentgateway vs kagent

| Aspecto | agentgateway | kagent |
|---------|-------------|--------|
| Paradigma | Gateway/API REST | Kubernetes CRDs |
| Instalación | Binary standalone | Helm en k8s |
| CRDs | No | Sí (bloqueados en MiniPC) |
| LLM providers | Custom/OpenAI compatible | Enum fijo |
| Flexibilidad LLM | ✅ Alta (cualquier endpoint OpenAI-compatible) | ❌ Fijo (OpenAI, Anthropic, Ollama...) |
| Uso | Ligero, PoC, local | Enterprise, multi-agent |
| Tamaño | 83 MB binary | Controller + CRDs (~2 MB) |
| MCP support | ✅ Sí | ✅ Sí |
| MiniMax | ✅ OpenAI-compatible | ⚠️ Solo si usa endpoint OpenAI |

## Diferencia clave: providers

**agentgateway** usa `custom` provider con `baseUrl` + `model`, así que cualquier LLM con API OpenAI-compatible funciona (MiniMax, Ollama, Groq, Together, etc.).

**kagent** tiene enum fijo de providers (`OpenAI`, `Anthropic`, `Ollama`, `Gemini`, `AzureOpenAI`) — MiniMax NO es first-class. Para MiniMax en kagent necesitarías endpoint OpenAI-compatible, pero no está documentado como opción.
