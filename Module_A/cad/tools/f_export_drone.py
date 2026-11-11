import adsk.core, adsk.fusion, os
OUT = os.environ.get('BRICS_CAD_OUT', os.path.expanduser('~/BRICS-HiTech-2026-Flying-Robotics/Module_A/cad/out'))
def run(_context: str):
    design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    root = design.rootComponent
    em = design.exportManager
    drone = [o for o in root.occurrences if o.component.name.startswith("TECHNIC 6S")][0].component
    files = []
    p = os.path.join(OUT, "TECHNIC6S_with_thermal_mount_assembly.step"); em.execute(em.createSTEPExportOptions(p, drone)); files.append(p)
    p = os.path.join(OUT, "BRICS_aerial_robotics_CAD.f3d"); em.execute(em.createFusionArchiveExportOptions(p, root)); files.append(p)
    for f in files:
        print("%-55s %8.1f KB" % (os.path.basename(f), os.path.getsize(f) / 1024.0))
