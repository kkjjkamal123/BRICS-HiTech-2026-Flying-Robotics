# 3. Design materials and components

## 3.1 Components, equipment and technical solutions

| No. | Component / assembly | Function in the system | Key specifications | Selection rationale / comments |
|---|---|---|---|---|
| 1 | SKYRIS TECHNIC 6S airframe | Carrier platform | Carbon frame, 4 arms, clip-on prop guards, TPU landing legs | Competition platform; guarded props for indoor flight |
| 2 | PX4 flight controller | Stabilisation, EKF2 state estimation, motor control | PX4 v1.17.0, EKF2 (vision + flow + range), offboard via MAVROS on TELEM2 at 921600 baud | Open-source, offboard API, GPS-denied fusion |
| 3 | 4-in-1 ESC + 4 motors | Propulsion | PWM 400 Hz, 1100 µs idle | Platform standard |
| 4 | 6S battery | Power | 6 cells, 21.9–24.8 V observed in our flights; low-voltage landing at 3.5 V/cell | Platform standard |
| 5 | Orange Pi 5 Pro + SKYRIS Shield | Onboard computer: ROS, perception, mission | RK3588S, 6 TOPS NPU, Ubuntu 20.04, ROS Noetic | NPU makes ≥ 10 FPS with three neural networks possible |
| 6 | Main camera (down) | ArUco navigation, optical flow, flame and car detection | 640 × 480 @ 30 Hz, calibrated (fx ≈ 484 px) | Shared with the navigation stack, already calibrated |
| 7 | TR256i thermal camera (down) | Temperature map, thermal detection | 256 × 192, ~25 Hz, raw 16-bit (Kelvin × 64), −15…600 °C | Radiometric: real °C per pixel, not just a picture |
| 8 | VL53L1X rangefinder | Height above the floor for EKF2 | 0–4 m, ~9.4 Hz, I²C | Height reference in GPS-denied flight |
| 9 | ArUco marker field | Absolute position | 7.5 × 4.5 m, 45 markers (IDs 100–144), 0.25 m markers, 0.75 m pitch, origin at the field centre | Provided by the organisers; our fence is tied to it |
| 10 | WS281x LED ring | Visual alarm | 58 LEDs | Red flash when a source is confirmed |
| 11 | RC transmitter (ExpressLRS / CRSF) | Manual override, kill switch | Channel 8 = kill switch (`RC_MAP_KILL_SW=8`) | Mandatory by the competition rules |
| 12 | Ground station laptop (macOS) | Operator interface | BRICS Dashboard, Wi-Fi | Native app, works offline |
| 13 | Thermal camera mount (our design) | Holds the TR256i looking down beside the main camera | PETG, 21.5 g, no supports, strap mounting | Lightweight, keeps the lens window clear, landing legs remain the lowest point |
| 14 | Software (ours) | Mission, perception, safety, dashboard | Python 3.8 on the drone, Swift on the ground station | See [05_Architecture.md](05_Architecture.md) |

## 3.2 Drawings, 3D models and diagrams

All CAD was built in Autodesk Fusion from scripts in [`../cad/`](../cad/) (see [`../cad/README_CAD.md`](../cad/README_CAD.md)). The SKYRIS kit has no published CAD, so the airframe model is reconstructed from the vector figures of the SKYRIS assembly guide. Board outlines and connectors use real sizes. The guard and leg curves are approximate.

| Material | File |
|---|---|
| Full aircraft assembly with all electronics and 64 wires | [`../cad/out/TECHNIC6S_with_thermal_mount_assembly.step`](../cad/out/TECHNIC6S_with_thermal_mount_assembly.step), [`../cad/out/BRICS_aerial_robotics_CAD.f3d`](../cad/out/BRICS_aerial_robotics_CAD.f3d) |
| Thermal camera mount (down / forward) | [`../cad/out/TR256i_mount_down.stl`](../cad/out/TR256i_mount_down.stl), [`.step`](../cad/out/TR256i_mount_down.step), [`../cad/out/TR256i_mount_forward.stl`](../cad/out/TR256i_mount_forward.stl) |
| Technical drawing of the mount (A3) | [`../cad/out/Drawing_TR256i_mount_down.pdf`](../cad/out/Drawing_TR256i_mount_down.pdf) |
| Wiring diagram and connection table | [`../cad/out/TECHNIC6S_wiring_diagram.pdf`](../cad/out/TECHNIC6S_wiring_diagram.pdf) |

![Aircraft model](../cad/out/technic6s_iso.png)

![Prop guard and landing gear](../cad/out/technic6s_guard_landing_gear.png)

![Thermal camera mount under the drone](../cad/out/render_down_drone_side.png)

![Wiring diagram](../cad/out/TECHNIC6S_wiring_diagram.png)

## 3.3 Mount verification (in CAD)

Checked by `cad/fusion_verify_mount.py`: single solid; mass < 30 g; the camera touches only the four crush ribs; the 56° lens cone is clear; the only overhangs are 2.2 mm lips (prints without supports); every strap slot has a free path; the STL is watertight. The full aircraft model passes an interference check of all 265 bodies with no unintended overlaps.

## 3.4 Photos of the completed prototype

Flight snapshots taken by the drone itself at the moment a source was confirmed are in [`../evidence/flights/`](../evidence/flights/). Example from the 21:20 survey (RGB camera, flame lamp confirmed):

![Flame lamp confirmed in flight](../evidence/flights/case1_fire_20261110_212037/snapshots/obj002_flame.jpg)
