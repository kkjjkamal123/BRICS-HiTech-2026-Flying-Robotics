#!/bin/bash
# Run ON THE DRONE once (needs sudo):   bash ~/brics_toolkit/setup/install_thermal_service.sh
# 1. turns off the drone's own "second camera" node, which holds the thermal camera and discards its temperatures
# 2. installs the service brics-thermal, which runs tools/thermal_node.py at every boot
# Undo:  bash ~/brics_toolkit/setup/install_thermal_service.sh --undo
set -e
L=~/technic_ws/src/technic/technic/launch/technic.launch
if [ "$1" = "--undo" ]; then
  sudo systemctl disable --now brics-thermal 2>/dev/null || true
  sudo rm -f /etc/systemd/system/brics-thermal.service
  [ -f "$L.bak_second_camera" ] && cp "$L.bak_second_camera" "$L"
  sudo systemctl daemon-reload
  sudo systemctl restart technic
  echo "undone: the drone's second camera node is back, brics-thermal removed"
  exit 0
fi
[ -f "$L.bak_second_camera" ] || cp "$L" "$L.bak_second_camera"
sed -i 's|<arg name="second_camera" default="true"/>|<arg name="second_camera" default="false"/>|' "$L"
grep -n 'name="second_camera"' "$L"
sudo tee /etc/systemd/system/brics-thermal.service >/dev/null <<UNIT
[Unit]
Description=BRICS thermal camera node (real temperatures, fire >= 100 C)
After=roscore.service technic.service
Wants=roscore.service

[Service]
User=$USER
Restart=always
RestartSec=3
ExecStart=/bin/bash -c 'source /opt/ros/noetic/setup.bash; exec python3 -u $HOME/brics_toolkit/tools/thermal_node.py --device /dev/camera_second --fire-c 100'

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl restart technic
sleep 6
sudo systemctl enable --now brics-thermal
sudo systemctl restart brics-thermal
echo "installed. Check:  systemctl status brics-thermal ;  rostopic hz /thermal/image_raw"
