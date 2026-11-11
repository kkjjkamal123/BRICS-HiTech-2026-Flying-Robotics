"""
Mission engine shared by all cases.

  class MyMission(Mission):
      def plan(self):                 # the flight itself, after takeoff
          for wp in self.survey_waypoints():
              self.fly(*wp)

  MyMission.main()                    # parses --config, --mock, --autostart

What it gives you:
  * state machine phases shown in the UI: WAITING -> PREFLIGHT -> TAKEOFF -> MISSION -> RETURN -> LAND -> REPORT
  * background perception thread: camera(s) -> detector(s) -> map coordinates -> ObjectTracker
  * confirmed objects -> on_object() hook (default: LED flash + optional inspection hover + snapshot)
  * safety: operator ABORT/LAND, low battery, lost markers, mission time limit, geofence / altitude limit
    -> immediate landing; operator RETURN -> fly home, then land
  * logs + saved frames (training data!) in runs/<case>_<time>/ and an HTML+CSV report at the end
Python 3.8 compatible.
"""
import argparse
import csv
import json
import math
import os
import sys
import threading
import time

import cv2
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)

from common.detector import build_detector, draw            # noqa: E402
from common.geometry import ObjectTracker, RayTracker, footprint, lawnmower  # noqa: E402
from common.report import write_report                       # noqa: E402
from common import mission_settings                          # noqa: E402
from common.ui_server import UIServer                        # noqa: E402
from drone.camera import CvCamera, MockCamera, RosCamera, RosThermalCamera      # noqa: E402
from drone.technic_api import DroneBase, MissionAbort, ReturnHome, make_drone  # noqa: E402

NAN = float("nan")


def default_fence(cfg):
    """
    Geofence (x0, y0, x1, y1) in the safety frame. Explicit `safety.fence: [x0, y0, x1, y1]` wins,
    `safety.fence: false` disables it. Otherwise it is the bounding box of everything the mission is meant
    to visit (area, home, swarm homes, supports / targets incl. orbit radius, waypoints) plus
    `safety.fence_margin` (default 1.0 m).
    """
    s = cfg.get("safety") or {}
    f = s.get("fence")
    if f is False or (isinstance(f, str) and f.lower() in ("off", "none", "false")):
        return None
    if f:
        f = [float(v) for v in f]
        if len(f) != 4 or f[0] >= f[2] or f[1] >= f[3]:
            raise ValueError("safety.fence must be [x0, y0, x1, y1] with x0 < x1 and y0 < y1")
        return tuple(f)
    pts, extra = [], 0.0
    a = cfg.get("area")
    if a:
        pts += [(a[0], a[1]), (a[2], a[3])]
    for key in ("home",):
        if cfg.get(key):
            pts.append(tuple(cfg[key][:2]))
    pts += [tuple(h[:2]) for h in (cfg.get("swarm") or {}).get("homes") or []]
    pts += [tuple(w[:2]) for w in cfg.get("waypoints") or []]
    struct = [tuple(t[:2]) for t in (cfg.get("supports") or []) + (cfg.get("targets") or [])]
    if struct:
        pts += struct
        extra = max(float((cfg.get("orbit") or {}).get("radius", 1.2)), float((cfg.get("span") or {}).get("offset", 1.0)))
    if not pts:
        return None
    m = float(s.get("fence_margin", 1.0))
    xs, ys = [float(p[0]) for p in pts], [float(p[1]) for p in pts]
    return (min(xs) - m - extra, min(ys) - m - extra, max(xs) + m + extra, max(ys) + m + extra)


def marker_field(path):
    """(x0, y0, x1, y1) of the floor marker centres in an ArUco map file (id length x y z ...), or None."""
    xs, ys = [], []
    try:
        with open(path) as f:
            for line in f:
                p = line.split("#")[0].split()
                if len(p) >= 5:
                    try:
                        if abs(float(p[4])) < 0.3:
                            xs.append(float(p[2]))
                            ys.append(float(p[3]))
                    except ValueError:
                        pass
    except (IOError, OSError, TypeError):
        return None
    return (min(xs), min(ys), max(xs), max(ys)) if len(xs) >= 2 else None


def outside_marker_field(fence, field, tol=0.3):
    """Text describing how far the geofence sticks out of the marker field, or None if it is inside (+tol)."""
    if field is None:
        return None
    if fence is None:
        return "there is no geofence, but the marker field is only x %.2f..%.2f  y %.2f..%.2f m" % (field[0], field[2], field[1], field[3])
    over = max(field[0] - fence[0], field[1] - fence[1], fence[2] - field[2], fence[3] - field[3])
    if over > tol:
        return ("the mission area / geofence (x %.2f..%.2f  y %.2f..%.2f) reaches %.2f m outside the marker field "
                "(x %.2f..%.2f  y %.2f..%.2f): beyond the markers the drone has no position"
                % (fence[0], fence[2], fence[1], fence[3], over, field[0], field[2], field[1], field[3]))
    return None


class Mission(object):
    name = "mission"

    def __init__(self, cfg, mock=False, autostart=False, time_scale=10.0):
        self.cfg = cfg
        self.mock = mock
        self.autostart = autostart or cfg.get("autostart", False)
        self.name = cfg.get("case", self.name)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = os.environ.get("BRICS_RUNS") or os.path.join(ROOT, "runs")
        self.run_dir = os.path.join(base, "%s_%s%s" % (self.name, stamp, "_mock" if mock else ""))
        k = 2
        while os.path.exists(self.run_dir):            # two runs started in the same second
            self.run_dir = os.path.join(base, "%s_%s_%d%s" % (self.name, stamp, k, "_mock" if mock else ""))
            k += 1
        os.makedirs(os.path.join(self.run_dir, "snapshots"))
        self.state = {"_lock": threading.Lock(), "phase": "INIT", "status": "", "log": [], "detections": [],
                      "counts": {}, "command": None, "report": None,
                      "area": cfg.get("area"), "home": cfg.get("home", [0.0, 0.0]), "xy": None, "track": []}
        # the operator-adjustable settings this run really uses (dashboard shows them next to its own)
        self.state["settings"] = {"altitude": cfg.get("altitude"), "step": cfg.get("step"),
                                  "overlap": cfg.get("overlap", 0.3), "speed": cfg.get("speed"),
                                  "fire_c": mission_settings.fire_threshold(cfg)}
        self.state["markers"] = self._marker_points(mock)   # marker centres, drawn on the dashboard map
        self._log_file = open(os.path.join(self.run_dir, "log.txt"), "a")
        # every single detection (not only confirmed objects): time, camera, class, confidence, map position
        self._events_f = open(os.path.join(self.run_dir, "events.csv"), "w", newline="")
        self._events = csv.writer(self._events_f)
        self._events.writerow(["time", "t_unix", "camera", "class", "conf", "x", "y", "z", "object_id", "confirmed_now",
                               "u", "v", "drone_x", "drone_y", "drone_z", "drone_yaw", "temp_c"])
        # one row per perception cycle -> processing frame rate per camera (Case 1: >= 10 FPS for > 90 % of the time)
        self._perf_f = open(os.path.join(self.run_dir, "perf.csv"), "w", newline="")
        self._perf = csv.writer(self._perf_f)
        self._perf.writerow(["t_unix", "cameras", "detect_ms", "cycle_ms", "n_dets"])
        self._perf_rows = []                 # (t, cameras) kept in memory for the FPS summary
        self._t_air = [None, None]           # wall-clock takeoff / landing time

        s = cfg.get("safety") or {}
        self.fence = default_fence(cfg)
        self.state["fence"] = list(self.fence) if self.fence else None
        dkw = dict(min_cell_voltage=s.get("min_cell_voltage", 3.5), check_frame=s.get("frame", "aruco_map"),
                   log=self.log, fence=self.fence, max_alt=s.get("max_altitude", 3.0),
                   battery_cells=s.get("battery_cells"))
        if mock:
            dkw["time_scale"] = time_scale
        self.drone = make_drone(mock=mock, **dkw)
        self.max_time = s.get("max_time", 540)
        self.alt = cfg.get("altitude", 1.5)
        self.speed = cfg.get("speed", 0.4)
        self.frame_id = cfg.get("frame_id", "aruco_map")
        self._returning = False
        self._airborne = False
        if self.fence:
            self.log("[safety] geofence x %.2f..%.2f  y %.2f..%.2f m, max altitude %s m (%s)" % (
                self.fence[0], self.fence[2], self.fence[1], self.fence[3], s.get("max_altitude", 3.0),
                "from config" if s.get("fence") else "auto: mission area + %.1f m" % float(s.get("fence_margin", 1.0))))
        else:
            self.log("[safety] WARNING: no geofence (safety.fence disabled and nothing to derive it from)")

        self.log("[settings] " + mission_settings.summary(cfg))
        self.fire_c = mission_settings.fire_threshold(cfg)
        if not mock and self.fire_c is not None:
            # the thermal node on the drone draws its FIRE boxes (dashboard thermal pane) at this temperature too
            try:
                import rospy
                rospy.set_param("/thermal/fire_c", float(self.fire_c))
            except Exception as e:
                self.log("[settings] could not pass fire_c to the thermal node: %s" % e)
        self.cameras = self._make_cameras(cfg.get("cameras", {"rgb": {"type": "ros"}}))
        self.detector = build_detector(cfg.get("detectors", []), base_dir=ROOT)
        t = cfg.get("tracker", {})
        if t.get("mode", "ground") == "rays":      # 3D triangulation (forward / oblique cameras)
            self.tracker = RayTracker(radius=t.get("radius", 0.3), min_hits=t.get("min_hits", 3),
                                      default_range=t.get("default_range", 1.0),
                                      require_triangulation=t.get("require_triangulation", True))
        else:                                      # objects on the floor (downward camera)
            self.tracker = ObjectTracker(radius=t.get("radius", 0.4), min_hits=t.get("min_hits", 3),
                                         same_object=t.get("same_object"))
        self.ignore = set(cfg.get("ignore_classes", []))
        self.alias = cfg.get("class_alias", {}) or {}          # e.g. {flame: fire, hotspot: fire}: one object, one name
        self.new_objects = []
        self._perc_run = False
        self.min_detect_alt = float(cfg.get("min_detect_altitude", 0.0) or 0.0)
        self.self_cal = bool(cfg.get("self_calibrate", False))
        self._selfcal_n = {}
        self._ui_dets = (None, [], 0.0)      # (camera key, detections, time) drawn on the live view
        self._live_preview = False
        self._perc_count = 0
        self._last_sync = -1e9
        self._frame_dt = float((cfg.get("mock") or {}).get("frame_dt", 0.4))
        self._t_start = None
        self._frames_csv = None
        self.save_every = cfg.get("save_frames_every", 0)      # seconds; >0 = collect training images
        self._last_save = 0
        self.ui = None
        if cfg.get("ui", {}).get("enabled", True):
            self.state["_web_page"] = bool(cfg.get("ui", {}).get("web_page", True))
            self.ui = UIServer(self.state, port=cfg.get("ui", {}).get("port", 8090),
                               title=cfg.get("title", "UAV Mission")).start()

    # ------------------------------------------------------------------ setup helpers
    def _make_cameras(self, cams):
        out = {}
        for key, c in cams.items():
            c = dict(c)
            typ = c.pop("type", "ros")
            if self.mock:
                if typ == "ros_thermal":
                    c.setdefault("thermal", "auto")           # simulated thermal camera gives deg C too
                out[key] = MockCamera(self.drone, scene=self.cfg.get("mock", {}).get("scene", []),
                                      **dict({k: v for k, v in c.items() if k in ("width", "height", "image_up_is_forward", "orientation", "thermal", "hfov_deg")},
                                           **((self.cfg.get("mock") or {}).get("camera_error") or {}).get(key, {})))
            elif typ == "ros":
                out[key] = RosCamera(self.drone, **c)
            elif typ == "ros_thermal":
                out[key] = RosThermalCamera(self.drone, **c)
            elif typ == "cv":
                out[key] = CvCamera(self.drone, **c)
            else:
                raise ValueError("camera type %s" % typ)
        return out

    def _marker_points(self, mock):
        """[[x, y], ...] of the floor markers: from the map loaded on the drone, or the venue map in config/ (mock)."""
        path = None
        if not mock:
            try:
                import rospy
                path = rospy.get_param("/aruco_map/map", None)
            except Exception:
                path = None
        if not path:
            path = os.path.join(ROOT, "config", str((self.cfg.get("mock") or {}).get("marker_map", "aruco_map_750x450_id100.txt")))
        pts = []
        try:
            with open(path) as f:
                for line in f:
                    p = line.split("#")[0].split()
                    if len(p) >= 5 and abs(float(p[4])) < 0.3:
                        pts.append([round(float(p[2]), 3), round(float(p[3]), 3)])
        except (IOError, OSError, ValueError, TypeError):
            return []
        return pts[:400]

    def log(self, msg):
        line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
        print(line)
        sys.stdout.flush()
        with self.state["_lock"]:
            self.state["log"].append(line)
            if len(self.state["log"]) > 500:
                del self.state["log"][:100]
        try:
            self._log_file.write(line + "\n")
            self._log_file.flush()
        except Exception:
            pass

    def phase(self, p, status=""):
        with self.state["_lock"]:
            self.state["phase"], self.state["status"] = p, status
        self.log("[phase] %s %s" % (p, status))

    # ------------------------------------------------------------------ perception
    def perceive_once(self):
        t_cycle = time.time()
        frames = {}
        for key, cam in self.cameras.items():
            f = cam.get()
            if f is not None:
                frames[key] = f
        if not frames:
            return []
        images = {k: f["img"] for k, f in frames.items()}
        for k, f in frames.items():
            if f.get("temp") is not None:
                images[k + "_temp"] = f["temp"]          # deg C map for 'thermal' detectors with mode: celsius
        t_det = time.time()
        dets = self.detector(images)
        now = time.time()
        detect_ms = (now - t_det) * 1000.0
        found = []
        for d in dets:
            d["name"] = self.alias.get(d["name"], d["name"])
            if d["name"] in self.ignore:
                continue
            key = d.get("image", "rgb")
            if key.endswith("_temp"):
                key = key[:-5]
            d["image"] = key
            if key not in frames:
                continue
            f, cam = frames[key], self.cameras[key]
            # On the ground and during the first metre of the climb the cameras look at the floor from a few
            # centimetres: tape, cables and the landing pad fill the picture and gave false alarms. Detections
            # only count once the drone is at least `min_detect_altitude` above the ground.
            pz = (f.get("pose") or (NAN,) * 4)[2]
            if self.min_detect_alt and (pz is None or math.isnan(pz) or pz < self.min_detect_alt):
                continue
            if isinstance(self.tracker, RayTracker):
                ray = cam.pixel_to_ray(d["center"][0], d["center"][1], f)
                if ray is None:
                    continue
                obj, newly = self.tracker.add_ray(d["name"], ray[0], ray[1], d["conf"], t=now,
                                                  range_hint=getattr(cam, "target_distance", None))
                p = (obj["x"], obj["y"], obj["z"])
            else:
                p = cam.pixel_to_map(d["center"][0], d["center"][1], f)
                if p is None:
                    continue
                # trust for the position: 1.0 in the middle of the picture, ~0.05 at the corners
                ih, iw = f["img"].shape[:2]
                r = math.hypot(d["center"][0] - iw / 2.0, d["center"][1] - ih / 2.0) / (0.5 * min(iw, ih))
                extra = {"temp_c": round(float(d["max_temp_c"]), 1)} if d.get("max_temp_c") is not None else None
                w = math.exp(-(r / 0.6) ** 2)
                # a NEW map entry is only opened by a view near the middle of the picture; views near the edge
                # (where a wrong lens value or camera mounting puts the object up to a metre off) only refine
                # an entry that already exists
                obj, newly = self.tracker.add(d["name"], p[0], p[1], p[2], d["conf"], t=now, extra=extra,
                                              weight=w, create=w >= 0.25)
                if obj is None:
                    continue
                if self.self_cal and cam.orientation != "forward":
                    f0, l0 = cam.floor_direction(d["center"][0], d["center"][1])
                    pose = f["pose"]
                    obj.setdefault("_obs", {}).setdefault(key, []).append(
                        (pose[0], pose[1], pose[3], pose[2] - cam.ground_z, f0, l0, w))
                    self._selfcal_step(key, cam)
                if extra and extra["temp_c"] > (obj.get("temp_c") or -1e9):
                    obj["temp_c"] = extra["temp_c"]              # hottest reading of this object so far
            d["map"] = p
            found.append(d)
            if newly:
                obj["confirmed_t"] = now
            self._events.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)) + ".%03d" % int((now % 1) * 1000),
                                   "%.3f" % now, key, d["name"], "%.3f" % d["conf"], "%.3f" % p[0], "%.3f" % p[1],
                                   "%.3f" % (p[2] if len(p) > 2 and p[2] is not None else 0.0),
                                   obj.get("id") or "", int(bool(newly)),
                                   "%.0f" % d["center"][0], "%.0f" % d["center"][1]]
                                  + ["%.3f" % v if v is not None and not math.isnan(v) else "" for v in (f.get("pose") or (NAN,) * 4)]
                                  + ["%.1f" % d["max_temp_c"] if d.get("max_temp_c") is not None else ""])
            if newly:
                snap = os.path.join(self.run_dir, "snapshots", "obj%03d_%s.jpg" % (obj["id"], d["name"]))
                cv2.imwrite(snap, draw(f["img"], [d], (0, 0, 255)))
                obj["snapshot"] = snap
                self.new_objects.append(obj)
                self.log("[detect] CONFIRMED #%d %s at (%.2f, %.2f) conf %.2f" % (obj["id"], obj["name"], obj["x"], obj["y"], d["conf"]))
        # UI frame + training-data capture
        if "rgb" in frames or frames:
            key = "rgb" if "rgb" in frames else list(frames)[0]
            img = frames[key]["img"]
            shown = [d for d in found if d.get("image", "rgb") == key]
            self._ui_dets = (key, shown, now)
            ok, jpg = False, None
            if not self._live_preview:       # --mock: the live view is the frame that was just analysed
                ok, jpg = cv2.imencode(".jpg", draw(img, shown), [cv2.IMWRITE_JPEG_QUALITY, 60])
            if self.save_every and now - self._last_save >= self.save_every:
                self._save_frames(frames)
                self._last_save = now
            conf = self.tracker.confirmed()
            with self.state["_lock"]:
                if ok:
                    self.state["frame_jpg"] = jpg.tobytes()
                self.state["detections"] = [{"id": o["id"], "name": o["name"], "x": o["x"], "y": o["y"], "conf": o["conf"],
                                             "temp": o.get("temp_c"), "hits": o["hits"],
                                             "time": time.strftime("%H:%M:%S", time.localtime(o.get("confirmed_t") or o.get("last_t") or now))}
                                            for o in conf]
                self.state["counts"] = self.tracker.counts()
                self.state["fps"] = self._fps_now()
        self._events_f.flush()
        cams = "+".join(sorted(frames))
        self._perf.writerow(["%.3f" % now, cams, "%.1f" % detect_ms, "%.1f" % ((time.time() - t_cycle) * 1000.0), len(dets)])
        self._perf_rows.append((now, set(frames)))
        if len(self._perf_rows) % 20 == 0:
            self._perf_f.flush()
        return found

    def _selfcal_step(self, key, cam):
        """Every few detections: do the views of each object agree? If another camera mounting / lens scale explains
        them clearly better, adopt it and move the mapped objects to where the corrected views put them."""
        from common import selfcal
        n = self._selfcal_n.get(key, 0) + 1
        self._selfcal_n[key] = n
        if n < 12 or n % 8:
            return
        groups = [o["_obs"][key] for o in self.tracker.objects if key in (o.get("_obs") or {})]
        res = selfcal.solve(groups, current=cam.correction or selfcal.IDENTITY)
        if res is None:
            return
        cam.correction = (res[0], res[1])
        self.log("[calibrate] %s %s" % (key, res[2]))
        for o in self.tracker.objects:                       # re-locate every object from all its stored views
            obs_all, pts = [], []
            for k, obs in (o.get("_obs") or {}).items():
                c = self.cameras[k].correction or selfcal.IDENTITY
                for ob in obs:
                    obs_all.append(ob)
                    pts.append(selfcal.project(ob, c[0], c[1]))
            if obs_all:
                sw = sum(ob[6] for ob in obs_all)
                o["x"] = sum(ob[6] * p[0] for ob, p in zip(obs_all, pts)) / sw
                o["y"] = sum(ob[6] * p[1] for ob, p in zip(obs_all, pts)) / sw
                o["w"] = sw

    def _fps_now(self, window=2.0):
        """Frames per second processed per camera over the last `window` seconds (shown in the UI)."""
        if not self._perf_rows:
            return {}
        t_end = self._perf_rows[-1][0]
        out = {}
        for t, cams in reversed(self._perf_rows):
            if t_end - t > window:
                break
            for c in cams:
                out[c] = out.get(c, 0) + 1
        return {c: round(n / window, 1) for c, n in out.items()}

    def fps_summary(self, threshold=10.0):
        """Per camera: share of 1-second windows with >= threshold processed frames, over the whole run and
        over the airborne time only. Case 1 criterion: >= 10 FPS for > 90 % of the operating time."""
        rows = self._perf_rows
        if not rows:
            return {}
        res = {}
        spans = {"run": (rows[0][0], rows[-1][0])}
        if self._t_air[0]:
            spans["airborne"] = (self._t_air[0], self._t_air[1] or rows[-1][0])
        for cam in sorted(set().union(*[c for _, c in rows])):
            r = {}
            for name, (t0, t1) in spans.items():
                nbins = int(t1 - t0)
                if nbins < 1:
                    continue
                bins = [0] * nbins
                for t, cams in rows:
                    if cam in cams and t0 <= t < t0 + nbins:
                        bins[int(t - t0)] += 1
                r[name] = {"seconds": nbins, "mean_fps": round(sum(bins) / float(nbins), 1),
                           "pct_seconds_ge_%g" % threshold: round(100.0 * sum(b >= threshold for b in bins) / nbins, 1)}
            res[cam] = r
        return res

    def _save_frames(self, frames):
        d = os.path.join(self.run_dir, "frames")
        if self._frames_csv is None:
            os.makedirs(d)
            self._frames_csv = open(os.path.join(d, "frames.csv"), "w")
            self._frames_csv.write("file,camera,t,x,y,z,yaw\n")
            with open(os.path.join(d, "camera_K.json"), "w") as fk:
                json.dump({k: [list(map(float, r)) for r in c.K] for k, c in self.cameras.items()}, fk)
            with open(os.path.join(d, "camera_meta.json"), "w") as fm:     # for analysis/weed_map.py --survey
                json.dump({k: {"image_up_is_forward": bool(getattr(c, "image_up_is_forward", True)),
                               "ground_z": float(getattr(c, "ground_z", 0.0)),
                               "orientation": getattr(c, "orientation", "down")} for k, c in self.cameras.items()}, fm)
        for key, f in frames.items():
            name = "%s_%d.jpg" % (key, int(f["t"] * 1000))
            cv2.imwrite(os.path.join(d, name), f["img"])
            p = f.get("pose") or (NAN, NAN, NAN, NAN)
            self._frames_csv.write("%s,%s,%.3f,%.3f,%.3f,%.3f,%.4f\n" % ((name, key, f["t"]) + tuple(p)))
        self._frames_csv.flush()

    def _preview_loop(self, cam, key):
        """Live view for the operator UI, independent of detection speed: the newest camera frame, scaled down and
        sent as soon as it arrives (ui.fps / ui.width / ui.quality). Boxes are the latest detections (<1 s old)."""
        ui = self.cfg.get("ui") or {}
        period = 1.0 / max(1.0, float(ui.get("fps", 15)))
        width, quality = int(ui.get("width", 640)), int(ui.get("quality", 50))
        last_t, warned = None, False
        while self._perc_run:
            t0 = time.time()
            try:
                f = cam.peek()
                if f is not None and f["t"] != last_t:
                    last_t = f["t"]
                    k, dets, t_d = self._ui_dets
                    vis = draw(f["img"], dets) if (k == key and dets and t0 - t_d < 1.0) else f["img"]
                    h, w = vis.shape[:2]
                    if width and w > width:
                        vis = cv2.resize(vis, (width, int(round(h * width / float(w)))), interpolation=cv2.INTER_AREA)
                    ok, jpg = cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, quality])
                    if ok:
                        with self.state["_lock"]:
                            self.state["frame_jpg"] = jpg.tobytes()
            except Exception as e:
                if not warned:
                    warned = True
                    self.log("[ui] live view error: %s" % e)
            time.sleep(max(0.005, period - (time.time() - t0)))

    def _perception_loop(self):
        while self._perc_run:
            try:
                if not self.perceive_once():
                    time.sleep(0.02)
            except Exception as e:
                self.log("[perception] error: %s" % e)
                time.sleep(0.5)
            self._perc_count += 1

    def _mock_sync(self):
        """--mock only: give perception one frame every mock.frame_dt (0.4) simulated seconds (repeatable tests)."""
        if not (self.mock and self._perc_run):
            return
        now = self.drone.now()
        if now - self._last_sync < self._frame_dt:
            return
        target, t_end = self._perc_count + 1, time.time() + 2.0
        while self._perc_count < target and time.time() < t_end and self._perc_run:
            time.sleep(0.002)
        self._last_sync = now

    def start_perception(self):
        if not self._perc_run:
            self._perc_run = True
            threading.Thread(target=self._perception_loop, daemon=True).start()
            ui = self.cfg.get("ui") or {}
            key = ui.get("camera") or ("rgb" if "rgb" in self.cameras else (list(self.cameras)[0] if self.cameras else None))
            cam = self.cameras.get(key)
            self._live_preview = bool(cam is not None and not self.mock and hasattr(cam, "peek") and ui.get("live", True))
            if self._live_preview:
                threading.Thread(target=self._preview_loop, args=(cam, key), daemon=True).start()

    def stop_perception(self):
        self._perc_run = False

    # ------------------------------------------------------------------ flight helpers for plan()
    def _during(self):
        """Called continuously while flying: telemetry to UI, operator commands, time limit, object hook."""
        self._mock_sync()
        with self.state["_lock"]:
            cmd, self.state["command"] = self.state.get("command"), None
        if cmd in ("abort", "land"):
            DroneBase.abort_flag = True
        elif cmd == "return" and not self._returning:
            raise ReturnHome("operator pressed RETURN")
        if self._t_start and self.drone.now() - self._t_start > self.max_time:
            raise MissionAbort("mission time limit %ds" % self.max_time)
        t = self.drone.telemetry(self.frame_id)
        with self.state["_lock"]:
            self.state["pos"] = "(%.2f, %.2f, %.2f)" % (t.x, t.y, t.z)
            if not (math.isnan(t.x) or math.isnan(t.y)):
                self.state["xy"] = [round(t.x, 2), round(t.y, 2)]
                tr = self.state["track"]
                if not tr or math.hypot(tr[-1][0] - t.x, tr[-1][1] - t.y) > 0.1:
                    tr.append([round(t.x, 2), round(t.y, 2)])
                    del tr[:-400]
            self.state["battery"] = "%.2f V/cell" % t.cell_voltage if not math.isnan(t.cell_voltage) else "?"

    def fly(self, x, y, z=None, yaw=NAN, speed=None, frame_id=None, tolerance=0.2, timeout=30, handle_objects=True):
        z = self.alt if z is None else z
        if (frame_id or self.frame_id) == self.drone.check_frame:
            bad = self.drone.outside_fence(x, y, z)
            if bad:
                self.log("[fence] waypoint (%.2f, %.2f, %.2f) SKIPPED: %s" % (x, y, z, bad))
                return False
        ok = self.drone.goto(x, y, z, yaw=yaw, speed=speed or self.speed, frame_id=frame_id or self.frame_id,
                             tolerance=tolerance, timeout=timeout, during=self._during)
        if handle_objects:
            self.handle_new_objects()
        return ok

    def hover(self, seconds):
        self.drone.hover(seconds, during=self._during)

    def handle_new_objects(self):
        while self.new_objects:
            self.on_object(self.new_objects.pop(0))

    def inspection_height(self):
        return (self.cfg.get("inspect") or {}).get("z", 1.0)

    def on_object(self, obj):
        """
        Default reaction: LED flash, optional inspection hover above the object.
        Moves are split so the drone never flies diagonally through other height layers / obstacles:
        horizontal at the survey height -> straight down -> hover -> straight up -> horizontal back.
        """
        self.drone.led(255, 0, 0, "flash")
        insp = self.cfg.get("inspect") or {}
        if not insp.get("enabled", False):
            return
        here = self.drone.telemetry(self.frame_id)
        if math.isnan(here.x) or math.isnan(here.z):
            self.log("[inspect] no position - inspection of #%d skipped" % obj["id"])
            return
        z_insp = self.inspection_height()
        bad = self.drone.outside_fence(obj["x"], obj["y"], z_insp)
        if bad:
            self.log("[inspect] object #%d %s - inspection skipped" % (obj["id"], bad))
            return
        self.phase("INSPECT", "object #%d %s" % (obj["id"], obj["name"]))
        self.fly(obj["x"], obj["y"], here.z, handle_objects=False)
        self.fly(obj["x"], obj["y"], z_insp, handle_objects=False)
        self.hover(insp.get("hover", 2.0))
        self.drone.led(255, 0, 0, "blink")
        self.fly(obj["x"], obj["y"], here.z, handle_objects=False)
        self.fly(here.x, here.y, here.z, handle_objects=False)
        self.drone.led(0, 0, 0, "fill")
        self.phase("MISSION", "resume")

    # ------------------------------------------------------------------ area helpers
    def survey_waypoints(self, area=None, z=None, overlap=None):
        a = area or self.cfg["area"]
        z = z or self.alt
        step = self.cfg.get("step")
        if not step:
            sc = self.cfg.get("survey_camera")             # e.g. 'thermal' if that camera finds the targets
            cam = self.cameras[sc] if sc in self.cameras else list(self.cameras.values())[0]
            K = cam.K
            hfov = math.degrees(2 * math.atan(K[0, 2] / K[0, 0]))
            vfov = math.degrees(2 * math.atan(K[1, 2] / K[1, 1]))
            w, h = footprint(z, hfov, vfov)
            ov = overlap if overlap is not None else self.cfg.get("overlap", 0.3)
            step = max(0.2, min(w, h) * (1 - ov))
        self.log("[plan] survey area %s at z=%.2f, line spacing %.2f m" % (a, z, step))
        with self.state["_lock"]:
            self.state["settings"]["step_used"] = round(float(step), 3)
        return lawnmower(a[0], a[1], a[2], a[3], step, z)

    # ------------------------------------------------------------------ main flow
    def plan(self):
        raise NotImplementedError

    def preflight(self):
        self.phase("PREFLIGHT")
        t = self.drone.telemetry(self.frame_id)
        problems = []
        if not t.connected:
            problems.append("FCU not connected")
        if not self.mock and math.isnan(t.x):
            # SKYRIS docs: the aruco_map frame usually appears only AFTER take-off, when the camera sees the
            # marker field. On the ground we only require the local EKF position ('map'); the mission then
            # waits for aruco_map right after take-off (wait_for_map) and lands if it never appears.
            tm = self.drone.telemetry("map")
            if math.isnan(tm.x) or self.cfg.get("require_map_before_takeoff", False):
                problems.append("no position in %s%s (are markers visible? is the map loaded?)" % (
                    self.frame_id, "" if not math.isnan(tm.x) else " and no local position in 'map'"))
            else:
                self.log("[preflight] %s not visible from the ground - OK, waiting for it after take-off" % self.frame_id)
        if not math.isnan(t.cell_voltage) and t.cell_voltage < self.drone.min_cell_voltage + 0.2:
            problems.append("battery too low to start: %.2f V/cell" % t.cell_voltage)
        ma = self.drone.max_alt
        for what, z in (("altitude", self.alt), ("takeoff_z", self.cfg.get("takeoff_z", self.alt))):
            if ma is not None and z > ma:
                problems.append("%s %.2f m is above safety.max_altitude %.2f m" % (what, z, ma))
        if not self.mock and self.frame_id == "aruco_map":
            # HARD RULE: never fly a plan that leaves the marker field loaded on the drone (no markers = no position).
            try:
                import rospy
                field = marker_field(rospy.get_param("/aruco_map/map", None))
            except Exception:
                field = None
            if field is None:
                self.log("[preflight] WARNING: could not read the drone's marker map - area not checked against it")
            else:
                bad = outside_marker_field(self.fence, field)
                if bad:
                    problems.append(bad + " - fix `area` / `safety.fence` in the config")
                    self._hard_stop = True
        if not self.mock and t.armed:
            problems.append("drone is already armed - land and disarm before starting a mission "
                            "(takeoff climbs relative to the current height)")
        if not math.isnan(t.x) and not math.isnan(t.y):
            bad = self.drone.outside_fence(t.x, t.y)
            if bad:
                problems.append("start position is %s - check the map / area / safety.fence" % bad)
        for k, cam in self.cameras.items():
            f = None
            for _ in range(30):
                f = cam.get()
                if f is not None:
                    break
                time.sleep(0.1)
            if f is None:
                problems.append("camera '%s' gives no image" % k)
        for p in problems:
            self.log("[preflight] PROBLEM: " + p)
        return not problems

    def wait_for_map(self, timeout=6.0):
        """After take-off: hover until the marker-map frame (aruco_map) gives a position. Never appears -> land."""
        start = self.drone.now()
        while True:
            t = self.drone.telemetry(self.frame_id)
            if not (math.isnan(t.x) or math.isnan(t.y)):
                if self.drone.now() - start > 0.05:
                    self.log("[nav] %s position acquired after take-off: (%.2f, %.2f, %.2f)" % (self.frame_id, t.x, t.y, t.z))
                return True
            if self.drone.now() - start > timeout:
                raise MissionAbort("no position in %s %.0f s after take-off - markers not visible / map not loaded"
                                   % (self.frame_id, timeout))
            self._during()
            self.drone.sleep(0.2)

    def wait_start(self):
        """Wait for START (web UI or Enter). Returns False if the operator pressed ABORT / LAND instead."""
        if self.autostart:
            # One click in the dashboard = fly. On the real drone a short countdown is shown first, so a wrong
            # click can still be cancelled with ABORT / LAND before the motors arm.
            n = 0 if self.mock else int((self.cfg.get("ui") or {}).get("start_countdown", 3))
            for left in range(n, 0, -1):
                self.phase("STARTING", "taking off in %d s - ABORT cancels" % left)
                t_end = time.time() + 1.0
                while time.time() < t_end:
                    with self.state["_lock"]:
                        c = self.state.get("command")
                        if c is not None:
                            self.state["command"] = None
                    if c in ("abort", "land", "return"):
                        return False
                    time.sleep(0.1)
            return True
        self.phase("WAITING", "press START in the web UI (or Enter in this terminal)")

        def stdin_wait():
            try:
                line = sys.stdin.readline()
            except Exception:
                return
            if not line:          # EOF: no terminal attached (nohup, service, IDE) -> only the web UI can start
                return
            with self.state["_lock"]:
                self.state["command"] = "start"
        if sys.stdin is not None:
            threading.Thread(target=stdin_wait, daemon=True).start()
        while True:
            with self.state["_lock"]:
                c = self.state.get("command")
                if c is not None:
                    self.state["command"] = None
            if c == "start":
                return True
            if c in ("abort", "land"):
                return False
            time.sleep(0.2)

    def run(self):
        DroneBase.abort_flag = False
        reason = "completed"
        self.start_perception()          # live view in UI before takeoff
        try:
            if not self.wait_start():
                self.phase("STOPPED", "operator abort before takeoff")
                self.finish("ABORT: operator abort before takeoff")
                return
            if not self.preflight():
                if not self.cfg.get("ignore_preflight", False) or getattr(self, "_hard_stop", False):
                    self.phase("STOPPED", "preflight failed - see log")
                    self.finish("preflight failed")
                    return
                self.log("[preflight] WARNING: ignore_preflight is set - flying despite the problems above")
            self._t_start = self.drone.now()
            self.phase("TAKEOFF")
            self._airborne = True
            self._t_air[0] = time.time()
            self.drone.takeoff(self.cfg.get("takeoff_z", self.alt), during=self._during)
            self.wait_for_map(self.cfg.get("map_wait", 6.0))
            self.phase("MISSION")
            self.plan()
            self.go_home()
        except ReturnHome as e:
            reason = "RETURN: %s" % e
            self.log("[mission] %s -> flying home" % e)
            try:
                self.go_home()
            except MissionAbort as e2:
                reason = "ABORT: %s" % e2
                self.log("[safety] %s -> landing" % e2)
            except (Exception, KeyboardInterrupt) as e2:
                reason = "ERROR while returning: %r" % e2
                self.log("[error] %r -> landing" % e2)
        except MissionAbort as e:
            reason = "ABORT: %s" % e
            self.log("[safety] %s -> landing" % e)
        except KeyboardInterrupt:
            reason = "ABORT: Ctrl+C"
            self.log("[safety] Ctrl+C -> landing")
        except Exception as e:
            reason = "ERROR: %s" % e
            self.log("[error] %r -> landing" % e)
            import traceback
            traceback.print_exc()
        if self._airborne:
            self.phase("LAND", reason)
            try:
                self.drone.land()
            except Exception as e:
                self.log("[land] %s - LAND WITH THE RC TRANSMITTER" % e)
        self.finish(reason)

    def go_home(self):
        self.phase("RETURN")
        self._returning = True
        home = self.cfg.get("home")
        if home:
            self.fly(home[0], home[1], self.alt, handle_objects=False)

    def extra_report_html(self):
        return ""

    def finish(self, reason):
        if self._t_air[0] and not self._t_air[1]:
            self._t_air[1] = time.time()
        self.stop_perception()
        self.phase("REPORT")
        for f in (self._events_f, self._perf_f):
            try:
                f.flush()
            except Exception:
                pass
        fps = self.fps_summary(10.0)
        with open(os.path.join(self.run_dir, "fps_summary.json"), "w") as f:
            json.dump(fps, f, indent=1)
        fps_txt = "; ".join("%s: %s" % (cam, ", ".join("%s %.1f FPS mean, %.1f %% of %d s >= 10 FPS" % (
            span, v["mean_fps"], v["pct_seconds_ge_10"], v["seconds"]) for span, v in r.items())) for cam, r in fps.items())
        objs = self.tracker.confirmed()
        dur = (self.drone.now() - self._t_start) if self._t_start else 0
        dist = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(self.drone.path, self.drone.path[1:]))
        meta = {"Case": self.cfg.get("title", self.name), "Result": reason, "Flight time (s)": "%.0f" % dur,
                "Distance flown (m)": "%.1f" % dist, "Objects confirmed": len(objs),
                "Processing rate": fps_txt or "-",
                "Detectors": ", ".join(getattr(d, "source", "?") for d, _, _ in self.detector.detectors),
                "Run folder": self.run_dir, "Mode": "MOCK" if self.mock else "REAL"}
        path = self.run_dir                                  # the dashboard reads the run folder (Results page)
        if self.cfg.get("report_html", True):                # `report_html: false` = no HTML at all
            path = write_report(os.path.join(self.run_dir, "report.html"), self.cfg.get("title", "Mission report"), objs,
                                path_xy=self.drone.path, area=self.cfg.get("area"), meta=meta,
                                extra_html=self.extra_report_html())
        with open(os.path.join(self.run_dir, "summary.json"), "w") as f:
            json.dump({"result": reason, "duration_s": round(dur, 1), "distance_m": round(dist, 2), "mock": self.mock,
                       "objects": len(objs), "counts": self.tracker.counts(), "case": self.name, "fps": fps}, f, indent=1)
        with open(os.path.join(self.run_dir, "objects.json"), "w") as f:
            json.dump([{k: v for k, v in o.items() if not k.startswith("_")} for o in objs], f, indent=1, default=str)
        cal = {k: {"rotation": c.correction[0], "lens_scale": round(c.correction[1], 3)}
               for k, c in self.cameras.items() if getattr(c, "correction", None)}
        if cal:
            with open(os.path.join(self.run_dir, "camera_selfcal.json"), "w") as f:
                json.dump(cal, f, indent=1)
        with open(os.path.join(self.run_dir, "path.csv"), "w") as f:
            w = csv.writer(f)
            w.writerow(["x", "y", "z"])
            w.writerows(self.drone.path)
        with self.state["_lock"]:
            self.state["report"] = path if path != self.run_dir else None
        self.phase("DONE", reason)
        self.log("[report] %s" % path)

    # ------------------------------------------------------------------ CLI
    @classmethod
    def main(cls, default_config=None):
        ap = argparse.ArgumentParser(description=cls.__doc__)
        ap.add_argument("--config", default=default_config, help="YAML config")
        ap.add_argument("--mock", action="store_true", help="simulate drone + camera on a laptop (no ROS)")
        ap.add_argument("--autostart", action="store_true", help="do not wait for START button")
        ap.add_argument("--time-scale", type=float, default=10.0, help="mock: speed-up factor")
        ap.add_argument("--keep-ui", type=float, default=0, help="keep UI running N seconds after finishing")
        ap.add_argument("--ui-port", type=int, help="operator UI port (default: ui.port in the config, 8090)")
        ap.add_argument("--no-ui", action="store_true", help="do not start the operator web UI")
        ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="change one config value for this run, e.g. --set altitude=1.2 --set fire_c=120 "
                             "--set step=auto --set area=[-2,-1,2,1] --set safety.fence=[-3,-1.5,3,1.5]")
        a = ap.parse_args()
        with open(a.config) as f:
            cfg = yaml.safe_load(f)
        apply_ui_args(cfg, a)
        try:
            changed = mission_settings.apply_overrides(cfg, a.set)
        except ValueError as e:
            print("SETTINGS REFUSED: %s" % e)
            sys.exit(2)
        problems = mission_settings.check_settings(cfg)
        if problems:
            print("SETTINGS REFUSED - nothing was flown:")
            for p in problems:
                print("  - " + p)
            print("Fix them in the dashboard (Mission settings) or in %s." % a.config)
            sys.exit(2)
        if changed:
            print("[settings] changed for this run: " + ", ".join("%s=%s" % kv for kv in changed))
        if not a.mock:
            # ONE mission script per drone. A second one (Launch pressed twice) would take the next UI port, compete
            # for the cameras and the NPU, and could fly its own plan - so it refuses to start.
            import fcntl
            cls._lock_file = open("/tmp/brics_mission.lock", "w")
            try:
                fcntl.flock(cls._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (IOError, OSError):
                print("A mission script is ALREADY RUNNING on this drone (it is waiting for Start, or flying).\n"
                      "Use Start / Land / Abort in the dashboard. To restart it: stop it first (Stop in the console, or\n"
                      "  pkill -INT -f case1_fire.py ).  Not starting a second one.")
                sys.exit(3)
        m = cls(cfg, mock=a.mock, autostart=a.autostart, time_scale=a.time_scale)
        m.run()
        if a.keep_ui:
            time.sleep(a.keep_ui)
        return m


def apply_ui_args(cfg, a):
    """--ui-port / --no-ui command-line overrides for the operator UI."""
    ui = dict(cfg.get("ui") or {})
    if getattr(a, "ui_port", None):
        ui["port"] = a.ui_port
    if getattr(a, "no_ui", False):
        ui["enabled"] = False
    cfg["ui"] = ui
    return cfg
