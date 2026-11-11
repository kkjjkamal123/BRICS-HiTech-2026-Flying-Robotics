# 7. Integration documentation

## 7.1 Interfaces actually used

| Interface | Endpoint | Data / signal format | Rate (measured) | Constraints |
|---|---|---|---|---|
| Flight controller ↔ onboard computer | MAVROS `fcu_url=/dev/ttyS0:921600` (PX4 TELEM2) | MAVLink 2 | — | Wired UART |
| Ground control | MAVROS `gcs_url=tcp-l://0.0.0.0:5760` | MAVLink over TCP | — | QGroundControl on the same network |
| ArUco position | `/mavros/vision_pose/pose` | `geometry_msgs/PoseStamped`, frame `aruco_map` | Only while markers are in view | Map file `aruco_map_750x450_id100.txt` |
| Optical flow | `/mavros/px4flow/raw/send` | `mavros_msgs/OpticalFlowRad` | 10 Hz | Floor texture, light |
| Rangefinder | `/rangefinder/range` → MAVROS distance sensor | `sensor_msgs/Range` | 9.4 Hz | 0–4 m |
| RGB camera | `/main_camera/image_raw`, `/main_camera/camera_info` | `sensor_msgs/Image` bgr8 640 × 480 | 30.5 Hz | — |
| Thermal camera (USB) | `/dev/camera_second` (UVC) | YUYV 256 × 384: picture + raw 16-bit Kelvin × 64 | ~25 Hz | Must be opened with colour conversion off |
| Thermal topics (our node) | `/thermal/temp`, `/thermal/image_raw`, `/thermal/max`, `/thermal/fire` | 32FC1 °C, bgr8, Float32, Bool | 24.7 Hz | Started by the `brics-thermal` service |
| Flight commands | ROS services `navigate`, `land`, `get_telemetry`, `led/set_effect`, `/mavros/set_mode` | `technic/srv/*`, `std_srvs/Trigger`, `mavros_msgs/SetMode` | `get_telemetry` ≈ 33 ms | `land` works only in OFFBOARD (fallback: AUTO.LAND) |
| Mission link | HTTP `:8090` | `GET /status` JSON, `GET /stream.mjpg` multipart JPEG, `POST /cmd?c=start\|return\|land\|abort` | Video ≤ 15 fps | Same network as the operator laptop |
| Video without a mission | HTTP `:8080` (SKYRIS web_video_server) | MJPEG | — | — |
| Administration | SSH `:22` | — | — | Password or key |
| Battery for the dashboard | `rostopic echo -p /mavros/battery` over SSH | CSV | 0.5 Hz | — |

Snapshot of the drone's interfaces and parameters: [`../../Others/evidence/drone_config/`](../../Others/evidence/drone_config/).

## 7.2 Two connection configurations

| | CC1: drone as access point | CC2: drone as client of a router / hotspot |
|---|---|---|
| Setting | SHIELD Wi-Fi slider **AP**, network `technic-xxxx` | Slider **AUTO**, network joined through the Technic web console |
| Drone address | 10.42.0.1 | DHCP: 192.168.137.239 (team hotspot, 9 Nov), 10.11.5.213 (venue network, 10–11 Nov) |
| Used for | First connection, web console, QGroundControl | SSH, deployment, dashboard, all mission flights |
| Changing between them | Dashboard: type the new address in the sidebar; scripts: `DRONE=<ip>` | Same |

The software never hard-codes an address: the dashboard keeps a list of recent drone addresses, and every script takes the address as a parameter.

**Two data sources** are also used in every flight: the RGB camera (`/main_camera/image_raw`) and the thermal camera (`/thermal/temp`). Both are logged per frame in `perf.csv` and `events.csv`.

## 7.3 Parameters changeable through configuration (no code changes)

All in [`../config/case1_fire.yaml`](../config/case1_fire.yaml). Most can also be changed from the dashboard for one run (`--set KEY=VALUE`, checked against safe limits):

| Group | Parameters |
|---|---|
| Area and route | `area`, `home`, `altitude`, `takeoff_z`, `speed`, `overlap` / `step`, `survey_camera` |
| Photos of a source | `snapshot_hover` (seconds the drone holds position), `inspect.enabled` (close inspection, off at this venue) |
| Cameras | `type` (ros / ros_thermal / cv), `topic`, `device`, `hfov_deg`, `orientation`, `image_up_is_forward` |
| Detectors | `model`, `conf`, `classes`, `every`, `min_temp_c`, `threshold_c`, `min_area` |
| Tracking | `tracker.radius`, `tracker.min_hits`, `tracker.same_object`, `class_alias`, `self_calibrate`, `min_detect_altitude` |
| Safety | `min_cell_voltage`, `battery_cells`, `max_time`, `max_altitude`, `fence`, `frame` |
| Operator link | `ui.port`, `ui.fps`, `ui.width`, `ui.quality`, `ui.start_countdown`, `ui.web_page` |

## 7.4 Changes that need code changes or a rebuild

* A thermal camera with a different raw format (new decoder in `common/thermal.py`).
* A flight stack without the `navigate` / `land` services (new class in `drone/technic_api.py`).
* A new detector type (new class in `common/detector.py`).
* New neural network weights: retraining and RKNN conversion (`train/train.py`, `setup/convert_rknn.sh`), no code change.
* Dashboard changes: Xcode rebuild (`setup/build_dashboard.sh`).
