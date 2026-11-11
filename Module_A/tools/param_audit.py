#!/usr/bin/env python3
"""
Safety audit of an ArduCopter parameter file (e.g. the Cube Orange+ backup) - offline, standard library only.

  python tools/param_audit.py ../cube_params_backup_original.csv
  python tools/param_audit.py params.csv --write-safe safe_changes.param --cells 3

Reads Mission Planner / MAVProxy files (NAME,VALUE or NAME VALUE per line, '#' comments) and QGroundControl
.params files (tab separated: vehicle, component, NAME, VALUE, type). The input file is NEVER modified.

Exit code: 0 = no FAIL findings, 1 = at least one FAIL (do not fly), 2 = file could not be read.
--write-safe writes ONLY the parameters that must change (Mission Planner .param format: NAME,VALUE) so they
can be loaded with Mission Planner / MAVProxy, or typed into QGC > Parameters by hand.
Values are for manual flying WITHOUT GPS (Stabilize / AltHold / Land), as in 4_Cube_FirstFlight_Checklist.md.
"""
import argparse
import os
import sys

GPS_MODES = {3: "Auto", 4: "Guided", 5: "Loiter", 6: "RTL", 14: "Flip?", 16: "PosHold", 17: "Brake", 21: "SmartRTL",
             23: "Follow", 24: "ZigZag", 27: "Auto RTL"}
MODE_NAMES = {0: "Stabilize", 1: "Acro", 2: "AltHold", 3: "Auto", 4: "Guided", 5: "Loiter", 6: "RTL", 7: "Circle",
              9: "Land", 11: "Drift", 13: "Sport", 15: "AutoTune", 16: "PosHold", 17: "Brake", 18: "Throw",
              21: "SmartRTL", 22: "FlowHold"}
ARM_SWITCH = {41: "ArmDisarm (old)", 153: "ArmDisarm", 154: "ArmDisarm with AirMode"}


def load_params(path):
    """Returns {NAME: float}. Raises ValueError if nothing could be parsed."""
    params = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "\t" in line and len(line.split("\t")) >= 4:          # QGC: vehicle comp NAME VALUE [type]
                parts = line.split("\t")
                name, val = parts[2], parts[3]
            else:
                parts = line.replace(",", " ").split()
                if len(parts) < 2:
                    continue
                name, val = parts[0], parts[1]
            try:
                params[name.strip().upper()] = float(val)
            except ValueError:
                continue
    if not params:
        raise ValueError("no parameters found in %s" % path)
    return params


def audit(p, cells=None):
    """
    Returns (findings, safe) where findings = [(level, name, message)], level in FAIL / WARN / INFO,
    and safe = {NAME: value} - the changes needed for a safe manual first flight without GPS.
    """
    out, safe = [], {}

    def g(name, default=None):
        return p.get(name, default)

    def add(level, name, msg, fix=None):
        out.append((level, name, msg))
        if fix is not None:
            safe[name] = fix

    # --- arming checks
    if "ARMING_SKIPCHK" in p:                                     # ArduPilot 4.7+: bitmask of checks to SKIP
        if g("ARMING_SKIPCHK") != 0:
            add("FAIL", "ARMING_SKIPCHK", "= %g: pre-arm checks are skipped (-1 = ALL off) - it will arm with broken "
                "sensors / bad calibration. Set 0." % g("ARMING_SKIPCHK"), 0)
    elif "ARMING_CHECK" in p and g("ARMING_CHECK") != 1:          # older firmware: 1 = all checks
        add("FAIL", "ARMING_CHECK", "= %g: not all pre-arm checks are enabled. Set 1." % g("ARMING_CHECK"), 1)

    # --- RC failsafe
    gps = g("GPS1_TYPE", g("GPS_TYPE", 1)) != 0
    fs = g("FS_THR_ENABLE")
    if fs is not None:
        if fs == 0:
            add("FAIL", "FS_THR_ENABLE", "= 0: NO radio failsafe - if the transmitter link is lost the drone keeps "
                "the last stick values and can fly away. Set 3 (Land).", 3)
        elif fs in (1, 4, 6) and not gps:
            add("WARN", "FS_THR_ENABLE", "= %g asks for RTL but there is no GPS: it falls back to Land anyway. "
                "Set 3 (Land) to make that explicit." % fs, 3)
    thr_min, fs_val = g("RC%d_MIN" % int(g("RCMAP_THROTTLE", 3)), 1000), g("FS_THR_VALUE", 975)
    if fs_val is not None and thr_min is not None and fs_val > thr_min - 10:
        add("WARN", "FS_THR_VALUE", "= %g is not at least 10 below the throttle minimum (%g): normal low throttle could "
            "trigger the failsafe, or the receiver's failsafe value may not be below it." % (fs_val, thr_min))

    # --- battery
    mon = g("BATT_MONITOR", 0)
    if mon == 0:
        add("WARN", "BATT_MONITOR", "= 0: no battery monitor -> no low-voltage failsafe and no voltage in QGC. "
            "Fit a power module (BATT_MONITOR = 4 for an analog PM), until then use a LiPo alarm + short flights.")
    else:
        if g("BATT_FS_LOW_ACT", 0) == 0:
            add("FAIL", "BATT_FS_LOW_ACT", "= 0: low battery does nothing. Set 1 (Land) without GPS.", 1)
        if g("BATT_FS_CRT_ACT", 0) == 0:
            add("FAIL", "BATT_FS_CRT_ACT", "= 0: critical battery does nothing. Set 1 (Land).", 1)
        if cells:
            for name, per_cell in (("BATT_LOW_VOLT", 3.5), ("BATT_CRT_VOLT", 3.3)):
                want = round(per_cell * cells, 2)
                if abs(g(name, 0) - want) > 0.25:
                    add("WARN", name, "= %g, expected about %.2f V for %dS (%.1f V/cell)" % (g(name, 0), want, cells, per_cell), want)
        elif g("BATT_LOW_VOLT", 0) == 0:
            add("WARN", "BATT_LOW_VOLT", "= 0: low-battery threshold not set (use 3.5 V x cells, pass --cells N)")

    # --- other failsafes / landing
    if g("DISARM_DELAY", 10) == 0:
        add("WARN", "DISARM_DELAY", "= 0: never auto-disarms after landing (props keep spinning at idle). Set 10.", 10)
    if g("FS_CRASH_CHECK", 1) == 0:
        add("WARN", "FS_CRASH_CHECK", "= 0: no automatic disarm after a crash. Set 1.", 1)
    if g("FS_VIBE_ENABLE", 1) == 0:
        add("INFO", "FS_VIBE_ENABLE", "= 0 (vibration failsafe off; only acts in position modes). Default 1.", 1)
    if g("LOG_BACKEND_TYPE", 1) == 0:
        add("WARN", "LOG_BACKEND_TYPE", "= 0: no flight logs (nothing to analyse after a crash). Set 1 once a microSD card is fitted.")
    if g("FENCE_ENABLE", 0) != 0 and not gps:
        add("WARN", "FENCE_ENABLE", "= %g without GPS: a horizontal fence needs a position; it may block arming." % g("FENCE_ENABLE"))

    # --- switches and flight modes
    for i in range(1, 17):
        opt = g("RC%d_OPTION" % i)
        if opt in ARM_SWITCH:
            add("INFO", "RC%d_OPTION" % i, "= %g %s: channel %d HIGH (>1800 us) arms, LOW disarms (also in flight). "
                "Check in QGC > Radio which switch position is HIGH." % (opt, ARM_SWITCH[opt], i))
        elif opt == 31:
            add("WARN", "RC%d_OPTION" % i, "= 31 Motor Emergency Stop: motors stop while channel %d is HIGH (>1800 us). "
                "Make sure it is on a switch you know, or that RC%d reads below 1800 at all times (or set 0)." % (i, i))
    ch = int(g("FLTMODE_CH", 5))
    modes = [int(g("FLTMODE%d" % k, 0)) for k in range(1, 7)]
    names = ", ".join("%d=%s" % (k + 1, MODE_NAMES.get(m, str(m))) for k, m in enumerate(modes))
    add("INFO", "FLTMODE1-6", "channel %d: %s (low PWM -> FLTMODE1, ~1500 -> FLTMODE4, high -> FLTMODE6)" % (ch, names))
    if not gps:
        bad = sorted(set(GPS_MODES[m] for m in modes if m in GPS_MODES))
        if bad:
            add("WARN", "FLTMODE1-6", "GPS modes selected without GPS: %s - the switch will be refused / jump to Land." % ", ".join(bad))
    if g("ARMING_RUDDER", 2) != 0:
        add("INFO", "ARMING_RUDDER", "= %g: throttle down + yaw right ~2 s arms%s." % (
            g("ARMING_RUDDER"), ", yaw left disarms (landed only)" if g("ARMING_RUDDER") == 2 else ""))
    if g("BRD_SAFETY_DEFLT", 1) == 0:
        add("INFO", "BRD_SAFETY_DEFLT", "= 0: no safety switch - motors can spin as soon as it is armed.")
    if g("MOT_PWM_TYPE", 0) == 0:
        add("INFO", "MOT_PWM_TYPE", "= 0 (normal PWM ESCs): calibrate the ESCs once (props OFF).")
    return out, safe


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("params", help="parameter file (.csv / .param / .params)")
    ap.add_argument("--cells", type=int, help="LiPo cell count, for the battery thresholds")
    ap.add_argument("--write-safe", metavar="FILE", help="write only the required changes (NAME,VALUE)")
    a = ap.parse_args(argv)
    try:
        p = load_params(a.params)
    except (OSError, ValueError) as e:
        print("cannot read parameters: %s" % e)
        return 2
    findings, safe = audit(p, a.cells)
    print("%d parameters read from %s" % (len(p), a.params))
    for level in ("FAIL", "WARN", "INFO"):
        for lv, name, msg in findings:
            if lv == level:
                print("  %-4s %-16s %s" % (lv, name, msg))
    n_fail = sum(1 for f in findings if f[0] == "FAIL")
    print("RESULT: %s (%d FAIL, %d WARN)" % ("DO NOT FLY - fix the FAIL items" if n_fail else "no blocking problems",
                                             n_fail, sum(1 for f in findings if f[0] == "WARN")))
    if a.write_safe:
        if os.path.abspath(a.write_safe) == os.path.abspath(a.params):
            print("refusing to overwrite the input file")
            return 2
        with open(a.write_safe, "w") as f:
            f.write("# safe changes from tools/param_audit.py for %s\n" % os.path.basename(a.params))
            for k in sorted(safe):
                f.write("%s,%g\n" % (k, safe[k]))
        print("-> %d changes written to %s" % (len(safe), a.write_safe))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
