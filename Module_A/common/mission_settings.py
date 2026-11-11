"""
Mission settings changed from the BRICS Dashboard without editing the YAML file.

The dashboard starts a mission with one `--set KEY=VALUE` per changed setting, e.g.

    python3 drone/case1_fire.py --config config/case1_fire.yaml \
        --set area=[-2.5,-1.0,2.5,1.0] --set safety.fence=[-3,-1.5,3,1.5] \
        --set altitude=1.5 --set step=auto --set fire_c=100

  KEY       dotted path into the config (`safety.fence`, `inspect.z`, ...), or one of the short names:
            fire_c   = threshold_c of every thermal detector in celsius mode (the "anything >= X C is fire" rule)
            step     = survey line spacing in metres, or `auto` (computed from the camera view + `overlap`)
  VALUE     YAML: numbers, lists [a, b], true / false, text.

`check_settings(cfg)` refuses values that would make the flight unsafe or meaningless (area outside the fence,
altitude above the safety ceiling, ...). Every mission runs it before anything flies, with or without --set.
Python 3.8 compatible.
"""
import yaml

LIMITS = {                       # same limits as the dashboard (Model/MissionSettings.swift, enum Limit)
    "altitude": (0.5, 2.5),      # m (also capped below safety.max_altitude)
    "step": (0.2, 2.0),          # m between survey lines
    "overlap": (0.0, 0.6),
    "speed": (0.1, 0.8),         # m/s
    "fire_c": (40.0, 400.0),     # deg C
}


def parse_value(text):
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return text


def thermal_detectors(cfg):
    return [d for d in cfg.get("detectors") or []
            if isinstance(d, dict) and d.get("type") == "thermal" and d.get("mode", "celsius") == "celsius"]


def fire_threshold(cfg):
    """The fire temperature rule (deg C) of the mission, or None if it has no raw-temperature detector."""
    for d in thermal_detectors(cfg):
        if d.get("threshold_c") is not None:
            return float(d["threshold_c"])
    return None


def apply_overrides(cfg, sets):
    """Applies ["key=value", ...] to cfg in place. Returns [(key, value), ...] that were applied."""
    done = []
    for item in sets or []:
        if "=" not in item:
            raise ValueError("--set %r: expected KEY=VALUE" % item)
        key, raw = item.split("=", 1)
        key, val = key.strip(), parse_value(raw.strip())
        if not key:
            raise ValueError("--set %r: empty key" % item)
        if key == "fire_c":
            dets = thermal_detectors(cfg)
            if not dets:
                raise ValueError("--set fire_c: this mission has no thermal detector in celsius mode")
            for d in dets:
                d["threshold_c"] = float(val)
        elif key == "step" and (val is None or str(val).lower() in ("auto", "none", "")):
            cfg.pop("step", None)
            val = "auto"
        else:
            node, parts = cfg, key.split(".")
            for p in parts[:-1]:
                if not isinstance(node.get(p), dict):
                    node[p] = {}
                node = node[p]
            node[parts[-1]] = val
        done.append((key, val))
    return done


def _box(v, name, problems):
    try:
        b = [float(x) for x in v]
    except (TypeError, ValueError):
        problems.append("%s must be 4 numbers [x0, y0, x1, y1], got %r" % (name, v))
        return None
    if len(b) != 4:
        problems.append("%s must be 4 numbers [x0, y0, x1, y1], got %r" % (name, v))
        return None
    if b[0] >= b[2] or b[1] >= b[3]:
        problems.append("%s %s: x0 must be < x1 and y0 < y1" % (name, b))
        return None
    return b


def _num(cfg, key, problems, lo, hi, value=None):
    v = cfg.get(key) if value is None else value
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        problems.append("%s must be a number, got %r" % (key, v))
        return None
    if not lo <= v <= hi:
        problems.append("%s = %g is outside the allowed %g .. %g" % (key, v, lo, hi))
    return v


def check_settings(cfg):
    """List of problems (empty = fine). Only checks the keys the config actually has."""
    problems = []
    s = cfg.get("safety") or {}
    area = _box(cfg["area"], "area", problems) if cfg.get("area") is not None else None
    fence = None
    f = s.get("fence")
    if isinstance(f, (list, tuple)):
        fence = _box(f, "safety.fence", problems)
    tol = 0.05
    if area and fence and (area[0] < fence[0] - tol or area[1] < fence[1] - tol or
                           area[2] > fence[2] + tol or area[3] > fence[3] + tol):
        problems.append("the scan area %s goes outside the geofence %s - the drone would skip those lines"
                        % (area, fence))
    home = cfg.get("home")
    if home is not None:
        try:
            hx, hy = float(home[0]), float(home[1])
            if fence and not (fence[0] - tol <= hx <= fence[2] + tol and fence[1] - tol <= hy <= fence[3] + tol):
                problems.append("home (%.2f, %.2f) is outside the geofence %s" % (hx, hy, fence))
        except (TypeError, ValueError, IndexError):
            problems.append("home must be [x, y], got %r" % (home,))
    max_alt = float(s.get("max_altitude", 3.0) or 3.0)
    alt = _num(cfg, "altitude", problems, LIMITS["altitude"][0], LIMITS["altitude"][1])
    if alt is not None and alt > max_alt - 0.2:
        problems.append("altitude %.2f m is too close to the safety ceiling safety.max_altitude = %.2f m "
                        "(keep it at least 0.2 m below)" % (alt, max_alt))
    _num(cfg, "step", problems, *LIMITS["step"])
    _num(cfg, "overlap", problems, *LIMITS["overlap"])
    _num(cfg, "speed", problems, *LIMITS["speed"])
    for d in thermal_detectors(cfg):
        if d.get("threshold_c") is not None:
            _num(cfg, "fire_c (thermal threshold_c)", problems, LIMITS["fire_c"][0], LIMITS["fire_c"][1],
                 value=d["threshold_c"])
    return problems


def summary(cfg):
    """One line with the settings the operator can change, for the mission log."""
    parts = []
    if cfg.get("area"):
        a = cfg["area"]
        parts.append("area x %.2f..%.2f y %.2f..%.2f" % (a[0], a[2], a[1], a[3]))
    f = (cfg.get("safety") or {}).get("fence")
    if isinstance(f, (list, tuple)) and len(f) == 4:
        parts.append("fence x %.2f..%.2f y %.2f..%.2f" % (f[0], f[2], f[1], f[3]))
    if cfg.get("home"):
        parts.append("home (%.2f, %.2f)" % (cfg["home"][0], cfg["home"][1]))
    if cfg.get("altitude") is not None:
        parts.append("altitude %.2f m" % float(cfg["altitude"]))
    parts.append("line spacing %s" % ("%.2f m" % float(cfg["step"]) if cfg.get("step")
                                      else "auto (%.0f%% overlap)" % (100 * float(cfg.get("overlap", 0.3)))))
    if cfg.get("speed") is not None:
        parts.append("speed %.2f m/s" % float(cfg["speed"]))
    fc = fire_threshold(cfg)
    if fc is not None:
        parts.append("fire >= %.0f C" % fc)
    return ", ".join(parts)
