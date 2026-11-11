# Others: supporting material

| Folder | Contents |
|---|---|
| `evidence/flights/` | Logs of the real Case 1 flights on 10 Nov 2026: `log.txt`, `events.csv` (every detection), `objects.json`, `path.csv`, `perf.csv` + `fps_summary.json` (processing rate), snapshots |
| `evidence/flight_tests/` | Hover, ArUco roam and lawn-mower flight logs |
| `evidence/drone_config/` | PX4 parameters, ROS interfaces, software versions and camera calibration read from the drone |
| `datasets/thermal_fire/` | Thermal dataset from our flights (heat source, flame lamp), YOLO format, with the labelling report |
| `datasets/flame/` | RGB dataset of the venue flame lamp, YOLO format |
| `economics/` | Economic model of the solution (NPV, IRR, payback) with results |
| `docker/` | Docker images: RKNN model converter, replica of the drone software |
| `weights/` | Pretrained COCO detector used in the first flights |

To retrain a model with these datasets, run the training scripts from `Module_A`, e.g.
`python train/train.py --data ../Others/datasets/thermal_fire/data.yaml --name thermal_fire --imgsz 256`.
