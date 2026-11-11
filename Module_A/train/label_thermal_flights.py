#!/usr/bin/env python3
"""
Build the THERMAL detection dataset from the thermal frames the Case 1 mission saved in flight
(runs/<run>/frames/thermal_*.jpg = the false-colour picture the mission's detectors see, 256 x 192).

Auto-labelling rule (checked by eye on contact sheets, 11 Nov 2026):
  * The picture is auto-ranged, so when something far hotter than the room is in view the room turns almost black:
    frame median gray <= 35. Only such frames can contain a target.
  * Object = glowing pixels (gray >= 90), grown by 15 px so the parts of one object join, with a hot core (>= 200).
  * Class by SHAPE:  fire  = compact round disc (the venue heat source, >= 100 C)  (fill >= 0.55, aspect <= 1.6, 1 core)
                     flame = everything else hot (the simulated flame lamp: coil from the side / hot spots in the bowl)
  * Frames are LEFT OUT (not used as negatives) when an object touches the image edge (class unclear),
    the box is huge (> 6000 px: warm floor, not a target), or the run is in --skip-positive-runs
    (19:33 run: two warm hands at x ~ 0 looked like a target).
  * Every other frame is a negative (no box): floor, markers, people, warm electronics.
Split by FLIGHT so validation frames come from flights the model never saw.

  python train/label_thermal_flights.py --runs datasets/thermal_flights --out datasets/thermal_fire \
      --val case1_fire_20261110_185700 case1_fire_20261110_212037
"""
import argparse
import glob
import json
import os
import shutil

import cv2
import numpy as np

MED_MAX = 35
NAMES = ["fire", "flame"]


def objects(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    med = float(np.median(g))
    if med > MED_MAX:
        return med, []
    glow = (g >= 90).astype(np.uint8)
    grown = cv2.dilate(glow, np.ones((15, 15), np.uint8))
    n, lab, _, _ = cv2.connectedComponentsWithStats(grown, 8)
    out = []
    for i in range(1, n):
        comp = (lab == i) & (glow > 0)
        if comp.sum() < 12 or not (g[lab == i] >= 200).any():
            continue
        ys, xs = np.nonzero(comp)
        x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        w, h = x2 - x1, y2 - y1
        fill = comp.sum() / float(w * h)
        cores = cv2.connectedComponents(((g >= 200) & comp).astype(np.uint8), connectivity=8)[0] - 1
        aspect = max(w, h) / float(max(1, min(w, h)))
        cls = "fire" if (fill >= 0.55 and aspect <= 1.6 and cores <= 1) else "flame"
        edge = x1 <= 1 or y1 <= 1 or x2 >= g.shape[1] - 1 or y2 >= g.shape[0] - 1
        p = 2
        out.append({"cls": cls, "box": [max(0, x1 - p), max(0, y1 - p), min(g.shape[1], x2 + p), min(g.shape[0], y2 + p)],
                    "edge": bool(edge), "area": w * h})
    return med, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", required=True, help="folder with run folders (each has frames/thermal_*.jpg)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--val", nargs="+", required=True, help="run folder names used ONLY for validation")
    ap.add_argument("--skip-positive-runs", nargs="*", default=["case1_fire_20261110_193314"])
    a = ap.parse_args()
    if os.path.exists(a.out):
        shutil.rmtree(a.out)
    for s in ("train", "val"):
        os.makedirs(os.path.join(a.out, "images", s))
        os.makedirs(os.path.join(a.out, "labels", s))
    stats, left_out, report = {}, [], {}
    for f in sorted(glob.glob(os.path.join(a.runs, "*", "frames", "thermal_*.jpg"))):
        run = f.split(os.sep)[-3]
        img = cv2.imread(f)
        if img is None:
            continue
        med, objs = objects(img)
        if objs and (run in a.skip_positive_runs or any(o["edge"] or o["area"] > 6000 for o in objs)):
            left_out.append(os.path.relpath(f, a.runs))
            continue
        split = "val" if run in a.val else "train"
        name = "%s_%s" % (run[-15:], os.path.basename(f))
        cv2.imwrite(os.path.join(a.out, "images", split, name), img)
        h, w = img.shape[:2]
        with open(os.path.join(a.out, "labels", split, name[:-4] + ".txt"), "w") as fl:
            for o in objs:
                x1, y1, x2, y2 = o["box"]
                fl.write("%d %.6f %.6f %.6f %.6f\n" % (NAMES.index(o["cls"]), (x1 + x2) / 2.0 / w, (y1 + y2) / 2.0 / h,
                                                        (x2 - x1) / float(w), (y2 - y1) / float(h)))
        st = stats.setdefault(split, {"images": 0, "negatives": 0, "fire": 0, "flame": 0})
        st["images"] += 1
        st["negatives"] += 0 if objs else 1
        for o in objs:
            st[o["cls"]] += 1
        report[os.path.relpath(f, a.runs)] = {"split": split, "median": med, "objects": objs}
    with open(os.path.join(a.out, "data.yaml"), "w") as fy:
        fy.write("path: %s\ntrain: images/train\nval: images/val\nnames:\n  0: fire\n  1: flame\n" % os.path.abspath(a.out))
    with open(os.path.join(a.out, "labels_report.json"), "w") as fr:
        json.dump({"stats": stats, "left_out": left_out, "val_runs": a.val, "frames": report}, fr, indent=0)
    print(json.dumps(stats, indent=1))
    print("left out (edge / huge / skipped run):", len(left_out))


if __name__ == "__main__":
    main()
