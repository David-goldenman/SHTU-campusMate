# Four audit findings: implementation plan

> Execution: superpowers:executing-plans, test-driven-development and verification-before-completion.

**Goal:** Fix all four confirmed audit findings, add regressions, pass full checks, and restart the actual 16666 instance.
**Spec:** User request of 2026-10-29 and `.codex/bug-audit-20261029-round2/findings.json`.
**Architecture:** Validate physical desktop storage ancestry before any writes. Preserve ordinary user files during migration, identifying real SQLite databases rather than arbitrary filename suffixes. Scope course groups by account and require the editing account on writes. Proxy notification agent responses without converting errors to success.
**Tech stack:** Node/Electron, Python/FastAPI, native JS.

## Constraints and review focus

- Work in the verified running `assignment-reliability` checkout on `codex/architecture-hardening`; preserve existing modifications, accounts and data. No commit, push or new worktree.
- Use synthetic fixtures only. Logs, scoped before snapshots and execution ledger live in `.codex/four-bug-fixes-20261029/`; do not revisit the previously blocked cleanup.
- Reject aliases into the program tree before desktop profile creation; safe nonexistent directories remain usable. Check both program and data ancestors.
- Preserve arbitrary user `.lock`, `-wal`, `-shm` and misleading `.sqlite3` documents, while producing standalone valid copies of actual SQLite databases and excluding the root vault lock and runtime directory.
- Account B cannot read/reset account A groups. Old forms and account changes during async validation must return 409. Existing legacy groups belong once to the account present at module initialization and remain preserved; they must never be claimed by whichever account happens to read first.
- Upstream agent errors keep status and safe diagnostic fields; success responses stay compatible. Status reads retain graceful unavailable behavior.

## Tasks

- [x] Desktop: add real junction tests to `checks/check_desktop_host.cjs`, observe failure, fix `desktop/storage.cjs`, verify safe and unsafe paths and host lifecycle.
- [x] Migration: extend `checks/check_data_migration.py`, observe missing user files, fix `scripts/migrate_data.py`, verify source/backup/destination and SQLite WAL data.
- [x] Course groups: add `modules/courses/checks/check_group_accounts.py`; fix `modules/courses/server/__init__.py`, update `modules/courses/web/index.js` to send account revision, and update existing API/browser fixtures. Verify legacy ownership, isolation, reset, stale writes and switch during validation.
- [x] Notification proxy: add `modules/notifications/checks/check_agent_proxy.py`, observe failure, propagate status/body in `modules/notifications/server/__init__.py`, verify errors and successful settings/check.
- [x] Update contracts, run full `check.ps1`, and obtain an independent read-only review of this scoped change.
- [x] Normally stop/start 16666 through `run-local.ps1` using the existing runtime; verify launch identity, health, ready modules and served updated frontend.

## Acceptance — 2026-10-29

- Four original regressions were observed failing before the fixes, then passing. Additional guards cover invalid main SQLite data, committed WAL content, stale account forms, legacy ownership and failure propagation.
- `check.ps1` exited 0: 98 Python checks, 13 JavaScript groups, Windows launcher and 133 JavaScript syntax checks.
- Actual course browser checks passed: grouping ownership, account mismatch, all four desktop/mobile themes, downloads and lifecycle cleanup. Test requests and downloaded files were synthetic.
- Independent review found no blocking defect. One old migration documentation sentence was corrected after verification.
- Normal stop/start reused the same runtime and data directory. New launcher PID 34224 / listener PID 43524 / launch id `f092f3be9b0f44bdbea87d3f34347dc6`.
- 16666 health and launch identity match; all 19 modules are ready. Root and current course frontend return HTTP 200; served code includes account-bound group saves and the mismatch guard. Live GET groups/view-state return matching account revisions without exposing account contents in logs.
- Evidence: `.codex/four-bug-fixes-20261029/check-full.log`, `courses-ui-red.log`, `courses-ui-green.log`, `acceptance.json`, `progress.md` and scoped `before/` copies.
- All modifications remain local. Existing installer binaries were not rebuilt or distributed.
