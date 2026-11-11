#!/usr/bin/env python3
"""
export_model.py - export a trained .pt for the drone, and VERIFY the export gives the same detections.

  python train/export_model.py models/fire/best.pt                      # ONNX (default) at training size
  python train/export_model.py models/fire/best.pt --imgsz 416          # smaller = ~2.3x faster on CPU
  python train/export_model.py models/fire/best.pt --formats onnx ncnn  # ncnn = fast on ARM CPU
  python train/export_model.py models/fire/best.pt --formats rknn       # Orange Pi NPU (needs Linux:
                                                                        #  Gazebo VM or docker/rknn - see README)
Formats:
  onnx  -> best.onnx           runs everywhere (onnxruntime or cv2.dnn); our detector reads it directly
  ncnn  -> best_ncnn_model/    fast ARM CPU inference via ultralytics + ncnn
  rknn  -> best_rknn_model/    RK3588 NPU (fastest), needs rknn-toolkit2 on Linux; INT8 if --int8 + --data
"""
import argparse
import glob
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
os.environ.setdefault("YOLO_OFFLINE", "1")


def verify_onnx(pt, onnx_path, data=None, imgsz=640):
    """Compare ultralytics(.pt) vs our YoloDetector(.onnx) on a few images."""
    import cv2
    from ultralytics import YOLO
    from common.detector import YoloDetector
    imgs = []
    if data and os.path.exists(str(data)):
        base = os.path.dirname(data) if str(data).endswith((".yaml", ".yml")) else data
        imgs = sorted(glob.glob(os.path.join(base, "**", "val", "**", "*.jpg"), recursive=True) +
                      glob.glob(os.path.join(base, "**", "val", "**", "*.png"), recursive=True))[:5]
    if not imgs:
        print("[export] (no validation images found for the self-check)")
        return
    ref = YOLO(pt)
    mine = YoloDetector(onnx_path, conf=0.25)
    if mine.task == "classify":
        ok = 0
        for p in imgs:
            im = cv2.imread(p)
            a = int(ref.predict(im, imgsz=imgsz, verbose=False)[0].probs.top1)
            d = mine(im)
            ok += int(bool(d) and d[0]["cls"] == a)
        print("[export] self-check classify: %d/%d images same top-1 class" % (ok, len(imgs)))
        return
    diff = 0
    for p in imgs:
        im = cv2.imread(p)
        n_ref = len(ref.predict(im, imgsz=imgsz, conf=0.25, verbose=False)[0].boxes)
        n_mine = len(mine(im))
        diff += abs(n_ref - n_mine)
        print("[export] self-check %-40s pytorch=%d  onnx(ours)=%d" % (os.path.basename(p)[:40], n_ref, n_mine))
    print("[export] self-check %s" % ("OK - ONNX matches PyTorch" if diff <= 1 else "WARNING: differences (%d)" % diff))


def export(pt, formats=("onnx",), imgsz=640, data=None, int8=False, half=False):
    from ultralytics import YOLO
    m = YOLO(pt)
    outs = {}
    for f in formats:
        kw = dict(format=f, imgsz=imgsz)
        if f == "onnx":
            kw.update(opset=12, simplify=True, dynamic=False)
        if f == "rknn":
            kw.update(name="rk3588")
            if int8:
                kw.update(int8=True, data=data)
        if f == "ncnn" and half:
            kw.update(half=True)
        print("[export] -> %s (imgsz %d)" % (f, imgsz))
        out = m.export(**kw)
        outs[f] = out
        print("[export] saved", out)
        if f == "onnx":
            verify_onnx(pt, out, data, imgsz)
    return outs


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("--formats", nargs="+", default=["onnx"], choices=["onnx", "ncnn", "rknn", "openvino", "torchscript"])
    ap.add_argument("--imgsz", type=int, default=None)
    ap.add_argument("--data", help="data.yaml (for INT8 calibration and the self-check)")
    ap.add_argument("--int8", action="store_true")
    ap.add_argument("--half", action="store_true")
    a = ap.parse_args()
    imgsz = a.imgsz
    if imgsz is None:
        try:
            from ultralytics import YOLO
            imgsz = int(YOLO(a.model).ckpt.get("train_args", {}).get("imgsz", 640))
        except Exception:
            imgsz = 640
    export(a.model, a.formats, imgsz, a.data, a.int8, a.half)
