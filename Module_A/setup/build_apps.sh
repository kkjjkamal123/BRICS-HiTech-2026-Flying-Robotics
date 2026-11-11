#!/bin/bash
# Rebuild the desktop apps (only needed if studio/desktop_app.py changes; the toolkit code itself is loaded at runtime).
#   bash setup/build_apps.sh            -> "BRICS Mission Studio.app" (macOS) + "BRICS Mission Studio.exe" (Windows, via Docker+Wine)
#   bash setup/build_apps.sh --mac      -> only the macOS .app
#   bash setup/build_apps.sh --win      -> only the Windows .exe
# The version comes from the VERSION file (marketing version) and common/version.py (BUILD number).
set -e
cd "$(dirname "$0")/.."
R="$PWD"
MAC=1; WINB=1
case "${1:-}" in
  --mac) WINB=0 ;;
  --win) MAC=0 ;;
  "") ;;
  *) echo "usage: $0 [--mac|--win]"; exit 2 ;;
esac
VER=$(tr -d ' \n' < VERSION)
BUILD=$(sed -n 's/^BUILD *= *\([0-9]*\).*/\1/p' common/version.py)
grep -q "APP_VERSION = \"$VER\"" studio/desktop_app.py || { echo "studio/desktop_app.py APP_VERSION differs from VERSION ($VER)"; exit 1; }
if [ $MAC = 1 ]; then
  echo "== macOS .app  $VER ($BUILD)"
  build/.venv_app/bin/pyinstaller --noconfirm --windowed --name "BRICS Mission Studio" --icon "$R/build/icon.icns" \
    --add-data "$R/studio/icon.png:." --hidden-import markdown.extensions.tables --hidden-import markdown.extensions.fenced_code \
    --exclude-module tkinter --osx-bundle-identifier org.brics.missionstudio --distpath build/dist --workpath build/pyi --specpath build studio/desktop_app.py
  APP="build/dist/BRICS Mission Studio.app"
  plutil -replace CFBundleShortVersionString -string "$VER" "$APP/Contents/Info.plist"
  plutil -replace CFBundleVersion -string "$BUILD" "$APP/Contents/Info.plist"
  codesign --force --deep --sign - "$APP"          # Info.plist changed -> re-sign (ad hoc, as PyInstaller does)
  rm -rf "BRICS Mission Studio.app" && cp -R "$APP" .
  ls -la "BRICS Mission Studio.app"
fi
if [ $WINB = 1 ]; then
  echo "== Windows .exe (Docker image brics-winbuild, colima with --vz-rosetta)"
  docker run --rm --platform linux/amd64 -v "$R":/src -w /src brics-winbuild bash -c 'WINEDEBUG=-all wine pyinstaller --noconfirm --onefile --windowed --name "BRICS Mission Studio" --icon "Z:\\src\\build\\icon.ico" --add-data "Z:\\src\\studio\\icon.png;." --hidden-import markdown.extensions.tables --hidden-import markdown.extensions.fenced_code --exclude-module tkinter --distpath "Z:\\src\\build\\dist_win" --workpath "Z:\\src\\build\\pyi_win" --specpath "Z:\\src\\build\\win" "Z:\\src\\studio\\desktop_app.py"'
  cp "build/dist_win/BRICS Mission Studio.exe" .
  ls -la "BRICS Mission Studio.exe"
fi
