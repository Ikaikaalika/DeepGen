# Step 1 Release Runbook (Signed + Notarized Beta)

## Prerequisites
- Apple Developer signing identity present on CI runner setup.
- GitHub repo secrets configured:
  - `MACOS_CODESIGN_IDENTITY`
  - `APPLE_ID`
  - `APPLE_TEAM_ID`
  - `APPLE_APP_PASSWORD`
- GitHub CLI authenticated (`gh auth login -h github.com`).

## Local Validation (already completed)
1. Build artifact:
   - `bash scripts/release/build_macos_app.sh`
2. Smoke test artifact:
   - `bash scripts/release/smoke_test_macos_artifact.sh dist/DeepGen.app dist/DeepGen.dmg`

## Dispatch Signed/Notarized CI Build
1. Push current branch.
2. Run preflight + dispatch:
   - `bash scripts/release/github_release_preflight.sh 0.1.0-beta.1 test`
3. Monitor run:
   - `gh run watch`
4. Download artifacts when complete:
   - `gh run download --name deepgen-macos-artifacts`

## Optional tagged release path
- Create/push tag: `v0.1.0-beta.1`
- The workflow will also publish release assets on tag runs.

## Verify Release Output
- Confirm DMG notarization and staple in logs.
- Install on clean macOS user/VM.
- Launch app and verify `/api/health` is `ok` or expected `degraded` warnings only.
