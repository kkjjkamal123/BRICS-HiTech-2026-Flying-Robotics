# Model `thermal_fire`

* task: detect
* base: yolo11n.pt
* train images: 660
* imgsz: 256, epochs run: see train/results.csv

| class | precision | recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| **all** | 0.989 | 0.933 | **0.987** | 0.743 |
| fire | 0.991 | 1.000 | 0.995 | 0.791 |
| flame | 0.988 | 0.867 | 0.979 | 0.695 |

Plots: `train/` (results.png, confusion_matrix.png, PR_curve.png, val_batch*_pred.jpg)
