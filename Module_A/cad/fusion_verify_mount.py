"""
Verification of the TR256i mount in the ACTIVE Fusion design (run after fusion_thermal_mount.py).
Checks: feature health, solid validity, module fit (contact only at crush ribs), lens field of view for every
possible lens position, print overhangs, mass. Prints PASS/FAIL lines. Modifies nothing in the design.
"""
import math

import adsk.core
import adsk.fusion

FOV_HALF_DEG = 28.0     # TR256i ~56 deg horizontal field of view -> 28 deg half angle (worst case used for all directions)
LENS_R = 3.0            # lens aperture radius (mm)
LENS_INSET = 6.0        # lens centre at least this far from the module edges (housing bezel)


def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    up = design.userParameters
    g = lambda n: up.itemByName(n).value * 10.0          # mm
    ok_all = True

    def report(name, ok, info=""):
        nonlocal ok_all
        ok_all = ok_all and ok
        print("%s  %-46s %s" % ("PASS" if ok else "FAIL", name, info))

    # 1 timeline health
    bad = []
    for i in range(design.timeline.count):
        it = design.timeline.item(i)
        if it.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
            bad.append("%s: %s" % (it.name, it.errorOrWarningMessage))
    report("timeline: all features healthy", not bad, "; ".join(bad) or "%d features" % design.timeline.count)

    for mount_occ in [o for o in root.occurrences if o.component.name.startswith("Thermal Mount")]:
        forward = "forward" in mount_occ.component.name
        tag = "FORWARD" if forward else "DOWN"
        mod_occ = [o for o in root.occurrences if o.component.name.startswith("TR256i") and
                   (("forward" in o.component.name) == forward)][0]
        check_part(design, g, report, mount_occ, mod_occ, forward, tag)
    print("RESULT:", "ALL CHECKS PASSED" if ok_all else "SOME CHECKS FAILED")


def forward_matrix(g):
    m = adsk.core.Matrix3D.create()
    m.setWithCoordinateSystem(adsk.core.Point3D.create(0, 0, -(g("mod_W") + 2 * g("clr") + 2 * g("wall")) / 20.0),
                              adsk.core.Vector3D.create(0, 1, 0), adsk.core.Vector3D.create(0, 0, -1),
                              adsk.core.Vector3D.create(-1, 0, 0))
    return m


def check_part(design, g, report0, mount_occ, mod_occ, forward, tag):
    report = lambda name, ok, info="": report0("[%s] %s" % (tag, name), ok, info)
    mount = mount_occ.bRepBodies.item(0)                      # proxy, world coordinates
    world = mount_occ.transform2.copy()
    report("mount: single solid body", mount_occ.bRepBodies.count == 1 and mount.isSolid,
           "bodies=%d solid=%s" % (mount_occ.bRepBodies.count, mount.isSolid))
    vol_cm3 = mount.volume
    report("mount: mass (PETG 1.27 g/cm3) < 30 g", vol_cm3 * 1.27 < 30, "%.1f g  (%.2f cm3)" % (vol_cm3 * 1.27, vol_cm3))
    # fit
    body = [b for b in mod_occ.bRepBodies if b.name == "TR256i body"][0]
    coll = adsk.core.ObjectCollection.create()
    coll.add(mount)
    coll.add(body)
    res = design.analyzeInterference(design.createInterferenceInput(coll))
    rib_vol_expected = 4 * g("rib_int") * 1.2 * g("mod_T")
    tot, centers = 0.0, []
    inv = world.copy()
    inv.invert()
    loc = forward_matrix(g) if forward else adsk.core.Matrix3D.create()
    loc_inv = loc.copy()
    loc_inv.invert()
    for r in res:
        ib = r.interferenceBody
        tot += ib.volume * 1000.0
        for lump in ib.lumps:
            bb = lump.boundingBox
            c = adsk.core.Point3D.create((bb.minPoint.x + bb.maxPoint.x) / 2, (bb.minPoint.y + bb.maxPoint.y) / 2,
                                         (bb.minPoint.z + bb.maxPoint.z) / 2)
            c.transformBy(inv)                     # world -> component
            c.transformBy(loc_inv)                 # component -> 'down' design frame
            centers.append((c.x * 10, c.y * 10))
    X1 = (g("mod_L") + g("clr")) / 2.0
    ribs_x = (X1 - 5.0, X1 - 15.0)
    only_ribs = all(min(abs(cx - rx) for rx in ribs_x) < 1.0 and abs(abs(cy) - (g("mod_W") / 2 + g("clr"))) < 1.0
                    for cx, cy in centers)
    report("fit: module touches ONLY the 4 crush ribs", only_ribs and len(centers) == 4 and tot <= rib_vol_expected,
           "%d contacts, %.2f mm3 (<= %.2f) at %s" % (len(centers), tot, rib_vol_expected,
                                                      ", ".join("(%.1f,%.1f)" % c for c in centers)))
    # field of view (cones built in the 'down' frame, mapped to world)
    tbm = adsk.fusion.TemporaryBRepManager.get()
    to_world = loc.copy()
    to_world.transformBy(world)
    z_face = -(g("mod_T") + g("clr_t"))
    X0 = -X1
    xs = [X0 + LENS_INSET + i * (g("mod_L") - 2 * LENS_INSET) / 8.0 for i in range(9)]
    ys = [-g("mod_W") / 2 + LENS_INSET + j * (g("mod_W") - 2 * LENS_INSET) / 4.0 for j in range(5)]
    L = 40.0
    hits = []
    for x in xs:
        for y in ys:
            p1 = adsk.core.Point3D.create(x / 10, y / 10, z_face / 10)
            p2 = adsk.core.Point3D.create(x / 10, y / 10, (z_face - L) / 10)
            cone = tbm.createCylinderOrCone(p1, LENS_R / 10, p2, (LENS_R + L * math.tan(math.radians(FOV_HALF_DEG))) / 10)
            tbm.transform(cone, to_world)
            m = tbm.copy(mount)
            tbm.booleanOperation(m, cone, adsk.fusion.BooleanTypes.IntersectionBooleanType)
            v = m.volume * 1000.0
            if v > 1e-4:
                hits.append((round(x, 1), round(y, 1), round(v, 3)))
    report("view: 56 deg cone clear for all lens positions", not hits,
           "%d positions%s" % (len(xs) * len(ys), ("  BLOCKED " + str(hits[:6])) if hits else ""))
    need = g("lip_t") * math.tan(math.radians(FOV_HALF_DEG))
    avail = LENS_INSET - LENS_R - (g("lip_w") - g("clr"))
    report("view: margin at the lip edge (worst case)", avail >= need, "available %.2f mm vs needed %.2f mm" % (avail, need))
    # printability: printed with the mounting-plate top face on the bed (world +Z normal faces become overhangs)
    up = adsk.core.Vector3D.create(0, 0, 1)
    zbed = None
    faces = []
    for f in mount.faces:
        ok_n, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
        if ok_n:
            faces.append((f, n))
    zbed = max(f.pointOnFace.z for f, n in faces if n.z > 0.999)
    over = []
    for f, n in faces:
        if n.z > math.cos(math.radians(45)) and abs(f.pointOnFace.z - zbed) > 1e-4:
            bb = f.boundingBox
            bspan = min(bb.maxPoint.x - bb.minPoint.x, bb.maxPoint.y - bb.minPoint.y) * 10
            perim = sum(e.length for e in f.edges) * 10
            strip = 4.0 * f.area * 100 / perim if perim > 0 else bspan     # upper bound of the true unsupported width
            span = min(bspan, strip)                                       # (rings/strips: ~2x width, rectangles: <= 2x short side)
            over.append((round(f.pointOnFace.z * 10, 2), round(span, 1), round(f.area * 100, 1)))
    lip_ok = all(sp <= 15.0 for z, sp, a in over)
    report("print: overhangs/bridges all <= 15 mm span (no supports)", lip_ok,
           "%d faces (z, shortest span, area): %s" % (len(over), over))
    # slots: strap / zip tie / nut path under every hole in the mounting plate must be free (6 mm below the plate)
    top_face = max([f for f, n in faces if n.z > 0.999], key=lambda f: f.pointOnFace.z)
    blocked, n_loops = [], 0
    for lp in top_face.loops:
        if lp.isOuter:
            continue
        n_loops += 1
        xs = [v.geometry.x for e in lp.edges for v in (e.startVertex, e.endVertex)]
        ys = [v.geometry.y for e in lp.edges for v in (e.startVertex, e.endVertex)]
        cx_, cy_ = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        w_, h_ = max(max(xs) - min(xs) - 0.02, 0.01), max(max(ys) - min(ys) - 0.02, 0.01)
        zt = zbed - g("plate_t") / 10.0
        box = tbm.createBox(adsk.core.OrientedBoundingBox3D.create(adsk.core.Point3D.create(cx_, cy_, zt - 0.31),
                            adsk.core.Vector3D.create(1, 0, 0), adsk.core.Vector3D.create(0, 1, 0), w_, h_, 0.6))
        m = tbm.copy(mount)
        tbm.booleanOperation(m, box, adsk.fusion.BooleanTypes.IntersectionBooleanType)
        if m.volume * 1000 > 0.05:
            blocked.append((round(cx_ * 10, 1), round(cy_ * 10, 1), round(m.volume * 1000, 1)))
    report("slots: path under every plate hole is free (6 mm)", not blocked,
           "%d holes checked%s" % (n_loops, ("  BLOCKED (x, y, mm3): " + str(blocked)) if blocked else ""))
    bb = mount.boundingBox
    report("print: size", True, "%.1f x %.1f x %.1f mm" % ((bb.maxPoint.x - bb.minPoint.x) * 10,
                                                           (bb.maxPoint.y - bb.minPoint.y) * 10, (bb.maxPoint.z - bb.minPoint.z) * 10))
    report("drone: hangs below the mounting surface", True, "%.1f mm (check landing-gear clearance)" % ((zbed - bb.minPoint.z) * 10))
