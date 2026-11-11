#!/usr/bin/env python3
"""
CASE 2 - Weed counting + digital infestation map. Works on laptop AND Orange Pi (numpy + cv2 only).

Two modes:
 A) ONE (or several independent) aerial image(s) of a plot  ->  count weeds in each, density grid overlay
      python3 analysis/weed_map.py --images field.jpg --model models/weeds/best.onnx --tile 640
      python3 analysis/weed_map.py --images field.jpg --exg            # no model: all green plants
 B) A drone survey folder (frames.csv with poses, from case2_weeds.py)  ->  project every detection onto the
    map, merge duplicates seen in overlapping photos, count, map in metres
      python3 analysis/weed_map.py --survey runs/case2_weeds_xxx/frames --model models/weeds/best.onnx

Outputs (in --out): annotated images, objects.csv, counts.csv, heatmap.png, report.html
Options:
  --count-classes weed            only count these classes (e.g. model has weed + crop)
  --gsd 0.005                     metres per pixel for single images (gives weeds per m^2)
  --cell 0.5                      grid cell size: metres (survey) or pixels/gsd (images) for the heat map
"""
import argparse
import csv
import glob
import math
import os
import sys

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from common.detector import ExGDetector, HSVDetector, YoloDetector, detect_tiled, draw  # noqa: E402
from common.geometry import ObjectTracker, nadir_pixel_to_ground                    # noqa: E402
from common.report import write_report                                                # noqa: E402

DEFAULT_K = [[332.0, 0, 320.0], [0, 332.0, 240.0], [0, 0, 1]]


def make_detector(a):
    if a.model:
        return YoloDetector(a.model, conf=a.conf, imgsz=a.imgsz)
    if a.hsv:
        return HSVDetector(label="weed", min_area=a.min_area)
    return ExGDetector(label="plant", min_area=a.min_area)


def heat_overlay(img, points_px, cell_px):
    """Colour grid over the image: green (few) -> red (many) weeds per cell."""
    H, W = img.shape[:2]
    gh, gw = int(math.ceil(H / float(cell_px))), int(math.ceil(W / float(cell_px)))
    grid = np.zeros((gh, gw), np.int32)
    for u, v in points_px:
        grid[min(gh - 1, int(v // cell_px)), min(gw - 1, int(u // cell_px))] += 1
    out = img.copy()
    mx = max(1, grid.max())
    over = img.copy()
    for i in range(gh):
        for j in range(gw):
            n = grid[i, j]
            if n == 0:
                continue
            t = n / float(mx)
            col = (0, int(255 * (1 - t)), int(255 * t))   # BGR green->red
            cv2.rectangle(over, (j * cell_px, i * cell_px), ((j + 1) * cell_px, (i + 1) * cell_px), col, -1)
    out = cv2.addWeighted(over, 0.40, img, 0.60, 0)
    for i in range(gh):
        for j in range(gw):
            if grid[i, j]:
                cv2.putText(out, str(grid[i, j]), (j * cell_px + 4, i * cell_px + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    return out, grid


def heat_map_metres(objs, cell, area=None, size=600):
    """Heat-map image of object positions (metres)."""
    xs = [o["x"] for o in objs] or [0]
    ys = [o["y"] for o in objs] or [0]
    x0, y0 = (area[0], area[1]) if area else (min(xs) - cell, min(ys) - cell)
    x1, y1 = (area[2], area[3]) if area else (max(xs) + cell, max(ys) + cell)
    gw, gh = max(1, int(math.ceil((x1 - x0) / cell))), max(1, int(math.ceil((y1 - y0) / cell)))
    grid = np.zeros((gh, gw), np.int32)
    for o in objs:
        j, i = int((o["x"] - x0) // cell), int((o["y"] - y0) // cell)
        if 0 <= i < gh and 0 <= j < gw:
            grid[i, j] += 1
    px = max(20, size // max(gw, gh))
    img = np.full((gh * px + 40, gw * px + 40, 3), 255, np.uint8)
    mx = max(1, grid.max())
    for i in range(gh):
        for j in range(gw):
            n = grid[i, j]
            t = n / float(mx)
            col = (230, 230, 230) if n == 0 else (0, int(255 * (1 - t)), int(255 * t))
            yy = 20 + (gh - 1 - i) * px          # y up
            cv2.rectangle(img, (20 + j * px, yy), (20 + (j + 1) * px, yy + px), col, -1)
            cv2.rectangle(img, (20 + j * px, yy), (20 + (j + 1) * px, yy + px), (180, 180, 180), 1)
            if n:
                cv2.putText(img, str(n), (24 + j * px, yy + px // 2 + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    cv2.putText(img, "cell %.2f m  (x right, y up)  max %d/cell" % (cell, mx), (20, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    return img, grid


def run_images(a, det, out):
    files = []
    for p in a.images:
        files += sorted(glob.glob(os.path.join(p, "*.*"))) if os.path.isdir(p) else [p]
    files = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"))]
    rows, total = [], {}
    for f in files:
        img = cv2.imread(f)
        if img is None:
            continue
        dets = detect_tiled(det, img, a.tile) if a.tile else det(img)
        if a.count_classes:
            dets = [d for d in dets if d["name"] in a.count_classes]
        counts = {}
        for d in dets:
            counts[d["name"]] = counts.get(d["name"], 0) + 1
            total[d["name"]] = total.get(d["name"], 0) + 1
        cell_px = max(1, int(a.cell / a.gsd) if a.gsd else int(a.cell if a.cell > 5 else max(img.shape[:2]) / 8))
        vis, grid = heat_overlay(draw(img, dets, (0, 0, 255)), [d["center"] for d in dets], cell_px)
        base = os.path.splitext(os.path.basename(f))[0]
        cv2.imwrite(os.path.join(out, base + "_weedmap.jpg"), vis)
        area_m2 = (img.shape[0] * img.shape[1] * a.gsd ** 2) if a.gsd else None
        dens = ("%.2f" % (len(dets) / area_m2)) if area_m2 else ""
        rows.append([os.path.basename(f), len(dets), dens] + ["%s=%d" % kv for kv in sorted(counts.items())])
        print("%-40s %4d objects %s %s" % (os.path.basename(f), len(dets), ("(%s per m2)" % dens) if dens else "", counts))
        with open(os.path.join(out, base + "_objects.csv"), "w") as fo:
            w = csv.writer(fo)
            w.writerow(["class", "conf", "u", "v", "x1", "y1", "x2", "y2"] + (["x_m", "y_m"] if a.gsd else []))
            for d in dets:
                extra = [d["center"][0] * a.gsd, d["center"][1] * a.gsd] if a.gsd else []
                w.writerow([d["name"], "%.3f" % d["conf"], "%.1f" % d["center"][0], "%.1f" % d["center"][1]] + ["%.1f" % v for v in d["box"]] + extra)
    with open(os.path.join(out, "counts.csv"), "w") as fo:
        w = csv.writer(fo)
        w.writerow(["image", "count", "per_m2", "by_class"])
        w.writerows(rows)
    print("TOTAL:", total, "->", out)
    return total


def run_survey(a, det, out):
    csv_path = os.path.join(a.survey, "frames.csv")
    kfile = os.path.join(a.survey, "camera_K.json")
    if a.K:
        K = np.array(a.K, dtype=float).reshape(3, 3)
    elif os.path.exists(kfile):
        import json
        K = np.array(json.load(open(kfile)).get(a.camera, DEFAULT_K), dtype=float)
    else:
        K = np.array(DEFAULT_K, dtype=float)
    meta = {}
    mfile = os.path.join(a.survey, "camera_meta.json")       # written by the mission (image orientation, floor height)
    if os.path.exists(mfile):
        import json
        meta = json.load(open(mfile)).get(a.camera, {})
    up_fwd, ground_z = bool(meta.get("image_up_is_forward", True)), float(meta.get("ground_z", 0.0))
    tracker = ObjectTracker(radius=a.merge, min_hits=1)
    n_img = 0
    with open(csv_path) as f:
        for r in csv.DictReader(f):
            if a.camera and r["camera"] != a.camera:
                continue
            img = cv2.imread(os.path.join(a.survey, r["file"]))
            if img is None:
                continue
            x, y, z, yaw = float(r["x"]), float(r["y"]), float(r["z"]), float(r["yaw"])
            if any(math.isnan(v) for v in (x, y, z, yaw)):
                continue
            n_img += 1
            dets = detect_tiled(det, img, a.tile) if a.tile else det(img)
            if a.count_classes:
                dets = [d for d in dets if d["name"] in a.count_classes]
            for d in dets:
                gx, gy = nadir_pixel_to_ground(d["center"][0], d["center"][1], K, x, y, z, yaw, ground_z=ground_z,
                                               cam_forward_is_image_up=up_fwd)
                tracker.add(d["name"], gx, gy, 0.0, d["conf"])
            cv2.imwrite(os.path.join(out, "det_" + r["file"]), draw(img, dets, (0, 0, 255)))
    objs = tracker.confirmed()
    hm, _ = heat_map_metres(objs, a.cell, a.area)
    cv2.imwrite(os.path.join(out, "heatmap.png"), hm)
    counts = tracker.counts()
    with open(os.path.join(out, "counts.csv"), "w") as fo:
        fo.write("class,count\n")
        for k, v in sorted(counts.items()):
            fo.write("%s,%d\n" % (k, v))
    ok, buf = cv2.imencode(".png", hm)
    import base64
    extra = "<h2>Infestation heat map</h2><img src='data:image/png;base64,%s'>" % base64.b64encode(buf.tobytes()).decode()
    write_report(os.path.join(out, "report.html"), "Weed infestation map", objs, area=a.area,
                 meta={"Images processed": n_img, "Unique objects": len(objs), "Counts": counts,
                       "Merge radius (m)": a.merge, "Grid cell (m)": a.cell}, extra_html=extra)
    print("Images: %d  unique objects: %d  %s -> %s" % (n_img, len(objs), counts, out))
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--images", nargs="+", help="image files or folders (independent images)")
    g.add_argument("--survey", help="folder with frames.csv + images (drone survey)")
    ap.add_argument("--model", help="trained YOLO model (.onnx/.pt). Without it: ExG vegetation detector")
    ap.add_argument("--hsv", action="store_true", help="use colour detector instead of ExG")
    ap.add_argument("--exg", action="store_true", help="(default without --model) Excess-Green plant detector")
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--imgsz", type=int, default=None)
    ap.add_argument("--tile", type=int, default=0, help="tile size for big images (e.g. 640). 0 = off")
    ap.add_argument("--min-area", type=int, default=60, help="min blob area (px) for ExG/HSV")
    ap.add_argument("--count-classes", nargs="*", help="only count these classes")
    ap.add_argument("--gsd", type=float, default=0, help="metres per pixel (images mode)")
    ap.add_argument("--cell", type=float, default=0.5, help="heat-map cell (m; or px in images mode without gsd)")
    ap.add_argument("--merge", type=float, default=0.08, help="survey: merge detections closer than this (m)")
    ap.add_argument("--area", type=float, nargs=4, help="survey: x0 y0 x1 y1 for the map")
    ap.add_argument("--camera", default="rgb")
    ap.add_argument("--K", type=float, nargs=9, help="camera matrix (9 numbers) for survey mode")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out = a.out or os.path.join(ROOT, "runs", "weedmap_" + __import__("time").strftime("%Y%m%d_%H%M%S"))
    if not os.path.isdir(out):
        os.makedirs(out)
    det = make_detector(a)
    return run_survey(a, det, out) if a.survey else run_images(a, det, out)


if __name__ == "__main__":
    main()
