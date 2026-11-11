#!/usr/bin/env python3
"""
CASE 1 - University 2035: Autonomous detection of ignition sources (campfire / flame, car).

Flight: takeoff -> lawnmower survey of the area -> every confirmed fire/car: LED alarm, hover above it,
snapshot, exact map coordinates -> return home -> land -> HTML/CSV report + live operator UI.

Detection (config/case1_fire.yaml): YOLO model (fire/smoke/car) + thermal hot-spot + HSV flame fallback.
Run:
  python3 drone/case1_fire.py --config config/case1_fire.yaml              # real drone / Gazebo
  python3 drone/case1_fire.py --config config/case1_fire.yaml --mock --autostart   # laptop test
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from drone.mission_base import Mission  # noqa: E402

PRIORITY = {"fire": 0, "flame": 0, "hotspot": 0, "smoke": 1, "car": 2}


class FireMission(Mission):
    """Case 1: fire / ignition source search."""
    name = "case1_fire"

    def plan(self):
        for (x, y, z, yaw) in self.survey_waypoints():
            self.fly(x, y, z, yaw)

    def on_object(self, obj):
        # fire-like objects get an inspection hover + red alarm; others just get logged + blue flash
        if PRIORITY.get(obj["name"], 3) == 0:
            self.log("[ALARM] IGNITION SOURCE #%d at (%.2f, %.2f)" % (obj["id"], obj["x"], obj["y"]))
            Mission.on_object(self, obj)
        else:
            self.drone.led(0, 0, 255, "flash")

    def extra_report_html(self):
        fires = [o for o in self.tracker.confirmed() if PRIORITY.get(o["name"], 3) == 0]
        if not fires:
            return "<h2 style='color:green'>No ignition sources found</h2>"
        items = "".join("<li><b>%s #%d</b> at X=%.2f m, Y=%.2f m</li>" % (o["name"], o["id"], o["x"], o["y"]) for o in fires)
        return "<h2 style='color:#c00'>&#128293; %d ignition source(s) found</h2><ul>%s</ul>" % (len(fires), items)


if __name__ == "__main__":
    FireMission.main(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "case1_fire.yaml"))
