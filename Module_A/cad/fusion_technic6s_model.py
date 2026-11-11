"""
TECHNIC 6S - detailed assembly WITH ALL ELECTRONICS AND WIRING + TR256i thermal mount (Autodesk Fusion API script).

NOT official SKYRIS CAD (none is published). Built from the SKYRIS assembly guide (offline/docs/.../Sborka.html, Sborka2.html):
  * arm + battery-plate outlines imported from the guide's vector drawings (2.svg, 15_11.svg), scale from hole patterns
  * layout as in the guide: battery on top (strap, XT60 on the battery plate) -> 35 mm alu standoffs ->
    ESC 4in1 + PX4 flight controller stack (30.5 mm) on the top centre plate, ELRS receiver taped behind it ->
    arms between the centre plates -> Orange Pi mount under the bottom plate (LED ring around it) -> Orange Pi 5 Pro
    (connectors facing down, HDMI to the rear) + SKYRIS "Orange Pi 5 Pro Shield V2" with the 30 mm cooler ->
    35 mm nylon standoffs -> camera plate with the USB camera (front) and the VL53L1X laser rangefinder.
  * every connection in the guide is a real wire (swept pipe): ESC<->FC 8-pin, motors -> MR30 -> ESC, XT60 power,
    FC TELEM1 -> ELRS receiver, FC TELEM2 -> shield UART0, ESC -> shield V IN, LED strip, cooler, VL53L1X -> I2C,
    camera USB, TR256i USB, WiFi antenna, ELRS antenna, battery balance lead.
Board sizes are real (Orange Pi 5 Pro 89x56, 30.5 mm stack 36x36, HAT 65x56, standard connector bodies); the positions of
small parts on the boards are representative. Main dimensions +-3 %.
Run AFTER fusion_thermal_mount.py in the same design: the 'looking down' mount + TR256i go under the camera plate.
"""
import json
import math
import os

import adsk.core
import adsk.fusion

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:   # run through the Fusion MCP connection (no __file__)
    HERE = os.environ.get("BRICS_CAD_DIR", os.path.expanduser("~/BRICS-HiTech-2026-Flying-Robotics/Module_A/cad"))
OUTLINES = os.path.join(HERE, "out", "technic_outlines.json")
HARNESS_JSON = os.path.join(HERE, "out", "technic6s_harness.json")
OFFSET_X = 420.0          # mm: drone placed beside the separate mount parts
MOTORS = [(sx * 86.1, sy * 96.0) for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
STANDOFFS = [(sx * 32.5, sy * 28.6) for sx in (-1, 1) for sy in (-1, 1)]        # 35 mm alu: top plate -> battery plate
LOW_STANDOFFS = [(sx * 28.0, sy * 40.0) for sx in (-1, 1) for sy in (-1, 1)]    # 35 mm nylon: OPi mount -> camera plate
STACK = [(sx * 15.25, sy * 15.25) for sx in (-1, 1) for sy in (-1, 1)]
OPI_HOLES = [(-41.0, -24.5), (-41.0, 24.5), (17.0, -24.5), (17.0, 24.5)]
SHIELD_POST = (-26.3, -24.5)
ARM_TIPS = [(sx * 97.2, sy * 116.8) for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
GUARD_R, GUARD_HALF_DEG = 92.0, 30.0   # guard band: radius around each motor (prop 76.2 -> 15.8 mm gap), +-30 deg either side
GEAR_SCREWS = [(8.0, 8.0), (-8.0, -8.0)]   # motor holes (16x16) used by the 2 M3x20 of the landing-gear mount (arm frame)
SLOT_TELEM2 = (-6.0, 34.0)    # cable passages through the centre plates (no arm material there - checked on the outlines)
SLOT_VIN = (14.0, -36.0)
THERMAL_ORIGIN = (0.0, -12.0, -44.5)


def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    for o in list(root.occurrences):
        if o.component.name.startswith("TECHNIC 6S"):
            o.deleteMe()
    data = json.load(open(OUTLINES))
    top_m = adsk.core.Matrix3D.create()
    top_m.translation = adsk.core.Vector3D.create(cm(OFFSET_X), 0, 0)
    occ = root.occurrences.addNewComponent(top_m)
    drone = occ.component
    drone.name = "TECHNIC 6S + electronics + wiring + thermal mount"
    A = Appear(app, design)
    ports = {}          # name -> (back face centre of the plug, outward axis)
    t = Tools()

    # ============================================================== frame
    fr = new_comp(drone, "Frame (carbon)")
    for i, arm in enumerate(data["arms"]):
        A.set(poly_extrude(fr, arm["outline"], 0.0, 4.0, "Arm %d" % (i + 1)), "carbon")
    A.set(rrect_extrude(fr, 0, 0, 70, 100, 9, -2.0, 0.0, "Centre plate bottom"), "carbon")
    A.set(rrect_extrude(fr, 0, 0, 70, 92, 9, 4.0, 6.0, "Centre plate top"), "carbon")
    cut_tools(fr, [t.cyl((x, y, -3), (x, y, 7), 1.6) for x, y in STANDOFFS + STACK + LOW_STANDOFFS]
              + [t.box((SLOT_TELEM2[0], SLOT_TELEM2[1], 2), (8, 6, 10)), t.box((SLOT_VIN[0], SLOT_VIN[1], 2), (6, 6, 10))])
    cut_tools(fr, [t.cyl((x, y, -1), (x, y, 5), 1.55) for x, y in ARM_TIPS] + [t.cyl((x, y, -1), (x, y, 5), 4.0) for x, y in MOTORS]
              + [t.cyl(P + (-1,), P + (5,), 1.6) for P in gear_screw_xy()])

    so = new_comp(drone, "Standoff L35 alu (x4)", reuse_for=STANDOFFS, z=6.0)
    tb = TB(so, A)
    tb.add(tb.cyl((0, 0, 0), (0, 0, 35.0), 2.75), "Standoff L35 alu", "alu_black")
    tb.flush()

    # ============================================================== battery plate, XT60, battery
    bp = new_comp(drone, "Battery plate + XT60")
    A.set(poly_extrude(bp, data["battery_plate"]["outline"], 41.0, 43.5, "Battery plate"), "carbon")
    cut_tools(bp, [t.cyl((x, y, 40), (x, y, 45), 1.6) for x, y in STANDOFFS] + [t.box((25, -17, 42.25), (9, 8, 4))])
    tb = TB(bp, A)
    tb.add(tb.box((25, -17, 51.5), (8.2, 15.8, 16)), "XT60 female (ESC lead)", "xt60")
    tb.add(tb.box((25, -17, 67.5), (8.2, 15.8, 16)), "XT60 male (battery lead)", "xt60")
    tb.add(tb.U(tb.box((19.95, -17, 48.25), (1.9, 18, 9.5)), tb.box((30.05, -17, 48.25), (1.9, 18, 9.5))), "XT60 mount (printed)", "printed")
    tb.flush()
    ports["xt60_f"] = ((25, -17, 43.5), (0, 0, -1))
    ports["xt60_m"] = ((25, -17, 75.5), (0, 0, 1))
    bat = new_comp(drone, "Battery 4S LiPo + strap")
    tb = TB(bat, A)
    tb.add(tb.box((0, 0, 60.0), (35, 105, 33)), "Battery 4S LiPo", "battery")
    tb.add(tb.D(tb.box((0, 8, 59.9), (37.4, 20, 36.2)), tb.box((0, 8, 59.9), (35.2, 22, 34.0))), "Battery strap (SKYRIS)", "rubber_black")
    tb.add(tb.box((-20.4, -37.75, 60), (5.8, 12.5, 6)), "Balance plug JST-XH 5p", "white")
    tb.flush()

    # ============================================================== flight stack: ESC 4in1 + PX4 FC (30.5 mm)
    st = new_comp(drone, "Flight stack: ESC 4in1 + PX4 flight controller")
    tb = TB(st, A)
    for x, y in STACK:
        tb.add(tb.cyl((x, y, 6.0), (x, y, 12.0), 2.75), "Nylon standoff M3x6 (M-F)", "nylon_black")
        tb.add(tb.cyl((x, y, 13.6), (x, y, 21.6), 2.75), "Nylon standoff M3x8 (F-F)", "nylon_black")
        tb.add(tb.D(tb.cyl((x, y, 20.6), (x, y, 24.2), 3.5), tb.cyl((x, y, 20), (x, y, 25), 1.5)), "FC damper", "rubber_black")
        tb.add(tb.cyl((x, y, 24.2), (x, y, 26.2), 2.75), "Screw M3 (FC)", "steel")
    tb.add(tb.D(tb.box((0, 0, 12.8), (36, 36, 1.6)), *[tb.cyl((x, y, 10), (x, y, 26), 1.6) for x, y in STACK]), "ESC 4in1 PCB", "pcb_black")
    tb.add(tb.U(*[tb.box((sx * 8.5 + dx, sy * 8.5, 14.1), (5, 6, 1.0)) for sx in (-1, 1) for sy in (-1, 1) for dx in (-3, 3)]),
           "ESC MOSFETs", "chip")
    tb.add(tb.U(*([tb.box((0, 0, 15.35), (22, 22, 1.5))] + [tb.box((-9 + 3 * k, 0, 18.1), (1.0, 22, 4.0)) for k in range(7)])),
           "ESC heatsink (alu)", "alu")
    tb.add(tb.D(tb.box((0, 0, 22.4), (36, 36, 1.6)), *[tb.cyl((x, y, 20), (x, y, 26), 1.6) for x, y in STACK]),
           "Flight controller PCB (PX4)", "pcb_black")
    tb.add(tb.U(tb.box((0, 1, 23.9), (14, 14, 1.4)), tb.box((-6, -8, 23.7), (3, 3, 1.0)), tb.box((3, -12, 23.7), (2.5, 2, 1.0)),
                tb.box((-12, 8, 23.6), (3, 2, 0.8)), tb.box((-3, 10, 23.6), (3, 1.6, 0.8))), "FC components (MCU, IMU, baro)", "chip")
    pins = [tb.box((12, 0, 24.45), (7.62, 20.32, 2.5))]
    pins += [tb.box((12 - 2.54 + 2.54 * j, -8.89 + 2.54 * i, 28.2), (0.64, 0.64, 6.0)) for i in range(8) for j in range(3)]
    tb.add(tb.U(*pins), "FC PWM pin header 8x3", "pin_header")
    conn(tb, ports, "fc_esc", (-5.5, -18.2, 24.7), (0, -1, 0), (1, 0, 0), 10, 3.0, 4.0, 3.5, "FC ESC socket 8p", "FC ESC plug 8p", "white", "white")
    conn(tb, ports, "esc_fc", (-5.5, -17.5, 15.1), (0, -1, 0), (1, 0, 0), 10, 3.0, 4.0, 3.5, "ESC FC socket 8p", "ESC FC plug 8p", "white", "white")
    conn(tb, ports, "telem1", (-18.2, -3, 25.325), (-1, 0, 0), (0, 1, 0), 7.5, 4.25, 4.5, 3.5, "FC TELEM1 socket (JST-GH)", "FC TELEM1 plug", "white", "white")
    conn(tb, ports, "telem2", (-6, 18.2, 25.325), (0, 1, 0), (1, 0, 0), 9.5, 4.25, 4.5, 3.5, "FC TELEM2 socket (JST-GH)", "FC TELEM2 plug", "white", "white")
    conn(tb, ports, None, (6, 18.2, 24.8), (0, 1, 0), (1, 0, 0), 8.9, 3.2, 7.5, 0, "FC USB-C", None, "steel", None)
    tb.flush()

    rx = new_comp(drone, "ELRS receiver")
    tb = TB(rx, A)
    tb.add(tb.box((0, -38, 8.0), (13, 20, 4.0)), "ELRS receiver", "rx")
    tb.flush()
    ports["rx"] = ((0, -28, 8.0), (0, 1, 0))

    mr = new_comp(drone, "MR30 motor connectors (x4)")
    tb = TB(mr, A)
    for sx in (-1, 1):
        for sy in (-1, 1):
            tb.add(tb.box((sx * 31.5, sy * 8, 9.2), (11, 8.6, 6.4)), "MR30 female (ESC)", "xt60")
            tb.add(tb.box((sx * 42.0, sy * 8, 9.2), (10, 8.6, 6.4)), "MR30 male (motor)", "xt60")
    tb.flush()

    # ============================================================== Orange Pi mount, LED ring, low standoffs, antenna
    om = new_comp(drone, "Orange Pi mount + LED ring + WiFi antenna")
    tb = TB(om, A)
    parts = [tb.box((0, 0, -3.5), (96, 60, 3)), tb.box((0, -33, -3.5), (16, 6, 3))]
    parts += [tb.box((x, y - (2 if y > 0 else -2), -3.5), (12, 12, 3)) for x, y in LOW_STANDOFFS]
    for k in range(4):
        a = math.radians(45 + 90 * k)
        c, s = math.cos(a), math.sin(a)
        parts.append(tb.box((46.5 * c, 46.5 * s, -3.5), (33, 6, 3), (c, s, 0), (-s, c, 0)))
        parts.append(tb.box((62 * c, 62 * s, -7.0), (2.0, 8, 10), (c, s, 0), (-s, c, 0)))
    parts += [tb.cyl((x, y, -9.0), (x, y, -5.0), 3.0) for x, y in OPI_HOLES]
    tb.add(tb.D(tb.U(*parts), *([tb.cyl((x, y, -12), (x, y, 0), 1.6) for x, y in LOW_STANDOFFS]
                               + [tb.cyl((x, y, -12), (x, y, 0), 1.3) for x, y in OPI_HOLES])), "Orange Pi mount (printed)", "printed")
    for x, y in LOW_STANDOFFS:
        tb.add(tb.cyl((x, y, -40.0), (x, y, -5.0), 2.75), "Nylon standoff M3x35 (F-F)", "nylon_black")
    tb.add(tb.D(tb.cyl((0, 0, -12), (0, 0, -2), 65.0), tb.cyl((0, 0, -13), (0, 0, -1), 63.0)), "LED strip WS2812 (58 LEDs)", "white")
    leds = []
    for k in range(58):
        a = 2 * math.pi * (k + 0.5) / 58.0
        c, s = math.cos(a), math.sin(a)
        leds.append(tb.box((65.6 * c, 65.6 * s, -7.0), (1.4, 5, 5), (c, s, 0), (-s, c, 0)))
    tb.add(tb.U(*leds), "LED chips", "led")
    tb.add(tb.box((0, -33, -6.5), (10, 6, 3)), "WiFi antenna holder", "printed")
    tb.add(tb.box((0, -45, -6.5), (8, 26, 1.0)), "WiFi antenna", "black")
    tb.flush()
    ports["ant"] = ((-5, -33, -6.5), (-1, 0, 0))

    # ============================================================== Orange Pi 5 Pro (component side DOWN, HDMI to the rear)
    op = new_comp(drone, "Orange Pi 5 Pro (89x56)")
    tb = TB(op, A)
    tb.add(tb.D(tb.box((0, 0, -9.8), (89, 56, 1.6)), *[tb.cyl((x, y, -12), (x, y, -8), 1.35) for x, y in OPI_HOLES + [SHIELD_POST]]),
           "Orange Pi 5 Pro PCB", "pcb_blue")
    tb.add(tb.U(*([tb.box((-8, 2, -11.6), (15, 15, 2))] + [tb.box((-14 + 3 * k, 2, -14.6), (1.0, 15, 4)) for k in range(5)])),
           "Heatsink RK3588S", "alu")
    tb.add(tb.U(*([tb.box((10, 4, -11.1), (12, 12, 1))] + [tb.box((5.5 + 3 * k, 4, -13.6), (1.0, 12, 4)) for k in range(4)])),
           "Heatsink LPDDR5", "alu")
    tb.add(tb.box((37.75, -1, -18.6), (17.5, 14.5, 16)), "USB-A double (USB3.0 + USB2.0)", "steel")
    tb.add(tb.box((37.75, -18, -18.6), (17.5, 14.5, 16)), "USB-A double (USB2.0 x2)", "steel")
    tb.add(tb.box((36.0, 18, -17.35), (21, 16, 13.5)), "Ethernet RJ45", "steel")
    tb.add(tb.box((-16, -22.75, -13.6), (15, 11.5, 6)), "HDMI 0", "steel")
    tb.add(tb.box((2, -22.75, -13.6), (15, 11.5, 6)), "HDMI 1", "steel")
    tb.add(tb.box((-33.5, -24.75, -12.2), (8.9, 7.5, 3.2)), "USB-C power", "steel")
    pins = [tb.box((-12, 24.5, -11.85), (51, 5.08, 2.5))]
    pins += [tb.box((-12 + (i - 9.5) * 2.54, 24.5 + j * 1.27, -16.1), (0.64, 0.64, 6.0)) for i in range(20) for j in (-1, 1)]
    tb.add(tb.U(*pins), "40-pin header (male)", "pin_header")
    tb.add(tb.U(tb.box((-30, 5, -11.3), (12, 12, 1.4)), tb.box((-28, -12, -11.1), (6, 6, 1.0)), tb.box((22, -2, -11.1), (10, 8, 1.0))),
           "OPi components (WiFi, PMIC, eMMC)", "chip")
    tb.add(tb.box((-42, -12, -11.1), (2.6, 2.6, 1.0)), "IPEX antenna socket", "steel")
    for x, y in OPI_HOLES:
        tb.add(tb.cyl((x, y, -12.6), (x, y, -10.6), 2.25), "Screw M2.5 (OPi)", "steel")
    tb.add(tb.cyl((SHIELD_POST[0], SHIELD_POST[1], -21.6), (SHIELD_POST[0], SHIELD_POST[1], -10.6), 2.5), "Nylon standoff M3x11 (shield)", "nylon_black")
    for key, y, name in (("usb_cam", -1.0, "USB-A plug (camera)"), ("usb_th", -18.0, "USB-A plug (TR256i)")):
        tb.add(tb.U(tb.box((40.5, y, -22.6), (12, 12, 4.5)), tb.box((55.5, y, -22.6), (18, 16, 8.5))), name, "black")
        ports[key] = ((64.5, y, -22.6), (1, 0, 0))
    tb.flush()

    # ============================================================== SKYRIS Orange Pi 5 Pro Shield V2 (+ cooler)
    sh = new_comp(drone, "SKYRIS Shield V2 + cooler")
    tb = TB(sh, A)
    tb.add(tb.D(tb.box((-12, 0, -22.4), (65, 56, 1.6)), *[tb.cyl((x, y, -25), (x, y, -20), 1.35) for x, y in OPI_HOLES + [SHIELD_POST]]),
           "SKYRIS shield PCB", "pcb_black")
    tb.add(tb.box((-12, 24.5, -17.35), (51, 5.08, 8.5)), "40-pin header (female)", "black")
    tb.add(tb.cyl((SHIELD_POST[0], SHIELD_POST[1], -25.2), (SHIELD_POST[0], SHIELD_POST[1], -23.2), 2.75), "Screw M3 (shield)", "steel")
    parts = [tb.D(tb.box((-14, -4, -28.2), (30, 30, 10)), tb.cyl((-14, -4, -34), (-14, -4, -22), 14.0)),
             tb.cyl((-14, -4, -33.0), (-14, -4, -23.6), 6.0)]
    for k in range(7):
        a = 2 * math.pi * k / 7.0
        c, s = math.cos(a), math.sin(a)
        parts.append(tb.box((-14 + 10 * c, -4 + 10 * s, -28.3), (8.8, 1.2, 7.0), (c, s, 0), (-s, c, 0)))
    tb.add(tb.U(*parts), "Cooler 30x30 5V", "black")
    tb.add(tb.U(tb.box((-36, -8, -25.2), (7, 7, 4)), tb.box((-36, 6, -23.95), (5, 4, 1.5)), tb.box((-36, -22, -24.7), (8, 3.5, 3))),
           "Shield components (DC-DC, switches)", "chip")
    pins = []
    for xc in (-4.0, 6.0):
        pins.append(tb.box((xc, -24, -24.45), (7.62, 2.54, 2.5)))
        pins += [tb.box((xc - 2.54 + 2.54 * j, -24, -28.7), (0.64, 0.64, 6.0)) for j in range(3)]
    tb.add(tb.U(*pins), "PWM0 / PWM1 headers", "pin_header")
    for key, x, w in (("uart0", -30, 9.5), ("uart2", -16, 9.5), ("i2c", 8, 7.5)):
        conn(tb, ports, key, (x, 17, -25.325), (0, 1, 0), (1, 0, 0), w, 4.25, 4.5, 6.0, "Shield %s socket" % key.upper(),
             "Shield %s plug" % key.upper() if key != "uart2" else None, "white", "white")
    conn(tb, ports, "vin", (15, -20, -29.2), (0, 0, -1), (1, 0, 0), 6, 4.5, 6, 6, "Shield V IN socket (PH2.0)", "Shield V IN plug", "red", "red")
    conn(tb, ports, "led", (16, -6, -29.2), (0, 0, -1), (1, 0, 0), 7.5, 5.8, 6, 6, "Shield LED socket", "Shield LED plug", "white", "white")
    conn(tb, ports, "fan5v", (16, 6, -29.2), (0, 0, -1), (1, 0, 0), 5, 5.8, 6, 6, "Shield 5V socket (cooler)", "Shield 5V plug", "white", "white")
    conn(tb, ports, None, (6, -14, -29.2), (0, 0, -1), (1, 0, 0), 5, 5.8, 6, 0, "Shield 5V socket (free)", None, "white", None)
    tb.flush()

    # ============================================================== camera plate: USB camera + VL53L1X
    cp = new_comp(drone, "Camera plate + USB camera + VL53L1X")
    A.set(rrect_extrude(cp, 0, 13, 80, 118, 8, -42.0, -40.0, "Camera plate"), "carbon")
    cam_posts = [(sx * 17.0, 50 + sy * 17.0) for sx in (-1, 1) for sy in (-1, 1)]
    vents = [t.cyl((-14 + 10 * math.cos(a), -4 + 10 * math.sin(a), -43), (-14 + 10 * math.cos(a), -4 + 10 * math.sin(a), -39), 2.5)
             for a in [2 * math.pi * k / 8 for k in range(8)]]
    cut_tools(cp, [t.cyl((0, 50, -43), (0, 50, -39), 8.0), t.cyl((27, 62, -43), (27, 62, -39), 4.0), t.cyl((-14, -4, -43), (-14, -4, -39), 3.0)]
              + [t.cyl((x, y, -43), (x, y, -39), 1.6) for x, y in LOW_STANDOFFS] + [t.cyl((x, y, -43), (x, y, -39), 1.35) for x, y in cam_posts]
              + vents)
    tb = TB(cp, A)
    for x, y in cam_posts:
        tb.add(tb.cyl((x, y, -40.0), (x, y, -20.0), 2.25), "Nylon standoff M2.5x20", "nylon_black")
    tb.add(tb.D(tb.box((0, 50, -19.2), (38, 38, 1.6)), *[tb.cyl((x, y, -21), (x, y, -17), 1.35) for x, y in cam_posts]), "USB camera board", "pcb_green")
    tb.add(tb.U(tb.box((0, 50, -22.5), (14, 14, 5)), tb.cyl((0, 50, -44.0), (0, 50, -25.0), 7.0)), "Camera lens (M12)", "black")
    conn(tb, ports, "cam", (9, 36, -16.9), (1, 0, 0), (0, 1, 0), 8, 3.0, 5, 4, "Camera USB socket", "Camera USB plug", "white", "white")
    tb.add(tb.U(tb.box((27, 58, -39.2), (13, 25, 1.6)), tb.box((27, 62, -40.8), (4.9, 2.5, 1.6))), "Laser rangefinder VL53L1X", "pcb_purple")
    tb.flush()
    ports["vl53"] = ((27, 47.5, -37.9), (0, -1, 0))

    # ============================================================== motors, props, legs, guard
    mot = new_comp(drone, "Motor 2306 (x4)", reuse_for=MOTORS, z=4.0)
    tb = TB(mot, A)
    tb.add(tb.cyl((0, 0, 0), (0, 0, 5.0), 13.5), "Motor base", "motor_dark")
    tb.add(tb.cyl((0, 0, 5.0), (0, 0, 19.0), 14.0), "Motor bell", "motor_green")
    tb.add(tb.cyl((0, 0, 19.0), (0, 0, 29.0), 2.5), "Shaft M5", "alu")
    tb.add(tb.cyl((0, 0, 26.5), (0, 0, 30.5), 4.6), "M5 nut", "steel")
    tb.flush()
    prop = new_comp(drone, "Propeller 6in 3-blade (x4)", reuse_for=MOTORS, z=4.0 + 21.0, rotations=[0, 40, 80, 20])
    build_prop(prop, A)
    gear = new_comp(drone, "Landing gear (x4): mount + spacer + leg",
                    matrices=[place(mx, my, 0, math.degrees(math.atan2(ty - my, tx - mx))) for (mx, my), (tx, ty) in zip(MOTORS, ARM_TIPS)])
    build_landing_gear(gear, A)
    gd = new_comp(drone, "Prop guard (x4) + jumpers")
    build_guard(gd, A, [b for b in fr.bRepBodies if b.name.startswith("Arm")])

    # ============================================================== our thermal mount + TR256i under the camera plate
    mounts = [o for o in root.occurrences if o.component.name.startswith("Thermal Mount (print) - looking down")]
    mods = [o for o in root.occurrences if o.component.name.startswith("TR256i (reference) - down")]
    if mounts:
        m = adsk.core.Matrix3D.create()
        m.setWithCoordinateSystem(P3(*THERMAL_ORIGIN), adsk.core.Vector3D.create(0, -1, 0), adsk.core.Vector3D.create(1, 0, 0),
                                  adsk.core.Vector3D.create(0, 0, 1))
        drone.occurrences.addExistingComponent(mounts[0].component, m)
        if mods:
            mo = drone.occurrences.addExistingComponent(mods[0].component, m)
            plug = [b for b in mo.bRepBodies if b.name == "USB-C plug"]
            if plug:
                bb = plug[0].boundingBox
                x = (bb.minPoint.x + bb.maxPoint.x) * 5
                if abs(x) > 200:          # proxy reported in world coordinates
                    x -= OFFSET_X
                ports["usb_tr256i"] = ((x, bb.minPoint.y * 10, (bb.minPoint.z + bb.maxPoint.z) * 5), (0, -1, 0))

    # ============================================================== wiring harness (every conductor = swept pipe)
    hn = new_comp(drone, "Wiring harness")
    W = Harness(hn, A, ports)
    W.cable("ESC-FC 8p", "fc_esc", "esc_fc", [(-5.5, -26.8, 20.5)], 0.4,
            ["yellow", "blue", "white", "white", "white", "white", "red", "black"], side=(1, 0, 0),
            ends=["FC ESC plug 8p", "ESC FC plug 8p"])
    W.cable("TELEM1 - ELRS", "telem1", "rx", [(-24.5, -3.5, 25.3), (-25, -10, 21), (-22, -22, 13), (-14, -25, 9.5), (-5, -24, 8.0),
                                             (-3, -22, 8.0)], 0.45, ["red", "black", "yellow", "green"],
            up=(0, 0, 1), ends=["FC TELEM1 plug", "ELRS receiver"])
    W.cable("TELEM2 - UART0", "telem2", "uart0", [(-6, 24.2, 25.3), (-6, 30, 21), (-6, 34, 12), (-6, 34, 4), (-6, 34, -4), (-6, 34, -10),
                                                  (-9, 33.5, -13), (-21, 30.5, -16.5), (-29, 30.5, -24.5)],
            0.45, ["red", "black", "yellow", "green"], side=(1, 0, 0), ends=["FC TELEM2 plug", "Shield UART0 plug"])
    W.cable("Battery power ESC", (4.5, -16, 15.2), "xt60_f", [(7, -26, 19), (16, -27, 30), (24, -20, 35.5), (25, -17, 38.0)],
            1.6, ["red", "black"], side=(1, 0, 0), ends=["ESC 4in1 PCB", "XT60 female (ESC lead)"], start_axis=(0, -1, 0))
    W.cable("V IN Orange Pi", (10.7, -16, 14.4), "vin", [(10.7, -20, 14.4), (12.5, -29, 9), (14, -36, 4), (14, -36, -4), (14.5, -35, -14),
                                                       (15, -31, -31), (15, -26, -37.5), (15, -22.8, -37.6)],
            0.6, ["red", "black"], side=(1, 0, 0), ends=["ESC 4in1 PCB", "Shield V IN plug"], start_axis=(0, -1, 0))
    W.cable("Battery lead", "xt60_m", (4, -52.5, 70), [(22, -28, 82), (12, -48, 82), (5, -60, 77), (4, -64, 72)], 1.6, ["red", "black"],
            side=(1, 0, 0), ends=["XT60 male (battery lead)", "Battery 4S LiPo"], end_axis=(0, -1, 0))
    W.cable("Balance lead", (-8, -52.5, 72), (-20.4, -44, 60), [(-8, -55.5, 72), (-14, -57, 66), (-20.4, -50, 60), (-20.4, -47, 60)], 0.4,
            ["red", "red", "red", "red", "black"], up=(0, 0, 1), ends=["Battery 4S LiPo", "Balance plug JST-XH 5p"],
            start_axis=(0, -1, 0), end_axis=(0, -1, 0))
    W.cable("LED strip", "led", (55.36, -30.06, -7.0), [(20, -9, -37.3), (36, -20, -37), (50, -29, -34), (56, -31.5, -27), (53.5, -29.8, -16),
                                                       (53, -29, -10)], 0.4, ["red", "white", "black"], up=(0, 0, 1),
            ends=["Shield LED plug", "LED strip WS2812 (58 LEDs)"], end_axis=(-0.879, 0.477, 0))
    W.cable("Cooler", (1, 8, -28.2), "fan5v", [(6, 8, -31), (10, 7.5, -36), (14, 6.5, -38.5)], 0.4, ["red", "black"],
            side=(1, 0, 0), ends=["Cooler 30x30 5V", "Shield 5V plug"], start_axis=(1, 0, 0))
    W.cable("VL53L1X - I2C", "vl53", "i2c", [(20, 41, -35), (12, 37, -31), (11, 31, -27)], 0.4, ["red", "black", "yellow", "green"], up=(0, 0, 1),
            ends=["Laser rangefinder VL53L1X", "Shield I2C plug"])
    W.cable("Camera USB", "cam", "usb_cam", [(17, 36, -16.9), (20.5, 34.5, -17.8), (27, 31.5, -21), (44, 30, -26), (60, 24, -27.5),
                                            (68, 10, -25), (71, 3, -23.2)], 1.3, ["black"],
            ends=["Camera USB plug", "USB-A plug (camera)"])
    if "usb_tr256i" in ports:
        p0 = ports["usb_tr256i"][0]
        W.cable("TR256i USB", "usb_tr256i", "usb_th", [(p0[0], -60, -47), (10, -60, -38), (36, -54, -34),
                                                      (62, -38, -29), (72, -26, -24.5)], 1.3, ["black"],
                ends=["USB-C plug", "USB-A plug (TR256i)"])
    W.cable("WiFi antenna", "ant", (-42, -12, -11.6), [(-8, -33, -6.6), (-20, -32.6, -7.5), (-40, -32, -8), (-46, -29, -9), (-47, -18, -11.5),
                                                      (-45.5, -12.5, -13.3)], 0.6, ["grey"],
            ends=["WiFi antenna holder", "IPEX antenna socket"], end_axis=(0, 0, -1))
    W.cable("ELRS antenna", (0, -48, 8.0), (-6, -62, 16), [(0, -51, 8.6), (-3, -56, 12)], 0.5, ["black"], ends=["ELRS receiver"],
            start_axis=(0, -1, 0))
    for (mx, my) in MOTORS:
        sx, sy = (1 if mx > 0 else -1), (1 if my > 0 else -1)
        tag = ("F" if sy > 0 else "R") + ("R" if sx > 0 else "L")
        W.cable("ESC pigtail " + tag, (sx * 16.5, sy * 8, 14.4), (sx * 26, sy * 8, 9.2), [(sx * 19.5, sy * 8, 14.3)],
                0.6, ["black"] * 3, up=(0, 0, 1), ends=["ESC 4in1 PCB", "MR30 female (ESC)"], end_axis=(-sx, 0, 0))
        L = math.hypot(mx, my)
        u = (mx / L, my / L)
        W.cable("Motor %s phases" % tag, (sx * 47, sy * 8, 9.2), (mx - u[0] * 13.5, my - u[1] * 13.5, 6.5),
                [(sx * 51, sy * 16, 7.5), (sx * 47, sy * 32, 5.8)]
                + arm_path(data["arms"], mx, my, [0.56, 0.7], 4.65) + [(mx - u[0] * 19, my - u[1] * 19, 5.5)],
                0.6, ["black"] * 3, up=(0, 0, 1), ends=["MR30 male (motor)", "Motor base", "Arm"],
                start_axis=(sx, 0, 0), end_axis=(-u[0], -u[1], 0))
    json.dump(W.meta, open(HARNESS_JSON, "w"), indent=1)

    if design.snapshots.hasPendingSnapshot:
        design.snapshots.add()
    app.activeViewport.fit()
    n = sum(c.bRepBodies.count for c in [drone] + [o.component for o in drone.occurrences])
    print("TR256i USB port:", ports.get("usb_tr256i"))
    for f in W.failed:
        print("PIPE FAILED:", f)
    print("OK TECHNIC 6S detailed model: %d occurrences, %d bodies, %d wires in %d cables" %
          (drone.occurrences.count, n, len(W.meta["wires"]), len(W.meta["cables"])))


# ============================================================================== wiring
class Harness(object):
    """Cables between ports. Each conductor is a pipe swept along a fitted 3D spline; multi-core cables lie side by side."""
    LOOK = {"red": "w_red", "black": "w_black", "yellow": "w_yellow", "green": "w_green", "white": "w_white", "blue": "w_blue", "grey": "w_grey"}

    def __init__(self, comp, A, ports):
        self.comp, self.A, self.ports = comp, A, ports
        self.meta = {"cables": {}, "wires": {}}
        self.failed = []
        self.tbm = adsk.fusion.TemporaryBRepManager.get()

    def _end(self, p, axis):
        if isinstance(p, str):
            return self.ports[p]
        return (p, axis)

    def cable(self, name, a, b, mids, r, colors, up=None, side=None, ends=(), start_axis=None, end_axis=None):
        (pa, aa) = self._end(a, start_axis)
        (pb, ab) = self._end(b, end_axis)
        n = len(colors)
        sp = 2 * r + 0.12
        off_max = (n - 1) / 2.0 * sp
        lead = max(2.5, 1.2 + r + off_max, 3 * r)
        pts = [tuple(pa)]
        if aa is not None:
            pts.append(vadd(pa, vmul(aa, lead)))
        pts += [tuple(m) for m in mids]
        if ab is not None:
            pts.append(vadd(pb, vmul(ab, lead)))
        pts.append(tuple(pb))
        pts = dedupe(pts)
        dense = round_path(pts, max(2.5 * r, off_max + 1.6 * r))
        tans = [vnorm(vsub(dense[min(i + 1, len(dense) - 1)], dense[max(i - 1, 0)])) for i in range(len(dense))]
        lat, prev = [], None
        for tv in tans:
            if up is not None:
                Lv = vcross(tv, up)
            else:
                h = side or (1, 0, 0)
                Lv = vsub(h, vmul(tv, vdot(h, tv)))
            if vlen(Lv) < 0.3:
                Lv = prev if prev is not None else vperp(tv)
                Lv = vsub(Lv, vmul(tv, vdot(Lv, tv)))
            Lv = vnorm(Lv)
            if prev is not None and vdot(Lv, prev) < 0:
                Lv = vmul(Lv, -1)
            lat.append(Lv)
            prev = Lv
        sm = []
        for i in range(len(lat)):                      # smooth the lay direction, keep it perpendicular to the wire
            acc = (0.0, 0.0, 0.0)
            for j in range(max(0, i - 5), min(len(lat), i + 6)):
                acc = vadd(acc, lat[j])
            acc = vsub(acc, vmul(tans[i], vdot(acc, tans[i])))
            sm.append(vnorm(acc) if vlen(acc) > 1e-6 else lat[i])
        self.meta["cables"][name] = {"ends": list(ends), "n": n, "r": r}
        for k, col in enumerate(colors):
            off = (k - (n - 1) / 2.0) * sp
            wpts = [vadd(p, vmul(Lv, off)) for p, Lv in zip(dense, sm)]
            dp = decimate(wpts, max(2.0, 3.0 * r))
            try:
                if min_radius(dp) < 1.25 * r:
                    raise RuntimeError("bend radius %.2f < %.2f" % (min_radius(dp), 1.25 * r))
                body = pipe(self.comp, dp, r)
            except RuntimeError as e:
                body = tube(self.comp, wpts, r, self.tbm)
                self.failed.append("%s #%d -> tube fallback (%s)" % (name, k + 1, str(e).splitlines()[0][:50]))
            body.name = "Wire %s #%d (%s)" % (name, k + 1, col)
            self.A.set(body, self.LOOK.get(col, "w_black"))
            self.meta["wires"][body.name] = name


def round_path(pts, R):
    """Polyline -> dense polyline with every corner bent on an arc (radius R, reduced if the segments are short)."""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        d1, d2 = vnorm(vsub(b, a)), vnorm(vsub(c, b))
        cosf = max(-1.0, min(1.0, vdot(d1, d2)))
        phi = math.acos(cosf)
        if phi < math.radians(2):
            out.append(b)
            continue
        tlen = R * math.tan(phi / 2)
        tlen = min(tlen, 0.48 * vlen(vsub(b, a)), 0.48 * vlen(vsub(c, b)))
        Rr = tlen / math.tan(phi / 2)
        p1 = vsub(b, vmul(d1, tlen))
        nvec = vnorm(vsub(d2, vmul(d1, cosf)))
        cen = vadd(p1, vmul(nvec, Rr))
        steps = max(2, int(math.degrees(phi) / 10))
        for k in range(steps + 1):
            al = phi * k / steps
            out.append(vadd(cen, vadd(vmul(nvec, -Rr * math.cos(al)), vmul(d1, Rr * math.sin(al)))))
    out.append(pts[-1])
    dense = [out[0]]
    for q in out[1:]:                                   # subdivide long straight runs
        p = dense[-1]
        L = vlen(vsub(q, p))
        m = int(L / 1.0)
        for k in range(1, m):
            dense.append(vadd(p, vmul(vsub(q, p), k / float(m))))
        if L > 0.05:
            dense.append(q)
    return dense


def decimate(pts, step):
    """Even spacing for the fitted spline (closely spaced points make Fusion splines wiggle -> self-intersecting pipes)."""
    out = [pts[0]]
    acc = 0.0
    for i in range(1, len(pts) - 1):
        acc += vlen(vsub(pts[i], pts[i - 1]))
        if acc >= step:
            out.append(pts[i])
            acc = 0.0
    if len(out) > 1 and vlen(vsub(pts[-1], out[-1])) < 0.6 * step:
        out.pop()
    out.append(pts[-1])
    return out


def tube(comp, pts, r, t):
    """Fallback wire: union of cylinders (+ spheres at real bends)."""
    q = [pts[0]]
    for p in pts[1:]:
        if vlen(vsub(p, q[-1])) >= 0.8:
            q.append(p)
    if len(q) < 2:
        q.append(pts[-1])
    body = None
    for i in range(1, len(q)):
        seg = t.createCylinderOrCone(P3(*q[i - 1]), cm(r), P3(*q[i]), cm(r))
        if body is None:
            body = seg
            continue
        try:
            t.booleanOperation(body, seg, adsk.fusion.BooleanTypes.UnionBooleanType)
        except RuntimeError:
            pass
        if i < len(q) - 1:
            d1, d2 = vnorm(vsub(q[i], q[i - 1])), vnorm(vsub(q[i + 1], q[i]))
            if vdot(d1, d2) < 0.998:
                try:
                    t.booleanOperation(body, t.createSphere(P3(*q[i]), cm(r * 0.995)), adsk.fusion.BooleanTypes.UnionBooleanType)
                except RuntimeError:
                    pass
    bf = comp.features.baseFeatures.add()
    bf.startEdit()
    comp.bRepBodies.add(body, bf)
    bf.finishEdit()
    return bf.bodies.item(0)


def min_radius(pts):
    best = 1e9
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        ab, bc, ca = vlen(vsub(b, a)), vlen(vsub(c, b)), vlen(vsub(a, c))
        area2 = vlen(vcross(vsub(b, a), vsub(c, a)))
        if area2 > 1e-9:
            best = min(best, ab * bc * ca / (2 * area2))
    return best


def pipe(comp, pts, r):
    sk = comp.sketches.add(comp.xYConstructionPlane)
    coll = adsk.core.ObjectCollection.create()
    for p in pts:
        coll.add(P3(*p))
    spl = sk.sketchCurves.sketchFittedSplines.add(coll)
    path = comp.features.createPath(spl, False)
    pi = comp.features.pipeFeatures.createInput(path, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    pi.sectionSize = adsk.core.ValueInput.createByReal(cm(2 * r))
    f = comp.features.pipeFeatures.add(pi)
    sk.isVisible = False
    return f.bodies.item(0)


def dedupe(pts):
    out = []
    for p in pts:
        if not out or vlen(vsub(p, out[-1])) > 1.0:
            out.append(p)
    return out


def arm_path(arms, mx, my, fracs, z):
    """Points along the middle of the real arm outline (documentation SVG) between the centre and the motor."""
    L = math.hypot(mx, my)
    u = (mx / L, my / L)
    nrm = (-u[1], u[0])
    arm = None
    for a in arms:
        if point_in_poly((0.6 * mx, 0.6 * my), a["outline"]):
            arm = a["outline"]
    out = []
    for f in fracs:
        p = (f * mx, f * my)
        if arm is None:
            out.append((p[0], p[1], z))
            continue
        ts = []
        for i in range(len(arm)):
            q1, q2 = arm[i], arm[(i + 1) % len(arm)]
            d = (q2[0] - q1[0], q2[1] - q1[1])
            den = nrm[0] * (-d[1]) - nrm[1] * (-d[0])
            if abs(den) < 1e-12:
                continue
            rx, ry = q1[0] - p[0], q1[1] - p[1]
            tt = (rx * (-d[1]) - ry * (-d[0])) / den
            s = (nrm[0] * ry - nrm[1] * rx) / den
            if 0 <= s <= 1:
                ts.append(tt)
        ts.sort()
        best = None
        for i in range(0, len(ts) - 1, 2):
            mid = (ts[i] + ts[i + 1]) / 2.0
            if best is None or abs(mid) < abs(best):
                best = mid
        best = best or 0.0
        out.append((p[0] + nrm[0] * best, p[1] + nrm[1] * best, z))
    return out


def point_in_poly(pt, poly):
    x, y = pt
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def conn(tb, ports, key, face, axis, wdir, w, h, d_sock, d_plug, sock_name, plug_name, sock_look, plug_look):
    """Connector: socket body behind the mating face, plug in front of it; the cable starts at the plug's back face."""
    tb.add(tb.box(vadd(face, vmul(axis, -d_sock / 2.0)), (d_sock, w, h), axis, wdir), sock_name, sock_look)
    if plug_name:
        tb.add(tb.box(vadd(face, vmul(axis, d_plug / 2.0)), (d_plug, w - 0.4, h - 0.3), axis, wdir), plug_name, plug_look)
    if key:
        ports[key] = (vadd(face, vmul(axis, d_plug)), tuple(axis))


# ============================================================================== builders (frame parts)
def build_prop(comp, A):
    """6 inch 3-blade prop: hub + tapered blades (flat, 2.5 mm), in the XY plane at z=0..2.5."""
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.sketchCurves.sketchCircles.addByCenterRadius(P3(0, 0), cm(7.0))
    R = 76.2
    prof = [(6, -7.0), (25, -9.0), (50, -7.0), (70, -4.5), (R, -1.0), (R, 1.5), (70, 4.5), (50, 6.5), (25, 8.0), (6, 7.0)]
    for k in range(3):
        a = math.radians(120 * k)
        c, s = math.cos(a), math.sin(a)
        polyline(sk, [(x * c - y * s, x * s + y * c) for x, y in prof])
    profs = adsk.core.ObjectCollection.create()
    for i in range(sk.profiles.count):
        profs.add(sk.profiles.item(i))
    ext = comp.features.extrudeFeatures
    inp = ext.createInput(profs, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    inp.setDistanceExtent(False, adsk.core.ValueInput.createByString("2.5 mm"))
    f = ext.add(inp)
    for b in f.bodies:
        b.name = "Propeller"
        A.set(b, "prop")


def arm_frame(i):
    """Unit vector a (motor -> arm tip, along the arm end) and n (left of a) for corner i."""
    (mx, my), (tx, ty) = MOTORS[i], ARM_TIPS[i]
    L = math.hypot(tx - mx, ty - my)
    a = ((tx - mx) / L, (ty - my) / L)
    return a, (-a[1], a[0])


def gear_screw_xy():
    """World XY of the M3x20 screws that hold each landing-gear mount (they go into the motor's own holes)."""
    out = []
    for i, (mx, my) in enumerate(MOTORS):
        a, n = arm_frame(i)
        out += [(mx + a[0] * u + n[0] * v, my + a[1] * u + n[1] * v) for u, v in GEAR_SCREWS]
    return out


def bez(p0, p1, p2, p3, n=14):
    out = []
    for i in range(n + 1):
        t = i / float(n)
        k = ((1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3)
        out.append((k[0] * p0[0] + k[1] * p1[0] + k[2] * p2[0] + k[3] * p3[0], k[0] * p0[1] + k[1] * p1[1] + k[2] * p2[1] + k[3] * p3[1]))
    return out


def leg_profiles():
    """'Ножка (мал)' (guide step 6, fig. 19/20): flat TPU fin in the vertical plane of the arm (u = outward along the arm
       from the motor axis, z). Top 12 mm sits in the slot of the landing-gear mount; the foot curls inwards under the arm.
       Outline + window (wall >= 5.9 mm, checked offline)."""
    front = bez((17, -17), (26, -34), (12, -64), (-28, -75.5), 16)
    back = bez((-33, -73), (-22, -56), (-10, -38), (-17, -17), 14)
    outline = [(-17, -5), (17, -5)] + front + [(-31, -75.8), (-33.5, -75)] + back[:-1] + [(-17, -17)]
    w1 = bez((10, -21), (16, -34), (4, -56), (-19, -66), 12)
    w2 = bez((-19, -66), (-12, -52), (-4, -36), (-10, -21), 10)
    return outline, w1 + w2[1:-1]


def sketch_loop_xz(sk, pts):
    """Closed polyline in the component XZ plane; pts = (x, z)."""
    L = sk.sketchCurves.sketchLines
    sp = [sk.modelToSketchSpace(P3(x, 0, z)) for x, z in pts]
    first = prev = None
    for i in range(1, len(sp)):
        ln = L.addByTwoPoints(prev if prev else sp[0], sp[i])
        if first is None:
            first = ln.startSketchPoint
        prev = ln.endSketchPoint
    L.addByTwoPoints(prev, first)


def cut_body(comp, body, tools, keep=False):
    """Cut temporary tool bodies (or real bodies when keep=True) from one body."""
    tc = adsk.core.ObjectCollection.create()
    if keep:
        for b in tools:
            tc.add(b)
    else:
        t = adsk.fusion.TemporaryBRepManager.get()
        tool = tools[0]
        for b in tools[1:]:
            t.booleanOperation(tool, b, adsk.fusion.BooleanTypes.UnionBooleanType)
        bf = comp.features.baseFeatures.add()
        bf.startEdit()
        comp.bRepBodies.add(tool, bf)
        bf.finishEdit()
        tc.add(bf.bodies.item(0))
    ci = comp.features.combineFeatures.createInput(body, tc)
    ci.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
    ci.isKeepToolBodies = keep
    comp.features.combineFeatures.add(ci)


def body_named(comp, name):
    return [b for b in comp.bRepBodies if b.name == name][0]


def build_landing_gear(comp, A):
    """Guide step 3 + 6 (fig. 5, 19, 20), one copy per motor, in the arm frame (x = along the arm end, origin = motor axis):
       'Проставка маунта шасси' (spacer) under the arm, 'Маунт шасси' (mount) under it, 2 x M3x20 up through mount + spacer + arm
       into the motor, 'Ножка (мал)' pushed into the mount slot and locked with an M3x14 across the mount."""
    outline, window = leg_profiles()
    sk = comp.sketches.add(comp.xZConstructionPlane)
    sketch_loop_xz(sk, outline)
    sketch_loop_xz(sk, window)
    prof = max([sk.profiles.item(i) for i in range(sk.profiles.count)],
               key=lambda p: (p.boundingBox.maxPoint.x - p.boundingBox.minPoint.x) * (p.boundingBox.maxPoint.y - p.boundingBox.minPoint.y))
    ext = comp.features.extrudeFeatures
    inp = ext.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    inp.setSymmetricExtent(adsk.core.ValueInput.createByString("6 mm"), True)
    leg = ext.add(inp).bodies.item(0)
    leg.name = "Leg (TPU)"
    A.set(leg, "rubber_black")
    sk.isVisible = False

    tb = TB(comp, A)
    tb.add(tb.box((-3.0, 0, -1.5), (30.0, 22.0, 3.0)), "Gear mount spacer", "printed")
    tb.add(tb.U(tb.cyl((-8.0, 0, -15.0), (-8.0, 0, -3.0), 12.0), tb.box((6.0, 0, -9.0), (28.0, 20.0, 12.0))), "Landing gear mount", "printed")
    for u, v in GEAR_SCREWS:
        tb.add(tb.U(tb.cyl((u, v, -17.0), (u, v, -15.0), 2.75), tb.cyl((u, v, -15.0), (u, v, 5.0), 1.45)), "Screw M3x20 (gear mount)", "steel")
    tb.add(tb.U(tb.cyl((0, -12.5, -9.0), (0, -10.0, -9.0), 2.75), tb.cyl((0, -10.0, -9.0), (0, 4.0, -9.0), 1.45)), "Screw M3x14 (leg)", "steel")
    tb.flush()
    mount, spacer = body_named(comp, "Landing gear mount"), body_named(comp, "Gear mount spacer")
    cut_body(comp, mount, [leg], keep=True)                         # the slot = exactly the leg's top
    cut_body(comp, mount, [tb.cyl((u, v, -16), (u, v, -2), 1.6) for u, v in GEAR_SCREWS] + [tb.cyl((0, -11, -9), (0, 11, -9), 1.6)])
    cut_body(comp, spacer, [tb.cyl((u, v, -4), (u, v, 1), 1.6) for u, v in GEAR_SCREWS])
    cut_body(comp, leg, [tb.cyl((0, -4, -9), (0, 4, -9), 1.6)])


def build_guard(comp, A, arms):
    """Guide step 7 (fig. 21-23): 4 x 'Защита пропеллера' clipped onto the arm ends (clip + 2 rails + tall outer band with a
       post at each end), joined by 2 x 'Перемычка (мал)' + 2 x 'Перемычка (бол)' screwed (M3x8) onto the posts.
       Optional M3x12 through clip + arm-tip hole."""
    z0, z1 = 6.0, 34.0
    R, T = GUARD_R, 2.5
    pl = offset_plane(comp, z0)
    posts = []                                        # (x, y, corner, side)
    for i, (mx, my) in enumerate(MOTORS):
        th = math.atan2(my, mx)
        a0, a1 = th - math.radians(GUARD_HALF_DEG), th + math.radians(GUARD_HALF_DEG)
        am = th
        sk = comp.sketches.add(pl)
        L = sk.sketchCurves.sketchLines
        Ar = sk.sketchCurves.sketchArcs

        def p(r, ang):
            return P3(mx + r * math.cos(ang), my + r * math.sin(ang))
        l1 = L.addByTwoPoints(p(R - T / 2, a0), p(R + T / 2, a0))
        l2 = L.addByTwoPoints(p(R - T / 2, a1), p(R + T / 2, a1))
        Ar.addByThreePoints(l1.startSketchPoint, p(R - T / 2, am), l2.startSketchPoint)
        Ar.addByThreePoints(l1.endSketchPoint, p(R + T / 2, am), l2.endSketchPoint)
        A.set(extrude_prof(comp, sk.profiles.item(0), z1 - z0, "Guard band"), "guard")
        sk.isVisible = False
        for ang in (a0, a1):
            posts.append((mx + R * math.cos(ang), my + R * math.sin(ang), i, ang))

    tb = TB(comp, A)
    for x, y, _, _ in posts:
        tb.add(tb.cyl((x, y, 4.0), (x, y, 36.0), 4.5), "Guard post", "guard")
        tb.add(tb.U(tb.cyl((x, y, 30.0), (x, y, 42.0), 1.45), tb.cyl((x, y, 42.0), (x, y, 44.5), 2.75)), "Screw M3x8 (jumper)", "steel")
    # jumpers: pair each post with the nearest post of the neighbouring guard
    done = set()
    for k, (x, y, i, _) in enumerate(posts):
        best = min([q for q in range(len(posts)) if posts[q][2] != i], key=lambda q: math.hypot(posts[q][0] - x, posts[q][1] - y))
        key = tuple(sorted((k, best)))
        if key in done:
            continue
        done.add(key)
        x2, y2 = posts[best][0], posts[best][1]
        L = math.hypot(x2 - x, y2 - y)
        kind = "long" if L > 240 else "short"
        d = ((x2 - x) / L, (y2 - y) / L)
        bar = tb.bar((x + d[0] * 4.0, y + d[1] * 4.0, 39.0), (x2 - d[0] * 4.0, y2 - d[1] * 4.0), (7.0, 5.0))
        boss = tb.U(bar, tb.D(tb.cyl((x, y, 36.0), (x, y, 42.0), 5.5), tb.cyl((x, y, 35), (x, y, 43), 1.6)),
                    tb.D(tb.cyl((x2, y2, 36.0), (x2, y2, 42.0), 5.5), tb.cyl((x2, y2, 35), (x2, y2, 43), 1.6)))
        tb.add(boss, "Guard jumper (%s)" % kind, "guard")
    tm = adsk.fusion.TemporaryBRepManager.get()
    clips = []
    for i, (mx, my) in enumerate(MOTORS):
        a, n = arm_frame(i)
        tx, ty = ARM_TIPS[i]
        arm = min(arms, key=lambda b: math.hypot(bbc(b.boundingBox)[0] * 10 - tx, bbc(b.boundingBox)[1] * 10 - ty))
        c = (mx + a[0] * 28.0, my + a[1] * 28.0, 2.0)
        clip = tb.box(c, (16.0, 16.0, 10.0), (a[0], a[1], 0), (n[0], n[1], 0))
        tb.D(clip, tm.copy(arm), tb.cyl((tx, ty, -4), (tx, ty, 8), 1.6))
        tb.add(clip, "Guard clip", "guard")
        tb.add(tb.U(tb.cyl((tx, ty, -3.0), (tx, ty, 7.0), 1.45), tb.cyl((tx, ty, 7.0), (tx, ty, 9.5), 2.75)), "Screw M3x12 (guard)", "steel")
        clips.append((i, a, n))
    tb.flush()
    # rails: clip -> both ends of the band (round 6 mm rods, below the prop disc)
    for i, a, n in clips:
        mx, my = MOTORS[i]
        for x, y, ci, ang in posts:
            if ci != i:
                continue
            k = 1.0 if (x - mx) * n[0] + (y - my) * n[1] > 0 else -1.0
            th = math.atan2(my, mx)
            mid = th + 0.55 * (ang - th)
            pts = [(mx + a[0] * 33 + n[0] * 4 * k, my + a[1] * 33 + n[1] * 4 * k, 2.0),
                   (mx + a[0] * 42 + n[0] * 13 * k, my + a[1] * 42 + n[1] * 13 * k, 3.5),
                   (mx + 78 * math.cos(mid), my + 78 * math.sin(mid), 7.0),
                   (x, y, 9.0)]
            dense = round_path(pts, 14.0)
            dp = decimate(dense, 9.0)
            try:
                body = pipe(comp, dp, 3.0)
            except RuntimeError:
                body = tube(comp, dense, 3.0, tm)
            body.name = "Guard rail"
            A.set(body, "guard")


# ============================================================================== geometry helpers
def cm(v):
    return v / 10.0


def P3(x, y, z=0.0):
    return adsk.core.Point3D.create(cm(x), cm(y), cm(z))


def V3(v):
    return adsk.core.Vector3D.create(*[float(c) for c in v])


def vadd(a, b):
    return tuple(x + y for x, y in zip(a, b))


def vsub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def vmul(a, s):
    return tuple(x * s for x in a)


def vdot(a, b):
    return sum(x * y for x, y in zip(a, b))


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def vlen(a):
    return math.sqrt(vdot(a, a))


def vnorm(a):
    n = vlen(a)
    return vmul(a, 1.0 / n) if n > 1e-12 else (1.0, 0.0, 0.0)


def vperp(t):
    return vcross(t, (0, 0, 1)) if abs(t[2]) < 0.9 else vcross(t, (1, 0, 0))


def place(x, y, z, deg=0.0):
    m = adsk.core.Matrix3D.create()
    if deg:
        m.setToRotation(math.radians(deg), adsk.core.Vector3D.create(0, 0, 1), adsk.core.Point3D.create(0, 0, 0))
    m.translation = adsk.core.Vector3D.create(cm(x), cm(y), cm(z))
    return m


def new_comp(parent, name, reuse_for=None, z=0.0, rotations=None, matrices=None):
    """Create a component; extra occurrences get their final transform at creation (no later moves)."""
    if matrices is None:
        if reuse_for:
            rot = rotations or [0] * len(reuse_for)
            matrices = [place(x, y, z, a) for (x, y), a in zip(reuse_for, rot)]
        else:
            matrices = [adsk.core.Matrix3D.create()]
    occ = parent.occurrences.addNewComponent(adsk.core.Matrix3D.create())   # helper copy at identity
    comp = occ.component
    comp.name = name
    if len(matrices) == 1 and matrices[0].isEqualTo(adsk.core.Matrix3D.create()):
        return comp
    for m in matrices:
        parent.occurrences.addExistingComponent(comp, m)
    occ.deleteMe()                     # (Fusion: copies placed relative to a rotated first copy end up offset)
    return comp


class Tools(object):
    """Temporary B-Rep shapes (mm in, cm inside Fusion)."""
    def __init__(self):
        self.t = adsk.fusion.TemporaryBRepManager.get()

    def box(self, c, s, ax=(1, 0, 0), ay=(0, 1, 0)):
        return self.t.createBox(adsk.core.OrientedBoundingBox3D.create(P3(*c), V3(ax), V3(ay), cm(s[0]), cm(s[1]), cm(s[2])))

    def cyl(self, a, b, r):
        return self.t.createCylinderOrCone(P3(*a), cm(r), P3(*b), cm(r))

    def bar(self, a, b2, wh):
        """horizontal bar from a (x, y, z) to b2 (x, y) at height a[2], cross-section w x h"""
        dx, dy = b2[0] - a[0], b2[1] - a[1]
        L = math.hypot(dx, dy)
        return self.box(((a[0] + b2[0]) / 2, (a[1] + b2[1]) / 2, a[2]), (L, wh[0], wh[1]), (dx / L, dy / L, 0), (-dy / L, dx / L, 0))

    def U(self, *bodies):
        base = bodies[0]
        for b in bodies[1:]:
            self.t.booleanOperation(base, b, adsk.fusion.BooleanTypes.UnionBooleanType)
        return base

    def D(self, base, *tools):
        for b in tools:
            self.t.booleanOperation(base, b, adsk.fusion.BooleanTypes.DifferenceBooleanType)
        return base


class TB(Tools):
    """Collects temporary bodies and adds them to a component in ONE base feature; names/appearances matched by bbox + volume."""
    def __init__(self, comp, A):
        Tools.__init__(self)
        self.comp, self.A, self.items = comp, A, []

    def add(self, body, name, look):
        self.items.append((body, name, look))
        return body

    def flush(self):
        if not self.items:
            return
        comp = self.comp
        bf = comp.features.baseFeatures.add()
        bf.startEdit()
        for body, _, _ in self.items:
            comp.bRepBodies.add(body, bf)
        bf.finishEdit()
        made = [bf.bodies.item(i) for i in range(bf.bodies.count)]
        if len(made) != len(self.items):
            raise RuntimeError("base feature body count mismatch in %s: %d vs %d" % (comp.name, len(made), len(self.items)))
        free = list(made)
        for body, name, look in self.items:
            c0 = bbc(body.boundingBox)
            best = min(free, key=lambda b: vlen(vsub(bbc(b.boundingBox), c0)) + abs(b.volume - body.volume) * 100)
            free.remove(best)
            best.name = name
            self.A.set(best, look)
        self.items = []


def bbc(bb):
    return ((bb.minPoint.x + bb.maxPoint.x) / 2, (bb.minPoint.y + bb.maxPoint.y) / 2, (bb.minPoint.z + bb.maxPoint.z) / 2)


def cut_tools(comp, tools):
    """Cut the union of temporary tool bodies from every body of comp."""
    if not tools:
        return
    t = adsk.fusion.TemporaryBRepManager.get()
    tool = tools[0]
    for b in tools[1:]:
        t.booleanOperation(tool, b, adsk.fusion.BooleanTypes.UnionBooleanType)
    for b in list(comp.bRepBodies):
        bf = comp.features.baseFeatures.add()
        bf.startEdit()
        comp.bRepBodies.add(t.copy(tool), bf)
        bf.finishEdit()
        tools_c = adsk.core.ObjectCollection.create()
        tools_c.add(bf.bodies.item(0))
        ci = comp.features.combineFeatures.createInput(b, tools_c)
        ci.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
        ci.isKeepToolBodies = False
        comp.features.combineFeatures.add(ci)


def polyline(sk, pts):
    L = sk.sketchCurves.sketchLines
    prev = prev_sp = first_sp = None
    for i, (x, y) in enumerate(pts):
        p = P3(x, y)
        if prev is None:
            prev = p
            continue
        ln = L.addByTwoPoints(prev_sp if prev_sp else prev, p)
        prev_sp = ln.endSketchPoint
        if i == 1:
            first_sp = ln.startSketchPoint
    L.addByTwoPoints(prev_sp, first_sp)


def offset_plane(comp, z_mm):
    ci = comp.constructionPlanes.createInput()
    ci.setByOffset(comp.xYConstructionPlane, adsk.core.ValueInput.createByString("%s mm" % z_mm))
    return comp.constructionPlanes.add(ci)


def extrude_prof(comp, prof, h_mm, name):
    ext = comp.features.extrudeFeatures
    inp = ext.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    inp.setDistanceExtent(False, adsk.core.ValueInput.createByString("%s mm" % h_mm))
    b = ext.add(inp).bodies.item(0)
    b.name = name
    return b


def poly_extrude(comp, pts, z0, z1, name):
    pl = offset_plane(comp, z0) if abs(z0) > 1e-9 else comp.xYConstructionPlane
    sk = comp.sketches.add(pl)
    polyline(sk, pts)
    prof = max([sk.profiles.item(i) for i in range(sk.profiles.count)], key=lambda p: p.areaProperties().area)
    return extrude_prof(comp, prof, z1 - z0, name)


def rrect_sketch(sk, cx, cy, w, h, r):
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    L = sk.sketchCurves.sketchLines
    Ar = sk.sketchCurves.sketchArcs
    l_b = L.addByTwoPoints(P3(x0 + r, y0), P3(x1 - r, y0))
    l_r = L.addByTwoPoints(P3(x1, y0 + r), P3(x1, y1 - r))
    l_t = L.addByTwoPoints(P3(x1 - r, y1), P3(x0 + r, y1))
    l_l = L.addByTwoPoints(P3(x0, y1 - r), P3(x0, y0 + r))
    c = math.cos(math.radians(45))
    Ar.addByThreePoints(l_b.endSketchPoint, P3(x1 - r + r * c, y0 + r - r * c), l_r.startSketchPoint)
    Ar.addByThreePoints(l_r.endSketchPoint, P3(x1 - r + r * c, y1 - r + r * c), l_t.startSketchPoint)
    Ar.addByThreePoints(l_t.endSketchPoint, P3(x0 + r - r * c, y1 - r + r * c), l_l.startSketchPoint)
    Ar.addByThreePoints(l_l.endSketchPoint, P3(x0 + r - r * c, y0 + r - r * c), l_b.startSketchPoint)


def rrect_extrude(comp, cx, cy, w, h, r, z0, z1, name):
    pl = offset_plane(comp, z0) if abs(z0) > 1e-9 else comp.xYConstructionPlane
    sk = comp.sketches.add(pl)
    rrect_sketch(sk, cx, cy, w, h, r)
    return extrude_prof(comp, sk.profiles.item(0), z1 - z0, name)


class Appear(object):
    LOOKS = {"carbon": "Carbon Fiber - Plain", "alu": "Aluminum - Satin", "alu_black": "Aluminum - Anodized Glossy (Grey)",
             "battery": "Paint - Metallic (Silver)", "rubber_black": "Plastic - Matte (Black)", "nylon_black": "Plastic - Matte (Black)",
             "printed": "Plastic - Matte (Black)", "pcb_black": "Paint - Enamel Glossy (Black)", "pcb_blue": "Paint - Enamel Glossy (Blue)",
             "pcb_green": "Paint - Enamel Glossy (Green)", "pcb_purple": "Plastic - Glossy (Blue)", "chip": "Plastic - Glossy (Black)",
             "steel": "Steel - Satin", "pin_header": "Gold - Polished", "white": "Plastic - Glossy (White)", "red": "Plastic - Glossy (Red)",
             "black": "Plastic - Glossy (Black)", "xt60": "Plastic - Glossy (Yellow)", "rx": "Plastic - Translucent Glossy (Blue)",
             "led": "LED - SMD 5050 - 20lm (White)", "motor_dark": "Paint - Enamel Glossy (Dark Grey)", "motor_green": "Paint - Metallic (Green)",
             "prop": "Plastic - Translucent Glossy (Gray)", "guard": "Plastic - Matte (Black)",
             "w_red": "Plastic - Glossy (Red)", "w_black": "Plastic - Glossy (Black)", "w_yellow": "Plastic - Glossy (Yellow)",
             "w_green": "Plastic - Glossy (Green)", "w_white": "Plastic - Glossy (White)", "w_blue": "Plastic - Glossy (Blue)",
             "w_grey": "Plastic - Glossy (Grey)"}

    def __init__(self, app, design):
        self.design, self.cache = design, {}
        self.lib = {}
        for lib in app.materialLibraries:
            for i in range(lib.appearances.count):
                a = lib.appearances.item(i)
                self.lib.setdefault(a.name, a)

    def set(self, body, look):
        name = self.LOOKS.get(look)
        if not name or name not in self.lib:
            return
        if name not in self.cache:
            ex = self.design.appearances.itemByName(name)
            self.cache[name] = ex if ex else self.design.appearances.addByCopy(self.lib[name], name)
        body.appearance = self.cache[name]
