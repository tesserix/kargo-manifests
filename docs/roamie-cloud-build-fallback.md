# Roamie Cloud Build fallback

The 2026-10-21 production release uses the existing GCP Artifact Registry
`global/roamie-api` repository because GitHub's billing limit prevented the
image-publishing jobs from starting. The existing registry credential also
lacks package write scope. No credential scopes or billing settings changed.

Cloud Build `8eb7e1af-71cb-48bd-9a41-55b494a6f0d1` built exact Roamie merge
commit `b1a346984e34c1b132342b7d5017c0b5fe43a258`, then passed the repository's
authenticated TLS/Postgres migration smoke test before publishing:

```
asia-south1-docker.pkg.dev/tesseracthub-480811/global/roamie-api@sha256:b131961779b37a1e7e734640c869a10a0eb4d9a648ef695d119a14e46c276e75
```

Trivy reported zero fixable High or Critical vulnerabilities. Kargo v1.11.1
does not populate platform metadata for a single-image manifest, so its
`linux/amd64` filter rejects that form. Wrap the tested image in an OCI index
before marking it deployable. For this release the verified index is:

```
sha256:071a35ab88a909f69a53a4fb2a6700a2a08a1c97d90251a9b701e189c73dffeb
```

`crane index append -m IMAGE@TESTED_DIGEST -t IMAGE:verified-index-SHA`
creates the index using the child's config for its platform. Inspect the
resulting manifest and assert that it contains exactly the tested digest
with platform `linux/amd64`, then add `deploy-<sha7>` to that index digest.
This preserves the tested binary and keeps platform filtering enabled.
Both ready production replicas use the index above; its only child is the
Cloud Build digest recorded earlier.

The Warehouse retains
the verified `deploy-<sha7>` tag filter and production auto-promotion. The
Stage updates repository, tag and digest together through Argo CD; both
the migration hook and API Deployment consume that same immutable image.

While this fallback is active, subsequent releases must publish and verify
images in `global/roamie-api` before adding a deploy tag. Normal GitHub
publishing alone will not promote an image here.

The existing Kargo controller and GKE node service accounts require
repository-level reader access to `global`. The approved bindings and
read-only planning/apply script are recorded in
[tesserix-k8s #1479](https://github.com/tesserix/tesserix-k8s/pull/1479).
No project-wide role or registry write permission was granted.

When GitHub image publishing works again, verify and warm the intended
GHCR mirror image, then change the Warehouse and Stage imageRepo together
back to `asia-south1-docker.pkg.dev/tesseracthub-480811/ghcr-remote/tesserix/roamie-api`
in a reviewed PR. Keep the repository override so Kargo changes all three
image fields together. Any production rollback needs its own explicit
approval and a verified image available in the selected repository.
