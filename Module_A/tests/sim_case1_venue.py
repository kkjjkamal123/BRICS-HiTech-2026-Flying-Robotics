#!/usr/bin/env python3
"""Rehearsal of the final Case 1 mission in the simulator, with the venue layout (ONE heat source on the left,
ONE flame lamp on the right) and deliberately WRONG camera calibrations, as on the real drone.

Pass = every scenario maps exactly one `fire` and one `flame`, each within 0.5 m of the truth, and nothing else.
    python tests/sim_case1_venue.py            (about 1 minute)
"""
import glob, json, math, os, subprocess, sys, tempfile
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PY = sys.executable
TRUTH = {"fire": (-2.0, 0.1), "flame": (2.3, 0.6)}
SCENARIOS = [
    ("perfect cameras", {}),
    ("thermal lens 30 % narrower than assumed", {"thermal": {"focal_error": 0.7}}),
    ("thermal lens 40 % wider than assumed", {"thermal": {"focal_error": 1.4}}),
    ("thermal camera mounted upside down", {"thermal": {"flipped": True}}),
    ("main camera upside down + thermal lens wrong", {"rgb": {"flipped": True}, "thermal": {"focal_error": 0.75}}),
    ("both cameras upside down, both lenses wrong", {"rgb": {"flipped": True, "focal_error": 1.25},
                                                    "thermal": {"flipped": True, "focal_error": 0.8}}),
    ("perfect cameras, jittery position (8 cm, 3 deg)", {"rgb": {"pose_noise": 0.08}, "thermal": {"pose_noise": 0.08}}),
    ("jittery position + thermal upside down, lens wrong", {"rgb": {"pose_noise": 0.08},
                                                           "thermal": {"pose_noise": 0.08, "flipped": True, "focal_error": 0.75}}),
]


def run(name, err, runs_dir):
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "case1_fire.yaml")))
    cfg.setdefault("mock", {})["camera_error"] = err
    cfg["save_frames_every"] = 0
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as f:
        yaml.safe_dump(cfg, f)
    env = dict(os.environ, BRICS_RUNS=runs_dir)
    p = subprocess.run([PY, os.path.join(ROOT, "drone", "case1_fire.py"), "--config", path, "--mock", "--autostart",
                        "--time-scale", "30", "--no-ui"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    os.remove(path)
    run_dir = sorted(glob.glob(os.path.join(runs_dir, "case1_fire_*")))[-1]
    objs = json.load(open(os.path.join(run_dir, "objects.json")))
    summary = json.load(open(os.path.join(run_dir, "summary.json")))
    ok, parts = summary["result"] == "completed", []
    names = sorted(o["name"] for o in objs)
    if names != ["fire", "flame"]:
        ok = False
    for o in objs:
        t = TRUTH.get(o["name"])
        e = math.hypot(o["x"] - t[0], o["y"] - t[1]) if t else float("nan")
        if not t or e > 0.5:
            ok = False
        temp = " %.0fC" % o["temp_c"] if o.get("temp_c") is not None else ""
        parts.append("%s%s (%.2f, %.2f) err %.2f m, %d views" % (o["name"], temp, o["x"], o["y"], e, o["hits"]))
    alarms = p.stdout.count("[ALARM] IGNITION SOURCE") + p.stderr.count("[ALARM] IGNITION SOURCE")
    if alarms != 2:
        ok = False
    print("%s  %-46s objects %d, alarms %d, %s | %s" % ("PASS" if ok else "FAIL", name, len(objs), alarms, summary["result"], "; ".join(parts)))
    return ok


def main():
    runs_dir = tempfile.mkdtemp(prefix="brics_sim_")
    results = [run(n, e, runs_dir) for n, e in SCENARIOS]
    print("== %d of %d scenarios passed" % (sum(results), len(results)))
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
