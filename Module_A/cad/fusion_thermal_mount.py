"""
BRICS Aerial Robotics - TR256i thermal camera mount for TECHNIC 6S  (Autodesk Fusion API script)

Run in Fusion: Utilities > Scripts and Add-Ins > + (this file) > Run.   Creates a NEW design document with:
  * "Thermal Mount (print)"   - one-piece mount, prints WITHOUT supports (plate face on the bed)
  * "TR256i (reference)"      - the thermal module, for fit checks / renders (not printed)
Edit the MEASUREMENTS below (calipers!) and re-run. All main dimensions are also Fusion user parameters.

Design:
  - module slides in from the USB-C end against a stop wall; 4 crush ribs give a press fit; the USB cable is
    zip-tied to the anchor tab, so the module cannot slide out
  - thin lips (1.4 mm) hold the module edges; the window edges are chamfered so the lens field of view is free
  - plate attaches to the drone with the venue velcro straps (15 mm), zip ties, or M3 screws in slots
"""
import math

import adsk.core
import adsk.fusion

# ----------------------------------------------------------------------------- MEASUREMENTS (mm)
P = {
    "mod_L": 56.6,      # TR256i body length (without USB-C plug)
    "mod_W": 34.4,      # body width
    "mod_T": 12.1,      # body thickness
    "clr": 0.35,        # side clearance per side (FDM)
    "clr_t": 0.40,      # clearance above the module
    "wall": 2.2,        # side / stop wall thickness
    "lip_w": 2.2,       # how far the lips reach under the module edges
    "lip_t": 1.4,       # lip thickness (thin = more field of view)
    "plate_t": 2.5,     # mounting plate thickness
    "wing": 21.0,       # plate wing width each side (velcro/zip-tie/M3 slots)
    "margin_x": 3.0,    # plate margin behind the stop wall
    "tab_x": 12.0,      # cable anchor tab length at the open end
    "rib_int": 0.15,    # crush rib interference per side
    "strap_w": 15.0,    # velcro strap width (venue: 15 mm)
}
SHOW_MODULE = True
BUILD_FORWARD = True       # also build the forward-looking mount (Case 4: power-line inspection)
REUSE_ACTIVE = False       # True = rebuild inside the active design (deletes its components) instead of a new document
LENS_FROM_FAR_END = 10.0   # reference model only: lens centre distance from the stop end (unknown on the real module)


def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not (REUSE_ACTIVE and design and design.rootComponent.occurrences.count
            and design.rootComponent.occurrences.item(0).component.name.startswith("Thermal Mount")):
        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
    design.designType = adsk.fusion.DesignTypes.ParametricDesignType
    root = design.rootComponent
    # rebuild: remove previous components - assemblies that USE the mounts (drone) first, then the mounts.
    # Never loop on a deletion that fails (that would freeze Fusion): bounded passes + explicit error.
    for _ in range(3):
        occs = sorted(list(root.occurrences), key=lambda o: 0 if o.component.name.startswith("TECHNIC") else 1)
        for o in occs:
            o.deleteMe()
        if root.occurrences.count == 0:
            break
    if root.occurrences.count:
        raise RuntimeError("could not delete %d old components - run with REUSE_ACTIVE = False (new document)"
                           % root.occurrences.count)
    um = design.userParameters
    for _ in range(um.count):
        if um.count == 0 or not um.item(um.count - 1).deleteMe():
            break
    for k, v in P.items():
        um.add(k, adsk.core.ValueInput.createByString("%s mm" % v), "mm", "TR256i mount")
    derived = {
        "cav_L": "mod_L + clr", "cav_W": "mod_W + 2 * clr", "cav_H": "mod_T + clr_t",
        "cr_W": "mod_W + 2 * clr + 2 * wall", "cr_H": "mod_T + clr_t + lip_t",
    }
    for k, e in derived.items():
        um.add(k, adsk.core.ValueInput.createByString(e), "mm", "derived")
    d = dict(P)
    d["cav_L"] = P["mod_L"] + P["clr"]
    d["cav_W"] = P["mod_W"] + 2 * P["clr"]
    d["cav_H"] = P["mod_T"] + P["clr_t"]
    d["cr_W"] = d["cav_W"] + 2 * P["wall"]
    d["cr_H"] = d["cav_H"] + P["lip_t"]

    # ---- 1) nadir mount (Case 1: camera looks DOWN)
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    comp = occ.component
    comp.name = "Thermal Mount (print) - looking down"
    build_cradle(comp, d, wings=True)
    body = comp.bRepBodies.item(0)
    body.name = "Thermal Mount DOWN"
    if SHOW_MODULE:
        build_module(root, d, adsk.core.Matrix3D.create(), "TR256i (reference) - down")
    msg = ["DOWN mount: %.2f cm3, %.1f g PETG" % (body.volume, body.volume * 1.27)]

    # ---- 2) forward mount (Case 4: camera looks FORWARD, +X = drone nose)
    if BUILD_FORWARD:
        off = adsk.core.Matrix3D.create()
        off.translation = adsk.core.Vector3D.create(0, cm(140), 0)          # placed beside the first part (at the end)
        occ2 = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        comp2 = occ2.component
        comp2.name = "Thermal Mount (print) - looking forward"
        build_cradle(comp2, d, wings=False)
        unit = comp2.bRepBodies.item(0)
        rot = forward_matrix(d)
        bodies = adsk.core.ObjectCollection.create()
        bodies.add(unit)
        mi = comp2.features.moveFeatures.createInput2(bodies)
        mi.defineAsFreeMove(rot)
        comp2.features.moveFeatures.add(mi)
        build_forward_plate(comp2, d)
        body2 = comp2.bRepBodies.item(0)
        body2.name = "Thermal Mount FORWARD"
        comp2.attributes.add("brics", "forward", "1")
        if comp2.bRepBodies.count != 1:
            raise RuntimeError("forward mount is not one solid (%d bodies)" % comp2.bRepBodies.count)
        occ2.transform2 = off
        if design.snapshots.hasPendingSnapshot:
            design.snapshots.add()                       # capture the new position in the parametric timeline
        if SHOW_MODULE:
            m = rot.copy()
            m.transformBy(off)
            build_module(root, d, m, "TR256i (reference) - forward")
        msg.append("FORWARD mount: %.2f cm3, %.1f g PETG, bodies=%d" % (body2.volume, body2.volume * 1.27, comp2.bRepBodies.count))
    app.activeViewport.fit()
    print("OK  " + " | ".join(msg))


def build_cradle(comp, d, wings=True):
    """Cradle + plate in the 'looking down' frame: module long axis X (open/USB end +X), lens -Z, plate on top (z>0)."""
    feats = comp.features
    X0 = -d["cav_L"] / 2.0                       # stop face (cavity -X end)
    X1 = d["cav_L"] / 2.0                        # open end
    wing = P["wing"] if wings else 0.0
    margin = P["margin_x"] if wings else 0.0
    # A plate (z = 0 .. plate_t)
    px0 = X0 - P["wall"] - margin
    px1 = X1 + P["tab_x"]
    py = d["cr_W"] / 2.0 + wing
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = "Plate"
    rect_dims(sk, px0, -py, px1, py,
              w_expr="mod_L + clr + wall + %s + tab_x" % ("margin_x" if wings else "0 mm"),
              h_expr="2 * (cr_W / 2 + %s)" % ("wing" if wings else "0 mm"),
              x_expr="(mod_L + clr) / 2 + wall + %s" % ("margin_x" if wings else "0 mm"),
              y_expr="cr_W / 2 + %s" % ("wing" if wings else "0 mm"))
    body = extrude(feats, sk.profiles.item(0), "plate_t", +1, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    # B cradle block (z = 0 .. -cr_H)
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = "Cradle outline"
    rect_dims(sk, X0 - P["wall"], -d["cr_W"] / 2, X1, d["cr_W"] / 2,
              w_expr="mod_L + clr + wall", h_expr="cr_W", x_expr="(mod_L + clr) / 2 + wall", y_expr="cr_W / 2")
    extrude(feats, sk.profiles.item(0), "cr_H", -1, adsk.fusion.FeatureOperations.JoinFeatureOperation, body)
    body = comp.bRepBodies.item(0)
    # C cavity (open at +X)
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = "Cavity"
    rect_dims(sk, X0, -d["cav_W"] / 2, X1 + 1.0, d["cav_W"] / 2,
              w_expr="mod_L + clr + 1 mm", h_expr="cav_W", x_expr="(mod_L + clr) / 2", y_expr="cav_W / 2")
    extrude(feats, sk.profiles.item(0), "cav_H", -1, adsk.fusion.FeatureOperations.CutFeatureOperation, body)
    # D window through the lip layer
    pl = offset_plane(comp, "-cav_H", "Lip top plane")
    sk = comp.sketches.add(pl)
    sk.name = "Window"
    wx0, wx1 = X0 + P["lip_w"], X1 - P["lip_w"]
    wy = d["cav_W"] / 2 - P["lip_w"]
    rect_dims(sk, wx0, -wy, wx1, wy, w_expr="mod_L + clr - 2 * lip_w", h_expr="cav_W - 2 * lip_w",
              x_expr="(mod_L + clr) / 2 - lip_w", y_expr="cav_W / 2 - lip_w")
    extrude(feats, sk.profiles.item(0), "lip_t + 1 mm", -1, adsk.fusion.FeatureOperations.CutFeatureOperation, body)
    # D2 lightening / ventilation window in the plate above the module
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = "Plate window"
    lx0, lx1, ly = X0 + 8.0, X1 - 8.0, d["cav_W"] / 2 - 6.0
    rect_dims(sk, lx0, -ly, lx1, ly, w_expr="mod_L + clr - 16 mm", h_expr="cav_W - 12 mm",
              x_expr="(mod_L + clr) / 2 - 8 mm", y_expr="cav_W / 2 - 6 mm")
    extrude(feats, sk.profiles.item(0), "plate_t + 1 mm", +1, adsk.fusion.FeatureOperations.CutFeatureOperation, body)
    # E crush ribs (4) near the open end
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = "Crush ribs"
    rib_d = P["clr"] + P["rib_int"]
    for xc in (X1 - 5.0, X1 - 15.0):
        for s in (+1, -1):
            yw = s * d["cav_W"] / 2.0
            rect(sk, xc - 0.6, min(yw, yw - s * rib_d), xc + 0.6, max(yw, yw - s * rib_d))
    profs = adsk.core.ObjectCollection.create()
    for i in range(sk.profiles.count):
        profs.add(sk.profiles.item(i))
    extrude(feats, profs, "cav_H", -1, adsk.fusion.FeatureOperations.JoinFeatureOperation, body)
    # F slots through the plate (wings) + cable anchor tab
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = "Slots (velcro / zip tie / M3 / cable)"
    if wings:
        wy_c = d["cr_W"] / 2.0 + P["wing"] / 2.0          # wing centre line
        for s in (+1, -1):
            for xv in (-18.0, 18.0):                        # velcro strap slots (strap runs along X over the drone part)
                slot(sk, xv, s * wy_c, P["strap_w"] + 1.5, 3.4, "y")
            slot(sk, 0.0, s * wy_c, P["wing"] - 7.0, 3.4, "y")           # M3 adjustment slot
            for xz in (px0 + 4.0, X1 - 2.0):                # zip-tie slots
                slot(sk, xz, s * wy_c, 5.0, 2.4, "y")
    for s in (+1, -1):                                  # cable anchor (zip tie around the USB cable)
        slot(sk, X1 + P["tab_x"] / 2.0, s * 6.0, 5.0, 2.4, "x")
    profs = adsk.core.ObjectCollection.create()
    for i in range(sk.profiles.count):
        profs.add(sk.profiles.item(i))
    extrude(feats, profs, "plate_t + 1 mm", +1, adsk.fusion.FeatureOperations.CutFeatureOperation, body)
    body = comp.bRepBodies.item(0)
    # G window chamfer (more field of view)
    zb = -d["cr_H"]
    edges = adsk.core.ObjectCollection.create()
    for e in body.edges:
        a, b = mm3(e.startVertex.geometry), mm3(e.endVertex.geometry)
        if abs(a[2] - zb) < 1e-3 and abs(b[2] - zb) < 1e-3:
            mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
            on_x = (abs(mx - wx0) < 1e-3 or abs(mx - wx1) < 1e-3) and abs(my) <= wy + 1e-3
            on_y = abs(abs(my) - wy) < 1e-3 and wx0 - 1e-3 <= mx <= wx1 + 1e-3
            if on_x or on_y:
                edges.add(e)
    chamfer(feats, edges, "1.0 mm", "window")
    body = comp.bRepBodies.item(0)
    # G2 lead-in chamfers at the open end (vertical inner wall edges + lip edge)
    edges = adsk.core.ObjectCollection.create()
    for e in body.edges:
        a, b = mm3(e.startVertex.geometry), mm3(e.endVertex.geometry)
        if abs(a[0] - X1) < 1e-3 and abs(b[0] - X1) < 1e-3:
            vertical_wall = abs(a[1] - b[1]) < 1e-3 and abs(abs(a[1]) - d["cav_W"] / 2) < 1e-3 \
                and min(a[2], b[2]) >= -d["cav_H"] - 1e-3 and max(a[2], b[2]) <= 1e-3
            lip_edge = abs(a[2] + d["cav_H"]) < 1e-3 and abs(b[2] + d["cav_H"]) < 1e-3
            if vertical_wall or lip_edge:
                edges.add(e)
    chamfer(feats, edges, "0.6 mm", "lead-in")
    body = comp.bRepBodies.item(0)
    # H fillets
    if wings:
        fil_edges(feats, body, lambda a, b: vert(a, b) and abs(abs(a.y * 10) - py) < 1e-3 and
                  (abs(a.x * 10 - px0) < 1e-3 or abs(a.x * 10 - px1) < 1e-3), "4 mm")
        body = comp.bRepBodies.item(0)
    fil_edges(feats, body, lambda a, b: vert(a, b) and abs(abs(a.y * 10) - d["cr_W"] / 2) < 1e-3 and
              abs(a.x * 10 - (X0 - P["wall"])) < 1e-3 and min(a.z, b.z) * 10 < -1.0, "1.5 mm")


def forward_matrix(d):
    """Local 'down' frame -> forward frame: X->Y (USB end to the side), Y->-Z, Z->-X (lens looks +X); top of unit at z=0."""
    m = adsk.core.Matrix3D.create()
    m.setWithCoordinateSystem(adsk.core.Point3D.create(0, 0, -cm(d["cr_W"] / 2.0)),
                              adsk.core.Vector3D.create(0, 1, 0),
                              adsk.core.Vector3D.create(0, 0, -1),
                              adsk.core.Vector3D.create(-1, 0, 0))
    return m


def build_forward_plate(comp, d):
    """Horizontal mounting plate on top of the rotated cradle unit + 2 gussets, joined into one body."""
    feats = comp.features
    body = comp.bRepBodies.item(0)
    X0, X1 = -d["cav_L"] / 2.0, d["cav_L"] / 2.0
    y0, y1 = X0 - P["wall"], X1 + P["tab_x"]                 # unit extent along world Y
    xb1 = d["cr_H"]                                          # front of the unit (lens side)
    xb0 = -P["plate_t"] - 34.0                               # plate extends 34 mm behind the unit
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = "Forward plate"
    rect(sk, xb0, y0, xb1, y1)
    extrude(feats, sk.profiles.item(0), "plate_t", +1, adsk.fusion.FeatureOperations.JoinFeatureOperation, body)
    body = comp.bRepBodies.item(0)
    # gussets behind the back plate (XZ triangles, 3 mm thick)
    g = 12.0
    for yc in (y0 + 1.5, X1 - 1.5):
        pl = comp.constructionPlanes.createInput()
        pl.setByOffset(comp.xZConstructionPlane, adsk.core.ValueInput.createByString("%s mm" % (yc - 1.5)))
        plane = comp.constructionPlanes.add(pl)
        sk = comp.sketches.add(plane)
        a = sk.modelToSketchSpace(P3(-P["plate_t"], yc - 1.5, 0.0))
        b = sk.modelToSketchSpace(P3(-P["plate_t"], yc - 1.5, -g))
        c = sk.modelToSketchSpace(P3(-P["plate_t"] - g, yc - 1.5, 0.0))
        L = sk.sketchCurves.sketchLines
        l1 = L.addByTwoPoints(a, b)
        l2 = L.addByTwoPoints(l1.endSketchPoint, c)
        L.addByTwoPoints(l2.endSketchPoint, l1.startSketchPoint)
        extrude_auto(feats, sk.profiles.item(0), "3 mm", adsk.fusion.FeatureOperations.JoinFeatureOperation,
                     adsk.core.Vector3D.create(0, 1, 0), body)
        body = comp.bRepBodies.item(0)
    # slots: 2 velcro straps (run along X), M3 slots, zip ties
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = "Forward plate slots"
    xa, xb = -P["plate_t"] - 7.0, -P["plate_t"] - 29.0
    for yc in (-16.0, 14.0):                                     # clear of the gussets (y ~ -29 / +28) and of each other
        for xs in (xa, xb):
            slot(sk, xs, yc, P["strap_w"] + 1.5, 3.4, "y")
    for yc in (y0 + 5.0, y1 - 5.0):
        slot(sk, (xa + xb) / 2.0, yc, 14.0, 3.4, "x")             # M3 slots
    for yc in (-1.0,):
        for xs in (xa, xb):
            slot(sk, xs, yc, 5.0, 2.4, "y")                        # zip-tie slots
    profs = adsk.core.ObjectCollection.create()
    for i in range(sk.profiles.count):
        profs.add(sk.profiles.item(i))
    extrude(feats, profs, "plate_t + 1 mm", +1, adsk.fusion.FeatureOperations.CutFeatureOperation, body)
    body = comp.bRepBodies.item(0)
    fil_edges(feats, body, lambda a, b: vert(a, b) and abs(a.x * 10 - xb0) < 1e-3 and
              (abs(a.y * 10 - y0) < 1e-3 or abs(a.y * 10 - y1) < 1e-3), "4 mm")


# ============================================================================= helpers
def cm(v):
    return v / 10.0


def mm3(p):
    return (p.x * 10.0, p.y * 10.0, p.z * 10.0)


def chamfer(feats, edges, dist, what):
    if edges.count == 0:
        raise RuntimeError("no edges matched for chamfer (%s)" % what)
    ch = feats.chamferFeatures.createInput2()
    ch.chamferEdgeSets.addEqualDistanceChamferEdgeSet(edges, adsk.core.ValueInput.createByString(dist), True)
    feats.chamferFeatures.add(ch)


def P3(x, y, z=0.0):
    return adsk.core.Point3D.create(cm(x), cm(y), cm(z))


def rect(sk, x0, y0, x1, y1):
    return sk.sketchCurves.sketchLines.addTwoPointRectangle(P3(x0, y0), P3(x1, y1))


def rect_dims(sk, x0, y0, x1, y1, w_expr, h_expr, x_expr, y_expr):
    """Rectangle fully constrained by parametric dimensions (expressions use user parameters)."""
    lines = rect(sk, x0, y0, x1, y1)
    pts = {}
    for i in range(lines.count):
        for p in (lines.item(i).startSketchPoint, lines.item(i).endSketchPoint):
            g = p.geometry
            pts[(round(g.x * 10, 3), round(g.y * 10, 3))] = p
    bl = pts[(round(x0, 3), round(y0, 3))]
    br = pts[(round(x1, 3), round(y0, 3))]
    tl = pts[(round(x0, 3), round(y1, 3))]
    D = sk.sketchDimensions
    H = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
    V = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation
    D.addDistanceDimension(bl, br, H, P3((x0 + x1) / 2, y0 - 6)).parameter.expression = w_expr
    D.addDistanceDimension(bl, tl, V, P3(x0 - 6, (y0 + y1) / 2)).parameter.expression = h_expr
    o = sk.originPoint
    if abs(x0) > 1e-6:      # x0 < 0 for all our rectangles -> distance = -x0
        D.addDistanceDimension(o, bl, H, P3(x0 / 2, y0 - 12)).parameter.expression = x_expr
    if abs(y0) > 1e-6:
        D.addDistanceDimension(o, bl, V, P3(x0 - 12, y0 / 2)).parameter.expression = y_expr
    return lines


def slot(sk, cx, cy, length, width, axis):
    """Obround slot (closed profile), length = end to end."""
    r = width / 2.0
    h = (length - width) / 2.0
    L = sk.sketchCurves.sketchLines
    A = sk.sketchCurves.sketchArcs
    if axis == "y":
        l1 = L.addByTwoPoints(P3(cx - r, cy - h), P3(cx - r, cy + h))
        l2 = L.addByTwoPoints(P3(cx + r, cy - h), P3(cx + r, cy + h))
        A.addByThreePoints(l1.endSketchPoint, P3(cx, cy + h + r), l2.endSketchPoint)
        A.addByThreePoints(l1.startSketchPoint, P3(cx, cy - h - r), l2.startSketchPoint)
    else:
        l1 = L.addByTwoPoints(P3(cx - h, cy - r), P3(cx + h, cy - r))
        l2 = L.addByTwoPoints(P3(cx - h, cy + r), P3(cx + h, cy + r))
        A.addByThreePoints(l1.endSketchPoint, P3(cx + h + r, cy), l2.endSketchPoint)
        A.addByThreePoints(l1.startSketchPoint, P3(cx - h - r, cy), l2.startSketchPoint)


def extrude(feats, profile, dist_expr, direction, op, body=None):
    ext = feats.extrudeFeatures
    inp = ext.createInput(profile, op)
    de = adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString(dist_expr))
    inp.setOneSideExtent(de, adsk.fusion.ExtentDirections.PositiveExtentDirection if direction > 0
                         else adsk.fusion.ExtentDirections.NegativeExtentDirection)
    if body is not None and op != adsk.fusion.FeatureOperations.NewBodyFeatureOperation:
        inp.participantBodies = [body]
    f = ext.add(inp)
    return f.bodies.item(0) if f.bodies.count else None


def offset_plane(comp, expr, name):
    ci = comp.constructionPlanes.createInput()
    ci.setByOffset(comp.xYConstructionPlane, adsk.core.ValueInput.createByString(expr))
    pl = comp.constructionPlanes.add(ci)
    pl.name = name
    return pl


def vert(a, b):
    return abs(a.x - b.x) < 1e-7 and abs(a.y - b.y) < 1e-7


def fil_edges(feats, body, pred, radius):
    edges = adsk.core.ObjectCollection.create()
    for e in body.edges:
        if pred(e.startVertex.geometry, e.endVertex.geometry):
            edges.add(e)
    if edges.count == 0:
        raise RuntimeError("no edges matched for fillet %s" % radius)
    fi = feats.filletFeatures.createInput()
    fi.edgeSetInputs.addConstantRadiusEdgeSet(edges, adsk.core.ValueInput.createByString(radius), True)
    feats.filletFeatures.add(fi)


def build_module(root, d, matrix, name):
    """TR256i reference body (box + lens + USB-C plug), seated against the stop wall and on the lips."""
    occ = root.occurrences.addNewComponent(matrix)
    comp = occ.component
    comp.name = name
    feats = comp.features
    z_bot = -d["cav_H"]                   # module bottom face sits on the lips
    x0 = -d["cav_L"] / 2.0
    pl = offset_plane(comp, "%s mm" % z_bot, "Module bottom")
    sk = comp.sketches.add(pl)
    rect(sk, x0, -d["mod_W"] / 2, x0 + d["mod_L"], d["mod_W"] / 2)
    b = extrude(feats, sk.profiles.item(0), "%s mm" % d["mod_T"], +1, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    b.name = "TR256i body"
    edges = adsk.core.ObjectCollection.create()
    for e in b.edges:
        edges.add(e)
    fi = feats.filletFeatures.createInput()
    fi.edgeSetInputs.addConstantRadiusEdgeSet(edges, adsk.core.ValueInput.createByString("1.2 mm"), True)
    feats.filletFeatures.add(fi)
    sk = comp.sketches.add(pl)
    sk.sketchCurves.sketchCircles.addByCenterRadius(P3(x0 + LENS_FROM_FAR_END, 0), cm(3.5))
    extrude(feats, sk.profiles.item(0), "0.6 mm", -1, adsk.fusion.FeatureOperations.NewBodyFeatureOperation).name = "Lens"
    xp = offset_plane_x(comp, x0 + d["mod_L"])
    sk = comp.sketches.add(xp)
    c1 = sk.modelToSketchSpace(P3(x0 + d["mod_L"], -4.2, z_bot + d["mod_T"] / 2 - 1.3))
    c2 = sk.modelToSketchSpace(P3(x0 + d["mod_L"], 4.2, z_bot + d["mod_T"] / 2 + 1.3))
    sk.sketchCurves.sketchLines.addTwoPointRectangle(c1, c2)
    pb = extrude_auto(feats, sk.profiles.item(0), "6.5 mm", adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
                      adsk.core.Vector3D.create(1, 0, 0))
    pb.name = "USB-C plug"


def offset_plane_x(comp, x_mm):
    ci = comp.constructionPlanes.createInput()
    ci.setByOffset(comp.yZConstructionPlane, adsk.core.ValueInput.createByString("%s mm" % x_mm))
    return comp.constructionPlanes.add(ci)


def extrude_auto(feats, profile, dist_expr, op, want_dir, body=None):
    """Extrude in the direction closest to want_dir (sketch normals can be flipped)."""
    ext = feats.extrudeFeatures
    inp = ext.createInput(profile, op)
    de = adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString(dist_expr))
    sk = profile.parentSketch
    sk_normal = sk.xDirection.crossProduct(sk.yDirection)
    direction = adsk.fusion.ExtentDirections.PositiveExtentDirection if sk_normal.dotProduct(want_dir) > 0 \
        else adsk.fusion.ExtentDirections.NegativeExtentDirection
    inp.setOneSideExtent(de, direction)
    if body is not None:
        inp.participantBodies = [body]
    return ext.add(inp).bodies.item(0)
