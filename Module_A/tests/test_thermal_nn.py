#!/usr/bin/env python3
"""Thermal neural network in the Case 1 detector chain (no ROS, no model needed).

  python tests/test_thermal_nn.py

Checks: a YOLO-type detector running on the thermal picture gets each box's hottest deg C from the temperature map,
`min_temp_c` (number or {class: deg C}) drops cold boxes, `fire_c` follows the thermal rule's threshold, and the
Case 1 config lists the thermal network on the thermal camera.
"""
import os
import sys

import numpy as np
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from common import detector as D  # noqa: E402


class FakeNet(object):
    """Stands in for the thermal YOLO: returns fixed boxes."""
    def __init__(self, dets):
        self.dets = dets

    def __call__(self, img):
        return [dict(d) for d in self.dets]


def scene():
    temp = np.full((192, 256), 22.0, np.float32)
    temp[40:50, 40:50] = 160.0            # heater
    temp[100:130, 150:180] = 70.0          # lamp: warm, below 100 C
    img = np.zeros((192, 256, 3), np.uint8)
    return img, temp


def run(min_temp_c, threshold_c=100.0):
    net = FakeNet([D._det("fire", 0, 0.9, 38, 38, 52, 52, "thermal_nn"),
                   D._det("flame", 1, 0.8, 148, 98, 182, 132, "thermal_nn"),
                   D._det("fire", 0, 0.6, 200, 10, 220, 30, "thermal_nn")])      # cold floor: no heat there
    net.every, net.min_temp_c = 1, min_temp_c
    th = D.ThermalDetector(mode="celsius", threshold_c=threshold_c, min_area=4, label="fire")
    th.every, th.min_temp_c = 1, None
    md = D.MultiDetector([(net, "thermal", 0), (th, "thermal_temp", 0)])
    # resolve 'fire_c' the way build_detector does
    for d, _, _ in md.detectors:
        if isinstance(getattr(d, "min_temp_c", None), dict):
            d.min_temp_c = {k: (threshold_c if v == "fire_c" else v) for k, v in d.min_temp_c.items()}
    img, temp = scene()
    return [d for d in md({"thermal": img, "thermal_temp": temp}) if d["source"] == "thermal_nn"]


def main():
    fails = []

    def check(ok, what):
        print(("PASS  " if ok else "FAIL  ") + what)
        if not ok:
            fails.append(what)

    out = run(None)
    check(len(out) == 3 and all("max_temp_c" in d for d in out), "every NN box gets max_temp_c")
    check(abs(out[0]["max_temp_c"] - 160.0) < 0.01 and abs(out[1]["max_temp_c"] - 70.0) < 0.01,
          "heater box reads 160 C, lamp box reads 70 C")
    out = run({"fire": "fire_c"})
    names = sorted((d["name"], round(d["max_temp_c"])) for d in out)
    check(names == [("fire", 160), ("flame", 70)], "{fire: fire_c}: cold 'fire' box dropped, lamp kept (%s)" % names)
    out = run({"fire": "fire_c"}, threshold_c=200.0)
    check([d["name"] for d in out] == ["flame"], "fire_c follows the thermal rule (200 C drops the 160 C heater)")
    out = run(100.0)
    check([d["name"] for d in out] == ["fire"], "a plain number applies to every class")

    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "case1_fire.yaml")))
    nn = [d for d in cfg["detectors"] if d.get("type") == "yolo" and d.get("image") == "thermal"]
    check(len(nn) == 1 and "thermal_fire" in nn[0]["model"], "case1 config runs the thermal network on the thermal camera")
    check(os.path.exists(os.path.join(ROOT, nn[0]["model"])) if nn else False, "thermal model file exists (%s)" % (nn[0]["model"] if nn else "-"))
    b = D.build_detector(cfg["detectors"], base_dir=ROOT)
    srcs = [os.path.basename(getattr(d, "model_path", "") or "") for d, k, _ in b.detectors if k == "thermal"]
    check(any(s for s in srcs), "build_detector loads the thermal network (%s)" % srcs)
    print("\n%d failed" % len(fails))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
