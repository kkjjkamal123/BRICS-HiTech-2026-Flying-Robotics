#!/usr/bin/env python3
"""Bench motor ramp test for TECHNIC 6S.  PROPS OFF ONLY.

Arm -> ramp throttle 0 -> 50 % -> hold -> ramp slowly back to 0 -> disarm.
Uses the TECHNIC simple_offboard `set_rates` service (roll/pitch/yaw rate = 0, only thrust changes)
and logs the PWM the flight controller sends to motor outputs 1-4 (/mavros/rc/out), so the test is
visible even with the motors unplugged.

On the drone:
    source ~/technic_ws/devel/setup.bash
    python3 motor_ramp_test.py --dry-run     # checks only, never arms
    python3 motor_ramp_test.py               # real test, 5 s countdown, Ctrl+C = stop + disarm
Options: --max 0.5 --up 3 --hold 2 --down 10 --yes (skip countdown)
"""
import argparse, sys, time
import rospy
from mavros_msgs.msg import State, ExtendedState, RCOut
from mavros_msgs.srv import CommandBool, CommandLong
from sensor_msgs.msg import BatteryState
from technic.srv import SetRates

ap = argparse.ArgumentParser()
ap.add_argument("--max", type=float, default=0.5, help="peak thrust 0..1 (default 0.5 = 50 %%)")
ap.add_argument("--up", type=float, default=3.0, help="seconds to ramp up")
ap.add_argument("--hold", type=float, default=2.0, help="seconds at peak")
ap.add_argument("--down", type=float, default=10.0, help="seconds to ramp down (slow)")
ap.add_argument("--dry-run", action="store_true", help="check everything, never arm")
ap.add_argument("--yes", action="store_true", help="skip the 5 s countdown")
a = ap.parse_args()
if not 0.0 < a.max <= 0.6:
    sys.exit("--max must be in (0, 0.6] for a bench test")

rospy.init_node("motor_ramp_test", disable_signals=True)   # let Ctrl+C reach our finally-block
st = {"state": None, "ext": None, "pwm": [], "bat": None}
rospy.Subscriber("/mavros/state", State, lambda m: st.__setitem__("state", m))
rospy.Subscriber("/mavros/extended_state", ExtendedState, lambda m: st.__setitem__("ext", m))
rospy.Subscriber("/mavros/rc/out", RCOut, lambda m: st.__setitem__("pwm", list(m.channels[:4])))
rospy.Subscriber("/mavros/battery", BatteryState, lambda m: st.__setitem__("bat", m.voltage))
for s in ("/set_rates", "/mavros/cmd/arming", "/mavros/cmd/command"):
    rospy.wait_for_service(s, timeout=10)
set_rates = rospy.ServiceProxy("/set_rates", SetRates)
arming = rospy.ServiceProxy("/mavros/cmd/arming", CommandBool)
command = rospy.ServiceProxy("/mavros/cmd/command", CommandLong)

t0 = time.time()
while st["state"] is None or st["ext"] is None:
    if time.time() - t0 > 5:
        sys.exit("No /mavros/state or /mavros/extended_state - is technic.service running?")
    time.sleep(0.1)

def log(msg):
    s = st["state"]
    print("%-28s armed=%-5s mode=%-12s PWM1-4=%s" % (msg, s.armed, s.mode, st["pwm"] or "n/a"), flush=True)

# ---- pre-checks -------------------------------------------------------------------------------
s = st["state"]
print("FCU connected: %s | armed: %s | mode: %s | landed_state: %d (1 = on ground) | battery: %s V"
      % (s.connected, s.armed, s.mode, st["ext"].landed_state, "%.2f" % st["bat"] if st["bat"] else "n/a"))
if not s.connected:
    sys.exit("ABORT: FCU not connected")
if s.armed:
    sys.exit("ABORT: already armed - disarm first")
if st["ext"].landed_state != ExtendedState.LANDED_STATE_ON_GROUND:
    sys.exit("ABORT: FC does not report ON_GROUND")
print("Plan: arm -> 0 to %.0f %% in %.1f s -> hold %.1f s -> %.0f %% to 0 in %.1f s -> disarm"
      % (a.max * 100, a.up, a.hold, a.max * 100, a.down))
if a.dry_run:
    print("DRY RUN OK - nothing armed.")
    sys.exit(0)

if not a.yes:
    print("!!! PROPS MUST BE OFF. Ctrl+C now to cancel.")
    for i in range(5, 0, -1):
        print("  arming in %d ..." % i, flush=True)
        time.sleep(1)

def thrust(t, arm=False):
    r = set_rates(roll_rate=0.0, pitch_rate=0.0, yaw_rate=0.0, thrust=float(t), auto_arm=arm)
    if not r.success:
        raise RuntimeError("set_rates(thrust=%.2f) failed: %s" % (t, r.message))

def disarm():
    try:
        thrust(0.0)
    except Exception as e:
        print("  (thrust 0 failed: %s)" % e)
    for _ in range(3):
        arming(False)
        time.sleep(0.7)
        if not st["state"].armed:
            return "normal disarm"
    # PX4 refuses a normal disarm if its land detector thinks it is flying -> force (safe: props off)
    command(command=400, param1=0.0, param2=21196.0)
    time.sleep(0.7)
    return "FORCE disarm" if not st["state"].armed else "DISARM FAILED - pull the battery!"

RATE = 10.0
peak_pwm = []
try:
    thrust(0.05, arm=True)          # switches to OFFBOARD and arms (blocking)
    log("ARMED")
    steps = [(a.up, lambda f: 0.05 + (a.max - 0.05) * f, "ramp up"),
             (a.hold, lambda f: a.max, "hold"),
             (a.down, lambda f: a.max * (1 - f), "ramp down")]
    for dur, fn, name in steps:
        n = max(1, int(dur * RATE))
        for i in range(1, n + 1):
            if not st["state"].armed:
                raise RuntimeError("FC disarmed by itself during '%s' (PX4 auto-disarm / failsafe)" % name)
            t = fn(i / n)
            thrust(t)
            if i % int(RATE / 2) == 0 or i == n:
                log("%-9s thrust %4.0f %%" % (name, t * 100))
            if name == "hold" and st["pwm"]:
                peak_pwm = st["pwm"]
            time.sleep(1 / RATE)
    thrust(0.0)
    time.sleep(1.0)
    log("thrust 0")
except KeyboardInterrupt:
    print("\nCtrl+C - stopping")
except Exception as e:
    print("\nERROR: %s" % e)
finally:
    print("Disarm: %s" % disarm())
    try:
        rospy.ServiceProxy("/simple_offboard/release", __import__("std_srvs.srv", fromlist=["Trigger"]).Trigger)()
    except Exception:
        pass
    log("END")
    if peak_pwm:
        print("PWM at %.0f %% thrust (motors 1-4): %s" % (a.max * 100, peak_pwm))
    rospy.signal_shutdown("done")
