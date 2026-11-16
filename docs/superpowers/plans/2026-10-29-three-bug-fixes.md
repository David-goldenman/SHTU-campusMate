# Three confirmed bugs: implementation plan

> Execution: superpowers:executing-plans, with test-driven-development and verification-before-completion.

**Goal:** Fix the three reproduced bugs, add permanent regression coverage, then restart the existing 16666 instance.

**Spec:** User request of 2026-10-29 and `.codex/bug-audit-20261029/findings.json`.

**Architecture:** Reject reparse points anywhere in program/data ancestry before installer mutations. Classify only the framework's read-only network explanation POST as non-mutating for view invalidation. Exclude `runtime` only at the data root during migration.

**Tech stack:** PowerShell 5.1, Python 3.12, native JavaScript modules.

## Constraints and rulings

- Use the verified running worktree `assignment-reliability`, branch `codex/architecture-hardening`; preserve all pre-existing edits and user data.
- User authorized implementation and restart; execute inline without an extra approval gate. No commit, push or PR.
- Development artifacts stay in `.codex/bug-fixes-20261029/`; its `progress.md` is the execution ledger. Prior file versions are in `before/` for scoped review despite existing uncommitted changes.
- All tests use synthetic files and requests. Do not migrate or uninstall actual user data.
- No shared interfaces between the three fixes.

## Review focus

- Ancestor junctions in installation and configured/default data paths must be rejected for install, rollback and uninstall.
- Existing installation maintenance scripts must receive the safety fix on upgrade.
- Successful or failed diagnostic POST requests must preserve a valid same-account preview.
- Real mutations and token changes must still invalidate delayed reads.
- Nested and repeatedly nested user `runtime` folders must survive in destination and backup while the top-level runtime is excluded.

## Tasks

- [x] Installer: extend `checks/check_windows_install.py`, observe failure, guard ancestry in `packaging/install.ps1`, and verify install/upgrade/rollback/uninstall behavior.
- [x] Migration: extend `checks/check_data_migration.py`, observe failure, scope exclusion in `scripts/migrate_data.py`, and verify copied user files, backups and failure preservation.
- [x] Cache: add `checks/check_network_view_cache.mjs` using the real API/cache/panel chain; integrate in `checks/check_frontend.mjs`, observe failure, fix `web/shared.js`, and verify diagnostic overlap plus mutation/account controls.
- [x] Update affected contracts in `docs/MODULES.md` and `docs/DELIVERY.md`; run `check.ps1` and scoped independent review.
- [x] Stop/start via existing `scripts/launch.py` with `.private/runtime/windows/venv/Scripts/python.exe`; verify new launch identity, health and served frontend fix on 16666.

## Acceptance — 2026-10-29

- All three regressions were observed failing before the corresponding fix, then passing.
- `check.ps1` exited 0: 96 Python checks, 13 JavaScript groups, Windows launcher and 133 JavaScript syntax checks. The new network/cache integration is included in the frontend group.
- Independent review accepted all three changes without actionable findings.
- Normal stop/start through `run-local.ps1` reused the existing Python and data directory. New launcher PID 52244, listener PID 96912, launch identity `9753cc5cf28a46f9a19a24fc3a47c01d`.
- Health identity matches the launcher record. Both `/` and `/assets/shared.js` return HTTP 200 on 16666; the served shared API contains both the diagnostic exception and write invalidation.
- Evidence: `.codex/bug-fixes-20261029/check-full.log`, `acceptance.json`, `progress.md`, and the scoped `before/` snapshots. No commit or publish; existing installer binaries were not rebuilt.
