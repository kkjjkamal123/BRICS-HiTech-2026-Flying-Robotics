"""
Thermal camera helpers (pure numpy + cv2, Python 3.8).

Many 256x192 USB-C "phone" thermal modules (InfiRay P2 / P2 Pro, TOPDON TC001 and OEM versions, probably also
the Mileseey TR256i given to each team) appear on Linux as a normal UVC camera that delivers a 256x384 YUYV frame:
  top half    (256x192): the image (luma)
  bottom half (256x192): RAW temperature, 16-bit little endian, Kelvin * 64
Read it with OpenCV and CAP_PROP_CONVERT_RGB = 0 to get the raw bytes, then decode_p2() -> temperature in deg C.
If a camera only gives a normal picture, use the brightness-based ThermalDetector modes instead.
"""
import math

import cv2
import numpy as np


def decode_p2(raw, width=256, height=192):
    """
    raw: frame from cv2.VideoCapture with CONVERT_RGB=0 (any shape with width*height*2*2 bytes).
    Returns (image_bgr uint8, temp_c float32 [height, width]) or (None, None) if the layout doesn't fit.
    """
    a = np.asarray(raw)
    n = a.size
    if n != width * height * 2 * 2:
        return None, None
    a = a.reshape(height * 2, width, 2)
    top, bottom = a[:height], a[height:]
    t16 = bottom[:, :, 0].astype(np.uint16) | (bottom[:, :, 1].astype(np.uint16) << 8)
    temp = t16.astype(np.float32) / 64.0 - 273.15
    med = float(np.median(temp))
    if not (-40.0 < med < 120.0):           # not a P2-style raw frame
        return None, None
    img = colorize(temp)
    return img, temp


def colorize(temp, lo=None, hi=None):
    """Temperature map -> false-colour BGR image (INFERNO), auto range unless lo/hi given."""
    t = np.asarray(temp, dtype=np.float32)
    lo = float(np.percentile(t, 1)) if lo is None else lo
    hi = float(np.percentile(t, 99.9)) if hi is None else hi
    g = np.clip((t - lo) / max(1e-3, hi - lo) * 255.0, 0, 255).astype(np.uint8)
    return cv2.applyColorMap(g, cv2.COLORMAP_INFERNO)


def annotate(img, temp):
    """Draw max temperature crosshair + text (for live view / probe)."""
    out = img.copy()
    y, x = np.unravel_index(int(np.argmax(temp)), temp.shape)
    sx, sy = out.shape[1] / float(temp.shape[1]), out.shape[0] / float(temp.shape[0])
    cx, cy = int(x * sx), int(y * sy)
    cv2.drawMarker(out, (cx, cy), (255, 255, 255), cv2.MARKER_CROSS, 14, 2)
    cv2.putText(out, "max %.1fC  median %.1fC" % (float(temp.max()), float(np.median(temp))), (4, 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    return out


def hot_regions(temp, fire_c=100.0, min_area=4):
    """Boxes (x1, y1, x2, y2, max_c) of connected areas at or above fire_c, in temperature-map pixels."""
    mask = (np.asarray(temp) >= fire_c).astype(np.uint8)
    if not mask.any():
        return []
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if area >= min_area:
            out.append((int(x), int(y), int(x + w - 1), int(y + h - 1), float(temp[lab == i].max())))
    return out


def render_view(temp, fire_c=100.0, scale=2, bar=58):
    """
    Operator picture of a temperature map: false colour, a temperature scale on the right (deg C), the hottest
    point marked with its value, and every area at or above fire_c boxed and labelled FIRE.
    Returns (bgr image, info) with info = {"max_c", "min_c", "fire", "regions"}.
    """
    t = np.asarray(temp, dtype=np.float32)
    h, w = t.shape
    tmax, tmin = float(t.max()), float(t.min())
    lo = math.floor(float(np.percentile(t, 1)))
    # The colour scale covers the scene BELOW the fire threshold, so people and warm objects stay visible when a
    # fire is in view; everything at or above fire_c is painted solid white-hot and boxed with its temperature.
    cool = t[t < fire_c]
    top_c = float(cool.max()) if cool.size else fire_c
    hi = math.ceil(min(fire_c, max(top_c, lo + 6.0)))    # at least a 6 C span, so a flat scene is not all noise
    hi = max(hi, lo + 1)
    small = colorize(t, lo, hi)
    small[t >= fire_c] = (255, 255, 255)
    img = cv2.resize(small, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
    regions = hot_regions(t, fire_c)
    for x1, y1, x2, y2, m in regions:
        p1, p2 = (x1 * scale - 3, y1 * scale - 3), ((x2 + 1) * scale + 3, (y2 + 1) * scale + 3)
        cv2.rectangle(img, p1, p2, (255, 255, 255), 3)
        cv2.rectangle(img, p1, p2, (0, 0, 255), 2)
        _label(img, "FIRE %.0fC" % m, (max(2, p1[0]), max(16, p1[1] - 6)), (0, 0, 255))
    y, x = np.unravel_index(int(np.argmax(t)), t.shape)
    cx, cy = int((x + 0.5) * scale), int((y + 0.5) * scale)
    cv2.drawMarker(img, (cx, cy), (255, 255, 255), cv2.MARKER_CROSS, 16, 2)
    if not regions:
        _label(img, "%.1fC" % tmax, (min(img.shape[1] - 70, cx + 10), max(16, cy - 8)), (255, 255, 255))
    _label(img, "max %.1fC   min %.1fC" % (tmax, tmin), (6, img.shape[0] - 8), (255, 255, 255))
    if regions:
        _label(img, "FIRE  >= %.0fC" % fire_c, (6, 20), (0, 0, 255), 0.6)

    # temperature scale: hot at the top
    H = img.shape[0]
    strip = np.zeros((H, bar, 3), np.uint8)
    top, bottom = 44, H - 14
    # cap of the scale: the fire band
    cv2.rectangle(strip, (6, 14), (21, 38), (255, 255, 255) if regions else (70, 70, 70), -1)
    cv2.rectangle(strip, (6, 14), (21, 38), (0, 0, 255), 2 if regions else 1)
    cv2.putText(strip, ">%.0f" % fire_c, (24, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 0, 255) if regions else (150, 150, 150), 1, cv2.LINE_AA)
    cv2.putText(strip, "FIRE", (24, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (0, 0, 255) if regions else (150, 150, 150), 1, cv2.LINE_AA)
    ramp = np.linspace(255, 0, bottom - top).astype(np.uint8).reshape(-1, 1)
    strip[top:bottom, 6:22] = cv2.applyColorMap(np.repeat(ramp, 16, axis=1), cv2.COLORMAP_INFERNO)
    cv2.rectangle(strip, (6, top), (21, bottom - 1), (160, 160, 160), 1)

    def ypos(v):
        return int(bottom - (v - lo) / float(hi - lo) * (bottom - top))
    for v in np.linspace(lo, hi, 5):
        yy = ypos(v)
        cv2.line(strip, (22, yy), (26, yy), (200, 200, 200), 1)
        cv2.putText(strip, "%.0f" % v, (28, min(H - 3, max(10, yy + 4))), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (230, 230, 230), 1, cv2.LINE_AA)
    cv2.putText(strip, "deg C", (4, 10), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (200, 200, 200), 1, cv2.LINE_AA)
    return np.hstack([img, strip]), {"max_c": tmax, "min_c": tmin, "fire": bool(regions), "regions": regions}


def _label(img, text, org, color, size=0.5):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, size, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, size, color, 1, cv2.LINE_AA)
