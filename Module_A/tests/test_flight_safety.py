#!/usr/bin/env python3
"""
Flight-safety unit tests (no drone, no ROS, no pytest needed):   python tests/test_flight_safety.py
Covers: geofence + altitude limit, takeoff/arming failures, operator commands, START only on a real Enter,
survey coverage,
triangulation ghosts.
"""
import io
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="brics_unit_")
os.environ["BRICS_RUNS"] = TMP                      # mission run folders go to a temp dir

import yaml  # noqa: E402

from common.geometry import RayTracker, lawnmower  # noqa: E402
from drone import mission_base as MB  # noqa: E402
from drone.technic_api import DroneBase, MissionAbort, MockDrone, ReturnHome, Telemetry  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def load(name):
    with open(os.path.join(ROOT, "config", name)) as f:
        cfg = yaml.safe_load(f)
    cfg["ui"] = {"enabled": False}
    return cfg


class Quiet(MB.Mission):
    """Mission with a scripted plan, quiet log."""
    name = "unit"

    def __init__(self, cfg, plan_fn=None, **kw):
        self.plan_fn = plan_fn
        self.lines = []
        MB.Mission.__init__(self, cfg, mock=True, time_scale=200.0, **kw)

    def log(self, msg):
        self.lines.append(msg)

    def plan(self):
        if self.plan_fn:
            self.plan_fn(self)


def simple_cfg(**kw):
    cfg = {"case": "unit", "area": [0, 0, 2, 2], "home": [0, 0], "altitude": 1.0, "takeoff_z": 1.0,
           "cameras": {"rgb": {"type": "ros"}}, "detectors": [], "ui": {"enabled": False},
           "safety": {"min_cell_voltage": 3.5, "max_time": 540, "frame": "aruco_map"}}
    cfg.update(kw)
    return cfg


# ----------------------------------------------------------------------------- geometry
@test
def lawnmower_covers_both_edges():
    for (y0, y1, step) in ((0, 4, 0.84), (0, 3, 0.75), (1, 1.2, 0.5), (0, 10, 3.0)):
        ys = sorted(set(round(p[1], 6) for p in lawnmower(0, y0, 2, y1, step, 1.0)))
        assert abs(ys[0] - y0) < 1e-9 and abs(ys[-1] - y1) < 1e-9, ys
        assert all(b - a <= step + 1e-9 for a, b in zip(ys, ys[1:])), ys


@test
def ray_tracker_never_confirms_untriangulated_ghost():
    t = RayTracker(radius=0.3, min_hits=3, default_range=1.0)
    for k in range(6):                          # 6 almost identical rays: no depth information
        _, newly = t.add_ray("x", (0, 0.001 * k, 1), (1, 0, 0))
        assert not newly
    assert t.confirmed() == []
    t2 = RayTracker(radius=0.3, min_hits=3)
    target = (2.0, 0.0, 1.0)
    confirmed = 0
    for k in range(6):                          # views from different positions -> triangulated
        o = (0.0, -1.0 + 0.4 * k, 1.0)
        d = [target[i] - o[i] for i in range(3)]
        obj, newly = t2.add_ray("x", o, d, range_hint=2.0)
        confirmed += newly
    c = t2.confirmed()
    assert confirmed == 1 and len(c) == 1 and c[0]["id"] == 1, c
    assert math.dist((c[0]["x"], c[0]["y"], c[0]["z"]), target) < 0.05


# ----------------------------------------------------------------------------- geofence


@test
def waypoint_outside_fence_is_skipped():
    m = Quiet(simple_cfg())
    m.drone.armed = True
    assert m.fly(10.0, 0.5, 1.0) is False                      # far outside: refused, drone did not move
    assert m.drone.target[0] < 1.0
    assert m.fly(1.0, 1.0, 5.0) is False                       # above max_altitude (3 m)
    assert any("SKIPPED" in line for line in m.lines)


@test
def leaving_the_fence_lands():
    d = MockDrone(fence=(0, 0, 2, 2), max_alt=2.5, log=lambda s: None)
    d.armed = True
    d.pos = [2.5, 1.0, 1.0]
    assert "geofence" in (d.safety_problem() or "")
    d.pos = [1.0, 1.0, 2.8]
    assert "altitude" in (d.safety_problem() or "")
    d.pos = [1.0, 1.0, 1.0]
    assert d.safety_problem() is None


@test
def drift_out_of_fence_during_mission_aborts_and_lands():
    def plan(m):
        m.drone.pos[0] = 5.0                                   # wind / bad pose estimate pushes it out
        m.fly(1.0, 1.0)
    m = Quiet(simple_cfg(), plan)
    m.autostart = True
    m.run()
    s = json.load(open(os.path.join(m.run_dir, "summary.json")))
    assert s["result"].startswith("ABORT") and "geofence" in s["result"], s
    assert not m.drone.armed


# ----------------------------------------------------------------------------- takeoff / arming
class RefusingDrone(MockDrone):
    class R(object):
        success, message = False, "Arming denied"

    def go(self, **kw):
        if kw.get("auto_arm"):
            return self.R()
        return MockDrone.go(self, **kw)


class NeverArms(MockDrone):
    def go(self, **kw):
        kw["auto_arm"] = False                                 # FCU silently does not arm
        return MockDrone.go(self, **kw)


@test
def takeoff_refused_aborts():
    for cls in (RefusingDrone, NeverArms):
        d = cls(time_scale=500, log=lambda s: None)
        try:
            d.takeoff(1.0, timeout=2.0)
            raise AssertionError("%s: takeoff did not abort" % cls.__name__)
        except MissionAbort as e:
            assert "arm" in str(e).lower(), e


@test
def operator_abort_during_takeoff():
    d = MockDrone(time_scale=500, log=lambda s: None)
    DroneBase.abort_flag = False

    def during():
        DroneBase.abort_flag = True
    try:
        d.takeoff(1.0, during=during)
        raise AssertionError("abort ignored during takeoff")
    except MissionAbort:
        pass
    finally:
        DroneBase.abort_flag = False


@test
def preflight_refuses_when_already_armed():
    m = Quiet(simple_cfg())
    m.mock = False                       # the armed check is for the real drone
    m.drone.armed = True
    assert m.preflight() is False
    assert any("already armed" in line for line in m.lines)


# ----------------------------------------------------------------------------- start / operator commands
@test
def stdin_eof_does_not_start_the_mission():
    m = Quiet(simple_cfg())
    old = sys.stdin
    sys.stdin = io.StringIO("")                                # no terminal (nohup / service): EOF at once
    res = {}
    try:
        th = threading.Thread(target=lambda: res.setdefault("r", m.wait_start()), daemon=True)
        th.start()
        th.join(1.0)
        assert th.is_alive(), "mission started by itself on stdin EOF"
        with m.state["_lock"]:
            m.state["command"] = "abort"
        th.join(2.0)
        assert res.get("r") is False
    finally:
        sys.stdin = old


@test
def abort_before_start_never_takes_off():
    m = Quiet(simple_cfg())
    with m.state["_lock"]:
        m.state["command"] = "abort"
    m.run()
    assert m.drone.path == [] and not m.drone.armed
    assert json.load(open(os.path.join(m.run_dir, "summary.json")))["result"].startswith("ABORT")


@test
def return_command_flies_home_then_lands():
    def plan(m):
        m.fly(1.8, 1.8)
        with m.state["_lock"]:
            m.state["command"] = "return"
        m.fly(0.2, 1.8)
        raise AssertionError("RETURN ignored")
    m = Quiet(simple_cfg(), plan)
    m.autostart = True
    m.run()
    s = json.load(open(os.path.join(m.run_dir, "summary.json")))
    assert s["result"].startswith("RETURN"), s
    assert math.hypot(m.drone.pos[0], m.drone.pos[1]) < 0.25 and not m.drone.armed


@test
def inspection_moves_are_vertical_and_horizontal_only():
    targets = []

    class Rec(Quiet):
        def fly(self, x, y, z=None, *a, **k):
            targets.append((x, y, self.alt if z is None else z))
            return True

        def hover(self, s):
            pass
    m = Rec(simple_cfg(inspect={"enabled": True, "z": 0.6, "hover": 1}))
    m.drone.pos = [0.5, 0.5, 1.4]
    m.on_object({"id": 1, "name": "fire", "x": 1.5, "y": 1.2, "z": 0})
    pts = [(0.5, 0.5, 1.4)] + targets
    for a, b in zip(pts, pts[1:]):
        horizontal = abs(a[2] - b[2]) < 1e-9
        vertical = math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-9
        assert horizontal or vertical, (a, b)
    assert min(p[2] for p in targets) == 0.6


# ----------------------------------------------------------------------------- case 4: never cross the wires


# ----------------------------------------------------------------------------- swarm


@test
def ui_status_json_is_finite():
    from common.ui_server import _finite
    s = json.dumps(_finite({"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": 2.0}}), allow_nan=False)
    assert s == '{"a": null, "b": [1.0, null], "c": {"d": 2.0}}', s


# ----------------------------------------------------------------------------- studio


# ----------------------------------------------------------------------------- Cube parameters


@test
def one_fire_is_mapped_once():
    """A heat source seen from a moving drone with a badly calibrated camera gives positions smeared over ~1 m.
    It must stay ONE map entry (the 10 Nov flight mapped the same heater again and again), located near the
    views where it was in the middle of the picture; a second source metres away stays separate."""
    import random
    from common.geometry import ObjectTracker
    rng = random.Random(3)
    tr = ObjectTracker(radius=1.2, min_hits=4)
    true_fire, true_flame = (-2.0, 0.5), (2.2, -0.4)
    new = 0
    for line_y in (-1.0, -0.33, 0.33, 1.0):                         # four survey lines over the field
        for k in range(51):
            dx, dy = -2.5 + 0.1 * k, line_y
            for name, (tx, ty) in (("fire", true_fire), ("flame", true_flame)):
                off = math.hypot(tx - dx, ty - dy)
                if off > 0.9:                                        # not in the picture
                    continue
                # projection error grows with the distance from the picture centre (wrong field of view / tilt)
                ex, ey = (tx - dx) * 0.6 + rng.gauss(0, 0.05), (ty - dy) * 0.6 + rng.gauss(0, 0.05)
                _, newly = tr.add(name, tx + ex, ty + ey, 0.0, 0.9, t=k, weight=math.exp(-(off / 0.9 / 0.6) ** 2))
                new += int(newly)
    conf = tr.confirmed()
    assert new == 2 and len(conf) == 2 and len(tr.objects) == 2, (new, [(o["name"], o["x"], o["y"], o["hits"]) for o in tr.objects])
    for o in conf:
        tx, ty = true_fire if o["name"] == "fire" else true_flame
        assert math.hypot(o["x"] - tx, o["y"] - ty) < 0.35, (o["name"], o["x"], o["y"])
    assert sorted(o["id"] for o in conf) == [1, 2]
    # two same-class sources 3 m apart are still two objects
    t2 = ObjectTracker(radius=1.2, min_hits=2)
    for _ in range(3):
        t2.add("fire", 0.0, 0.0)
        t2.add("fire", 3.0, 0.0)
    assert len(t2.confirmed()) == 2
    # a source that is hot AND looks like a flame: camera model and thermal camera give ONE entry, named fire
    t3 = ObjectTracker(radius=1.2, min_hits=2, same_object=["fire", "flame"])
    for _ in range(3):
        t3.add("flame", 1.0, 1.0, conf=0.7)
    _, newly = t3.add("fire", 1.1, 0.9, conf=0.9, extra={"temp_c": 180.0})
    assert not newly and len(t3.objects) == 1 and t3.objects[0]["name"] == "fire" and t3.objects[0]["temp_c"] == 180.0
    t3.add("flame", -2.0, 0.0); t3.add("flame", -2.0, 0.0)
    assert sorted(o["name"] for o in t3.confirmed()) == ["fire", "flame"] and t3.counts() == {"fire": 1, "flame": 1}


@test
def one_click_run_counts_down_and_abort_cancels():
    """Final mission: one click = fly. On the real drone a countdown runs first and ABORT cancels before arming."""
    cfg = load("case1_fire.yaml")
    cfg["ui"] = {"enabled": False, "start_countdown": 1}
    m = mission(MB.Mission, cfg) if "mission" in globals() else None
    if m is None:
        from drone.case1_fire import FireMission
        m = FireMission(cfg, mock=True, autostart=True, time_scale=50)
    m.mock, m.autostart = False, True                 # take the real-drone path of wait_start only
    t0 = time.time()
    assert m.wait_start() is True and 0.9 < time.time() - t0 < 2.5
    assert m.state["phase"] == "STARTING"
    cfg["ui"]["start_countdown"] = 3
    threading.Timer(0.4, lambda: m.state.__setitem__("command", "abort")).start()
    t0 = time.time()
    assert m.wait_start() is False and time.time() - t0 < 1.5      # cancelled long before the 3 s are over
    m.mock = True


@test
def dashboard_settings_overrides_and_refusals():
    """--set from the dashboard: values land in the config, unsafe ones are refused before anything flies."""
    import yaml
    from common import mission_settings as ms
    base = os.path.join(ROOT, "config", "case1_fire.yaml")
    cfg = yaml.safe_load(open(base))
    assert ms.check_settings(cfg) == []
    ms.apply_overrides(cfg, ["area=[-2,-1,2,1]", "safety.fence=[-3,-1.5,3,1.5]", "altitude=1.2", "step=0.6",
                             "fire_c=120", "home=[0.5,0]"])
    assert cfg["area"] == [-2, -1, 2, 1] and cfg["safety"]["fence"] == [-3, -1.5, 3, 1.5]
    assert cfg["altitude"] == 1.2 and cfg["step"] == 0.6 and ms.fire_threshold(cfg) == 120.0
    assert ms.check_settings(cfg) == []
    ms.apply_overrides(cfg, ["step=auto"])
    assert "step" not in cfg
    for bad in (["area=[-4,-1,2,1]"], ["area=[2,-1,-2,1]"], ["home=[5,0]"], ["altitude=2.9"], ["altitude=0.1"],
                ["fire_c=10"], ["step=0.05"], ["speed=3"], ["safety.fence=[-3,-1.5,3]"]):
        c = yaml.safe_load(open(base))
        ms.apply_overrides(c, bad)
        assert ms.check_settings(c), "not refused: %s" % bad
    try:
        ms.apply_overrides(yaml.safe_load(open(base)), ["altitude"])
        raise AssertionError("KEY without =VALUE accepted")
    except ValueError:
        pass
    # a fence wider than the marker field is still refused by preflight (no position beyond the markers)
    from drone.mission_base import outside_marker_field
    assert outside_marker_field((-4.0, -1.5, 3.0, 1.5), (-3.0, -1.5, 3.0, 1.5))


def main():
    failed = 0
    for fn in TESTS:
        DroneBase.abort_flag = False
        t0 = time.time()
        try:
            fn()
            print("  ok    %-55s %.1fs" % (fn.__name__, time.time() - t0))
        except Exception:
            failed += 1
            print("  FAIL  %s" % fn.__name__)
            traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    if failed:
        print("%d of %d TESTS FAILED" % (failed, len(TESTS)))
        return 1
    print("ALL %d TESTS PASSED" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
