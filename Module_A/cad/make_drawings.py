#!/usr/bin/env python3
"""
Technical drawings (A3) of the printed parts, generated from the REAL Fusion model edges (cad/out/edges_*.json,
exported by the Fusion script) + the mount parameters. Output: cad/out/Drawing_*.pdf / .png
"""
import datetime
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
P = {"mod_L": 56.6, "mod_W": 34.4, "mod_T": 12.1, "clr": 0.35, "clr_t": 0.40, "wall": 2.2, "lip_w": 2.2, "lip_t": 1.4,
     "plate_t": 2.5, "wing": 21.0, "margin_x": 3.0, "tab_x": 12.0, "rib_int": 0.15, "strap_w": 15.0}
cav_L, cav_W, cav_H = P["mod_L"] + P["clr"], P["mod_W"] + 2 * P["clr"], P["mod_T"] + P["clr_t"]
cr_W, cr_H = cav_W + 2 * P["wall"], cav_H + P["lip_t"]


def load(tag):
    d = json.load(open(os.path.join(OUT, "edges_%s.json" % tag)))
    return d["edges"], d["volume_cm3"]


def view(ax, edges, a, b, title, flip_b=False):
    for e in edges:
        xs = [p[a] for p in e]
        ys = [(-p[b] if flip_b else p[b]) for p in e]
        ax.plot(xs, ys, color="#222", lw=0.55)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10, loc="left")
    ax.axis("off")


def dim(ax, p1, p2, off, text, horizontal=True):
    """Dimension line between p1 and p2, offset perpendicular by off (mm)."""
    (x1, y1), (x2, y2) = p1, p2
    kw = dict(color="#0b5394", lw=0.7)
    if horizontal:
        y = y1 + off
        ax.plot([x1, x1], [y1, y], **kw)
        ax.plot([x2, x2], [y2, y], **kw)
        ax.annotate("", xy=(x1, y), xytext=(x2, y), arrowprops=dict(arrowstyle="<->", color="#0b5394", lw=0.7))
        ax.text((x1 + x2) / 2, y + (1.2 if off > 0 else -1.2), text, ha="center", va="bottom" if off > 0 else "top", fontsize=7.5, color="#0b5394")
    else:
        x = x1 + off
        ax.plot([x1, x], [y1, y1], **kw)
        ax.plot([x2, x], [y2, y2], **kw)
        ax.annotate("", xy=(x, y1), xytext=(x, y2), arrowprops=dict(arrowstyle="<->", color="#0b5394", lw=0.7))
        ax.text(x + (1.2 if off > 0 else -1.2), (y1 + y2) / 2, text, ha="left" if off > 0 else "right", va="center",
                fontsize=7.5, color="#0b5394", rotation=90)


def title_block(fig, name, vol, notes):
    ax = fig.add_axes([0.62, 0.03, 0.36, 0.2])
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 1, 1, fill=False, lw=1.2, transform=ax.transAxes))
    rows = [("Part", name), ("Material", "PETG (or PLA+), 0.2 mm layers, 4 walls, 30 % gyroid"),
            ("Mass", "%.1f g (PETG 1.27 g/cm3), volume %.2f cm3" % (vol * 1.27, vol)),
            ("Print", "flat mounting face on the bed, NO supports"),
            ("Units / scale", "mm / not to scale - use the STEP/STL"),
            ("Project", "BRICS Hi-Tech 2026 Aerial Robotics - Chennai Institute of Technology"),
            ("Source", "Autodesk Fusion parametric model (cad/fusion_thermal_mount.py), %s" % datetime.date.today().isoformat())]
    for i, (k, v) in enumerate(rows):
        y = 0.9 - i * 0.125
        ax.text(0.02, y, k, fontsize=7.5, weight="bold", transform=ax.transAxes, va="center")
        ax.text(0.22, y, v, fontsize=7.5, transform=ax.transAxes, va="center")
    na = fig.add_axes([0.02, 0.03, 0.58, 0.2])
    na.axis("off")
    na.text(0, 1, "NOTES\n" + "\n".join("%d. %s" % (i + 1, n) for i, n in enumerate(notes)), fontsize=7.5, va="top", family="monospace")


def drawing_down():
    edges, vol = load("down")
    fig = plt.figure(figsize=(16.54, 11.69))
    fig.suptitle("TR256i thermal camera mount - LOOKING DOWN (Case 1)", fontsize=15, x=0.02, ha="left", weight="bold")
    X0 = -cav_L / 2
    px0, px1, py = X0 - P["wall"] - P["margin_x"], cav_L / 2 + P["tab_x"], cr_W / 2 + P["wing"]
    ax = fig.add_axes([0.03, 0.28, 0.42, 0.62])
    view(ax, edges, 0, 1, "TOP VIEW (drone side, plate)")
    dim(ax, (px0, -py), (px1, -py), -8, "%.1f" % (px1 - px0))
    dim(ax, (px1, -py), (px1, py), 8, "%.1f" % (2 * py), horizontal=False)
    dim(ax, (-18, py - P["wing"] / 2 + 8.25), (18, py - P["wing"] / 2 + 8.25), 6, "velcro slots 16.5 x 3.4  @ x = -18 / +18")
    dim(ax, (X0, -cav_W / 2), (X0 + cav_L, -cav_W / 2), -3, "cavity %.2f (module %.1f)" % (cav_L, P["mod_L"]))
    ax2 = fig.add_axes([0.5, 0.58, 0.47, 0.32])
    view(ax2, edges, 0, 2, "FRONT VIEW (side)")
    dim(ax2, (px0, P["plate_t"]), (px0, -cr_H), -6, "%.1f" % (P["plate_t"] + cr_H), horizontal=False)
    dim(ax2, (px1, 0), (px1, P["plate_t"]), 5, "%.1f" % P["plate_t"], horizontal=False)
    ax3 = fig.add_axes([0.5, 0.27, 0.47, 0.3])
    view(ax3, edges, 1, 2, "SIDE VIEW (from the USB-C / open end)")
    dim(ax3, (-cav_W / 2, -cr_H), (cav_W / 2, -cr_H), -5, "cavity %.2f (module %.1f)" % (cav_W, P["mod_W"]))
    dim(ax3, (py, -cav_H), (py, 0), 4, "%.1f" % cav_H, horizontal=False)
    title_block(fig, "Thermal Mount DOWN (TR256i, TECHNIC 6S)", vol, [
        "Fits TR256i 56.6 x 34.4 x 12.1 mm: clearance %.2f/side, %.2f on top; 4 crush ribs %.2f press fit." % (P["clr"], P["clr_t"], P["rib_int"]),
        "Slide module in from the open end (USB-C out), zip-tie the USB cable to the anchor tab.",
        "Lips %.1f x %.1f mm hold the edges; window chamfered 1 mm - 56 deg lens view verified clear." % (P["lip_w"], P["lip_t"]),
        "Attach with the venue velcro straps (15 mm) through the wing slots, or zip ties / M3 in the slots.",
        "Verified in Fusion: single solid, fit (ribs only), field of view (45 lens positions), no supports."])
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, "Drawing_TR256i_mount_down.%s" % ext), dpi=130)
    plt.close(fig)


def drawing_forward():
    edges, vol = load("forward")
    fig = plt.figure(figsize=(16.54, 11.69))
    fig.suptitle("TR256i thermal camera mount - LOOKING FORWARD (Case 4)", fontsize=15, x=0.02, ha="left", weight="bold")
    xs = [p[0] for e in edges for p in e]
    ys = [p[1] for e in edges for p in e]
    zs = [p[2] for e in edges for p in e]
    ax = fig.add_axes([0.03, 0.3, 0.3, 0.6])
    view(ax, edges, 0, 1, "TOP VIEW (plate)")
    dim(ax, (min(xs), min(ys)), (max(xs), min(ys)), -6, "%.1f" % (max(xs) - min(xs)))
    dim(ax, (max(xs), min(ys)), (max(xs), max(ys)), 6, "%.1f" % (max(ys) - min(ys)), horizontal=False)
    ax2 = fig.add_axes([0.36, 0.3, 0.3, 0.6])
    view(ax2, edges, 0, 2, "SIDE VIEW (lens looks +X)")
    dim(ax2, (min(xs), min(zs)), (min(xs), max(zs)), -6, "%.1f" % (max(zs) - min(zs)), horizontal=False)
    ax3 = fig.add_axes([0.69, 0.3, 0.29, 0.6])
    view(ax3, edges, 1, 2, "FRONT VIEW (lens side)")
    dim(ax3, (min(ys), min(zs)), (max(ys), min(zs)), -5, "%.1f" % (max(ys) - min(ys)))
    title_block(fig, "Thermal Mount FORWARD (TR256i, TECHNIC 6S)", vol, [
        "Same cradle as the DOWN mount rotated 90 deg: the lens looks forward (power-line inspection).",
        "Hangs %.0f mm below the mounting face - check landing-gear clearance on the drone." % (max(zs) - min(zs)),
        "Two gussets stiffen the back plate; plate slots: 2 velcro straps, M3, zip ties.",
        "Print plate face down - largest bridge 12.5 mm, no supports.",
        "Verified in Fusion: single solid, fit (ribs only), field of view, printability."])
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, "Drawing_TR256i_mount_forward.%s" % ext), dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    drawing_down()
    if os.path.exists(os.path.join(OUT, "edges_forward.json")):
        drawing_forward()
    else:
        print("edges_forward.json missing - forward drawing skipped (run cad/build_all_cad.py)")
    print("drawings ->", OUT)
