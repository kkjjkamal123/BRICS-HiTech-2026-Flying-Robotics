#!/bin/bash
# (Re)install the laptop environment. Works OFFLINE from offline/wheels_mac if internet is blocked.
set -e
cd "$(dirname "$0")/.."
PY=${PY:-/opt/homebrew/bin/python3.11}
[ -x "$PY" ] || PY=python3
if [ ! -x .venv/bin/python ]; then $PY -m venv .venv; fi
if [ -d offline/wheels_mac ] && [ "$(ls offline/wheels_mac | wc -l)" -gt 5 ]; then
  echo "[install] offline install from offline/wheels_mac"
  .venv/bin/pip install --no-index --find-links offline/wheels_mac -r setup/requirements_laptop.txt
else
  echo "[install] online install"
  .venv/bin/pip install -r setup/requirements_laptop.txt
fi
mkdir -p "$HOME/Library/Application Support/Ultralytics"
cp -n weights/Arial*.ttf "$HOME/Library/Application Support/Ultralytics/" 2>/dev/null || true
.venv/bin/python -c "import ultralytics, torch, cv2, onnxruntime; print('OK ultralytics', ultralytics.__version__, '| torch', torch.__version__, '| mps', torch.backends.mps.is_available())"
