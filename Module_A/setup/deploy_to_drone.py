#!/usr/bin/env python3
"""Copy toolkit + models to the drone and install its Python packages offline (macOS / Windows / Linux, uses ssh + scp).
   python setup/deploy_to_drone.py [--ip 10.42.0.1]        deploy
   python setup/deploy_to_drone.py --fetch                  copy flight results (runs/) back to this computer
The drone password for user 'orangepi' is asked by ssh."""
import argparse, os, shutil, subprocess, sys, tarfile, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ap = argparse.ArgumentParser()
ap.add_argument("--ip", default="10.42.0.1")
ap.add_argument("--user", default="orangepi")
ap.add_argument("--fetch", action="store_true")
a = ap.parse_args()
host = "%s@%s" % (a.user, a.ip)
if a.fetch:
    os.makedirs(os.path.join(ROOT, "runs"), exist_ok=True)
    sys.exit(subprocess.call(["scp", "-r", host + ":~/brics_toolkit/runs/*", os.path.join(ROOT, "runs")]))
SKIP_DIRS = {".venv", ".venv_win", "datasets", "runs", "docker", "deliverables", "__pycache__", "build", "dist", "python_win", "cad"}
SKIP_SUB = ("offline/docs", "offline/wheels_mac", "offline/wheels_win")
SKIP_FILES = {"core"}           # crash dumps in the toolkit root (hundreds of MB)
def keep(rel):
    parts = rel.replace("\\", "/").split("/")
    if rel in SKIP_FILES or parts[0] in SKIP_DIRS or any(rel.replace("\\", "/").startswith(s) for s in SKIP_SUB):
        return False
    if rel.endswith(".pt") or "/train/" in rel.replace("\\", "/") and rel.startswith("models") or "/_selftest" in "/" + rel:
        return False
    return not rel.endswith((".pyc", ".app", ".exe"))
tmp = os.path.join(tempfile.gettempdir(), "brics_toolkit_deploy.tar.gz")
with tarfile.open(tmp, "w:gz") as t:
    for d, dirs, files in os.walk(ROOT):
        rd = os.path.relpath(d, ROOT)
        dirs[:] = [x for x in dirs if keep(os.path.normpath(os.path.join(rd, x)))]
        for f in files:
            rel = os.path.normpath(os.path.join(rd, f))
            if keep(rel):
                t.add(os.path.join(d, f), arcname="brics_toolkit/" + rel.replace("\\", "/"))
print("[deploy] package %.1f MB -> %s" % (os.path.getsize(tmp) / 1e6, host))
rc = subprocess.call(["scp", tmp, host + ":/tmp/brics_toolkit_deploy.tar.gz"])
if rc:
    sys.exit(rc)
remote = ("cd ~ && tar xzf /tmp/brics_toolkit_deploy.tar.gz && cd brics_toolkit && "
          "python3 -m pip install --user --no-index --find-links offline/wheels_pi onnxruntime 'numpy<1.25' rknn-toolkit-lite2 ; "
          "python3 -c \"import onnxruntime, cv2, yaml; print('drone OK: onnxruntime', onnxruntime.__version__, 'cv2', cv2.__version__)\"")
sys.exit(subprocess.call(["ssh", "-t", host, remote]))
