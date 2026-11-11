#!/usr/bin/env python3
"""
thermal_probe.py - find the USB thermal camera (TR256i / InfiRay P2 / TC001 ...) and check what it delivers.

  python3 tools/thermal_probe.py            # list + test every camera, print the config to use
  python3 tools/thermal_probe.py --show 1   # live view of device 1 with max temperature (needs a screen)
  python3 tools/thermal_probe.py --snap 1   # save runs/thermal_snap.png (+ .npy temperatures) - works over SSH

Point it at something hot (hand ~34 C, IR heater > 100 C) and check the max temperature.
Python 3.8 compatible (runs on the Orange Pi).
"""
import argparse
import glob
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from common.thermal import annotate, colorize, decode_p2  # noqa: E402

LINUX = sys.platform.startswith("linux")


def devices():
    if LINUX:
        return sorted(int(p.replace("/dev/video", "")) for p in glob.glob("/dev/video*") if p[10:].isdigit())
    return list(range(6))


def probe(dev):
    res = {"device": dev, "opens": False, "raw": False}
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2 if LINUX else cv2.CAP_ANY)
    if not cap.isOpened():
        return res
    cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
    ok, raw = cap.read()
    if ok:
        res["opens"] = True
        res["raw_shape"] = tuple(np.asarray(raw).shape)
        img, temp = decode_p2(raw)
        if img is not None:
            res["raw"] = True
            res["t_median"], res["t_max"] = float(np.median(temp)), float(temp.max())
    cap.release()
    if not res["raw"]:
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2 if LINUX else cv2.CAP_ANY)
        ok, img = cap.read()
        if ok:
            res["opens"] = True
            res["shape"] = tuple(img.shape)
        cap.release()
    return res


def grab(dev):
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2 if LINUX else cv2.CAP_ANY)
    cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
    raw_mode = True
    for _ in range(5):
        ok, raw = cap.read()
    img, temp = decode_p2(raw) if ok else (None, None)
    if img is None:
        cap.release()
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2 if LINUX else cv2.CAP_ANY)
        raw_mode = False
    return cap, raw_mode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", type=int, help="live view of this device")
    ap.add_argument("--snap", type=int, help="save one snapshot of this device")
    a = ap.parse_args()
    if a.show is not None or a.snap is not None:
        dev = a.show if a.show is not None else a.snap
        cap, raw_mode = grab(dev)
        print("device %d: %s" % (dev, "RAW temperature mode" if raw_mode else "picture only (brightness mode)"))
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            if raw_mode:
                img, temp = decode_p2(frame)
                if img is None:
                    continue
                vis = annotate(cv2.resize(img, (512, 384), interpolation=cv2.INTER_NEAREST), temp)
            else:
                vis, temp = frame, None
            if a.snap is not None:
                os.makedirs(os.path.join(ROOT, "runs"), exist_ok=True)
                p = os.path.join(ROOT, "runs", "thermal_snap.png")
                cv2.imwrite(p, vis)
                if temp is not None:
                    np.save(p.replace(".png", ".npy"), temp)
                    print("max %.1f C, median %.1f C" % (temp.max(), np.median(temp)))
                print("saved", p)
                break
            cv2.imshow("thermal %d (q = quit)" % dev, vis)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
        return
    print("Probing cameras ...")
    found = []
    for d in devices():
        r = probe(d)
        if not r["opens"]:
            continue
        if r["raw"]:
            print("  /dev/video%d  RAW THERMAL  frame %s  median %.1f C  max %.1f C   <-- thermal camera (deg C)" % (
                d, r["raw_shape"], r["t_median"], r["t_max"]))
            found.append((d, "auto"))
        else:
            print("  /dev/video%d  picture %s" % (d, r.get("shape") or r.get("raw_shape")))
    if found:
        d, mode = found[0]
        print("\nPut this in the mission config (cameras:):\n  thermal:\n    type: cv\n    device: %d\n    thermal: %s\n    hfov_deg: 56" % (d, mode))
    else:
        print("\nNo raw-temperature camera found. If the thermal camera is listed as 'picture', use it with:\n"
              "    thermal: plain     (detector: type thermal, image: thermal, mode: percentile)\n"
              "Check it is plugged in:  lsusb ; v4l2-ctl --list-devices")


if __name__ == "__main__":
    main()
