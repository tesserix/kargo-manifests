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
├── project.yaml                # Project + Roles + RoleBindings + per-project secrets references
├── warehouses/
│   ├── <service-a>.yaml        # one Warehouse per artifact source
│   └── <service-b>.yaml
└── stages/
    ├── dev.yaml                # Stage(dev) — auto-promotion enabled, watches the warehouses
    ├── staging.yaml            # Stage(staging) — promoted from dev, manual approval
    └── prod.yaml               # Stage(prod) — promoted from staging, hard manual gate
```

## Step-by-step

### 1. Pick a name

`<product>` should be lower-kebab-case and match the product's
existing tesserix-k8s convention (e.g. `homechef`, `mark8ly`,
`devai`, `gameverse`). The Kargo namespace will be
`kargo-<product>` — that name flows from here into the AppProject's
destination wildcard (`kargo-*`) and into Argo CD's generated
Application name (`kargo-project-<product>`).

### 2. Create the directory

```bash
mkdir -p projects/<product>/{warehouses,stages}
```

### 3. Write `project.yaml`

Minimal template:

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: Project
metadata:
  name: <product>
spec:
  promotionPolicies: []   # optional auto-promotion policies, see Stage docs
```

You can also drop additional resources into the same file separated
by `---` — typical adds are project-scoped Roles for service-specific
RBAC, or `Secret`s with the `kargo.akuity.io/cred-type` label for
git/image-pull credentials (those should be sourced from GCP Secret
Manager via ExternalSecrets — never committed in plaintext).

### 4. Define each Warehouse

One Warehouse per upstream artifact source. Most apps need:

- **One image Warehouse** per service binary, watching `ghcr.io/tesserix/<service>` for new `main-<sha>` tags.
- **One git Warehouse** if Stage promotion bumps a chart's `values.yaml` / Kustomize overlay (most do, since Argo CD on the GKE side renders from git).

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: Warehouse
metadata:
  name: <service>
spec:
  freightCreationPolicy: Automatic
  interval: 60s
  subscriptions:
    - image:
        repoURL: ghcr.io/tesserix/<service>
        imageSelectionStrategy: NewestBuild
        # only main-<sha7-8> tags trigger promotion; ignores :latest,
        # release tags, semver, etc.
        allowTags: '^main-[a-f0-9]{7,8}$'
        platform: linux/amd64
        discoveryLimit: 20
```

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
    - origin: { kind: Warehouse, name: <service> }
      sources: { direct: true }
  promotionTemplate:
    spec:
      vars:
        - name: imageRepo
          value: ghcr.io/tesserix/<service>
      steps:
        - uses: git-clone
          config:
            repoURL: https://github.com/tesserix/tesserix-k8s.git
            checkout:
              - branch: main
                path: ./out
        - uses: yaml-update
          config:
            path: ./out/charts/apps/<service>/values-prod.yaml
            updates:
              - key: image.tag
                value: ${{ imageFrom(vars.imageRepo).Tag }}
        - uses: git-commit
          config:
            path: ./out
            message: 'chore(<service>): bump dev image to ${{ imageFrom(vars.imageRepo).Tag }}'
        - uses: git-push
          config: { path: ./out }
        - uses: argocd-update
          config:
            apps:
              - name: <service>
                sources:
                  - repoURL: https://github.com/tesserix/tesserix-k8s.git
                    desiredRevision: ${{ outputs['git-commit'].commit }}
```

Then `staging.yaml` and `prod.yaml` look identical except:
- `requestedFreight[].sources.direct: false` and instead
  `requestedFreight[].sources.stages: [dev]` (or `[staging]` for prod).
- The `git-clone` checkout path / Argo CD app name changes per env.
- `prod.yaml` adds an approval gate: `verification` block, or simply no
  `Stage`-level auto-promotion policy (controlled at the Project level).

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
