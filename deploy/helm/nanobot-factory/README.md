# nanobot-factory — Helm Chart

A production-ready Helm chart for deploying the **nanobot-factory** AIGC
data production platform (FastAPI backend + Vue 3 web UI).

## TL;DR

```bash
helm upgrade --install nanobot-factory ./deploy/helm/nanobot-factory \
    --namespace nanobot-factory --create-namespace
```

## Prerequisites

- Kubernetes **≥ 1.25**
- Helm **≥ 3.10**
- An Ingress controller (the chart defaults to `nginx`)
- cert-manager (only if `ingress.tls` is enabled and you use `letsencrypt-*` issuers)
- A default StorageClass (only if `persistence.data.enabled=true`)

## Installing the chart

```bash
# 1. Install with defaults
helm upgrade --install nanobot-factory ./deploy/helm/nanobot-factory \
    --namespace nanobot-factory --create-namespace

# 2. Wait for rollout
kubectl -n nanobot-factory wait --for=condition=ready pod \
    -l app.kubernetes.io/instance=nanobot-factory --timeout=300s

# 3. Port-forward to verify
kubectl -n nanobot-factory port-forward svc/nanobot-factory 8080:80
# open http://localhost:8080/healthz
```

### With custom values

```bash
helm upgrade --install nanobot-factory ./deploy/helm/nanobot-factory \
    --namespace nanobot-factory --create-namespace \
    --set replicaCount=3 \
    --set image.tag=1.1.0 \
    --set config.logLevel=DEBUG \
    --set ingress.hosts[0].host=nanobot.example.com
```

### With a values file

```bash
helm upgrade --install nanobot-factory ./deploy/helm/nanobot-factory \
    -f my-prod-values.yaml
```

## Configuration

The most common knobs are listed below. See [`values.yaml`](./values.yaml) for
the full list.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `image.repository` | string | `nanobot-factory` | Container image repo |
| `image.tag` | string | `1.0.0` | Image tag (defaults to `appVersion`) |
| `replicaCount` | int | `2` | Pod replicas (ignored when autoscaling is enabled) |
| `service.type` | string | `ClusterIP` | Service type |
| `ingress.enabled` | bool | `true` | Create an Ingress |
| `ingress.className` | string | `nginx` | IngressClass name |
| `ingress.hosts` | list | `[{host: nanobot.example.com}]` | Virtual hosts |
| `autoscaling.enabled` | bool | `true` | Create an HPA |
| `autoscaling.minReplicas` | int | `2` | Min replicas |
| `autoscaling.maxReplicas` | int | `10` | Max replicas |
| `podDisruptionBudget.enabled` | bool | `true` | Create a PDB |
| `persistence.data.enabled` | bool | `true` | Provision a data PVC |
| `persistence.data.size` | string | `50Gi` | Data PVC size |
| `persistence.logs.enabled` | bool | `true` | Provision a logs PVC |
| `persistence.logs.size` | string | `20Gi` | Logs PVC size |
| `config.logLevel` | string | `INFO` | Backend log level |
| `config.allowedOrigins` | string | `https://nanobot.example.com` | CORS allowlist |

## Upgrading

```bash
helm upgrade nanobot-factory ./deploy/helm/nanobot-factory \
    --namespace nanobot-factory
```

Helm uses a rolling update (`maxSurge=1, maxUnavailable=0`), so users see no
downtime as long as at least two replicas are running.

### When the ConfigMap changes

The chart uses a `checksum/config` annotation on the pod template so any
change to the ConfigMap triggers a rollout automatically. To avoid restarts
when only environment variables change in a non-urgent way, edit the value
with `--reuse-values`:

```bash
helm upgrade nanobot-factory ./deploy/helm/nanobot-factory \
    --reuse-values --set config.logLevel=DEBUG
```

## Uninstalling

```bash
helm uninstall nanobot-factory --namespace nanobot-factory
```

The command removes all Kubernetes resources created by the chart, **except**
PVCs (which are retained by default to prevent accidental data loss):

```bash
kubectl -n nanobot-factory delete pvc \
    -l app.kubernetes.io/instance=nanobot-factory
```

## Files in this chart

```
nanobot-factory/
├── Chart.yaml              # chart metadata
├── values.yaml             # default configuration
├── README.md               # this file
└── templates/
    ├── _helpers.tpl        # template helpers (labels, names)
    ├── namespace.yaml      # Namespace (optional)
    ├── serviceaccount.yaml # SA + Role + RoleBinding
    ├── configmap.yaml      # app configuration
    ├── deployment.yaml     # Deployment + PVCs
    ├── service.yaml        # ClusterIP service
    ├── ingress.yaml        # Ingress (TLS via cert-manager)
    ├── hpa.yaml            # HorizontalPodAutoscaler
    ├── pdb.yaml            # PodDisruptionBudget
    └── NOTES.txt           # post-install message
```

## Resources created

| Kind | Count | Notes |
|------|-------|-------|
| Namespace | 0 or 1 | `namespace.create=true` to opt in |
| ServiceAccount | 1 | minimal, no API token |
| Role / RoleBinding | 1 / 1 | read access to own ConfigMap |
| ConfigMap | 1 | injected via `envFrom` |
| Deployment | 1 | 1 container (nginx + uvicorn) |
| Service | 1 | ClusterIP, ports 80 + 8001 |
| Ingress | 0 or 1 | `ingress.enabled=true` to opt in |
| HorizontalPodAutoscaler | 0 or 1 | `autoscaling.enabled=true` |
| PodDisruptionBudget | 0 or 1 | `podDisruptionBudget.enabled=true` |
| PersistentVolumeClaim | 0 / 1 / 2 | data + logs |

## Security context

The chart applies a hardened pod security context by default:

- `runAsNonRoot: true`
- `runAsUser: 101` (matches the nginx user in the runtime image)
- `readOnlyRootFilesystem: true`
- `allowPrivilegeEscalation: false`
- `capabilities.drop: ["ALL"]`
- `seccompProfile: RuntimeDefault`
- `automountServiceAccountToken: false`

## License

MIT — see [`LICENSE`](../../LICENSE).