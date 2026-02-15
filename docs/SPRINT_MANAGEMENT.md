# DeepGen Mac App Sprint Management Plan

## Current LLM Support
- Supported now: OpenAI API, Anthropic Claude API, local MLX.
- Planned hardening in Sprint 2: keychain-backed secret storage and provider reliability tests.

## Program Goal
Ship a signed, production-quality macOS genealogy application with secure local data handling, internet + archive research, review workflows, and safe AI-assisted enrichment.

## Delivery Cadence
- Sprint length: 2 weeks
- Release train: internal beta every sprint, external beta every 2 sprints
- Environments: local dev, beta notarized build, production notarized build

## Sprint 1: App Foundation and Packaging
### Status
- In progress (implemented in-repo tooling and CI workflow scaffold).

### Goals
- Native app packaging, signing, notarization, and installer flow.
- Basic auto-update channel.

### Scope
- Build `.app` and `.dmg` pipeline.
- Apple Developer signing + notarization setup.
- Update framework integration (Sparkle or equivalent).
- Crash-safe startup checks.
- Keychain-backed provider secret storage + legacy plaintext migration.

### Exit Criteria
- App installs on clean macOS machine.
- Notarization passes.
- Update check works against test feed.

## Sprint 2: AI Provider Layer and Secrets
### Goals
- Harden provider layer and secure credential storage.

### Scope
- Stabilize `openai` + `anthropic` + `mlx` provider behavior and failover UX.
- Add keychain health diagnostics and recovery UX.
- Keep non-secret config in SQLite.

### Exit Criteria
- User can switch between OpenAI, Claude, and MLX.
- Keys no longer stored in plaintext DB.
- Regression tests pass for all backends.

## Sprint 3: Folder Permissions and Indexing Jobs
### Goals
- Production-grade local folder integration.

### Scope
- Native folder picker.
- Persistent security-scoped bookmarks.
- Permission state and reauthorization UX.
- Background indexing queue with progress, cancel, retry.

### Exit Criteria
- Folder reconnect persists across restarts.
- Large folder indexing can be resumed after restart.
- UI shows real-time status and failures.

## Sprint 4: Genealogy Data Ingestion and Evidence Quality
### Goals
- Real FamilySearch integration and stronger evidence quality.

### Scope
- FamilySearch OAuth + refresh token handling.
- Live FamilySearch record fetch + normalized evidence objects.
- Evidence confidence framework and contradiction detection.
- Citation traceability per proposal.

### Exit Criteria
- OAuth login succeeds and refreshes without user re-login.
- Research findings include linked citations per claim.
- Contradictions are surfaced in UI.

## Sprint 5: Review, Merge, and Safe Face Pairing Workflow
### Goals
- Human-in-the-loop decisioning for all sensitive actions.

### Scope
- Proposal review queue (approve/reject/edit).
- Merge/dedupe engine with conflict resolution.
- Undo/rollback for merges and applied updates.
- Face pairing review queue; no auto-apply.
- Consent and disclosure prompts for biometric features.

### Exit Criteria
- No automated identity merge without user approval.
- Face matches require explicit user confirmation.
- Undo restores pre-merge state.

## Sprint 6: Reliability, Compliance, and Launch Readiness
### Goals
- Production ops, privacy controls, and QA completeness.

### Scope
- Structured logging and telemetry.
- In-app diagnostics export.
- Backup/snapshot + restore flow.
- Data export/delete controls.
- E2E tests for core workflows.
- Performance profiling and memory tuning.

### Exit Criteria
- Recovery drill validated from backup.
- Privacy actions complete within product SLA.
- Launch checklist signed off.

## Cross-Sprint Backlog (Must-Have)
- Alembic migrations and schema versioning.
- Offline mode behavior and degraded UX states.
- API retry policy and circuit breaking.
- Accessibility pass for keyboard/screen-reader usage.
- Security review for third-party dependencies.

## Tracking Model
- Epics: one per sprint goal area.
- Stories: vertical slices with UI + backend + tests.
- Bugs: severity P0-P3 with 48h SLA for P0/P1.

## Definition of Done
- Feature implemented behind stable API.
- Unit + integration tests added and passing.
- Documentation updated.
- Error handling and user-visible states covered.
- Security/privacy review completed where applicable.

## Risks and Mitigations
- Face recognition false matches.
  - Mitigation: strict thresholds + mandatory manual review.
- Provider API changes/rate limits.
  - Mitigation: adapter layer + retries + cached evidence.
- Apple notarization delays.
  - Mitigation: automate preflight signing checks.
- Large archives causing slow scans.
  - Mitigation: chunked indexing + incremental state.

## First Sprint Task Breakdown (Ready to Start)
1. Create release pipeline for signed `.app` and `.dmg`.
2. Add app startup health checks and error dialogs.
3. Integrate update framework with test channel.
4. Add installer smoke tests on clean macOS VM.
5. Publish Sprint 1 internal beta notes.
