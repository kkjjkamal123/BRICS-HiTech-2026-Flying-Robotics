#!/bin/bash
# Builds the native macOS dashboard and installs the ONE copy at brics_toolkit/BRICS Dashboard.app
#   bash setup/build_dashboard.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/dashboard"
xcodegen generate >/dev/null
xcodebuild -project BRICSDashboard.xcodeproj -scheme BRICSDashboard -configuration Debug -derivedDataPath build/dd build 2>&1 | grep -E "error:|BUILD"
BUILT="build/dd/Build/Products/Debug/BRICS Dashboard.app"
[ -d "$BUILT" ] || { echo "build failed"; exit 1; }
pkill -f "MacOS/BRICS Dashboard" 2>/dev/null || true
rm -rf "$ROOT/BRICS Dashboard.app"
ditto "$BUILT" "$ROOT/BRICS Dashboard.app"
rm -rf "$BUILT"          # keep a single copy of the app on this Mac
echo "installed: $ROOT/BRICS Dashboard.app"
