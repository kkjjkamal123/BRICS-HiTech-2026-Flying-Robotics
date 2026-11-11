#!/usr/bin/env python3
"""
Rebuild ALL CAD in Autodesk Fusion through its local MCP connection, verify it, render and export it.
  1. Open Autodesk Fusion (with the MCP add-in running), then:   .venv/bin/python cad/build_all_cad.py
Steps: thermal mounts (new document) -> verification (must pass) -> STEP/STL/F3D -> renders ->
       TECHNIC 6S assembly -> interference check (must be 0) -> exports -> renders -> technical drawings.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(HERE, "out")
MCP = os.path.join(HERE, "tools", "fusion_mcp.py")
PY = sys.executable


def call(tool, args, img=None, timeout=900):
    env = dict(os.environ)
    if img:
        env["FUSION_IMG"] = img
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(args, f)
    f.close()
    r = subprocess.run([PY, MCP, "call", tool, "@" + f.name], capture_output=True, text=True, env=env, timeout=timeout)
    os.unlink(f.name)
    out = (r.stdout or "") + (r.stderr or "")
    try:
        d = json.loads(r.stdout)
        return d.get("message") or d.get("error") or out
    except ValueError:
        return out.strip()


def script(path_or_code, timeout=900):
    code = open(path_or_code).read() if os.path.exists(path_or_code) else path_or_code
    return call("fusion_mcp_execute", {"featureType": "script", "object": {"script": code}}, timeout=timeout)


def shot(keys, out, ex, ey, ez, w=1800, h=1200, hide="", zoom=1.0):
    tpl = open(os.path.join(HERE, "tools", "f_camera.py.tpl")).read()
    script(tpl.replace("__KEYS__", keys).replace("__HIDE__", hide).replace("__ZOOM__", str(zoom))
           .replace("__EX__", str(ex)).replace("__EY__", str(ey)).replace("__EZ__", str(ez)))
    call("fusion_mcp_read", {"queryType": "screenshot", "direction": "current", "width": w, "height": h,
                             "transparentBackground": True}, img=out)


def step(title):
    print("\n== " + title, flush=True)


def need(cond, msg):
    if not cond:
        print("STOP: " + msg)
        sys.exit(1)


def main():
    step("Fusion connection")
    r = script("import adsk.core\ndef run(_context: str):\n    print('Fusion', adsk.core.Application.get().version)\n", timeout=60)
    print(r)
    need("Fusion" in r, "Fusion is not reachable - open Autodesk Fusion (MCP add-in) and retry")
    step("Thermal mounts (new document)")
    r = script(os.path.join(HERE, "fusion_thermal_mount.py")); print(r)
    need(r.startswith("OK"), "mount build failed")
    script(os.path.join(HERE, "tools", "f_appearance.py"))
    step("Verification")
    r = script(os.path.join(HERE, "fusion_verify_mount.py")); print(r)
    need("ALL CHECKS PASSED" in r, "verification failed - nothing exported")
    step("Export mounts"); print(script(os.path.join(HERE, "tools", "f_export_mounts.py")))
    step("Renders: mounts")
    shot("looking down|- down", os.path.join(OUT, "render_down_camera_side.png"), -1, -1.2, -0.9)
    shot("looking down|- down", os.path.join(OUT, "render_down_drone_side.png"), -1, -1.2, 0.9)
    shot("looking down", os.path.join(OUT, "render_down_mount_only.png"), -1, -1.2, -0.9)
    shot("looking forward|- forward", os.path.join(OUT, "render_forward_front.png"), 1.2, -1, -0.5)
    shot("looking forward|- forward", os.path.join(OUT, "render_forward_back.png"), -1.2, 1, 0.8)
    step("TECHNIC 6S assembly")
    r = script(os.path.join(HERE, "fusion_technic6s_model.py")); print(r)
    need(r.startswith("OK") or "\nOK TECHNIC" in r, "drone model failed")
    need("PIPE FAILED" not in r, "a wire fell back to a tube - check the route")
    r = script(os.path.join(HERE, "fusion_check_drone.py")); print(r)
    need("UNINTENDED overlaps: 0" in r, "interference found in the drone assembly")
    need("deeper than 2.5 mm3 (review): 0" in r, "a wire is buried in a part - check the route")
    step("Export drone"); print(script(os.path.join(HERE, "tools", "f_export_drone.py")))
    step("Renders: drone")
    shot("TECHNIC 6S", os.path.join(OUT, "technic6s_iso.png"), -1, -1.25, 0.9)
    shot("TECHNIC 6S", os.path.join(OUT, "technic6s_front.png"), 0, 1, 0.0001)
    shot("TECHNIC 6S", os.path.join(OUT, "technic6s_top.png"), 0, 0, 1)
    shot("TECHNIC 6S", os.path.join(OUT, "technic6s_underside.png"), -0.8, -1, -0.7)
    shot("TECHNIC 6S", os.path.join(OUT, "_under_raw.png"), -0.5, -0.9, -0.8, 2400, 1600)
    nog = "Prop guard|Propeller|Landing gear"
    shot("TECHNIC 6S", os.path.join(OUT, "technic6s_electronics_top.png"), -1, -0.8, 0.9, hide=nog + "|Battery 4S", zoom=1.9)
    shot("TECHNIC 6S", os.path.join(OUT, "technic6s_electronics_rear.png"), 0.6, -1, 0.35, hide=nog, zoom=1.9)
    shot("TECHNIC 6S", os.path.join(OUT, "technic6s_electronics_under.png"), -0.9, -0.7, -0.8, hide=nog + "|Camera plate|Thermal Mount|TR256i", zoom=1.9)
    shot("TECHNIC 6S", os.path.join(OUT, "technic6s_wiring_side.png"), 1, 0.15, 0.05, hide=nog, zoom=1.6)
    shot("TECHNIC 6S", os.path.join(OUT, "technic6s_guard_landing_gear.png"), -0.9, -1.2, -0.35)
    step("Post-process images + drawings")
    venv = os.path.join(ROOT, ".venv", "bin", "python")
    subprocess.run([venv, os.path.join(HERE, "postprocess_images.py")], check=True)
    subprocess.run([venv, os.path.join(HERE, "make_drawings.py")], check=True)
    subprocess.run([venv, os.path.join(HERE, "make_wiring_diagram.py")], check=True)
    print("\nALL CAD REBUILT AND VERIFIED -> %s" % OUT)


if __name__ == "__main__":
    main()
