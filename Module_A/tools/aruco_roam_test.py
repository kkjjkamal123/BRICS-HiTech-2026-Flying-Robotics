#!/usr/bin/env python3
"""TECHNIC 6S ArUco roam test: take off wherever you put it -> lock the start point in the ArUco marker map ->
fly a LAWN-MOWER pattern over the marker field (parallel lines, --spacing apart) -> fly back to the start point ->
slow descent -> land -> disarm.
    --pattern lawnmower (default)  covers the whole safe zone once, line by line
    --pattern random               the old behaviour: random points for --roam seconds, within --radius of the start

No arena size needed: the safe zone comes from the marker map loaded on the drone
(outermost marker centres shrunk by --margin), intersected with a box of +-radius around the start point.
Random points are only picked inside that zone, so the drone stays away from the walls / net.

Safety: Ctrl+C or any error while airborne -> LAND where it is (never cuts motors in the air).
        No marker map seen for > --marker-timeout s -> LAND where it is.
        Outside the safe zone (+0.4 m) or above alt + 0.8 m -> stop roaming, fly home, land.
        RC kill switch (channel 8) always overrides.

On the drone (TECHNIC web terminal or ssh orangepi@10.42.0.1):
    source /opt/ros/noetic/setup.bash; source ~/technic_ws/devel/setup.bash
    python3 aruco_roam_test.py --dry-run     # shows map, safe zone, example points; never arms
    python3 aruco_roam_test.py               # real flight (5 s countdown)
Options: --roam 30 --alt 1.5 --speed 0.3 --margin 0.5 --radius 1.5 --min-hop 0.5 --seed N --map-file PATH
Laptop check of the geometry (no ROS):  python3 aruco_roam_test.py --selftest
A CSV log is written to ~/flight_logs/.
"""
import argparse, csv, math, os, random, re, sys, tempfile, time

LAUNCH = os.path.expanduser("~/technic_ws/src/technic/technic/launch/aruco.launch")
MAP_DIR = os.path.expanduser("~/technic_ws/src/technic/aruco_pose/map")


# ----------------------------------------------------------------------------- geometry (pure, testable)
def parse_map(path):
    """Marker map lines: id length x y z [yaw pitch roll]. Returns [(id, length, x, y, z)]."""
    out = []
    with open(path) as f:
        for line in f:
            line = line.split("#")[0].strip()
            p = line.split()
            if len(p) < 5:
                continue
            try:
                out.append((int(float(p[0])), float(p[1]), float(p[2]), float(p[3]), float(p[4])))
            except ValueError:
                continue
    return out


def safe_zone(markers, home, margin, radius):
    """(x0, y0, x1, y1): marker field shrunk by margin, intersected with home +- radius. None if empty."""
    hx, hy = home
    x0, y0, x1, y1 = hx - radius, hy - radius, hx + radius, hy + radius
    floor = [m for m in markers if abs(m[4]) < 0.3]          # only markers lying on the floor
    if floor:
        xs, ys = [m[2] for m in floor], [m[3] for m in floor]
        x0, y0 = max(x0, min(xs) + margin), max(y0, min(ys) + margin)
        x1, y1 = min(x1, max(xs) - margin), min(y1, max(ys) - margin)
    if x1 - x0 < 0.2 or y1 - y0 < 0.2:
        return None
    return (x0, y0, x1, y1)


def next_point(zone, cur, min_hop, rng, tries=200):
    """Random point inside the zone at least min_hop from cur (best effort)."""
    best, best_d = None, -1.0
    for _ in range(tries):
        p = (rng.uniform(zone[0], zone[2]), rng.uniform(zone[1], zone[3]))
        d = math.hypot(p[0] - cur[0], p[1] - cur[1])
        if d >= min_hop:
            return p
        if d > best_d:
            best, best_d = p, d
    return best


def lawnmower_points(zone, start, spacing):
    """Waypoints that sweep the zone in parallel lines along its longer side, `spacing` apart (spread evenly so
    both edges are flown). Starts at the corner nearest to `start`; consecutive lines run in opposite directions."""
    x0, y0, x1, y1 = zone
    along_x = (x1 - x0) >= (y1 - y0)                       # lines run along the longer side
    a0, a1, b0, b1 = (x0, x1, y0, y1) if along_x else (y0, y1, x0, x1)
    n = max(2, int(math.ceil((b1 - b0) / max(0.05, spacing) - 1e-9)) + 1)
    rows = [b0 + (b1 - b0) * i / (n - 1) for i in range(n)]
    sa, sb = (start[0], start[1]) if along_x else (start[1], start[0])
    if abs(sb - rows[-1]) < abs(sb - rows[0]):
        rows.reverse()
    forward = abs(sa - a0) <= abs(sa - a1)                 # begin at the nearer end of the first line
    pts = []
    for b in rows:
        ends = (a0, a1) if forward else (a1, a0)
        for a_ in ends:
            pts.append((a_, b) if along_x else (b, a_))
        forward = not forward
    return pts


def inside(zone, x, y, tol=0.0):
    return zone[0] - tol <= x <= zone[2] + tol and zone[1] - tol <= y <= zone[3] + tol


def selftest():
    rng = random.Random(1)
    grid = [(i, 0.33, 0.85 * (i % 6), 0.85 * (i // 6), 0.0) for i in range(36)]      # 6x6 field, 0..4.25 m
    z = safe_zone(grid, (0.85, 0.85), 0.5, 1.5)
    assert z == (0.5, 0.5, 2.35, 2.35), z
    cur = (0.85, 0.85)
    for _ in range(500):
        p = next_point(z, cur, 0.5, rng)
        assert inside(z, p[0], p[1]), p
        cur = p
    assert safe_zone(grid[:1], (0, 0), 0.5, 1.5) is None          # single marker: no room -> refuse
    assert safe_zone([], (0, 0), 0.5, 1.0) == (-1.0, -1.0, 1.0, 1.0)   # no map: radius only
    fd, tmp = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write("# id length x y z yaw pitch roll\n0 0.33 0 0 0 0 0 0\n1 0.33 1 0 0 0 0 0\n2 0.33 0 1 0\n")
    assert [m[0] for m in parse_map(tmp)] == [0, 1, 2]
    os.remove(tmp)
    # lawn-mower: official arena map zone (x -2.5..2.5, y -1..1), start near the lower-left corner
    zone = (-2.5, -1.0, 2.5, 1.0)
    pts = lawnmower_points(zone, (-2.0, -0.8), 0.75)
    assert pts[0] == (-2.5, -1.0) and len(pts) == 8, pts                      # 4 lines of 5 m, 0.67 m apart
    assert all(inside(zone, p[0], p[1], 1e-9) for p in pts)
    assert sorted(set(round(p[1], 3) for p in pts)) == [-1.0, -0.333, 0.333, 1.0]
    for k in range(0, len(pts), 2):                                          # each line is straight along x ...
        assert pts[k][1] == pts[k + 1][1] and abs(pts[k][0] - pts[k + 1][0]) == 5.0
    for k in range(1, len(pts) - 1, 2):                                      # ... and the step to the next line is short
        assert pts[k][0] == pts[k + 1][0]
    tall = lawnmower_points((0.0, 0.0, 1.0, 3.0), (0.9, 2.9), 0.5)             # taller than wide: lines along y
    assert tall[0] == (1.0, 3.0) and len(tall) == 6, tall
    print("selftest OK: zone %s, 500 random points all inside, lawn-mower %d waypoints" % (z, len(pts)))


# ----------------------------------------------------------------------------- drone
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", choices=["lawnmower", "random"], default="lawnmower")
    ap.add_argument("--spacing", type=float, default=0.75, help="lawn-mower: distance between lines, m")
    ap.add_argument("--max-time", type=float, default=300.0, help="lawn-mower: give up and fly home after this many seconds")
    ap.add_argument("--roam", type=float, default=30.0, help="random pattern: seconds of roaming")
    ap.add_argument("--alt", type=float, default=1.5, help="flight height above take-off point, m (camera looks straight down: 1.5-2 m sees more markers)")
    ap.add_argument("--speed", type=float, default=0.3, help="m/s while roaming")
    ap.add_argument("--margin", type=float, default=0.5, help="stay this far inside the outermost markers, m")
    ap.add_argument("--radius", type=float, default=None,
                    help="never further than this from the start point, m (default: 1.5 for random, whole field for lawn-mower)")
    ap.add_argument("--min-hop", type=float, default=0.5, help="minimum distance between random points, m")
    ap.add_argument("--marker-timeout", type=float, default=4.0, help="land if no marker map seen this long, s")
    ap.add_argument("--min-voltage", type=float, default=21.6, help="battery total volts (6S: 3.6 V/cell)")
    ap.add_argument("--map-file", help="marker map file (default: the one the drone has loaded)")
    ap.add_argument("--seed", type=int, help="random seed (printed, so a flight can be repeated)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true", help="skip countdown")
    ap.add_argument("--selftest", action="store_true", help="laptop geometry test, no ROS")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not 0.6 <= a.alt <= 2.0:
        sys.exit("--alt must be 0.6 .. 2.0 m")
    mow = a.pattern == "lawnmower"
    if a.radius is None:
        a.radius = 50.0 if mow else 1.5
    if not 0.3 <= a.spacing <= 2.0:
        sys.exit("--spacing must be 0.3 .. 2.0 m")

    import rospy
    from mavros_msgs.msg import ExtendedState
    from mavros_msgs.srv import CommandBool
    from sensor_msgs.msg import Range
    from std_srvs.srv import Trigger
    from technic.srv import Navigate, GetTelemetry

    rospy.init_node("aruco_roam_test", disable_signals=True)
    st = {"ext": None, "range": None, "map_t": 0.0}
    rospy.Subscriber("/mavros/extended_state", ExtendedState, lambda m: st.__setitem__("ext", m))
    rospy.Subscriber("/rangefinder/range", Range, lambda m: st.__setitem__("range", m.range))
    rospy.Subscriber("/aruco_map/pose", rospy.AnyMsg, lambda m: st.__setitem__("map_t", time.time()))
    for s in ("/navigate", "/land", "/get_telemetry", "/mavros/cmd/arming"):
        rospy.wait_for_service(s, timeout=10)
    navigate = rospy.ServiceProxy("/navigate", Navigate)
    land_srv = rospy.ServiceProxy("/land", Trigger)
    telem = rospy.ServiceProxy("/get_telemetry", GetTelemetry)
    arming = rospy.ServiceProxy("/mavros/cmd/arming", CommandBool)
    NAN = float("nan")

    # ---- which marker map is loaded?
    path = a.map_file or rospy.get_param("/aruco_map/map", None)
    if not path:
        try:
            m = re.search(r'name="map"\s+default="([^"]+)"', open(LAUNCH).read())
            path = os.path.join(MAP_DIR, m.group(1)) if m else None
        except IOError:
            path = None
    markers = parse_map(path) if path and os.path.exists(path) else []
    floor = [mk for mk in markers if abs(mk[4]) < 0.3]
    if floor:
        xs, ys = [mk[2] for mk in floor], [mk[3] for mk in floor]
        print("Marker map: %s  (%d markers, centres x %.2f..%.2f  y %.2f..%.2f m)" % (path, len(markers), min(xs), max(xs), min(ys), max(ys)))
    else:
        print("WARNING: no marker map file found (%s) - only the +-%.1f m box around the start limits the roam" % (path, a.radius))

    seed = a.seed if a.seed is not None else int(time.time()) % 100000
    rng = random.Random(seed)

    os.makedirs(os.path.expanduser("~/flight_logs"), exist_ok=True)
    log_path = os.path.expanduser(time.strftime("~/flight_logs/roam_%Y%m%d_%H%M%S.csv"))
    log_f = open(log_path, "w", newline="")
    log_w = csv.writer(log_f)
    log_w.writerow(["t", "phase", "armed", "mode", "x", "y", "z", "target_x", "target_y", "marker_age_s", "voltage"])
    T0 = time.time()
    target = [NAN, NAN]

    def sample(phase, show=False):
        t = telem(frame_id="aruco_map")
        age = time.time() - st["map_t"] if st["map_t"] else float("inf")
        log_w.writerow(["%.2f" % (time.time() - T0), phase, t.armed, t.mode, "%.3f" % t.x, "%.3f" % t.y, "%.3f" % t.z,
                        "%.2f" % target[0], "%.2f" % target[1], "%.1f" % min(age, 999), "%.2f" % t.voltage])
        if show:
            print("%-8s pos=(%5.2f, %5.2f, %4.2f)  target=(%5.2f, %5.2f)  markers %s  %5.2f V  %s %s" % (
                phase, t.x, t.y, t.z, target[0], target[1], "OK" if age < 1.0 else "lost %.1fs" % age,
                t.voltage, "ARMED" if t.armed else "disarmed", t.mode), flush=True)
        return t, age

    def land_and_disarm():
        print("LANDING ...", flush=True)
        try:
            land_srv()
        except Exception as e:
            print("  land service error: %s - USE THE RC" % e)
        start, i = time.time(), 0
        while time.time() - start < 30:
            t, _ = sample("land", show=(i % 5 == 0))
            if not t.armed:
                return "landed + auto-disarmed by PX4"
            if st["ext"] and st["ext"].landed_state == ExtendedState.LANDED_STATE_ON_GROUND and time.time() - start > 3:
                arming(False)
            i += 1
            time.sleep(0.1)
        return "STILL ARMED after 30 s - use the RC kill switch!"

    # ---- pre-flight
    t = telem(frame_id="aruco_map")
    tl = telem(frame_id="map")
    for _ in range(30):
        if st["ext"] and st["range"] is not None:
            break
        time.sleep(0.1)
    problems = []
    if not t.connected:                       problems.append("FCU not connected")
    if t.armed:                               problems.append("already armed")
    if math.isnan(tl.x):                      problems.append("no local position (optical flow / rangefinder)")
    if t.voltage < a.min_voltage:             problems.append("battery %.2f V < %.2f V" % (t.voltage, a.min_voltage))
    if not st["ext"] or st["ext"].landed_state != ExtendedState.LANDED_STATE_ON_GROUND: problems.append("FC not reporting ON_GROUND")
    if st["range"] is None or not (0.0 <= st["range"] < 0.3): problems.append("rangefinder %s (expected < 0.3 m on the ground)" % st["range"])
    if floor and not math.isnan(t.x) and safe_zone(markers, (t.x, t.y), a.margin, a.radius) is None:
        problems.append("start point (%.2f, %.2f) is too close to the edge of the marker field - move it inwards" % (t.x, t.y))
    print("Pre-flight: connected=%s armed=%s mode=%s aruco_map=(%.2f, %.2f) battery=%.2f V seed=%d" % (
        t.connected, t.armed, t.mode, t.x, t.y, t.voltage, seed))
    if math.isnan(t.x):
        print("  (aruco_map not visible from the ground - normal; it is locked right after take-off)")
    else:
        z = safe_zone(markers, (t.x, t.y), a.margin, a.radius)
        if z:
            print("  safe zone if started here: x %.2f..%.2f  y %.2f..%.2f m" % (z[0], z[2], z[1], z[3]))
            if mow:
                wp = lawnmower_points(z, (t.x, t.y), a.spacing)
                length = sum(math.hypot(wp[k + 1][0] - wp[k][0], wp[k + 1][1] - wp[k][1]) for k in range(len(wp) - 1))
                print("  lawn-mower: %d lines, %.1f m, about %.0f s: " % (len(wp) // 2, length, length / a.speed + 3 * len(wp))
                      + " ".join("(%.2f, %.2f)" % p for p in wp))
            else:
                r2, cur, pts = random.Random(seed), (t.x, t.y), []
                for _ in range(5):
                    cur = next_point(z, cur, a.min_hop, r2)
                    pts.append("(%.2f, %.2f)" % cur)
                print("  first random points: " + " ".join(pts))
    if mow:
        print("Plan: take off %.1f m -> lock start -> lawn-mower lines %.2f m apart at %.2f m/s -> back to start -> land" % (a.alt, a.spacing, a.speed))
    else:
        print("Plan: take off %.1f m -> lock start -> roam %.0f s at %.2f m/s -> back to start -> land" % (a.alt, a.roam, a.speed))
    if problems:
        sys.exit("NOT SAFE TO FLY:\n  - " + "\n  - ".join(problems))
    if a.dry_run:
        print("DRY RUN OK - nothing armed.")
        return

    if not a.yes:
        print("!!! Props on, area clear, people back >= 3 m, RC ready (ch8 kill). Ctrl+C now to cancel.")
        for i in range(5, 0, -1):
            print("  take-off in %d ..." % i, flush=True)
            time.sleep(1)

    airborne = False
    result = "?"
    CEIL = a.alt + 0.8

    def check(phase, zone=None):
        t, age = sample(phase)
        if not t.armed:
            raise RuntimeError("disarmed unexpectedly during %s" % phase)
        if age > a.marker_timeout:
            raise RuntimeError("LAND: no marker map for %.1f s" % age)
        if math.isnan(t.x) or math.isnan(t.z):
            raise RuntimeError("LAND: lost aruco_map position")
        if t.z - home_z > CEIL:
            raise RuntimeError("LAND: too high (%.2f m)" % (t.z - home_z))
        if zone and not inside(zone, t.x, t.y, 0.4):
            raise GoHome("left the safe zone at (%.2f, %.2f)" % (t.x, t.y))
        return t

    class GoHome(Exception):
        pass

    def goto(x, y, z, speed, phase, zone=None, deadline=None):
        target[0], target[1] = x, y
        # explicit heading = the heading locked at the start (yaw=NaN semantics differ between firmwares)
        r = navigate(x=x, y=y, z=z, yaw=heading[0], speed=speed, frame_id="aruco_map", auto_arm=False)
        if not r.success:
            raise RuntimeError("navigate failed: %s" % r.message)
        t0, i = time.time(), 0
        dist = math.hypot(x - t.x, y - t.y) if not math.isnan(t.x) else 2.0
        while True:
            tt = check(phase, zone)
            if i % 5 == 0:
                sample(phase, show=True)
            d = telem(frame_id="navigate_target")
            if math.sqrt(d.x ** 2 + d.y ** 2 + d.z ** 2) < 0.15:
                return tt
            if deadline and time.time() > deadline:
                return tt                      # roam time is over -> caller flies home
            if time.time() - t0 > dist / speed + 10:
                raise GoHome("could not reach (%.2f, %.2f)" % (x, y))
            i += 1
            time.sleep(0.1)

    home_z = 0.0
    heading = [0.0]
    try:
        tl = telem(frame_id="map")
        home_z = 0.0
        sample("ground")
        r = navigate(x=0, y=0, z=a.alt, yaw=0, speed=0.5, frame_id="body", auto_arm=True)   # yaw 0 in body = keep heading (as hover_test)
        if not r.success:
            raise RuntimeError("take-off/arm failed: %s" % r.message)
        airborne = True
        print("ARMED - climbing to %.1f m" % a.alt, flush=True)
        t0 = time.time()
        while True:                                            # climb (body frame) + wait for the marker map
            sample("climb")
            t = telem(frame_id="aruco_map")
            tm = telem(frame_id="map")
            if not t.armed:
                raise RuntimeError("did not arm / disarmed")
            if tm.z - tl.z > CEIL:
                raise RuntimeError("LAND: too high during climb")
            d = telem(frame_id="navigate_target")
            if math.sqrt(d.x ** 2 + d.y ** 2 + d.z ** 2) < 0.15 and not math.isnan(t.x):
                break
            if time.time() - t0 > a.alt / 0.5 + 10:
                raise RuntimeError("LAND: %s after take-off" % ("no marker map" if math.isnan(t.x) else "height not reached"))
            time.sleep(0.1)
        home = (t.x, t.y)
        heading[0] = t.yaw                                     # hold this heading for the whole flight
        tm = telem(frame_id="map")
        home_z = t.z - (tm.z - tl.z)                           # floor height in aruco_map = now - height actually climbed
        zone = safe_zone(markers, home, a.margin, a.radius)
        if zone is None:
            raise GoHome("start point is too close to the edge of the marker field - no room to roam")
        print("START locked at aruco_map (%.2f, %.2f), height %.2f m. Safe zone x %.2f..%.2f  y %.2f..%.2f m" % (
            home + (t.z - home_z, zone[0], zone[2], zone[1], zone[3])), flush=True)
        z_fly = home_z + a.alt
        if mow:
            wp = lawnmower_points(zone, home, a.spacing)
            deadline = time.time() + a.max_time
            print("Lawn-mower: %d lines, %d waypoints" % (len(wp) // 2, len(wp)), flush=True)
            for n, p in enumerate(wp):
                if time.time() > deadline:
                    raise GoHome("lawn-mower time limit (%.0f s) reached at waypoint %d of %d" % (a.max_time, n, len(wp)))
                print("-> %s %d/%d (%.2f, %.2f)" % ("line end" if n % 2 else "line start", n + 1, len(wp), p[0], p[1]), flush=True)
                # the way to the first corner may start outside the zone (take-off near the field edge): no zone check there
                goto(p[0], p[1], z_fly, a.speed, "mow", zone if n > 0 else None)
            print("Lawn-mower finished (%d lines) - returning to start" % (len(wp) // 2), flush=True)
            raise GoHome("pattern complete")
        deadline = time.time() + a.roam
        cur, n = home, 0
        while time.time() < deadline:
            p = next_point(zone, cur, a.min_hop, rng)
            n += 1
            print("-> point %d (%.2f, %.2f)  [%.0f s left]" % (n, p[0], p[1], deadline - time.time()), flush=True)
            t = goto(p[0], p[1], z_fly, a.speed, "roam", zone, deadline)
            cur = (t.x, t.y)
        print("Roam finished (%d points) - returning to start" % n, flush=True)
        raise GoHome("roam time over")
    except GoHome as e:
        if airborne:
            print("RETURN: %s" % e, flush=True)
            try:
                goto(home[0], home[1], home_z + a.alt, max(a.speed, 0.3), "return")
                print("Over the start point - slow descent", flush=True)
                goto(home[0], home[1], home_z + 0.25, 0.25, "descend")
            except NameError:
                pass                                           # no home locked -> land in place
            except Exception as e2:
                print("ABORT during return: %s" % e2)
    except KeyboardInterrupt:
        print("\nCtrl+C - landing where it is")
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
        t, _ = sample("end", show=True)
        try:
            print("Landing error vs start point: %.2f m" % math.hypot(t.x - home[0], t.y - home[1]))
        except (NameError, TypeError):
            pass
        log_f.close()
        print("RESULT: %s\nLog: %s  (seed %d)" % (result, log_path, seed))
        rospy.signal_shutdown("done")


if __name__ == "__main__":
    main()
