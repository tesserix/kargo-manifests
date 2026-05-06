# kargo-manifests

GitOps source of truth for the Kargo control plane running on
`tesseract-prod-in-gke`. This repo holds **Project**, **Warehouse**,
**Stage**, and **PromotionTask** resources for every product whose
release-promotion is automated by Kargo.

The Kargo platform itself (controller, API, Dex, RBAC) lives in
[`tesserix/tesserix-k8s`](https://github.com/tesserix/tesserix-k8s)
under `argocd/prod/infrastructure/kargo.yaml` and the
[`release` AppProject](https://github.com/tesserix/tesserix-k8s/blob/main/argocd/prod/projects/release.yaml).
This repo only contributes *what* gets promoted, not the platform that
runs it.

## Project status

| Project | State | Tag pattern | Strategy | Notes |
|---|---|---|---|---|
| `kargo-fanzone` | live, auto-promoting | `^main-[a-f0-9]{7,12}$` | `NewestBuild` | 23 services, multi-arch OCI images, `platform: linux/amd64` |
| `kargo-mark8ly` | live, auto-promoting | `^main-[a-f0-9]{7,12}$` | `NewestBuild` | 8 Apps from 7 image repos, single-arch Docker v2 manifests, no platform filter |
| `kargo-homechef` | live, auto-promoting | `^main-[a-f0-9]{7,12}$` | `NewestBuild` | 5 Apps (api + 4 portals), multi-arch OCI images, `platform: linux/amd64`. Shared `tesseract-nexus/global-services/auth-bff` image is out of scope here — it's used by DevAI too and will land under a separate `kargo-shared-services` Project. |
| `kargo-tesserix-blog` | live, auto-promoting | `^main-[a-f0-9]{7,12}$` | `NewestBuild` | 1 App (tesserix-blog Next.js), single-arch Docker v2 manifest, no `platform:` filter. MongoDB sidecar (`mongo:7.0`) deliberately not subscribed (third-party image, no CI). |

Phase 2 remaining: `gameverse` (Rust — needs runbook addendum),
`social`, `scrapper`, `stockpilot`, `devai`, `guardix`. The shared
`auth-bff` image used by HomeChef + DevAI also needs its own Project
(`kargo-shared-services`). Bookkeeping was removed from the cluster
on 2026-05-07 (not production-ready). Pattern is the same as
fanzone/mark8ly/homechef/tesserix-blog — see
[`docs/adding-a-project.md`](docs/adding-a-project.md) for the
runbook and [`docs/phase-1-retrospective.md`](docs/phase-1-retrospective.md)
for the gotchas to avoid.

## Layout

```
kargo-manifests/
├── projects/                   # one directory per Kargo Project
│   └── <product>/
│       ├── project.yaml        # Project resource (owns the kargo-<product> namespace)
│       ├── warehouses/         # Warehouse resources — what to watch (image, git)
│       │   └── *.yaml
│       └── stages/             # Stage resources — environments + promotion plumbing
│           └── *.yaml
├── templates/                  # reusable promotion logic
│   ├── promotion-tasks/        # PromotionTask (namespace-scoped) — referenced from a single project
│   └── cluster-promotion-tasks/  # ClusterPromotionTask — usable by any project
├── argocd/
│   └── kargo-projects-appset.yaml   # ApplicationSet — turns each projects/<name> into its own Argo CD Application
└── docs/
    └── adding-a-project.md
```

## How a deploy lands on the cluster

```
   ┌─ kargo-manifests/projects/<product>/   (this repo, you edit here)
   │
   │           git push
   ▼
   tesserix-k8s/argocd/prod/apps/release/kargo-manifests-appset.yaml
                                                       │
   ArgoCD ApplicationSet                                ▼
                                                  Argo CD Application: kargo-projects-<product>
                                                       │
                                                       │ syncs to
                                                       ▼
                                                  Kargo Project namespace: kargo-<product>
                                                       │
                                                       │ Kargo controller reconciles
                                                       ▼
                                                  Warehouses watch ghcr.io / git
                                                       │
                                                       │ on new artifact: Freight
                                                       ▼
                                                  Stage(dev) auto-promotes ──► Stage(staging) ──► Stage(prod)
                                                                                                       │
                                                                                                       ▼
                                                                                                  ArgoCD Application updated,
                                                                                                  GKE cluster reconciles
```

## Service accounts that need access

| Account | What it needs | Where credentials live |
|---|---|---|
| ArgoCD repo-server | **read** `tesserix/kargo-manifests` so it can render the manifests it syncs | `argocd-repository-tesserix-kargo-manifests` Secret in `argocd` ns (synced from GCP SM `prod-ghcr-token` like the existing `tesserix-new-k8s-repo` Secret) |
| Kargo controller | **read+write** the *application* repos referenced by Warehouses, when a PromotionTask of type `git-clear`, `git-overwrite`, `helm-update-image` etc. has to commit a tag bump back to git | per-Project Secret with annotation `kargo.akuity.io/cred-type: git`, label `kargo.akuity.io/cred-type: repository`, sourced from GCP Secret Manager via ESO |

This repo itself does **not** need Kargo write access — Kargo
controllers don't commit back here. They commit to the *target* repo
(usually `tesserix-k8s` or a service repo) where Argo CD Applications
read image tags.

## Conventions

- Every Project lands in a namespace called **`kargo-<product>`**
  (matches the `release` AppProject's destination wildcard
  `kargo-*` in `tesserix-k8s/argocd/prod/projects/release.yaml`).
- Project name == directory name == namespace suffix. No surprises.
- Every Warehouse and Stage has its own file under
  `projects/<product>/warehouses/` and `projects/<product>/stages/`
  respectively. Easier to diff than one huge YAML.
- Image-watch Warehouses pin the platform to `linux/amd64` and use
  `imageSelectionStrategy: NewestBuild` with an `allowTags` regex so a
  rogue `:latest` push doesn't trigger a promotion.
- All `targetRevision` references on this repo's ApplicationSet are
  pinned to `HEAD` (i.e. branch tip) — Kargo Projects are operational
  state, not versioned releases.

## Adding a project

See [`docs/adding-a-project.md`](docs/adding-a-project.md).

## CI / workflows

This repo doesn't (and shouldn't) build anything. Lint-only is fine.
A GitHub Actions workflow that runs `kubeconform` against the Kargo
CRDs is recommended but not yet configured.

## Secrets and licensing

No secrets are committed here. Kargo credential Secrets live in
GCP Secret Manager, are mirrored into the cluster by ExternalSecrets,
and are referenced from `kargo-manifests` only by name.

The `tesserix` org has limited GitHub Actions minutes for private
repos, so any workflow added here must follow the
[public→build→private cycle](https://github.com/tesserix/tesserix-k8s/blob/main/CLAUDE.md#publicprivate-repo-toggle-for-builds-must-follow)
documented in tesserix-k8s.
