#!/usr/bin/env python3
"""
Full self-test, works offline on macOS / Windows / Linux:   python tests/run_all_tests.py [--no-train] [--quick]

  --no-train   skip the 3-epoch training run (predict is then checked with an existing model, if any)
  --quick      only code + flight-safety unit tests + mock missions (about 2 min)
Every check has a timeout; failing checks write their output to a log file in the temp folder.
"""
import argparse
import glob
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PY = sys.executable
TMP = tempfile.gettempdir()
T = os.path.join("datasets", "_selftest")
results = []

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--no-train", action="store_true", help="skip model training")
ap.add_argument("--quick", action="store_true", help="code, unit tests and mock missions only")
ap.add_argument("--timeout", type=float, default=900, help="per-check timeout in seconds")
A = ap.parse_args()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def check(name, cmd, pattern=None, count=None):
    """PASS if the command exits with 0 and its output matches `pattern` (at least `count` times)."""
    t0 = time.time()
    rc = -1
    try:
        r = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=A.timeout)
        out, rc = r.stdout.decode("utf-8", "replace"), r.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace") + "\nTIMEOUT after %ds" % A.timeout
    except Exception as e:
        out = "EXCEPTION %s" % e
    hits = len(re.findall(pattern, out)) if pattern else 1
    ok = rc == 0 and hits >= (count or 1)
    results.append(ok)
    print("  %s  %s  (%.0f s)" % ("PASS" if ok else "FAIL", name, time.time() - t0))
    sys.stdout.flush()
    if not ok:
        log = os.path.join(TMP, "brics_fail_%d.log" % len(results))
        with open(log, "w") as f:
            f.write("$ %s\n(exit code %s, %d matches of %r)\n%s" % (" ".join(cmd), rc, hits, pattern, out))
        print("        log: %s" % log)


def mission(script, cfg):
    return [PY, script, "--config", cfg, "--mock", "--autostart", "--time-scale", "30", "--no-ui"]


print("== code")
check("python compile", [PY, "-m", "compileall", "-q", "common", "drone", "analysis", "train", "economics", "tools", "studio", "tests"])
check("flight-safety unit tests", [PY, "tests/test_flight_safety.py"], r"ALL \d+ TESTS PASSED")
print("== missions (mock drone + mock camera)")
check("case1 fire: 2 fires", mission("drone/case1_fire.py", "config/case1_fire.yaml"), r"\[ALARM\] IGNITION SOURCE", 2)
check("case1 venue rehearsal: 1 fire + 1 flame under 8 camera / position errors", [PY, "tests/sim_case1_venue.py"], r"== 8 of 8 scenarios passed")
check("case2 weeds: count 7", mission("drone/case2_weeds.py", "config/case2_weeds.yaml"), r"final count: \{'plant': 7\}")
check("case4 powerline: 2 defects", mission("drone/case4_powerline.py", "config/case4_powerline.yaml"), r"\[DEFECT\] #\d", 2)
check("case3 swarm: 1 alert", [PY, "tests/run_swarm_mock.py", "--scale", "20", "--port", str(free_port()), "--no-ui"],
      r"alerts: \[\{'id': 1")
check("cube params audit (original backup = DO NOT FLY)", [PY, "-c", "import sys; sys.argv=['x', '../cube_params_backup_original.csv'];"
      "sys.path.insert(0, 'tools'); import param_audit; rc = param_audit.main(sys.argv[1:]); sys.exit(0 if rc == 1 else 1)"]
      if os.path.exists(os.path.join(ROOT, "..", "cube_params_backup_original.csv")) else [PY, "-c", "print('no backup file - skipped')"])
if A.quick:
    print("== result: %d passed, %d failed" % (sum(results), len(results) - sum(results)))
    sys.exit(0 if all(results) else 1)

print("== datasets (all formats)")
for f in ("yolo", "coco", "voc", "csv", "classify"):
    if not os.path.isdir(os.path.join(ROOT, T, "raw_" + f)):
        subprocess.run([PY, "train/make_synthetic.py", "shapes", "--out", os.path.join(T, "raw_" + f), "--n", "120", "--format", f],
                       cwd=ROOT, timeout=A.timeout)
    check("prepare " + f, [PY, "train/prepare_dataset.py", os.path.join(T, "raw_" + f), "--out", os.path.join(T, "prep_" + f)], "NEXT")
print("== training + export (short)")
model = "models/_selftest_quick/best.onnx"
if A.no_train:
    if not os.path.exists(os.path.join(ROOT, model)):
        model = "weights/yolo11n.onnx"
    print("  SKIP  train detect + onnx (--no-train) - predict uses %s" % model)
else:
    check("train detect + onnx", [PY, "train/train.py", "--data", os.path.join(T, "prep_yolo"), "--name", "_selftest_quick",
                                  "--quality", "fast", "--epochs", "3", "--imgsz", "320"], r"ONNX matches|self-check")
if os.path.exists(os.path.join(ROOT, model)):
    check("predict onnx", [PY, "train/predict.py", "--model", model, "--source", os.path.join(T, "prep_yolo", "images", "val")], "ms/frame")
else:
    print("  SKIP  predict onnx (no model)")
al = os.path.join(TMP, "brics_al")
shutil.rmtree(al, ignore_errors=True)
os.makedirs(al)
for f in glob.glob(os.path.join(ROOT, T, "prep_yolo", "images", "val", "*.jpg")):
    shutil.copy2(f, al)
check("autolabel hsv", [PY, "train/autolabel.py", al, "--hsv", "--label", "fire"], "auto-labelled")
check("weed_map images", [PY, "analysis/weed_map.py", "--images", os.path.join(T, "prep_yolo", "images", "val"), "--exg",
                          "--out", os.path.join(TMP, "brics_wm")], "TOTAL")
print("== economics")
check("econ 4 cases", [PY, "economics/econ.py"] + ["economics/%s.yaml" % c for c in ("case1_fire", "case2_weeds", "case3_swarm", "case4_powerline")],
      "case4_powerline: NPV")
print("== documents")
check("make_docs case4", [PY, "tools/make_docs.py", "--case", "case4", "--no-github", "--out", os.path.join(TMP, "brics_docs_test")], "DONE")
print("== result: %d passed, %d failed" % (sum(results), len(results) - sum(results)))
sys.exit(0 if all(results) else 1)
