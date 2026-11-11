"""
Geometry helpers (pure numpy, Python 3.8). Used on the drone AND in offline analysis.

  quat_to_R(qx,qy,qz,qw)                -> 3x3 rotation matrix
  pixel_ray(u, v, K, D)                 -> unit-less ray [x, y, 1] in the camera optical frame
  ray_to_ground(origin, R, ray, z=0)    -> 3D point where the ray hits the plane z = ground_z
  nadir_pixel_to_ground(...)            -> same, assuming a downward camera (when TF is not available)
  footprint(z, hfov, vfov)              -> ground width/height seen by the camera
  ObjectTracker                         -> merges repeated detections of the same object into one
"""
import math

import numpy as np


def quat_to_R(qx, qy, qz, qw):
    n = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw) or 1.0
    x, y, z, w = qx / n, qy / n, qz / n, qw / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def pixel_ray(u, v, K, D=None):
    """Normalised camera ray for pixel (u, v). Undistorts if D (distortion) is given."""
    K = np.asarray(K, dtype=np.float64).reshape(3, 3)
    if D is not None and np.any(np.asarray(D)):
        import cv2
        p = cv2.undistortPoints(np.array([[[u, v]]], np.float64), K, np.asarray(D, np.float64))[0][0]
        return np.array([p[0], p[1], 1.0])
    return np.array([(u - K[0, 2]) / K[0, 0], (v - K[1, 2]) / K[1, 1], 1.0])


def ray_to_ground(origin, R, ray_cam, ground_z=0.0):
    """
    origin: camera position in world (map) frame, R: camera->world rotation,
    ray_cam: ray in camera optical frame. Returns world point on plane z=ground_z or None.
    """
    ray = R.dot(ray_cam)
    if abs(ray[2]) < 1e-9:
        return None
    s = (ground_z - origin[2]) / ray[2]
    if s <= 0:
        return None
    return np.asarray(origin) + s * ray


def nadir_pixel_to_ground(u, v, K, drone_x, drone_y, drone_z, yaw, ground_z=0.0, D=None,
                          cam_forward_is_image_up=True):
    """
    Approximation for a camera pointing straight down (TECHNIC main camera).
    Image 'up' = drone forward (x), image 'right' = drone right (-y) by default.
    Returns (x, y) in the same frame as drone_x/drone_y (e.g. aruco_map).
    """
    r = pixel_ray(u, v, K, D)
    h = drone_z - ground_z
    dx_img, dy_img = r[0] * h, r[1] * h          # metres: right, down in the image
    if cam_forward_is_image_up:
        fwd, left = -dy_img, -dx_img
    else:
        fwd, left = dy_img, dx_img
    c, s = math.cos(yaw), math.sin(yaw)
    return drone_x + c * fwd - s * left, drone_y + s * fwd + c * left


def footprint(z, hfov_deg, vfov_deg):
    """Ground area (width, height in metres) seen by a downward camera at height z."""
    return (2 * z * math.tan(math.radians(hfov_deg) / 2), 2 * z * math.tan(math.radians(vfov_deg) / 2))


def fov_from_K(K, width, height):
    K = np.asarray(K).reshape(3, 3)
    return (math.degrees(2 * math.atan(width / (2 * K[0, 0]))), math.degrees(2 * math.atan(height / (2 * K[1, 1]))))


class ObjectTracker(object):
    """
    Merges detections of the same physical object (same class, closer than `radius` metres).
    An object is 'confirmed' after `min_hits` detections -> avoids false alarms from 1 bad frame.
    """

    def __init__(self, radius=0.4, min_hits=3, same_object=None):
        self.radius, self.min_hits = radius, min_hits
        self.objects = []      # dicts: id, name, x, y, z, hits, w, conf, first_t, last_t, snapshot
        self._next = 1
        # same_object: class names that can be the SAME physical thing seen by different sensors, most important
        # first, e.g. ["fire", "flame"]: a source that is hot AND looks like a flame is one entry, called "fire".
        self.same = list(same_object or [])

    def _same(self, a, b):
        return a == b or (a in self.same and b in self.same)

    def add(self, name, x, y, z=0.0, conf=1.0, t=0.0, extra=None, weight=1.0, create=True):
        """
        Add one observation. Returns (object, newly_confirmed).
        ONE physical object = ONE entry: an observation closer than `radius` to an existing object of the same
        class is merged into it, never mapped again. `weight` says how much this observation is trusted for the
        POSITION (an object in the middle of the picture is located much better than one at the edge), so the
        stored position converges on the best views instead of smearing along the flight path.
        """
        weight = max(1e-3, float(weight))
        best, best_d = None, 1e9
        for o in self.objects:
            if not self._same(o["name"], name):
                continue
            d = math.hypot(o["x"] - x, o["y"] - y)
            if d < best_d:
                best, best_d = o, d
        if best is not None and best_d <= self.radius:
            if name != best["name"] and self.same.index(name) < self.same.index(best["name"]):
                best["name"] = name                        # e.g. the thermal camera confirms heat: flame -> fire
            w0 = best.get("w", float(best["hits"]))
            w1 = w0 + weight
            best["x"] = (best["x"] * w0 + x * weight) / w1      # weighted mean position
            best["y"] = (best["y"] * w0 + y * weight) / w1
            best["z"] = (best["z"] * w0 + z * weight) / w1
            best["w"] = w1
            best["hits"] += 1
            best["last_t"] = t
            if conf > best["conf"]:
                best["conf"] = conf
                if extra:
                    best.update(extra)
            newly = best["id"] is None and best["hits"] >= self.min_hits
            if newly:
                self._number(best)
            self._absorb_neighbours(best)
            return best, newly
        if not create:
            return None, False                             # a poor view never opens a new entry
        o = {"id": None, "name": name, "x": x, "y": y, "z": z, "hits": 1, "w": weight,
             "conf": conf, "first_t": t, "last_t": t}
        if extra:
            o.update(extra)
        self.objects.append(o)
        if self.min_hits <= 1:
            self._number(o)
        return o, self.min_hits <= 1

    def _absorb_neighbours(self, keep):
        """After `keep` moved: swallow same-class entries that are now within `radius` of it (a position that
        was refined can land next to an older duplicate). A confirmed entry always survives an unconfirmed one."""
        for o in list(self.objects):
            if o is keep or not self._same(o["name"], keep["name"]):
                continue
            if math.hypot(o["x"] - keep["x"], o["y"] - keep["y"]) > self.radius:
                continue
            if o["id"] is not None and (keep["id"] is None or o["id"] < keep["id"]):
                continue                                   # the older confirmed entry will absorb `keep` on its next hit
            if o["id"] is not None:
                continue                                   # never delete an entry that was already reported
            wk, wo = keep.get("w", 1.0), o.get("w", 1.0)
            for k in ("x", "y", "z"):
                keep[k] = (keep[k] * wk + o[k] * wo) / (wk + wo)
            keep["w"] = wk + wo
            keep["hits"] += o["hits"]
            keep["first_t"] = min(keep["first_t"], o["first_t"])
            for cam, obs in (o.get("_obs") or {}).items():          # raw views, kept for the camera self-calibration
                keep.setdefault("_obs", {}).setdefault(cam, []).extend(obs)
            self.objects.remove(o)

    def _number(self, o):
        """Confirmed objects are numbered 1, 2, 3 ... in the order they are confirmed (candidates have no id)."""
        o["id"] = self._next
        self._next += 1

    def confirmed(self):
        return [o for o in self.objects if o["hits"] >= self.min_hits]

    def counts(self):
        c = {}
        for o in self.confirmed():
            c[o["name"]] = c.get(o["name"], 0) + 1
        return c


def lawnmower(x0, y0, x1, y1, step, z, yaw=float("nan")):
    """
    Boustrophedon survey path covering rectangle (x0,y0)-(x1,y1). Returns list of (x,y,z,yaw).
    Lines are spread evenly from y0 to y1 (both edges are flown) with a spacing of at most `step`,
    so the far edge of the area is never left uncovered.
    """
    if step <= 0:
        raise ValueError("step must be > 0")
    if y1 < y0:
        y0, y1 = y1, y0
    n = max(1, int(math.ceil((y1 - y0) / float(step) - 1e-9)))
    pts = []
    for i in range(n + 1 if y1 > y0 else 1):
        y = y0 + (y1 - y0) * i / float(n)
        row = [(x0, y), (x1, y)]
        pts += row[::-1] if i % 2 else row
    return [(px, py, z, yaw) for px, py in pts]


def orbit(cx, cy, radius, z, n=12, start_deg=0.0, face_center=True):
    """Waypoints on a circle around (cx, cy), yaw pointing at the centre."""
    pts = []
    for i in range(n + 1):
        a = math.radians(start_deg) + 2 * math.pi * i / n
        x, y = cx + radius * math.cos(a), cy + radius * math.sin(a)
        yaw = math.atan2(cy - y, cx - x) if face_center else float("nan")
        pts.append((x, y, z, yaw))
    return pts


def split_area(x0, y0, x1, y1, n, index, axis="x"):
    """Split a rectangle into n equal strips; returns strip `index` (0-based) as (x0,y0,x1,y1)."""
    if axis == "x":
        w = (x1 - x0) / float(n)
        return (x0 + index * w, y0, x0 + (index + 1) * w, y1)
    h = (y1 - y0) / float(n)
    return (x0, y0 + index * h, x1, y0 + (index + 1) * h)


class RayTracker(object):
    """
    3D object localisation by TRIANGULATION from several viewpoints (for forward/oblique cameras, e.g.
    power-line inspection). Each detection is a ray (camera origin + direction). Rays from different
    positions that pass close to the same point are merged; the position is the least-squares
    intersection of all rays. Until a second, sufficiently different view exists, the position is the
    point at `default_range` along the first ray.
    With require_triangulation (default) an object is only CONFIRMED once its 3D position has really been
    triangulated from sufficiently different views - a guess at `default_range` is never reported.
    Same interface as ObjectTracker (add_ray instead of add, confirmed(), counts()).
    """

    def __init__(self, radius=0.3, min_hits=3, default_range=1.0, min_angle_deg=8.0, require_triangulation=True):
        self.radius, self.min_hits, self.default_range = radius, min_hits, default_range
        self.min_angle = math.radians(min_angle_deg)
        self.require_tri = require_triangulation
        self.objects = []
        self._next = 1

    @staticmethod
    def _ray_point_dist(o, d, p):
        v = p - o
        t = max(0.0, float(v.dot(d)))
        return float(np.linalg.norm(v - t * d)), t

    def _solve(self, obj):
        A, b = np.zeros((3, 3)), np.zeros(3)
        for o, d in obj["_rays"]:
            M = np.eye(3) - np.outer(d, d)
            A += M
            b += M.dot(o)
        dirs = np.array([d for _, d in obj["_rays"]])
        # need angular diversity, otherwise the system is ill-conditioned
        spread = max(math.acos(min(1.0, abs(float(dirs[0].dot(d))))) for d in dirs)
        if spread < self.min_angle:
            return None
        try:
            return np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            return None

    def add_ray(self, name, origin, direction, conf=1.0, t=0.0, extra=None, range_hint=None):
        o = np.asarray(origin, float)
        d = np.asarray(direction, float)
        d = d / (np.linalg.norm(d) or 1.0)
        best, best_dist = None, 1e9
        for ob in self.objects:
            if ob["name"] != name:
                continue
            dist, tt = self._ray_point_dist(o, d, np.array([ob["x"], ob["y"], ob["z"]]))
            if tt > 0 and dist < best_dist:
                best, best_dist = ob, dist
        if best is not None and best_dist <= self.radius:
            best["_rays"].append((o, d))
            if len(best["_rays"]) > 300:          # keep the first view + the latest ones (bounded cost)
                best["_rays"] = best["_rays"][:1] + best["_rays"][-299:]
            best["hits"] += 1
            best["last_t"] = t
            p = self._solve(best)
            if p is not None:
                best["x"], best["y"], best["z"] = float(p[0]), float(p[1]), float(p[2])
                best["triangulated"] = True
            if conf > best["conf"]:
                best["conf"] = conf
                if extra:
                    best.update(extra)
            return best, self._newly(best)
        r = range_hint or self.default_range
        p = o + d * r
        ob = {"id": None, "name": name, "x": float(p[0]), "y": float(p[1]), "z": float(p[2]), "hits": 1,
              "conf": conf, "first_t": t, "last_t": t, "_rays": [(o, d)], "triangulated": False}
        if extra:
            ob.update(extra)
        self.objects.append(ob)
        return ob, self._newly(ob)

    def _ok(self, o):
        return o["hits"] >= self.min_hits and (o.get("triangulated") or not self.require_tri)

    def _newly(self, o):
        """True exactly once: the first time the object meets the confirmation rule."""
        if self._ok(o) and not o.get("_confirmed"):
            o["_confirmed"] = True
            o["id"] = self._next
            self._next += 1
            return True
        return False

    def confirmed(self):
        return [{k: v for k, v in o.items() if not k.startswith("_")} for o in self.objects if self._ok(o)]

    def counts(self):
        c = {}
        for o in self.confirmed():
            c[o["name"]] = c.get(o["name"], 0) + 1
        return c
