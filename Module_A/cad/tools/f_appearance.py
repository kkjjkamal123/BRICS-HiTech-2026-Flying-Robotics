import adsk.core, adsk.fusion
def find(app, words):
    for lib in app.materialLibraries:
        for i in range(lib.appearances.count):
            a = lib.appearances.item(i)
            n = a.name.lower()
            if all(w in n for w in words):
                return a
    return None
def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    orange = find(app, ["plastic - glossy (yellow)"])
    dark = find(app, ["paint - enamel glossy (dark grey)"])
    glass = find(app, ["glass"]) 
    print("appearances:", orange.name if orange else None, "|", dark.name if dark else None, "|", glass.name if glass else None)
    def get(a):
        ex = design.appearances.itemByName(a.name)
        return ex if ex else design.appearances.addByCopy(a, a.name)
    for o in design.rootComponent.occurrences:
        for b in o.component.bRepBodies:
            if o.component.name.startswith("Thermal Mount") and orange:
                b.appearance = get(orange)
            elif b.name == "Lens" and glass:
                b.appearance = get(glass)
            elif dark:
                b.appearance = get(dark)
