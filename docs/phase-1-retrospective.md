# Phase 1 retrospective — fanzone + mark8ly

What we hit during the first end-to-end onboarding, why, and the
exact pattern that follows for the remaining products
(homechef, devai, gameverse, blog, …).

## The pattern (use this for every new product)

For each product `<P>`:

### 1. In tesserix-k8s

#### 1.1 ExternalSecret for GHCR image creds
```
external-secrets/prod/kargo-<P>/externalsecret.yaml   # ghcr-image-creds, regex scoped
external-secrets/prod/kargo-<P>/kustomization.yaml
```
Register in `external-secrets/prod/kustomization.yaml`. The Secret
name is **always** `ghcr-image-creds` and lives in the
`kargo-<P>` namespace. `repoURL` is a regex narrowing the PAT scope to
just that product's GHCR packages.

#### 1.2 Annotate every Argo CD Application that Kargo will mutate
```
metadata:
  annotations:
    kargo.akuity.io/authorized-stage: kargo-<P>:prod
spec:
  source:
    helm:
      parameters:
        - name: image.tag
          value: "<current-tag>"   # any non-empty placeholder; Kargo overwrites on first promotion
```
**Both** the annotation AND the `helm.parameters.image.tag` block are
required. Without the annotation Kargo refuses to mutate the App.
Without `helm.parameters.image.tag` there's no field for Kargo to
patch — it doesn't write to `values.yaml`.

### 2. In kargo-manifests

```
projects/<P>/
├── project.yaml                 # Namespace + Project + ProjectConfig
├── warehouses/services.yaml     # 1 Warehouse, N image subscriptions
└── stages/prod.yaml             # 1 Stage, N argocd-update steps
```

That's it. The kargo-projects ApplicationSet in tesserix-k8s
(`argocd/prod/apps/release/kargo-projects-appset.yaml`) generates
`kargo-project-<P>` on its own. **Do not** add anything to
tesserix-k8s for the Kargo CRDs themselves.

## The seven gotchas we hit (don't repeat)

### 1. `Project` has no `spec` in Kargo 1.9
Old docs and example tutorials show `spec.promotionPolicies` on
`Project`. In 1.9, that field was extracted into a separate
**`ProjectConfig`** CRD. The Project resource is now a tiny
cluster-scoped marker with no spec at all.

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: Project
metadata:
  name: kargo-<P>          # MUST equal the namespace name (see gotcha 2)
---
apiVersion: kargo.akuity.io/v1alpha1
kind: ProjectConfig
metadata:
  name: kargo-<P>
  namespace: kargo-<P>
spec:
  promotionPolicies:
    - stage: prod
      autoPromotionEnabled: true
```

Symptom if you forget: ArgoCD reports
`failed to create typed patch object (.spec: field not declared in schema)`.

### 2. `Project.metadata.name` MUST equal the namespace name
The Kargo project admission webhook
(`pkg/webhook/kubernetes/project/webhook.go`) does
`Get(namespace=project.Name)` and rejects with *"namespace already
exists and is not labeled as a Project namespace"* if the namespace
either (a) doesn't exist with that name, or (b) exists but doesn't
have the right label.

Implication: if you want the project to live in `kargo-foo`, the
`Project` resource is named `kargo-foo`. The dir under
`projects/<dirname>/` should match too — call it `projects/foo/`,
inside use `kargo-foo` as the resource name. The
`kargo.akuity.io/authorized-stage` annotation on Argo CD Applications
must therefore be `kargo-foo:prod`, **not** `foo:prod`.

We initially named everything just `foo` and bounced off this for
two refresh cycles.

### 3. The namespace label is `kargo.akuity.io/project: "true"`
Per `api/v1alpha1/labels.go` (`LabelValueTrue = "true"`), the value
of the project namespace label is the literal string `"true"` — it's
a **boolean marker**, not a back-reference to the project name. We
spent half an hour assuming the value was the project name; the
admission webhook keeps rejecting until you set it to `"true"`.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: kargo-<P>
  labels:
    kargo.akuity.io/project: "true"   # <-- exact value, not the project name
```

### 4. Field-ownership conflict on existing namespaces
If the `kargo-<P>` namespace already exists (e.g. because Argo CD
created it via `CreateNamespace=true`) without the label, ArgoCD's
**ServerSideApply** refuses to add the label because the namespace
metadata's `labels` field has another field manager. Symptom:
`Please review the fields above—they currently have other managers`.

Fix: one-shot `kubectl label namespace kargo-<P> kargo.akuity.io/project=true --overwrite`. After Kargo adopts the namespace and ArgoCD next syncs, ownership is fine going forward. This is a true bootstrap one-off.

### 5. `helm.images[].key` is the parameter NAME, not an image URL
In Kargo 1.9 the `argocd-update` step's
`apps[].sources[].helm.images[]` config has fields named **`key`** and
**`value`**:

```yaml
helm:
  images:
    - key: image.tag                                                 # Helm parameter name
      value: ${{ imageFrom("ghcr.io/tesserix/<svc>").Tag }}          # value to set
```

The earlier (deprecated) syntax used `image:` + `parameter:` and
is still in the Kargo docs in places. We followed that in the first
cut and the kubeconform check caught it.

### 6. `imageFrom("<url>")` matches by exact URL string
The URL inside `imageFrom()` must be a string that **also appears in
the Warehouse's image subscriptions list**. We watch `ghcr.io/...`
even though the chart values reference the `asia-south1-docker.pkg.dev/.../ghcr-remote/...`
mirror — so `imageFrom("ghcr.io/...")` is what to use, not the GAR
mirror URL. The repo URL in the chart values is independent; only
the **tag** is updated by argocd-update.

### 7. Watch GAR mirror, NOT ghcr.io directly
**Cost + reliability win.** Every Warehouse poll lists tags + fetches
manifests for each artifact. Pointing at `ghcr.io/...` means each call
goes out through Cloud NAT to GHCR's edge — that's $0.045/GB billed,
and we hit a non-deterministic `dial tcp ... i/o timeout` from the
kargo-controller pod (likely an HTTP/2 + Cloud-NAT-keepalive
interaction; same network from a sibling curl pod completed in 0.3s).

Pointing at the in-region GAR remote-repo mirror solves both:

```yaml
subscriptions:
  - image:
      repoURL: asia-south1-docker.pkg.dev/tesseracthub-480811/ghcr-remote/tesserix/<service>
      imageSelectionStrategy: NewestBuild
      allowTags: '^main-[a-f0-9]{7,8}$'
      platform: linux/amd64
      discoveryLimit: 5
```

- Same tag — GAR caches GHCR transparently.
- In-region traffic = no NAT data-processing cost.
- `imageFrom("asia-south1-docker.pkg.dev/.../<svc>").Tag` returns just
  the tag string, so the chart's `image.repository` (which already
  points at GAR) doesn't need to change.

Auth: don't bother creating a `kargo.akuity.io/cred-type=image`
Secret per project — instead bind the kargo-controller K8s SA to a
GCP SA via Workload Identity once, cluster-wide:

```bash
PROJECT=tesseracthub-480811
gcloud iam service-accounts create kargo-controller --project=$PROJECT
gcloud artifacts repositories add-iam-policy-binding ghcr-remote \
  --project=$PROJECT --location=asia-south1 \
  --member="serviceAccount:kargo-controller@$PROJECT.iam.gserviceaccount.com" \
  --role=roles/artifactregistry.reader
gcloud iam service-accounts add-iam-policy-binding \
  "kargo-controller@$PROJECT.iam.gserviceaccount.com" --project=$PROJECT \
  --member="serviceAccount:$PROJECT.svc.id.goog[kargo/kargo-controller]" \
  --role=roles/iam.workloadIdentityUser
```

…and annotate the K8s SA via the kargo Helm values:

```yaml
controller:
  serviceAccount:
    annotations:
      iam.gke.io/gcp-service-account: kargo-controller@tesseracthub-480811.iam.gserviceaccount.com
```

Kargo's `gar/workload_identity_federation.go` auto-detects GCE and uses
ADC for any `*.pkg.dev` host. No Secret needed.

### 8. Don't blow the GAR upstream-fetch quota
`artifactregistry.googleapis.com` enforces a per-host-per-minute
upstream-fetch quota (default ~60 req/min) for **remote repositories**.
On the first Warehouse poll, every uncached tag triggers GAR to fetch
its manifest from GHCR. With 23 fanzone subscriptions × `discoveryLimit:
20`, that's 460 cold-cache fetches in seconds — instant
`TOOMANYREQUESTS`.

Set `discoveryLimit: 5` (you only ever promote the newest tag with
`NewestBuild`, so 5 is plenty) and `interval: 300s` (the default 60s
hammers GAR for no benefit when the source rarely changes more than
once every few minutes). Once GAR has the manifests cached, future
polls are free.

```yaml
spec:
  freightCreationPolicy: Automatic
  interval: 300s              # was 60s — 5× quota relief
  subscriptions:
    - image:
        ...
        discoveryLimit: 5     # was 20 — 4× quota relief
```

### 9. ArgoCD chokes on Deployment.status.terminatingReplicas
Kubernetes 1.31+ adds `Deployment.status.terminatingReplicas`.
ArgoCD's vendored OpenAPI schema doesn't know about it, so the
structured-merge diff fails on every sync of any chart that contains
a Deployment with active terminating replicas, with:
`error building typed value from live resource: .status.terminatingReplicas: field not declared in schema`.

Fix: drop the entire `status` subtree from the diff in the affected
Application's `ignoreDifferences` block. Status is owned by
controllers anyway.

```yaml
ignoreDifferences:
  - group: apps
    kind: Deployment
    jsonPointers:
      - /status
```

## Architecture as deployed

```
┌────────────────────────────────────────────────────────────────────────┐
│ tesserix/tesserix-k8s    (this is your gitops platform repo)           │
│                                                                        │
│  argocd/prod/apps/release/                                             │
│    ├─ kargo-projects-appset.yaml   ── ApplicationSet (git-dir gen)     │
│    └─ kargo-templates-app.yaml     ── ClusterPromotionTasks            │
│                                                                        │
│  external-secrets/prod/kargo-<P>/  ── ghcr-image-creds Secret per ns   │
│                                                                        │
│  argocd/prod/apps/<P>/*.yaml       ── App.metadata.annotations         │
│                                       kargo.akuity.io/authorized-stage │
│                                       App.spec.source.helm.parameters  │
│                                       (image.tag — Kargo writes here)  │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            │ ApplicationSet generates one
                            ▼ Argo CD Application per dir
┌────────────────────────────────────────────────────────────────────────┐
│ tesserix/kargo-manifests   (this repo — Kargo CRDs)                    │
│                                                                        │
│  projects/<P>/                                                         │
│    ├─ project.yaml              ── Namespace + Project + ProjectConfig │
│    ├─ warehouses/services.yaml  ── one Warehouse, N subscriptions      │
│    └─ stages/prod.yaml          ── one Stage, N argocd-update steps    │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            │ Argo CD applies into kargo-<P> namespace
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Cluster: tesseract-prod-in-gke                                         │
│                                                                        │
│  ns kargo-<P>:    Project + ProjectConfig + Warehouse + Stage           │
│  ns <P>:          actual app workloads (Knative, Deployments)          │
│                                                                        │
│  Warehouse polls ghcr.io/tesserix/* every 60s                          │
│  → New tag matches allowTags regex                                     │
│  → Freight created                                                     │
│  → ProjectConfig.promotionPolicies says auto-promote                   │
│  → Promotion runs argocd-update                                        │
│  → Argo CD App.spec.source.helm.parameters.image.tag updated           │
│  → Argo CD reconciles                                                  │
│  → Knative service / Deployment rolls                                  │
│  → kubelet pulls from GAR mirror (cached layers)                       │
└────────────────────────────────────────────────────────────────────────┘
```

## What goes where

| | tesserix-k8s | kargo-manifests |
|---|---|---|
| ArgoCD Application / ApplicationSet / AppProject | ✅ | ❌ |
| ExternalSecret (any) | ✅ | ❌ |
| Helm chart (values, templates) for an app | ✅ | ❌ |
| ArgoCD Application annotation `kargo.akuity.io/authorized-stage` | ✅ on the existing App | (referenced from here) |
| Kargo `Project` / `ProjectConfig` / `Warehouse` / `Stage` / `Promotion` / `PromotionTask` | ❌ | ✅ |
| Kargo `ClusterPromotionTask` (cluster-scoped, reusable) | ❌ | ✅ under `templates/` |

If you ever feel the urge to put a `Warehouse` in tesserix-k8s,
stop — that's how this split breaks down. The corollary: the only
thing the kargo-projects ApplicationSet ever syncs onto the cluster
is **kargo.akuity.io/* CRDs and a project Namespace**.

## Phase 2 onboarding (next products)

Run through this checklist for each of homechef, devai, gameverse,
blog, social, scrapper, stockpilot, bookkeeping, guardix:

1. Identify the GHCR repos the product publishes — `gh package list`
   or look at `kubectl -n <P> get deploy -o jsonpath='{...}'`.
2. Identify the tag pattern (`main-<sha>`, `sha-<sha>`, semver,
   `latest+digest`) — this becomes the Warehouse's `allowTags`.
3. Inventory the Argo CD Applications under
   `tesserix-k8s/argocd/prod/apps/<P>/` and add the
   `kargo.akuity.io/authorized-stage: kargo-<P>:prod` annotation +
   `helm.parameters.image.tag` placeholder to each.
4. Create `kargo-manifests/projects/<P>/{project,warehouses/services,stages/prod}.yaml`
   following the `mark8ly` shape. (mark8ly is the cleanest single-bundle
   reference; fanzone is the multi-service per-Argo-App reference.)
5. Add `external-secrets/prod/kargo-<P>/` to tesserix-k8s. Just a
   regex-scoped clone of the existing kargo-mark8ly file.
6. Push both repos. Watch:
   - `kubectl -n argocd get app kargo-project-<P>` → Synced/Healthy
   - `kubectl get project.kargo.akuity.io kargo-<P>` → Ready/True
   - `kubectl -n kargo-<P> get warehouse services` → Ready/True (after
     ~60 s)
   - `kubectl -n kargo-<P> get freight` → at least one entry
   - `kubectl -n kargo-<P> get promotion` → eventually Succeeded
7. From the Kargo UI (`https://kargo.tesserix.app`) verify the
   Project shows up and a Freight has been promoted.

If a step gets stuck, the log of `deploy/kargo-controller` (in the
`kargo` namespace, log level `INFO`) tells you exactly which CRD or
network call is failing.
