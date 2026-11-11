#!/usr/bin/env python3
"""
CASE 3 - Swarm agent (runs on EACH drone). 3-5 drones scan a palm plantation and find the infected tree.

  * asks the planner (laptop) for the next free zone, scans it, reports 'zone done', asks again
  * if the planner is unreachable -> falls back to a fixed strip = its drone_id (mission still works)
  * own altitude layer per drone (drone_id) -> no collisions between drones crossing zones.
    Each drone climbs straight up to its layer above its own pad and stays in it (also while marking a tree)
  * infected tree (thermal / spectral / colour sign, or YOLO) confirmed -> hover + LED red + report
    coordinates to the planner, which raises the "treatment needed" alert
  * heartbeat every ~1 s, obeys RETURN ALL / ABORT ALL

Run on drone k:  python3 drone/case3_swarm_agent.py --config config/case3_swarm.yaml --id k
Laptop test of a 3-drone swarm (all mocked): bash tests/run_swarm_mock.sh
"""
import json
import os
import sys
import threading
import time

try:
    from urllib.request import Request, urlopen
except ImportError:  # pragma: no cover
    from urllib2 import Request, urlopen

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common.geometry import split_area                       # noqa: E402
from drone.mission_base import Mission                        # noqa: E402
from drone.technic_api import DroneBase, MissionAbort, ReturnHome  # noqa: E402


class SwarmAgent(Mission):
    """Case 3: swarm agent."""
    name = "case3_swarm"

    def __init__(self, cfg, drone_id=0, **kw):
        sw = cfg.setdefault("swarm", {})
        self.id = str(drone_id)
        self.n = sw.get("n_drones", 3)
        self.url = sw.get("planner_url")
        self.zone = None
        self.remote_cmd = "continue"
        cfg = dict(cfg)
        cfg["case"] = "%s_d%s" % (cfg.get("case", "case3_swarm"), self.id)
        cfg["altitude"] = sw.get("base_altitude", 1.2) + int(drone_id) * sw.get("layer_step", 0.4)
        cfg["takeoff_z"] = cfg["altitude"]          # climb vertically into the own layer before moving sideways
        homes = sw.get("homes")
        if homes and int(drone_id) < len(homes):
            cfg["home"] = homes[int(drone_id)]
        ui = dict(cfg.get("ui", {}))
        ui["port"] = ui.get("port", 8090) + (int(drone_id) if sw.get("mock_ports") else 0)
        cfg["ui"] = ui
        Mission.__init__(self, cfg, **kw)
        if self.mock and homes:              # mock drones start at their own home pad
            self.drone.pos = [homes[int(drone_id)][0], homes[int(drone_id)][1], 0.0]
            self.drone.target = list(self.drone.pos)
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    # ---------------------------------------------------------------- comms
    def _post(self, path, obj, timeout=1.5):
        if not self.url:
            return None
        try:
            req = Request(self.url + path, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
            return json.loads(urlopen(req, timeout=timeout).read())
        except Exception:
            return None

    def _get(self, path, timeout=1.5):
        if not self.url:
            return None
        try:
            return json.loads(urlopen(self.url + path, timeout=timeout).read())
        except Exception:
            return None

    def _heartbeat_loop(self):
        while True:
            try:
                t = self.drone.telemetry(self.frame_id)
                with self.state["_lock"]:
                    ph, bat = self.state.get("phase"), self.state.get("battery", "?")
                r = self._post("/heartbeat", {"id": self.id, "phase": ph, "xyz": [t.x, t.y, t.z], "battery": bat, "zone": self.zone})
                if r:
                    self.remote_cmd = r.get("cmd", "continue")
                    if self.remote_cmd == "abort":
                        DroneBase.abort_flag = True
            except Exception:
                pass
            time.sleep(1.0)

    # ---------------------------------------------------------------- mission
    def _during(self):
        Mission._during(self)
        if self.remote_cmd == "return" and not getattr(self, "_returning", False):
            raise ReturnHome("planner: RETURN ALL")

    def plan(self):
        sw = self.cfg["swarm"]
        if self.url and self._get("/state") is not None:
            self.log("[swarm] planner online: %s" % self.url)
            while True:
                t = self._get("/task?id=%s" % self.id)
                if t is None:
                    self.log("[swarm] planner lost -> finishing with fallback strip")
                    break
                if t.get("cmd") == "abort":
                    DroneBase.abort_flag = True
                    raise MissionAbort("planner: ABORT ALL")
                if t.get("cmd") == "return":
                    raise ReturnHome("planner: RETURN ALL")
                if t.get("cmd") != "zone":
                    self.log("[swarm] planner says %s" % t.get("cmd"))
                    return
                self.zone = t["zone"]
                self.log("[swarm] scanning zone %d %s" % (self.zone, t["rect"]))
                self.scan(t["rect"])
                self._post("/zone_done", {"id": self.id, "zone": self.zone})
                self.zone = None
        # fallback: static strip by drone id
        rect = split_area(*(list(self.cfg["area"]) + [self.n, int(self.id) % self.n, sw.get("axis", "x")]))
        self.zone = "static-%s" % self.id
        self.log("[swarm] static strip %s" % (rect,))
        self.scan(rect)

    def scan(self, rect):
        for (x, y, z, yaw) in self.survey_waypoints(area=rect, z=self.alt):
            self.fly(x, y, z, yaw)

    def on_object(self, obj):
        self.log("[swarm] INFECTED TREE #%d at (%.2f, %.2f) -> reporting" % (obj["id"], obj["x"], obj["y"]))
        r = self._post("/detection", {"id": self.id, "name": obj["name"], "x": obj["x"], "y": obj["y"], "conf": obj["conf"]})
        if r is not None and not r.get("new", True):
            self.log("[swarm] already reported by another drone")
            return
        Mission.on_object(self, obj)          # hover above + LED (marks the tree) - in the own layer
        self.drone.led(255, 0, 0, "fill")

    def inspection_height(self):
        """Never leave the own altitude layer to mark a tree: other drones fly in the layers below/above."""
        return self.alt


if __name__ == "__main__":
    import argparse
    import yaml
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "case3_swarm.yaml"))
    ap.add_argument("--id", type=int, required=True, help="drone number 0..n-1")
    ap.add_argument("--planner", help="override planner url, e.g. http://192.168.1.10:8000")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--autostart", action="store_true")
    ap.add_argument("--time-scale", type=float, default=10.0)
    ap.add_argument("--ui-port", type=int, help="operator UI base port (default ui.port, 8090; mock: +id)")
    ap.add_argument("--no-ui", action="store_true")
    a = ap.parse_args()
    with open(a.config) as f:
        cfg = yaml.safe_load(f)
    from drone.mission_base import apply_ui_args
    apply_ui_args(cfg, a)
    if a.planner:
        cfg.setdefault("swarm", {})["planner_url"] = a.planner
    if a.mock:
        cfg.setdefault("swarm", {})["mock_ports"] = True
    SwarmAgent(cfg, drone_id=a.id, mock=a.mock, autostart=a.autostart, time_scale=a.time_scale).run()
