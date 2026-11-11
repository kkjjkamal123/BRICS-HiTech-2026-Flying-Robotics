#!/usr/bin/env python3
"""
label_tool.py - fast OFFLINE bounding-box labeller (OpenCV window). Saves YOLO labels.

  python train/label_tool.py my_images/ --classes fire smoke car
  python train/label_tool.py my_images/                      # classes from my_images/classes.txt
  -> labels in my_images/labels/*.txt + my_images/classes.txt  -> then:
  python train/prepare_dataset.py my_images --out datasets/fire

MOUSE   left-drag = new box (current class)   right-click on a box = delete it
KEYS    1..9  choose class            d / space = next image (auto-saves)    a = previous
        w     change class of last box to current class
        u     undo last box           c = clear all boxes on this image      e = mark empty (no objects)
        z     zoom fit on/off          g = go to first unlabelled image       q / ESC = save + quit
        h     help in terminal
Resumes at the first unlabelled image. Also good to REVIEW boxes made by autolabel.py.
"""
import argparse
import glob
import os
import sys

import cv2
import numpy as np

COLORS = [(0, 0, 255), (0, 200, 0), (255, 0, 0), (0, 200, 255), (255, 0, 255), (255, 255, 0), (0, 128, 255),
          (128, 0, 255), (0, 255, 128), (200, 200, 200)]
IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")


class Labeller(object):
    def __init__(self, folder, classes, max_w=1400, max_h=850):
        self.folder = folder
        self.files = sorted(f for f in glob.glob(os.path.join(folder, "*")) if f.lower().endswith(IMG_EXT))
        if not self.files:
            sys.exit("no images in %s" % folder)
        self.ldir = os.path.join(folder, "labels")
        if not os.path.isdir(self.ldir):
            os.makedirs(self.ldir)
        self.classes = classes
        open(os.path.join(folder, "classes.txt"), "w").write("\n".join(classes) + "\n")
        self.cur_cls, self.i = 0, 0
        self.max_w, self.max_h, self.fit = max_w, max_h, True
        self.drag = None
        self.boxes = []

    def label_path(self, f):
        return os.path.join(self.ldir, os.path.splitext(os.path.basename(f))[0] + ".txt")

    def load(self):
        f = self.files[self.i]
        self.img = cv2.imread(f)
        H, W = self.img.shape[:2]
        self.scale = min(1.0, self.max_w / float(W), self.max_h / float(H)) if self.fit else 1.0
        self.boxes = []
        p = self.label_path(f)
        if os.path.exists(p):
            for line in open(p):
                v = line.split()
                if len(v) == 5:
                    c, cx, cy, w, h = int(v[0]), float(v[1]) * W, float(v[2]) * H, float(v[3]) * W, float(v[4]) * H
                    self.boxes.append([c, cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])

    def save(self, empty_ok=False):
        H, W = self.img.shape[:2]
        p = self.label_path(self.files[self.i])
        if not self.boxes and not empty_ok and not os.path.exists(p):
            return
        with open(p, "w") as f:
            for c, x1, y1, x2, y2 in self.boxes:
                x1, x2 = sorted((max(0, x1), min(W, x2)))
                y1, y2 = sorted((max(0, y1), min(H, y2)))
                if x2 - x1 < 2 or y2 - y1 < 2:
                    continue
                f.write("%d %.6f %.6f %.6f %.6f\n" % (c, (x1 + x2) / 2 / W, (y1 + y2) / 2 / H, (x2 - x1) / W, (y2 - y1) / H))

    def first_unlabelled(self):
        for k, f in enumerate(self.files):
            if not os.path.exists(self.label_path(f)):
                return k
        return len(self.files) - 1

    def render(self):
        s = self.scale
        vis = cv2.resize(self.img, None, fx=s, fy=s) if s != 1.0 else self.img.copy()
        for c, x1, y1, x2, y2 in self.boxes:
            col = COLORS[c % len(COLORS)]
            cv2.rectangle(vis, (int(x1 * s), int(y1 * s)), (int(x2 * s), int(y2 * s)), col, 2)
            cv2.putText(vis, self.classes[c] if c < len(self.classes) else str(c), (int(x1 * s), max(12, int(y1 * s) - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2)
        if self.drag and self.drag[2] is not None:
            x0, y0, x1, y1 = self.drag
            cv2.rectangle(vis, (x0, y0), (x1, y1), COLORS[self.cur_cls % len(COLORS)], 1)
        done = sum(os.path.exists(self.label_path(f)) for f in self.files)
        bar = "[%d/%d] %s | class %d: %s | boxes %d | labelled %d/%d | h=help" % (
            self.i + 1, len(self.files), os.path.basename(self.files[self.i]), self.cur_cls + 1,
            self.classes[self.cur_cls], len(self.boxes), done, len(self.files))
        cv2.rectangle(vis, (0, 0), (vis.shape[1], 24), (0, 0, 0), -1)
        cv2.putText(vis, bar, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        y = 44
        for k, n in enumerate(self.classes[:9]):
            cv2.putText(vis, "%d %s" % (k + 1, n), (6, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        COLORS[k % len(COLORS)], 2 if k == self.cur_cls else 1)
            y += 18
        cv2.imshow("label_tool", vis)

    def on_mouse(self, ev, x, y, flags, _):
        s = self.scale
        if ev == cv2.EVENT_LBUTTONDOWN:
            self.drag = [x, y, x, y]
        elif ev == cv2.EVENT_MOUSEMOVE and self.drag:
            self.drag[2], self.drag[3] = x, y
            self.render()
        elif ev == cv2.EVENT_LBUTTONUP and self.drag:
            x0, y0 = self.drag[0], self.drag[1]
            self.drag = None
            if abs(x - x0) > 3 and abs(y - y0) > 3:
                self.boxes.append([self.cur_cls, min(x0, x) / s, min(y0, y) / s, max(x0, x) / s, max(y0, y) / s])
            self.render()
        elif ev == cv2.EVENT_RBUTTONDOWN:
            px, py = x / s, y / s
            for k in range(len(self.boxes) - 1, -1, -1):
                _, x1, y1, x2, y2 = self.boxes[k]
                if x1 <= px <= x2 and y1 <= py <= y2:
                    del self.boxes[k]
                    break
            self.render()

    def run(self):
        cv2.namedWindow("label_tool", cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback("label_tool", self.on_mouse)
        self.i = self.first_unlabelled()
        self.load()
        while True:
            self.render()
            k = cv2.waitKey(0) & 0xFF
            if k in (ord("q"), 27):
                self.save()
                break
            elif ord("1") <= k <= ord("9") and k - ord("1") < len(self.classes):
                self.cur_cls = k - ord("1")
            elif k in (ord("d"), ord(" "), ord("n")):
                self.save(empty_ok=True)
                if self.i < len(self.files) - 1:
                    self.i += 1
                    self.load()
                else:
                    print("last image")
            elif k in (ord("a"), ord("p")):
                self.save()
                if self.i > 0:
                    self.i -= 1
                    self.load()
            elif k == ord("u") and self.boxes:
                self.boxes.pop()
            elif k == ord("w") and self.boxes:
                self.boxes[-1][0] = self.cur_cls
            elif k == ord("c"):
                self.boxes = []
            elif k == ord("e"):
                self.boxes = []
                self.save(empty_ok=True)
                if self.i < len(self.files) - 1:
                    self.i += 1
                    self.load()
            elif k == ord("z"):
                self.fit = not self.fit
                self.save()
                self.load()
            elif k == ord("g"):
                self.save()
                self.i = self.first_unlabelled()
                self.load()
            elif k == ord("h"):
                print(__doc__)
        cv2.destroyAllWindows()
        n = sum(os.path.exists(self.label_path(f)) for f in self.files)
        print("labelled %d/%d images -> %s" % (n, len(self.files), self.ldir))
        print("NEXT: python train/prepare_dataset.py %s --out datasets/<name>" % self.folder)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--classes", nargs="*")
    a = ap.parse_args()
    cls = a.classes
    cf = os.path.join(a.folder, "classes.txt")
    if not cls and os.path.exists(cf):
        cls = [l.strip() for l in open(cf) if l.strip()]
    if not cls:
        sys.exit("give --classes name1 name2 ...")
    Labeller(a.folder, cls).run()
