#!/usr/bin/env python3
"""Simulate a 3-drone swarm on one computer (planner + 3 mocked agents). Works on macOS / Windows / Linux.
   python tests/run_swarm_mock.py [--config config/case3_swarm.yaml] [--scale 15] [--port 8000] [--no-ui]
   Dashboard: http://localhost:<port>   drone UIs: http://localhost:8090, 8091, 8092 (unless --no-ui)
   --port 0 picks a free port (used by the self-test so it never collides with a running planner)."""
import argparse, json, os, socket, subprocess, sys, time
from urllib.request import urlopen
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ap = argparse.ArgumentParser()
ap.add_argument("--config", default="config/case3_swarm.yaml")
ap.add_argument("--scale", default="15")
ap.add_argument("--n", type=int, default=3)
ap.add_argument("--port", type=int, default=8000, help="planner port (0 = any free port)")
ap.add_argument("--no-ui", action="store_true", help="do not start the drones' operator UIs")
ap.add_argument("--timeout", type=float, default=600, help="give up after this many seconds")
a = ap.parse_args()
if a.port == 0:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    a.port = s.getsockname()[1]
    s.close()
py = sys.executable
url = "http://127.0.0.1:%d" % a.port
os.makedirs(os.path.join(ROOT, "runs"), exist_ok=True)
planner = subprocess.Popen([py, "drone/case3_planner.py", "--config", a.config, "--port", str(a.port),          # mock alerts
                            "--alerts", os.path.join(ROOT, "runs", "swarm_mock_alerts.csv")], cwd=ROOT)   # stay out of the real file
agents = []
try:
    for _ in range(50):                      # wait until the planner answers (instead of a fixed sleep)
        try:
            urlopen(url + "/state", timeout=1).read()
            break
        except Exception:
            time.sleep(0.2)
    for i in range(a.n):
        log = open(os.path.join(ROOT, "runs", "swarm_mock_agent%d.log" % i), "w")
        cmd = [py, "drone/case3_swarm_agent.py", "--config", a.config, "--id", str(i), "--mock", "--autostart",
               "--planner", url, "--time-scale", a.scale] + (["--no-ui"] if a.no_ui else [])
        agents.append(subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT))
    end = time.time() + a.timeout
    while time.time() < end and any(p.poll() is None for p in agents):
        time.sleep(0.5)
    rc = 0
    for p in agents:
        if p.poll() is None:
            p.kill()
            rc = 1
            print("agent timed out")
        rc = rc or p.returncode
    s = json.loads(urlopen(url + "/state", timeout=5).read())
    print("---- planner state")
    print("zones:", [z["state"] + "/" + str(z["drone"]) for z in s["zones"]])
    print("alerts:", s["targets"])
finally:
    for p in agents:
        if p.poll() is None:
            p.kill()
    planner.terminate()
sys.exit(rc)
