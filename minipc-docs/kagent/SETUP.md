# Kagent — Setup en k3s (MiniPC)

## Estado: ⚠️ Parcial

**kagent-controller** no puede desplegarse completamente en el MiniPC por las siguientes limitaciones:

### Problema: CRDs demasiado grandes

| CRD | Tamaño | Límite k8s | Resultado |
|---|---|---|---|
| `agents.kagent.dev` | 939 KB | 262 KB | ❌ `Too long: may not be more than 262144 bytes` |
| `sandboxagents.kagent.dev` | 808 KB | 262 KB | ❌ `Too long: may not be more than 262144 bytes` |

El schema de validación del CRD `Agent` contiene descripciones extensas que generan annotations internas > 262KB en el API server de Kubernetes. Este límite es de k8s mismo y no es configurable.

### CRDs instalados

Los siguientes CRDs sí se instalaron correctamente:

```
agentharnesses.kagent.dev
memories.kagent.dev
modelconfigs.kagent.dev
modelproviderconfigs.kagent.dev
remotemcpservers.kagent.dev
toolservers.kagent.dev
```

## Solución alternativa: Docker standalone

kagent-controller puede ejecutarse como container Docker standalone, ignorando k8s para la gestión de CRDs.

```bash
# Verificar imagen
docker pull ghcr.io/kagent-io/kagent-controller:latest

# O construir desde código
cd /tmp/kagent-repo
docker build -t kagent-controller:latest \
  -f go/Dockerfile .

# Ejecutar
docker run -d \
  --name kagent-controller \
  -p 8080:8080 \
  -e KUBERNETES_MODE=false \
  -e LOG_LEVEL=info \
  kagent-controller:latest
```

## Proveedores soportados

kagent soporta estos providers (de los cuales solo `OpenAI` + custom endpoint sirve para MiniMax):

```yaml
providers:
  default: openAI      # ← MiniMax usa este con endpoint override
  openAI:
    provider: OpenAI
    apiKeySecretRef: kagent-openai
    apiKeySecretKey: OPENAI_API_KEY
  anthropic:
    provider: Anthropic
    apiKeySecretRef: kagent-anthropic
  ollama:
    provider: Ollama    # Local — útil en este hardware
  azureOpenAI:
    provider: AzureOpenAI
  gemini:
    provider: Gemini
```

## Configurar MiniMax como provider (usando OpenAI)

MiniMax es compatible con la API de OpenAI. Se configura como `OpenAI` con `endpoint` personalizado:

```bash
# Crear Secret con la API key de MiniMax
kubectl create secret generic kagent-minimax \
  --namespace=kagent \
  --from-literal=MINIMAX_API_KEY=tu-api-key

# Aplicar ModelProviderConfig
cat <<EOF | kubectl apply -f -
apiVersion: kagent.dev/v1alpha2
kind: ModelProviderConfig
metadata:
  name: minimax-provider
  namespace: kagent
spec:
  type: OpenAI
  endpoint: https://api.minimax.io/v1
  secretRef:
    name: kagent-minimax
    key: MINIMAX_API_KEY
  models:
    - name: MiniMax-Text-01
      displayName: "MiniMax Text 01"
    - name: abab6.5s-chat
      displayName: "MiniMax Chat"
EOF
```

## Instalación Helm (para cluster que soporte CRDs)

```bash
# Instalar Helm
curl -fsSL https://github.com/helm/helm/releases/download/v3.17.4/helm-v3.17.4-linux-amd64.tar.gz \
  -o /tmp/helm.tar.gz
tar xzf /tmp/helm.tar.gz -C /tmp/
sudo mv /tmp/linux-amd64/helm /usr/local/bin/helm

# Instalar CRDs
helm install kagent-crds ./helm/kagent-crds/ --namespace kagent

# Instalar kagent con OpenAI provider
helm install kagent ./helm/kagent/ --namespace kagent \
  --set providers.default=openAI \
  --set providers.openAI.apiKeySecretRef=kagent-openai
```

## Recursos

- Repo: https://github.com/kagent-dev/kagent
- Docs: https://kagent.dev
- Helm chart: OCI (`ghcr.io/kagent-io/helm-charts/kagent`)
- Releases: https://github.com/kagent-dev/kagent/releases

## Próximos pasos

1. Ejecutar kagent-controller como container standalone con MiniMax
2. Probar un `Agent` end-to-end vía API REST
3. Si se dispone de cluster cloud (EKS/GKE/k3s), desplegar el Helm chart completo
