# Proveedores LLM — MiniMax en el MiniPC

## MiniMax (usado actualmente)

MiniMax es el proveedor configurado para agentgateway. La API es OpenAI-compatible.

### Configuración

```
Base URL: https://api.minimax.io/v1
API Key:  $MINIMAX_API_KEY (en ~/.hermes/.env)
Model:    MiniMax-Text-01
```

### Verificación

```bash
curl -X POST https://api.minimax.io/v1/chat/completions \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "MiniMax-Text-01",
    "messages": [{"role": "user", "content": "Responde en una palabra"}],
    "max_tokens": 10
  }'
```

### Modelos disponibles

| Modelo | Descripción | Contexto |
|---|---|---|
| `MiniMax-Text-01` | Modelo principal de texto | 1M tokens |
| `abab6.5s-chat` | Chat optimizado | 32K tokens |

## Ollama (alternativa local)

Ollama ya está instalado en el MiniPC. Útil para inference 100% local.

### Modelos recomendados para este hardware

```
ollama pull qwen3:8b          # ~5GB — mejor todo-en-uno
ollama pull gemma3:12b        # ~8GB — multimodal
ollama pull deepseek-r1:7b    # ~5GB — razonamiento puro
ollama pull llama3.1:8b       # ~5GB — baseline
```

### Endpoint

```
http://localhost:11434/v1/chat/completions
```

### Configurar en agentgateway

```yaml
llm:
  port: 4000
  models:
    - name: ollama
      provider:
        custom:
          formats:
            - type: completions
      params:
        apiKey: "ollama"    # dummy, no auth
        baseUrl: "http://localhost:11434/v1"
        model: "qwen3:8b"
```

## Comparativa: MiniMax cloud vs Ollama local

| Aspecto | MiniMax (cloud) | Ollama (local) |
|---|---|---|
| Latencia | ~1-3s | ~5-20s (CPU) |
|throughput | Alto | Bajo (sin GPU NVIDIA) |
| Coste | API key (cuota gratuita) | Gratuito |
| Privacidad | Datos van a MiniMax | 100% local |
| GPU acceleration | NVIDIA/AMD optimizado | CPU/Vulkan (limitado) |
| Modelos disponibles | Todos los de MiniMax | GGUF descargados |
| Contexto | Hasta 1M tokens | Limitado por RAM |
| Fine-tuning | No | Sí (con Ollama run) |
