import adsk.core, adsk.fusion, json, os
OUT = os.environ.get('BRICS_CAD_OUT', os.path.expanduser('~/BRICS-HiTech-2026-Flying-Robotics/Module_A/cad/out'))
def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    for o in root.occurrences:
        o.isLightBulbOn = True
    em = design.exportManager
    done = []
    for o in root.occurrences:
        c = o.component
        if not c.name.startswith("Thermal Mount"):
            continue
        tag = "forward" if "forward" in c.name else "down"
        b = c.bRepBodies.item(0)
        stl = os.path.join(OUT, "TR256i_mount_%s.stl" % tag)
        opt = em.createSTLExportOptions(b, stl)
        opt.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
        opt.isBinaryFormat = True
        em.execute(opt)
        stp = os.path.join(OUT, "TR256i_mount_%s.step" % tag)
        em.execute(em.createSTEPExportOptions(stp, c))
        done += [stl, stp]
        # edge polylines in component coordinates (for drawings)
        edges = []
        for e in b.edges:
            ev = e.evaluator
            ok, p0, p1 = ev.getParameterExtents()
            ok, pts = ev.getStrokes(p0, p1, 0.005)
            edges.append([[p.x * 10, p.y * 10, p.z * 10] for p in pts])
        json.dump({"edges": edges, "volume_cm3": b.volume}, open(os.path.join(OUT, "edges_%s.json" % tag), "w"))
    asm = os.path.join(OUT, "TR256i_mounts_assembly.step")
    em.execute(em.createSTEPExportOptions(asm, root))
    f3d = os.path.join(OUT, "TR256i_mounts.f3d")
    em.execute(em.createFusionArchiveExportOptions(f3d, root))
    done += [asm, f3d]
    for f in done:
        print("%-60s %8.1f KB" % (os.path.basename(f), os.path.getsize(f) / 1024.0))
