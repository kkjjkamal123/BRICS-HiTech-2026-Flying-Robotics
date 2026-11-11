#!/usr/bin/env python3
"""
TECHNIC 6S wiring diagram + connection table (from the SKYRIS assembly guide, offline/docs/.../Sborka.html + Sborka2.html,
ConnectingToPX4.html, LedStrip.html, LaserRangefinder.html, GPIO.html) - matches the wires in the Fusion model.
Output: cad/out/TECHNIC6S_wiring_diagram.pdf / .png
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

BOX = {   # name: (x, y, w, h, colour, subtitle)
    "BAT": (0.5, 8.6, 3.0, 1.2, "#e8e8e8", "Battery 4S LiPo"),
    "ESC": (5.0, 8.4, 3.4, 1.6, "#d9e2f3", "ESC 4in1 (stack, bottom)"),
    "FC": (5.0, 5.6, 3.4, 1.9, "#d9e2f3", "PX4 flight controller\n(stack, top)"),
    "MOT": (10.2, 8.4, 3.1, 1.6, "#e2f0d9", "Motors M1-M4\n2306"),
    "RX": (0.5, 5.9, 3.0, 1.2, "#fff2cc", "ELRS receiver"),
    "SH": (5.0, 2.1, 3.4, 2.6, "#fde9d9", "SKYRIS Orange Pi 5 Pro\nShield V2"),
    "OPI": (10.2, 2.1, 3.1, 2.6, "#d9ead3", "Orange Pi 5 Pro\n(RK3588S, ROS)"),
    "LED": (0.5, 3.6, 3.0, 1.0, "#ffffff", "LED strip WS2812\n58 LEDs (ring)"),
    "FAN": (0.5, 2.2, 3.0, 0.9, "#ffffff", "Cooler 30 mm 5 V"),
    "TOF": (0.5, 0.6, 3.0, 1.1, "#ffffff", "Laser rangefinder\nVL53L1X"),
    "CAM": (14.4, 3.7, 2.9, 1.0, "#ffffff", "USB camera (main,\nlooking down)"),
    "TR": (14.4, 2.3, 2.9, 1.1, "#fce4d6", "TR256i thermal\n(our mount)"),
    "ANT": (14.4, 0.9, 2.9, 0.9, "#ffffff", "WiFi antenna"),
    "SERVO": (5.0, 0.2, 3.4, 1.0, "#f3f3f3", "PWM0 / PWM1:\nservo / gripper (optional)"),
}
LINKS = [  # (from, to, label, colours, style)
    ("BAT", "ESC", "XT60 on the battery plate", ["#c00000", "#000000"], "-"),
    ("ESC", "MOT", "4 x MR30 (3 phase wires each)", ["#000000"] * 3, "-"),
    ("ESC", "FC", "8-pin cable 'ESC 4in1 to FC'\nsticker 'FC' -> FC side", ["#f1c232", "#3d85c6", "#999999", "#c00000", "#000000"], "-"),
    ("RX", "FC", "TELEM1 (JST-GH): 5V GND TX RX", ["#c00000", "#000000", "#f1c232", "#38761d"], "-"),
    ("FC", "SH", "TELEM2 -> UART0 (MAVLink to OPi)", ["#c00000", "#000000", "#f1c232", "#38761d"], "-"),
    ("ESC", "SH", "power lead,\nred PH2.0 -> 'V IN'", ["#c00000", "#000000"], "-", [(9.3, 8.75), (9.3, 4.3)]),
    ("SH", "OPI", "40-pin header", ["#b8860b"], "-"),
    ("LED", "SH", "LED: 5V GND DIN(GPIO21)", ["#c00000", "#cccccc", "#000000"], "-"),
    ("FAN", "SH", "+5V (any of 3)", ["#c00000", "#000000"], "-"),
    ("TOF", "SH", "I2C", ["#c00000", "#000000", "#f1c232", "#38761d"], "-"),
    ("CAM", "OPI", "USB-A", ["#000000"], "-"),
    ("TR", "OPI", "USB-C -> USB-A", ["#000000"], "-"),
    ("ANT", "OPI", "IPEX", ["#888888"], "-"),
    ("SERVO", "SH", "PWM0 (GPIO pin 17)", ["#999999"], "--"),
    ("FC", "OPI", "USB-C (optional link, CBRK_USB_CHK=197848)", ["#999999"], "--"),
]
TABLE = [
    ("1", "Battery 4S (XT60 male)", "XT60 female on battery plate -> ESC power pads", "Main power"),
    ("2", "ESC 4in1 (8-pin)", "Flight controller ESC port", "VBAT, current, telemetry, M1-M4 signals"),
    ("3", "Motors M1-M4 (MR30)", "ESC 4in1 MR30 pigtails", "3 phases each; zip-tie wires mid-arm"),
    ("4", "ELRS receiver", "FC TELEM1", "RC link (CRSF); bind phrase in ExpressLRS"),
    ("5", "FC TELEM2", "Shield UART0", "MAVLink <-> mavros on the Orange Pi"),
    ("6", "Power lead (red PH2.0)", "Shield V IN", "Orange Pi + shield supply"),
    ("7", "Shield", "Orange Pi 40-pin header + M3x11 standoff", "Shield V2 sits on the OPi"),
    ("8", "Cooler 30 mm", "Shield +5V", "Labels down"),
    ("9", "LED strip WS2812 (58)", "Shield LED", "led_count 58, gpio 21"),
    ("10", "VL53L1X", "Shield I2C", "rangefinder_vl53l1x:=true; optical flow needs it"),
    ("11", "USB camera", "Orange Pi USB-A", "main_camera.launch: direction_z down"),
    ("12", "TR256i thermal camera", "Orange Pi USB-A (2nd stack)", "Our addition (Case 1 / Case 4)"),
    ("13", "WiFi antenna", "Orange Pi IPEX; antenna in rear holder", "Move it out from between the USB ports"),
    ("14", "Servo / gripper (opt.)", "Shield PWM0 (G 5V S)", "gpio mode 17 pwm; servo power from 5 V"),
    ("15", "FC USB-C (opt.)", "Orange Pi USB", "only if UART link unused; fcu_conn:=usb"),
]


def centre(k):
    x, y, w, h = BOX[k][:4]
    return x + w / 2, y + h / 2


def edge_point(k, toward):
    x, y, w, h = BOX[k][:4]
    cx, cy = x + w / 2, y + h / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    sx = (w / 2) / abs(dx) if dx else 1e9
    sy = (h / 2) / abs(dy) if dy else 1e9
    s = min(sx, sy)
    return cx + dx * s, cy + dy * s


def main():
    fig = plt.figure(figsize=(16.54, 11.69))
    fig.suptitle("TECHNIC 6S - complete wiring (as modelled in Fusion)", x=0.02, ha="left", fontsize=16, weight="bold")
    ax = fig.add_axes([0.02, 0.36, 0.96, 0.58])
    ax.set_xlim(0, 17.6)
    ax.set_ylim(0, 10.3)
    ax.axis("off")
    for link in LINKS:
        a, b, label, cols, style = link[:5]
        way = list(link[5]) if len(link) > 5 else []
        p1 = edge_point(a, way[0] if way else centre(b))
        p2 = edge_point(b, way[-1] if way else centre(a))
        if way:   # leave/enter the boxes horizontally
            p1 = (BOX[a][0] + BOX[a][2], way[0][1])
            p2 = (BOX[b][0] + BOX[b][2], way[-1][1])
        pts = [p1] + way + [p2]
        n = len(cols)
        for i, c in enumerate(cols):
            o = (i - (n - 1) / 2.0) * 0.045
            xs, ys = [], []
            for j in range(len(pts) - 1):
                (x0, y0), (x1, y1) = pts[j], pts[j + 1]
                L = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
                nx, ny = -(y1 - y0) / L, (x1 - x0) / L
                xs += [x0 + nx * o, x1 + nx * o]
                ys += [y0 + ny * o, y1 + ny * o]
            ax.plot(xs, ys, color=c, lw=1.6, ls=style, zorder=1)
        k = (len(pts) - 1) // 2
        (x0, y0), (x1, y1) = pts[k], pts[k + 1]
        L = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        nx, ny = -(y1 - y0) / L, (x1 - x0) / L
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        ax.text(mx + nx * 0.18, my + ny * 0.18, label, fontsize=7.4, ha="center", va="center", zorder=3,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#bbbbbb", lw=0.5))
    for k, (x, y, w, h, col, title) in BOX.items():
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.12", fc=col, ec="#333333", lw=1.1, zorder=2))
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=9.5, weight="bold", zorder=3)
    tx = fig.add_axes([0.02, 0.02, 0.96, 0.32])
    tx.axis("off")
    rows = [("#", "From", "To", "Note")] + TABLE
    tab = tx.table(cellText=[list(r) for r in rows[1:]], colLabels=list(rows[0]), loc="upper left", cellLoc="left",
                   colWidths=[0.03, 0.25, 0.36, 0.36])
    tab.auto_set_font_size(False)
    tab.set_fontsize(8)
    tab.scale(1, 1.18)
    for (r, c), cell in tab.get_celld().items():
        cell.set_edgecolor("#cccccc")
        if r == 0:
            cell.set_facecolor("#0b5394")
            cell.get_text().set_color("white")
            cell.get_text().set_weight("bold")
    fig.text(0.98, 0.005, "Source: SKYRIS TECHNIC 6S assembly guide (offline copy). Solid = installed, dashed = optional.",
             ha="right", fontsize=7.5, color="#555555")
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, "TECHNIC6S_wiring_diagram.%s" % ext), dpi=130)
    print("wiring diagram ->", os.path.join(OUT, "TECHNIC6S_wiring_diagram.pdf"))


if __name__ == "__main__":
    main()
