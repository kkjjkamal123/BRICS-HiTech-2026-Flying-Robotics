#!/bin/bash
# Builds the native macOS dashboard and installs the ONE copy at brics_toolkit/BRICS Dashboard.app
#   bash setup/build_dashboard.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/dashboard"
xcodegen generate >/dev/null
rm -rf "build/dd/Build/Products/Release/BRICS Dashboard.app"       # never install a stale product
xcodebuild -project BRICSDashboard.xcodeproj -scheme BRICSDashboard -configuration Release -derivedDataPath build/dd build 2>&1 | grep -E "error:|BUILD" || true
BUILT="build/dd/Build/Products/Release/BRICS Dashboard.app"
# only a COMPLETE app replaces the installed one: a failed build can leave a folder without the program in it
[ -x "$BUILT/Contents/MacOS/BRICS Dashboard" ] || { echo "BUILD FAILED - the installed app was NOT touched"; exit 1; }
pkill -f "MacOS/BRICS Dashboard" 2>/dev/null || true
rm -rf "$ROOT/BRICS Dashboard.app"
ditto "$BUILT" "$ROOT/BRICS Dashboard.app"
rm -rf "$BUILT"          # keep a single copy of the app on this Mac
echo "installed: $ROOT/BRICS Dashboard.app"
