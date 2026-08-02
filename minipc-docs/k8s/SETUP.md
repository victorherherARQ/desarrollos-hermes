# Kubernetes (k3s) — Setup en MiniPC

## Resumen

```
Cluster: k3d-minipc
k3s:     v1.35.5+k3s1
k3d:     v5.9.0
Nodes:   1 server (no agents)
API:     https://localhost:6550
Ingress: http://localhost:9080 / https://localhost:9443
kubectl: /tmp/kubectl (v1.32.0)
kubeconfig: ~/.kube/config (merged con fix localhost)
```

## Instalación completa

### 1. Prerrequisitos

- Docker funcionando (sin sudo)
- WSL2 con Ubuntu 24.04
- Usuario en grupo `docker`

### 2. Instalar k3d

```bash
# Binary directo (sin sudo)
curl -fsSL https://github.com/k3d-io/k3d/releases/download/v5.9.0/k3d-linux-amd64 -o /tmp/k3d
chmod +x /tmp/k3d
```

### 3. Crear cluster

```bash
# Puerto 8080 ocupado por structurizr-c4-viewer — usamos alternativos
/tmp/k3d cluster create minipc \
  --api-port 6550 \
  -p "9080:80@loadbalancer" \
  -p "9443:443@loadbalancer" \
  --k3s-arg "--disable=traefik@server:0"
```

El loadbalancer mapea:
- `http://localhost:9080` → Ingress del cluster
- `https://localhost:9443` → Ingress TLS

### 4. kubectl (sin sudo)

```bash
curl -fsSL https://dl.k8s.io/release/v1.32.0/bin/linux/amd64/kubectl \
  -o /tmp/kubectl
chmod +x /tmp/kubectl
```

### 5. Fix kubeconfig y verificar

```bash
# k3d genera "https://0.0.0.0:6550" — TLS handshake falla con 0.0.0.0
# Cambiar a localhost
/tmp/k3d kubeconfig get minipc | \
  sed 's|https://0\.0\.0\.0:6550|https://localhost:6550|g' > ~/.kube/config

# Verificar cluster
export KUBECONFIG=~/.kube/config
/tmp/kubectl --kubeconfig=$KUBECONFIG get nodes
```

Output esperado:
```
NAME                  STATUS   ROLES           AGE   VERSION
k3d-minipc-server-0   Ready    control-plane   40m   v1.35.5+k3s1
```

## CRDs instalados

### ✅ Exitosos (6/8)

| CRD | Estado | Notas |
|-----|--------|-------|
| `agentharnesses.kagent.dev` | ✅ | |
| `toolregistrations.kagent.dev` | ✅ | |
| `resolvedtoolpipes.kagent.dev` | ✅ | |
| `resolvedagentpipes.kagent.dev` | ✅ | |
| `registeredagentpipes.kagent.dev` | ✅ | |
| `resolvedtoolinvocations.kagent.dev` | ✅ | |

### ❌ Bloqueados (2/8) — límite 262KB por annotation

| CRD | Tamaño | Error |
|-----|--------|-------|
| `agents.kagent.dev` | 939 KB | `metadata.annotations: Too long: may not be more than 262144 bytes` |
| `sandboxagents.kagent.dev` | 808 KB | Mismo error |

## Comandos útiles

```bash
# Ver nodos
/tmp/kubectl --kubeconfig=~/.kube/config get nodes -o wide

# Ver namespaces
/tmp/kubectl --kubeconfig=~/.kube/config get ns

# Ver pods de sistema
/tmp/kubectl --kubeconfig=~/.kube/config get pods -n kube-system

# Ver CRDs
/tmp/kubectl --kubeconfig=~/.kube/config get crds

# Ver logs del API server
/tmp/kubectl --kubeconfig=~/.kube/config logs -n kube-system -l component=kube-apiserver --tail=20

# Eliminar cluster
/tmp/k3d cluster delete minipc
```

## Problemas conocidos

### Puerto 8080 ocupado

```
ERRO[0025] Failed to start: Bind for 0.0.0.0:8080 failed: port is already allocated
```

**Solución**: Usar puertos alternativos (9080/9443).

### CRDs kagent muy grandes

Los CRDs `agents` y `sandboxagents` contienen schemas de OpenAPI enormes.
El límite de annotations en k8s es 262 KB. **No hay workaround en k3d/kind.**

**Solución real**: 
- Modificar los CRDs truncando descripciones de schemas (no trivial)
- Usar un cluster cloud (EKS/GKE) con límites mayores
- Deploy kagent-controller como container Docker (sin k8s CRDs)

## Arquitectura del cluster

```
┌─────────────────────────────────────────────────────────────┐
│  k3d-minipc (1 server node)                                │
│                                                             │
│  kube-system                                               │
│  ├── coredns            DNS cluster                        │
│  ├── traefik            Ingress (deshabilitado)            │
│  ├── local-path-provisioner   Storage local              │
│  └── metrics-server    Métricas                          │
│                                                             │
│  kube-node-lease        Heartbeats nodos                  │
│  default                                                 │
└─────────────────────────────────────────────────────────────┘
```
