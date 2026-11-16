# campusMate architecture hardening implementation plan

> For agentic workers: use superpowers:executing-plans to implement task by task, with one final independent review. User approved execution of the in-chat P0–P4 plan on 2026-10-28.

**Goal:** make failures diagnosable, authentication recovery coordinated, UI state reliable, and Windows installation independent of a developer environment.

**Architecture:** keep the existing local FastAPI modular monolith, native ES-module frontend, shared authentication and official Harness integration. Extend the established error/runtime, account-revision, view-cache and lifecycle contracts. Ship a Windows Electron host with a fixed bundled backend runtime.

**Tech stack:** Python 3.12, FastAPI, SQLite, Windows DPAPI, JavaScript ES Modules, official DeepSeek Harness SDK, Electron.

**Spec:** the user-approved in-chat P0–P4 plan, restated in the tasks and constraints below.

## Global constraints

- Work in the launcher's daily checkout; preserve all pre-existing changes and `.private` data. Source-only starting snapshot is `.codex/architecture-hardening-20261028/before/`.
- Keep all work local and uncommitted until the user asks for a grouped commit or publication. No automatic push/PR/merge.
- Preserve module API v1 and existing response fields; introduce additive fields and compatible projections.
- Never log credentials, source bodies, user prompts, cookies, private URLs or account identifiers in diagnostics.
- Authentication tests and model tests use synthetic fixtures. Actual verification/OTP remains with the user.
- UI work preserves all four themes and the existing documented module lifecycle.
- Windows release program files are read-only; private data and runtime state live in a writable user location. No credentials bundled in release assets.
- Complete checks and normal restart of the daily 16666 instance at integration, using its existing environment.

## Review focus

- Concurrent module reads encounter expiry while another login or account switch is in flight.
- A successful status request must not overwrite a failed source synchronization state.
- Page disposal, theme changes, repeated clicks or a late response must not revive stale account UI.
- A bundled build runs with no developer PATH, a read-only program folder, and a Chinese/space-containing user path.
- Upgrade failure leaves original data and the previous runnable installation intact.

## Task P0: baseline and reproducible evidence

- [x] Identify daily checkout from shortcut and launcher record; preserve source snapshot; create `codex/architecture-hardening` branch in place.
- [ ] Run `check.ps1`; classify any pre-existing failures before editing production code.
- [ ] Reuse the fixed synthetic startup/interaction fixtures and retain all timing samples; compare final implementation under the same environment.
- [ ] Audit that new behavioral checks run as behavior checks, not only syntax checks.

## Task P1: correlated diagnostics and source outcomes

Files: `backend/core/errors.py`, `backend/core/runtime.py`, `backend/core/modules.py`, `backend/main.py`, `backend/services/campus/source.py`, `web/settings.js`, new focused diagnostic helpers/checks as needed.

Interface: preserve `detail/code/action/request_id`; propagate one operation identifier across nested module calls. Keep HTTP request success separate from source synchronization success, cache timestamp and failure stage.

- [ ] Add failing tests for nested-call correlation, privacy, successful status polling after failed sync, partial result, cancellation and disabled dependency.
- [ ] Implement bounded diagnostic metadata and runtime source outcomes; render and copy safe summaries in existing settings.
- [ ] Verify focused checks and existing framework/campus checks; document additive API fields.

## Task P2: authentication state and coordinated recovery

Files: `backend/services/auth/service.py`, `school.py`, `protocols.py`, `routes.py`, `web/school-login.js`, authentication settings rendering; existing recovery/account checks plus focused concurrent tests.

Interface: retain provider IDs, `account_revision`, `session_revision`, `get_status()` and `read_with_recovery()`. Separate configured credentials, session health and target-service availability; expose safe consistent recovery state.

- [ ] Reproduce concurrent-expiry, switch-during-recovery, partial-target failure and persisted recovery pause with synthetic clients.
- [ ] Coalesce only matching account/session recovery; never replay rejected credentials, verification or non-idempotent writes automatically.
- [ ] Preserve successful target sessions and invalidate stale account results; migrate consumers compatibly.
- [ ] Verify all auth checks and shared source behavior.

## Task P3: consistent asynchronous frontend behavior

Files: `web/lifecycle.js`, `shared.js`, `view-cache.js`, `campus.js`; dashboard, courses, assignments and timetable web entrypoints first; remaining existing callers where they have the same behavior.

- [ ] Add tests for unmount/switch/late-result, duplicate action, cached-partial-error display, focus/filter retention and themed layouts.
- [ ] Reuse existing helpers; add only proven shared behavior. Keep background download/sync ownership independent of page lifetime.
- [ ] Verify relevant browser checks for all themes and narrow viewports; compare synthetic timings against P0.

## Task P4: Windows runtime, desktop host and installation

Files: `backend/core/paths.py`, `scripts/launch.py`, shared runtime path consumers; new `desktop/` host/build config, packaging scripts, migration/upgrade checks and delivery documentation.

- [ ] Test resource/data separation and explicit legacy data migration before changing path logic; default development mode retains current `.private`.
- [ ] Build a pinned Windows Python/Node/Harness/plugin runtime and an explicit release source allowlist. Prepare licenses and dependency inventory.
- [ ] Implement Electron single-instance/readiness/local-port/service-lifetime behavior; retain local Host/Origin/write-token protection and official browser login boundary.
- [ ] Produce a local Windows installation candidate. Verify clean environment, Unicode paths, read-only program resources, repeat launch, port conflict, graceful exit and upgrade/rollback with synthetic data.
- [ ] Report separately any validation requiring a clean VM, publisher certificate, actual school credentials or external service access; never claim those from mocks.

## Final integration

- [ ] Run complete required checks and independent review of changes relative to the preserved starting snapshot.
- [ ] Address important findings with reproducing tests, then repeat relevant integration checks.
- [ ] Update the existing daily instance through its normal launcher and verify ready state on 16666.
- [ ] Deliver local code, install artifacts, test evidence and known limitations; keep changes uncommitted.
