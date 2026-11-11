# Model `fire`

* task: detect
* base: yolo11n.pt
* train images: 209
* imgsz: 640, epochs run: see train/results.csv

| class | precision | recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| **all** | 0.993 | 1.000 | **0.995** | 0.741 |
| fire | 0.993 | 1.000 | 0.995 | 0.741 |

Plots: `train/` (results.png, confusion_matrix.png, PR_curve.png, val_batch*_pred.jpg)
