#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

VERSION="${1:-0.1.0-beta.1}"
CHANNEL="${2:-test}"
WORKFLOW_FILE="macos-release.yml"

required_tools=(gh git)
for tool in "${required_tools[@]}"; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing required tool: $tool" >&2
    exit 1
  fi
done

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub auth is not ready. Run: gh auth login -h github.com" >&2
  exit 1
fi

repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"

echo "Repo: $repo"
echo "Checking required GitHub secrets..."

required_secrets=(
  MACOS_CODESIGN_IDENTITY
  APPLE_ID
  APPLE_TEAM_ID
  APPLE_APP_PASSWORD
)

secrets_output="$(gh secret list 2>/tmp/deepgen_gh_secret_err || true)"
if [[ -z "$secrets_output" ]]; then
  err_text="$(cat /tmp/deepgen_gh_secret_err 2>/dev/null || true)"
  echo "Unable to read GitHub secrets. Ensure you are authenticated with repo admin access." >&2
  if [[ -n "$err_text" ]]; then
    echo "$err_text" >&2
  fi
  exit 1
fi

missing=()
for secret in "${required_secrets[@]}"; do
  if ! printf "%s\n" "$secrets_output" | awk '{print $1}' | grep -Fx "$secret" >/dev/null 2>&1; then
    missing+=("$secret")
  fi
done

if (( ${#missing[@]} > 0 )); then
  echo "Missing secrets: ${missing[*]}" >&2
  echo "Add each with: gh secret set <NAME>" >&2
  exit 1
fi

if ! gh workflow list | awk '{print $1}' | grep -Fx "$WORKFLOW_FILE" >/dev/null 2>&1; then
  echo "Workflow file not found in GitHub Actions list: $WORKFLOW_FILE" >&2
  exit 1
fi

echo "All preflight checks passed."

echo "Dispatching workflow: $WORKFLOW_FILE"
gh workflow run "$WORKFLOW_FILE" -f version="$VERSION" -f channel="$CHANNEL"

echo "Workflow dispatched. Recent runs:"
gh run list --workflow "$WORKFLOW_FILE" --limit 5
