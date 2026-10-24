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
