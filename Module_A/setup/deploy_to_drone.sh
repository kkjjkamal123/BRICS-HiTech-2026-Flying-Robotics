#!/bin/bash
# Copy the toolkit + models to the drone and install the Python packages OFFLINE.
#   bash setup/deploy_to_drone.sh                 (drone in AP mode: 10.42.0.1)
#   DRONE=192.168.1.21 bash setup/deploy_to_drone.sh
# Password for user orangepi is asked by ssh (TECHNIC default: see docs / ask organisers).
set -e
cd "$(dirname "$0")/.."
DRONE=${DRONE:-10.42.0.1}
USER_=${DUSER:-orangepi}
echo "[deploy] -> $USER_@$DRONE:~/brics_toolkit"
# same exclusions as setup/deploy_to_drone.py: no laptop-only GBs (build/, Windows wheels, apps, datasets) on the drone
rsync -av --delete -e "ssh $SSH_OPTS" --exclude '.venv' --exclude '.venv_win' --exclude 'datasets' --exclude 'runs' --exclude 'offline/docs' \
  --exclude 'offline/wheels_mac' --exclude 'offline/wheels_win*' --exclude 'offline/python_win' --exclude '*.pt' \
  --exclude 'models/*/train' --exclude 'models/*/val' --exclude 'models/_selftest*' --exclude '__pycache__' --exclude 'docker' \
  --exclude 'build' --exclude 'dist' --exclude 'deliverables' --exclude 'cad' --exclude '*.app' --exclude '*.exe' --exclude '/core' \
  ./ "$USER_@$DRONE:~/brics_toolkit/"
ssh $SSH_OPTS -t "$USER_@$DRONE" 'cd ~/brics_toolkit && python3 -m pip install --user --no-index --find-links offline/wheels_pi onnxruntime "numpy<1.25" rknn-toolkit-lite2 ; python3 -c "import onnxruntime, cv2, yaml; print(\"drone OK: onnxruntime\", onnxruntime.__version__, \"cv2\", cv2.__version__)"'
echo "[deploy] done. On the drone:  cd ~/brics_toolkit && python3 drone/case1_fire.py --config config/case1_fire.yaml"
