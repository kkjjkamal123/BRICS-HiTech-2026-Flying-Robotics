# 8. Safety and maintainability

## 8.1 Safe operation: software

| Protection | Rule | Where |
|---|---|---|
| RC kill switch | Channel 8 stops the motors at the flight-controller level, independent of our software | PX4 `RC_MAP_KILL_SW=8` |
| Operator ABORT / LAND / Stop | Land in place; the dashboard never disarms in the air | `mission_base.run`, dashboard |
| Operator RETURN HOME | Fly to home at survey height, then land | `mission_base.go_home` |
| Geofence | Fence = outer marker centres `[-3, -1.5, 3, 1.5]`; leaving it or climbing above 3 m → land; waypoints outside are skipped | `technic_api.safety_problem`, `mission_base.fly` |
| Map-boundary check | A fence more than 0.3 m outside the marker map loaded on the drone → mission refuses to start (cannot be overridden) | `mission_base.preflight` |
| Pre-flight | FCU connected, not already armed, battery ≥ 3.7 V/cell, cameras give images, planned heights below the limit | `mission_base.preflight` |
| Position loss | No `aruco_map` pose → land; map not found 6 s after take-off → land | `technic_api`, `mission_base.wait_for_map` |
| Battery | Pack voltage / 6 cells < 3.5 V → land | `technic_api._fix_cell_voltage` |
| Time limit | 540 s (slot is 600 s) → land | `mission_base._during` |
| Arming failure | Mission stops instead of continuing | `technic_api.takeoff` |
| Land refused | Retry, then PX4 AUTO.LAND; if the pilot is in a manual mode, hands off to the pilot | `technic_api._land_fallback` |
| Duplicate start | Second mission instance refuses to start | lock file `/tmp/brics_mission.lock` |
| False alarms | 4 consistent sightings before an alarm; no detections below 0.6 m; thermal network boxes must be really hot | `config/case1_fire.yaml` |
| PX4 failsafes | RC loss → Land (`NAV_RCL_ACT=3`), low battery action (`COM_LOW_BAT_ACT=2`) | [`Others/evidence/drone_config/px4_params.txt`](../../Others/evidence/drone_config/px4_params.txt) |

Unit tests for these rules: [`../tests/test_flight_safety.py`](../tests/test_flight_safety.py) (all pass on the drone, 11 Nov 2026).

## 8.2 Safe operation: hardware, mounts and cables

* Props inside the SKYRIS clip-on guards; landing legs are the lowest point.
* The drone never descends towards a source or a tree: it photographs from survey height, so it keeps its distance from the tall artificial trees.
* The thermal camera sits in a cradle with crush ribs and is held by two straps through the mount's slots; its USB cable is tied to the anchor tab so it cannot reach the props.
* All connectors (XT60, MR30, JST, USB) are plugged, not soldered, and follow the SKYRIS assembly guide.
* Before every flight the pre-test checklist ([09](09_Pretest_Checklist.md)) checks props, frame, cables and the kill switch.

## 8.3 Maintainability

| What | How it is replaced or changed without rebuilding the system |
|---|---|
| Thermal camera | Unplug USB, slide out of the cradle; the node reopens the device automatically |
| Battery, props | Standard platform parts |
| Mission parameters | YAML or the dashboard; no code change ([07](07_Integration.md)) |
| Neural networks | Replace the model folder; ONNX fallback is automatic if the NPU model is missing |
| Our software on the drone | `setup/deploy_to_drone.sh`; the platform's own software is not modified |
| Thermal service | `setup/install_thermal_service.sh` installs it, `--undo` restores the stock camera node; backups of the changed launch files are kept on the drone |
| Logs | Every run in `runs/<case>_<time>/`; the dashboard copies them back |
