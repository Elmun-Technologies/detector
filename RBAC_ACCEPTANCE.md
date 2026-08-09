# RBAC acceptance checklist

This is a security release checklist, not a claim of completion. A category is checked only after every route is protected by Bearer identity, DB resource-to-workspace resolution and a role integration test.

- [x] JWT validation: missing/invalid/expired/issuer/audience HTTP tests.
- [x] Persisted video upload: editor membership before storage write.
- [x] Persisted analysis report/status, metrics and JSON/PDF export: resource-chain authorization.
- [x] Content plan/item and competitor read/write: role enforcement.
- [x] Payment checkout: owner-only; verified provider webhook idempotency.
- [x] Self-only persisted user deletion.
- [x] Legacy MVP analysis routes blocked in `ENVIRONMENT=production`.
- [ ] Workspace read/update/delete/settings/usage authorization.
- [ ] Membership and role-management HTTP routes with escalation prevention.
- [ ] Instagram OAuth/account/sync/disconnect routes with RBAC.
- [ ] Subscription/history/invoice read and payment administration routes.
- [ ] Retry/cancel/progress lifecycle routes.
- [ ] Data export and audit-log access policies.
- [ ] Complete endpoint inventory regression test.

## Policy

`viewer` reads; `editor` changes content/videos; `admin` manages workspace resources; `owner` alone manages members, roles, subscription and checkout. Unknown resources are `404`; known but unauthorized resources are `403`. Public provider webhooks never use Bearer auth, but must validate provider signature and resolve their target workspace server-side.
