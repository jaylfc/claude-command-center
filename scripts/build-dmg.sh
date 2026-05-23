#!/usr/bin/env bash
# Build a macOS .dmg installer for CCC.
#
# Output: ccc-v<version>.dmg in the repo root.
#
# The DMG contains:
#   - CCC.app           — a thin AppleScript/bash launcher that wraps
#                         scripts/install.sh. Drag this to /Applications.
#   - Applications      — symlink target so the user can drag CCC.app onto it.
#
# CCC.app does NOT bundle Python or the Claude CLI. It expects them on PATH
# (same prereqs as curl install). If they are missing, the launcher pops a
# friendly dialog pointing to docs.claude.com.
#
# This is the "click-to-install" path, alongside curl-bash and brew tap.
# All three paths share the same install.sh, so behaviour stays consistent.
#
# Usage:
#   ./scripts/build-dmg.sh                # version pulled from pyproject.toml
#   ./scripts/build-dmg.sh 4.3.1          # explicit version
#
# Requirements: macOS (uses hdiutil, sips, iconutil, plutil). All are
# system-provided on every Mac.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "build-dmg: macOS-only (uses hdiutil + iconutil)" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Resolve version
# ---------------------------------------------------------------------------
VERSION="${1:-}"
if [ -z "$VERSION" ]; then
  VERSION="$(grep -E '^version *= *"' "$REPO_ROOT/pyproject.toml" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')"
fi
if [ -z "$VERSION" ]; then
  echo "build-dmg: could not resolve version (pass as arg or set in pyproject.toml)" >&2
  exit 1
fi
echo "build-dmg: version = $VERSION"

DMG_NAME="ccc-v${VERSION}.dmg"
DMG_PATH="$REPO_ROOT/$DMG_NAME"
VOL_NAME="CCC v${VERSION}"

# ---------------------------------------------------------------------------
# Staging dirs
# ---------------------------------------------------------------------------
WORK_DIR="$(mktemp -d -t ccc-dmg-build)"
trap 'rm -rf "$WORK_DIR"' EXIT
APP_DIR="$WORK_DIR/CCC.app"
STAGING_DIR="$WORK_DIR/staging"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources" "$STAGING_DIR"

# ---------------------------------------------------------------------------
# Icon: convert _assets/Claude Command Center.png to .icns
# ---------------------------------------------------------------------------
SRC_ICON="$REPO_ROOT/_assets/Claude Command Center.png"
if [ -f "$SRC_ICON" ]; then
  echo "build-dmg: rendering icon from $SRC_ICON"
  ICONSET="$WORK_DIR/CCC.iconset"
  mkdir -p "$ICONSET"
  sips -z 16   16   "$SRC_ICON" --out "$ICONSET/icon_16x16.png"      >/dev/null
  sips -z 32   32   "$SRC_ICON" --out "$ICONSET/icon_16x16@2x.png"   >/dev/null
  sips -z 32   32   "$SRC_ICON" --out "$ICONSET/icon_32x32.png"      >/dev/null
  sips -z 64   64   "$SRC_ICON" --out "$ICONSET/icon_32x32@2x.png"   >/dev/null
  sips -z 128  128  "$SRC_ICON" --out "$ICONSET/icon_128x128.png"    >/dev/null
  sips -z 256  256  "$SRC_ICON" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
  sips -z 256  256  "$SRC_ICON" --out "$ICONSET/icon_256x256.png"    >/dev/null
  sips -z 512  512  "$SRC_ICON" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
  sips -z 512  512  "$SRC_ICON" --out "$ICONSET/icon_512x512.png"    >/dev/null
  sips -z 1024 1024 "$SRC_ICON" --out "$ICONSET/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "$ICONSET" -o "$APP_DIR/Contents/Resources/CCC.icns"
else
  echo "build-dmg: no icon at $SRC_ICON — DMG will use default Finder icon"
fi

# ---------------------------------------------------------------------------
# Bundle the installer script
# ---------------------------------------------------------------------------
cp "$REPO_ROOT/scripts/install.sh" "$APP_DIR/Contents/Resources/install.sh"
chmod +x "$APP_DIR/Contents/Resources/install.sh"

# ---------------------------------------------------------------------------
# Info.plist
# ---------------------------------------------------------------------------
cat > "$APP_DIR/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key><string>en</string>
  <key>CFBundleDisplayName</key><string>Claude Command Center</string>
  <key>CFBundleExecutable</key><string>CCC</string>
  <key>CFBundleIconFile</key><string>CCC</string>
  <key>CFBundleIdentifier</key><string>com.github.claude-command-center</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>CCC</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundleVersion</key><string>${VERSION}</string>
  <key>LSMinimumSystemVersion</key><string>10.15</string>
  <key>LSUIElement</key><false/>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSHumanReadableCopyright</key><string>MIT — github.com/amirfish1/claude-command-center</string>
</dict>
</plist>
EOF
plutil -lint "$APP_DIR/Contents/Info.plist" >/dev/null

# ---------------------------------------------------------------------------
# Launcher: Contents/MacOS/CCC
# ---------------------------------------------------------------------------
cat > "$APP_DIR/Contents/MacOS/CCC" <<'LAUNCHER_EOF'
#!/bin/bash
# CCC.app launcher.
#
# Fast path: if CCC is already running on :8090, just open the browser.
# Slow path: spawn Terminal.app and run the bundled install.sh with
# CCC_FROM=dmg. The user sees familiar install output and the script
# either drops them into ./run.sh foreground or installs as a launchd
# service (their choice — install.sh asks).
set -euo pipefail

PORT=8090
URL="http://localhost:${PORT}"

# Resolve bundle layout
APP_BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
RESOURCES_DIR="$(cd "$APP_BIN_DIR/../Resources" && pwd)"
INSTALL_SCRIPT="$RESOURCES_DIR/install.sh"

# LaunchServices strips PATH to a minimal default when a .app is
# double-clicked. Add the common spots `claude`, `git`, `python3` live:
#   ~/.local/bin    Anthropic native installer default for claude
#   /opt/homebrew   Homebrew on Apple Silicon
#   /usr/local      Homebrew on Intel / traditional
#   ~/.bun/bin      Bun (some users install claude via bun)
#   /usr/bin:/bin   System binaries (python3, git from Xcode CLT)
export PATH="$HOME/.local/bin:$HOME/.bun/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

# Fast path: server already up
if (echo > "/dev/tcp/127.0.0.1/${PORT}") >/dev/null 2>&1; then
  open "$URL" >/dev/null 2>&1 || true
  exit 0
fi

# Sanity: bundled installer present
if [ ! -f "$INSTALL_SCRIPT" ]; then
  osascript -e 'display alert "CCC installer missing" message "This DMG is missing scripts/install.sh. Re-download from github.com/amirfish1/claude-command-center/releases or try the curl install."' >/dev/null 2>&1 || true
  exit 1
fi

# Prereq: claude CLI. python3 + git are checked again by install.sh, but
# claude is the one most likely missing on a fresh Mac and the error there
# is less recoverable, so warn early.
if ! command -v claude >/dev/null 2>&1; then
  osascript <<APPLESCRIPT >/dev/null 2>&1 || true
set claudeURL to "https://docs.claude.com/en/docs/claude-code"
set dialogResult to display alert "Claude CLI not found" message "CCC needs the Claude Code CLI on your PATH. Install it from Anthropic's docs, then re-launch CCC." buttons {"Cancel", "Open docs"} default button "Open docs"
if button returned of dialogResult is "Open docs" then
  do shell script "open " & quoted form of claudeURL
end if
APPLESCRIPT
  exit 1
fi

# Copy installer to /tmp so Terminal can read it without bundle-quarantine drama
TMP_SCRIPT="$(mktemp -t ccc-install).sh"
cp "$INSTALL_SCRIPT" "$TMP_SCRIPT"
chmod +x "$TMP_SCRIPT"

# Open Terminal with the installer
osascript <<APPLESCRIPT >/dev/null 2>&1
tell application "Terminal"
  activate
  do script "clear; echo '→ Claude Command Center installer (DMG path)'; echo; CCC_FROM=dmg bash '${TMP_SCRIPT}'; echo; echo '(You can close this window once CCC is running.)'"
end tell
APPLESCRIPT

exit 0
LAUNCHER_EOF
chmod +x "$APP_DIR/Contents/MacOS/CCC"

# ---------------------------------------------------------------------------
# Strip extended attributes that Gatekeeper sometimes chokes on
# ---------------------------------------------------------------------------
xattr -cr "$APP_DIR" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Ad-hoc codesign — does not satisfy notarization but does prevent the
# "App is damaged" error after quarantine on Apple Silicon. Optional; the
# DMG still works without it, the user just has to right-click → Open.
# ---------------------------------------------------------------------------
if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "$APP_DIR" >/dev/null 2>&1 || \
    echo "build-dmg: ad-hoc codesign failed (non-fatal)"
fi

# ---------------------------------------------------------------------------
# Stage + build DMG
# ---------------------------------------------------------------------------
cp -R "$APP_DIR" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

# Drop a small README the user sees if they explore the DMG
cat > "$STAGING_DIR/README.txt" <<EOF
Claude Command Center — v${VERSION}

1. Drag CCC.app onto the Applications folder.
2. Open CCC from Launchpad or /Applications.
3. The installer opens a Terminal window. Approve the prereqs, then
   the dashboard opens at http://localhost:8090.

First launch: macOS may say "CCC is from an unidentified developer".
Right-click CCC.app in Applications → Open → Open. This only happens
once. CCC is open source; the project is unsigned by choice (no Apple
developer account).

Curl and Homebrew install paths are also available — see
https://github.com/amirfish1/claude-command-center
EOF

echo "build-dmg: assembling $DMG_NAME"
rm -f "$DMG_PATH"
hdiutil create \
  -volname "$VOL_NAME" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  -fs HFS+ \
  -imagekey zlib-level=9 \
  "$DMG_PATH" >/dev/null

SIZE_KB="$(du -k "$DMG_PATH" | awk '{print $1}')"
echo "build-dmg: wrote $DMG_PATH (${SIZE_KB} KB)"
echo "build-dmg: next steps —"
echo "  open '$DMG_PATH'                       # smoke test locally"
echo "  gh release upload v${VERSION} '$DMG_PATH'   # publish to GitHub release"
