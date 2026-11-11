# Changelog

## 1.1.0 (build 2) - 2026-11-06

### Flight safety
- **Geofence and altitude limit.** Leaving the mission area + 1 m, or climbing above `safety.max_altitude` (default 3 m), lands the drone.
  Waypoints and inspection targets outside the fence are skipped and never flown. The fence is derived from the mission
  automatically (area, home, swarm pads, towers + orbit radius, waypoints). You can also set it with `safety.fence` / `safety.fence_margin`.
- **Takeoff no longer "continues" when the drone did not take off.** If PX4 refuses to arm (navigate rejected) or the drone is still
  disarmed after the timeout, the mission stops. Operator ABORT/RETURN, battery and link checks now also work during takeoff.
- **No more unintended starts.** A closed stdin (`nohup`, service, IDE) used to count as "Enter" and started the mission without the
  operator. Now only a real Enter or the START button starts it. ABORT/LAND before START cancels the flight without arming.
- **Case 4 (power line): the plan never crosses the wires.** Before, the default plan crossed the wire span diagonally at wire height
  (orbit 2 → span start, and on the way home), and full circles crossed the wires at every orbit. Now it flies arcs on one side of the line,
  interleaved with the span passes, and routes transits and the way home around the line ends when needed. The old full circles are
  still available as `orbit.full_circle: true`.
- **Case 3 (swarm): drones stay in their height layer.** Each drone climbs vertically to its layer above its own pad. When it marks an
  infected tree it hovers in its own layer: before, it descended diagonally through the other drones' layers. Planner ABORT ALL / RETURN ALL
  now act on the drone immediately, even between zones.
- Inspection hover (Case 1 and generic missions): horizontal at survey height → straight down → hover → straight up → back. No diagonal descents.
- Pre-flight refuses to start if the drone is already armed (the takeoff would climb relative to the current height), if the start
  position is outside the fence, or if a planned height is above the limit.
- `land()` checks the land service answer, retries once, and warns loudly if the drone is still armed ("land with the RC").
- Exceptions while returning home (not only MissionAbort) now still lead to a landing.
- Operator UI: new **RETURN HOME** button (fly home, then land). LAND / ABORT still land in place.

### Bugs
- Survey lawnmower left the far edge of the area unflown when the size was not a multiple of the line spacing. Lines are now spread
  evenly from edge to edge.
- Case 4 reported "ghost" defects positioned at an assumed distance (no triangulation). Objects are now confirmed only after real 3D triangulation.
- Confirmed objects are numbered 1, 2, 3 ... (unconfirmed candidates no longer use up IDs, which caused gaps like "#1, #3").
- A drone that lost its position (NaN) broke the swarm dashboard (invalid JSON). The same could happen on the operator UI.
- Weed map survey analysis ignored the camera orientation (`image_up_is_forward`) and floor height used in flight. The mission now saves
  `camera_meta.json` and the analysis uses it. A zero heat-map cell size could also crash it.
- Two missions started in the same second crashed on the run folder name.
- `deploy_to_drone.sh` copied `build/` (1.9 GB), the Windows wheels, the apps, `deliverables/`, `cad/` and a 400 MB crash dump to the drone.
  `deploy_to_drone.py` copied the crash dump too.
- Mock swarm runs appended test alerts to the real `swarm_alerts.csv`. They now go to `runs/swarm_mock_alerts.csv`.

### Mission Studio
- Desktop app: a corrupt project file or a config with a YAML error no longer leaves a blank or dead page. The YAML editor opens with
  the error shown so you can fix it. Quick settings are validated (area has 4 numbers with x0 < x1, home has 2, tower pairs, safe ranges
  for altitude / speed / time / cell voltage, planner URL). Config and project files are written atomically.
- Window title and Help page show the app and toolkit versions. Finishing a training run no longer jumps away from the page you are on.
- Web studio (`studio.py`): requests from other web sites are refused (Host / Origin / JSON checks against CSRF and DNS rebinding).
  The drone IP is validated before it is used in a shell command (command injection). `/api/md` and `/api/open` stay inside the toolkit
  folder. Missing project or unknown action returns an error instead of dropping the connection.
- The self-test button runs without training.
- The .app now has a real version (`CFBundleShortVersionString` 1.1.0, `CFBundleVersion` 2). `setup/build_apps.sh --mac` / `--win`
  builds one platform only.

### Tests and tools
- New `tests/test_flight_safety.py` (20 tests): geofence, takeoff/arming failures, start/abort/return, stdin EOF, inspection moves,
  Case 4 "never crosses the wires" on 4 line layouts, swarm layers, planner NaN robustness, triangulation ghosts, studio input checks,
  Cube parameter audit.
- `tests/run_all_tests.py`: checks exit codes (the compile check always passed before), `--no-train` / `--quick`, a timeout per check,
  free ports for the swarm test, no operator UI ports needed. Mock runs are repeatable: the mock drone uses a virtual clock in step
  with the camera frames, so a busy computer no longer makes detections flaky.
- New `tools/param_audit.py`: safety audit of an ArduCopter parameter file (arming checks, radio / battery failsafes, disarm delay,
  arm and emergency-stop switches, flight modes without GPS). `--write-safe` writes only the required changes. The input file is never modified.
- `VERSION` file and `common/version.py` (single source of the version).

### Documents
- `4_Cube_FirstFlight_Checklist.md` corrected (see the file): mandatory "safety settings back on" step before any flight. The radio
  failsafe test needs `FS_THR_ENABLE` set first. The arm switch is CH6 HIGH (stock FS-i6: SwA **down**), not "SwA up". The CH7 motor
  emergency stop is now explained. QGC cannot load the Mission Planner-format backup, and restoring it as a whole restores the unsafe state.
  Battery failsafe values added for 3S. Disarming with SwA in the air drops the drone; SwC down = Land is the normal emergency action.
- README updated (safety features, Case 3/4 behaviour, self-test options). `3_Toolkit_Manual.pdf` regenerated from it.
