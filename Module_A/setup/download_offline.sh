#!/bin/bash
# Download everything needed to reinstall WITHOUT internet (run while you still have internet).
set -e
cd "$(dirname "$0")/.."
mkdir -p offline/wheels_mac offline/wheels_pi
.venv/bin/pip download -d offline/wheels_mac -r setup/requirements_laptop.txt
# drone (Orange Pi: Ubuntu 20.04, Python 3.8, aarch64) - via the pi-replica container
docker run --rm -v "$PWD":/work brics-pi-env pip3 download -d /work/offline/wheels_pi "onnxruntime<1.20" "numpy<1.25" rknn-toolkit-lite2
echo "done: $(du -sh offline | cut -f1)"
