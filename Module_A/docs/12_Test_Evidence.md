# 12. Test evidence so far

All files referenced here are in [`../evidence/`](../evidence/). Flight times are the drone's clock.

## 12.1 Flight tests

| Date / time | Test | Result | Evidence |
|---|---|---|---|
| 9 Nov | Hover 1.5 m, 5 s position hold, land | Passed | [`hover_20261109_172036.csv`](../evidence/flight_tests/hover_20261109_172036.csv) |
| 10 Nov | ArUco roam on the venue map | Passed | [`roam_20261110_144903.csv`](../evidence/flight_tests/roam_20261110_144903.csv) |
| 10 Nov | Lawn-mower survey, return to start, land (120 s) | Passed; landed at (0.012, 0.016) vs start (0.02, 0.01) in the map frame | [`roam_20261110_175340.csv`](../evidence/flight_tests/roam_20261110_175340.csv) |
| 10 Nov 17:56 | Case 1 mission, first attempt | Wrong (placeholder) area in the config: the drone headed past the marker field; landed by the pilot. Led to the map-boundary check | [`case1_fire_20261110_175559`](../evidence/flights/case1_fire_20261110_175559/) |
| 10 Nov 18:53, 18:57 | Case 1 mission, full survey | Completed; heat source found by the thermal channel, lamp by the RGB network; 13.9 / 13.3 FPS. One source was mapped several times → tracker changed | [`185333`](../evidence/flights/case1_fire_20261110_185333/), [`185700`](../evidence/flights/case1_fire_20261110_185700/) |
| 10 Nov 21:11 | Case 1 mission with the new tracker and self-calibration | Completed; one entry per source; ≥ 10 FPS in 100 % of seconds | [`211101`](../evidence/flights/case1_fire_20261110_211101/) |
| 10 Nov 21:20 | Case 1 mission, one-click start | First attempt: PX4 refused to arm → stopped safely ([`181724`](../evidence/flights/case1_fire_20261110_181724/)). Second attempt completed; two flame lamps mapped once each; ≥ 10 FPS in 100 % / 99 % of seconds | [`212037`](../evidence/flights/case1_fire_20261110_212037/) |

## 12.2 Processing rate (C4)

| Flight | RGB mean FPS / % of seconds ≥ 10 | Thermal mean FPS / % of seconds ≥ 10 |
|---|---|---|
| 18:57 | 13.9 / 98.6 % | 13.3 / 98.0 % |
| 21:11 | 13.2 / 100 % | 12.9 / 100 % |
| 21:20 | 13.8 / 100 % | 13.3 / 99.1 % |

These flights ran the RGB flame and car networks. The thermal network was added on 11 Nov; its frame rate in flight is the next test.

## 12.3 Neural networks

| Model | Data | Result | Files |
|---|---|---|---|
| Thermal YOLO11n (`fire`, `flame`), 256 px | 904 thermal frames from our venue flights; validation = two whole flights not used for training (18:57 and 21:20) | **mAP@0.5 0.987** (fire 0.995, flame 0.979), precision 0.989, recall 0.933 | [`../models/thermal_fire/metrics.md`](../models/thermal_fire/metrics.md), plots in `models/thermal_fire/train/` |
| RGB YOLO11n flame lamp, 416 px | 257 frames from two venue videos, split by frame blocks | mAP@0.5 0.995, precision 0.993, recall 1.0 | [`../models/fire/metrics.md`](../models/fire/metrics.md) |
| COCO YOLO11n (car), 416 px | Pretrained | — | `weights/yolo11n_416.onnx` |

Labelling of the thermal frames is reproducible with [`../train/label_thermal_flights.py`](../train/label_thermal_flights.py): one class by shape (round heat source vs flame lamp coil), frames with ambiguous objects at the image edge left out.

## 12.4 NPU benchmark on the drone

| Model | CPU (onnxruntime) | NPU (RKNN) | Same result CPU vs NPU |
|---|---|---|---|
| Thermal network, 256 px, 117 frames of the 21:20 flight | 83.1 ms | **13.4 ms** | 117 / 117 frames |
| RGB flame network, 416 px, 12 validation images | 228 ms | **40 ms** | 12 / 12 |

## 12.5 Software tests

| Test | Where | Result |
|---|---|---|
| `tests/test_flight_safety.py` (22 tests) | On the drone, 11 Nov | All pass |
| `tests/test_thermal_nn.py` (8 checks) | On the drone and the laptop, 11 Nov | All pass |
| `tests/sim_case1_venue.py` (8 scenarios) | Laptop, 11 Nov | 8 / 8: exactly one fire and one flame, ≤ 0.05 m error, warm laptop ignored |

## 12.6 Still to be measured in Module B

Coordinate accuracy against tape-measured positions (C5), car detection with the expert's car model (C3), Return Home reaction time (C7), and the frame rate with the thermal network in flight (C4).
