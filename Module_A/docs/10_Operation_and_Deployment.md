# 10. Operation, deployment and scaling

## 10.1 Test environment

| Machine | Requirement |
|---|---|
| Drone | SKYRIS TECHNIC 6S with its stock Orange Pi image (Ubuntu 20.04, ROS Noetic, SKYRIS `technic` workspace) |
| Laptop (training, deployment) | macOS or Linux, Python 3.11, internet once for `pip install` (or the offline wheel folder) |
| Ground station | macOS 26 for the BRICS Dashboard (Xcode + XcodeGen to build) |

## 10.2 Installation

**Laptop**
```bash
cd Module_A
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r setup/requirements_laptop.txt
python tests/test_thermal_nn.py            # quick check, no drone needed
python tests/sim_case1_venue.py            # full mission against the simulated venue (8 scenarios)
```

**Drone** (laptop on the drone's network)
```bash
bash setup/download_offline.sh             # once, with internet: wheels for the drone (onnxruntime, rknn-toolkit-lite2)
DRONE=<drone-ip> bash setup/deploy_to_drone.sh     # copies the code and models, installs the wheels
ssh orangepi@<drone-ip> 'bash ~/brics_toolkit/setup/install_thermal_service.sh'   # thermal node as a service
```
If pip on the drone rejects a wheel (pip 20 does not know `manylinux_2_27`), unzip the wheel into `~/.local/lib/python3.8/site-packages`.

**Venue marker map:** copy `config/aruco_map_750x450_id100.txt` to `~/technic_ws/src/technic/aruco_pose/map/` on the drone, set it as `map` in `aruco.launch`, then `sudo systemctl restart technic`.

**Ground station**
```bash
brew install xcodegen
bash setup/build_dashboard.sh              # builds "BRICS Dashboard.app" inside Module_A
```

## 10.3 Startup

1. Battery in, wait for the drone to boot (~1 min). RC on.
2. Open **BRICS Dashboard**, type the drone address in the sidebar, press **Test connection**, then **Sync drone clock**.
3. Check the pre-test checklist ([09](09_Pretest_Checklist.md)): live RGB and thermal video, battery %, map loaded.
4. Place the drone on the home position (field centre), facing the same direction as in the map.

## 10.4 Normal operation

1. Mission Control → **Run mission**. The drone shows a 3 s countdown (ABORT cancels), then takes off.
2. Watch the live map: each source appears once with class, temperature and time; the event list shows every detection.
3. The drone surveys, stops briefly to photograph each source (it never descends towards it), returns home and lands by itself. **Return Home** can be pressed at any time.
4. Results: Dashboard → **Results** (path, detections, snapshots, frame-rate statistics). Files are in `runs/case1_fire_<date>_<time>/` on the drone.

Command-line equivalent on the drone:
```bash
source /opt/ros/noetic/setup.bash; source ~/technic_ws/devel/setup.bash
cd ~/brics_toolkit && python3 drone/case1_fire.py --config config/case1_fire.yaml --autostart
```

## 10.5 Safe shutdown

1. Wait for `DONE` in the dashboard (the drone has landed and disarmed).
2. Copy the logs back (Flight Tests → Copy flight logs back).
3. Disconnect the battery. To power down the computer first: `sudo poweroff` over SSH.

**Emergency:** ABORT / LAND in the dashboard lands immediately. If the drone does not react, the pilot takes over with the RC; the **kill switch (channel 8)** stops the motors.

## 10.6 Typical errors

| Message / symptom | Cause | Action |
|---|---|---|
| Dashboard "not connected" | Laptop on a different network, wrong address | Join the drone's network, retype the address, Test connection |
| `preflight ... reaches X m outside the marker field` | Area or fence in the config is bigger than the marker map | Fix `area` / `safety.fence` inside x −3…3, y −1.5…1.5 |
| `no position in aruco_map ... after take-off` | Wrong map loaded, markers not visible, poor light | Check `rosparam get /aruco_map/map`, lighting, camera focus |
| `takeoff rejected: Arming timed out` | PX4 pre-arm check failed | Read the PX4 message in QGroundControl, fix, run again |
| `no thermal data on topic 'thermal/temp'` | Thermal camera unplugged or service stopped | Plug in, `sudo systemctl restart brics-thermal` |
| `A mission script is ALREADY RUNNING` | Run pressed twice | Use Start/Land in the dashboard, or stop the running one first |
| Low frame rate | Models on the CPU (NPU runtime missing) | Check the start log for "running on the NPU"; reinstall `rknn-toolkit-lite2` |

## 10.7 Scaling and further integration

* **Larger areas:** replace the ArUco map with GNSS/RTK (outdoors) or visual-inertial odometry; the mission uses `frame_id` and `area` from the config, so the survey logic stays the same.
* **More drones:** the mission engine is per drone; several drones can survey separate zones of a larger area, each with its own altitude.
* **Other targets:** any new object class needs only a dataset and a training run (`train/train.py --data <dataset> --name <model>`), then the model path in the config.
* **Integration with the customer's systems:** the mission link already outputs JSON events with map coordinates; converting `aruco_map` metres to geographic coordinates is a single transform once GNSS is used.
