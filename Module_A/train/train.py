#!/usr/bin/env python3
"""
train.py - ONE command: any dataset -> best model -> exported for the drone.

  python train/train.py --data <anything> --name fire

<anything> can be: a raw dataset folder / .zip in ANY supported format (auto-converted with
prepare_dataset.py), a prepared folder, a data.yaml, or a classification folder.

What it does:
  1. converts / checks the dataset, detects the task (detect / segment / classify)
  2. picks model size + epochs from dataset size and --quality (fast | balanced | best)
  3. trains from the pretrained weights in weights/ (works OFFLINE), early-stops, keeps the best epoch
  4. validates: mAP50, mAP50-95, precision, recall per class  -> models/<name>/metrics.md
  5. exports models/<name>/best.onnx (for the Orange Pi CPU / our detector) and checks it matches PyTorch
  6. prints the exact config lines to use the model in a mission

Examples:
  python train/train.py --data datasets/raw/fire.zip --name fire                    # everything automatic
  python train/train.py --data datasets/fire/data.yaml --name fire --quality best
  python train/train.py --data datasets/fire --name fire --hours 1.5                # stop after 1.5 h
  python train/train.py --data datasets/weeds --name weeds --aerial --imgsz 960     # small objects from above
  python train/train.py --data datasets/fire --name fire --arch yolo26              # newest architecture
  python train/train.py --data models/fire/train/weights/last.pt --resume           # continue after a crash
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)
os.environ.setdefault("YOLO_OFFLINE", "1")


def pick_device(req):
    if req and req != "auto":
        return req
    import torch
    if torch.cuda.is_available():
        return "0"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def resolve_data(data, name):
    """Return (data_arg_for_ultralytics, task, n_train_images, names)."""
    import yaml
    p = data
    if os.path.isdir(p) and os.path.exists(os.path.join(p, "data.yaml")):
        p = os.path.join(p, "data.yaml")
    if p.endswith((".yaml", ".yml")) and os.path.exists(p):
        y = yaml.safe_load(open(p))
        if not os.path.isabs(str(y.get("path", ""))) or not os.path.isdir(str(y.get("path", ""))):
            # dataset made elsewhere (Roboflow) -> normalise it
            return resolve_data(_prepare([os.path.dirname(os.path.abspath(p))], name), name)
        base = y["path"]
        tr = os.path.join(base, y["train"]) if isinstance(y["train"], str) else os.path.join(base, y["train"][0])
        imgs = [f for f in glob.glob(os.path.join(tr, "**", "*.*"), recursive=True) if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"))]
        lbl_dir = tr.replace(os.sep + "images", os.sep + "labels")
        task = "detect"
        for lf in glob.glob(os.path.join(lbl_dir, "*.txt"))[:200]:
            for line in open(lf):
                if len(line.split()) > 5:
                    task = "segment"
                break
            if task == "segment":
                break
        n = y["names"]
        names = [n[k] for k in sorted(n)] if isinstance(n, dict) else list(n)
        return p, task, len(imgs), names
    if os.path.isdir(p) and os.path.isdir(os.path.join(p, "train")) and not glob.glob(os.path.join(p, "train", "*.txt")):
        classes = sorted(d for d in os.listdir(os.path.join(p, "train")) if os.path.isdir(os.path.join(p, "train", d)))
        if classes and not os.path.isdir(os.path.join(p, "train", "images")):
            n = len(glob.glob(os.path.join(p, "train", "*", "*.*")))
            return os.path.abspath(p), "classify", n, classes
    # raw dataset in any format
    return resolve_data(_prepare([p], name), name)


def _prepare(inputs, name):
    from train import prepare_dataset
    out = os.path.join(ROOT, "datasets", name)
    print("[train] converting dataset with prepare_dataset.py -> %s" % out)
    return prepare_dataset.main(list(inputs) + ["--out", out])


PRESETS = {      # (model size by #train images, epochs, patience)
    "fast":     (lambda n: "n", 40, 15),
    "balanced": (lambda n: "n" if n < 400 else "s", 120, 30),
    "best":     (lambda n: "s" if n < 1500 else "m", 250, 50),
}


def base_weights(arch, size, task):
    suffix = {"detect": "", "segment": "-seg", "classify": "-cls"}[task]
    cand = ["%s%s%s.pt" % (arch, size, suffix), "%sn%s.pt" % (arch, suffix), "yolo11%s%s.pt" % (size, suffix),
            "yolo11n%s.pt" % suffix]
    for c in cand:
        p = os.path.join(ROOT, "weights", c)
        if os.path.exists(p):
            if c != cand[0]:
                print("[train] %s not available offline -> using %s" % (cand[0], c))
            return p
    print("[train] WARNING no local weights for %s - ultralytics will try to download %s" % (task, cand[0]))
    return cand[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--name", default=None, help="model name -> models/<name>/")
    ap.add_argument("--quality", choices=list(PRESETS), default="balanced")
    ap.add_argument("--arch", default="yolo11", choices=["yolo11", "yolo26"], help="yolo11 = most compatible")
    ap.add_argument("--model", help="explicit base weights (overrides --arch/--quality size)")
    ap.add_argument("--task", choices=["auto", "detect", "segment", "classify"], default="auto")
    ap.add_argument("--epochs", type=int)
    ap.add_argument("--patience", type=int)
    ap.add_argument("--hours", type=float, help="max training time in hours (overrides epochs)")
    ap.add_argument("--imgsz", type=int, default=None, help="default 640 (detect) / 224 (classify)")
    ap.add_argument("--batch", type=int, default=None)
    ap.add_argument("--device", default="auto", help="auto | cpu | mps | 0")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--aerial", action="store_true", help="top-down drone images: vertical flips + rotations")
    ap.add_argument("--export-imgsz", type=int, default=None, help="ONNX input size (smaller = faster on the Pi)")
    ap.add_argument("--no-export", action="store_true")
    ap.add_argument("--resume", action="store_true", help="--data is a last.pt to resume")
    ap.add_argument("--extra", nargs="*", default=[], help="extra ultralytics args key=value")
    a = ap.parse_args(argv)

    from ultralytics import YOLO
    from ultralytics import settings as ysettings
    try:
        ysettings.update({"sync": False})
    except Exception:
        pass

    if a.resume:
        YOLO(a.data).train(resume=True)
        return

    name = a.name or os.path.splitext(os.path.basename(a.data.rstrip("/")))[0]
    data, task, n_train, names = resolve_data(a.data, name)
    if a.task != "auto":
        task = a.task
    size_fn, epochs, patience = PRESETS[a.quality]
    size = size_fn(n_train)
    weights = a.model or base_weights(a.arch, size, task)
    epochs = a.epochs or (epochs if n_train >= 100 else int(epochs * 1.5))   # tiny datasets need more epochs
    patience = a.patience or patience
    device = pick_device(a.device)
    imgsz = a.imgsz or (224 if task == "classify" else 640)
    batch = a.batch or ((64 if task == "classify" else 16) if size in ("n", "s") else 8)
    out_dir = os.path.join(ROOT, "models", name)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    print("=" * 70)
    print("[train] task=%s  classes=%s  train images=%d" % (task, names, n_train))
    print("[train] base=%s  epochs=%d  patience=%d  imgsz=%d  batch=%d  device=%s" % (
        os.path.basename(weights), epochs, patience, imgsz, batch, device))
    print("=" * 70)

    args = dict(data=data, epochs=epochs, patience=patience, imgsz=imgsz, batch=batch, device=device,
                project=out_dir, name="train", exist_ok=True, workers=a.workers, seed=0, plots=True,
                cos_lr=(a.quality == "best"), close_mosaic=10, verbose=True)
    if a.hours:
        args["time"] = a.hours
    if a.aerial and task != "classify":
        args.update(flipud=0.5, degrees=15.0, scale=0.5)
    for kv in a.extra:
        k, v = kv.split("=", 1)
        try:
            v = json.loads(v)
        except ValueError:
            pass
        args[k] = v

    t0 = time.time()
    model = YOLO(weights)
    model.train(**args)
    best = os.path.join(out_dir, "train", "weights", "best.pt")
    if not os.path.exists(best):
        best = os.path.join(out_dir, "train", "weights", "last.pt")
    shutil.copy2(best, os.path.join(out_dir, "best.pt"))
    open(os.path.join(out_dir, "names.txt"), "w").write("\n".join(names) + "\n")
    print("[train] finished in %.1f min -> %s/best.pt" % ((time.time() - t0) / 60, out_dir))

    # ---- validation metrics (for the Module B test report!)
    m = YOLO(os.path.join(out_dir, "best.pt"))
    md = ["# Model `%s`" % name, "", "* task: %s" % task, "* base: %s" % os.path.basename(weights),
          "* train images: %d" % n_train, "* imgsz: %d, epochs run: see train/results.csv" % imgsz, ""]
    try:
        r = m.val(data=data, imgsz=imgsz, device=device, plots=True, project=out_dir, name="val", exist_ok=True, verbose=False)
        if task == "classify":
            md += ["| metric | value |", "|---|---|", "| top1 accuracy | %.3f |" % r.top1, "| top5 accuracy | %.3f |" % r.top5]
        else:
            box = r.seg if task == "segment" else r.box
            md += ["| class | precision | recall | mAP50 | mAP50-95 |", "|---|---|---|---|---|",
                   "| **all** | %.3f | %.3f | **%.3f** | %.3f |" % (box.mp, box.mr, box.map50, box.map)]
            for i, c in enumerate(r.box.ap_class_index):
                p, rc, ap50, ap = box.class_result(i)
                md.append("| %s | %.3f | %.3f | %.3f | %.3f |" % (m.names[int(c)], p, rc, ap50, ap))
    except Exception as e:
        md.append("validation failed: %s" % e)
    md += ["", "Plots: `train/` (results.png, confusion_matrix.png, PR_curve.png, val_batch*_pred.jpg)"]
    open(os.path.join(out_dir, "metrics.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))

    # ---- export ONNX + self-check with our runtime-independent detector
    if not a.no_export:
        from train.export_model import export
        export(os.path.join(out_dir, "best.pt"), formats=["onnx"], imgsz=a.export_imgsz or imgsz, data=data)

    print("\n" + "=" * 70)
    print("USE IT in a mission config (detectors:):")
    print("  - type: yolo\n    model: models/%s/best.onnx\n    conf: 0.4" % name)
    print("TEST IT:   python train/predict.py --model models/%s/best.onnx --source <images|video|0>" % name)
    print("FOR NPU:   python train/export_model.py models/%s/best.pt --formats rknn   (Linux / Docker)" % name)
    print("=" * 70)


if __name__ == "__main__":
    main()
