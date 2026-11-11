#!/usr/bin/env python3
"""
extract_frames.py - turn videos (phone / drone recordings) into a clean image folder for labelling.
Skips blurry frames and near-duplicates automatically.

  python train/extract_frames.py flight1.mp4 flight2.mp4 --out venue_photos --every 0.5
  python train/extract_frames.py runs/case1_fire_*/frames --out venue_photos      # mission frames
Options: --every SECONDS between frames, --min-sharpness (variance of Laplacian), --max-similarity
"""
import argparse
import glob
import os

import cv2
import numpy as np

IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp")


def sharpness(img):
    return cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()


def signature(img):
    s = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (32, 24)).astype(np.float32)
    return (s - s.mean()) / (s.std() + 1e-6)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--every", type=float, default=0.5, help="seconds between frames (videos)")
    ap.add_argument("--min-sharpness", type=float, default=40.0)
    ap.add_argument("--max-similarity", type=float, default=0.97, help="skip frames more similar than this")
    ap.add_argument("--resize", type=int, default=0, help="max width (0 = keep)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    last, kept, seen = None, 0, 0

    def consider(img, tag):
        nonlocal last, kept, seen
        seen += 1
        if img is None or sharpness(img) < a.min_sharpness:
            return
        sig = signature(img)
        if last is not None and float((sig * last).mean()) > a.max_similarity:
            return
        last = sig
        if a.resize and img.shape[1] > a.resize:
            img = cv2.resize(img, (a.resize, int(img.shape[0] * a.resize / float(img.shape[1]))))
        cv2.imwrite(os.path.join(a.out, "%s_%05d.jpg" % (tag, kept)), img)
        kept += 1

    for src in a.sources:
        tag = os.path.splitext(os.path.basename(src.rstrip("/")))[0]
        if os.path.isdir(src):
            for f in sorted(glob.glob(os.path.join(src, "*"))):
                if f.lower().endswith(IMG_EXT):
                    consider(cv2.imread(f), tag)
            continue
        cap = cv2.VideoCapture(src)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, int(round(fps * a.every)))
        k = 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            if k % step == 0:
                ok, img = cap.retrieve()
                if ok:
                    consider(img, tag)
            k += 1
    print("checked %d frames, kept %d sharp & different images -> %s" % (seen, kept, a.out))
    print("NEXT: python train/label_tool.py %s --classes ..." % a.out)


if __name__ == "__main__":
    main()
