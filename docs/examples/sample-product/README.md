# Example: `sample-product`

Reference layout for a single-service Kargo Project. Lives under
`docs/examples/` precisely so the `kargo-projects` ApplicationSet in
tesserix-k8s does **not** generate an Argo CD Application for it.

## Copy + adapt

```bash
cp -R docs/examples/sample-product projects/<your-product>
sed -i '' 's/sample-product/<your-product>/g' projects/<your-product>/**/*.yaml
sed -i '' 's/sample-service/<your-service>/g' projects/<your-product>/**/*.yaml
```

(Replace `<your-product>` and `<your-service>` with real names. On
GNU `sed`, drop the `''` after `-i`.)

## What this example illustrates

- **One Project** owning the `kargo-sample-product` namespace.
- **One Warehouse** (`sample-service`) watching
  `ghcr.io/tesserix/sample-service:main-<sha>` for new builds.
- **Three Stages** (`dev`, `staging`, `prod`) cascading dev → staging
  → prod, with `dev` and `staging` auto-promoting and `prod` waiting
  for a human.
- **Reuse of the cluster-wide PromotionTask**
  `bump-image-in-tesserix-k8s` (in `templates/cluster-promotion-tasks/`)
  rather than inlining the git-clone + yaml-update + push + argocd-update
  steps in every Stage.

## What this example does NOT cover

- **Verification gates** (`spec.verification.analysisTemplates`) — wire
  one up via an `AnalysisTemplate` resource when you've got a smoke
  test to run.
- **Multi-service projects** — add another file under `warehouses/`
  per service and reference each from the corresponding Stage.
- **Per-stage subscriptions to git Warehouses** — needed if a Stage
  has to follow a chart version, not just an image tag.
- **Project-scoped credential Secrets** — for repos Kargo writes
  back to, you need a Secret labeled `kargo.akuity.io/cred-type=git`
  in the Project namespace, materialised from GCP Secret Manager via
  ExternalSecrets. Skipped here to keep the example minimal.
