#!/usr/bin/env python3
"""TECHNIC 6S hover test: arm -> climb to 1.5 m -> position-hold 5 s -> slow descent -> land -> disarm.

Uses the TECHNIC simple_offboard services (navigate / land / get_telemetry), same as block programming.
Safety: Ctrl+C or any error while airborne => LAND (never cuts motors in the air).
        Too high / lost position / disarmed unexpectedly => abort + land.

On the drone:
    source ~/technic_ws/devel/setup.bash
    python3 hover_test.py --dry-run       # all checks, never arms
    python3 hover_test.py                 # real flight (5 s countdown)
Options: --alt 1.5 --hold 5 --climb-speed 0.5 --descent-speed 0.25 --min-voltage 21.6 --yes
A CSV log is written to ~/flight_logs/.
"""
import argparse, csv, math, os, sys, time
import rospy
from mavros_msgs.msg import ExtendedState
from mavros_msgs.srv import CommandBool
from sensor_msgs.msg import Range
from technic.srv import Navigate, GetTelemetry
from std_srvs.srv import Trigger

ap = argparse.ArgumentParser()
ap.add_argument("--alt", type=float, default=1.5, help="hover height above take-off point, m")
ap.add_argument("--hold", type=float, default=5.0, help="position-hold time, s")
ap.add_argument("--climb-speed", type=float, default=0.5, help="m/s")
ap.add_argument("--descent-speed", type=float, default=0.25, help="m/s (slow)")
ap.add_argument("--min-voltage", type=float, default=21.6, help="battery total volts (6S: 3.6 V/cell)")
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--yes", action="store_true", help="skip countdown")
a = ap.parse_args()
if not 0.5 <= a.alt <= 3.0:
    sys.exit("--alt must be 0.5 .. 3.0 m")
CEILING = a.alt + 0.8            # abort + land if we ever go higher than this
ARRIVE_TOL = 0.15                # m
CLIMB_TIMEOUT = a.alt / a.climb_speed + 10

rospy.init_node("hover_test", disable_signals=True)
st = {"ext": None, "range": None}
rospy.Subscriber("/mavros/extended_state", ExtendedState, lambda m: st.__setitem__("ext", m))
rospy.Subscriber("/rangefinder/range", Range, lambda m: st.__setitem__("range", m.range))
for s in ("/navigate", "/land", "/get_telemetry", "/mavros/cmd/arming"):
    rospy.wait_for_service(s, timeout=10)
navigate = rospy.ServiceProxy("/navigate", Navigate)
land_srv = rospy.ServiceProxy("/land", Trigger)
telem = rospy.ServiceProxy("/get_telemetry", GetTelemetry)
arming = rospy.ServiceProxy("/mavros/cmd/arming", CommandBool)

os.makedirs(os.path.expanduser("~/flight_logs"), exist_ok=True)
log_path = os.path.expanduser(time.strftime("~/flight_logs/hover_%Y%m%d_%H%M%S.csv"))
log_f = open(log_path, "w", newline="")
log_w = csv.writer(log_f)
log_w.writerow(["t", "phase", "armed", "mode", "x", "y", "z", "height", "range", "vz", "voltage"])
T0 = time.time()
z0 = 0.0
hold_xy = (0.0, 0.0)

def sample(phase, show=False):
    t = telem(frame_id="map")
    h = t.z - z0
    log_w.writerow(["%.2f" % (time.time() - T0), phase, t.armed, t.mode, "%.3f" % t.x, "%.3f" % t.y,
                    "%.3f" % t.z, "%.3f" % h, "%.3f" % (st["range"] or float("nan")), "%.2f" % t.vz, "%.2f" % t.voltage])
    if show:
        print("%-10s h=%5.2f m  rng=%5.2f  drift=%4.2f m  vz=%+5.2f  %5.2f V  %s %s"
              % (phase, h, st["range"] or float("nan"), math.hypot(t.x - hold_xy[0], t.y - hold_xy[1]),
                 t.vz, t.voltage, "ARMED" if t.armed else "disarmed", t.mode), flush=True)
    return t, h

def check_safe(t, h, phase):
    if not t.armed:
        raise RuntimeError("disarmed unexpectedly during %s" % phase)
    if h > CEILING:
        raise RuntimeError("too high: %.2f m > %.2f m ceiling" % (h, CEILING))
    if math.isnan(t.x) or math.isnan(t.z):
        raise RuntimeError("lost local position")

def wait_arrival(phase, timeout):
    start, i = time.time(), 0
    while True:
        t, h = sample(phase, show=(i % 5 == 0))
        check_safe(t, h, phase)
        d = telem(frame_id="navigate_target")
        if math.sqrt(d.x ** 2 + d.y ** 2 + d.z ** 2) < ARRIVE_TOL:
            return t, h
        if time.time() - start > timeout:
            raise RuntimeError("%s timed out after %.0f s (h=%.2f m)" % (phase, timeout, h))
        i += 1
        time.sleep(0.1)

def land_and_disarm():
    print("LANDING ...", flush=True)
    r = land_srv()
    if not r.success:
        print("  land service: %s" % r.message)
    start, i = time.time(), 0
    while time.time() - start < 30:
        t, h = sample("land", show=(i % 5 == 0))
        if not t.armed:
            return "landed + auto-disarmed by PX4"
        if st["ext"] and st["ext"].landed_state == ExtendedState.LANDED_STATE_ON_GROUND and time.time() - start > 3:
            arming(False)
        i += 1
        time.sleep(0.1)
    return "STILL ARMED after 30 s - use the web 'Land' button / RC kill switch!"

# ---------------- pre-flight checks ----------------
t = telem(frame_id="map")
ext = None
for _ in range(30):
    ext = st["ext"]
    if ext and st["range"] is not None:
        break
    time.sleep(0.1)
problems = []
if not t.connected:                                         problems.append("FCU not connected")
if t.armed:                                                 problems.append("already armed")
if math.isnan(t.x) or math.isnan(t.z):                      problems.append("no local position (optical flow / ArUco / rangefinder)")
if t.voltage < a.min_voltage:                               problems.append("battery %.2f V < %.2f V" % (t.voltage, a.min_voltage))
if not ext or ext.landed_state != ExtendedState.LANDED_STATE_ON_GROUND: problems.append("FC not reporting ON_GROUND")
if st["range"] is None or not (0.0 <= st["range"] < 0.3): problems.append("rangefinder reading %s (expected < 0.3 m on ground)" % st["range"])
if abs(math.degrees(t.roll)) > 10 or abs(math.degrees(t.pitch)) > 10: problems.append("not level (roll %.0f, pitch %.0f deg)" % (math.degrees(t.roll), math.degrees(t.pitch)))
print("Pre-flight: connected=%s armed=%s mode=%s pos=(%.2f, %.2f, %.2f) range=%s battery=%.2f V"
      % (t.connected, t.armed, t.mode, t.x, t.y, t.z, st["range"], t.voltage))
print("Plan: arm -> climb to %.1f m at %.2f m/s -> hold %.0f s -> descend at %.2f m/s -> land -> disarm  (ceiling %.1f m)"
      % (a.alt, a.climb_speed, a.hold, a.descent_speed, CEILING))
if problems:
    sys.exit("NOT SAFE TO FLY:\n  - " + "\n  - ".join(problems))
if a.dry_run:
    print("DRY RUN OK - all checks passed, nothing armed. Log: %s" % log_path)
    sys.exit(0)

if not a.yes:
    print("!!! Clear area, people back >= 3 m. Ctrl+C now to cancel.")
    for i in range(5, 0, -1):
        print("  take-off in %d ..." % i, flush=True)
        time.sleep(1)

z0, hold_xy = t.z, (t.x, t.y)
airborne = False
result = "?"
try:
    r = navigate(x=0, y=0, z=a.alt, yaw=0, speed=a.climb_speed, frame_id="body", auto_arm=True)
    if not r.success:
        raise RuntimeError("navigate/arm failed: %s" % r.message)
    airborne = True
    print("ARMED - climbing", flush=True)
    t, h = wait_arrival("climb", CLIMB_TIMEOUT)
    hold_xy = (t.x, t.y)
    print("Reached %.2f m - position hold %.0f s" % (h, a.hold), flush=True)
    start, i = time.time(), 0
    while time.time() - start < a.hold:
        t, h = sample("hold", show=(i % 5 == 0))
        check_safe(t, h, "hold")
        i += 1
        time.sleep(0.1)
    t, h = sample("hold", show=True)
    down = max(0.0, h - 0.25)
    print("Slow descent %.2f m at %.2f m/s" % (down, a.descent_speed), flush=True)
    r = navigate(x=0, y=0, z=-down, yaw=0, speed=a.descent_speed, frame_id="body", auto_arm=False)
    if not r.success:
        raise RuntimeError("descent navigate failed: %s" % r.message)
    wait_arrival("descend", down / a.descent_speed + 10)
except KeyboardInterrupt:
    print("\nCtrl+C - aborting: landing")
except Exception as e:
    print("\nABORT: %s" % e)
finally:
    try:
        if airborne or telem(frame_id="map").armed:
            result = land_and_disarm()
        else:
            result = "never armed"
    except KeyboardInterrupt:
        result = "script stopped during landing - PX4 continues AUTO.LAND on its own"
    try:
        rospy.ServiceProxy("/simple_offboard/release", Trigger)()
    except Exception:
        pass
    sample("end", show=True)
    log_f.close()
    print("RESULT: %s\nLog: %s" % (result, log_path))
    rospy.signal_shutdown("done")
