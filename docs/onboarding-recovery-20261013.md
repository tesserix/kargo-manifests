# Onboarding recovery release — 2026-10-13

The user authorized admin merge bypass and production deployment. The four delivery
PRs were merged. Admin enforcement on tesserix-workflows was restored immediately
and its review requirements verified unchanged. The main application workflow
38368351404 was rejected before jobs started because GitHub account billing/spending
limits remain blocked; admin merge bypass cannot start those runners.

Recovery source: `ad0f3a5dbd4be1006db0db1988eb3cc976a88c42`, checked out cleanly from
merged main. Both Linux amd64 images use the shared digest-pinned Tesserix bases,
OCI source/revision labels, BuildKit provenance and SBOM attestations. They are
published to the existing GCP `global` registry through the active account, after
local quality, real-PostgreSQL tests, health smoke and blocking fixable HIGH/CRITICAL
image scans. This recovery has no GitHub OIDC image signature; no signature
verification policy is disabled. Normal reusable CI retains its signing gate.

Only this source commit selects `global` in the Kargo Stage. Every other Freight
explicitly restores the normal GHCR mirror repositories, as well as both tags.
The deploy branch is advanced manually only after both immutable recovery images
are available and their scans pass. Kargo performs the promotion and Argo performs
the deployment; no Deployment is imperatively patched and no database migration
or credential rotation is included. Both workloads retain two replicas.

Before advancing deploy, record the published digests and local evidence. Verify
Kargo promotion success, Argo Synced/Healthy, two ready replicas per workload and
the authenticated public UI. Prior API/web tag for recovery is
`8773c8e133d0435a9bf19e60c4ad5f0d8ad5d061` in the normal GHCR mirror; restoring it
requires the separately approved rollback procedure. Fix GitHub billing to restore
normal automatic builds and releases. The one-commit registry exception remains
usable for a deliberate re-promotion of this exact recovery artifact.

## Published artifact evidence

Both blocking Trivy scans completed successfully with no fixable HIGH/CRITICAL
findings. The readonly web-container `/healthz` smoke returned `ok`.

| Image | Published OCI index digest |
| --- | --- |
| `global/onboarding-api` | `sha256:57accf2143304e291da86d231948d646d29ee70a25b1bb3944e9ad4b59a70c7a` |
| `global/onboarding-web` | `sha256:95af126addcee79b63168a9dc96d290313661c11f13374822adf61ec1c84adf3` |

Remote manifest inspection confirmed Linux amd64 manifests and separate SPDX SBOM
and SLSA provenance attestation layers for both images. Kargo recovery configuration
PR46 passed its public CI and was merged before manually advancing `deploy` to the
source commit above. Initial discovery exposed a missing namespace-local Git
credential; GitOps PR1387 adds an ExternalSecret referencing the existing platform
credential with an exact match to the private onboarding source repository.

## Deployment and live verification

Kargo promotion `prod.01m4t6g1c12kxqtqppybwp1znd.dbac93f` succeeded. Stage `prod`
is Healthy/Ready with verified Freight `dbac93fd77ba776ee8c093c4de3142b93935065a`.
Argo application `onboarding-service` is Synced/Healthy. API and web each have
2/2 updated, available replicas; their running image IDs match the published
index digests above. GitOps PR1387 repository checks subsequently passed.

The authenticated public site at `https://onboard.tesserix.app` was reloaded and
checked against live data: YES HOSPITAL is active, its two members include the
synthetic test owner, and its creation audit event is visible. Dashboard,
organization directory, products, global audit and all organization tabs were
opened. Member-removal confirmation stayed disabled for incorrect text, enabled
for the exact identifier, and was cancelled without mutation. The Members view
was inspected at desktop and 390px mobile widths; mobile document width equals
viewport width and cards stack. Browser error logs were empty. No live members,
product grants, domains or identity providers were changed by the smoke test.

Normal GitHub Actions release jobs remain blocked by billing. This successful
recovery rollout does not claim a GitHub OIDC image signature or a successful
normal application CI run.
