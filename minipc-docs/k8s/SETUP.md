# Kubernetes (k3s) — Setup en MiniPC

## Resumen

```
Cluster: k3d-minipc
k3s:     v1.35.5+k3s1
k3d:     v5.9.0
Nodes:   1 server (no agents)
API:     https://localhost:6550
```

## Instalación

### 1. Prerrequisitos

- Docker funcionando (sin sudo)
- WSL2 con Ubuntu 24.04
- Usuario en grupo `docker`

### 2. Instalar k3d (sin sudo)

```bash
# Descargar binary directamente
curl -fsSL https://github.com/k3d-io/k3d/releases/download/v5.9.0/k3d-linux-amd64 -o /tmp/k3d
chmod +x /tmp/k3d

# Mover a PATH
sudo mv /tmp/k3d /usr/local/bin/k3d   # si tienes sudo
# o
cp /tmp/k3d ~/bin/k3d
export PATH=$PATH:~/bin
```

### 3. Crear cluster

```bash
# El puerto 8080 está ocupado por structurizr-c4-viewer
# Usamos puertos alternativos

k3d cluster create minipc \
  --api-port 6550 \
  -p "9080:80@loadbalancer" \
  -p "9443:443@loadbalancer" \
  --k3s-arg "--disable=traefik@server:0"
```

> **Nota**: El loadbalancer de k3d mapea puertos del host al cluster. Con los puertos elegidos:
> - `http://localhost:9080` → Ingress del cluster
> - `https://localhost:9443` → Ingress TLS del cluster

### 4. Obtener kubeconfig

```bash
# Kubeconfig default de k3d
k3d kubeconfig get minipc > ~/.kube/config.minipc

# FIX: k3d genera "0.0.0.0:6550" como server — hay que cambiarlo
sed 's|https://0\.0\.0\.0:6550|https://localhost:6550|g' \
  ~/.kube/config.minipc > ~/.kube/config

# Verificar
export KUBECONFIG=~/.kube/config
kubectl get nodes
```

### 5. kubectl (sin sudo)

```bash
# Instalar kubectl
curl -fsSL https://dl.k8s.io/release/v1.32.0/bin/linux/amd64/kubectl \
  -o ~/bin/kubectl
chmod +x ~/bin/kubectl

# o usar el de k3d
/tmp/k3d kubeconfig get minipc > /tmp/kubeconfig
/tmp/k3d kubeconfig get minipc | sed 's|0\.0\.0\.0|localhost|g' > ~/.kube/config
```

## Verificar cluster

```bash
kubectl --kubeconfig=~/.kube/config get nodes
kubectl --kubeconfig=~/.kube/config get ns
```

```
NAME                  STATUS   ROLES           AGE   VERSION
k3d-minipc-server-0   Ready    control-plane   40m   v1.35.5+k3s1
```

## Servicios instalados

| Namespace | Servicio | Nota |
|---|---|---|
| default | k3d-minipc-server-0 | control-plane |
| kube-system | coredns, traefik, local-path-provisioner | k3s components |

## Problemas conocidos

### Puerto 8080 ocupado

```
ERRO[0025] Failed to start: Bind for 0.0.0.0:8080 failed: port is already allocated
```

**Solución**: Usar puertos alternativos (9080/9443 en vez de 8080/443).

### CRDs muy grandes en kind

Los CRDs `agents.kagent.dev` y `sandboxagents.kagent.dev` pesan ~900KB cada uno.
El API server de kind rechaza CRDs con annotations > 262KB.
k3d tiene el mismo límite. **kagent-controller no puede desplegarse como CRD en este entorno.**

## Limpieza

```bash
k3d cluster delete minipc
```
