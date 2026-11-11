# Module A: Autonomous Forest Fire Monitoring UAV (Case 1)

**BRICS Hi-Tech Future Skills 2026 · Flying Robotics · Chennai Institute of Technology**
Kamalesh Vadivelu Syamala · Bejin Paul Josephin Paul Benjamin

An autonomous quadcopter (SKYRIS TECHNIC 6S) that flies a survey route without GPS, finds ignition sources with neural networks running on its NPU (thermal and RGB cameras), measures their temperature, puts them on a live map with type and time, and reports everything to the operator's dashboard.

## Results so far

* Autonomous survey flights on the venue marker map: completed, return to the start point, automatic landing.
* Thermal neural network (heat source + flame lamp): **mAP@0.5 0.987** on two flights not used for training.
* RGB flame network: mAP@0.5 0.995. All networks on the NPU (13.4 ms and 40 ms per frame).
* Onboard processing in flight: 13–14 FPS, ≥ 10 FPS in 98–100 % of airborne seconds.
* 22 flight-safety tests and 8 venue-simulation scenarios pass.

Details: [docs/12_Test_Evidence.md](docs/12_Test_Evidence.md).

## Documentation (Module A)

| # | Document | Requirement |
|---|---|---|
| 1 | [Technical description](docs/01_Technical_Description.md): purpose, characteristics, block diagram, key decisions | Submission 1 |
| 2 | [Team roles](docs/02_Team_Roles.md) | Submission 2 |
| 3 | [Design materials and components](docs/03_Design_Materials_and_Components.md): component table, CAD, drawings, wiring | Submission 3 |
| 4 | [Relevance and existing solutions](docs/04_Relevance_and_Existing_Solutions.md) | Rec. 1, 2 |
| 5 | [Extended architecture](docs/05_Architecture.md): components, interfaces, sequence, failures, strengths/limitations | Rec. 3 |
| 6 | [Tool selection](docs/06_Tool_Selection.md) | Rec. 4 |
| 7 | [Integration](docs/07_Integration.md): interfaces, two connection configurations, configurable parameters | Rec. 5 |
| 8 | [Safety and maintainability](docs/08_Safety_and_Maintainability.md) | Rec. 6 |
| 9 | [Pre-test checklist](docs/09_Pretest_Checklist.md) | Rec. 7 |
| 10 | [Operation, deployment and scaling](docs/10_Operation_and_Deployment.md) | Rec. 9 |
| 11 | [Technical specification](docs/11_Technical_Specification.md): C1–C7, modules, scenario | Spec |
| 12 | [Test evidence](docs/12_Test_Evidence.md) | — |

## Repository layout

| Folder | Contents |
|---|---|
| `drone/` | Missions (`case1_fire.py`), mission engine, drone API with safety layer, cameras |
| `common/` | Detectors (YOLO on NPU/CPU, thermal), geometry and tracker, camera self-calibration, thermal decoding, mission link |
| `tools/` | Thermal camera node, flight tests (motor ramp, hover, ArUco roam/scan), parameter audit |
| `config/` | Mission configuration (`case1_fire.yaml`) and the venue ArUco map |
| `dashboard/` | BRICS Dashboard, native macOS ground station (SwiftUI) |
| `train/` | Dataset preparation, labelling, training, export (ONNX / RKNN) |
| `models/`, `weights/` | Trained networks (ONNX + RKNN) with metrics and training plots |
| `datasets/` | Our venue datasets (thermal and RGB) |
| `cad/` | Fusion scripts and outputs: thermal camera mount, aircraft model, wiring diagram |
| `tests/` | Flight-safety tests, thermal network tests, venue simulator |
| `evidence/` | Real flight logs, detections, snapshots, drone configuration |
| `economics/` | Economic model (Module C) |
| `setup/` | Install, deploy, model conversion, dashboard build |
| `studio/` | Desktop tool for training, simulation and document generation |

## Dependencies

| Where | Software |
|---|---|
| Drone | Stock SKYRIS TECHNIC 6S image: Ubuntu 20.04, ROS Noetic, MAVROS, SKYRIS `technic`; Python 3.8, OpenCV, NumPy, PyYAML; onnxruntime 1.19, rknn-toolkit-lite2 2.3 |
| Laptop | Python 3.11 and [`setup/requirements_laptop.txt`](setup/requirements_laptop.txt) (Ultralytics, PyTorch, ONNX Runtime, OpenCV, …); Docker for RKNN conversion |
| Ground station | macOS 26, Xcode, XcodeGen |

## Install and run

```bash
# laptop
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r setup/requirements_laptop.txt
python tests/sim_case1_venue.py                     # whole mission against the simulated venue

# drone (laptop on the drone's network)
bash setup/download_offline.sh                      # once, with internet
DRONE=<drone-ip> bash setup/deploy_to_drone.sh
ssh orangepi@<drone-ip> 'bash ~/brics_toolkit/setup/install_thermal_service.sh'

# ground station
bash setup/build_dashboard.sh                       # then open "BRICS Dashboard.app" → Run mission
```

On the drone without the dashboard:
```bash
source /opt/ros/noetic/setup.bash; source ~/technic_ws/devel/setup.bash
cd ~/brics_toolkit && python3 drone/case1_fire.py --config config/case1_fire.yaml --autostart
```

Simulation on a laptop (no drone, no ROS): `python drone/case1_fire.py --config config/case1_fire.yaml --mock --autostart`.

Full operating manual: [docs/10_Operation_and_Deployment.md](docs/10_Operation_and_Deployment.md).

## Licence

Source code: [GNU AGPL-3.0](LICENSE). Third-party components and their licences: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
