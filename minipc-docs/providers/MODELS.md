# LLM Providers — MiniPC

## Resumen de providers

| Provider | Tipo | Estado | Notas |
|----------|------|--------|-------|
| **MiniMax** | Cloud (API) | ✅ Productivo | `MiniMax-Text-01`, vía agentgateway `:4000` |
| **Ollama** | Local | ✅ Instalado | `qwen3:8b` + `llama3:latest` |

---

## MiniMax (cloud) — Recomendado

### Por qué MiniMax
- API OpenAI-compatible (fungible con cualquier cliente OpenAI)
- Modelo `MiniMax-Text-01`: reasoning + coding + chat
- Sin RAM local, sin GPU, funciona siempre
- Integrado en agentgateway `:4000`

### Configuración agentgateway

```yaml
llm:
  models:
    - name: minimax
      provider:
        custom:
          formats:
            - type: completions
      params:
        apiKey: "${MINIMAX_API_KEY}"      # Variable de entorno
        baseUrl: "https://api.minimax.io/v1"
        model: "MiniMax-Text-01"
```

### Test directo

```bash
curl -X POST https://api.minimax.io/v1/chat/completions \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"MiniMax-Text-01","messages":[{"role":"user","content":"Di hola"}],"max_tokens":30}'
```

### Alternativa: vía agentgateway

```bash
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"minimax","messages":[{"role":"user","content":"Di hola"}],"max_tokens":30}'
```

---

## Ollama (local)

### Modelos instalados

| Modelo | Tamaño | RAM necesaria | Quantization | Estado |
|--------|--------|-------------|--------------|--------|
| `qwen3:8b` | 5.0 GB | 5.3 GB | Q4_K_M | ⚠️ Instalado, requiere RAM |
| `llama3:latest` | 4.7 GB | 4.6 GB | Q4_0 | ⚠️ Instalado, requiere RAM |

### Instalación de Ollama

```bash
# Servicio ya instalado y corriendo
systemctl status ollama

# Endpoints
http://localhost:11434  # API REST
```

### Instalar modelo (descarga directa desde HuggingFace)

```bash
# 1. Descargar GGUF desde HuggingFace (no desde Ollama registry — lento)
python3 << 'EOF'
from huggingface_hub import hf_hub_download
path = hf_hub_download(
    repo_id="Qwen/Qwen3-8B-GGUF",
    filename="Qwen3-8B-Q4_K_M.gguf",
    local_dir="/tmp/qwen3-models",
)
print(path)
EOF

# 2. Crear Modelfile
cat > /tmp/Modelfile.qwen3 << 'EOF'
FROM /tmp/qwen3-models/Qwen3-8B-Q4_K_M.gguf
PARAMETER temperature 0.7
PARAMETER top_p 0.8
PARAMETER num_ctx 4096
PARAMETER num_predict 2048
SYSTEM "You are a helpful assistant."
EOF

# 3. Importar a Ollama
ollama create qwen3:8b -f /tmp/Modelfile.qwen3
```

### Configuración agentgateway con Ollama

```yaml
llm:
  models:
    - name: ollama-qwen3
      provider:
        custom:
          formats:
            - type: completions
      params:
        apiKey: "ollama-local"    # Ollama no usa auth
        baseUrl: "http://localhost:11434/v1"
        model: "qwen3:8b"
```

### Test Ollama directo

```bash
# Requiere RAM libre > 5.3 GB
curl -s http://localhost:11434/api/generate \
  -d '{"model":"qwen3:8b","prompt":"Di hola","stream":false,"options":{"num_predict":20}}'
```

### Problema de RAM

```
MemAvailable: ~4.7 GB
Qwen3 8B necesita: 5.3 GB
```

**Solución**: Liberar RAM parando containers no esenciales:

```bash
# Parar media stack (~2-3 GB)
docker stop plex-server radarr sonarr lidarr bazarr jackett transmission

# Ahora funciona:
curl -s http://localhost:11434/api/generate \
  -d '{"model":"qwen3:8b","prompt":"Di hola","stream":false}'
```

---

## Comparativa: MiniMax vs Ollama local

| Criterio | MiniMax (cloud) | Ollama + Qwen3 (local) |
|----------|----------------|----------------------|
| Coste | ~$0.1-1/M tokens | Gratis (electricidad) |
| Latencia | ~500ms-2s | ~10-50 tkn/s (GPU) |
| Calidad | Muy alta (reasoning) | Alta (Q4_K_M ~90% quality) |
| RAM | 0 GB | 5.3 GB mínimo |
| Disponibilidad | Requiere internet | Offline |
| Fine-tuning | No | Sí (con Ollama) |
| Privacidad | Datos van a MiniMax | 100% local |
| Setup actual | ✅ Configurado | ⚠️ Instalado, RAM pendiente |

**Recomendación**: Usar MiniMax para producción/poa, Ollama para experimentos offline.

---

## Modelos recomendados para local

| Modelo | Params | Tamaño | RAM | Uso ideal |
|--------|--------|--------|-----|-----------|
| **Qwen3 8B** | 8.2B | 5.0 GB | 5.3 GB | Todo-en-uno (chat, code, reasoning) |
| Gemma3 12B | 12B | 8.1 GB | 8.5 GB | Mejor calidad, necesita más RAM |
| DeepSeek-R1 7B | 7B | 4.7 GB | 5.0 GB | Reasoning/matemáticas |
| Phi-4 3.8B | 3.8B | 2.5 GB | 2.7 GB | Ligero, rápido, menos calidad |

---

## Proveedores cloud alternativos (OpenAI-compatible)

Si en el futuro necesitas cambiar de proveedor, todos son drop-in replacement:

```yaml
# Groq (ultra-rápido, free tier)
baseUrl: "https://api.groq.com/openai/v1"
model: "llama-3.1-70b-versatile"

# Together AI
baseUrl: "https://api.together.xyz/v1"
model: "meta-llama/Llama-3-70b-chat-hf"

# OpenRouter (agregador)
baseUrl: "https://openrouter.ai/api/v1"
model: "anthropic/claude-sonnet-4"
```
