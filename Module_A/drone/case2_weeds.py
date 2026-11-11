#!/usr/bin/env python3
"""
CASE 2 - Geosaero: Automatic counting of weed plants + digital infestation map.

Flight: takeoff -> lawnmower survey; at every waypoint STOP, settle, take a sharp photo with exact pose
-> land -> automatically run analysis/weed_map.py on the photos (detect, project to metres, merge duplicates
from overlapping photos, count, heat map) -> report.
Live detections during flight are also shown in the UI.

Run:
  python3 drone/case2_weeds.py --config config/case2_weeds.yaml
  python3 drone/case2_weeds.py --config config/case2_weeds.yaml --mock --autostart
Re-run the analysis later with another model:
  python3 analysis/weed_map.py --survey runs/<run>/frames --model models/weeds/best.onnx --count-classes weed
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from drone.mission_base import Mission  # noqa: E402


class WeedMission(Mission):
    """Case 2: weed survey + counting."""
    name = "case2_weeds"

    def plan(self):
        settle = self.cfg.get("photo_settle", 0.8)
        # turn off time-based saving; we save exactly one sharp photo per waypoint
        self.save_every = 0
        for i, (x, y, z, yaw) in enumerate(self.survey_waypoints_dense()):
            self.fly(x, y, z, 0.0, tolerance=0.12)       # fixed yaw = straight image grid
            self.hover(settle)
            frames = {}
            for key, cam in self.cameras.items():
                f = None
                for _ in range(20):
                    f = cam.get()
                    if f is not None:
                        break
                    self.drone.sleep(0.05)
                if f is not None:
                    frames[key] = f
            if frames:
                self._save_frames(frames)
            self.log("[photo] %d at (%.2f, %.2f)" % (i, x, y))

    def survey_waypoints_dense(self):
        """Grid of photo points: lawnmower lines, plus intermediate points along each line."""
        import math
        pts = self.survey_waypoints()
        step = self.cfg.get("photo_spacing", 0.6)
        out = []
        for (x0, y0, z, yaw), (x1, y1, _, _) in zip(pts[0::2], pts[1::2]):
            n = max(1, int(math.ceil(abs(x1 - x0) / step)))
            out += [(x0 + (x1 - x0) * k / float(n), y0 + (y1 - y0) * k / float(n), z, yaw) for k in range(n + 1)]
        return out

    def on_object(self, obj):
        pass        # no stopping for weeds - counting is done on the photos

    def extra_report_html(self):
        frames = os.path.join(self.run_dir, "frames")
        if not os.path.exists(os.path.join(frames, "frames.csv")):
            return "<p>No survey photos.</p>"
        from analysis import weed_map
        a = self.cfg.get("analysis", {})
        args = ["--survey", frames, "--out", os.path.join(self.run_dir, "weedmap"),
                "--merge", str(a.get("merge", 0.08)), "--cell", str(a.get("cell", 0.5))]
        root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        model = os.path.join(root, a["model"]) if a.get("model") else None
        if model and os.path.exists(model):
            args += ["--model", model]
        elif model:
            self.log("[weeds] model %s not found - using ExG vegetation detector" % model)
        if a.get("count_classes"):
            args += ["--count-classes"] + list(a["count_classes"])
        if a.get("tile"):
            args += ["--tile", str(a["tile"])]
        if self.cfg.get("area"):
            args += ["--area"] + [str(v) for v in self.cfg["area"]]
        counts = weed_map.main(args)
        self.log("[weeds] final count: %s" % counts)
        return ("<h2>Weed count (merged over all photos): %s</h2><p>Full map: <a href='weedmap/report.html'>weedmap/report.html</a></p>"
                % ", ".join("%s = <b>%d</b>" % kv for kv in sorted(counts.items())))


if __name__ == "__main__":
    WeedMission.main(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "case2_weeds.yaml"))
