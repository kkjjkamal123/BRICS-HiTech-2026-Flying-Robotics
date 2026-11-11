#!/usr/bin/env python3
"""
autolabel.py - label hundreds of images automatically, then just REVIEW them in label_tool.py.

Detector options:
  --model models/fire/best.pt      a model you trained on a few labelled images (iterative labelling)
  --model weights/yolo11s.pt       COCO model: person, car, truck, bird ... (80 classes) - use --keep / --map
  --hsv  --label flame             colour threshold (tune --ranges)  -> flames, coloured markers
  --exg  --label plant             green vegetation                  -> plants / weeds / trees
  --thermal --label hotspot        bright spots in thermal images

  python train/autolabel.py venue_photos/ --hsv --label fire
  python train/autolabel.py venue_photos/ --model weights/yolo11s.pt --keep car truck --map truck=car
  python train/autolabel.py venue_photos/ --model models/fire/best.pt --conf 0.3      # round 2
  python train/label_tool.py venue_photos/                                           # review / fix

Iterative recipe (fastest way to a good model):
  1. label 30-50 images by hand (label_tool)   2. train --quality fast    3. autolabel the rest with it
  4. review/fix in label_tool                  5. train --quality best on everything
"""
import argparse
import glob
import os
import sys

import cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from common.detector import ExGDetector, HSVDetector, ThermalDetector, YoloDetector, detect_tiled  # noqa: E402

IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--model")
    g.add_argument("--hsv", action="store_true")
    g.add_argument("--exg", action="store_true")
    g.add_argument("--thermal", action="store_true")
    ap.add_argument("--label", default=None, help="class name for hsv/exg/thermal")
    ap.add_argument("--ranges", default=None, help='HSV ranges JSON, e.g. "[[[0,120,150],[22,255,255]]]"')
    ap.add_argument("--min-area", type=int, default=150)
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--keep", nargs="*", help="only keep these model classes")
    ap.add_argument("--map", nargs="*", default=[], help="rename classes OLD=NEW")
    ap.add_argument("--tile", type=int, default=0)
    ap.add_argument("--overwrite", action="store_true", help="also re-label images that already have labels")
    a = ap.parse_args(argv)

    if a.model:
        det = YoloDetector(a.model, conf=a.conf, classes=a.keep)
    elif a.hsv:
        import json
        det = HSVDetector(ranges=json.loads(a.ranges) if a.ranges else None, min_area=a.min_area, label=a.label or "object")
    elif a.exg:
        det = ExGDetector(min_area=a.min_area, label=a.label or "plant")
    else:
        det = ThermalDetector(min_area=a.min_area, label=a.label or "hotspot", mode="percentile")
    rename = dict(m.split("=", 1) for m in a.map)

    ldir = os.path.join(a.folder, "labels")
    if not os.path.isdir(ldir):
        os.makedirs(ldir)
    cf = os.path.join(a.folder, "classes.txt")
    classes = [l.strip() for l in open(cf) if l.strip()] if os.path.exists(cf) else []
    files = sorted(f for f in glob.glob(os.path.join(a.folder, "*")) if f.lower().endswith(IMG_EXT))
    n_img = n_box = 0
    for f in files:
        lp = os.path.join(ldir, os.path.splitext(os.path.basename(f))[0] + ".txt")
        if os.path.exists(lp) and not a.overwrite:
            continue
        img = cv2.imread(f)
        if img is None:
            continue
        H, W = img.shape[:2]
        dets = detect_tiled(det, img, a.tile) if a.tile else det(img)
        lines = []
        for d in dets:
            name = rename.get(d["name"], d["name"])
            if name not in classes:
                classes.append(name)
            x1, y1, x2, y2 = d["box"]
            lines.append("%d %.6f %.6f %.6f %.6f" % (classes.index(name), (x1 + x2) / 2 / W, (y1 + y2) / 2 / H, (x2 - x1) / W, (y2 - y1) / H))
        open(lp, "w").write("\n".join(lines) + ("\n" if lines else ""))
        n_img += 1
        n_box += len(lines)
    open(cf, "w").write("\n".join(classes) + "\n")
    print("auto-labelled %d images, %d boxes, classes %s" % (n_img, n_box, classes))
    print("NEXT: review ->  python train/label_tool.py %s" % a.folder)


if __name__ == "__main__":
    main()
