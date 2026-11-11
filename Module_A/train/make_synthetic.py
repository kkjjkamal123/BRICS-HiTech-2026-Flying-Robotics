#!/usr/bin/env python3
"""
make_synthetic.py - generate training data.

MODE paste (REAL technique, use at the venue when you have few labelled photos):
  Cuts every labelled object out of a small labelled YOLO dataset and pastes random copies (scaled,
  rotated, flipped, brightness-jittered) onto background photos of the venue floor/field (no objects).
  20 labelled photos + 30 floor photos -> 1000 realistic training images in a minute.

    python train/make_synthetic.py paste --objects datasets/fire --backgrounds venue_floor/ \
        --out datasets/fire_synth --n 1000
    python train/prepare_dataset.py datasets/fire datasets/fire_synth --out datasets/fire_all
    python train/train.py --data datasets/fire_all --name fire

  You can also give --objects a folder of cut-out PNGs with transparency, sub-folder name = class:
    cutouts/fire/*.png  cutouts/car/*.png

MODE shapes (self-test of the pipeline, no real data needed):
    python train/make_synthetic.py shapes --out datasets/_selftest --n 200 --format yolo|coco|voc|csv|classify
"""
import argparse
import glob
import json
import os
import random

import cv2
import numpy as np

IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


# ----------------------------------------------------------------------------- shapes (self-test)
SHAPES = {"fire": (0, 90, 255), "car": (200, 60, 30), "weed": (40, 170, 40)}


def shape_image(rnd, w=416, h=416):
    img = np.full((h, w, 3), [rnd.randint(70, 140)] * 3, np.uint8)
    img = cv2.add(img, np.random.RandomState(rnd.randint(0, 1 << 30)).randint(0, 40, img.shape, dtype=np.uint8))
    objs = []
    for _ in range(rnd.randint(0, 4)):
        name = rnd.choice(list(SHAPES))
        s = rnd.randint(20, 70)
        x, y = rnd.randint(0, w - s - 1), rnd.randint(0, h - s - 1)
        col = tuple(int(np.clip(c + rnd.randint(-25, 25), 0, 255)) for c in SHAPES[name])
        if name == "fire":
            pts = np.array([[x + s // 2, y], [x + s, y + s], [x, y + s]], np.int32)
            cv2.fillPoly(img, [pts], col)
        elif name == "car":
            cv2.rectangle(img, (x, y + s // 4), (x + s, y + 3 * s // 4), col, -1)
            y, s_h = y + s // 4, s // 2
            objs.append((name, x, y, x + s, y + s_h))
            continue
        else:
            cv2.circle(img, (x + s // 2, y + s // 2), s // 2, col, -1)
        objs.append((name, x, y, x + s, y + s))
    return img, objs


def make_shapes(out, n, fmt, seed=0):
    rnd = random.Random(seed)
    names = sorted(SHAPES)
    os.makedirs(out, exist_ok=True)
    coco = {"images": [], "annotations": [], "categories": [{"id": i + 1, "name": c} for i, c in enumerate(names)]}
    rows = []
    for i in range(n):
        img, objs = shape_image(rnd)
        h, w = img.shape[:2]
        fn = "img%04d.jpg" % i
        if fmt == "classify":
            if len(objs) == 0:
                continue
            cls = objs[0][0]
            d = os.path.join(out, cls)
            os.makedirs(d, exist_ok=True)
            cv2.imwrite(os.path.join(d, fn), img)
            continue
        if fmt == "yolo":
            os.makedirs(os.path.join(out, "images"), exist_ok=True)
            os.makedirs(os.path.join(out, "labels"), exist_ok=True)
            cv2.imwrite(os.path.join(out, "images", fn), img)
            with open(os.path.join(out, "labels", fn[:-4] + ".txt"), "w") as f:
                for nme, x1, y1, x2, y2 in objs:
                    f.write("%d %.6f %.6f %.6f %.6f\n" % (names.index(nme), (x1 + x2) / 2.0 / w, (y1 + y2) / 2.0 / h, (x2 - x1) / float(w), (y2 - y1) / float(h)))
            continue
        cv2.imwrite(os.path.join(out, fn), img)
        if fmt == "coco":
            coco["images"].append({"id": i, "file_name": fn, "width": w, "height": h})
            for nme, x1, y1, x2, y2 in objs:
                coco["annotations"].append({"id": len(coco["annotations"]) + 1, "image_id": i, "category_id": names.index(nme) + 1,
                                            "bbox": [x1, y1, x2 - x1, y2 - y1], "area": (x2 - x1) * (y2 - y1), "iscrowd": 0})
        elif fmt == "voc":
            xml = "<annotation><filename>%s</filename><size><width>%d</width><height>%d</height><depth>3</depth></size>" % (fn, w, h)
            for nme, x1, y1, x2, y2 in objs:
                xml += "<object><name>%s</name><bndbox><xmin>%d</xmin><ymin>%d</ymin><xmax>%d</xmax><ymax>%d</ymax></bndbox></object>" % (nme, x1, y1, x2, y2)
            open(os.path.join(out, fn[:-4] + ".xml"), "w").write(xml + "</annotation>")
        elif fmt == "csv":
            for nme, x1, y1, x2, y2 in objs:
                rows.append("%s,%d,%d,%s,%d,%d,%d,%d" % (fn, w, h, nme, x1, y1, x2, y2))
    if fmt == "yolo":
        open(os.path.join(out, "classes.txt"), "w").write("\n".join(names) + "\n")
    if fmt == "coco":
        json.dump(coco, open(os.path.join(out, "_annotations.coco.json"), "w"))
    if fmt == "csv":
        open(os.path.join(out, "_annotations.csv"), "w").write("filename,width,height,class,xmin,ymin,xmax,ymax\n" + "\n".join(rows) + "\n")
    print("[synth] %d %s images -> %s" % (n, fmt, out))


# ----------------------------------------------------------------------------- copy-paste augmentation
def load_cutouts(src, pad=0.08):
    """Returns list of (class_name, BGRA cut-out)."""
    cuts = []
    pngs = glob.glob(os.path.join(src, "*", "*.png"))
    if pngs and not os.path.exists(os.path.join(src, "data.yaml")) and not glob.glob(os.path.join(src, "labels")):
        for p in pngs:
            im = cv2.imread(p, cv2.IMREAD_UNCHANGED)
            if im is None:
                continue
            if im.shape[2] == 3:
                im = np.dstack([im, np.full(im.shape[:2], 255, np.uint8)])
            cuts.append((os.path.basename(os.path.dirname(p)), im))
        return cuts
    import yaml
    names = None
    y = os.path.join(src, "data.yaml")
    if os.path.exists(y):
        n = yaml.safe_load(open(y))["names"]
        names = [n[k] for k in sorted(n)] if isinstance(n, dict) else n
    elif os.path.exists(os.path.join(src, "classes.txt")):
        names = [l.strip() for l in open(os.path.join(src, "classes.txt")) if l.strip()]
    for lf in glob.glob(os.path.join(src, "**", "labels", "**", "*.txt"), recursive=True):
        base = lf.replace(os.sep + "labels" + os.sep, os.sep + "images" + os.sep)[:-4]
        ip = next((base + e for e in IMG_EXT if os.path.exists(base + e)), None)
        if not ip:
            continue
        im = cv2.imread(ip)
        H, W = im.shape[:2]
        for line in open(lf):
            v = line.split()
            if len(v) != 5:
                continue
            c, cx, cy, w, h = int(v[0]), float(v[1]) * W, float(v[2]) * H, float(v[3]) * W, float(v[4]) * H
            x1, y1 = int(max(0, cx - w / 2 * (1 + pad))), int(max(0, cy - h / 2 * (1 + pad)))
            x2, y2 = int(min(W, cx + w / 2 * (1 + pad))), int(min(H, cy + h / 2 * (1 + pad)))
            crop = im[y1:y2, x1:x2]
            if crop.size == 0 or crop.shape[0] < 6 or crop.shape[1] < 6:
                continue
            # soft elliptical alpha so the paste blends into the background
            a = np.zeros(crop.shape[:2], np.uint8)
            cv2.ellipse(a, (crop.shape[1] // 2, crop.shape[0] // 2), (crop.shape[1] // 2, crop.shape[0] // 2), 0, 0, 360, 255, -1)
            a = cv2.GaussianBlur(a, (0, 0), max(1, min(crop.shape[:2]) * 0.06))
            cuts.append((names[c] if names and c < len(names) else "class%d" % c, np.dstack([crop, a])))
    return cuts


def paste_one(bg, cut, rnd, scale_range):
    H, W = bg.shape[:2]
    s = rnd.uniform(*scale_range)
    ch, cw = cut.shape[:2]
    k = s * min(H, W) / float(max(ch, cw))
    cut = cv2.resize(cut, (max(4, int(cw * k)), max(4, int(ch * k))))
    if rnd.random() < 0.5:
        cut = cut[:, ::-1]
    if rnd.random() < 0.5:
        cut = cut[::-1]
    ang = rnd.uniform(-180, 180)
    ch, cw = cut.shape[:2]
    M = cv2.getRotationMatrix2D((cw / 2.0, ch / 2.0), ang, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(ch * sin + cw * cos), int(ch * cos + cw * sin)
    M[0, 2] += nw / 2.0 - cw / 2.0
    M[1, 2] += nh / 2.0 - ch / 2.0
    cut = cv2.warpAffine(np.ascontiguousarray(cut), M, (nw, nh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    if nw >= W or nh >= H:
        return None
    x, y = rnd.randint(0, W - nw), rnd.randint(0, H - nh)
    rgb = cut[:, :, :3].astype(np.float32) * rnd.uniform(0.75, 1.25)
    a = cut[:, :, 3:].astype(np.float32) / 255.0
    roi = bg[y:y + nh, x:x + nw].astype(np.float32)
    bg[y:y + nh, x:x + nw] = np.clip(rgb * a + roi * (1 - a), 0, 255).astype(np.uint8)
    ys, xs = np.where(cut[:, :, 3] > 100)
    if len(xs) == 0:
        return None
    return (x + xs.min(), y + ys.min(), x + xs.max(), y + ys.max())


def make_paste(objects, backgrounds, out, n, per_image=(1, 4), scale=(0.05, 0.25), seed=0, size=None):
    rnd = random.Random(seed)
    cuts = load_cutouts(objects)
    if not cuts:
        raise SystemExit("[synth] no objects found in %s" % objects)
    bgs = [p for p in glob.glob(os.path.join(backgrounds, "**", "*.*"), recursive=True) if p.lower().endswith(IMG_EXT)]
    if not bgs:
        raise SystemExit("[synth] no background images in %s" % backgrounds)
    names = sorted(set(c for c, _ in cuts))
    for d in ("images", "labels"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    for i in range(n):
        bg = cv2.imread(rnd.choice(bgs))
        if size:
            bg = cv2.resize(bg, (size, int(size * bg.shape[0] / float(bg.shape[1]))))
        H, W = bg.shape[:2]
        lines = []
        for _ in range(rnd.randint(*per_image)):
            c, cut = rnd.choice(cuts)
            b = paste_one(bg, cut, rnd, scale)
            if b:
                x1, y1, x2, y2 = b
                lines.append("%d %.6f %.6f %.6f %.6f" % (names.index(c), (x1 + x2) / 2.0 / W, (y1 + y2) / 2.0 / H, (x2 - x1) / float(W), (y2 - y1) / float(H)))
        cv2.imwrite(os.path.join(out, "images", "syn%05d.jpg" % i), bg)
        open(os.path.join(out, "labels", "syn%05d.txt" % i), "w").write("\n".join(lines) + "\n")
    open(os.path.join(out, "classes.txt"), "w").write("\n".join(names) + "\n")
    print("[synth] %d pasted images, %d cut-outs, classes %s -> %s" % (n, len(cuts), names, out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("shapes")
    s.add_argument("--out", required=True)
    s.add_argument("--n", type=int, default=200)
    s.add_argument("--format", default="yolo", choices=["yolo", "coco", "voc", "csv", "classify"])
    p = sub.add_parser("paste")
    p.add_argument("--objects", required=True, help="labelled YOLO dataset OR folder of class sub-folders with PNG cut-outs")
    p.add_argument("--backgrounds", required=True, help="folder of photos without objects (venue floor / field)")
    p.add_argument("--out", required=True)
    p.add_argument("--n", type=int, default=1000)
    p.add_argument("--per-image", type=int, nargs=2, default=[1, 4])
    p.add_argument("--scale", type=float, nargs=2, default=[0.05, 0.25], help="object size as fraction of image")
    p.add_argument("--size", type=int, default=None, help="resize backgrounds to this width")
    a = ap.parse_args()
    if a.mode == "shapes":
        make_shapes(a.out, a.n, a.format)
    else:
        make_paste(a.objects, a.backgrounds, a.out, a.n, tuple(a.per_image), tuple(a.scale), size=a.size)
