# Nanobot Factory — Kubernetes Deployment (P3-8-W1)

Production-grade Kubernetes manifests for the Nanobot Factory platform:
**12 microservices + API Gateway + PostgreSQL (pgvector) + Redis + MinIO**.

## Stack overview

| Layer            | Component             | Image / Source                | Port  |
|------------------|-----------------------|-------------------------------|-------|
| **Edge**         | Nginx Ingress         | `ingress-nginx/controller`    | 80/443 |
| **Gateway**      | API Gateway (FastAPI) | `nanobot-factory:v0.8.0`      | 8000  |
| **Storage**      | PostgreSQL + pgvector | `pgvector/pgvector:pg16`      | 5432  |
|                  | Redis 7               | `redis:7-alpine`              | 6379  |
|                  | MinIO                 | `minio/minio:latest`          | 9000/9001 |
| **Domain (12)**  | user-service          | `backend.services.user_service.main`        | 8001 |
|                  | asset-service         | `backend.services.asset_service.main`       | 8002 |
|                  | annotation-service    | `backend.services.annotation_service.main`  | 8003 |
|                  | cleaning-service      | `backend.services.cleaning_service.main`    | 8004 |
|                  | scoring-service       | `backend.services.scoring_service.main`     | 8005 |
|                  | dataset-service       | `backend.services.dataset_service.main`     | 8006 |
|                  | evaluation-service    | `backend.services.evaluation_service.main`  | 8007 |
|                  | agent-service         | `backend.services.agent_service.main`       | 8008 |
|                  | workflow-service      | `backend.services.workflow_service.main`    | 8009 |
|                  | notification-service  | `backend.services.notification_service.main`| 8010 |
|                  | search-service        | `backend.services.search_service.main`      | 8011 |
|                  | collection-service    | `backend.services.collection_service.main`  | 8012 |

All 12 domain services run with **2 replicas minimum, 10 max** (HPA, CPU 70%).

## Directory layout

```
.
├── k8s/                                  # Raw K8s manifests (kubectl apply -k)
│   ├── namespaces.yaml                   # nanobot-factory namespace
│   ├── configmaps.yaml                   # non-secret global config
│   ├── secrets.yaml                      # CHANGE_ME_ placeholders + postgres / minio creds
│   ├── postgres.yaml                     # StatefulSet + Service + PVC (10Gi)
│   ├── redis.yaml                        # Deployment + Service (AOF on, 256MB)
│   ├── minio.yaml                        # Deployment + Service + PVC (50Gi) + bucket-init Job
│   ├── gateway.yaml                      # Deployment + NodePort 30800 + routes ConfigMap
│   ├── ingress.yaml                      # Nginx Ingress + WS split + cert-manager
│   ├── kustomization.yaml                # Kustomize aggregation
│   └── services/                         # 12 microservice Deployments + Services + HPAs
│       ├── user-service.yaml
│       ├── asset-service.yaml
│       ├── annotation-service.yaml
│       ├── cleaning-service.yaml
│       ├── scoring-service.yaml
│       ├── dataset-service.yaml
│       ├── evaluation-service.yaml
│       ├── agent-service.yaml
│       ├── workflow-service.yaml
│       ├── notification-service.yaml
│       ├── search-service.yaml
│       └── collection-service.yaml
└── helm/nanobot-factory/                 # Helm chart (alternative install)
    ├── Chart.yaml                        # v0.1.0
    ├── values.yaml                       # default values
    └── templates/
        ├── _helpers.tpl                  # fullname + commonLabels + resources
        ├── _microservice.tpl             # 12-service template (DRY)
        ├── namespace.yaml
        ├── configmap.yaml
        ├── secret.yaml
        ├── postgres.yaml
        ├── redis.yaml
        ├── minio.yaml
        ├── gateway.yaml
        ├── microservices.yaml            # renders all 12
        └── ingress.yaml
```

## Quick start

### Option A — kubectl + Kustomize

```bash
# 1. (Optional) edit secrets.yaml — replace CHANGE_ME_ with real secrets
$EDITOR k8s/secrets.yaml

# 2. Validate YAML locally (no kubectl needed)
make k8s-validate

# 3. Dry-run apply (client-side)
make k8s-dryrun   # kubectl apply --dry-run=client -k k8s/

# 4. Real deploy
make k8s-deploy   # kubectl apply -k k8s/

# 5. Watch status
make k8s-status
```

### Option B — Helm

```bash
# 1. Render templates locally (no cluster connection)
make helm-template   # helm template nanobot-factory helm/nanobot-factory/

# 2. Install
make helm-install    # helm install nanobot-factory helm/nanobot-factory/

# 3. Uninstall
make helm-uninstall
```

Override values:

```bash
helm install nanobot-factory helm/nanobot-factory/ \
  --namespace nanobot-factory --create-namespace \
  --set image.tag=v0.9.0 \
  --set secrets.postgresPassword=$(openssl rand -hex 32) \
  --set secrets.jwtSecret=$(openssl rand -hex 64)
```

## Prerequisites

### Cluster

- Kubernetes 1.25+ (for `autoscaling/v2` HPA + `networking.k8s.io/v1` Ingress)
- `kubectl` 1.25+
- `helm` 3.10+ (only if using the chart)
- Metrics Server (for HPA `cpu` / `memory` metrics)
- Nginx Ingress Controller (for Ingress resources)
- cert-manager (for TLS via `letsencrypt-prod`)

### Image

The deployment assumes an image `ghcr.io/minimax-ai/nanobot-factory:v0.8.0` exists.
Build locally first:

```bash
make docker:build   # tags ghcr.io/minimax-ai/nanobot-factory:v0.8.0
```

To use a different registry / tag:

```bash
# Kustomize:
sed -i 's|ghcr.io/minimax-ai/nanobot-factory:v0.8.0|<your-registry>/<your-image>:<tag>|' \
    k8s/kustomization.yaml
make k8s-deploy

# Helm:
helm install nanobot-factory helm/nanobot-factory/ \
  --set image.registry=<your-registry> \
  --set image.repository=<your-image> \
  --set image.tag=<tag>
```

## Secrets

`k8s/secrets.yaml` ships with `CHANGE_ME_` placeholders. **Replace these before
production deploy**:

```bash
# Generate strong secrets
export POSTGRES_PASSWORD=$(openssl rand -hex 32)
export JWT_SECRET=$(openssl rand -hex 64)
export JWT_REFRESH_SECRET=$(openssl rand -hex 64)
export MINIO_ROOT_PASSWORD=$(openssl rand -hex 32)
export S3_ACCESS_KEY=$(openssl rand -hex 16)
export S3_SECRET_KEY=$(openssl rand -hex 32)
export SMTP_PASSWORD=$(openssl rand -hex 24)
export ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
export CSRF_SECRET=$(openssl rand -hex 32)

# Re-encode (or use --from-literal when applying)
kubectl -n nanobot-factory create secret generic nanobot-secrets \
  --from-literal=POSTGRES_PASSWORD=$POSTGRES_PASSWORD \
  --from-literal=JWT_SECRET=$JWT_SECRET \
  --from-literal=JWT_REFRESH_SECRET=$JWT_REFRESH_SECRET \
  --from-literal=MINIO_ROOT_PASSWORD=$MINIO_ROOT_PASSWORD \
  --from-literal=S3_ACCESS_KEY=$S3_ACCESS_KEY \
  --from-literal=S3_SECRET_KEY=$S3_SECRET_KEY \
  --from-literal=SMTP_PASSWORD=$SMTP_PASSWORD \
  --from-literal=ENCRYPTION_KEY=$ENCRYPTION_KEY \
  --from-literal=CSRF_SECRET=$CSRF_SECRET \
  --dry-run=client -o yaml | kubectl apply -f -
```

For production, prefer **External Secrets Operator** + AWS Secrets Manager /
HashiCorp Vault. See `k8s/secrets.yaml` header for the recommended pattern.

## HPA (Horizontal Pod Autoscaler)

Every workload has HPA configured:

- **Domain services**: min 2 / max 10 replicas, target CPU 70%
- **Gateway**: min 2 / max 10 replicas, target CPU 70%
- **PostgreSQL / Redis / MinIO**: 1 replica (stateful; HA out of scope)

Verify:

```bash
kubectl get hpa -n nanobot-factory
```

## Networking

```
Internet ──► Nginx Ingress ──► gateway (NodePort 30800) ──► 12 microservices
                                              │
                                              └─► app monolith (:8765) fallback
```

The gateway is exposed as `NodePort 30800` for direct access (bypass Ingress),
and via Ingress on `api-gateway.nanobot-factory.com`.

## Storage

| PVC                 | Size   | Mount                            | Service    |
|---------------------|--------|----------------------------------|------------|
| `postgres-data`     | 10 Gi  | `/var/lib/postgresql/data`       | postgres   |
| `minio-data`        | 50 Gi  | `/data`                          | minio      |
| Redis               | n/a    | `emptyDir` (AOF on tmpfs OK)     | redis      |

The `standard` storage class is referenced; change to your cloud's class via:

```bash
# Kustomize: edit each StatefulSet / Deployment in-place
# Helm: --set postgres.storageClassName=gp3
```

## Health checks

Every service exposes `/healthz`. Test:

```bash
kubectl port-forward -n nanobot-factory svc/gateway 8000:8000 &
curl http://127.0.0.1:8000/_gw/healthz
curl http://127.0.0.1:8000/healthz   # monolith app fallback
```

## Validation

```bash
make k8s-validate   # yaml.safe_load_all — exit code 0 if all OK
make helm-template  # helm template — renders all manifests
make k8s-dryrun     # kubectl apply --dry-run=client
```

## Cleanup

```bash
make k8s-delete       # kubectl delete -k k8s/
make helm-uninstall   # helm uninstall nanobot-factory
```

## Known limitations / next steps

1. **PostgreSQL single replica** — for HA, replace with CloudNative-PG operator.
2. **Redis single replica** — replace with Redis Sentinel or cluster mode.
3. **MinIO single replica** — replace with distributed mode (4+ nodes).
4. **No PodDisruptionBudget** yet — add `policy/v1` PDBs for `minAvailable: 1`.
5. **No NetworkPolicy** yet — add `networking.k8s.io/v1` NetworkPolicy per pod.
6. **Secrets in plaintext** — migrate to External Secrets / Sealed Secrets.
7. **Resource quotas** not set per namespace — add `LimitRange` + `ResourceQuota`.

## References

- Routes: `backend/gateway/routes.yaml` (gateway config; 12 services + catch-all)
- Docker compose (single-node equivalent): `docker-compose.yml`
- Dockerfile: `Dockerfile` (multi-stage: node 20 → python 3.11 → nginx 1.27)