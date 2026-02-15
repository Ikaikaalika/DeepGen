#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.13 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python 3.11+ is required but no compatible interpreter was found." >&2
  exit 1
fi

APP_NAME="DeepGen"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"
APP_PATH="$DIST_DIR/${APP_NAME}.app"
DMG_PATH="$DIST_DIR/${APP_NAME}.dmg"
VENV_DIR="$ROOT_DIR/.venv-release"

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e .[macapp]
python -m pip install pyinstaller

rm -rf "$BUILD_DIR" "$DIST_DIR"

python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  deepgen/mac_app.py

if [[ ! -d "$APP_PATH" ]]; then
  echo "Expected app bundle missing: $APP_PATH" >&2
  exit 1
fi

if [[ -n "${MACOS_CODESIGN_IDENTITY:-}" ]]; then
  codesign --force --deep --options runtime --timestamp --sign "$MACOS_CODESIGN_IDENTITY" "$APP_PATH"
fi

hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$APP_PATH" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

if [[ -n "${MACOS_CODESIGN_IDENTITY:-}" ]]; then
  codesign --force --sign "$MACOS_CODESIGN_IDENTITY" "$DMG_PATH"
fi

echo "Built app: $APP_PATH"
echo "Built dmg: $DMG_PATH"
