#!/usr/bin/env python3
"""Convert a trained model to RKNN (Orange Pi 5 Pro NPU) offline with Docker (macOS: colima, Windows: Docker Desktop).
   python setup/convert_rknn.py models/<name>/best.pt [--imgsz 640]  ->  models/<name>/best_rknn_model/"""
import argparse, os, shutil, subprocess, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ap = argparse.ArgumentParser()
ap.add_argument("pt")
ap.add_argument("--imgsz", default="640")
a = ap.parse_args()
if sys.platform == "darwin" and subprocess.call(["colima", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
    print("[rknn] starting colima (Docker) ...")
    subprocess.call(["colima", "start"])
pt = a.pt.replace("\\", "/")
onnx = os.path.join(ROOT, os.path.splitext(pt)[0] + ".onnx")
if os.path.exists(onnx):
    shutil.copy2(onnx, onnx + ".keep")          # the RKNN export rewrites best.onnx -> keep the verified one
cmd = ["docker", "run", "--rm", "--network", "none", "-v", "%s:/work" % ROOT, "brics-rknn", "bash", "-c",
       "mkdir -p /root/.config/Ultralytics && cp /work/weights/Arial*.ttf /root/.config/Ultralytics/ 2>/dev/null; "
       "yolo export model=%s format=rknn name=rk3588 imgsz=%s" % (pt, a.imgsz)]
print("[rknn]", " ".join(cmd))
rc = subprocess.call(cmd)
if os.path.exists(onnx + ".keep"):
    shutil.move(onnx + ".keep", onnx)
out = os.path.splitext(pt)[0] + "_rknn_model"
print("[rknn] %s -> use in config:  model: %s" % ("OK" if rc == 0 and os.path.isdir(os.path.join(ROOT, out)) else "FAILED", out))
sys.exit(rc)
