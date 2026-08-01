# agentgateway — Standalone (Solo.io)

## Estado: ✅ Funcional

agentgateway v1.4.1 instalado y funcionando en el MiniPC.

## Qué es

Gateway de conectividad de agentes AI de la **Linux Foundation** (proyecto de solo.io).
Conecta agentes con LLMs locales o cloud, soportando MCP (Model Context Protocol).

- ⭐ 4.2k stars en GitHub
- Contributors: Cisco, AWS, Microsoft, Adobe, Salesforce, Bloomberg
- Repo: https://github.com/agentgateway/agentgateway

## Instalación

```bash
cd ~/desarrollos-hermes/agentgateway-poc

# 1. Descargar binary
curl -fsSL https://github.com/agentgateway/agentgateway/releases/download/v1.4.1/agentgateway-linux-amd64 \
  -o agentgateway
chmod +x agentgateway

# 2. Configurar API key de MiniMax
./inject_key.sh   # inyecta key desde ~/.hermes/.env

# 3. Arrancar
./agentgateway -f config.yaml
```

## Endpoints

| Puerto | Servicio |
|---|---|
| `:4000` | Gateway API (chat completions, etc.) |
| `:19001` | Readiness probe |
| `:19002` | Stats/metrics |

## Verificación

```bash
# Health check
curl http://localhost:19001/ready

# Test chat completions con MiniMax
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -d '{
    "model": "minimax",
    "messages": [{"role": "user", "content": "Di hola en una frase"}],
    "max_tokens": 50
  }'
```

## Configuración

```yaml
# config.yaml (ejemplo)
config:
  readinessAddr: 127.0.0.1:19001
  statsAddr: 127.0.0.1:19002

llm:
  port: 4000
  models:
    - name: minimax
      provider:
        custom:
          formats:
            - type: completions
      params:
        apiKey: "TU_API_KEY"
        baseUrl: "https://api.minimax.io/v1"
        model: "MiniMax-Text-01"
```

## Modelos MiniMax disponibles

| Modelo | Tipo | Uso |
|---|---|---|
| `MiniMax-Text-01` | Texto |chat, reasoning, coding |
| `abab6.5s-chat` | Chat |Conversacional |

## MCP Support

agentgateway soporta MCP para conectar herramientas externas a los agentes:

```yaml
mcp:
  enabled: true
  servers:
    my-mcp-server:
      command: python3
      args:
        - /path/to/mcp-server.py
      env:
        API_KEY: secret
```

## Diferencia con kagent

| Aspecto | agentgateway | kagent |
|---|---|---|
| Paradigma | Gateway/API | Kubernetes-native CRD |
| Instalación | Binary standalone | Helm en k8s |
| CRDs | No | Sí (bloqueados en MiniPC) |
| LLM providers | Custom/OpenAI compatible | Enum fijo (OpenAI, Anthropic, Ollama...) |
| Uso | Ligero, PoC, local | Enterprise, multi-agent |
| Tamaño | 83 MB binary | Completo (controller + CRDs) |
