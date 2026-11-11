"""Interference check of the TECHNIC 6S detailed assembly (all bodies incl. every wire). Reports overlaps > 0.3 mm3.
Wires may only touch the parts listed as their cable ends (cad/out/technic6s_harness.json) and their own neighbour cores."""
import json
import os

import adsk.core
import adsk.fusion

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = os.environ.get("BRICS_CAD_DIR", os.path.expanduser("~/BRICS-HiTech-2026-Flying-Robotics/Module_A/cad"))
INTENDED = [("Arm", "Arm"), ("Arm", "Centre plate"), ("Standoff L35", "Battery plate"),
            ("Battery strap", "Battery 4S"), ("Battery strap", "Battery plate"),
            ("FC damper", "Flight controller PCB"), ("FC damper", "Nylon standoff M3x8"), ("FC damper", "Screw M3 (FC)"),
            ("40-pin header (male)", "40-pin header (female)"), ("USB-A plug", "USB-A double"),
            ("LED chips", "LED strip"), ("Orange Pi mount", "LED strip"), ("WiFi antenna", "WiFi antenna holder"),
            ("Motor bell", "Motor base"), ("Shaft M5", "M5 nut"), ("Shaft M5", "Propeller"), ("M5 nut", "Propeller"),
            ("Guard", "Guard"), ("Guard clip", "Arm"), ("Screw M3x8 (jumper)", "Guard"), ("Screw M3x12 (guard)", "Guard clip"),
            ("Screw M3x12 (guard)", "Arm"), ("Screw M3x20 (gear mount)", "Motor base"), ("Screw M3x20 (gear mount)", "Arm"),
            ("Screw M3x20 (gear mount)", "Landing gear mount"), ("Screw M3x20 (gear mount)", "Gear mount spacer"),
            ("Leg (TPU)", "Landing gear mount"), ("Screw M3x14 (leg)", "Leg (TPU)"), ("Screw M3x14 (leg)", "Landing gear mount"),
            ("Gear mount spacer", "Arm"), ("Gear mount spacer", "Landing gear mount"),
            ("TR256i body", "Thermal Mount"), ("Lens", "TR256i body"), ("USB-C plug", "TR256i body")]
LIMIT = 0.3   # mm3


def run(_context: str):
    design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    top = [o for o in design.rootComponent.occurrences if o.component.name.startswith("TECHNIC 6S")][0]
    meta = json.load(open(os.path.join(HERE, "out", "technic6s_harness.json")))
    wires, cables = meta["wires"], meta["cables"]
    coll = adsk.core.ObjectCollection.create()
    for o in list(top.childOccurrences):
        for b in o.bRepBodies:
            coll.add(b)
    res = design.analyzeInterference(design.createInterferenceInput(coll))
    bad, ok, wire_contacts, deep = [], 0, 0, []

    def allowed(a, b):
        if any((a.startswith(x) and b.startswith(y)) or (b.startswith(x) and a.startswith(y)) for x, y in INTENDED):
            return True
        for w, other in ((a, b), (b, a)):
            if w in wires:
                c = wires[w]
                if other in wires and wires[other] == c:
                    return True
                if any(other.startswith(e) for e in cables[c]["ends"]):
                    return True
        return False
    for r in res:
        v = r.interferenceBody.volume * 1000
        a, b = r.entityOne.name, r.entityTwo.name
        if allowed(a, b):
            ok += 1
            if a in wires or b in wires:
                wire_contacts += 1
                if v > 2.5 and not (a in wires and b in wires):
                    deep.append("%s  <->  %s : %.2f mm3" % (a, b, v))
        elif v > LIMIT:
            bad.append("%s  <->  %s : %.2f mm3" % (a, b, v))
        else:
            ok += 1
    print("bodies checked: %d (wires: %d in %d cables), intended/negligible contacts: %d (wire ends: %d), UNINTENDED overlaps: %d"
          % (coll.count, len(wires), len(cables), ok, wire_contacts, len(bad)))
    for x in sorted(bad):
        print("  ", x)
    print("wire end contacts deeper than 2.5 mm3 (review): %d" % len(deep))
    for x in sorted(deep):
        print("  ", x)
