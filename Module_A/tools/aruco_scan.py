#!/usr/bin/env python3
"""TECHNIC 6S ArUco scan for MANUAL flight: you fly with the RC, this script only watches.

It NEVER arms, never takes off and never sends a flight command. It reads the camera, lists every ArUco
marker it sees (ID, how often, when, and where the drone was if the marker map gives a position) and
writes a CSV to ~/flight_logs/.

On the drone (TECHNIC web terminal or ssh orangepi@<drone-ip>):
    source /opt/ros/noetic/setup.bash; source ~/technic_ws/devel/setup.bash
    python3 aruco_scan.py                 # runs until Ctrl+C (or Stop in the dashboard), then prints the summary
    python3 aruco_scan.py --duration 120  # stop by itself after 120 s
Options:
    --source auto|topic|opencv   auto = the drone's own detector (aruco_detect/markers) if it is running,
                                 otherwise OpenCV on the camera image
    --image main_camera/image_raw   camera topic for --source opencv
    --dict DICT_4X4_1000            marker family for --source opencv
    --expect 0-99                   IDs you expect (e.g. the map): the summary lists the ones never seen
Laptop check without ROS:  python3 aruco_scan.py --selftest
"""
import argparse, csv, math, os, sys, time

NAN = float("nan")


# ----------------------------------------------------------------------------- pure helpers (testable)
def parse_ids(text):
    """'0-5,9,12-13' -> {0,1,2,3,4,5,9,12,13}"""
    out = set()
    for part in str(text or "").replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def fmt_ids(ids):
    """{0,1,2,5,7,8} -> '0-2 5 7-8'"""
    ids = sorted(ids)
    out, i = [], 0
    while i < len(ids):
        j = i
        while j + 1 < len(ids) and ids[j + 1] == ids[j] + 1:
            j += 1
        out.append(str(ids[i]) if i == j else "%d-%d" % (ids[i], ids[j]))
        i = j + 1
    return " ".join(out) if out else "-"


class Book(object):
    """What has been seen so far."""

    def __init__(self):
        self.seen = {}      # id -> dict(count, first, last, x, y, z)

    def add(self, mid, t, pos):
        """Returns True the first time this ID is seen."""
        m = self.seen.get(mid)
        new = m is None
        if new:
            m = self.seen[mid] = {"count": 0, "first": t, "last": t, "x": NAN, "y": NAN, "z": NAN}
        m["count"] += 1
        m["last"] = t
        if pos and all(math.isfinite(v) for v in pos) and not math.isfinite(m["x"]):
            m["x"], m["y"], m["z"] = pos      # where the drone was when it first saw the marker with a valid position
        return new

    def summary(self, t0, expect=None):
        lines = ["", "=" * 62, "ArUco scan summary: %d different markers" % len(self.seen), "=" * 62,
                 "  ID   times seen   first seen   last seen   drone position at first sight"]
        for mid in sorted(self.seen):
            m = self.seen[mid]
            pos = "(%.2f, %.2f, %.2f)" % (m["x"], m["y"], m["z"]) if math.isfinite(m["x"]) else "no map position"
            lines.append("  %-4d %-12d %6.1f s     %6.1f s    %s" % (mid, m["count"], m["first"] - t0, m["last"] - t0, pos))
        lines.append("IDs seen: " + fmt_ids(self.seen))
        if expect:
            missing = set(expect) - set(self.seen)
            extra = set(self.seen) - set(expect)
            lines.append("Expected %d, seen %d of them. NOT seen: %s" % (len(expect), len(expect) - len(missing), fmt_ids(missing)))
            if extra:
                lines.append("Seen but not expected: " + fmt_ids(extra))
        return "\n".join(lines)


def make_cv_detector(dict_name):
    import cv2
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name))
    if hasattr(cv2.aruco, "ArucoDetector"):                       # OpenCV >= 4.7
        det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())
        detect = det.detectMarkers
    else:                                                          # OpenCV 4.2 on the Orange Pi
        p = cv2.aruco.DetectorParameters_create()
        detect = lambda g: cv2.aruco.detectMarkers(g, d, parameters=p)

    def run(img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        corners, ids, _ = detect(gray)
        if ids is None:
            return []
        return [(int(i), float(c[0][:, 0].mean()), float(c[0][:, 1].mean())) for c, i in zip(corners, ids.flatten())]
    return run


def selftest():
    import cv2, numpy as np
    assert parse_ids("0-3, 7,9-10") == {0, 1, 2, 3, 7, 9, 10}
    assert fmt_ids({0, 1, 2, 5, 7, 8}) == "0-2 5 7-8" and fmt_ids([]) == "-"
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
    gen = cv2.aruco.generateImageMarker if hasattr(cv2.aruco, "generateImageMarker") else cv2.aruco.drawMarker
    img = np.full((480, 640), 255, np.uint8)
    for k, mid in enumerate((3, 42, 117)):
        img[170:290, 40 + 200 * k:160 + 200 * k] = gen(d, mid, 120)
    found = make_cv_detector("DICT_4X4_1000")(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    assert sorted(f[0] for f in found) == [3, 42, 117], found
    b = Book()
    assert b.add(3, 10.0, (1.0, 2.0, 1.5)) and not b.add(3, 11.0, (5.0, 5.0, 5.0)) and b.add(42, 12.0, None)
    assert b.seen[3]["count"] == 2 and b.seen[3]["x"] == 1.0
    s = b.summary(10.0, expect={3, 42, 50})
    assert "NOT seen: 50" in s and "IDs seen: 3 42" in s, s
    print(s)
    print("SELFTEST OK")


# ----------------------------------------------------------------------------- ROS part
def main():
    ap = argparse.ArgumentParser(description="Passive ArUco scan for manual flight (never arms).")
    ap.add_argument("--source", choices=["auto", "topic", "opencv"], default="auto")
    ap.add_argument("--markers-topic", default="aruco_detect/markers")
    ap.add_argument("--image", default="main_camera/image_raw")
    ap.add_argument("--dict", default="DICT_4X4_1000")
    ap.add_argument("--frame", default="aruco_map", help="frame for the drone position")
    ap.add_argument("--expect", default="", help="IDs you expect, e.g. 0-99")
    ap.add_argument("--duration", type=float, default=0, help="stop after this many seconds (0 = until Ctrl+C)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--yes", action="store_true", help=argparse.SUPPRESS)        # accepted for the dashboard, not needed
    ap.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    import rospy
    rospy.init_node("aruco_scan", anonymous=True)
    book, state = Book(), {"now": set(), "frames": 0, "pos": None, "pos_t": 0.0}
    t0 = time.time()
    log_dir = os.path.expanduser("~/flight_logs")
    os.makedirs(log_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    ev_path = os.path.join(log_dir, "aruco_scan_%s.csv" % stamp)
    ev_f = open(ev_path, "w", newline="")
    ev = csv.writer(ev_f)
    ev.writerow(["time", "t_s", "id", "source", "drone_x", "drone_y", "drone_z", "u_or_rel_x", "v_or_rel_y", "rel_z"])
    last_row = {}

    def record(mid, source, a_, b_, c_):
        now = time.time()
        pos = state["pos"] if now - state["pos_t"] < 1.0 else None
        if book.add(mid, now, pos):
            where = " | drone at (%.2f, %.2f, %.2f)" % pos if pos else ""
            print("[new] marker %d  (t = %.1f s, %d so far)%s" % (mid, now - t0, len(book.seen), where))
            sys.stdout.flush()
        state["now"].add(mid)
        if now - last_row.get(mid, 0) >= 0.5:               # at most 2 rows per marker per second
            last_row[mid] = now
            p = pos or (NAN, NAN, NAN)
            ev.writerow([time.strftime("%H:%M:%S", time.localtime(now)), "%.2f" % (now - t0), mid, source,
                         "%.3f" % p[0], "%.3f" % p[1], "%.3f" % p[2], "%.3f" % a_, "%.3f" % b_, "%.3f" % c_])

    # --- source: the drone's own detector, or OpenCV on the camera image
    source = a.source
    if source in ("auto", "topic"):
        import rostopic
        cls = None
        t_end = time.time() + (6.0 if source == "topic" else 2.5)
        while cls is None and time.time() < t_end and not rospy.is_shutdown():
            cls = rostopic.get_topic_class(rospy.resolve_name(a.markers_topic), blocking=False)[0]
            if cls is None:
                time.sleep(0.3)
        if cls is not None:
            def on_markers(msg):
                state["frames"] += 1
                for m in getattr(msg, "markers", []):
                    p = m.pose.position
                    record(int(m.id), "topic", p.x, p.y, p.z)
            rospy.Subscriber(a.markers_topic, cls, on_markers, queue_size=5)
            source = "topic"
            print("[scan] using the drone's detector: %s" % a.markers_topic)
        elif source == "topic":
            print("[scan] ERROR: nothing is published on %s. Is ArUco enabled on the drone? Try --source opencv" % a.markers_topic)
            return 2
        else:
            source = "opencv"
    if source == "opencv":
        from sensor_msgs.msg import Image
        import numpy as np
        detect = make_cv_detector(a.dict)

        def to_image(msg):                      # no cv_bridge: it does not import on the TECHNIC image
            ch = 1 if msg.encoding.lower() in ("mono8", "8uc1") else (4 if msg.encoding.lower() in ("bgra8", "rgba8") else 3)
            arr = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)[:, :msg.width * ch]
            arr = arr.reshape(msg.height, msg.width, ch) if ch > 1 else arr.reshape(msg.height, msg.width)
            return arr[:, :, 0] if ch > 1 else arr       # one channel is enough to find black/white markers

        def on_image(msg):
            state["frames"] += 1
            for mid, u, v in detect(to_image(msg)):
                record(mid, "opencv", u, v, NAN)
        rospy.Subscriber(a.image, Image, on_image, queue_size=1, buff_size=2 ** 24)
        print("[scan] using OpenCV (%s) on camera topic %s" % (a.dict, a.image))

    # --- optional: drone position in the marker map (read only)
    telemetry = None
    try:
        from technic import srv
        telemetry = rospy.ServiceProxy("get_telemetry", srv.GetTelemetry)
        rospy.wait_for_service("get_telemetry", timeout=3)
    except Exception as e:
        telemetry = None
        print("[scan] no position (get_telemetry not available: %s) - IDs only" % e)

    expect = parse_ids(a.expect)
    print("[scan] PASSIVE: this script never arms and never moves the drone. Fly with the RC. Ctrl+C / Stop = finish.")
    sys.stdout.flush()
    last_print, warned = 0.0, False
    try:
        while not rospy.is_shutdown():
            now = time.time()
            if a.duration and now - t0 >= a.duration:
                break
            if telemetry is not None:
                try:
                    tm = telemetry(frame_id=a.frame)
                    ok = all(math.isfinite(v) for v in (tm.x, tm.y, tm.z))
                    state["pos"], state["pos_t"] = ((tm.x, tm.y, tm.z), now) if ok else (None, 0.0)
                except Exception:
                    state["pos"] = None
            if now - last_print >= 1.0:
                last_print = now
                visible, state["now"] = state["now"], set()
                pos = "pos (%.2f, %.2f, %.2f)" % state["pos"] if state["pos"] else "pos -"
                print("[%5.0f s] total %-3d | in view now: %-24s | %s" % (now - t0, len(book.seen), fmt_ids(visible), pos))
                sys.stdout.flush()
                ev_f.flush()
                if state["frames"] == 0 and now - t0 > 5 and not warned:
                    warned = True
                    print("[scan] WARNING: no camera data yet on %s" % (a.markers_topic if source == "topic" else a.image))
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        ev_f.close()
        sum_path = os.path.join(log_dir, "aruco_scan_%s_summary.csv" % stamp)
        with open(sum_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "times_seen", "first_seen_s", "last_seen_s", "drone_x", "drone_y", "drone_z"])
            for mid in sorted(book.seen):
                m = book.seen[mid]
                w.writerow([mid, m["count"], "%.1f" % (m["first"] - t0), "%.1f" % (m["last"] - t0),
                            "%.3f" % m["x"], "%.3f" % m["y"], "%.3f" % m["z"]])
        print(book.summary(t0, expect))
        print("log: %s\nsummary: %s" % (ev_path, sum_path))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
