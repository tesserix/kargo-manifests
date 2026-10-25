# Helivanta production promotion hold

Production automatic promotion is disabled while the pending India-only
migrations are reviewed. Source merges may publish images and advance the deploy
branch, but must not automatically run these migrations against production.
The already deployed UI → Global API → product API path remains live.

Read-only preflight on 2026-10-24 found 15 incompatible rows across eight tables:
country policy (1), pharmacy outlets (1), catalogue products (1), supply parties
(3), addresses (1), tax registrations (1), premises (2), and licences (5).
No records were changed. The documented helivanta_system preflight role lacks
SELECT on the policy table; counts were verified in a read-only transaction by
the authenticated PostgreSQL administrator on the primary. A restricted-role
zero count must never be treated as proof that the environment is clear.

The data owners must classify these records and approve any export, retention or
cleanup separately. Do not delete or relabel them to make deployment pass, bypass
the migration guard, or lower test/security gates. Follow the source repository's
`docs/deployment/remove-pakistan-release.md` and retention policy. Before promotion,
require an approved data plan, a fresh complete preflight, verified recovery
coverage and passing source CI. A manual production promotion also requires that
review; disabling automatic promotion is not permission to bypass it manually.

The Stage requests product API, Global API and shell updates from the same
reviewed commit in order. The API owns the migration hook. Promotion success and
Argo synchronization alone do not prove all updated replicas are healthy; verify
the migration hook and final readiness of all three workloads before accepting
the release. The Global API uses the backend image's independent
`/app/global-api` executable. It has no database migration of its own.

Restore automatic promotion only in a reviewed change removing this hold and
updating its regression test after the data review is complete. This hold adds no
workloads or capacity and does not roll back the running application.

## Reviewed manual release — 2026-10-25

The user explicitly requested removal of confirmed Pakistan test fixtures while
continuing India development. Root TEST codes, fictional policy-review evidence
and dependency inspection supported classification. The reviewable source is
[tesserix/helivanta#1319](https://github.com/tesserix/helivanta/pull/1319).
The protected recovery capture was restored into isolated PostgreSQL, including
the preserved India corporate parent. Rollback and commit rehearsals passed;
exact-snapshot guards reject drift. The full application migration binary also
passed against the restored schema and production migration ledger after cleanup.

The approved production transaction removed exactly 97 scoped test rows behind
the original 15 blockers and wrote 97 explicit cleanup audit entries. All 12
India preflight counts are now zero. FK definitions, trigger states and RLS flags
match the pre-operation snapshot; the pharmacy organization and India corporate
parent remain unchanged. Historical audits and stored objects were not removed.

The source release is `30efb51d17986a1f77136129a056ae3f833d82d4`
([PR #1318](https://github.com/tesserix/helivanta/pull/1318)); its full source PR
CI passed and the merged images were scanned, signed and published. The selected
Freight is `62a8796e936a36e1ed7fccc4d9ef78f8adac4740`; the explicit manual Promotion
is `prod.01m5q2p0v04mgak4qv9ysce8wg.62a8796`. Its production migration hook reports
`migrations applied`. Check final replica readiness and public routing separately
from Promotion/Synced status; those statuses alone are insufficient acceptance.
MediConnect owner configuration follows in
[tesserix/tesserix-k8s#1525](https://github.com/tesserix/tesserix-k8s/pull/1525).

Automatic promotion remains disabled. The original data blocker is resolved,
but this note authorizes no other freight and does not change the project's
promotion policy. A future automatic-promotion change still needs its own reviewed
source and updated regression test.


## MediConnect registrar release — 2026-10-25

The accessibility release in
[tesserix/helivanta#1320](https://github.com/tesserix/helivanta/pull/1320)
was separately promoted and verified before registrar development. The hospital
registrar identity-review flow is in
[#1321](https://github.com/tesserix/helivanta/pull/1321); the follow-up
[#1322](https://github.com/tesserix/helivanta/pull/1322) fixes withdrawals handled
by older writers during a rolling upgrade. The initial registrar Freight was
intentionally skipped after a red regression reproduced stale review state.

The corrected deployed source is `cccd5ffa47e70983bd9b23dc09e3794185447cf7`.
Its source tree exactly matches the tested PR. All PR checks passed, including
Go coverage, web and browser E2E, image scans and secret checks. The complete local
backend race/coverage gate also passed. Real PostgreSQL/NATS and Global API HTTP
integration tests cover hospital/tenant isolation, revoked registrar grants,
self-review denial, stale registration, immutable decisions, outbox/audit failures,
duplicate and reordered delivery, rolling-upgrade withdrawal recovery, and the
absence of new consent or clinical grants.

Approved manual Freight: `37e974537cab0831011da3a3f01b842f348678bb`.
Promotion: `prod.01m5qa01czxa72d3vqt84eenm4.37e9745` (Succeeded).
The API migration job completed; read-only production inspection confirmed
`0004_mediconnect`, `0005_mediconnect`, `0005_patientmaster`, and enabled/forced
RLS on both new review tables. Migration and repeat-application rehearsals used
production schema only, with synthetic local accounts and no copied patient data.

Final Argo state is Synced/Healthy for API, Global API and shell, with 2/2 ready
replicas each. Running digests match the published corrected source:

- API and Global API:
  `sha256:cbbe0fcafd9913eb95e397fa9fd952c84ff4d392e01fbaa39744decf0432a7f6`.
- Shell:
  `sha256:90be35181568e9802d498864d3e90b7a432f3a1a9fc74609b390b2d9e68d312b`.

Live probes of all nine MediConnect and three registrar routes returned 401 with
Global API Via headers for unauthenticated requests carrying forged identity
headers. The IAM probe also returned 401, an unknown product returned 404, and
login returned 200. From the shell, direct product API access returned mesh 403;
Global API access reached the expected 401 authentication gate. These are live
boundary/readiness checks, not a claim of authenticated clinical testing in
production; the positive approval/rejection journeys ran against isolated real
services locally and in CI.

The selected policy is independent hospital registrar evidence review. Patient
and proxy consent remains separate, and identity verification never grants
clinical access. Evidence references and reviewer identity remain in patientmaster;
MediConnect owns only the request and scoped identity-review projection. The
result consumer can read its original request but cannot modify it. Projection
repair on reads/retries/result delivery preserves prior withdrawal and emits one
missing cancellation atomically; it is not a background sweep.

Automatic promotion remains **false**, and `tesserix/helivanta` remains **public**.
Do not roll back to older review readers/writers while submissions exist without
a coordinated write hold and reconciliation. Retain migration and audit history.
Issues #37 and #552 remain open because consent/proxy authority, clinical disclosure
and broader portal scope are still separate work. Protected local rehearsal and
verification evidence is under
`~/.local/state/helivanta/mediconnect-registrar-review-20261025`.

## MediConnect account-consent release — 2026-10-25

[Helivanta #1323](https://github.com/tesserix/helivanta/pull/1323) adds eight
Global API-routed endpoints for tenant-reviewed notice publication/read/list/
retirement and subject-owned consent acceptance/read/list/withdrawal. The source
is `c722210b52de329d51097ae7a759175b0ccedf0b`; its tree exactly matches the tested
PR head `e9d0e10231346754a247c3348692e8746c2459cb`.

Full local backend race/coverage and all PR CI checks passed, including real
PostgreSQL/NATS and Global API HTTP journeys, production-role grants, concurrent
acceptance/withdrawal, terminal replay, tenant/peer/admin denial, immutable notice
content, retirement/stale hashes, and audit/outbox rollback. MediConnect coverage
is 83.2%. The initial PR Go attempt failed installing the linter due to a
checksum-service TLS timeout; the retry passed without bypassing checks.

Migration `0006_mediconnect` was rehearsed with a schema-only production copy
and 100 existing migration identifiers, plus synthetic data. Repeat migration
and previous-migrator compatibility passed. No patient data was copied. A
100k synthetic receipt query used the scoped page index under app-role forced
RLS (4 buffer hits, 0.139ms for that sample); this is not load/SLO certification.

Approved exact Freight: `d4fc0515577a95d79d5a9b7b832fa38ff8b1c290`.
Published OCI revision labels match the source, and the image pipeline passed
builds, scans, signing and deploy-branch publication. Expected digests:

- API and Global API:
  `sha256:8ae80f29dd059c85868c0336c5791fdc4dae4c6468fd80d34e0fe0206fb44081`.
- Shell:
  `sha256:d8374efe9abdcea2ccc9d6285d72e9fc59b6caf58bf6d3f73896515fbf93518c`.

No production legal text, notice or receipt is seeded. Account purposes remain
optional; receipts are declarations, not clinical/proxy authority, eligibility
proof or permission to start processing. Registrar identity approval remains
separate. Valkey remains the platform cache; PostgreSQL is the receipt authority.

The migration is additive with retained audit/history and no destructive down
migration. Previous binaries omit the new routes. Any future processing consumer
must fail closed without current consent, notice and eligibility checks.
Automatic promotion remains false and the source repository remains public.
#37, #552 and #556 remain open: clinical/proxy authority and expiry, reviewed
policy/content, rights/officer workflow and owner-authorized clinical disclosure
are separate work. UI/mobile and OTP remain excluded from the API-only scope.
Protected rehearsal and verification evidence is stored at
`~/.local/state/helivanta/mediconnect-consent-20261025`.

Release verification passed: promotion
`prod.01m5rb10yyxnwyvv83m34hp077.d4fc051` succeeded, the migration completed,
and API/Global API/shell are each 2/2 with exact expected live image digests and
Argo Synced/Healthy. Both new tables have forced RLS, owner `helivanta`, and
verified `hms_app` SELECT/INSERT/UPDATE privileges. All post-merge CI checks
passed before promotion. The 21 unauthenticated route probes returned 401 through
Global API with no-store responses; unknown product returned 404 and login 200.
From the shell workload, direct owner access returned mesh 403 and Global API
returned authentication 401. These are production boundary probes; authenticated
functional/negative journeys ran locally and in CI with synthetic data.

## Privacy casework release — 2026-10-25

[Helivanta #1324](https://github.com/tesserix/helivanta/pull/1324) adds ten
Global API-routed endpoints for tenant-local officer nomination, acceptance,
revocation and subject-owned privacy case intake, conversation and review.
Source `87ef85ae4d230acc14773eb70877ff457208bb39` exactly matches the tested
PR head `8746498c908b6830893d80fd4943c91a7a744ebf` tree.

Full local backend race/coverage, build, vet, lint, contract checks and all PR
CI checks passed. Privacy coverage is 83.1%. Tests use real PostgreSQL/NATS,
owner/runtime database roles and Global API HTTP requests: peer/tenant/admin
isolation, officer expiry/replacement/revocation, stale nominations and versions,
concurrent retries, immutable command history and audit rollback. The final
local regression log is `/tmp/privacy-full-regression-final.log`.

Migration `0001_privacy` was rehearsed on a schema-only production copy with
101 existing migration identifiers and synthetic data. Apply/repeat and previous
migrator compatibility passed. All three new tables use forced RLS. The 100k-case
synthetic query rehearsal used scoped subject/queue indexes; its 0.546ms/0.204ms
samples are not load or SLO certification. No production patient data was copied.

Exact Freight: `98694b2ada3f9ff524774f08177862314ec5f63e`.
Published image OCI revision labels match source:

- API and Global API:
  `sha256:84b7c8d1b6c88451d6d93cc9ca51d1d8c79aa35dfb544806cc3fff000eb25432`.
- Shell:
  `sha256:ad0ec103267781695b6fa534b6037d64d0eefa742870cb6a953e4fa3d824ff15`.

This release does not seed production officers or policies. Admin appointment
management grants no case-read authority; nominees must accept from their own
verified session. Officer self-adjudication is forbidden. Case `responded` means
a recorded response, not completed correction, erasure or clinical disclosure.
PostgreSQL remains authoritative; Valkey remains the shared cache.

No deadline worker or policy extension is included. #66 remains assigned to
Sam123ben and open for durable deadlines, escalation, wider intake and provider
notifications. Clinical/proxy authority, owner-authorized record release and
booking/reminder integrations remain outstanding; #37/#552/#556 remain open.
No clinical/legal readiness or approved notice content is implied. Automatic
promotion remains false and the source repository remains public. The migration
is additive and forward-only; rollback retains case/audit history.

Protected evidence: `~/.local/state/helivanta/privacy-casework-20261025`.
Main CI run `40154103399` passed, including backend race/coverage, web, e2e,
scripts and secret scan. Promotion
`prod.01m5renm8z8qqk9z1x1g11nvtn.98694b2` succeeded. All three workloads
returned to 2/2 on the exact published digests and Argo Synced/Healthy.
Migration `0001_privacy` is applied; the table owner, runtime grants and FORCE
RLS were verified against live metadata. All 31 protected HTTP route probes
returned 401 through Global API with `no-store`; login returned 200 and unknown
product 404. Shell-to-owner mesh access returned 403 and shell-to-Global API
reached the 401 authentication gate. These production probes validate release
and authentication boundaries; authenticated case transitions were tested in
isolated local/CI databases, not by inserting production test cases.
