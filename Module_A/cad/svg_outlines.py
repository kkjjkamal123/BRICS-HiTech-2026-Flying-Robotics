#!/usr/bin/env python3
"""
Extract part outlines (in mm) from the TECHNIC 6S documentation SVG drawings, for the Fusion drone model.
  2.svg    - top view of the 4 carbon arms (filled paths cls-1/2/4/5)
  15_11.svg- top view of the battery plate
Scale (mm per SVG unit) is derived from known hole patterns (see cad/README_CAD.md).
Output: cad/out/technic_outlines.json
"""
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "..", "offline", "docs", "docs.skyris.ru", "technic6S", "assets")


# ----------------------------------------------------------------------------- SVG path -> polylines
TOK = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


def _arc(p0, rx, ry, phi, fa, fs, p1, n=16):
    """SVG elliptical arc endpoint parametrisation -> points (excluding p0)."""
    if rx == 0 or ry == 0:
        return [p1]
    phi = math.radians(phi)
    c, s = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2.0, (p0[1] - p1[1]) / 2.0
    x1, y1 = c * dx + s * dy, -s * dx + c * dy
    rx, ry = abs(rx), abs(ry)
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        co = -co
    cxp, cyp = co * rx * y1 / ry, -co * ry * x1 / rx
    cx = c * cxp - s * cyp + (p0[0] + p1[0]) / 2.0
    cy = s * cxp + c * cyp + (p0[1] + p1[1]) / 2.0
    ang = lambda ux, uy, vx, vy: math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
    t1 = ang(1, 0, (x1 - cxp) / rx, (y1 - cyp) / ry)
    dt = ang((x1 - cxp) / rx, (y1 - cyp) / ry, (-x1 - cxp) / rx, (-y1 - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    pts = []
    for i in range(1, n + 1):
        t = t1 + dt * i / n
        pts.append((cx + rx * math.cos(t) * c - ry * math.sin(t) * s, cy + rx * math.cos(t) * s + ry * math.sin(t) * c))
    return pts


def path_to_polys(d, nb=8):
    toks = TOK.findall(d)
    i, cmd = 0, None
    cur, start = (0.0, 0.0), (0.0, 0.0)
    last_c = None
    polys, poly = [], []

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v
    while i < len(toks):
        if re.match(r"[A-Za-z]", toks[i]):
            cmd = toks[i]
            i += 1
            if cmd in "Zz":
                if poly:
                    polys.append(poly)
                poly = []
                cur = start
                last_c = None
                continue
        rel = cmd.islower()
        C = cmd.upper()
        ox, oy = cur if rel else (0.0, 0.0)
        if C == "M":
            x, y = num() + ox, num() + oy
            if poly:
                polys.append(poly)
            poly = [(x, y)]
            cur = start = (x, y)
            cmd = "l" if rel else "L"
            last_c = None
        elif C == "L":
            cur = (num() + ox, num() + oy)
            poly.append(cur)
            last_c = None
        elif C == "H":
            cur = (num() + (cur[0] if rel else 0.0), cur[1])
            poly.append(cur)
            last_c = None
        elif C == "V":
            cur = (cur[0], num() + (cur[1] if rel else 0.0))
            poly.append(cur)
            last_c = None
        elif C in "CS":
            if C == "C":
                c1 = (num() + ox, num() + oy)
            else:
                c1 = (2 * cur[0] - last_c[0], 2 * cur[1] - last_c[1]) if last_c else cur
            c2 = (num() + ox, num() + oy)
            p = (num() + ox, num() + oy)
            for k in range(1, nb + 1):
                t = k / float(nb)
                mt = 1 - t
                poly.append((mt ** 3 * cur[0] + 3 * mt * mt * t * c1[0] + 3 * mt * t * t * c2[0] + t ** 3 * p[0],
                             mt ** 3 * cur[1] + 3 * mt * mt * t * c1[1] + 3 * mt * t * t * c2[1] + t ** 3 * p[1]))
            last_c, cur = c2, p
        elif C in "QT":
            if C == "Q":
                c1 = (num() + ox, num() + oy)
            else:
                c1 = (2 * cur[0] - last_c[0], 2 * cur[1] - last_c[1]) if last_c else cur
            p = (num() + ox, num() + oy)
            for k in range(1, nb + 1):
                t = k / float(nb)
                mt = 1 - t
                poly.append((mt * mt * cur[0] + 2 * mt * t * c1[0] + t * t * p[0], mt * mt * cur[1] + 2 * mt * t * c1[1] + t * t * p[1]))
            last_c, cur = c1, p
        elif C == "A":
            rx, ry, phi, fa, fs = num(), num(), num(), num(), num()
            p = (num() + ox, num() + oy)
            poly += _arc(cur, rx, ry, phi, int(fa), int(fs), p)
            cur = p
            last_c = None
        else:
            raise ValueError("unsupported path command %s" % cmd)
    if poly:
        polys.append(poly)
    return polys


def simplify(pts, tol):
    """Douglas-Peucker on a closed polyline."""
    pts = np.asarray(pts, float)
    if len(pts) < 4:
        return pts

    def dp(a, b):
        if b <= a + 1:
            return [a, b]
        p, q = pts[a], pts[b]
        seg = pts[a + 1:b]
        v = q - p
        L = np.hypot(*v)
        d = np.abs(v[0] * (seg - p)[:, 1] - v[1] * (seg - p)[:, 0]) / L if L > 1e-12 else np.hypot(*(seg - p).T)
        k = int(np.argmax(d))
        if d[k] > tol:
            m = a + 1 + k
            return dp(a, m)[:-1] + dp(m, b)
        return [a, b]
    # split closed loop at the farthest point from the first
    far = int(np.argmax(np.hypot(*(pts - pts[0]).T)))
    idx = dp(0, far)[:-1] + dp(far, len(pts) - 1)
    out = pts[sorted(set(idx))]
    return out


def area(poly):
    p = np.asarray(poly)
    return 0.5 * (np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1)))


def svg_paths(fname, cls=None):
    t = open(fname, encoding="utf8").read()
    out = []
    for m in re.finditer(r"<path ([^>]*)/?>", t):
        attrs = m.group(1)
        c = re.search(r'class="([^"]+)"', attrs)
        d = re.search(r'\sd="([^"]+)"', " " + attrs)
        if d and (cls is None or (c and c.group(1) in cls)):
            out.append((c.group(1) if c else "", d.group(1)))
    return out


def main():
    res = {}
    # ---- arms (2.svg). Frame centre = centre of the 4-hole 10 mm square; scale from that square (9.9 mm)
    f2 = os.path.join(DOCS, "2.svg")
    cx, cy, unit = 82.57, 98.47, 9.9 / 7.98
    arms = []
    for c, d in svg_paths(f2, ("cls-1", "cls-2", "cls-4", "cls-5")):
        polys = path_to_polys(d)
        outer = max(polys, key=lambda p: abs(area(p)))
        mm = [((x - cx) * unit, -(y - cy) * unit) for x, y in outer]
        simp = simplify(mm, 0.08)
        arms.append({"color": c, "outline": [list(map(float, p)) for p in simp], "n_raw": len(mm)})
    res["arms"] = arms
    allp = np.array([p for a in arms for p in a["outline"]])
    res["arms_extent_mm"] = [float(allp[:, 0].min()), float(allp[:, 0].max()), float(allp[:, 1].min()), float(allp[:, 1].max())]
    # ---- battery plate (15_11.svg): largest closed path = outline; scale so its 4 corner holes match the standoffs (65 x 57)
    f15 = os.path.join(DOCS, "15_11.svg")
    polys = []
    for c, d in svg_paths(f15):
        polys += [p for p in path_to_polys(d) if len(p) > 6]
    big = max(polys, key=lambda p: abs(area(p)))
    bb = np.array(big)
    res["battery_plate_raw_extent"] = [float(bb[:, 0].min()), float(bb[:, 0].max()), float(bb[:, 1].min()), float(bb[:, 1].max())]
    # holes: small near-circular loops
    holes = []
    for p in polys:
        a = np.array(p)
        w, h = np.ptp(a[:, 0]), np.ptp(a[:, 1])
        if 1.0 < w < 6 and 0.8 < w / max(h, 1e-6) < 1.25:
            holes.append((float(a[:, 0].mean()), float(a[:, 1].mean()), float(w)))
    res["battery_plate_raw_holes"] = holes
    json.dump(res, open(os.path.join(HERE, "out", "technic_outlines.json"), "w"), indent=1)
    print("arms:", [(a["color"], a["n_raw"], len(a["outline"])) for a in arms])
    print("arms extent mm (x0, x1, y0, y1):", [round(v, 1) for v in res["arms_extent_mm"]])
    print("battery plate raw extent:", [round(v, 2) for v in res["battery_plate_raw_extent"]])
    print("battery plate hole candidates:", [tuple(round(v, 2) for v in h) for h in holes])


if __name__ == "__main__":
    main()
