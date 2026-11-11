# Third-party components

This project is licensed under the GNU AGPL-3.0 (see [LICENSE](LICENSE)). The AGPL was chosen because the training and export pipeline uses Ultralytics YOLO, which is AGPL-3.0. The components below are used, not redistributed, unless stated otherwise.

| Component | Used for | Licence |
|---|---|---|
| Ultralytics YOLO11 (and the trained weights derived from it in `models/`, `weights/`) | Training, export, detection models | AGPL-3.0 |
| PyTorch | Training | BSD-3-Clause |
| ONNX, ONNX Runtime | Model format, CPU inference | Apache-2.0 / MIT |
| Rockchip RKNN Toolkit 2 / RKNN Toolkit Lite 2 | NPU conversion and inference | BSD-3-Clause |
| OpenCV | Image processing, camera access | Apache-2.0 |
| NumPy | Numerics | BSD-3-Clause |
| PyYAML | Configuration | MIT |
| ROS Noetic, MAVROS | Middleware, MAVLink bridge | BSD-3-Clause / GPLv3, LGPLv3, BSD |
| PX4 Autopilot | Flight controller firmware (on the platform) | BSD-3-Clause |
| SKYRIS TECHNIC software (`technic`, `aruco_pose`, `simple_offboard`) | Platform API, ArUco positioning (on the platform image) | See the SKYRIS repositories |
| PySide6 / Qt | Desktop tool in `studio/` | LGPLv3 |
| matplotlib, pandas, openpyxl, python-pptx, markdown | Reports and documents | PSF-compatible / BSD / MIT |
| Microsoft COCO dataset (pretrained car detector) | `weights/yolo11n_416.*` | CC BY 4.0 (annotations) |

The ArUco map `config/aruco_map_750x450_id100.txt` was provided by the competition organisers.
