#!/usr/bin/env python3
"""
CASE 3 - Swarm planner (runs on the LAPTOP / ground station). Standard library only.

The planner splits the plantation into zones and hands them out like a work queue:
  * every drone asks for the next zone when it is free  -> zones are distributed AUTONOMOUSLY
  * a zone whose drone stops sending heartbeats (crash / battery / link) is put back in the queue
  * detections of infected trees from all drones are merged and shown as ALERTS (need for treatment)
  * ABORT ALL / RETURN ALL buttons

Run:  python3 drone/case3_planner.py --config config/case3_swarm.yaml       then open http://localhost:8000
Agents (one per drone) connect to http://<laptop-ip>:8000 (set planner_url in the config).
"""
import argparse
import json
import math
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common.geometry import split_area  # noqa: E402

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Swarm control</title><style>
body{font-family:Arial;background:#111;color:#eee;margin:0}header{background:#6a040f;padding:10px 16px;font-size:20px;font-weight:bold}
.wrap{display:flex;flex-wrap:wrap;gap:12px;padding:12px}.card{background:#222;border-radius:8px;padding:12px;flex:1;min-width:300px}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #333;padding:4px;text-align:left}
button{font-size:17px;padding:10px 18px;border:0;border-radius:6px;margin:4px;color:#fff;cursor:pointer}
.alert{background:#e63946;padding:8px;border-radius:6px;margin:4px 0;font-weight:bold}
</style></head><body><header>Swarm Control - Red Palm Weevil detection</header><div class="wrap">
<div class="card"><button style="background:#e9c46a;color:#000" onclick="cmd('return')">RETURN ALL</button>
<button style="background:#e63946" onclick="if(confirm('ABORT ALL?'))cmd('abort')">ABORT ALL (land)</button>
<button style="background:#2a9d8f" onclick="cmd('continue')">CONTINUE</button>
<h3>Drones</h3><table id="dr"></table><h3>Zones</h3><table id="zn"></table></div>
<div class="card"><h3>Infected trees - treatment needed</h3><div id="al"></div><svg id="map" width="420" height="420" style="background:#fafafa"></svg></div></div>
<script>
function cmd(c){fetch('/global?c='+c,{method:'POST'})}
async function tick(){const s=await (await fetch('/state')).json();
let d='<tr><th>ID</th><th>Phase</th><th>Pos</th><th>Battery</th><th>Zone</th><th>Last seen</th></tr>';
for(const k in s.drones){const x=s.drones[k];d+=`<tr><td>${k}</td><td>${x.phase}</td><td>${x.pos}</td><td>${x.battery}</td><td>${x.zone}</td><td>${x.age.toFixed(1)}s</td></tr>`}
document.getElementById('dr').innerHTML=d;
let z='<tr><th>Zone</th><th>Rect</th><th>State</th><th>Drone</th></tr>';
s.zones.forEach((q,i)=>{z+=`<tr><td>${i}</td><td>${q.rect.map(v=>v.toFixed(1)).join(', ')}</td><td>${q.state}</td><td>${q.drone??''}</td></tr>`});
document.getElementById('zn').innerHTML=z;
let a='';s.targets.forEach(t=>{a+=`<div class="alert">Tree #${t.id} ${t.name} at (${t.x.toFixed(2)}, ${t.y.toFixed(2)}) - found by drone ${t.drone}</div>`});
document.getElementById('al').innerHTML=a||'<i>none yet</i>';
const A=s.area,k=380/Math.max(A[2]-A[0],A[3]-A[1]),P=(x,y)=>[20+(x-A[0])*k,400-(y-A[1])*k];let m='';
const col={todo:'#ddd',active:'#8ecae6',done:'#95d5b2'};
s.zones.forEach(q=>{const[a,b]=P(q.rect[0],q.rect[3]),[c,e]=P(q.rect[2],q.rect[1]);m+=`<rect x="${a}" y="${b}" width="${c-a}" height="${e-b}" fill="${col[q.state]}" stroke="#555"/>`});
for(const kk in s.drones){const x=s.drones[kk];if(x.xy){const[a,b]=P(x.xy[0],x.xy[1]);m+=`<circle cx="${a}" cy="${b}" r="6" fill="#023047"/><text x="${a+8}" y="${b}" font-size="12">${kk}</text>`}}
s.targets.forEach(t=>{const[a,b]=P(t.x,t.y);m+=`<circle cx="${a}" cy="${b}" r="8" fill="#e63946"/>`});
document.getElementById('map').innerHTML=m;}
setInterval(tick,700);tick();</script></body></html>"""


class Planner(object):
    def __init__(self, cfg):
        self.cfg = cfg
        sw = cfg.get("swarm", {})
        self.area = cfg["area"]
        n_zones = sw.get("zones", 2 * sw.get("n_drones", 3))
        self.zones = [{"rect": list(split_area(*(self.area + [n_zones, i, sw.get("axis", "x")]))), "state": "todo",
                       "drone": None} for i in range(n_zones)]
        self.drones = {}
        self.targets = []
        self.global_cmd = "continue"
        self.timeout = sw.get("heartbeat_timeout", 8.0)
        self.merge = sw.get("merge_radius", 0.5)
        self.lock = threading.Lock()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _watchdog(self):
        while True:
            time.sleep(1)
            with self.lock:
                now = time.time()
                for did, d in self.drones.items():
                    if d["phase"] not in ("DONE", "LAND", "REPORT") and now - d["t"] > self.timeout:
                        for z in self.zones:
                            if z["state"] == "active" and z["drone"] == did:
                                z["state"], z["drone"] = "todo", None
                                print("[planner] drone %s lost -> zone requeued" % did)
                        d["phase"] = "LOST"

    def heartbeat(self, m):
        xyz = [v if isinstance(v, (int, float)) and math.isfinite(v) else None for v in list(m.get("xyz") or [])[:3]]
        xyz += [None] * (3 - len(xyz))
        ok = None not in xyz
        with self.lock:
            self.drones[str(m["id"])] = {"phase": m.get("phase", "?"),
                                         "pos": "(%.1f, %.1f, %.1f)" % tuple(xyz) if ok else "NO POSITION",
                                         "xy": xyz[:2] if ok else None, "battery": m.get("battery", "?"),
                                         "zone": m.get("zone"), "t": time.time()}
            return {"cmd": self.global_cmd}

    def task(self, did):
        with self.lock:
            if self.global_cmd != "continue":
                return {"cmd": self.global_cmd}
            for i, z in enumerate(self.zones):
                if z["state"] == "active" and z["drone"] == did:
                    return {"cmd": "zone", "zone": i, "rect": z["rect"]}
            for i, z in enumerate(self.zones):
                if z["state"] == "todo":
                    z["state"], z["drone"] = "active", did
                    print("[planner] zone %d -> drone %s" % (i, did))
                    return {"cmd": "zone", "zone": i, "rect": z["rect"]}
            return {"cmd": "done"}

    def zone_done(self, did, i):
        with self.lock:
            if 0 <= i < len(self.zones) and self.zones[i]["drone"] == did:
                self.zones[i]["state"] = "done"
                print("[planner] zone %d done by %s" % (i, did))
        return {"ok": True}

    def detection(self, m):
        if not all(isinstance(m.get(k), (int, float)) and math.isfinite(m[k]) for k in ("x", "y")):
            return {"new": False, "error": "bad coordinates"}
        with self.lock:
            for t in self.targets:
                if t["name"] == m["name"] and math.hypot(t["x"] - m["x"], t["y"] - m["y"]) < self.merge:
                    return {"new": False}
            t = {"id": len(self.targets) + 1, "name": m["name"], "x": m["x"], "y": m["y"], "drone": m["id"], "t": time.time()}
            self.targets.append(t)
            print("[planner] ALERT tree #%d %s at (%.2f, %.2f) by drone %s - TREATMENT NEEDED" % (t["id"], t["name"], t["x"], t["y"], t["drone"]))
            with open(self.cfg.get("swarm", {}).get("alerts_file", "swarm_alerts.csv"), "a") as f:
                f.write("%s,%d,%s,%.3f,%.3f,%s\n" % (time.strftime("%H:%M:%S"), t["id"], t["name"], t["x"], t["y"], t["drone"]))
            return {"new": True, "id": t["id"]}

    def snapshot(self):
        with self.lock:
            now = time.time()
            dr = {k: dict(v, age=now - v["t"]) for k, v in self.drones.items()}
            return {"drones": dr, "zones": self.zones, "targets": self.targets, "area": self.area, "cmd": self.global_cmd}


def serve(planner, port):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            b = json.dumps(obj, default=str, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b)

        def _body(self):
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            p, _, q = self.path.partition("?")
            if p == "/":
                b = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b)
            elif p == "/state":
                self._json(planner.snapshot())
            elif p == "/task":
                self._json(planner.task(q.split("id=")[-1]))
            else:
                self._json({"error": "404"}, 404)

        def do_POST(self):
            p, _, q = self.path.partition("?")
            if p == "/heartbeat":
                self._json(planner.heartbeat(self._body()))
            elif p == "/detection":
                self._json(planner.detection(self._body()))
            elif p == "/zone_done":
                m = self._body()
                self._json(planner.zone_done(str(m["id"]), int(m["zone"])))
            elif p == "/global":
                c = q.split("c=")[-1]
                if c not in ("continue", "return", "abort"):
                    return self._json({"error": "unknown command"}, 400)
                planner.global_cmd = c
                print("[planner] GLOBAL COMMAND: %s" % planner.global_cmd.upper())
                self._json({"ok": True})
            else:
                self._json({"error": "404"}, 404)

    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    print("[planner] dashboard: http://localhost:%d   (agents use http://<this-laptop-ip>:%d)" % (port, port))
    return srv


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "case3_swarm.yaml"))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--alerts", help="alerts CSV file (default swarm.alerts_file in the config)")
    a = ap.parse_args()
    with open(a.config) as f:
        cfg = yaml.safe_load(f)
    if a.alerts:
        cfg.setdefault("swarm", {})["alerts_file"] = a.alerts
    serve(Planner(cfg), a.port).serve_forever()
