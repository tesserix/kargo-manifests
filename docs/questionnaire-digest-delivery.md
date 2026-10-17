# Questionnaire image delivery

The company and console promotions use `tag@digest` through regional GAR. This
preserves the CI commit tag for traceability while the container runtime resolves
the immutable digest. The platform API promotion contract is unchanged.

GAR remote repositories can temporarily cache a missing tag when it is requested
before upstream publication finishes. A tag may return 404 even while the exact
CI image is available by digest. Do not probe unpublished release tags, delete
images to clear the cache, or switch production pulls to GHCR.

For an authorised release recovery:

1. Require the source PR and release CI to pass, including both published images.
2. Verify each CI tag's digest in the upstream registry, then verify that exact
   digest through the regional GAR URI. Never substitute an unverified image.
3. Assemble a Kargo Freight with the normal Warehouse origin (`services`), image
   repository, original tag and verified digest. Preserve any other image in the
   current verified Freight. Record the CI run URL and recovery reason as annotations.
4. Server-dry-run the Freight before creation. Registering a verified Freight is
   Kargo's supported manual assembly path; it is not a manual container build/push.
5. Let the existing authorised `prod` Stage promote it through `argocd-update`.
   Verify both workloads Ready, their runtime digests, and public/private behavior.
6. The Warehouse's next successful discovery will converge to the same content
   once its tag cache refreshes. The digest pin remains part of normal promotions.

Release `0957aaea49b15bb6a48dec10cd484d4f2ab91bc2` passed CI run
https://github.com/tesserix/tesserix-home/actions/runs/39044852137. GAR verified:

- company: `sha256:9e95607c304de76fbcc40f8bdfa902f046bfe4708d4834bc42799cbcd914857c`
- console: `sha256:4659746aecbeb2e15f64787c58da81f951018ee6fc68c2dd0e7a559f199549e0`

No new registry credentials, IAM roles or public access are needed for this recovery.

## Stale Argo operation recovery

During this release, company had `operationState.phase: Running` from
`2026-10-17T14:39:15Z`, but no active `operation`; it was Healthy and Synced.
Argo's supported terminate-operation API confirmed "No operation is in progress".
That false status blocked Kargo until its first promotion timed out.

Before a status repair, verify the exact application, absence of an active operation,
Healthy/Synced state, and the stale attempt's start time. Save the old operation state
privately. Use resourceVersion, phase and start-time JSON patch tests to guard against
concurrent changes, then mark only the stale attempt Error with the recovery reason
and finish time. Do not change workload specs or interrupt a real running operation.
Use the active Kubernetes RBAC boundary; an isolated Argo CLI config avoids reusing an
expired saved OIDC session. No credential rotation is necessary.

A terminal Kargo promotion is not retried by a refresh annotation. Create a fresh
Promotion for the same verified Freight using the current Stage's complete promotion
template, after a server dry-run. Release recovery succeeded as
`prod.01m5596z4r7550kx1w7czz1zzb.cfd5898` for Freight
`cfd5898211efe036f314324fcc3a27d7a7c51b89`. Both company and console became
Healthy/Synced with two ready replicas and their verified GAR digest references.
The private local status audit is `/private/tmp/questionnaires-company-stale-operation.json`.
