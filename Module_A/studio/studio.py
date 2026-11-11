#!/usr/bin/env python3
"""
BRICS Mission Studio - point-and-click control of the whole toolkit (offline, runs in the browser).

  bash studio.command        (double-click in Finder)     or     .venv/bin/python studio/studio.py
  -> opens http://localhost:7777

Select PS -> data & model -> mission -> test -> economics -> documents -> drone.  AUTOPILOT does all of it.
"""
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

ROOT = os.path.abspath(os.environ.get("BRICS_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
import yaml  # noqa: E402

from studio.cases import CASES, custom_case  # noqa: E402

WIN = sys.platform.startswith("win")


def find_python():
    """The toolkit's Python environment (never the frozen app executable)."""
    for c in (os.path.join(ROOT, ".venv", "bin", "python"), os.path.join(ROOT, ".venv", "Scripts", "python.exe"),
              os.path.join(ROOT, ".venv_win", "Scripts", "python.exe")):
        if os.path.exists(c):
            return c
    if not getattr(sys, "frozen", False):
        return sys.executable
    return shutil.which("python3") or shutil.which("python") or "python"


PY = find_python()
PROJ_DIR = os.path.join(ROOT, "studio", "projects")
os.makedirs(PROJ_DIR, exist_ok=True)
os.makedirs(os.path.join(ROOT, "config", "generated"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "economics", "generated"), exist_ok=True)
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

JOBS = {}
LOCK = threading.Lock()


# ============================================================================ jobs
class Job(object):
    def __init__(self, title):
        self.id = uuid.uuid4().hex[:8]
        self.title, self.status, self.lines, self.rc = title, "running", [], None
        self.started, self.ended, self.result = time.time(), None, {}
        self.proc = None
        with LOCK:
            JOBS[self.id] = self

    def log(self, s):
        for part in str(s).replace("\r\n", "\n").split("\n"):
            part = ANSI.sub("", part.split("\r")[-1])
            if part.strip():
                self.lines.append(part)
        if len(self.lines) > 4000:
            del self.lines[:1000]

    def run(self, cmd, cwd=ROOT):
        """Run one command, stream output. Returns exit code."""
        self.log("$ " + " ".join(shlex.quote(c) for c in cmd))
        env = dict(os.environ, PYTHONUNBUFFERED="1", YOLO_OFFLINE="1")
        self.proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, bufsize=0)
        buf = b""
        while True:
            ch = self.proc.stdout.read(256)
            if not ch:
                break
            buf += ch
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self.log(line.decode("utf-8", "replace"))
        if buf:
            self.log(buf.decode("utf-8", "replace"))
        rc = self.proc.wait()
        self.log("(exit code %d)" % rc)
        return rc

    def finish(self, ok=True):
        self.status = "done" if ok else "failed"
        self.ended = time.time()

    def to_dict(self, tail=400):
        return {"id": self.id, "title": self.title, "status": self.status, "log": self.lines[-tail:],
                "elapsed": round((self.ended or time.time()) - self.started), "result": self.result}


def start_job(title, fn):
    j = Job(title)

    def wrap():
        try:
            ok = fn(j)
            j.finish(ok is not False)
        except Exception as e:
            import traceback
            j.log("ERROR: %s" % e)
            j.log(traceback.format_exc())
            j.finish(False)
    threading.Thread(target=wrap, daemon=True).start()
    return j


# ============================================================================ projects
def slugify(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")[:40] or "project"


HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,252}$")


def check_host(ip):
    """Drone IP / host name typed by the user - only letters, digits, dots and dashes (it ends up in a shell)."""
    ip = str(ip or "").strip()
    if not HOST_RE.match(ip):
        raise ValueError("invalid drone address %r (use e.g. 10.42.0.1)" % ip)
    return ip


def proj_path(slug):
    return os.path.join(PROJ_DIR, slug + ".json")


def load_project(slug=None):
    """Current (or given) project dict, or None if there is none / the file is unreadable."""
    try:
        if slug is None:
            cur = os.path.join(PROJ_DIR, "_current")
            if not os.path.exists(cur):
                return None
            with open(cur) as f:
                slug = f.read().strip()
        if not slug or slugify(slug) != slug:
            return None
        p = proj_path(slug)
        if not os.path.exists(p):
            return None
        with open(p) as f:
            pr = json.load(f)
        return pr if isinstance(pr, dict) and pr.get("slug") and pr.get("config") else None
    except (OSError, ValueError):
        return None


def list_projects():
    """All readable projects (corrupt files are skipped instead of breaking the app)."""
    out = []
    for f in sorted(glob.glob(os.path.join(PROJ_DIR, "*.json"))):
        if f.endswith("_case.json"):
            continue
        pr = load_project(os.path.splitext(os.path.basename(f))[0])
        if pr:
            out.append(pr)
    return out


def _write(path, text):
    """Write atomically (a crash / full disk never leaves a half-written config or project)."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def save_project(p):
    _write(proj_path(p["slug"]), json.dumps(p, indent=1))
    _write(os.path.join(PROJ_DIR, "_current"), p["slug"])
    return p


def case_of(p):
    return CASES[p["case"]] if p["case"] in CASES else p["case_data"]


TEMPLATES = {
    "survey": {"area": [0, 0, 4, 4], "altitude": 1.5, "speed": 0.4, "overlap": 0.3,
               "inspect": {"enabled": True, "z": 1.0, "hover": 3.0}, "tracker": {"radius": 0.4, "min_hits": 3},
               "cameras": {"rgb": {"type": "ros", "topic": "main_camera/image_raw_throttled"}}},
    "photos": {"area": [0, 0, 3, 3], "altitude": 1.2, "speed": 0.3, "overlap": 0.35, "photo_spacing": 0.6, "photo_settle": 0.8,
               "tracker": {"radius": 0.08, "min_hits": 1}, "analysis": {"merge": 0.08, "cell": 0.5},
               "cameras": {"rgb": {"type": "ros", "topic": "main_camera/image_raw_throttled"}}},
    "orbit": {"targets": [[1.5, 2.0]], "altitude": 1.2, "speed": 0.3,
              "orbit": {"radius": 1.2, "target_radius": 0.15, "heights": [0.8, 1.5], "points": 8, "dwell": 0.8},
              "tracker": {"mode": "rays", "radius": 0.25, "min_hits": 4, "default_range": 1.0},
              "cameras": {"rgb": {"type": "ros", "topic": "main_camera/image_raw_throttled", "orientation": "forward"}}},
    "waypoints": {"waypoints": [[1, 0, 1.2, 0], [2, 1, 1.2, 90], [1, 2, 1.2, 180]], "altitude": 1.2, "speed": 0.4,
                  "waypoint_dwell": 0.5, "tracker": {"radius": 0.4, "min_hits": 3},
                  "cameras": {"rgb": {"type": "ros", "topic": "main_camera/image_raw_throttled"}}},
}


def new_project(case_key, custom=None):
    if case_key in CASES:
        c = CASES[case_key]
        slug = case_key + "_" + slugify(c["short"])
        cfg = yaml.safe_load(open(os.path.join(ROOT, c["config"])))
        econ_src = os.path.join(ROOT, c["econ"])
        p = {"slug": slug, "case": case_key, "title": c["title"]}
    else:
        c = custom_case(custom["title"], custom.get("problem", ""), custom.get("customer", ""),
                        custom.get("objects", "").split(","), custom.get("mission_type", "survey"))
        c["partner"] = custom.get("partner", "")
        slug = "custom_" + slugify(custom["title"])
        mt = custom.get("mission_type", "survey")
        cfg = json.loads(json.dumps(TEMPLATES[mt]))
        cfg.update({"case": slug, "title": custom["title"], "mission_type": mt, "home": [0, 0], "takeoff_z": 1.0,
                    "frame_id": "aruco_map", "save_frames_every": 1.0,
                    "reaction": {"alarm_classes": [], "inspect": mt == "survey", "led": [255, 0, 0], "hover": 1.5},
                    "safety": {"min_cell_voltage": 3.5, "max_time": 540, "frame": "aruco_map"}, "ui": {"enabled": True, "port": 8090},
                    "detectors": [{"type": "hsv", "label": (c["classes"] or ["object"])[0], "min_area": 200}]})
        area = cfg.get("area") or [0, 0, 4, 4]
        cfg["mock"] = {"scene": [{"name": (c["classes"] or ["object"])[0], "x": area[0] + 0.3 * (area[2] - area[0]),
                                  "y": area[1] + 0.6 * (area[3] - area[1]), "z": 1.2, "r": 0.12, "color": [0, 60, 255]}]}
        if mt == "orbit":
            t = cfg["targets"][0]
            cfg["mock"]["scene"] = [{"name": "target", "x": t[0], "y": t[1], "z": 1.0, "r": 0.15, "color": [120, 120, 120]},
                                    {"name": (c["classes"] or ["defect"])[0], "x": t[0], "y": t[1] - 0.15, "z": 1.5, "r": 0.05, "color": [0, 0, 230]}]
        econ_src = os.path.join(ROOT, "economics", "case1_fire.yaml")
        p = {"slug": slug, "case": "custom", "title": custom["title"], "case_data": c}
        json.dump(c, open(os.path.join(PROJ_DIR, slug + "_case.json"), "w"), indent=1)
    p["config"] = "config/generated/%s.yaml" % slug
    p["econ"] = "economics/generated/%s.yaml" % slug
    p["model"] = None
    p["dataset"] = None
    p["created"] = time.strftime("%Y-%m-%d %H:%M")
    cfg["case"] = slug
    if not os.path.exists(os.path.join(ROOT, p["config"])):
        yaml.safe_dump(cfg, open(os.path.join(ROOT, p["config"]), "w"), sort_keys=False)
    if not os.path.exists(os.path.join(ROOT, p["econ"])):
        e = yaml.safe_load(open(econ_src))
        if p["case"] == "custom":
            e["title"] = custom["title"]
            e["customer"] = custom.get("customer", "")
            e["purpose"] = custom.get("problem", "")
        yaml.safe_dump(e, open(os.path.join(ROOT, p["econ"]), "w"), sort_keys=False, allow_unicode=True)
    return save_project(p)


def mission_script(p):
    if p["case"] == "case3":
        return "drone/case3_swarm_agent.py"
    return case_of(p).get("script") or "drone/generic_mission.py"


def apply_model(p, model_path, conf=0.4):
    """Put the trained model as the first YOLO detector of the project config."""
    cfgp = os.path.join(ROOT, p["config"])
    cfg = yaml.safe_load(open(cfgp))
    dets = cfg.get("detectors", [])
    rel = os.path.relpath(model_path, ROOT)
    for d in dets:
        if d.get("type") == "yolo" and "weights/yolo11n" not in str(d.get("model")):
            d["model"], d["conf"] = rel, conf
            d.pop("classes", None)
            break
    else:
        dets.insert(0, {"type": "yolo", "model": rel, "conf": conf})
    cfg["detectors"] = dets
    if cfg.get("analysis") is not None:
        cfg["analysis"]["model"] = rel
    yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
    p["model"] = rel
    save_project(p)


# ============================================================================ actions
def act_prepare(j, a):
    p = load_project()
    out = os.path.join(ROOT, "datasets", p["slug"])
    rc = j.run([PY, "train/prepare_dataset.py"] + a["inputs"] + ["--out", out] + (["--val", str(a["val"])] if a.get("val") else []))
    if rc == 0:
        p["dataset"] = os.path.relpath(out, ROOT)
        save_project(p)
        rep = os.path.join(out, "dataset_report.txt")
        j.result["report"] = open(rep).read() if os.path.exists(rep) else ""
    return rc == 0


def act_train(j, a):
    p = load_project()
    data = a.get("data") or p.get("dataset")
    if not data:
        j.log("No dataset - choose one first")
        return False
    name = a.get("name") or p["slug"]
    cmd = [PY, "train/train.py", "--data", data, "--name", name, "--quality", a.get("quality", "balanced"), "--arch", a.get("arch", "yolo11")]
    if a.get("hours"):
        cmd += ["--hours", str(a["hours"])]
    if a.get("epochs"):
        cmd += ["--epochs", str(a["epochs"])]
    if a.get("imgsz"):
        cmd += ["--imgsz", str(a["imgsz"])]
    if a.get("aerial"):
        cmd.append("--aerial")
    rc = j.run(cmd)
    onnx = os.path.join(ROOT, "models", name, "best.onnx")
    if rc == 0 and os.path.exists(onnx):
        apply_model(p, onnx)
        j.log("Model applied to mission config: %s" % os.path.relpath(onnx, ROOT))
        m = os.path.join(ROOT, "models", name, "metrics.md")
        j.result["metrics"] = open(m).read() if os.path.exists(m) else ""
    return rc == 0


def act_mock(j, a):
    p = load_project()
    if p["case"] == "case3":
        rc = j.run([PY, "tests/run_swarm_mock.py", "--config", p["config"], "--scale", "20"])
        for k in range(3):
            lf = os.path.join(ROOT, "runs", "swarm_mock_agent%d.log" % k)
            if os.path.exists(lf):
                j.log("---- drone %d" % k)
                for line in open(lf).read().splitlines():
                    if any(t in line for t in ("[swarm]", "DONE", "ERROR", "error")):
                        j.log(line)
        runs = sorted(glob.glob(os.path.join(ROOT, "runs", p["slug"] + "_d0_*_mock")), key=os.path.getmtime)
        if runs:
            j.result["run"] = os.path.relpath(runs[-1], ROOT)
            j.result["report"] = os.path.relpath(os.path.join(runs[-1], "report.html"), ROOT)
        return rc == 0
    rc = j.run([PY, mission_script(p), "--config", p["config"], "--mock", "--autostart", "--time-scale", str(a.get("scale", 20))])
    runs = sorted(glob.glob(os.path.join(ROOT, "runs", p["slug"] + "_*_mock")), key=os.path.getmtime)
    if runs:
        j.result["run"] = os.path.relpath(runs[-1], ROOT)
        sj = os.path.join(runs[-1], "summary.json")
        j.result["summary"] = json.load(open(sj)) if os.path.exists(sj) else {}
        j.result["report"] = os.path.relpath(os.path.join(runs[-1], "report.html"), ROOT)
    return rc == 0


def act_econ(j, a):
    p = load_project()
    rc = j.run([PY, "economics/econ.py", p["econ"]])
    md = os.path.join(ROOT, "economics", "generated", "out", p["slug"] + ".md")
    if os.path.exists(md):
        j.result["md"] = open(md).read()
    return rc == 0


def act_docs(j, a):
    p = load_project()
    cmd = [PY, "tools/make_docs.py", "--config", p["config"], "--econ", p["econ"], "--out", os.path.join("deliverables", p["slug"])]
    if p["case"] in CASES:
        cmd += ["--case", p["case"]]
    else:
        cmd += ["--custom", os.path.join("studio", "projects", p["slug"] + "_case.json")]
    if p.get("model"):
        cmd += ["--model", os.path.dirname(p["model"])]
    run = sorted(glob.glob(os.path.join(ROOT, "runs", p["slug"] + "_*")), key=os.path.getmtime)
    run = [r for r in run if os.path.exists(os.path.join(r, "report.csv"))]
    if run:
        real = [r for r in run if not r.endswith("_mock")]
        cmd += ["--run", (real or run)[-1]]
    rc = j.run(cmd)
    j.result["folder"] = os.path.join("deliverables", p["slug"])
    return rc == 0


def act_rknn(j, a):
    p = load_project()
    if not p.get("model"):
        j.log("Train or choose a model first")
        return False
    pt = os.path.splitext(p["model"])[0] + ".pt"
    rc = j.run([PY, "setup/convert_rknn.py", pt, "--imgsz", str(a.get("imgsz", 640))])
    rk = os.path.splitext(pt)[0] + "_rknn_model"
    if rc == 0 and a.get("use") and os.path.isdir(os.path.join(ROOT, rk)):
        apply_model(p, os.path.join(ROOT, rk))
        j.log("Mission now uses the NPU model %s" % rk)
    return rc == 0


def act_autolabel(j, a):
    cmd = [PY, "train/autolabel.py", a["folder"]]
    if a.get("method") == "model":
        cmd += ["--model", a["model"]]
    else:
        cmd += ["--" + a.get("method", "hsv"), "--label", a.get("label") or "object"]
    return j.run(cmd) == 0


def act_extract(j, a):
    return j.run([PY, "train/extract_frames.py"] + a["inputs"] + ["--out", a["out"], "--every", str(a.get("every", 0.5))]) == 0


def act_synth(j, a):
    return j.run([PY, "train/make_synthetic.py", "paste", "--objects", a["objects"], "--backgrounds", a["backgrounds"],
                  "--out", a["out"], "--n", str(a.get("n", 1000))]) == 0


def act_selftest(j, a):
    return j.run([PY, "tests/run_all_tests.py", "--no-train"]) == 0


def act_planner(j, a):
    p = load_project()
    return j.run([PY, "drone/case3_planner.py", "--config", p["config"], "--port", "8000"]) == 0


def act_autopilot(j, a):
    """Everything, autonomously."""
    p = load_project()
    steps = []
    if a.get("dataset"):
        steps.append(("Prepare dataset", lambda: act_prepare(j, {"inputs": [a["dataset"]]})))
        steps.append(("Train model", lambda: act_train(j, {"quality": a.get("quality", "balanced"), "hours": a.get("hours"),
                                                           "aerial": a.get("aerial"), "arch": a.get("arch", "yolo11")})))
        if a.get("rknn"):
            steps.append(("Convert to RKNN (NPU)", lambda: act_rknn(j, {"use": False})))
    steps += [("Simulation test of the mission", lambda: act_mock(j, {})),
              ("Economic efficiency", lambda: act_econ(j, {})),
              ("Documents + presentation + GitHub repo", lambda: act_docs(j, {}))]
    j.result["steps"] = [s[0] for s in steps]
    for i, (name, fn) in enumerate(steps):
        j.result["step"] = i
        j.log("=" * 60)
        j.log("STEP %d/%d: %s" % (i + 1, len(steps), name))
        j.log("=" * 60)
        if not fn():
            j.log("STEP FAILED: %s" % name)
            if name.startswith(("Prepare", "Train")):
                return False
    j.result["step"] = len(steps)
    j.result["folder"] = os.path.join("deliverables", p["slug"])
    j.log("AUTOPILOT FINISHED -> deliverables/%s" % p["slug"])
    return True


ACTIONS = {"prepare": ("Prepare dataset", act_prepare), "train": ("Train model", act_train), "mock": ("Simulation test", act_mock),
           "econ": ("Economics", act_econ), "docs": ("Generate documents", act_docs), "rknn": ("Convert to RKNN", act_rknn),
           "autolabel": ("Auto-label", act_autolabel), "extract": ("Extract frames", act_extract), "synth": ("Synthetic data", act_synth),
           "selftest": ("Self-test", act_selftest), "thermal_local": ("Thermal camera probe (this computer)", lambda j, a: j.run([PY, "tools/thermal_probe.py"]) == 0), "planner": ("Swarm planner", act_planner), "autopilot": ("AUTOPILOT", act_autopilot)}


def open_terminal(cmd):
    """Open a visible terminal window running cmd in ROOT (for steps that need a password)."""
    if WIN:
        subprocess.Popen('start "BRICS" cmd /k "cd /d "%s" && %s"' % (ROOT, cmd), shell=True)
    elif sys.platform == "darwin":
        sh = "cd %s && %s" % (shlex.quote(ROOT), cmd)
        script = 'tell application "Terminal" to do script "%s"' % sh.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.Popen(["osascript", "-e", script, "-e", 'tell application "Terminal" to activate'])
    else:
        subprocess.Popen(["x-terminal-emulator", "-e", "bash", "-c", "cd %s && %s; exec bash" % (shlex.quote(ROOT), cmd)])


def terminal_commands(pr, what, ip="10.42.0.1", drone_id=0, folder="", classes=None, extra=None):
    extra = extra or {}
    ip = check_host(ip)
    drone_id = int(drone_id)
    extra = dict(extra)
    for k in ("size", "dx", "dy"):
        if k in extra:
            extra[k] = float(extra[k])
    for k in ("nx", "ny", "first", "device"):
        if k in extra:
            extra[k] = int(extra[k])
    q = (lambda x: '"%s"' % str(x).replace('"', '')) if WIN else shlex.quote
    py = q(PY)
    return {
        "deploy": "%s setup/deploy_to_drone.py --ip %s" % (py, ip),
        # non-interactive ssh does not read ~/.bashrc -> load ROS + the TECHNIC workspace explicitly (rospy, technic.srv)
        "run_drone": "ssh -t orangepi@%s \"source /opt/ros/noetic/setup.bash; source ~/technic_ws/devel/setup.bash; cd ~/brics_toolkit && python3 %s --config %s %s\"" % (
            ip, mission_script(pr), pr["config"], ("--id %s" % drone_id) if pr["case"] == "case3" else ""),
        "fetch_runs": "%s setup/deploy_to_drone.py --ip %s --fetch" % (py, ip),
        "ssh": "ssh orangepi@%s" % ip,
        "label": "%s train/label_tool.py %s %s" % (py, q(folder), ("--classes " + " ".join(q(c) for c in classes)) if classes else ""),
        "colima": "colima start" if not WIN else "echo Start Docker Desktop from the Start menu",
        "thermal_probe": "ssh -t orangepi@%s \"cd ~/brics_toolkit && python3 tools/thermal_probe.py && python3 tools/thermal_probe.py --snap %s\"" % (
            ip, extra.get("device", 1)),
        "aruco_map": ("ssh -t orangepi@%s \"cd ~/technic_ws/src/technic/aruco_pose/map && rosrun aruco_pose genmap.py %s %s %s %s %s %s -o brics_map.txt "
                      "&& echo && echo Map written: brics_map.txt - set it in aruco.launch: map=brics_map.txt, then: sudo systemctl restart technic\"") % (
            ip, extra.get("size", 0.33), extra.get("nx", 10), extra.get("ny", 10), extra.get("dx", 0.85), extra.get("dy", 0.85), extra.get("first", 0)),
    }[what]


def open_path(f):
    if WIN:
        os.startfile(f)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", f])


def md_to_html(md):
    try:
        import markdown
        return markdown.markdown(md, extensions=["tables", "fenced_code"])
    except Exception:
        return "<pre>%s</pre>" % md


def list_models():
    out = []
    for d in sorted(glob.glob(os.path.join(ROOT, "models", "*"))):
        if os.path.basename(d).startswith("_selftest"):
            continue
        files = [f for f in ("best.onnx", "best.pt") if os.path.exists(os.path.join(d, f))]
        if not files:
            continue
        m = os.path.join(d, "metrics.md")
        out.append({"name": os.path.basename(d), "onnx": os.path.relpath(os.path.join(d, "best.onnx"), ROOT) if "best.onnx" in files else None,
                    "rknn": os.path.isdir(os.path.join(d, "best_rknn_model")),
                    "metrics": md_to_html(open(m).read()) if os.path.exists(m) else ""})
    return out


# ============================================================================ HTTP
def inside_root(rel):
    """Absolute path of `rel` if it is inside the toolkit folder, else None (no ../ escapes)."""
    f = os.path.realpath(os.path.join(ROOT, str(rel or "")))
    return f if f == ROOT or f.startswith(ROOT + os.sep) else None


NEEDS_PROJECT = ("/api/config", "/api/econ", "/api/deliverables", "/api/config/form", "/api/model/use", "/api/terminal")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _local_request(self):
        """
        Only accept requests made by the studio page itself: Host must be localhost (blocks DNS rebinding) and
        POSTs must be JSON from our own origin (a random web page cannot drive the studio = no CSRF).
        """
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in ("localhost", "127.0.0.1", "::1"):
            return False
        if self.command == "POST":
            if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
                return False
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).hostname not in ("localhost", "127.0.0.1", "::1"):
                return False
        return True

    def do_GET(self):
        self._guarded(self._get)

    def do_POST(self):
        self._guarded(self._post)

    def _guarded(self, fn):
        if not self._local_request():
            return self._send(403, {"error": "forbidden"})
        if urlparse(self.path).path in NEEDS_PROJECT and not load_project():
            return self._send(409, {"error": "choose a problem statement first"})
        try:
            fn()
        except Exception as e:                       # never kill the connection without an answer
            import traceback
            traceback.print_exc()
            try:
                self._send(500, {"error": "%s: %s" % (type(e).__name__, e)})
            except Exception:
                pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, default=str)
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def _get(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        p = u.path
        if p == "/":
            return self._send(200, open(os.path.join(ROOT, "studio", "index.html"), "rb").read(), "text/html; charset=utf-8")
        if p == "/api/state":
            pr = load_project()
            projects = list_projects()
            cases = {k: {"title": v["title"], "short": v["short"], "partner": v["partner"], "problem": v["problem"],
                         "mission_type": v["mission_type"], "classes": v["classes"]} for k, v in CASES.items()}
            info = None
            if pr:
                c = case_of(pr)
                info = {"title": c["title"], "problem": c["problem"], "solution": c["solution"], "classes": c.get("classes", []),
                        "mission_type": c.get("mission_type"), "script": mission_script(pr)}
            return self._send(200, {"project": pr, "case": info, "projects": projects, "cases": cases, "models": list_models(),
                                    "root": ROOT})
        if p == "/api/config":
            pr = load_project()
            txt = open(os.path.join(ROOT, pr["config"])).read()
            return self._send(200, {"yaml": txt, "path": pr["config"], "cfg": yaml.safe_load(txt)})
        if p == "/api/econ":
            pr = load_project()
            return self._send(200, {"yaml": open(os.path.join(ROOT, pr["econ"])).read(), "path": pr["econ"]})
        if p == "/api/jobs":
            with LOCK:
                js = [j.to_dict(tail=3) for j in sorted(JOBS.values(), key=lambda x: -x.started)][:15]
            return self._send(200, js)
        if p.startswith("/api/job/"):
            j = JOBS.get(p.split("/")[-1])
            return self._send(200, j.to_dict()) if j else self._send(404, {"error": "no job"})
        if p == "/api/ls":
            path = os.path.expanduser(q.get("path") or "~")
            if not os.path.isdir(path):
                path = os.path.dirname(path)
            items = []
            try:
                for n in sorted(os.listdir(path), key=str.lower):
                    if n.startswith("."):
                        continue
                    f = os.path.join(path, n)
                    items.append({"name": n, "dir": os.path.isdir(f), "path": f})
            except OSError:
                pass
            return self._send(200, {"path": path, "parent": os.path.dirname(path), "items": items[:500]})
        if p == "/api/deliverables":
            pr = load_project()
            d = os.path.join(ROOT, "deliverables", pr["slug"])
            files = sorted(os.listdir(d)) if os.path.isdir(d) else []
            return self._send(200, {"folder": d, "files": files})
        if p == "/api/md":
            f = inside_root(q.get("path", ""))
            return self._send(200, {"html": md_to_html(open(f).read()) if f and os.path.isfile(f) else ""})
        if p == "/file":
            f = inside_root(unquote(q.get("path", "")))
            if not f or not os.path.isfile(f):
                return self._send(404, b"not found", "text/plain")
            ext = os.path.splitext(f)[1].lower()
            ct = {".html": "text/html; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".pdf": "application/pdf",
                  ".md": "text/plain; charset=utf-8", ".csv": "text/plain; charset=utf-8", ".svg": "image/svg+xml"}.get(ext, "application/octet-stream")
            return self._send(200, open(f, "rb").read(), ct)
        return self._send(404, {"error": "not found"})

    def _post(self):
        p = urlparse(self.path).path
        b = self._body()
        if not isinstance(b, dict):
            return self._send(400, {"error": "JSON object expected"})
        if p == "/api/project/new":
            pr = new_project(b.get("case"), b.get("custom"))
            return self._send(200, pr)
        if p == "/api/project/open":
            pr = load_project(b.get("slug"))
            if not pr:
                return self._send(404, {"error": "no such project"})
            save_project(pr)
            return self._send(200, pr)
        if p in ("/api/config", "/api/econ"):
            pr = load_project()
            try:
                yaml.safe_load(b["yaml"])
            except Exception as e:
                return self._send(400, {"error": "YAML error: %s" % e})
            _write(os.path.join(ROOT, pr["config" if p == "/api/config" else "econ"]), b["yaml"])
            return self._send(200, {"ok": True})
        if p == "/api/config/form":
            pr = load_project()
            cfgp = os.path.join(ROOT, pr["config"])
            cfg = yaml.safe_load(open(cfgp))
            for k, v in b.items():
                cur = cfg
                ks = k.split(".")
                for kk in ks[:-1]:
                    cur = cur.setdefault(kk, {})
                cur[ks[-1]] = v
            yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
            return self._send(200, {"ok": True})
        if p == "/api/model/use":
            pr = load_project()
            apply_model(pr, os.path.join(ROOT, b["path"]), b.get("conf", 0.4))
            return self._send(200, {"ok": True})
        if p == "/api/run":
            act = b.pop("action")
            if act not in ACTIONS:
                return self._send(400, {"error": "unknown action"})
            title, fn = ACTIONS[act]
            j = start_job(title, lambda job: fn(job, b))
            return self._send(200, {"job": j.id})
        if p == "/api/job/stop":
            j = JOBS.get(b["id"])
            if j and j.proc and j.proc.poll() is None:
                j.proc.terminate()
                j.log("(stopped by user)")
            return self._send(200, {"ok": True})
        if p == "/api/terminal":
            pr = load_project()
            what = b["what"]
            try:
                cmd = terminal_commands(pr, what, b.get("ip") or "10.42.0.1", b.get("id", 0), b.get("folder", ""), b.get("classes"))
            except (KeyError, ValueError, TypeError) as e:
                return self._send(400, {"error": str(e)})
            open_terminal(cmd)
            return self._send(200, {"ok": True, "cmd": cmd})
        if p == "/api/open":
            f = inside_root(b.get("path", ""))
            if not f or not os.path.exists(f):
                return self._send(404, {"error": "not found"})
            open_path(f)
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "not found"})


def main():
    port = int(os.environ.get("STUDIO_PORT", 7777))
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    url = "http://localhost:%d" % port
    print("BRICS Mission Studio running at %s  (Ctrl+C to quit)" % url)
    if not os.environ.get("STUDIO_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
