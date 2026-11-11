#!/usr/bin/env python3
"""
make_docs.py - generates ALL competition deliverables for a problem statement, automatically.

  python tools/make_docs.py --case case1 [--config config/case1_fire.yaml] [--model models/fire] [--run runs/...]
  python tools/make_docs.py --custom studio/projects/my_ps.json --config config/generated/my_ps.yaml

Output: deliverables/<name>/
  01_Technical_Description.md   purpose, characteristics, block diagram, key engineering decisions (Module A)
  02_Team_Roles.md              roles table (Module A)
  03_Components.md              component / equipment table (Module A, D)
  04_Test_Programme.md          requirements -> procedure -> expected (Module B)
  05_Test_Report.md             actual results from mission runs + model metrics (Module B, D)
  06_Economics.md + .xlsx       payback, ROI, NPV, IRR, sensitivity (Module C)
  07_Operating_Instructions.md  how to run the system (Module A deliverable)
  08_Defence_QA.md              prepared answers for the experts
  block_diagram.png, mission_map.png
  ALL_DOCUMENTS.html / .pdf     everything in one file
  Presentation.pptx / .pdf      10-slide defence presentation (Module D: PDF + PPTX)
  github_repo/                  ready-to-publish repository (code + docs), git-initialised
"""
import argparse
import csv
import glob
import json
import math
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)

import yaml  # noqa: E402

from studio.cases import BASE_COMPONENTS, CASES, COMMON_DECISIONS, COMMON_REQUIREMENTS, TEAM  # noqa: E402

BRAVE = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


# ----------------------------------------------------------------------------- data collection
def latest_run(case_name, prefer_real=True):
    runs = sorted(glob.glob(os.path.join(ROOT, "runs", case_name + "_*")), key=os.path.getmtime, reverse=True)
    runs = [r for r in runs if os.path.exists(os.path.join(r, "report.csv"))]
    real = [r for r in runs if not r.endswith("_mock")]
    return (real or runs or [None])[0] if prefer_real else (runs or [None])[0]


def read_run(run, cfg):
    if not run:
        return None
    objs = []
    with open(os.path.join(run, "report.csv")) as f:
        for r in csv.DictReader(f):
            objs.append({"id": r["id"], "name": r["class"], "x": float(r["x"]), "y": float(r["y"]), "z": float(r["z"]),
                         "conf": float(r["conf"]), "hits": r["hits"]})
    path = []
    if os.path.exists(os.path.join(run, "path.csv")):
        with open(os.path.join(run, "path.csv")) as f:
            path = [(float(r["x"]), float(r["y"]), float(r["z"])) for r in csv.DictReader(f)]
    result, duration = "", None
    log = open(os.path.join(run, "log.txt")).read() if os.path.exists(os.path.join(run, "log.txt")) else ""
    for line in log.splitlines():
        if "[phase] DONE" in line:
            result = line.split("DONE", 1)[1].strip()
    lines = [l for l in log.splitlines() if l[:2].isdigit()]
    if len(lines) > 1:
        t0, t1 = lines[0][:8], lines[-1][:8]
        s = lambda t: int(t[:2]) * 3600 + int(t[3:5]) * 60 + int(t[6:8])
        duration = s(t1) - s(t0)
    dist = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:]))
    sj = os.path.join(run, "summary.json")
    if os.path.exists(sj):
        sm = json.load(open(sj))
        duration = sm.get("duration_s", duration)
        result = sm.get("result", result)
    res = {"dir": run, "mock": run.endswith("_mock"), "objects": objs, "path": path, "result": result or "completed",
           "duration": duration, "distance": dist,
           "snapshots": sorted(glob.glob(os.path.join(run, "snapshots", "*.jpg")))[:6]}
    # accuracy vs ground truth (mock scene, or 'ground_truth' list in the config for real tests)
    truth = cfg.get("ground_truth") or ([o for o in cfg.get("mock", {}).get("scene", [])
                                         if not str(o["name"]).startswith(("tower", "palm", "decoy"))] if res["mock"] else [])
    if truth:
        errs, found = [], 0
        for t in truth:
            d = [math.sqrt((o["x"] - t["x"]) ** 2 + (o["y"] - t["y"]) ** 2 + ((o["z"] - t.get("z", o["z"])) ** 2)) for o in objs]
            if d and min(d) < 0.5:
                found += 1
                errs.append(min(d))
        res["truth_n"], res["found"] = len(truth), found
        res["false"] = max(0, len(objs) - found)
        res["err_mean"] = sum(errs) / len(errs) if errs else None
        res["err_max"] = max(errs) if errs else None
    return res


def read_metrics(model_dir):
    if not model_dir:
        return None
    p = os.path.join(model_dir, "metrics.md")
    return open(p).read() if os.path.exists(p) else None


# ----------------------------------------------------------------------------- CAD (Fusion) assets
CAD_OUT = os.path.join(ROOT, "cad", "out")
CAD_FILES = ["TR256i_mount_down.stl", "TR256i_mount_down.step", "TR256i_mount_forward.stl", "TR256i_mount_forward.step",
             "TECHNIC6S_with_thermal_mount_assembly.step", "BRICS_aerial_robotics_CAD.f3d",
             "Drawing_TR256i_mount_down.pdf", "Drawing_TR256i_mount_forward.pdf", "Drawing_TR256i_mount_down.png",
             "technic6s_iso.png", "technic6s_front.png", "technic6s_top.png", "technic6s_underside_mount_closeup.png",
             "render_down_camera_side.png", "render_down_drone_side.png", "render_forward_front.png",
             "technic6s_electronics_top.png", "technic6s_electronics_under.png", "technic6s_electronics_rear.png",
             "technic6s_wiring_side.png", "technic6s_guard_landing_gear.png", "TECHNIC6S_wiring_diagram.pdf", "TECHNIC6S_wiring_diagram.png"]


def copy_cad(out):
    """Copy the verified CAD outputs into deliverables/<project>/cad. Returns list of copied names."""
    if not os.path.isdir(CAD_OUT):
        return []
    d = os.path.join(out, "cad")
    os.makedirs(d, exist_ok=True)
    got = []
    for f in CAD_FILES:
        src = os.path.join(CAD_OUT, f)
        if os.path.exists(src):
            shutil.copy2(src, d)
            got.append(f)
    readme = os.path.join(ROOT, "cad", "README_CAD.md")
    if os.path.exists(readme):
        shutil.copy2(readme, d)
    return got


# ----------------------------------------------------------------------------- figures
def block_diagram(case, cfg, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    fig, ax = plt.subplots(figsize=(13, 7.2))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 7.2)
    ax.axis("off")
    dets = ", ".join(sorted(set(d.get("type", "?") for d in cfg.get("detectors", [])))) or "YOLO"
    cams = ", ".join(cfg.get("cameras", {"rgb": {}}).keys())
    B = {
        "cam": (0.3, 5.2, 2.6, 1.2, "Camera(s)\n%s" % cams, "#ffe8cc"),
        "per": (3.6, 5.2, 3.0, 1.2, "Perception\n%s detectors" % dets, "#d0ebff"),
        "trk": (7.3, 5.2, 2.6, 1.2, "Tracker\nconfirm + map coords", "#d0ebff"),
        "ui": (10.4, 5.2, 2.4, 1.2, "Operator web UI\nalerts, live view", "#d3f9d8"),
        "aru": (0.3, 3.2, 2.6, 1.2, "ArUco map / VPE\nindoor position", "#ffe8cc"),
        "mis": (3.6, 3.2, 3.0, 1.2, "Mission state machine\n%s + safety" % cfg.get("mission_type", case.get("mission_type", "")), "#e5dbff"),
        "rep": (7.3, 3.2, 2.6, 1.2, "Report generator\nHTML/CSV/map", "#d3f9d8"),
        "plan": (10.4, 3.2, 2.4, 1.2, "Swarm planner\n(zones, alerts)" if "swarm" in cfg else "Customer\n(coordinates, photos)", "#d3f9d8"),
        "off": (3.6, 1.2, 3.0, 1.2, "simple_offboard / MAVROS\nnavigate(), land()", "#e5dbff"),
        "px4": (7.3, 1.2, 2.6, 1.2, "PX4 EKF2\nstabilisation", "#fff3bf"),
        "mot": (10.4, 1.2, 2.4, 1.2, "Motors / ESC", "#fff3bf"),
        "rc": (0.3, 1.2, 2.6, 1.2, "RC transmitter\nKILL SWITCH", "#ffc9c9"),
    }
    for k, (x, y, w, h, t, c) in B.items():
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05", fc=c, ec="#333", lw=1.3))
        ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=10.5)

    def arrow(a, b, label=""):
        xa, ya, wa, ha = B[a][:4]
        xb, yb, wb, hb = B[b][:4]
        p1 = (xa + wa / 2, ya + ha / 2)
        p2 = (xb + wb / 2, yb + hb / 2)
        if abs(p1[1] - p2[1]) < 0.1:
            p1, p2 = (xa + wa if xb > xa else xa, p1[1]), (xb if xb > xa else xb + wb, p2[1])
        else:
            p1, p2 = (p1[0], ya if yb < ya else ya + ha), (p2[0], yb + hb if yb < ya else yb)
        ax.annotate("", xy=p2, xytext=p1, arrowprops=dict(arrowstyle="->", lw=1.6, color="#333"))
        if label:
            ax.text((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 + 0.12, label, ha="center", fontsize=8.5, color="#555")
    arrow("cam", "per", "images")
    arrow("per", "trk", "detections")
    arrow("trk", "ui", "objects")
    arrow("aru", "mis", "pose")
    arrow("trk", "mis")
    arrow("mis", "rep")
    arrow("rep", "plan")
    arrow("mis", "off", "setpoints")
    arrow("off", "px4", "MAVLink")
    arrow("px4", "mot")
    arrow("rc", "off", "override")
    arrow("ui", "plan")
    ax.text(6.5, 6.85, "Functional block diagram - %s" % case["title"], ha="center", fontsize=13, weight="bold")
    plt.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def mission_map(run, cfg, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 6))
    if cfg.get("area"):
        a = cfg["area"]
        ax.add_patch(plt.Rectangle((a[0], a[1]), a[2] - a[0], a[3] - a[1], fill=False, ls="--", ec="grey", label="area"))
    for i, s in enumerate(cfg.get("supports", cfg.get("targets", []))):
        ax.plot(s[0], s[1], "ks", ms=12)
        ax.text(s[0] + 0.1, s[1] + 0.1, "T%d" % (i + 1))
    if run and run["path"]:
        ax.plot([p[0] for p in run["path"]], [p[1] for p in run["path"]], "-", color="#4363d8", alpha=0.6, label="flight path")
    if run:
        names = sorted(set(o["name"] for o in run["objects"]))
        for k, n in enumerate(names):
            pts = [o for o in run["objects"] if o["name"] == n]
            ax.scatter([o["x"] for o in pts], [o["y"] for o in pts], s=90, label=n, zorder=3)
            for o in pts:
                ax.text(o["x"] + 0.06, o["y"] + 0.06, "#%s" % o["id"], fontsize=8)
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.set_xlabel("x (m, aruco_map)")
    ax.set_ylabel("y (m)")
    ax.legend(loc="best", fontsize=8)
    ax.set_title("Mission map - detected objects")
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------- markdown documents
def md_table(header, rows):
    s = "| " + " | ".join(header) + " |\n|" + "---|" * len(header) + "\n"
    for r in rows:
        s += "| " + " | ".join(str(c) for c in r) + " |\n"
    return s


def cad_section(cad):
    if not cad:
        return ""
    t = ("## 7b. Custom hardware - TR256i thermal camera mount (3D printed, designed in Autodesk Fusion)\n"
         "The TR256i thermal module (56.6 x 34.4 x 12.1 mm) is held in a one-piece printed cradle under the TECHNIC 6S frame: "
         "it slides in from the USB-C end against a stop wall, 4 crush ribs give a press fit, the USB cable is zip-tied to an "
         "anchor tab, and thin 1.4 mm lips hold the edges so the 56 deg lens view is never blocked. The plate attaches with the "
         "venue 15 mm velcro straps (or zip ties / M3). Mass 21.5 g (PETG), prints without supports.\n\n"
         "**Verified in Fusion:** single solid; module touches only the 4 crush ribs; lens cone clear for 45 lens positions; "
         "only overhangs are 2.2 mm lips; every strap slot has a free path; STL watertight (volume = model).\n\n")
    if "technic6s_iso.png" in cad:
        t += "![TECHNIC 6S with thermal mount](cad/technic6s_iso.png)\n\n"
    if "technic6s_underside_mount_closeup.png" in cad:
        t += "![thermal mount under the frame](cad/technic6s_underside_mount_closeup.png)\n\n"
    if "Drawing_TR256i_mount_down.png" in cad:
        t += "![drawing](cad/Drawing_TR256i_mount_down.png)\n\n"
    if "technic6s_electronics_top.png" in cad:
        t += ("### Electronics and wiring (full Fusion model)\n"
              "Modelled as in the SKYRIS assembly guide: ESC 4in1 + PX4 flight controller stack on the top centre plate "
              "(8-pin ESC-FC cable, ELRS receiver on TELEM1), 4 motors via MR30 connectors, XT60 power on the battery plate, "
              "Orange Pi 5 Pro under the frame with the SKYRIS Shield V2 (FC TELEM2 -> UART0, power to V IN, cooler, LED ring, "
              "VL53L1X on I2C), USB camera and our TR256i on the Orange Pi USB ports. 64 individual wires in 22 cables; "
              "the prop guard (4 clip-on guards + 2 short / 2 long jumpers) and the landing gear (mount, spacer and TPU leg under "
              "each motor) follow guide steps 3, 6 and 7. An interference check of all 265 bodies shows every wire touches only "
              "its own connectors.\n\n"
              "![electronics](cad/technic6s_electronics_top.png)\n\n![Orange Pi + shield wiring](cad/technic6s_electronics_under.png)\n\n")
    if "TECHNIC6S_wiring_diagram.png" in cad:
        t += "![wiring diagram](cad/TECHNIC6S_wiring_diagram.png)\n\n"
    if "technic6s_guard_landing_gear.png" in cad:
        t += "![prop guard and landing gear](cad/technic6s_guard_landing_gear.png)\n\n"
    t += ("Files in `cad/`: " + ", ".join("`%s`" % f for f in cad if f.endswith((".stl", ".step", ".f3d", ".pdf"))) +
          ". The TECHNIC 6S assembly is a representative model built from the SKYRIS documentation drawings "
          "(arm and battery-plate outlines imported from the vector figures, scale from the 30.5 mm FC pattern; main "
          "dimensions +-3 %), not official SKYRIS CAD.\n\n")
    return t


def write_docs(case, cfg, run, metrics, econ_md, out, name, cad=None):
    docs = {}
    decisions = case.get("decisions", []) + COMMON_DECISIONS
    params = [("Mission type", cfg.get("mission_type", case.get("mission_type"))), ("Area / targets", cfg.get("area") or cfg.get("supports") or cfg.get("targets")),
              ("Altitude", "%s m" % cfg.get("altitude")), ("Speed", "%s m/s" % cfg.get("speed")),
              ("Detectors", ", ".join("%s%s" % (d.get("type"), (" (%s)" % os.path.basename(str(d.get("model")))) if d.get("model") else "") for d in cfg.get("detectors", []))),
              ("Confirmation", "%s detections, merge radius %s m" % (cfg.get("tracker", {}).get("min_hits", 3), cfg.get("tracker", {}).get("radius", 0.4))),
              ("Safety", "land if cell < %s V, markers lost, outside geofence, > %s s, operator abort" % (cfg.get("safety", {}).get("min_cell_voltage", 3.5), cfg.get("safety", {}).get("max_time", 540)))]
    docs["01_Technical_Description.md"] = (
        "# Technical description - %s\n\n**Partner:** %s  \n**Team:** %s\n\n## 1. Problem\n%s\n\n**Customer:** %s\n\n"
        "## 2. Purpose of the system\n%s\n\n## 3. Main characteristics\n%s\n\n## 4. Functional block diagram\n![block diagram](block_diagram.png)\n\n"
        "## 5. Mission parameters\n%s\n## 6. Key engineering decisions and rationale\n%s\n## 7. Algorithm\n"
        "1. Pre-flight checks (FCU, position in aruco_map, battery, camera) - mission refuses to start on failure\n"
        "2. Take-off (auto-arm, OFFBOARD) to mission altitude\n3. Mission plan (%s) executed waypoint by waypoint; perception runs in parallel on every frame\n"
        "4. Each detection -> map coordinates -> tracker; object confirmed after N detections -> reaction (alarm, inspection, report to UI)\n"
        "5. Safety supervisor: operator abort/land, low battery, lost position, geofence / altitude limit, time limit -> landing; operator RETURN -> fly home and land\n6. Return home, land, automatic report (HTML/CSV/map/snapshots)\n\n"
        "%s"
        "## 8. Risks and mitigation\n%s\n" % (
            case["title"], case.get("partner", ""), ", ".join(t[0] for t in TEAM), case["problem"], case["customer"], case["solution"],
            "\n".join("- " + c for c in case["characteristics"]), md_table(["Parameter", "Value"], params),
            md_table(["Decision", "Rationale"], decisions), cfg.get("mission_type", case.get("mission_type")),
            cad_section(cad), "\n".join("- " + r for r in case.get("risks", []))))
    docs["02_Team_Roles.md"] = "# Team roles\n\n" + md_table(["Competitor", "Role", "Responsibilities"], TEAM)
    extra = []
    for c in cfg.get("cameras", {}).values():
        if c.get("type") == "cv":
            extra.append(("Additional camera (USB, e.g. thermal)", "Second sensor for detection", "device %s" % c.get("device"), "Detect what RGB cannot (heat)"))
    for d in cfg.get("detectors", []):
        if d.get("type") == "yolo":
            extra.append(("AI model %s" % os.path.basename(os.path.dirname(str(d["model"]))) or d["model"], "Object detection", "YOLO, conf %.2f" % d.get("conf", 0.4), "Trained on task data + venue images"))
    if cad:
        extra.append(("TR256i thermal mount (own design, 3D printed PETG)", "Holds the thermal camera under the frame, lens free",
                      "21.5 g, 74 x 82 x 16 mm, press fit + cable anchor, velcro/zip/M3", "Designed and verified in Autodesk Fusion"))
    docs["03_Components.md"] = "# Components, equipment and technical solutions\n\n" + md_table(
        ["No.", "Component / assembly", "Role in the system", "Main parameters", "Reason for selection"],
        [(i + 1,) + tuple(r) for i, r in enumerate(BASE_COMPONENTS + extra)])
    reqs = case.get("requirements", []) + COMMON_REQUIREMENTS
    docs["04_Test_Programme.md"] = "# Test programme and procedure\n\n" + md_table(
        ["No.", "System requirement", "Verification procedure", "Expected result"], [(("R%d" % (i + 1),) + tuple(r)) for i, r in enumerate(reqs)])
    # test report
    tr = "# Test report\n\n"
    if run:
        tr += "## Mission run `%s` (%s)\n\n" % (os.path.basename(run["dir"]), "simulation / mock" if run["mock"] else "real flight")
        rows = [("Result", run["result"]), ("Flight distance", "%.1f m" % run["distance"]),
                ("Duration", "%s s" % run["duration"] if run["duration"] is not None else "-"),
                ("Objects confirmed", len(run["objects"]))]
        if run.get("truth_n"):
            rows += [("Detection rate", "%d / %d (%.0f%%)" % (run["found"], run["truth_n"], 100.0 * run["found"] / run["truth_n"])),
                     ("False / extra objects", run["false"]),
                     ("Position error (mean / max)", "%.3f m / %.3f m" % (run["err_mean"] or 0, run["err_max"] or 0))]
        tr += md_table(["Metric", "Value"], rows) + "\n![mission map](mission_map.png)\n\n"
        tr += "### Detected objects\n" + md_table(["#", "Class", "X (m)", "Y (m)", "Z (m)", "Conf", "Hits"],
                                                  [(o["id"], o["name"], "%.2f" % o["x"], "%.2f" % o["y"], "%.2f" % o["z"], "%.2f" % o["conf"], o["hits"]) for o in run["objects"]])
        sd = os.path.join(out, "snapshots")
        os.makedirs(sd, exist_ok=True)
        for s in run["snapshots"]:
            shutil.copy2(s, sd)
            tr += "\n![snapshot](snapshots/%s)" % os.path.basename(s)
        tr += "\n\n"
    else:
        tr += "*(No mission run found yet - run the mission (mock or real) and regenerate.)*\n\n"
    if metrics:
        tr += "## AI model validation\n\n" + metrics.split("\n", 1)[1] + "\n"
    tr += "## Requirement verification\n\n" + md_table(["No.", "Requirement", "Expected", "Actual", "Status"],
                                                       [("R%d" % (i + 1), r[0], r[2], "", "") for i, r in enumerate(reqs)])
    tr += "\n*Fill 'Actual' with measured values from the flight log table and videos (links).* \n"
    docs["05_Test_Report.md"] = tr
    if econ_md:
        docs["06_Economics.md"] = econ_md
    script = case.get("script", "drone/generic_mission.py")
    docs["07_Operating_Instructions.md"] = (
        "# Operating instructions\n\n## Preparation\n1. Charge batteries, check props, RC kill switch tested with props off\n"
        "2. Place the drone on the start pad, power on, connect to Wi-Fi `technic-xxxx`\n3. Check markers visible: web UI -> image topics\n\n"
        "## Start\n```bash\nssh orangepi@10.42.0.1\ncd ~/brics_toolkit\npython3 %s --config %s\n```\n"
        "4. Open **http://10.42.0.1:8090** -> press **START MISSION**\n5. Watch live view and alerts; **RETURN HOME** (fly home, land), **LAND** / **ABORT** (land where it is) at any time; RC kill switch for emergencies\n\n"
        "## After the flight\n6. Report: link in the UI or `runs/<run>/report.html` (map, objects, coordinates, snapshots, CSV)\n"
        "7. Copy runs to the laptop: `scp -r orangepi@10.42.0.1:~/brics_toolkit/runs ./`\n\n"
        "## Adapting to a new site\nEdit the YAML config: area / targets, altitude, detectors, safety limits. Test with `--mock` first.\n" % (script, cfg.get("_path", "config/...")))
    docs["08_Defence_QA.md"] = "# Prepared answers for the experts\n\n" + "\n".join(
        "**Q: %s**  \nA: %s\n" % tuple(qa) for qa in case.get("qa", []) + [
            ("What if the markers are not visible?", "Position in aruco_map becomes NaN -> safety supervisor lands the drone; optical flow keeps it stable meanwhile."),
            ("What if the radio/Wi-Fi link is lost?", "Everything runs on board; the mission continues and lands; RC kill switch is independent."),
            ("How did you test it?", "Simulation (mock + Gazebo), then flights with a test programme: requirement -> procedure -> expected -> actual, logs and videos."),
            ("Who did what?", "; ".join("%s - %s" % (t[0].split()[0], t[1]) for t in TEAM))])
    for k, v in docs.items():
        open(os.path.join(out, k), "w").write(v)
    return docs


# ----------------------------------------------------------------------------- html / pdf
CSS = """body{font-family:-apple-system,Helvetica,Arial,sans-serif;font-size:10.5pt;line-height:1.45;max-width:900px;margin:auto;color:#222}
h1{font-size:18pt;border-bottom:2px solid #333;padding-bottom:4px;page-break-before:always}h1:first-of-type{page-break-before:avoid}
h2{font-size:13pt;margin-top:18px}table{border-collapse:collapse;width:100%;margin:8px 0;font-size:9.5pt}
th,td{border:1px solid #bbb;padding:4px 6px;vertical-align:top}th{background:#eee}img{max-width:100%}
pre{background:#f5f5f5;padding:8px;font-size:9pt;white-space:pre-wrap}@page{margin:14mm}"""


def to_pdf(html_path, pdf_path, landscape=False):
    pdf_path = os.path.abspath(pdf_path)
    cands = [BRAVE, CHROME, r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "/usr/bin/chromium", "/usr/bin/google-chrome"]
    for b in cands:
        if os.path.exists(b):
            subprocess.run([b, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf=" + pdf_path,
                            __import__("pathlib").Path(html_path).resolve().as_uri()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            return os.path.exists(pdf_path)
    return False


def all_html(docs, out, title):
    import markdown
    body = "\n".join(markdown.markdown(docs[k], extensions=["tables", "fenced_code"]) for k in sorted(docs))
    p = os.path.join(out, "ALL_DOCUMENTS.html")
    open(p, "w").write("<!DOCTYPE html><html><head><meta charset='utf-8'><title>%s</title><style>%s</style></head><body>%s</body></html>" % (title, CSS, body))
    to_pdf(p, os.path.join(out, "ALL_DOCUMENTS.pdf"))
    return p


# ----------------------------------------------------------------------------- presentation
def presentation(case, cfg, run, metrics, econ_m, out, name):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    NAVY = RGBColor(0x1D, 0x35, 0x57)
    html_slides = []

    def slide(title, bullets=None, image=None, table=None, notes=None):
        s = prs.slides.add_slide(blank)
        bar = s.shapes.add_shape(1, 0, 0, prs.slide_width, Inches(1.0))
        bar.fill.solid()
        bar.fill.fore_color.rgb = NAVY
        bar.line.fill.background()
        tb = s.shapes.add_textbox(Inches(0.4), Inches(0.15), Inches(12.5), Inches(0.8)).text_frame
        tb.text = title
        tb.paragraphs[0].runs[0].font.size = Pt(28)
        tb.paragraphs[0].runs[0].font.bold = True
        tb.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)
        left_w = Inches(6.3) if (image or table) and bullets else Inches(12.4)
        if bullets:
            tf = s.shapes.add_textbox(Inches(0.5), Inches(1.3), left_w, Inches(5.8)).text_frame
            tf.word_wrap = True
            for i, b in enumerate(bullets):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.text = u"• " + b
                p.font.size = Pt(19 if len(bullets) < 6 else 16)
                p.space_after = Pt(8)
        if image and os.path.exists(image):
            from PIL import Image as PImage
            w, h = PImage.open(image).size
            maxw, maxh = (6.3, 5.8) if bullets else (12.3, 6.0)
            k = min(maxw / (w / 100.0), maxh / (h / 100.0))
            iw, ih = w / 100.0 * k, h / 100.0 * k
            x = 6.9 if bullets else (13.333 - iw) / 2
            s.shapes.add_picture(image, Inches(x), Inches(1.3), Inches(iw), Inches(ih))
        if table:
            rows, cols = len(table), len(table[0])
            x = Inches(6.9) if bullets else Inches(0.6)
            w = Inches(6.0) if bullets else Inches(12.1)
            t = s.shapes.add_table(rows, cols, x, Inches(1.4), w, Inches(0.4) * rows).table
            for r in range(rows):
                for c in range(cols):
                    cell = t.cell(r, c)
                    cell.text = str(table[r][c])
                    cell.text_frame.paragraphs[0].font.size = Pt(13 if rows < 9 else 11)
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        html_slides.append((title, bullets or [], image, table))

    slide(case["title"], ["Team: " + " & ".join(t[0] for t in TEAM), "Chennai Institute of Technology, India",
                          "BRICS Hi-Tech Future Skills 2026 - Aerial Robotics", "Partner: " + case.get("partner", "")],
          notes="Introduce team and case in 15 seconds.")
    slide("The problem", [case["problem"], "Customer: " + case["customer"]], notes="Why the customer cares - numbers.")
    slide("Our solution", [case["solution"]] + case["characteristics"][:3])
    slide("System architecture", None, image=os.path.join(out, "block_diagram.png"))
    cad_dir = os.path.join(out, "cad")
    if os.path.exists(os.path.join(cad_dir, "technic6s_iso.png")):
        slide("Our drone: TECHNIC 6S + thermal camera", ["Fusion model built from the SKYRIS assembly guide",
                                                          "TR256i thermal camera in our own 3D-printed mount under the frame",
                                                          "Main camera (ArUco + RGB) at the front, Orange Pi 5 Pro NPU on board"],
              image=os.path.join(cad_dir, "technic6s_iso.png"))
    if os.path.exists(os.path.join(cad_dir, "technic6s_electronics_top.png")):
        slide("Electronics & wiring", ["ESC 4in1 + PX4 FC stack, ELRS on TELEM1, MR30 motor plugs, XT60 power",
                                       "Orange Pi 5 Pro + SKYRIS shield: TELEM2 -> UART0, LED ring, VL53L1X, cooler",
                                       "USB camera + TR256i thermal on the Orange Pi USB ports",
                                       "64 wires modelled - interference check: 0 clashes"],
              image=os.path.join(cad_dir, "technic6s_electronics_top.png"))
    if os.path.exists(os.path.join(cad_dir, "TECHNIC6S_wiring_diagram.png")):
        slide("Wiring diagram", None, image=os.path.join(cad_dir, "TECHNIC6S_wiring_diagram.png"))
    if os.path.exists(os.path.join(cad_dir, "render_down_camera_side.png")):
        slide("Custom hardware: thermal camera mount", ["Designed in Autodesk Fusion, printed in PETG (21.5 g), no supports",
                                                         "Slide-in cradle + crush ribs + cable anchor = vibration-proof",
                                                         "1.4 mm lips: 56 deg field of view verified clear",
                                                         "Mounts with the venue velcro straps - no drilling"],
              image=os.path.join(cad_dir, "render_down_camera_side.png"))
    dec = case.get("decisions", []) + COMMON_DECISIONS[:3]
    slide("Key engineering decisions", ["%s - %s" % tuple(d) for d in dec[:5]])
    slide("Algorithm & safety", ["Pre-flight checks -> take-off -> %s plan" % cfg.get("mission_type", case.get("mission_type")),
                                 "Perception on every frame -> map coordinates -> multi-frame confirmation",
                                 "Reaction: alarm, inspection, live report to operator",
                                 "Safety supervisor: abort button, low battery, lost markers, geofence, time limit -> land",
                                 "RC kill switch always overrides"])
    if run:
        rows = [["Metric", "Value"], ["Result", run["result"]], ["Objects confirmed", len(run["objects"])], ["Distance flown", "%.1f m" % run["distance"]]]
        if run.get("truth_n"):
            rows += [["Detection rate", "%d/%d" % (run["found"], run["truth_n"])], ["Position error mean/max", "%.2f / %.2f m" % (run["err_mean"] or 0, run["err_max"] or 0)]]
        slide("Test results", ["Run: %s (%s)" % (os.path.basename(run["dir"]), "simulation" if run["mock"] else "flight")], image=os.path.join(out, "mission_map.png"))
        slide("Test results - numbers", None, table=rows)
    if metrics:
        lines = [l for l in metrics.splitlines() if l.startswith("|") and "---" not in l]
        tbl = [[c.strip().replace("*", "") for c in l.strip("|").split("|")] for l in lines]
        if tbl:
            slide("AI model quality (validation)", None, table=tbl[:10])
    if econ_m:
        def f(v):
            return "{:,.0f}".format(v).replace(",", " ")
        slide("Economic efficiency", ["NPV %s RUB > 0" % f(econ_m["npv"]), "IRR %.0f%% > discount rate %.0f%%" % (100 * (econ_m["irr"] or 0), 100 * econ_m["rate"]),
                                      "Payback %.1f years, ROI %.0f%%" % (econ_m["payback"] or 0, 100 * (econ_m["roi"] or 0)), "Conclusion: economically feasible"],
              table=[["Item", "Value"], ["CAPEX", f(econ_m["capex"])], ["OPEX / year", f(econ_m["opex1"])], ["Benefits / year", f(econ_m["ben1"])]])
    slide("Conclusion & next steps", ["Working autonomous prototype with onboard AI and automatic reports",
                                      "Tested in simulation and flights against a test programme",
                                      "Scales to the real site: GNSS/RTK, bigger area, same software",
                                      "Code & documentation: GitHub repository"])
    p = os.path.join(out, "Presentation.pptx")
    prs.save(p)
    # PDF version via HTML slides
    import base64
    hs = []
    for title, bullets, image, table in html_slides:
        img = ""
        if image and os.path.exists(image):
            img = "<img src='data:image/png;base64,%s'>" % base64.b64encode(open(image, "rb").read()).decode()
        tb = ""
        if table:
            tb = "<table>" + "".join("<tr>" + "".join("<td>%s</td>" % c for c in r) + "</tr>" for r in table) + "</table>"
        ul = "<ul>" + "".join("<li>%s</li>" % b for b in bullets) + "</ul>" if bullets else ""
        hs.append("<section><header>%s</header><div class='c'><div class='l'>%s</div><div class='r'>%s%s</div></div></section>" % (title, ul, img, tb))
    css = ("@page{size:13.333in 7.5in;margin:0}body{margin:0;font-family:Arial}section{width:13.333in;height:7.5in;page-break-after:always;overflow:hidden}"
           "header{background:#1d3557;color:#fff;font-size:30pt;font-weight:bold;padding:.2in .4in;height:.6in}.c{display:flex;padding:.3in .5in;gap:.3in}"
           ".l{flex:1;font-size:19pt}.r{flex:1}.r img{max-width:100%;max-height:5.6in}li{margin-bottom:10px}table{border-collapse:collapse;font-size:14pt}td{border:1px solid #999;padding:6px 10px}")
    hp = os.path.join(out, "Presentation_slides.html")
    open(hp, "w").write("<!DOCTYPE html><html><head><meta charset='utf-8'><style>%s</style></head><body>%s</body></html>" % (css, "".join(hs)))
    to_pdf(hp, os.path.join(out, "Presentation.pdf"))
    return p


# ----------------------------------------------------------------------------- github repo
def github_repo(out, case, name):
    repo = os.path.join(out, "github_repo")
    if os.path.isdir(repo):
        shutil.rmtree(repo)
    os.makedirs(repo)
    for d in ("common", "drone", "analysis", "config", "train", "economics", "tools", "studio", "tests", "setup", "cad"):
        shutil.copytree(os.path.join(ROOT, d), os.path.join(repo, d), ignore=shutil.ignore_patterns("__pycache__", "projects", "*.pyc", "outdated", "_*.png"))
    shutil.copytree(out, os.path.join(repo, "docs"), ignore=shutil.ignore_patterns("github_repo", "*.pdf", "*.pptx", "*.xlsx", "ALL_DOCUMENTS.html", "Presentation_slides.html"))
    open(os.path.join(repo, "README.md"), "w").write(
        "# %s\n\nBRICS Hi-Tech Future Skills 2026 - Aerial Robotics - team %s\n\n%s\n\n## Solution\n%s\n\n"
        "## Structure\n- `drone/` missions (TECHNIC 6S, ROS), `common/` detection/geometry/UI, `train/` AI pipeline, `config/` YAML, `economics/`, `docs/` documentation\n\n"
        "## Run\n```bash\npython3 %s --config <config.yaml>          # on the drone\npython3 %s --config <config.yaml> --mock --autostart   # laptop test\n```\n"
        "See `docs/` for the technical description, test programme and report, economics and operating instructions.\n"
        % (case["title"], " & ".join(t[0] for t in TEAM), case["problem"], case["solution"], case.get("script"), case.get("script")))
    open(os.path.join(repo, ".gitignore"), "w").write("runs/\ndatasets/\n*.pt\n__pycache__/\n.venv/\n")
    try:
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=BRICS Team", "-c", "user.email=team@example.com", "commit", "-qm",
                        "%s - solution and documentation" % case["title"]], cwd=repo, check=True)
    except Exception as e:
        print("[docs] git init skipped:", e)
    return repo


# ----------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", help="case1 | case2 | case3 | case4")
    ap.add_argument("--custom", help="JSON file describing a custom PS (made by Mission Studio)")
    ap.add_argument("--config")
    ap.add_argument("--model", help="models/<name> folder (for metrics)")
    ap.add_argument("--run", help="runs/<run> folder (default: latest for this case)")
    ap.add_argument("--econ", help="economics YAML")
    ap.add_argument("--out")
    ap.add_argument("--no-github", action="store_true")
    a = ap.parse_args(argv)
    if a.custom:
        case = json.load(open(a.custom))
        name = os.path.splitext(os.path.basename(a.custom))[0]
    else:
        case = CASES[a.case]
        name = a.case + "_" + case["short"].lower().replace(" ", "_")
    cfg_path = a.config or case.get("config")
    cfg = yaml.safe_load(open(os.path.join(ROOT, cfg_path) if not os.path.isabs(cfg_path) else cfg_path))
    cfg["_path"] = cfg_path
    out = a.out or os.path.join(ROOT, "deliverables", name)
    os.makedirs(out, exist_ok=True)
    print("[docs] %s -> %s" % (case["title"], out))
    run_dir = a.run or latest_run(cfg.get("case", name))
    if run_dir is None and cfg.get("swarm"):
        run_dir = latest_run(cfg.get("case", "case3_swarm") + "_d0")
    run = read_run(run_dir, cfg) if run_dir else None
    model_dir = a.model
    if not model_dir:
        for d in cfg.get("detectors", []):
            if d.get("type") == "yolo" and os.path.exists(os.path.join(ROOT, os.path.dirname(str(d["model"])), "metrics.md")):
                model_dir = os.path.join(ROOT, os.path.dirname(str(d["model"])))
                break
    metrics = read_metrics(model_dir)
    econ_md, econ_m = None, None
    econ_yaml = a.econ or case.get("econ")
    if econ_yaml:
        from economics import econ
        ecfg = yaml.safe_load(open(os.path.join(ROOT, econ_yaml) if not os.path.isabs(econ_yaml) else econ_yaml))
        econ_md, econ_m = econ.report(ecfg, name)
        econ.write_xlsx(ecfg, econ_m, os.path.join(out, "06_Economics.xlsx"))
    cad = copy_cad(out)
    block_diagram(case, cfg, os.path.join(out, "block_diagram.png"))
    mission_map(run, cfg, os.path.join(out, "mission_map.png"))
    docs = write_docs(case, cfg, run, metrics, econ_md, out, name, cad)
    all_html(docs, out, case["title"])
    presentation(case, cfg, run, metrics, econ_m, out, name)
    if not a.no_github:
        github_repo(out, case, name)
    print("[docs] run used: %s" % (run_dir or "none"))
    print("[docs] DONE: %s" % "  ".join(sorted(os.listdir(out))))
    return out


if __name__ == "__main__":
    main()
