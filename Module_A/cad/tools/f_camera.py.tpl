import adsk.core, adsk.fusion
def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    keys = "__KEYS__".split("|")
    hide = "__HIDE__".split("|")
    shown = []
    for o in design.rootComponent.occurrences:
        o.isLightBulbOn = any(k and k in o.component.name for k in keys)
        if o.isLightBulbOn:
            shown.append(o)
            stack = list(o.childOccurrences)
            while stack:
                c = stack.pop()
                c.isLightBulbOn = not any(h and h in c.component.name for h in hide)
                stack += list(c.childOccurrences)
    bb = None
    for o in shown:
        b = o.boundingBox
        if bb is None:
            bb = b.copy()
        else:
            bb.combine(b)
    c = adsk.core.Point3D.create((bb.minPoint.x + bb.maxPoint.x) / 2, (bb.minPoint.y + bb.maxPoint.y) / 2, (bb.minPoint.z + bb.maxPoint.z) / 2)
    vp = app.activeViewport
    cam = vp.camera
    cam.isSmoothTransition = False
    cam.cameraType = adsk.core.CameraTypes.OrthographicCameraType
    d = adsk.core.Vector3D.create(__EX__, __EY__, __EZ__)
    d.normalize()
    d.scaleBy(200)
    zoom = __ZOOM__
    cam.target = c
    cam.eye = adsk.core.Point3D.create(c.x + d.x, c.y + d.y, c.z + d.z)
    cam.upVector = adsk.core.Vector3D.create(0, 1, 0) if abs(d.z) > 199 else adsk.core.Vector3D.create(0, 0, 1)
    vp.camera = cam
    vp.fit()
    if zoom != 1.0:
        cam = vp.camera
        cam.viewExtents = cam.viewExtents / zoom
        vp.camera = cam
