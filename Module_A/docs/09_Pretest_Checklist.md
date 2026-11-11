# 9. Pre-test start-up checklist (prototype readiness)

Filled in before every test session. The state recorded below is from **11 Nov 2026** (drone `technic-8655`).

| # | Check | How | Result 11 Nov |
|---|---|---|---|
| 1 | Props secure, frame and cables tight, thermal camera seated, lens clear | Visual | Filled at the test |
| 2 | Battery ≥ 3.8 V/cell | Dashboard battery / QGC | Filled at the test |
| 3 | RC on, kill switch (ch 8) stops the motors | Arm on the ground, flip ch 8 | Filled at the test |
| 4 | Laptop and drone on the same network, drone clock synced | Dashboard: Test connection, Sync drone clock | OK (venue network) |
| 5 | Venue ArUco map loaded on the drone | `rosparam get /aruco_map/map` = `aruco_map_750x450_id100.txt` | OK |
| 6 | Thermal service running, real temperatures | `/thermal/temp` 24.7 Hz, room ~20 °C | OK |
| 7 | Neural networks load on the NPU | Mission start log: thermal_fire, fire, weights "running on the NPU" | OK |
| 8 | Safety tests pass on the drone | `python3 tests/test_flight_safety.py` | OK, 22/22 |
| 9 | Thermal network tests pass on the drone | `python3 tests/test_thermal_nn.py` | OK, 8/8 |
| 10 | Mission config: area, home, fence inside the marker field | Mission refuses to start otherwise | OK |
| 11 | Drone on the home position (field centre) | Visual | Filled at the test |
| 12 | Screen and video recording started | — | Filled at the test |

**Can the system be started and the planned tests initiated?** Yes. The mission starts with one click and passes pre-flight; the last complete survey flights were on 10 Nov.

**Modifications required before testing:**

| Area | Required? | Note |
|---|---|---|
| Structure | No | — |
| Principal components | No | — |
| Software | No | Current version deployed 11 Nov (thermal neural network added) |
| Configuration | Check | Confirm `min_temp_c` for the flame lamp against `/thermal/max` with the lamp in view; confirm the frame rate with the thermal network in a test flight |
