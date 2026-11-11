#!/usr/bin/env python3
"""
GENERIC mission - for ANY new problem statement (built by Mission Studio, or by hand).

mission_type (config):
  survey      lawnmower over `area` with a downward camera, react to objects        (search & detect tasks)
  photos      survey that stops at a grid and saves sharp photos + analysis count   (counting / mapping tasks)
  orbit       circle around `targets` (structures) facing them, forward camera      (inspection tasks)
  waypoints   fly a given list of `waypoints` [[x, y, z, yaw_deg], ...]              (route / patrol tasks)

reaction (config) for confirmed objects of `alarm_classes` (empty = all):
  inspect: true/false   descend + hover above the object (survey types)
  led: [r, g, b]        LED colour for the alarm
  hover: seconds        extra hover to film the object
Run:  python3 drone/generic_mission.py --config config/generated/<name>.yaml [--mock --autostart]
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common.geometry import orbit  # noqa: E402
from drone.mission_base import Mission  # noqa: E402


class GenericMission(Mission):
    """Generic configurable mission."""
    name = "generic"

    def plan(self):
        t = self.cfg.get("mission_type", "survey")
        if t == "survey":
            for (x, y, z, yaw) in self.survey_waypoints():
                self.fly(x, y, z, yaw)
        elif t == "photos":
            from drone.case2_weeds import WeedMission
            WeedMission.plan(self)
        elif t == "orbit":
            o = self.cfg.get("orbit", {})
            for i, s in enumerate(self.cfg.get("targets", [])):
                self.current = "target %d" % (i + 1)
                for c in self.cameras.values():
                    c.target_distance = o.get("radius", 1.2) - o.get("target_radius", 0.15)
                for h in o.get("heights", [1.0, 1.5]):
                    for (x, y, z, yaw) in orbit(s[0], s[1], o.get("radius", 1.2), h, n=o.get("points", 8)):
                        self.fly(x, y, z, yaw, tolerance=0.15)
                        self.hover(o.get("dwell", 0.8))
        elif t == "waypoints":
            for w in self.cfg.get("waypoints", []):
                yaw = math.radians(w[3]) if len(w) > 3 and w[3] is not None else float("nan")
                self.fly(w[0], w[1], w[2] if len(w) > 2 else self.alt, yaw)
                self.hover(self.cfg.get("waypoint_dwell", 0.5))
        else:
            raise ValueError("unknown mission_type %s" % t)

    def survey_waypoints_dense(self):
        from drone.case2_weeds import WeedMission
        return WeedMission.survey_waypoints_dense(self)

    def on_object(self, obj):
        r = self.cfg.get("reaction", {})
        alarm = r.get("alarm_classes") or []
        if alarm and obj["name"] not in alarm:
            self.drone.led(0, 0, 255, "flash")
            return
        self.log("[ALARM] %s #%d at (%.2f, %.2f, %.2f)" % (obj["name"], obj["id"], obj["x"], obj["y"], obj.get("z", 0)))
        led = r.get("led", [255, 0, 0])
        self.drone.led(led[0], led[1], led[2], "flash")
        if r.get("inspect", False) and self.cfg.get("mission_type", "survey") in ("survey", "waypoints"):
            self.cfg.setdefault("inspect", {})["enabled"] = True
            Mission.on_object(self, obj)
        elif r.get("hover", 0):
            self.hover(r["hover"])

    def extra_report_html(self):
        if self.cfg.get("mission_type") == "photos":
            from drone.case2_weeds import WeedMission
            return WeedMission.extra_report_html(self)
        objs = self.tracker.confirmed()
        return "<h2>%d object(s) found: %s</h2>" % (len(objs), ", ".join("%s=%d" % kv for kv in sorted(self.tracker.counts().items())))


if __name__ == "__main__":
    GenericMission.main()
