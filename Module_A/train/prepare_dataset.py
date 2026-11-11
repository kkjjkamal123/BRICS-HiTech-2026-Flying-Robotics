#!/usr/bin/env python3
"""
prepare_dataset.py - turn ANY dataset they give you into a clean, train-ready YOLO dataset.

Auto-detects (folder or .zip):
  * YOLO          data.yaml + images/labels (Roboflow "YOLOv5/v8/v11" export, Ultralytics)  or  images + .txt
  * COCO JSON     *.json with images/annotations/categories (Roboflow "COCO", CVAT, LabelMe->COCO)
  * Pascal VOC    *.xml per image (LabelImg, CVAT VOC)
  * CSV           filename,class,xmin,ymin,xmax,ymax  (Roboflow "TensorFlow CSV", Kaggle style; also x,y,w,h)
  * Classification   folder-per-class  (fire/ nofire/ ...)  with or without train/val sub-folders
  * Only images   -> tells you to label them (train/label_tool.py or train/autolabel.py)

Several inputs can be MERGED (classes matched by name). Classes can be renamed / filtered.

Usage:
  python train/prepare_dataset.py INPUT [INPUT2 ...] --out datasets/fire
  python train/prepare_dataset.py fire.zip --out datasets/fire --val 0.2
  python train/prepare_dataset.py a/ b/ --out datasets/mix --rename Fire=fire flame=fire --keep fire smoke
  python train/prepare_dataset.py cls_folders/ --out datasets/fire_cls          (classification)
  python train/prepare_dataset.py coco/ --out datasets/weeds_seg --task segment (polygons -> YOLO-seg)

Output:  OUT/images/{train,val[,test]}  OUT/labels/{...}  OUT/data.yaml  OUT/dataset_report.txt
         (classification: OUT/train/<class>/  OUT/val/<class>/)
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import random
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")
SPLIT_ALIASES = {"train": "train", "training": "train", "val": "val", "valid": "val", "validation": "val",
                 "test": "test", "testing": "test"}


# ----------------------------------------------------------------------------- utils
def is_img(p):
    return p.lower().endswith(IMG_EXT)


def all_files(root):
    for d, _, fs in os.walk(root):
        if "/." in d or "__MACOSX" in d:
            continue
        for f in fs:
            if not f.startswith("."):
                yield os.path.join(d, f)


def split_of(path, root):
    """Find train/val/test in the path (Roboflow: train/images/x.jpg, valid/..)."""
    for part in os.path.relpath(path, root).lower().replace("\\", "/").split("/")[:-1]:
        if part in SPLIT_ALIASES:
            return SPLIT_ALIASES[part]
    return None


def img_size(path):
    try:
        import cv2
        im = cv2.imread(path)
        if im is not None:
            return im.shape[1], im.shape[0]
    except ImportError:
        pass
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def uniq_name(path):
    h = hashlib.md5(os.path.abspath(path).encode()).hexdigest()[:6]
    b, e = os.path.splitext(os.path.basename(path))
    return "%s_%s%s" % (b.replace(" ", "_"), h, e.lower())


def extract_zip(p, workdir):
    out = os.path.join(workdir, os.path.splitext(os.path.basename(p))[0])
    if not os.path.isdir(out):
        print("[prep] extracting", p)
        with zipfile.ZipFile(p) as z:
            z.extractall(out)
    return out


def load_yaml(p):
    try:
        import yaml
        return yaml.safe_load(open(p))
    except ImportError:          # tiny fallback parser for 'names:'
        names = []
        for line in open(p):
            line = line.strip()
            if line.startswith("names:") and "[" in line:
                names = [n.strip().strip("'\"") for n in line.split("[", 1)[1].rsplit("]", 1)[0].split(",")]
        return {"names": names}


# ----------------------------------------------------------------------------- record format
# Every reader returns list of samples: {"img": path, "split": train/val/test/None,
#   "boxes": [(class_name, cx, cy, w, h) normalised]  or "polys": [(class_name, [x1,y1,x2,y2...] normalised)]}


def read_yolo(root):
    yamls = [f for f in all_files(root) if os.path.basename(f) in ("data.yaml", "dataset.yaml", "data.yml")]
    names = None
    if yamls:
        y = load_yaml(yamls[0]) or {}
        n = y.get("names")
        names = [n[k] for k in sorted(n)] if isinstance(n, dict) else n
    for nf in ("classes.txt", "obj.names", "_darknet.labels", "names.txt"):
        cand = [f for f in all_files(root) if os.path.basename(f) == nf]
        if not names and cand:
            names = [l.strip() for l in open(cand[0]) if l.strip()]
    txts = {}
    for f in all_files(root):
        if f.endswith(".txt") and os.path.basename(f) not in ("classes.txt", "obj.names", "names.txt", "README.txt", "README.roboflow.txt"):
            txts.setdefault(os.path.splitext(os.path.basename(f))[0], []).append(f)
    samples = []
    for f in all_files(root):
        if not is_img(f):
            continue
        stem = os.path.splitext(os.path.basename(f))[0]
        cands = txts.get(stem, [])
        # prefer the label file whose path mirrors the image path (images/ -> labels/)
        want = f.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt"
        lab = want if want in cands else (cands[0] if cands else None)
        s = {"img": f, "split": split_of(f, root), "boxes": [], "polys": []}
        if lab:
            for line in open(lab):
                v = line.split()
                if len(v) < 5:
                    continue
                c = int(float(v[0]))
                cname = names[c] if names and c < len(names) else "class%d" % c
                nums = [float(x) for x in v[1:]]
                if len(nums) == 4:
                    s["boxes"].append((cname,) + tuple(nums))
                else:                                   # segmentation polygon
                    s["polys"].append((cname, nums))
        s["labelled"] = lab is not None
        samples.append(s)
    return samples


def read_coco(root, jsons):
    # global class list = categories that have >= 1 annotation (Roboflow adds an empty super-category)
    used, catname = set(), {}
    data = []
    for j in jsons:
        d = json.load(open(j))
        data.append((j, d))
        for c in d.get("categories", []):
            catname[(j, c["id"])] = c["name"]
        for a in d.get("annotations", []):
            used.add(catname.get((j, a["category_id"])))
    samples = []
    for j, d in data:
        base = os.path.dirname(j)
        anns = {}
        for a in d.get("annotations", []):
            anns.setdefault(a["image_id"], []).append(a)
        idx = {}
        for f in all_files(root):
            if is_img(f):
                idx.setdefault(os.path.basename(f), f)
        for im in d["images"]:
            fn = im["file_name"]
            p = os.path.join(base, fn)
            if not os.path.exists(p):
                p = idx.get(os.path.basename(fn))
            if not p:
                continue
            W, H = float(im.get("width") or 0), float(im.get("height") or 0)
            if not W or not H:
                W, H = img_size(p)
            s = {"img": p, "split": split_of(j, root) or split_of(p, root), "boxes": [], "polys": [], "labelled": True}
            for a in anns.get(im["id"], []):
                name = catname.get((j, a["category_id"]))
                if name not in used:
                    continue
                x, y, w, h = a["bbox"]
                if w <= 0 or h <= 0:
                    continue
                s["boxes"].append((name, (x + w / 2) / W, (y + h / 2) / H, w / W, h / H))
                seg = a.get("segmentation")
                if isinstance(seg, list) and seg and isinstance(seg[0], list) and len(seg[0]) >= 6:
                    poly = seg[0]
                    s["polys"].append((name, [poly[i] / (W if i % 2 == 0 else H) for i in range(len(poly))]))
            samples.append(s)
    return samples


def read_voc(root, xmls):
    idx = {}
    for f in all_files(root):
        if is_img(f):
            idx.setdefault(os.path.splitext(os.path.basename(f))[0], f)
    samples = []
    for x in xmls:
        try:
            r = ET.parse(x).getroot()
        except ET.ParseError:
            continue
        if r.tag != "annotation":
            continue
        fn = (r.findtext("filename") or "").strip()
        p = os.path.join(os.path.dirname(x), fn)
        if not (fn and os.path.exists(p)):
            p = idx.get(os.path.splitext(os.path.basename(fn))[0]) or idx.get(os.path.splitext(os.path.basename(x))[0])
        if not p:
            continue
        W = float(r.findtext("size/width") or 0)
        H = float(r.findtext("size/height") or 0)
        if not W or not H:
            W, H = img_size(p)
        s = {"img": p, "split": split_of(x, root), "boxes": [], "polys": [], "labelled": True}
        for o in r.findall("object"):
            b = o.find("bndbox")
            x1, y1, x2, y2 = [float(b.findtext(k)) for k in ("xmin", "ymin", "xmax", "ymax")]
            s["boxes"].append((o.findtext("name").strip(), (x1 + x2) / 2 / W, (y1 + y2) / 2 / H, (x2 - x1) / W, (y2 - y1) / H))
        samples.append(s)
    return samples


def read_csv(root, csvs):
    def col(cols, *names):
        low = {c.lower().strip(): c for c in cols}
        for n in names:
            if n in low:
                return low[n]
        return None
    idx = {}
    for f in all_files(root):
        if is_img(f):
            idx.setdefault(os.path.basename(f), f)
    by_img = {}
    for c in csvs:
        rows = list(csv.DictReader(open(c)))
        if not rows:
            continue
        cols = rows[0].keys()
        fcol = col(cols, "filename", "file", "image", "image_id", "img", "path", "image_path", "file_name")
        ccol = col(cols, "class", "label", "name", "category", "class_name")
        x1c, y1c = col(cols, "xmin", "x_min", "x1", "left"), col(cols, "ymin", "y_min", "y1", "top")
        x2c, y2c = col(cols, "xmax", "x_max", "x2", "right"), col(cols, "ymax", "y_max", "y2", "bottom")
        xc, yc, wc, hc = col(cols, "x"), col(cols, "y"), col(cols, "w", "width_box", "bbox_width"), col(cols, "h", "height_box", "bbox_height")
        Wc, Hc = col(cols, "width"), col(cols, "height")
        if not fcol or not ccol:
            continue
        for r in rows:
            fn = r[fcol]
            p = os.path.join(os.path.dirname(c), fn)
            if not os.path.exists(p):
                p = idx.get(os.path.basename(fn)) or idx.get(os.path.basename(fn) + ".jpg") or idx.get(os.path.basename(fn) + ".png")
            if not p:
                continue
            s = by_img.setdefault(p, {"img": p, "split": split_of(c, root) or split_of(p, root), "boxes": [], "polys": [], "labelled": True})
            if not r.get(ccol):
                continue
            W = float(r[Wc]) if Wc and r.get(Wc) else None
            H = float(r[Hc]) if Hc and r.get(Hc) else None
            if not W or not H:
                W, H = img_size(p)
            try:
                if x1c and x2c:
                    x1, y1, x2, y2 = float(r[x1c]), float(r[y1c]), float(r[x2c]), float(r[y2c])
                else:
                    x1, y1 = float(r[xc]), float(r[yc])
                    x2, y2 = x1 + float(r[wc]), y1 + float(r[hc])
            except (TypeError, ValueError):
                continue
            if max(x2, y2) <= 1.0:      # already normalised
                W = H = 1.0
            s["boxes"].append((r[ccol].strip(), (x1 + x2) / 2 / W, (y1 + y2) / 2 / H, (x2 - x1) / W, (y2 - y1) / H))
    return list(by_img.values())


def detect_classification(root):
    """class folders with images and no annotation files -> {split: {class: [imgs]}}"""
    files = list(all_files(root))
    if any(f.endswith((".txt", ".xml", ".json", ".csv")) and "readme" not in f.lower() for f in files):
        return None
    out = {}
    for f in files:
        if not is_img(f):
            continue
        parts = os.path.relpath(f, root).replace("\\", "/").split("/")
        if len(parts) < 2:
            return None
        cls = parts[-2]
        sp = SPLIT_ALIASES.get(parts[-3].lower()) if len(parts) >= 3 else None
        out.setdefault(sp, {}).setdefault(cls, []).append(f)
    return out or None


def read_any(src, workdir, task):
    if src.lower().endswith(".zip"):
        src = extract_zip(src, workdir)
    if not os.path.isdir(src):
        sys.exit("[prep] not found: %s" % src)
    files = list(all_files(src))
    jsons = []
    for f in files:
        if f.endswith(".json"):
            try:
                with open(f) as fh:
                    head = fh.read(4000)
                if '"images"' in head or '"annotations"' in head or '"categories"' in head:
                    d = json.load(open(f))
                    if "images" in d and "annotations" in d:
                        jsons.append(f)
            except Exception:
                pass
    if task == "classify":
        c = detect_classification(src)
        if c:
            return "classify", c
    if any(os.path.basename(f) in ("data.yaml", "dataset.yaml") for f in files) or \
            any(f.endswith(".txt") and "/labels/" in f for f in files):
        return "YOLO", read_yolo(src)
    if jsons:
        return "COCO", read_coco(src, jsons)
    xmls = [f for f in files if f.endswith(".xml")]
    if xmls:
        return "VOC", read_voc(src, xmls)
    csvs = [f for f in files if f.endswith(".csv")]
    if csvs:
        s = read_csv(src, csvs)
        if s:
            return "CSV", s
    if any(f.endswith(".txt") for f in files):
        s = read_yolo(src)
        if any(x["labelled"] for x in s):
            return "YOLO", s
    c = detect_classification(src)
    if c:
        return "classify", c
    imgs = [f for f in files if is_img(f)]
    if imgs:
        sys.exit("[prep] %d images but NO labels in %s.\n  -> label them:   python train/label_tool.py %s --classes a b c\n"
                 "  -> or auto-label: python train/autolabel.py %s --detector hsv|exg|model.pt" % (len(imgs), src, src, src))
    sys.exit("[prep] could not recognise dataset format in %s" % src)


# ----------------------------------------------------------------------------- writers
def write_detect(samples, out, val, test, seed, task, names_order=None, link=False):
    rnd = random.Random(seed)
    names = names_order or sorted({b[0] for s in samples for b in s["boxes"]} | {p[0] for s in samples for p in s["polys"]})
    cid = {n: i for i, n in enumerate(names)}
    have_split = any(s["split"] == "val" for s in samples)
    if not have_split:
        rnd.shuffle(samples)
        n = len(samples)
        nv = max(1, int(round(n * val))) if n > 1 else 0
        nt = int(round(n * test))
        for i, s in enumerate(samples):
            s["split"] = "val" if i < nv else ("test" if i < nv + nt else "train")
    for s in samples:
        s["split"] = s["split"] or "train"
    if os.path.isdir(out):
        shutil.rmtree(out)
    stats = {}
    for s in samples:
        sp = s["split"]
        di, dl = os.path.join(out, "images", sp), os.path.join(out, "labels", sp)
        for d in (di, dl):
            if not os.path.isdir(d):
                os.makedirs(d)
        name = uniq_name(s["img"])
        dst = os.path.join(di, name)
        if link:
            try:
                os.link(s["img"], dst)
            except OSError:
                shutil.copy2(s["img"], dst)
        else:
            shutil.copy2(s["img"], dst)
        lines = []
        if task == "segment" and s["polys"]:
            for n_, poly in s["polys"]:
                if n_ in cid:
                    lines.append("%d " % cid[n_] + " ".join("%.6f" % min(1, max(0, v)) for v in poly))
        else:
            for n_, cx, cy, w, h in s["boxes"]:
                if n_ not in cid or w <= 0 or h <= 0:
                    continue
                cx, cy = min(1, max(0, cx)), min(1, max(0, cy))
                w, h = min(1, w), min(1, h)
                lines.append("%d %.6f %.6f %.6f %.6f" % (cid[n_], cx, cy, w, h))
        with open(os.path.join(dl, os.path.splitext(name)[0] + ".txt"), "w") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
        st = stats.setdefault(sp, {"images": 0, "background": 0})
        st["images"] += 1
        if not lines:
            st["background"] += 1
        for l in lines:
            k = names[int(l.split()[0])]
            st[k] = st.get(k, 0) + 1
    splits = sorted(stats)
    y = "# generated by prepare_dataset.py\npath: %s\n" % os.path.abspath(out)
    y += "train: images/train\nval: images/%s\n" % ("val" if "val" in stats else "train")
    if "test" in stats:
        y += "test: images/test\n"
    y += "names:\n" + "".join("  %d: %s\n" % (i, n) for i, n in enumerate(names))
    open(os.path.join(out, "data.yaml"), "w").write(y)
    return names, stats, splits


def write_classify(groups, out, val, seed, keep=None, rename=None):
    rnd = random.Random(seed)
    if os.path.isdir(out):
        shutil.rmtree(out)
    merged = {}
    for sp, classes in groups.items():
        for c, imgs in classes.items():
            c = rename.get(c, c) if rename else c
            if keep and c not in keep:
                continue
            merged.setdefault(c, []).extend((sp, i) for i in imgs)
    stats = {}
    for c, items in merged.items():
        has_val = any(sp == "val" for sp, _ in items)
        rnd.shuffle(items)
        nv = max(1, int(round(len(items) * val)))
        for k, (sp, img) in enumerate(items):
            if not has_val:
                sp = "val" if k < nv else "train"
            sp = sp or "train"
            d = os.path.join(out, sp, c)
            if not os.path.isdir(d):
                os.makedirs(d)
            shutil.copy2(img, os.path.join(d, uniq_name(img)))
            stats.setdefault(sp, {}).setdefault(c, 0)
            stats[sp][c] += 1
    open(os.path.join(out, "names.txt"), "w").write("\n".join(sorted(merged)) + "\n")
    return sorted(merged), stats


# ----------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="dataset folder(s) or .zip file(s)")
    ap.add_argument("--out", required=True, help="output folder, e.g. datasets/fire")
    ap.add_argument("--val", type=float, default=0.15, help="validation fraction if the data has no split")
    ap.add_argument("--test", type=float, default=0.0, help="test fraction if the data has no split")
    ap.add_argument("--task", choices=["detect", "segment", "classify", "auto"], default="auto")
    ap.add_argument("--rename", nargs="*", default=[], help="OLD=NEW class renames (merge synonyms)")
    ap.add_argument("--keep", nargs="*", help="keep only these classes (after renaming)")
    ap.add_argument("--drop", nargs="*", default=[], help="drop these classes")
    ap.add_argument("--resplit", action="store_true", help="ignore the existing train/val split, make a new one")
    ap.add_argument("--max-background", type=float, default=0.3, help="max fraction of images with no objects")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--link", action="store_true", help="hard-link instead of copying images (saves disk)")
    a = ap.parse_args(argv)

    rename = dict(r.split("=", 1) for r in a.rename)
    work = os.path.join(os.path.dirname(os.path.abspath(a.out)), "_extracted")
    if not os.path.isdir(work):
        os.makedirs(work)

    all_samples, cls_groups, formats = [], None, []
    for src in a.inputs:
        fmt, data = read_any(src, work, a.task)
        formats.append("%s (%s)" % (fmt, src))
        print("[prep] %s: format %s" % (src, fmt))
        if fmt == "classify":
            if cls_groups is None:
                cls_groups = {}
            for sp, d in data.items():
                for c, imgs in d.items():
                    cls_groups.setdefault(sp, {}).setdefault(c, []).extend(imgs)
            continue
        all_samples += data

    if cls_groups is not None and not all_samples:
        names, stats = write_classify(cls_groups, a.out, a.val, a.seed, a.keep, rename)
        rep = "Classification dataset: %s\nclasses: %s\n%s\n" % (a.out, names, json.dumps(stats, indent=1))
        open(os.path.join(a.out, "dataset_report.txt"), "w").write(rep)
        print(rep + "\nNEXT: python train/train.py --data %s" % a.out)
        return a.out

    task = a.task if a.task != "auto" else ("segment" if any(s["polys"] for s in all_samples) and
                                            all(s["polys"] or not s["boxes"] for s in all_samples) else "detect")
    # rename / filter
    for s in all_samples:
        s["boxes"] = [(rename.get(b[0], b[0]),) + tuple(b[1:]) for b in s["boxes"]]
        s["polys"] = [(rename.get(p[0], p[0]), p[1]) for p in s["polys"]]
        if a.keep:
            s["boxes"] = [b for b in s["boxes"] if b[0] in a.keep]
            s["polys"] = [p for p in s["polys"] if p[0] in a.keep]
        s["boxes"] = [b for b in s["boxes"] if b[0] not in a.drop]
        s["polys"] = [p for p in s["polys"] if p[0] not in a.drop]
        if a.resplit:
            s["split"] = None
    # limit background images
    fg = [s for s in all_samples if s["boxes"] or s["polys"]]
    bg = [s for s in all_samples if not (s["boxes"] or s["polys"])]
    max_bg = int(len(fg) * a.max_background / max(1e-6, 1 - a.max_background))
    random.Random(a.seed).shuffle(bg)
    if len(bg) > max_bg:
        print("[prep] keeping %d of %d background (empty) images" % (max_bg, len(bg)))
        bg = bg[:max_bg]
    samples = fg + bg
    if not fg:
        sys.exit("[prep] no labelled objects found - check --keep/--rename or the dataset")

    names, stats, splits = write_detect(samples, a.out, a.val, a.test, a.seed, task, link=a.link)
    lines = ["Dataset: %s" % os.path.abspath(a.out), "Task: %s" % task, "Sources: %s" % "; ".join(formats),
             "Classes (%d): %s" % (len(names), ", ".join("%d=%s" % (i, n) for i, n in enumerate(names))), ""]
    for sp in splits:
        lines.append("%-5s %s" % (sp, json.dumps(stats[sp])))
    tr = stats.get("train", {})
    warn = [n for n in names if tr.get(n, 0) < 30]
    if warn:
        lines.append("\nWARNING few training examples (<30) for: %s  -> label more / use make_synthetic.py paste" % ", ".join(warn))
    rep = "\n".join(lines)
    open(os.path.join(a.out, "dataset_report.txt"), "w").write(rep + "\n")
    print(rep)
    print("\nNEXT: python train/train.py --data %s/data.yaml" % a.out)
    return a.out


if __name__ == "__main__":
    main()
