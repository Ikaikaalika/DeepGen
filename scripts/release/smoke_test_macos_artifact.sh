#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_PATH="${1:-$ROOT_DIR/dist/DeepGen.app}"
DMG_PATH="${2:-$ROOT_DIR/dist/DeepGen.dmg}"
MOUNTPOINT="/Volumes/DeepGen"

if [[ ! -d "$APP_PATH" ]]; then
  echo "Missing app bundle: $APP_PATH" >&2
  exit 1
fi

if [[ ! -f "$APP_PATH/Contents/Info.plist" ]]; then
  echo "Missing Info.plist in app bundle" >&2
  exit 1
fi

if [[ ! -x "$APP_PATH/Contents/MacOS/DeepGen" ]]; then
  echo "Missing executable in app bundle" >&2
  exit 1
fi

codesign --verify --deep --strict "$APP_PATH" || {
  echo "codesign verification failed (allowed in unsigned local builds)"
}

if [[ -f "$DMG_PATH" ]]; then
  hdiutil attach "$DMG_PATH" -nobrowse -quiet
  if [[ ! -d "$MOUNTPOINT" ]]; then
    echo "Failed to mount dmg at $MOUNTPOINT" >&2
    exit 1
  fi
  if [[ ! -d "$MOUNTPOINT/DeepGen.app" ]]; then
    echo "Mounted dmg missing DeepGen.app" >&2
    hdiutil detach "$MOUNTPOINT" -quiet || true
    exit 1
  fi
  hdiutil detach "$MOUNTPOINT" -quiet
fi

echo "Smoke test passed for macOS installer artifacts."
