# 6. Tool selection rationale

## 6.1 Software and libraries

| Tool / library | Version | Where | Role | Selection criteria / compatibility |
|---|---|---|---|---|
| PX4 Autopilot | 1.17.0 | Flight controller | Attitude/position control, EKF2 | Supplied with TECHNIC 6S; supports vision + flow + range fusion |
| ROS Noetic | Noetic | Orange Pi | Middleware between sensors, MAVROS and our nodes | Preinstalled SKYRIS image; all platform drivers are ROS nodes |
| MAVROS | 1.20.1 | Orange Pi | MAVLink bridge, `set_mode`, battery, local position | Standard PX4 ↔ ROS bridge |
| SKYRIS `technic` (simple_offboard, aruco_pose, optical_flow) | 0.25.0 | Orange Pi | `navigate`, `land`, `get_telemetry`; ArUco positioning | Platform API; we build on it instead of re-implementing offboard control |
| Python | 3.8 (drone), 3.11 (laptop) | Both | Mission, perception, tools | Python 3.8 is the drone's ROS version; code stays 3.8-compatible |
| OpenCV | 4.2 (drone) | Both | Camera I/O, image processing, raw UVC read | Available on the image; reads the thermal camera without colour conversion |
| NumPy | 1.24 | Both | Temperature maps, geometry | — |
| Ultralytics YOLO11 | 8.4 | Laptop | Training detectors, export to ONNX/RKNN | Fast training on small venue datasets; nano model fits the NPU budget |
| ONNX Runtime | 1.19 (drone) | Both | CPU inference fallback, model check after export | Same model file on laptop and drone |
| RKNN Toolkit 2 / RKNN Lite 2 | 2.3.2 / 2.3.0 | Docker on laptop / drone | Conversion and NPU inference on RK3588 | Only way to use the 6 TOPS NPU |
| PyYAML | 5.3 | Both | Mission configuration | Human-editable configs |
| SwiftUI (Swift 6, macOS 26) | — | Ground station | BRICS Dashboard | Native, low-latency video, works offline |
| XcodeGen | — | Laptop | Generates the Xcode project from `project.yml` | Reproducible builds, no generated files in git |
| Autodesk Fusion (+ Python API) | — | Laptop | CAD of the mount and the aircraft | Scripted, verifiable models (interference, mass) |
| Docker (Colima) | — | Laptop | RKNN converter image, drone software replica | Converter needs x86/ARM Linux; keeps the laptop clean |
| Git / GitHub | — | — | Version control, submission | Required |

## 6.2 Comparison with alternatives (predefined parameters)

### Inference runtime on the drone

Parameters: latency per frame on the Orange Pi (ms), identical output to the reference model, achievable FPS of the full mission. Measured on the drone with our models:

| Model | onnxruntime (CPU) | RKNN (NPU) | Outputs identical |
|---|---|---|---|
| RGB flame model, 416 px | 228 ms | **40 ms** | 12/12 validation images |
| Thermal model, 256 px | 83 ms | **13.4 ms** | 117/117 flight frames |
| Full mission (three networks), in flight | ~1.5 FPS (first flight, CPU) | **13–14 FPS** | — |

**Choice: RKNN.** The CPU cannot reach the required 10 FPS. ONNX stays in the repository as the fallback: the mission uses it automatically if the NPU runtime is missing.

### Thermal detection method

Parameters: requirement fit (NN on thermal images), detection of the heat source in our flights, false alarms on warm non-targets.

| Method | NN on thermal images | Heat source detected in flights 21:11 and 21:20 | Warm laptop (45 °C, simulation) |
|---|---|---|---|
| Temperature threshold only (≥ 100 °C) | No | No (source visible but below the threshold) | Rejected |
| Thermal YOLO only | Yes | Yes (by shape) | **Falsely detected** |
| **Thermal YOLO + measured °C gate (chosen)** | Yes | Yes | Rejected |

### Positioning

| Option | Works indoors | Accuracy | Available on the platform |
|---|---|---|---|
| GNSS | No | — | No |
| Optical flow only | Yes | Drifts over time | Yes |
| **ArUco map + optical flow + rangefinder (chosen)** | Yes | Returned to the take-off point after a 120 s lawn-mower flight with ~1 cm difference in the map frame | Yes |

### Operator interface

| Option | Video latency | Works without a browser / internet | One-click mission start |
|---|---|---|---|
| Web page served by the drone | Higher (browser polling) | Needs a browser | Yes |
| **Native macOS app (chosen)** | Low (pushed MJPEG) | Yes | Yes |
