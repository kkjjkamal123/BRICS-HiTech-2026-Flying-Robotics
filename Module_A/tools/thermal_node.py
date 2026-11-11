#!/usr/bin/env python3
"""TECHNIC 6S thermal node: owns the USB thermal camera (TR256i) and publishes REAL temperatures.

The camera sends a 256 x 384 frame: top half = picture, bottom half = raw temperature (16 bit, Kelvin x 64).
The drone's own "second camera" node throws that raw half away, so this node reads the device itself.

Publishes:
    /thermal/image_raw   bgr8     false-colour picture WITH the temperature scale, hottest point and FIRE boxes
                                  (this is what the dashboard shows; also at http://<drone>:8080)
    /thermal/temp        32FC1    temperature of every pixel, deg C        (the mission reads this)
    /thermal/max         Float32  hottest temperature in view, deg C
    /thermal/fire        Bool     true when anything is at or above --fire-c

Rule: everything at or above --fire-c (default 100 C) is fire. A running mission can change it with the ROS
parameter /thermal/fire_c (checked once a second; the dashboard's fire temperature setting).

Run (normally started by the service brics-thermal, see setup/install_thermal_service.sh):
    source /opt/ros/noetic/setup.bash
    python3 ~/brics_toolkit/tools/thermal_node.py [--device /dev/camera_second] [--fire-c 100] [--rate 12]
Laptop check without ROS or a camera:  python3 tools/thermal_node.py --selftest
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from common.thermal import decode_p2, render_view  # noqa: E402

W, H = 256, 192


def open_camera(device):
    """Open the thermal camera in raw mode (no colour conversion, both halves). None if it is not there yet."""
    dev = os.path.realpath(device) if isinstance(device, str) and os.path.exists(device) else device
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H * 2)
    cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def selftest():
    t = np.full((H, W), 23.0, np.float32) + np.random.RandomState(1).randn(H, W).astype(np.float32) * 0.3
    cv2.circle(t, (180, 60), 9, 36.5, -1)                       # a hand
    img, info = render_view(t)
    assert not info["fire"] and abs(info["max_c"] - 36.5) < 2, info
    cv2.circle(t, (70, 120), 6, 240.0, -1)                      # heater
    img, info = render_view(t)
    assert info["fire"] and len(info["regions"]) == 1 and info["max_c"] > 200, info
    assert img.shape[0] == H * 2 and img.shape[1] > W * 2
    # raw frame round trip: Kelvin x 64, little endian, in the bottom half
    raw = np.zeros((H * 2, W, 2), np.uint8)
    k = ((t + 273.15) * 64).astype(np.uint16)
    raw[H:, :, 0], raw[H:, :, 1] = k & 255, k >> 8
    _, back = decode_p2(raw)
    assert back is not None and float(np.abs(back - t).max()) < 0.05
    out = os.path.join(ROOT, "runs", "thermal_selftest.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cv2.imwrite(out, img)
    print("SELFTEST OK  ->", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="/dev/camera_second")
    ap.add_argument("--fire-c", type=float, default=100.0)
    ap.add_argument("--rate", type=float, default=25.0, help="published frames per second (the camera gives 25)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    import rospy
    from sensor_msgs.msg import Image
    from std_msgs.msg import Bool, Float32
    rospy.init_node("thermal_node")
    pub_img = rospy.Publisher("thermal/image_raw", Image, queue_size=1)
    pub_temp = rospy.Publisher("thermal/temp", Image, queue_size=1)
    pub_max = rospy.Publisher("thermal/max", Float32, queue_size=1)
    pub_fire = rospy.Publisher("thermal/fire", Bool, queue_size=1)

    def image_msg(arr, encoding, stamp):
        m = Image()
        m.header.stamp, m.header.frame_id = stamp, "thermal_optical"
        m.height, m.width, m.encoding, m.is_bigendian = arr.shape[0], arr.shape[1], encoding, 0
        m.step = arr.strides[0]
        m.data = arr.tobytes()
        return m

    cap, bad, warmup, last_pub, last_note, fire_was = None, 0, 0, 0.0, 0.0, False
    last_param = 0.0
    period = 1.0 / max(1.0, a.rate)
    while not rospy.is_shutdown():
        if cap is None:
            cap = open_camera(a.device)
            if cap is None:
                if time.time() - last_note > 10:
                    last_note = time.time()
                    rospy.logwarn("thermal: cannot open %s (not plugged in, or another program holds it) - retrying", a.device)
                time.sleep(1.0)
                continue
            rospy.loginfo("thermal: camera %s opened", a.device)
            bad, warmup = 0, 8                             # a few more frames after the garbage start-up ones
        ok, raw = cap.read()
        _, temp = decode_p2(raw) if ok and raw is not None else (None, None)
        if temp is None:
            bad += 1
            if bad > 250:                                  # ~10 s. The camera sends garbage for its first 2-4 s after
                                                           # every open, so reopening sooner would loop forever.
                size = None if raw is None else np.asarray(raw).shape
                rospy.logwarn("thermal: no valid raw temperature frames (frame %s) - reopening", size)
                cap.release()
                cap = None
                time.sleep(1.0)
            continue
        bad = 0
        if warmup > 0:
            warmup -= 1
            continue
        now = time.time()
        if now - last_pub < period * 0.7:               # 0.7: do not drop every second frame when rate = camera rate
            continue
        last_pub = now
        if now - last_param > 1.0:                      # the mission sets /thermal/fire_c (dashboard setting)
            last_param = now
            try:
                fc = float(rospy.get_param("/thermal/fire_c", a.fire_c))
                if fc != a.fire_c and 30.0 <= fc <= 1000.0:
                    rospy.loginfo("thermal: fire threshold %.0f C -> %.0f C", a.fire_c, fc)
                    a.fire_c = fc
            except (ValueError, TypeError, KeyError):
                pass
        stamp = rospy.Time.now()
        view, info = render_view(temp, a.fire_c)
        pub_temp.publish(image_msg(np.ascontiguousarray(temp, dtype=np.float32), "32FC1", stamp))
        pub_img.publish(image_msg(np.ascontiguousarray(view), "bgr8", stamp))
        pub_max.publish(Float32(info["max_c"]))
        pub_fire.publish(Bool(info["fire"]))
        if info["fire"] != fire_was:
            fire_was = info["fire"]
            rospy.loginfo("thermal: %s (max %.1f C, threshold %.0f C)", "FIRE in view" if fire_was else "fire gone", info["max_c"], a.fire_c)
    if cap is not None:
        cap.release()


if __name__ == "__main__":
    main()
