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

The Stage now promotes product API, Global API and shell from the same reviewed
commit in order. The API migration hook and health check must complete before the
connector and shell advance. The Global API uses the backend image's independent
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
