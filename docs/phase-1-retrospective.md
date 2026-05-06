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

### 7. kargo-controller HTTP/2 + GHCR token endpoint timeout
The Kargo controller container periodically times out reaching
`https://ghcr.io/token?...` on this cluster, even though plain
`curl` from a sibling pod with the same SA in the same namespace
hits ghcr.io in 0.3s. Symptom in the Warehouse status:
`dial tcp 20.207.73.86:443: i/o timeout`.

Workaround: disable Go's HTTP/2 client in the controller deployment.

```bash
kubectl -n kargo set env deploy/kargo-controller GODEBUG=http2client=0
```

(Add to a Helm-values overlay later so it survives upstream chart
upgrades. Open issue: figure out the root cause — likely an HTTP/2
connection-reuse interaction between go-containerregistry and
Cloud NAT keepalives.)

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
