# GrowthBook platform-tool upgrades

The `growthbook` Warehouse and `growthbook-prod` Stage belong to `kargo-infra`.
They share the platform's GitOps promotion mechanism but do not bundle unrelated
tool upgrades. Automatic promotion prepares a PR; it does not bypass protected
main or silently approve a database migration.

Discovery is limited to stable three-part Docker tags in `>=5.2.0 <5.3.0` for
linux/amd64. Newer minor/major releases require a reviewed range change with
vendor compatibility and recovery evidence. Each Freight pins a version/digest
pair. The Stage updates the effective production Helm values, matching chart
defaults and appVersion in `tesserix/tesserix-k8s`, then opens a generated-branch
PR. A no-op retry skips proposal creation. After merge it waits for the exact
Argo revision and GrowthBook sync/operation/health.

Before merging a generated proposal, verify the image release/provenance,
Mongo/SDK compatibility, recoverable backup, preserved existing feature data and
project/environment isolation. Pinning alone does not prove SDK acceptance.
Do not widen the version range or merge an irreversible migration without its
reviewed recovery plan. The shared MongoDB image and provider users/features are
not modified by this Stage.

Initial activation depends on the digest-aware GrowthBook chart change being
merged first. Otherwise `image.digest` would not affect rendered workloads.
The owning PR must verify that prerequisite before enabling this promotion lane.

Validation: `uv run --with pyyaml python -m unittest discover -s tests -v`, plus
repository YAML/schema CI. Live verification must record the Warehouse Freight,
generated PR, merged revision, effective workload digest and Argo health. Do not
store credentials, SDK payloads or provider backups in this public repository.
