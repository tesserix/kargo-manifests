# Adding a Kargo Project

Use this runbook when you're onboarding a new product (or a new
service inside an existing product) into Kargo-driven promotions.

## Vocabulary, in 30 seconds

| Concept | What it is |
|---|---|
| **Project** | Kargo's ownership unit. Lives in namespace `kargo-<name>`. Holds Warehouses + Stages + roles. |
| **Warehouse** | A subscription. Watches a container image tag pattern (or a git revision range, chart version) and emits new `Freight` whenever something matches. |
| **Freight** | An immutable bag of artifact references — a specific image digest, git commit, etc. The thing that moves through stages. |
| **Stage** | An environment (dev, staging, prod). Has a list of Warehouses it accepts Freight from, an optional approval policy, and the **PromotionTask sequence** that materializes the Freight. |
| **PromotionTask** | A reusable recipe — typically *clone a target git repo, bump the image tag, push, wait for Argo CD to sync*. |

## File layout per project

```
projects/<product>/
├── project.yaml                # Namespace + Project + ProjectConfig
├── warehouses/
│   └── services.yaml           # one Warehouse, one image subscription per service
└── stages/
    └── prod.yaml               # Stage(prod) — auto-promotes from the bundled Warehouse
```

For multi-env cascading (dev → staging → prod), the
[`docs/examples/sample-product/`](examples/sample-product/) tree
shows the layout. We deliberately use only `prod` in Phase 1 — single
env per cluster.

## Step-by-step

> **Read this first:** [`phase-1-retrospective.md`](phase-1-retrospective.md)
> — 13 gotchas we burned through onboarding fanzone + mark8ly. Especially
> #3 (label value), #8 (GAR upstream quota), #10 (single-arch platform
> filter), #11 (Lexical vs NewestBuild), #13 (parent app-of-apps must
> ignore helm.parameters).

### 1. Pick a name

`<product>` should be lower-kebab-case and match the product's
existing tesserix-k8s convention (e.g. `homechef`, `mark8ly`,
`devai`, `gameverse`). The Kargo namespace will be
`kargo-<product>` — that name flows from here into the AppProject's
destination wildcard (`kargo-*`) and into Argo CD's generated
Application name (`kargo-project-<product>`).

The Kargo Project resource itself is named **`kargo-<product>`**
(matches the namespace; Kargo enforces this). The
`kargo.akuity.io/authorized-stage` annotation on each Argo CD App is
therefore `kargo-<product>:prod`.

### 2. Create the directory

```bash
mkdir -p projects/<product>/{warehouses,stages}
```

### 3. Write `project.yaml`

Template (Kargo 1.9 — Project + ProjectConfig + Namespace):

```yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: kargo-<product>
  labels:
    kargo.akuity.io/project: "true"   # MUST be the literal "true", not the project name
---
apiVersion: kargo.akuity.io/v1alpha1
kind: Project
metadata:
  name: kargo-<product>               # MUST equal the namespace name
---
apiVersion: kargo.akuity.io/v1alpha1
kind: ProjectConfig
metadata:
  name: kargo-<product>
  namespace: kargo-<product>
spec:
  promotionPolicies:
    - stage: prod
      autoPromotionEnabled: true       # latest Freight auto-promotes onto prod
```

> Notes:
> - **`Project.spec` doesn't exist in 1.9.** Promotion policies moved to `ProjectConfig`.
> - **`Project.metadata.name` MUST equal the namespace name.** Kargo's webhook rejects mismatch.
> - **Namespace label value is literally `"true"`**, not the project name.

Image-credential Secrets and project-scoped Roles can live in the
same file separated by `---`. Image creds aren't usually needed —
the kargo-controller's GCP SA + Workload Identity gets the GAR mirror
read access cluster-wide.

### 4. Define a single Warehouse with one subscription per service

Use **one** Warehouse with N image subscriptions (cleaner than N
warehouses). Each subscription corresponds to a service binary.

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: Warehouse
metadata:
  name: services
spec:
  freightCreationPolicy: Automatic
  interval: 300s              # 5min — kind to GAR upstream-fetch quota (gotcha #8)
  subscriptions:
    - image:
        repoURL: asia-south1-docker.pkg.dev/tesseracthub-480811/ghcr-remote/tesserix/<service>
        imageSelectionStrategy: Lexical    # see note below
        allowTagsRegexes:  # main-<sha7-12> from CI
          - '^main-[a-f0-9]{7,12}$'
        strictSemvers: false                # tags aren't semver — required (gotcha)
        # platform: linux/amd64             # ONLY for multi-arch OCI indexes — gotcha #10
        discoveryLimit: 5                   # newest 5 tags is plenty
```

**Strategy choice:**
- **`Lexical`** for SHA-based tags (`main-<sha>`, `sha-<sha>`). No
  manifest-config fetch per tag, lighter on quota, "just works" with
  any single-arch or multi-arch image. **Default for new projects.**
- **`NewestBuild`** when you want strict newest-by-build-time and
  your build pushes multi-arch OCI index manifests. Costs an extra
  config-blob fetch per tag — see retrospective #11.

**Platform filter:**
- Multi-arch OCI image index (e.g. `docker buildx build --platform linux/amd64,linux/arm64`)
  → keep `platform: linux/amd64`.
- Single-arch Docker v2 manifest (typical buildx-action default for
  one platform) → **omit** `platform:` entirely. Otherwise Kargo
  silently filters every tag out and you get `MissingImageReferences`
  with no errors logged (gotcha #10).

**Quick test:**
```bash
TOKEN=$(gcloud auth print-access-token)
curl -sS -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.v2+json" \
  https://ghcr.io/v2/tesserix/<service>/manifests/main-<sha7> \
  | jq .mediaType
```
- `application/vnd.oci.image.index.v1+json` → multi-arch, keep platform
- `application/vnd.docker.distribution.manifest.v2+json` → single-arch, drop platform

### 5. Define Stages

Stages cascade. The first stage (typically `dev`) has
`requestedFreight[].sources.direct: true` so it pulls straight from
the Warehouse. Later stages reference the previous stage:

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: Stage
metadata:
  name: dev
spec:
  requestedFreight:
    - origin: { kind: Warehouse, name: services }
      sources: { direct: true }
  promotionTemplate:
    spec:
      vars:
        - name: argocdRepo
          value: https://github.com/tesserix/tesserix-k8s.git
      steps:
        # one block per service — Kargo writes spec.source.helm.parameters.image.tag
        # on each Argo CD Application directly. No git commits needed.
        - uses: argocd-update
          config:
            apps:
              - name: <service>
                namespace: argocd
                sources:
                  - repoURL: ${{ vars.argocdRepo }}
                    helm:
                      images:
                        - key: image.tag
                          value: ${{ imageFrom("asia-south1-docker.pkg.dev/tesseracthub-480811/ghcr-remote/tesserix/<service>").Tag }}
        # repeat for every service in the project ...
```

> **Phase 1 only ships a `prod` Stage.** Multi-stage cascading
> (dev → staging → prod) is documented in
> [`docs/examples/sample-product/`](examples/sample-product/) but
> isn't yet used in this cluster — there's only one env.

> **Don't write to git.** Kargo's `argocd-update` step writes
> `spec.source.helm.parameters.image.tag` on the Argo CD Application
> directly. We deliberately avoid the git-clone / yaml-update /
> git-commit / git-push chain because:
>
> - Every promotion would churn tesserix-k8s (one commit per service ×
>   N services × every CI build), making the history unreadable.
> - The CI auto-bump-k8s job that some products had was duplicating
>   exactly this work and producing inconsistent state (12 vs 7 char
>   short SHAs — see retrospective #12).
> - helm.parameters override values.yaml, so the parameter write is
>   the source of truth at deploy time.
>
> The only adjustment needed in tesserix-k8s for each Argo CD App:
>
> 1. `metadata.annotations.kargo.akuity.io/authorized-stage:
>    kargo-<product>:prod`
> 2. `spec.source.helm.parameters` block with at least
>    `name: image.tag, value: "<some-current-tag>"` so Helm has a
>    parameter to overwrite.
> 3. Parent `<product>-app-of-apps.yaml` gets an `ignoreDifferences`
>    block on `/spec/source/helm/parameters` so it doesn't self-heal
>    Kargo's writes (gotcha #13).

### 6. Verify locally

```bash
yamllint -c .yamllint.yaml projects/<product>/
kubeconform -ignore-missing-schemas \
  -schema-location default \
  -schema-location .crds/kargo-crds.yaml \
  projects/<product>/**/*.yaml
```

(Both run automatically in CI on push.)

### 7. Push

```bash
git checkout -b feat/kargo-<product>
git add projects/<product>/
git commit -m "feat(<product>): onboard kargo project"
git push -u origin feat/kargo-<product>
gh pr create --fill
```

When the PR merges to `main`, Argo CD's `kargo-projects`
ApplicationSet (in `tesserix-k8s/argocd/prod/apps/release/`)
generates a new Application called `kargo-project-<product>` and
syncs the `kargo-<product>` namespace. Within ~60 s the Warehouses
discover the latest matching image and the `dev` Stage produces its
first promotion.

### 8. Watch it land

```bash
export KUBECONFIG=~/.kube/gke-prod
kubectl -n kargo-<product> get warehouse,stage,freight,promotion
argocd app get kargo-project-<product>
```

In the Kargo UI at https://kargo.tesserix.app, your project shows
up under **Projects**; click in for the freight graph.

## Cleanup

Removing a project from the cluster is **deliberately destructive**:
delete the `projects/<product>/` directory, commit, push to `main`.
Argo CD's ApplicationSet sees the directory is gone, deletes the
`kargo-project-<product>` Application; the Application's
`resources-finalizer.argocd.argoproj.io` finalizer cascade-deletes the
Kargo Project, all its Warehouses, Stages, Freight, Promotions, and
finally the `kargo-<product>` namespace.

If you need to keep the historical Freight/Promotion data, dump it
first:

```bash
kubectl -n kargo-<product> get freight -o yaml > /tmp/<product>-freight-archive.yaml
kubectl -n kargo-<product> get promotions -o yaml > /tmp/<product>-promo-archive.yaml
```

…and stash somewhere durable before merging the deletion PR.
