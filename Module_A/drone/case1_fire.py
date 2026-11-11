#!/usr/bin/env python3
"""
CASE 1 - University 2035: autonomous detection of ignition sources (heat source / flame) and trees.

Flight: takeoff -> lawn-mower survey of the area -> every confirmed fire / flame: alarm, the drone holds its position
at survey height (it never descends or flies towards it: tall artificial trees stand in the field) and photographs it
with both cameras -> trees are mapped and photographed without stopping -> return home -> land.

Detection (config/case1_fire.yaml): thermal neural network (fire, flame) + >= 100 C rule, RGB flame network,
green-area detector for trees.
Run:
  python3 drone/case1_fire.py --config config/case1_fire.yaml              # real drone
  python3 drone/case1_fire.py --config config/case1_fire.yaml --mock --autostart   # laptop test
"""
import os
import sys

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from drone.mission_base import Mission  # noqa: E402

IGNITION = {"fire", "flame", "hotspot", "smoke"}


class FireMission(Mission):
    """Case 1: ignition source search."""
    name = "case1_fire"

    def plan(self):
        for (x, y, z, yaw) in self.survey_waypoints():
            self.fly(x, y, z, yaw)
        self.handle_new_objects()

    def go_home(self):
        Mission.go_home(self)
        # sources confirmed on the way home still get their alarm and photos (from home, before landing)
        for obj in self.new_objects[:]:
            self.new_objects.remove(obj)
            if obj["name"] in IGNITION:
                self.log("[ALARM] IGNITION SOURCE #%d %s at (%.2f, %.2f)%s" % (
                    obj["id"], obj["name"], obj["x"], obj["y"],
                    "  %.0f C" % obj["temp_c"] if obj.get("temp_c") is not None else ""))
                self.drone.led(255, 0, 0, "flash")
            self.snapshot_all(obj, "late")

    def snapshot_all(self, obj, tag=""):
        """Photo from every camera at this moment: runs/<run>/snapshots/obj<id>_<class>_<camera>[_tag].jpg"""
        saved = []
        for key, cam in self.cameras.items():
            peek = getattr(cam, "peek", None)
            f = peek() if peek else cam.get()          # simulated cameras render a fresh frame
            if f is None or f.get("img") is None:
                continue
            name = "obj%03d_%s_%s%s.jpg" % (obj["id"], obj["name"], key, ("_" + tag) if tag else "")
            path = os.path.join(self.run_dir, "snapshots", name)
            if cv2.imwrite(path, f["img"]):
                saved.append(name)
        if saved:
            obj.setdefault("snapshots", []).extend(saved)
            self.log("[snapshot] #%d %s: %s" % (obj["id"], obj["name"], ", ".join(saved)))

    def on_object(self, obj):
        if obj["name"] in IGNITION:
            self.log("[ALARM] IGNITION SOURCE #%d %s at (%.2f, %.2f)%s" % (
                obj["id"], obj["name"], obj["x"], obj["y"],
                "  %.0f C" % obj["temp_c"] if obj.get("temp_c") is not None else ""))
            self.drone.led(255, 0, 0, "flash")
            hold = float(self.cfg.get("snapshot_hover", 2.0) or 0.0)
            if hold > 0:
                self.phase("SNAPSHOT", "object #%d %s - holding position %.0f s" % (obj["id"], obj["name"], hold))
                self.snapshot_all(obj, "start")
                self.hover(hold)
                self.snapshot_all(obj, "end")
                self.phase("MISSION", "resume")
            else:
                self.snapshot_all(obj)
            Mission.on_object(self, obj)          # close inspection only if `inspect.enabled` (off at this venue)
        else:
            self.log("[detect] %s #%d at (%.2f, %.2f) - mapped, no stop" % (obj["name"], obj["id"], obj["x"], obj["y"]))
            self.drone.led(0, 255, 0, "flash")
            self.snapshot_all(obj)

    def extra_report_html(self):
        fires = [o for o in self.tracker.confirmed() if o["name"] in IGNITION]
        if not fires:
            return "<h2 style='color:green'>No ignition sources found</h2>"
        items = "".join("<li><b>%s #%d</b> at X=%.2f m, Y=%.2f m</li>" % (o["name"], o["id"], o["x"], o["y"]) for o in fires)
        return "<h2 style='color:#c00'>&#128293; %d ignition source(s) found</h2><ul>%s</ul>" % (len(fires), items)


if __name__ == "__main__":
    FireMission.main(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "case1_fire.yaml"))
