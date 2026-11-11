#!/usr/bin/env python3
"""
predict.py - test any model / detector config on images, a folder, a video or a camera.

  python train/predict.py --model models/fire/best.onnx --source test_images/
  python train/predict.py --model models/fire/best.pt --source flight.mp4 --show
  python train/predict.py --model models/fire/best.onnx --source 0 --show          # webcam
  python train/predict.py --config config/case1_fire.yaml --source runs/<run>/frames   # all mission detectors
  python train/predict.py --hsv --source photos/ --show                               # tune colour detector
Saves annotated results to runs/predict_<time>/ and prints counts + speed (ms/frame).
"""
import argparse
import glob
import os
import sys
import time

import cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from common.detector import HSVDetector, ExGDetector, MultiDetector, YoloDetector, build_detector, detect_tiled, draw  # noqa: E402

IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--model")
    g.add_argument("--config", help="mission YAML: uses its detectors list")
    g.add_argument("--hsv", action="store_true")
    g.add_argument("--exg", action="store_true")
    ap.add_argument("--source", required=True, help="image, folder, video file or camera index")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--tile", type=int, default=0)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    if a.model:
        det = MultiDetector([(YoloDetector(a.model, conf=a.conf), "rgb", a.tile)])
    elif a.config:
        import yaml
        det = build_detector(yaml.safe_load(open(a.config)).get("detectors", []), base_dir=ROOT)
    elif a.hsv:
        det = MultiDetector([(HSVDetector(), "rgb", a.tile)])
    else:
        det = MultiDetector([(ExGDetector(), "rgb", a.tile)])
    out = a.out or os.path.join(ROOT, "runs", "predict_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out, exist_ok=True)

    src = a.source
    if os.path.isdir(src) or (os.path.isfile(src) and src.lower().endswith(IMG_EXT)):
        files = sorted(f for f in glob.glob(os.path.join(src, "*")) if f.lower().endswith(IMG_EXT)) if os.path.isdir(src) else [src]
        frames = ((os.path.basename(f), cv2.imread(f)) for f in files)
    else:
        cap = cv2.VideoCapture(int(src) if src.isdigit() else src)

        def gen():
            k = 0
            while True:
                ok, im = cap.read()
                if not ok:
                    break
                k += 1
                yield "frame%06d.jpg" % k, im
        frames = gen()
    total, times, n = {}, [], 0
    writer = None
    for name, img in frames:
        if img is None:
            continue
        t = time.time()
        dets = det(img)
        times.append(time.time() - t)
        n += 1
        for d in dets:
            total[d["name"]] = total.get(d["name"], 0) + 1
        vis = draw(img, dets)
        if os.path.isdir(src) or src.lower().endswith(IMG_EXT):
            cv2.imwrite(os.path.join(out, name), vis)
            print("%-35s %s" % (name, ", ".join("%s %.2f" % (d["name"], d["conf"]) for d in dets) or "-"))
        else:
            if writer is None:
                writer = cv2.VideoWriter(os.path.join(out, "result.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 15, (vis.shape[1], vis.shape[0]))
            writer.write(vis)
        if a.show:
            cv2.imshow("predict", vis)
            if cv2.waitKey(1 if not os.path.isdir(src) else 0) & 0xFF in (ord("q"), 27):
                break
    if writer:
        writer.release()
    if times:
        print("\n%d frames, %.1f ms/frame (%.1f FPS), detections per class: %s" % (
            n, 1000 * sum(times) / len(times), len(times) / sum(times), total))
    print("results ->", out)


if __name__ == "__main__":
    main()
