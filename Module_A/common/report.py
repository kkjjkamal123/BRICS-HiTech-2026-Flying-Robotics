"""
Self-contained HTML mission report (opens offline in any browser, prints to PDF).
No dependencies except numpy/cv2. Python 3.8.

  write_report(path, title, objects, path_xy=None, area=None, meta=None, images_dir=None)
"""
import base64
import datetime
import html
import os

import cv2

COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6", "#9a6324", "#808000", "#000075"]


def _img_tag(path_or_img, width=220):
    try:
        img = cv2.imread(path_or_img) if isinstance(path_or_img, str) else path_or_img
        if img is None:
            return ""
        h, w = img.shape[:2]
        if w > 480:
            img = cv2.resize(img, (480, int(h * 480.0 / w)))
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return '<img src="data:image/jpeg;base64,%s" width="%d">' % (base64.b64encode(buf.tobytes()).decode(), width)
    except Exception:
        return ""


def svg_map(objects, path_xy=None, area=None, size=520, title="aruco_map (m)"):
    """Top-down SVG map: flight path, area, objects coloured by class."""
    xs, ys = [], []
    for o in objects:
        xs.append(o["x"]); ys.append(o["y"])
    if path_xy:
        xs += [p[0] for p in path_xy]; ys += [p[1] for p in path_xy]
    if area:
        xs += [area[0], area[2]]; ys += [area[1], area[3]]
    if not xs:
        return "<p>(no data for map)</p>"
    x0, x1, y0, y1 = min(xs) - 0.5, max(xs) + 0.5, min(ys) - 0.5, max(ys) + 0.5
    span = max(x1 - x0, y1 - y0)
    k = (size - 60) / span

    def P(x, y):  # world -> svg (y up)
        return 40 + (x - x0) * k, size - 30 - (y - y0) * k

    out = ['<svg width="%d" height="%d" style="background:#fafafa;border:1px solid #ccc">' % (size, size)]
    # grid every 1 m
    gx = int(x0)
    while gx <= x1:
        a, b = P(gx, y0); c, d = P(gx, y1)
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#e3e3e3"/>' % (a, b, c, d))
        out.append('<text x="%.1f" y="%d" font-size="10" fill="#888">%d</text>' % (a - 3, size - 15, gx))
        gx += 1
    gy = int(y0)
    while gy <= y1:
        a, b = P(x0, gy); c, d = P(x1, gy)
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#e3e3e3"/>' % (a, b, c, d))
        out.append('<text x="5" y="%.1f" font-size="10" fill="#888">%d</text>' % (b + 3, gy))
        gy += 1
    if area:
        a, b = P(area[0], area[3]); c, d = P(area[2], area[1])
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" stroke="#999" stroke-dasharray="5,4"/>' % (a, b, c - a, d - b))
    if path_xy and len(path_xy) > 1:
        pts = " ".join("%.1f,%.1f" % P(p[0], p[1]) for p in path_xy)
        out.append('<polyline points="%s" fill="none" stroke="#4363d8" stroke-width="1.5" opacity="0.6"/>' % pts)
    names = sorted(set(o["name"] for o in objects))
    for o in objects:
        cx, cy = P(o["x"], o["y"])
        col = COLORS[names.index(o["name"]) % len(COLORS)]
        out.append('<circle cx="%.1f" cy="%.1f" r="7" fill="%s" opacity="0.85"/>' % (cx, cy, col))
        out.append('<text x="%.1f" y="%.1f" font-size="11">#%s</text>' % (cx + 9, cy + 4, o.get("id", "")))
    ly = 15
    for i, n in enumerate(names):
        out.append('<circle cx="%d" cy="%d" r="5" fill="%s"/><text x="%d" y="%d" font-size="12">%s</text>'
                   % (size - 130, ly, COLORS[i % len(COLORS)], size - 120, ly + 4, html.escape(n)))
        ly += 16
    out.append('<text x="40" y="14" font-size="11" fill="#555">%s</text></svg>' % html.escape(title))
    return "\n".join(out)


def write_report(path, title, objects, path_xy=None, area=None, meta=None, extra_html=""):
    meta = meta or {}
    counts = {}
    for o in objects:
        counts[o["name"]] = counts.get(o["name"], 0) + 1
    rows = []
    for o in objects:
        snap = _img_tag(o["snapshot"]) if o.get("snapshot") else ""
        rows.append("<tr><td>%s</td><td><b>%s</b></td><td>%.2f</td><td>%.2f</td><td>%.2f</td><td>%.2f</td><td>%s</td><td>%s</td></tr>" % (
            o.get("id", ""), html.escape(o["name"]), o["x"], o["y"], o.get("z", 0.0), o.get("conf", 0),
            o.get("hits", 1), snap))
    meta_rows = "".join("<tr><th>%s</th><td>%s</td></tr>" % (html.escape(str(k)), html.escape(str(v))) for k, v in meta.items())
    count_rows = "".join("<tr><td>%s</td><td><b>%d</b></td></tr>" % (html.escape(k), v) for k, v in sorted(counts.items()))
    doc = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>%(t)s</title>
<style>body{font-family:Arial,sans-serif;margin:20px;color:#222} table{border-collapse:collapse;margin:8px 0}
th,td{border:1px solid #bbb;padding:4px 8px;text-align:left;vertical-align:top} th{background:#eee}
.row{display:flex;gap:30px;flex-wrap:wrap} h1{margin-bottom:0} .sub{color:#666;margin-top:2px}</style></head><body>
<h1>%(t)s</h1><div class="sub">Generated %(now)s</div>
<div class="row"><div><h2>Summary</h2><table>%(meta)s</table><h3>Objects found</h3><table><tr><th>Class</th><th>Count</th></tr>%(counts)s</table></div>
<div><h2>Map</h2>%(map)s</div></div>
%(extra)s
<h2>Detections</h2><table><tr><th>ID</th><th>Class</th><th>X (m)</th><th>Y (m)</th><th>Z (m)</th><th>Conf</th><th>Hits</th><th>Snapshot</th></tr>%(rows)s</table>
</body></html>""" % {
        "t": html.escape(title), "now": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "meta": meta_rows, "counts": count_rows or "<tr><td colspan=2>none</td></tr>",
        "map": svg_map(objects, path_xy, area), "rows": "".join(rows), "extra": extra_html}
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w") as f:
        f.write(doc)
    # CSV next to it (for Excel / the jury)
    with open(os.path.splitext(path)[0] + ".csv", "w") as f:
        def ts(t):
            return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S") if isinstance(t, (int, float)) and t > 1e9 else ""
        f.write("id,class,x,y,z,conf,hits,first_seen,confirmed,last_seen\n")
        for o in objects:
            f.write("%s,%s,%.3f,%.3f,%.3f,%.3f,%s,%s,%s,%s\n" % (o.get("id", ""), o["name"], o["x"], o["y"], o.get("z", 0), o.get("conf", 0),
                                                         o.get("hits", 1), ts(o.get("first_t")), ts(o.get("confirmed_t")), ts(o.get("last_t"))))
    return path
