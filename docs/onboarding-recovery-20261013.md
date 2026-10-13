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
