#!/usr/bin/env python3
"""
CASE 4 - Rosseti / Rosatom: autonomous inspection of power-line (PTL) mock-up and energy facilities.

Flight plan (config/case4_powerline.yaml):
  1. ORBIT each support (tower): arc at several heights on the inspection side, nose (and inspection camera)
     facing the tower, short stop at every point for sharp frames
  2. SPAN pass to the next support: fly along the wires at a side offset, looking at the wires
  3. repeat 1-2 for every support (always on the same side of the line -> the drone never crosses the wires)
  4. return, land, report: every defect with type, coordinates (x, y, z), which support / span, snapshot

Defect detection:
  * thermal camera hot-spot  -> "overheating" (contacts / clamps)
  * YOLO model trained on the venue mock-up -> e.g. insulator_damage, support_deformation, wire_sag,
    corona, bird_nest, foreign_object ... (any classes you train)
  * HSV fallback for coloured defect markers used on mock-ups

Run:  python3 drone/case4_powerline.py --config config/case4_powerline.yaml [--mock --autostart]
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common.geometry import orbit  # noqa: E402
from drone.mission_base import Mission  # noqa: E402

SEVERITY = {"overheating": "HIGH", "hotspot": "HIGH", "corona": "HIGH", "insulator_damage": "HIGH",
            "support_deformation": "MEDIUM", "wire_sag": "MEDIUM", "sag": "MEDIUM", "bird_nest": "LOW"}


class PowerLineMission(Mission):
    """Case 4: power line inspection."""
    name = "case4_powerline"

    def set_target_distance(self, d):
        for cam in self.cameras.values():
            cam.target_distance = d

    def plan(self):
        """
        Collision-safe inspection order: orbit arc around support 1 -> span pass 1-2 -> arc around support 2 -> ...
        Everything is flown on ONE side of the line (the side the home pad is on, or span.side), and the arcs
        stop `orbit.wire_margin_deg` before the wire directions, so the drone never crosses the wires -
        neither during the orbits, nor between supports, nor on the way home.
        orbit.full_circle: true restores full circles (only safe if the wires are well below/above the orbit heights).
        """
        sp = [tuple(map(float, s[:2])) for s in self.cfg["supports"]]
        o = self.cfg.get("orbit", {})
        radius, n, dwell = o.get("radius", 1.2), o.get("points", 8), o.get("dwell", 0.8)
        heights = o.get("heights", [1.0, 1.6])
        tower_r = o.get("support_radius", 0.15)
        speed = o.get("speed", 0.3)
        span = self.cfg.get("span", {})
        do_span = span.get("enabled", True) and len(sp) > 1
        if len(sp) == 1 or o.get("full_circle", False):
            if len(sp) > 1:
                self.log("[plan] WARNING orbit.full_circle: the orbits cross the wires - only if the wires are clear of %s" % heights)
            else:
                self.log("[plan] single support: full circle (wire directions unknown - check clearance!)")
            for i, s in enumerate(sp):
                self.current = "support %d" % (i + 1)
                self.phase("MISSION", "orbit %s" % self.current)
                self.set_target_distance(radius - tower_r)
                for h in heights:
                    for (x, y, z, yaw) in orbit(s[0], s[1], radius, h, n=n, start_deg=o.get("start_deg", -90)):
                        self.fly(x, y, z, yaw, speed=speed, tolerance=0.15)
                        self.hover(dwell)
            if do_span:
                self.log("[plan] full_circle mode: span pass skipped (transits would cross the wires)")
            return
        side = self.inspection_side(sp)
        self._router = (sp, radius)
        self.log("[plan] inspection side: %s of the line support 1 -> %d (never crossing the wires)"
                 % ("left" if side > 0 else "right", len(sp)))
        for i in range(len(sp)):
            self.current = "support %d" % (i + 1)
            self.phase("MISSION", "orbit %s" % self.current)
            self.set_target_distance(radius - tower_r)
            pts = self.arc_waypoints(sp, i, side, radius, heights, n, o.get("wire_margin_deg", 25.0), end_forward=i < len(sp) - 1)
            for k, (x, y, z, yaw, stop) in enumerate(pts):
                if k == 0:
                    self.transit(x, y, z, speed)
                self.fly(x, y, z, yaw, speed=speed, tolerance=0.15)
                if stop:
                    self.hover(dwell)
            if do_span and i < len(sp) - 1:
                self.current = "span %d-%d" % (i + 1, i + 2)
                self.phase("MISSION", "inspect %s" % self.current)
                self.set_target_distance(span.get("offset", 1.0))
                for k, (x, y, z, yaw) in enumerate(self.span_waypoints(sp[i], sp[i + 1], side, span.get("offset", 1.0),
                                                                        span.get("height", 1.5), span.get("step", 0.5))):
                    if k == 0:
                        self.transit(x, y, z, span.get("speed", 0.3))
                    self.fly(x, y, z, yaw, speed=span.get("speed", 0.3), tolerance=0.15)
                    self.hover(span.get("dwell", 0.5))

    def inspection_side(self, sp):
        """+1 = left, -1 = right of the direction support 1 -> last support. Default: the side of the home pad."""
        want = str(self.cfg.get("span", {}).get("side", "auto")).lower()
        if want in ("left", "right"):
            return 1 if want == "left" else -1
        (ax, ay), (bx, by) = sp[0], sp[-1]
        hx, hy = (self.cfg.get("home") or [ax, ay - 1.0])[:2]
        cross = (bx - ax) * (hy - ay) - (by - ay) * (hx - ax)
        return 1 if cross >= 0 else -1

    # ------------------------------------------------------------------ collision-free transits
    def _route_nodes(self, sp, r):
        """Detour points: both sides of every support (bisector, distance r) and beyond both line ends."""
        nodes = []
        for i, (cx, cy) in enumerate(sp):
            dirs = []
            if i > 0:
                dirs.append(math.atan2(sp[i - 1][1] - cy, sp[i - 1][0] - cx))
            if i < len(sp) - 1:
                dirs.append(math.atan2(sp[i + 1][1] - cy, sp[i + 1][0] - cx))
            if len(dirs) == 1:                                  # line end: also straight beyond it
                nodes.append((cx - r * math.cos(dirs[0]), cy - r * math.sin(dirs[0])))
                dirs.append(dirs[0] + math.pi)
            a, b = dirs
            mid = math.atan2(math.sin(a) + math.sin(b), math.cos(a) + math.cos(b))
            if abs(math.cos(a - b) + 1) < 1e-9:                 # straight through: bisector is the normal
                mid = a + math.pi / 2
            for ang in (mid, mid + math.pi):
                nodes.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        return nodes

    @staticmethod
    def _seg_dist(p, q, a, b):
        def orient(u, v, w):
            return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])
        if orient(a, b, p) * orient(a, b, q) < 0 and orient(p, q, a) * orient(p, q, b) < 0:
            return 0.0

        def pd(c, u, v):
            vx, vy = v[0] - u[0], v[1] - u[1]
            L2 = vx * vx + vy * vy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((c[0] - u[0]) * vx + (c[1] - u[1]) * vy) / L2))
            return math.hypot(c[0] - u[0] - t * vx, c[1] - u[1] - t * vy)
        return min(pd(p, a, b), pd(q, a, b), pd(a, p, q), pd(b, p, q))

    def _seg_ok(self, p, q, sp, r):
        """Segment p-q keeps >= 0.6*r from every support and >= 0.5 m from every wire (2D, conservative)."""
        if any(self._seg_dist(p, q, s, s) < 0.6 * r for s in sp):
            return False
        return all(self._seg_dist(p, q, a, b) >= 0.5 for a, b in zip(sp, sp[1:]))

    def safe_route(self, a, b):
        """Shortest detour a -> b through the detour points that never crosses / grazes a wire or support."""
        sp, r = self._router
        if self._seg_ok(a, b, sp, r):
            return []
        nodes = [tuple(a), tuple(b)] + self._route_nodes(sp, r)
        dist, prev, todo = {0: 0.0}, {}, set(range(len(nodes)))
        while todo:
            u = min(todo, key=lambda k: dist.get(k, float("inf")))
            if u not in dist or u == 1:
                break
            todo.discard(u)
            for v in todo:
                if self._seg_ok(nodes[u], nodes[v], sp, r):
                    d = dist[u] + math.hypot(nodes[u][0] - nodes[v][0], nodes[u][1] - nodes[v][1])
                    if d < dist.get(v, float("inf")):
                        dist[v], prev[v] = d, u
        if 1 not in dist:
            self.log("[plan] WARNING: no clear transit from (%.2f, %.2f) to (%.2f, %.2f) - flying direct" % (a + b))
            return []
        path, k = [], prev.get(1)
        while k is not None and k != 0:
            path.append(nodes[k])
            k = prev.get(k)
        return path[::-1]

    def transit(self, x, y, z=None, speed=None):
        """Fly to the start of the next section via detour points if the straight line is not clear."""
        if not getattr(self, "_router", None):
            return
        t = self.drone.telemetry(self.frame_id)
        if math.isnan(t.x):
            return
        route = self.safe_route((t.x, t.y), (x, y))
        if route:
            self.log("[plan] transit via %s (keeps clear of wires and supports)" % ", ".join("(%.2f, %.2f)" % p for p in route))
        for (px, py) in route:
            self.fly(px, py, t.z, speed=speed, handle_objects=False)

    def go_home(self):
        """Return home without crossing the wires (detour around the line if needed), then land."""
        home = self.cfg.get("home")
        if home and getattr(self, "_router", None):
            self.phase("RETURN")
            self._returning = True
            self.transit(home[0], home[1])
        Mission.go_home(self)

    @staticmethod
    def arc_waypoints(sp, i, side, radius, heights, n, margin_deg, end_forward=True):
        """
        Viewpoints around support i on the inspection side only: from just after the wire towards the previous
        support to just before the wire towards the next one (boustrophedon over the heights).
        Returns (x, y, z, yaw_to_support, dwell?) tuples; the last point is at the forward end if end_forward.
        """
        cx, cy = sp[i]
        if i < len(sp) - 1:
            phi_f = math.atan2(sp[i + 1][1] - cy, sp[i + 1][0] - cx)
        else:
            phi_f = math.atan2(cy - sp[i - 1][1], cx - sp[i - 1][0])        # virtual continuation
        phi_b = math.atan2(sp[i - 1][1] - cy, sp[i - 1][0] - cx) if i > 0 else phi_f + math.pi
        sigma = -side                                                       # left side -> sweep clockwise
        extent = ((phi_f - phi_b) * sigma) % (2 * math.pi)
        m = math.radians(margin_deg)
        usable = extent - 2 * m
        if usable < math.radians(10):                                       # very sharp bend: one viewpoint
            angles = [phi_b + sigma * extent / 2.0]
        else:
            k = max(2, int(n))
            angles = [phi_b + sigma * (m + usable * j / float(k - 1)) for j in range(k)]

        def pt(a, h):
            x, y = cx + radius * math.cos(a), cy + radius * math.sin(a)
            return (x, y, h, math.atan2(cy - y, cx - x))
        out = []
        for hi, h in enumerate(heights):
            seq = angles if hi % 2 == 0 else angles[::-1]
            out += [pt(a, h) + (True,) for a in seq]
        if end_forward and len(heights) % 2 == 0 and len(angles) > 1:      # ended at the back end -> transit along the arc
            out += [pt(a, heights[-1]) + (False,) for a in angles[1:]]
        return out

    @staticmethod
    def span_waypoints(a, b, side, offset, height, step):
        """Points parallel to the wires a->b at `offset` on the inspection side, camera facing the wires."""
        (ax, ay), (bx, by) = a, b
        L = math.hypot(bx - ax, by - ay)
        if L < 1e-6:
            return []
        ux, uy = (bx - ax) / L, (by - ay) / L
        nx, ny = -uy * side, ux * side                       # unit normal towards the inspection side
        yaw = math.atan2(-ny, -nx)                           # look back at the line
        steps = max(2, int(L / step))
        return [(ax + ux * L * k / steps + nx * offset, ay + uy * L * k / steps + ny * offset, height, yaw)
                for k in range(steps + 1)]

    def on_object(self, obj):
        obj["where"] = self.locate(obj)
        obj["severity"] = SEVERITY.get(obj["name"], "CHECK")
        self.log("[DEFECT] #%d %s (%s) at (%.2f, %.2f, %.2f) on %s" % (
            obj["id"], obj["name"], obj["severity"], obj["x"], obj["y"], obj["z"], obj["where"]))
        self.drone.led(255, 0, 0, "flash")
        self.hover(self.cfg.get("defect_hover", 1.5))            # extra frames of the defect

    def locate(self, obj):
        """Name the nearest support or span for the report."""
        sp = self.cfg["supports"]
        best, bd = "", 1e9
        for i, (x, y) in enumerate(sp):
            d = math.hypot(obj["x"] - x, obj["y"] - y)
            if d < bd:
                best, bd = "support %d" % (i + 1), d
        for i in range(len(sp) - 1):
            (ax, ay), (bx, by) = sp[i], sp[i + 1]
            L2 = (bx - ax) ** 2 + (by - ay) ** 2
            t = max(0.0, min(1.0, ((obj["x"] - ax) * (bx - ax) + (obj["y"] - ay) * (by - ay)) / L2))
            d = math.hypot(obj["x"] - (ax + t * (bx - ax)), obj["y"] - (ay + t * (by - ay)))
            if d + 0.3 < bd and 0.15 < t < 0.85:
                best, bd = "span %d-%d (%.0f%% along)" % (i + 1, i + 2, 100 * t), d
        return best

    def extra_report_html(self):
        objs = self.tracker.confirmed()
        if not objs:
            return "<h2 style='color:green'>No defects detected</h2>"
        rows = "".join("<tr><td>%d</td><td><b>%s</b></td><td>%s</td><td>%s</td><td>%.2f</td><td>%.2f</td><td>%.2f</td></tr>" % (
            o["id"], o["name"], o.get("severity", ""), o.get("where", ""), o["x"], o["y"], o["z"]) for o in objs)
        return ("<h2 style='color:#c00'>%d defect(s) - ground station report</h2><table><tr><th>#</th><th>Defect</th>"
                "<th>Severity</th><th>Location</th><th>X</th><th>Y</th><th>Height</th></tr>%s</table>" % (len(objs), rows))


if __name__ == "__main__":
    PowerLineMission.main(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "case4_powerline.yaml"))
