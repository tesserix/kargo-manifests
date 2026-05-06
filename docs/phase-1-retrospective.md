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

### 10. `platform: linux/amd64` silently drops single-arch images
Kargo's image selector applies the `platform` constraint by reading
platform metadata **out of the manifest**. That works when the build
publishes a multi-arch OCI image index
(`application/vnd.oci.image.index.v1+json`) where each entry has a
`platform: { os, architecture }` block — but a single-arch
`application/vnd.docker.distribution.manifest.v2+json` manifest
**carries no platform metadata at all**; the OS/arch is determined by
the image *config blob*, not the manifest. The selector finds no
platform match in the manifest and silently `continue`s past the tag
(no error, no log, just `0 references discovered`).

This was the failure mode for mark8ly: every CI image is single-arch
linux/amd64 but published as a flat Docker v2 manifest. The
Warehouse listed tags fine, applied the regex fine, then `getImagesByTags`
quietly returned an empty list.

Fix: **drop the `platform:` line for single-arch images**.

```yaml
subscriptions:
  - image:
      repoURL: asia-south1-docker.pkg.dev/.../<svc>
      imageSelectionStrategy: Lexical
      allowTags: '^main-[a-f0-9]{7,12}$'
      # platform: linux/amd64    # <-- omit for single-arch builds
      discoveryLimit: 5
```

Keep the constraint for multi-arch OCI indexes (fanzone) — it picks
the right entry out of the index.

### 11. `NewestBuild` needs manifest-config fetches; budget accordingly
`imageSelectionStrategy: NewestBuild` ranks tags by their image's
`org.opencontainers.image.created` annotation, which lives in the
*config blob* — a separate registry call per tag in addition to the
manifest fetch. With cold GAR cache + many tags, you burn through
the upstream-fetch quota fast (see gotcha #8) and may end up with a
warehouse that can never complete its first scan.

`imageSelectionStrategy: Lexical` only sorts the tag strings — no
config fetch, no manifest config dependency, no cold-cache problem.
For SHA-based tags (`sha-<12hex>`, `main-<sha7>`) the lexical order
isn't strictly time-ordered, but in practice we promote *the latest
tag* (whichever sorted last), so it's fine for our use case.

Use NewestBuild when the *order* of tags matters (e.g. you want to
promote the most-recently-built image regardless of name). Use
Lexical when you just want "the matching tag" with minimal registry
chatter.

### 12. Don't run `bump-image-in-tesserix-k8s` from CI when Kargo is on
Some products (mark8ly, originally) had a CI job that committed image
tags directly to tesserix-k8s `charts/apps/<svc>/values.yaml`. Once a
Kargo Project is in front of those Apps, that job becomes:

- **Redundant** — Kargo writes `spec.source.helm.parameters.image.tag`
  on the Argo CD Application; helm parameters override values.yaml.
- **Inconsistent** — the bump-k8s job and the build job often compute
  short SHAs differently (12 chars vs 7), producing values.yaml
  references to tags that were never pushed.
- **Adversarial** — every CI commit churns tesserix-k8s with a value
  that Kargo will overwrite seconds later anyway.

Delete the bump-k8s job. Kargo + the GAR mirror are the deploy path
now.

### 14. Test the *new image* before declaring victory
Symptom: Kargo Promotion `Succeeded`, Argo CD App `Synced/Healthy`,
Stage `Healthy` — but the new pod is in `Init:RunContainerError` and
the rolling-update is stalled with the *old* replica still serving.

Cause we hit: the new `mark8ly-auth-bff:main-<sha>` image was built
without the `/migrate` init-container binary at the path the
Deployment expects. Kargo + Argo CD did their jobs; the image itself
was broken. Look at the failing pod's events:

```
Warning  Failed   ... Error: failed to create containerd task:
  ... exec: "/migrate": stat /migrate: no such file or directory
```

That's an upstream Dockerfile / build-stage bug, not a Kargo issue.
Fix in the application repo's Dockerfile. Kargo will auto-promote the
fix on the next CI build.

To temporarily pin to the previous (working) Freight while the
Dockerfile is fixed: in the Kargo UI, open the Project → Stage →
*Promote* a specific older Freight. Don't disable
`autoPromotionEnabled` globally — that just delays the next bad
image, it doesn't fix anything.

### 13. `app-of-apps` `selfHeal: true` reverts Kargo's helm.parameters
A parent Argo CD Application that syncs a directory of child
Applications (e.g. `fanzone-app-of-apps` reading
`argocd/prod/apps/fanzone/`) treats each child Application's
`spec.source.helm.parameters` as a managed field. When Kargo's
`argocd-update` step writes a new `image.tag` value, the parent
detects drift and self-heals it back to whatever the git copy says.
The result: Kargo says "promotion succeeded" but the actual deploy
is still pinned to the placeholder, and the Knative service stays
on the wrong tag (often a 404 if the placeholder was a fake SHA).

Fix: add `ignoreDifferences` + `RespectIgnoreDifferences=true` to the
parent app-of-apps so it doesn't fight Kargo on that path.

```yaml
spec:
  ignoreDifferences:
    - group: argoproj.io
      kind: Application
      jsonPointers:
        - /spec/source/helm/parameters
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - RespectIgnoreDifferences=true
```

Apply this to **every** product app-of-apps that has Kargo wiring.

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

### A. Discover the product's image facts (do these BEFORE writing any YAML)

1. **Image repos** — `gh package list --user tesserix --filter <P>` or
   `kubectl -n <P> get deploy,ksvc -o jsonpath='{range .items[*]}{.spec.template.spec.containers[0].image}{"\n"}{end}'`.
2. **Tag pattern** — what does CI emit? Look at `*-build.yml` /
   `ci.yml` in the application repo. Standard now is `main-<sha7-12>`.
3. **Manifest type** — single-arch Docker v2 or multi-arch OCI index?
   ```bash
   TOKEN=$(gcloud auth print-access-token)
   curl -sS -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.v2+json" \
     https://ghcr.io/v2/tesserix/<service>/manifests/<latest-tag> | jq .mediaType
   ```
   If it's `image.index.v1+json` → keep `platform: linux/amd64`.
   If it's `manifest.v2+json` → **omit** platform constraint (gotcha #10).

### B. Clean up the application's CI workflow (in the product repo, not tesserix-k8s)

4. **Drop `:latest` tag emission** — both from `metadata-action` and
   from any `Trivy`/scanning steps that reference `:latest`. Replace
   with `main-<sha>` from the metadata-action output.
5. **Remove any post-build `kubectl patch ksvc` / `kubectl rollout`
   step**. Kargo owns deploys; CI's job ends after image push.
6. **Remove any `bump-image-in-tesserix-k8s` job** (gotcha #12). Kargo
   writes `helm.parameters` directly — we don't want CI also
   committing values.yaml bumps in parallel.
7. **Pin the short-SHA length** — pick 7 or 12 chars and use it
   consistently for both the build tag AND any places the bump might
   reference. Mismatched 7/12 char shorts produced phantom values.yaml
   tags during onboarding.

### C. Update the Argo CD Apps in tesserix-k8s

8. For each Application under `argocd/prod/apps/<P>/*.yaml`:
   - Add annotation `kargo.akuity.io/authorized-stage: kargo-<P>:prod`.
   - Add `spec.source.helm.parameters` with at least
     `- name: image.tag, value: "<some-current-tag>"`. Doesn't matter
     what the value is — Kargo overwrites on first promotion. Just
     can't be empty or missing.
   - Don't put `image.tag: "latest"` here — combined with
     `pullPolicy: Always` it creates a race where every cold-start
     pulls a different digest, fighting Kargo (gotcha that bit fanzone).
9. The parent `<P>-app-of-apps.yaml` must add (gotcha #13):
   ```yaml
   ignoreDifferences:
     - group: argoproj.io
       kind: Application
       jsonPointers:
         - /spec/source/helm/parameters
   syncPolicy:
     syncOptions:
       - RespectIgnoreDifferences=true
   ```

### D. Create the Kargo Project in this repo

10. `cp -R docs/examples/sample-product projects/<P>` then edit:
    - `project.yaml`: replace `sample-product` with `kargo-<P>` in
      Namespace, Project, ProjectConfig — all three resource names.
      Keep the namespace label `kargo.akuity.io/project: "true"` exactly.
    - `warehouses/services.yaml`: one subscription per service. URLs
      point at `asia-south1-docker.pkg.dev/.../ghcr-remote/tesserix/<svc>`.
      Set `imageSelectionStrategy: Lexical`, `strictSemvers: false`,
      `interval: 300s`, `discoveryLimit: 5`. Drop `platform:` if
      step 3 said the manifests are single-arch.
    - `stages/prod.yaml`: one `argocd-update` step per Argo CD App in
      `tesserix-k8s/argocd/prod/apps/<P>/`. Use `imageFrom("...").Tag`
      with the GAR mirror URL exactly matching the Warehouse's repoURL.

### E. Add image creds (only if needed)

11. If you're watching GAR (recommended) and the kargo-controller GCP
    SA already has `roles/artifactregistry.reader` (it does after
    Phase 1), **skip this step entirely** — Workload Identity handles
    it cluster-wide. If you're watching GHCR directly, add an
    ExternalSecret at
    `tesserix-k8s/external-secrets/prod/kargo-<P>/externalsecret.yaml`
    sourcing `prod-ghcr-username`/`prod-ghcr-token` with regex
    `^ghcr\.io/tesserix/<P>-.*` and label
    `kargo.akuity.io/cred-type: image`.

### F. Push and validate

12. Push tesserix-k8s + kargo-manifests changes. Validate in this order:
    - `kubectl -n argocd get app kargo-project-<P>` → Synced/Healthy
    - `kubectl get project.kargo.akuity.io kargo-<P>` → Ready/True
    - `kubectl -n kargo-<P> get warehouse services` → Ready/True after
      one cycle (≤ 5 min). If `MissingImageReferences` persists, see
      gotchas #8, #10, #11.
    - `kubectl -n kargo-<P> get freight` → at least one entry within 5
      min. Each `images[]` entry in the Freight must have a non-empty
      `digest` (else the platform filter dropped it; see gotcha #10).
    - `kubectl -n kargo-<P> get promotion` → eventually Succeeded.
    - **Test the new image actually starts** (gotcha #14):
      `kubectl -n <P> get pods` — old + new replicas, new should
      reach Ready=1/1. If new is in `Init:RunContainerError` /
      `CrashLoopBackOff`, that's an upstream Dockerfile bug, not a
      Kargo issue. Roll back the Stage to a known-good Freight via
      the Kargo UI's Promote button while you fix the build.
13. Open the Kargo UI (https://kargo.tesserix.app) → verify the
    Project shows up, has a Warehouse / Stage / Freight / Promotion,
    and the Stage box is green.

If a step gets stuck, the log of `deploy/kargo-controller` (in the
`kargo` namespace, log level `INFO`) tells you exactly which CRD or
network call is failing. The 14 gotchas above cover everything we hit
during fanzone + mark8ly onboarding.

## Phase 1 verified end-to-end

| Project | First Freight | Outcome |
|---|---|---|
| `kargo-fanzone` | `joyous-chicken` (`main-b3b1fa8`) | Stage `Healthy=True, Verified` — 23/23 services running on per-service `main-<sha>` |
| `kargo-mark8ly` | `dangling-indri` (`main-03dff04` → `main-8ad1c6c`) | Auto-promotion working; latest CI image has an unrelated Dockerfile bug missing `/migrate` (gotcha #14 — old replica still serving) |

Auto-promotion proved with TWO independent CI pushes:
1. fanzone-battle-ground commit `b3b1fa8` → CI built → GAR cached →
   Kargo Warehouse polled → Freight `joyous-chicken` → auto-promote
   → 23 Argo CD Applications updated → Knative rolled.
2. mark8ly commit `8ad1c6c` → same flow, all 8 mark8ly Apps got the
   new tag. (Image is broken upstream, but Kargo's part worked.)

GHCR egress went to **0** for these two products — Kargo reads the
in-region GAR mirror via Workload Identity.
