# DeepGen Internal Beta - Sprint 1

## Build
- Version: `0.1.0-beta.1`
- Target: macOS 14+
- Artifact: `DeepGen.dmg`
- Channel: `test`

## Sprint 1 Scope Delivered
- Native macOS `.app` + `.dmg` build pipeline.
- Optional signing and notarization automation in CI.
- Startup preflight checks with dialog errors in mac app mode.
- Basic update-channel feed + update notification plumbing.
- Installer smoke test script for app bundle and mounted DMG validation.
- Keychain-backed storage for provider secrets with migration from legacy SQLite plaintext values.

## How To Validate
1. Install from `DeepGen.dmg`.
2. Launch `DeepGen.app`.
3. Confirm startup succeeds and UI loads.
4. In terminal, call `/api/health` and verify no startup errors.
5. Run smoke script: `bash scripts/release/smoke_test_macos_artifact.sh`.

## Known Gaps
- Automatic in-app updater UI is basic notification-driven.
- Full clean-VM install test remains a manual checklist.

## Rollback
- Revert to previous `DeepGen.dmg` and set update feed to previous version.
- Disable update checks by unsetting `DEEPGEN_UPDATE_FEED_URL`.
