"""Builds the Module B evidence charts and data tables from the real flight logs.

Run with the toolkit venv:  ../brics_toolkit/.venv/bin/python make_figures.py
Reads  ~/Desktop/BRICS Mission Logs/case1_fire_<date>_<time>/ (real flights only, no *_mock)
Writes figures/chart_*.png and evidence_numbers.txt (every number quoted in the report).
"""
import csv, json, math, os, re, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "brics_toolkit"))
from common.geometry import lawnmower  # the planner the drone itself uses

LOGS = os.path.expanduser("~/Desktop/BRICS Mission Logs")
BLUE, ORANGE, INK, MUTED = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e"
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
                     "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                     "axes.spines.right": False})


def dseg(p, a, b):
    (ax, ay), (bx, by), (px, py) = a, b, p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


flights = []
for run in sorted(os.listdir(LOGS)):
    if not run.startswith("case1_fire_2026111") or run.endswith(("_mock", ".zip")):
        continue
    d = os.path.join(LOGS, run)
    try:
        s = json.load(open(os.path.join(d, "summary.json")))
    except Exception:
        continue
    if s.get("result") != "completed":
        continue
    log = open(os.path.join(d, "log.txt")).read()
    m = re.search(r"\[plan\] survey area \[([^\]]+)\] at z=([\d.]+), line spacing ([\d.]+)", log)
    area = [float(v) for v in m.group(1).split(",")]
    wps = lawnmower(area[0], area[1], area[2], area[3], float(m.group(3)), float(m.group(2)))
    P = [(float(r["x"]), float(r["y"])) for r in csv.DictReader(open(os.path.join(d, "path.csv")))]
    wp_err = [min(dseg(w[:2], P[i], P[i + 1]) for i in range(len(P) - 1)) for w in wps]
    perf = list(csv.DictReader(open(os.path.join(d, "perf.csv"))))
    det = sorted(float(r["detect_ms"]) for r in perf if r["detect_ms"])
    ev = list(csv.DictReader(open(os.path.join(d, "events.csv"))))
    flights.append(dict(
        run=run, label=run[17:19] + " Nov " + run[20:22] + ":" + run[22:24], alt=float(m.group(2)),
        dur=s["duration_s"], dist=s["distance_m"], counts=s.get("counts", {}),
        rgb=s["fps"]["rgb"]["airborne"], th=s["fps"]["thermal"]["airborne"],
        wp_n=len(wps), wp_max=max(wp_err), home=math.hypot(*P[-1]),
        det_med=det[len(det) // 2] if det else float("nan"), events=len(ev),
        objects=json.load(open(os.path.join(d, "objects.json")))))

out = open(os.path.join(HERE, "evidence_numbers.txt"), "w")
out.write("flight | alt m | dur s | dist m | waypoints | max wp err m | home err m | RGB mean/%>=10 | "
          "thermal mean/%>=10 | detect ms median | events | counts\n")
for f in flights:
    out.write(f"{f['run']} | {f['alt']} | {f['dur']} | {f['dist']} | {f['wp_n']} | {f['wp_max']:.2f} | "
              f"{f['home']:.2f} | {f['rgb']['mean_fps']}/{f['rgb']['pct_seconds_ge_10']} | "
              f"{f['th']['mean_fps']}/{f['th']['pct_seconds_ge_10']} | {f['det_med']:.1f} | {f['events']} | "
              f"{f['counts']}\n")

# ---- Chart 1: share of airborne seconds at >= 10 FPS per flight (C4) ----
fig, ax = plt.subplots(figsize=(7.2, 2.6), dpi=200)
xs = range(len(flights))
w = 0.38
ax.bar([x - w / 2 - 0.01 for x in xs], [f["rgb"]["pct_seconds_ge_10"] for f in flights], w, color=BLUE,
       label="RGB stream")
ax.bar([x + w / 2 + 0.01 for x in xs], [f["th"]["pct_seconds_ge_10"] for f in flights], w, color=ORANGE,
       label="Thermal stream")
ax.axhline(90, color=INK, lw=0.9, ls="--")
ax.text(1.0, 1.02, "dashed line: C4 threshold > 90 %", transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color=INK)
ax.set_xticks(list(xs))
ax.set_xticklabels([f["label"] for f in flights], rotation=45, ha="right", fontsize=7.5)
ax.set_ylabel("% of airborne 1-s intervals\nat ≥ 10 FPS")
ax.set_ylim(0, 105)
ax.grid(axis="y", color="#e6e5e0", lw=0.6)
ax.set_axisbelow(True)
ax.legend(frameon=False, ncol=2, loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "figures", "chart_fps.png"))

# ---- Chart 2: waypoint error per flight (C1) ----
fig, ax = plt.subplots(figsize=(7.2, 2.2), dpi=200)
ax.bar(list(xs), [f["wp_max"] for f in flights], 0.55, color=BLUE, label="worst planned waypoint")
ax.plot(list(xs), [f["home"] for f in flights], "o", color=ORANGE, ms=4.5, mec="white", mew=1,
        label="end of return leg vs home")
ax.axhline(0.25, color=INK, lw=0.9, ls="--")
ax.text(len(flights) - 0.5, 0.255, "C1 threshold 0.25 m", ha="right", va="bottom", fontsize=8)
ax.axhline(0.5, color=MUTED, lw=0.9, ls=":")
ax.text(len(flights) - 0.5, 0.505, "C7 landing threshold 0.5 m", ha="right", va="bottom", fontsize=8,
        color=MUTED)
ax.set_xticks(list(xs))
ax.set_xticklabels([f["label"] for f in flights], rotation=45, ha="right", fontsize=7.5)
ax.set_ylabel("horizontal error (m)")
ax.set_ylim(0, 0.6)
ax.grid(axis="y", color="#e6e5e0", lw=0.6)
ax.set_axisbelow(True)
ax.legend(frameon=False, ncol=2, loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "figures", "chart_route.png"))

# ---- Chart 3: repeatability of reported object positions over the four evening flights (C5) ----
evening = [f for f in flights if f["run"] >= "case1_fire_20261111_215"]
pts = [(o["x"], o["y"], o["name"], f["label"]) for f in evening for o in f["objects"]]
clusters = []  # greedy 0.6 m clustering per class family (fire vs tree)
fam = lambda n: "tree" if n == "tree" else "fire"
for x, y, n, lab in pts:
    for c in clusters:
        cx = sum(p[0] for p in c) / len(c); cy = sum(p[1] for p in c) / len(c)
        if fam(c[0][2]) == fam(n) and math.hypot(x - cx, y - cy) < 0.6:
            c.append((x, y, n, lab)); break
    else:
        clusters.append([(x, y, n, lab)])
fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=200)
ax.add_patch(plt.Rectangle((-3.75, -2.25), 7.5, 4.5, fill=False, ec=MUTED, lw=0.8))
ax.add_patch(plt.Rectangle((-2.5, -1), 5, 2, fill=False, ec=BLUE, lw=0.8, ls="--"))
ax.text(-2.45, 1.05, "survey area 5 × 2 m", color=BLUE, fontsize=7.5, va="bottom")
ax.text(-3.7, 2.3, "ArUco field 7.5 × 4.5 m", color=MUTED, fontsize=7.5, va="bottom")
style = {"fire": dict(marker="o", color=ORANGE), "tree_fire": dict(marker="^", color="#e34948"),
         "tree": dict(marker="s", color="#1baf7a")}
seen = set()
for x, y, n, lab in pts:
    ax.scatter(x, y, s=22, edgecolors="white", linewidths=0.8, zorder=3, **style[n],
               label=n.replace("_", " ") if n not in seen else None)
    seen.add(n)
rows = []
for c in clusters:
    if len(c) < 3:   # seen in fewer than 3 flights: not a repeatable object
        continue
    cx = sum(p[0] for p in c) / len(c); cy = sum(p[1] for p in c) / len(c)
    r = max(math.hypot(p[0] - cx, p[1] - cy) for p in c)
    ax.add_patch(plt.Circle((cx, cy), 0.5, fill=False, ec=INK, lw=0.6, ls=":"))
    rows.append((fam(c[0][2]), cx, cy, len(c), len({p[3] for p in c}), r))
ax.scatter(0, 0, marker="+", s=60, color=INK, zorder=3, label="home pad / map origin")
ax.set_aspect("equal")
ax.set_xlim(-4, 4.4); ax.set_ylim(-2.5, 2.7)
ax.set_xlabel("x (m, aruco_map)"); ax.set_ylabel("y (m)")
ax.legend(frameon=False, fontsize=7.5, loc="center left", bbox_to_anchor=(1.0, 0.5))
fig.tight_layout()
fig.savefig(os.path.join(HERE, "figures", "chart_repeat.png"))

out.write("\nrepeatability clusters (family, mean x, mean y, reports, flights, max dev from mean m)\n")
for r in sorted(rows, key=lambda r: (r[0], r[1])):
    out.write(f"{r[0]} | {r[1]:.2f} | {r[2]:.2f} | {r[3]} | {r[4]} | {r[5]:.2f}\n")
out.close()
print(open(os.path.join(HERE, "evidence_numbers.txt")).read())

# ---- Charts 4 + 5: real-flight detection events and detection map (dashboard style), 11 Nov 23:07 ----
RUN = os.path.join(LOGS, "case1_fire_20261111_230709")
CANVAS, PANEL, TXT2, TXT3 = "#121418", "#121418", "#9097A3", "#5C636E"
CLS = {"fire": "#FF453A", "tree_fire": "#FF453A", "flame": "#FF6A1F", "tree": "#32D74B"}
ev = list(csv.DictReader(open(os.path.join(RUN, "events.csv"))))
t0 = float(ev[0]["t_unix"])
objs = json.load(open(os.path.join(RUN, "objects.json")))
conf_rows = [e for e in ev if e["confirmed_now"] == "1"]


def dark(ax, fig):
    fig.patch.set_facecolor(CANVAS)
    ax.set_facecolor(PANEL)
    for sp in ax.spines.values():
        sp.set_color("#2a2d33")
    ax.tick_params(colors=TXT2, labelsize=7)
    ax.xaxis.label.set_color(TXT2); ax.yaxis.label.set_color(TXT2)


fig, ax = plt.subplots(figsize=(7.2, 2.3), dpi=220)
dark(ax, fig)
for c in ("tree", "flame", "fire", "tree_fire"):
    pts = [(float(e["t_unix"]) - t0, float(e["conf"])) for e in ev if e["class"] == c]
    ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=3, color=CLS[c], alpha=0.55, lw=0)
for e in conf_rows:
    t = float(e["t_unix"]) - t0
    ax.axvline(t, color=TXT3, lw=0.6, ls=(0, (2, 2)))
    ax.scatter(t, float(e["conf"]), marker="D", s=26, color=CLS[e["class"]], ec="white", lw=0.5, zorder=3)
    ax.text(t, float(e["conf"]) + 0.07, "#" + e["object_id"], color="#EDEFF2", fontsize=6.5, ha="center",
            family="monospace")
ax.set_ylim(0, 1.08); ax.set_xlim(-1, (float(ev[-1]["t_unix"]) - t0) + 1)
ax.set_xlabel("seconds since first detection"); ax.set_ylabel("NN confidence")
for c, lab in (("fire", "fire / tree heat band"), ("flame", "flame"), ("tree", "tree")):
    ax.scatter([], [], s=12, color=CLS[c], label=lab)
ax.scatter([], [], marker="D", s=22, color="#9097A3", ec="white", lw=0.5, label="confirmed")
ax.legend(frameon=False, fontsize=7, ncol=4, labelcolor=TXT2, loc="lower right", bbox_to_anchor=(1, 1.0))
fig.tight_layout()
fig.savefig(os.path.join(HERE, "figures", "real_events.png"), facecolor=CANVAS)

# detection map: light floor + markers, every raw detection, path, confirmed objects with 0.5 m circles
markers = [l.split() for l in open(os.path.join(HERE, "..", "brics_toolkit", "config", "aruco_map_750x450_id100.txt"))
           if l.strip() and not l.startswith("#")]
path = [(float(r["x"]), float(r["y"])) for r in csv.DictReader(open(os.path.join(RUN, "path.csv")))]
fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=220)
dark(ax, fig)
ax.add_patch(plt.Rectangle((-3.75, -2.25), 7.5, 4.5, color="#E9E7E1", zorder=0))
for m in markers:
    L, x, y = float(m[1]), float(m[2]), float(m[3])
    ax.add_patch(plt.Rectangle((x - L / 2, y - L / 2), L, L, color="#26282c", zorder=1))
    ax.text(x, y - L / 2 - 0.09, m[0], fontsize=4.5, ha="center", color="#7a7d83", zorder=1)
ax.add_patch(plt.Rectangle((-2.5, -1), 5, 2, fill=False, ec="#5C636E", lw=0.8, ls="--", zorder=2))
ax.plot([p[0] for p in path], [p[1] for p in path], color="#3b6fd6", lw=1.3, alpha=0.9, zorder=2)
for c in ("tree", "flame", "fire", "tree_fire"):
    pts = [(float(e["x"]), float(e["y"])) for e in ev if e["class"] == c]
    ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=2.5, color=CLS[c], alpha=0.35, lw=0, zorder=3)
OFF = {3: (6, -22), 4: (10, -20), 5: (6, 10), 6: (-78, 10), 8: (6, -24), 9: (-80, 8), 10: (6, 8)}
for o in objs:
    col = CLS.get(o["name"], "#9097A3")
    ax.add_patch(plt.Circle((o["x"], o["y"]), 0.5, fill=False, ec=col, lw=0.7, ls=(0, (2, 2)), zorder=4))
    ax.scatter(o["x"], o["y"], s=40, color=col, ec="white", lw=0.9, zorder=5)
    ax.annotate(f"#{o['id']} {o['name'].replace('_', ' ')}\n({o['x']:.2f}, {o['y']:.2f})", (o["x"], o["y"]),
                xytext=OFF.get(o["id"], (6, 6)), textcoords="offset points", fontsize=5.5, color="#EDEFF2", family="monospace",
                bbox=dict(boxstyle="round,pad=0.25", fc="#181B20", ec="none", alpha=0.9), zorder=6)
ax.scatter(0, 0, marker="+", s=70, color="#0A0B0D", zorder=5)
ax.set_aspect("equal"); ax.set_xlim(-3.95, 4.6); ax.set_ylim(-2.45, 2.6)
ax.set_xlabel("x (m, aruco_map)"); ax.set_ylabel("y (m)")
fig.tight_layout()
fig.savefig(os.path.join(HERE, "figures", "real_detmap.png"), facecolor=CANVAS)
print("raw detections plotted:", len(ev), "confirmed:", len(conf_rows), "objects:", len(objs))
