# 11. Technical specification (Case 1)

All coordinates in metres in the `aruco_map` frame (origin = field centre). Items marked **[to agree]** are fixed with the lead expert before testing starts.

## 11.1 Seven mandatory verifiable characteristics

| No. | Characteristic | Unit | Threshold | Measurement method | Evidence file |
|---|---|---|---|---|---|
| C1 | Autonomous flight along the predefined route | % of planned waypoints reached without RC input | 100 %, each within 0.25 m | Planned waypoints (`log.txt` `[plan]`) vs flown path (`path.csv`), RC untouched on video | `log.txt`, `path.csv` |
| C2 | Neural-network detection of the simulated flame in thermal images | mAP@0.5 | ≥ 0.85 | Thermal frames saved every 1 s in the scored flight are labelled and evaluated with the flight model (`yolo val`) | `frames/`, labels, mAP printout |
| C3 | Detection of the additional object (car) | Detected / placed | 1 of 1, correct class | Expert places the car model; confirmed `car` in `objects.json` | `objects.json`, `events.csv` |
| C4 | Onboard processing rate on the NPU | % of 1-s intervals of airborne time with ≥ 10 processed frames | > 90 % | Every perception cycle is logged; `fps_summary.json` computes the share | `perf.csv`, `fps_summary.json` |
| C5 | Accuracy of object coordinates | m, horizontal error | ≤ 0.5 m | Expert tape-measures each target from the field centre; compared with `objects.json` | `objects.json`, photo of measurement |
| C6 | Real-time display of detections on the map with type and time | s from confirmation to display | ≤ 2 s | Screen recording of the dashboard vs confirmation time in `events.csv` | `events.csv`, screen recording |
| C7 | Autonomous return on operator command | s reaction / m landing error | ≤ 2 s / ≤ 0.5 m from home | Operator presses Return Home; `[ui] operator pressed RETURN` vs `[phase] RETURN`; landing point vs home | `log.txt`, `path.csv` |

Also covered in the end-to-end scenario: every event is logged (time, coordinates, type, confidence) in `events.csv`; at least one flame detection per flight.

## 11.2 Three functional modules

| Module | Contents | Separately verifiable function | Pass criterion |
|---|---|---|---|
| M1 Flight and navigation | PX4 EKF2 (vision + flow + range), SKYRIS offboard, mission planner, safety layer | Take-off to 1.5 m, 5 s hold, land (`tools/hover_test.py`) | Height 1.5 ± 0.15 m; drift ≤ 0.2 m; lands and disarms without RC |
| M2 Thermal and visual perception | TR256i + thermal node, thermal YOLO, RGB YOLO, car YOLO on the NPU, tracker | Drone held still 1.5 m above the heat source / lamp | Source confirmed within 3 s; ≥ 10 FPS |
| M3 Ground station and logging | Mission link, BRICS Dashboard, logs | Bench test with a detection | Object on the map with type, coordinates and time; row in `events.csv`; command logged within 1 s |

## 11.3 End-to-end scenario

**Initial conditions:** drone on the home position (field centre), battery ≥ 3.8 V/cell, venue marker map loaded, heat source, flame lamp and car model placed by the expert at positions unknown to the team.

**Sequence:** Run mission → pre-flight → take-off to 1.0 m → survey at 1.5 m → each confirmed source: alarm, inspection hover, snapshot → expert signal → Return Home → landing → report.

**Pass:** C1–C7 thresholds met; no manual piloting; total time ≤ 9 min.

**Attempts:** [to agree]. **Permitted recovery:** battery swap, restart from the dashboard, placing the drone back on home, automatic safety landing followed by a restart. **Not permitted during the scenario:** changes to code, configuration or hardware.

## 11.4 Connection configurations

CC1 (drone access point) and CC2 (drone on a router / hotspot), see [07_Integration.md](07_Integration.md).

## 11.5 Additional functions

| No. | Function | Verification | Pass criterion | New component |
|---|---|---|---|---|
| AF1 | Automatic close inspection of each confirmed source | Source placed in the area | Hover point ≤ 0.3 m from the reported position; snapshot saved | Inspection behaviour in `drone/mission_base.py` |
| AF2 | Automatic safety landing (geofence, battery, marker loss, time) | Run with a small fence in the config | Lands automatically; reason in `log.txt` | Safety layer in `drone/technic_api.py` |
| AF3 | Temperature of every source shown on the map | Heat source in view | °C value matches `/thermal/max` | Thermal node + °C check in `common/detector.py` |
