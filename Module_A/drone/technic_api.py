"""
Flight API wrapper for TECHNIC 6S (simple_offboard services) + a MOCK drone for testing on a laptop.

Real drone (Orange Pi / Gazebo VM):  drone = make_drone(mock=False)
Laptop test without ROS:              drone = make_drone(mock=True)

Same methods for both:
  drone.takeoff(z)                       climb to z metres (body frame), auto-arm
  drone.goto(x, y, z, yaw, frame, speed) fly to point and WAIT until reached (or timeout)
  drone.go(x, y, z, ...)                 send target, do not wait
  drone.reached(tolerance)               True if at the current target
  drone.hover(seconds)
  drone.land()                           land and wait for disarm
  drone.telemetry(frame)                 object with x,y,z,yaw,armed,mode,voltage,cell_voltage,connected
  drone.led(r,g,b, effect)               LED strip (silently ignored if not available)

Python 3.8 compatible.
"""
import math
import threading
import time

NAN = float("nan")


class Telemetry(object):
    def __init__(self, **kw):
        self.x = self.y = self.z = self.yaw = 0.0
        self.vx = self.vy = self.vz = 0.0
        self.armed, self.mode, self.connected = False, "", True
        self.voltage = self.cell_voltage = NAN
        self.frame_id = "map"
        self.__dict__.update(kw)


class DroneBase(object):
    """Common logic (waiting, safety checks) shared by real and mock drones."""
    abort_flag = False

    def __init__(self, min_cell_voltage=3.5, check_frame="aruco_map", log=print, fence=None, max_alt=None,
                 battery_cells=None):
        self.min_cell_voltage = min_cell_voltage
        self.battery_cells = battery_cells   # e.g. 6: PX4 without BAT1_N_CELLS reports cell_voltage = pack voltage
        self._cells_warned = False
        self.check_frame = check_frame
        self.log = log
        self.fence = fence       # (x0, y0, x1, y1) in check_frame: leaving it = land now
        self.max_alt = max_alt   # metres in check_frame: climbing above it = land now
        self.path = []           # flown positions (for the report map)

    @staticmethod
    def _rejected(resp):
        """navigate/land services answer (success, message). Returns the message if the FCU side refused."""
        if resp is None or getattr(resp, "success", True):
            return None
        return getattr(resp, "message", "") or "rejected"

    def outside_fence(self, x, y, z=None):
        """Reason string if (x, y, z) is outside the geofence / altitude limit, else None."""
        if self.fence and not (self.fence[0] <= x <= self.fence[2] and self.fence[1] <= y <= self.fence[3]):
            return "outside geofence (%.2f, %.2f) not in [%.2f, %.2f, %.2f, %.2f]" % ((x, y) + tuple(self.fence))
        if self.max_alt is not None and z is not None and z > self.max_alt:
            return "above altitude limit (%.2f m > %.2f m)" % (z, self.max_alt)
        return None

    # --- to implement
    def go(self, x=0, y=0, z=0, yaw=NAN, speed=0.5, frame_id="aruco_map", auto_arm=False):
        raise NotImplementedError

    def telemetry(self, frame_id=""):
        raise NotImplementedError

    def _land(self):
        raise NotImplementedError

    def sleep(self, s):
        time.sleep(s)

    def now(self):
        return time.time()

    # --- shared
    def reached(self, tolerance=0.2):
        t = self.telemetry("navigate_target")
        return math.sqrt(t.x ** 2 + t.y ** 2 + t.z ** 2) < tolerance

    def safety_problem(self, check_position=True):
        """Returns a reason string if the mission must stop, else None."""
        if DroneBase.abort_flag:
            return "operator abort"
        t = self.telemetry(self.check_frame)
        if not t.connected:
            return "flight controller disconnected"
        if not math.isnan(t.cell_voltage) and 0 < t.cell_voltage < self.min_cell_voltage:
            return "low battery (%.2f V/cell)" % t.cell_voltage
        if not check_position:
            return None
        if self.check_frame and (math.isnan(t.x) or math.isnan(t.y)):
            return "lost position in %s (markers not visible?)" % self.check_frame
        if self.check_frame and not math.isnan(t.x):
            return self.outside_fence(t.x, t.y, None if math.isnan(t.z) else t.z)
        return None

    def goto(self, x=0, y=0, z=0, yaw=NAN, speed=0.5, frame_id="aruco_map", auto_arm=False,
             tolerance=0.2, timeout=30.0, during=None):
        """Fly and wait. `during` is called repeatedly while flying (e.g. perception). Returns True if reached."""
        msg = self._rejected(self.go(x=x, y=y, z=z, yaw=yaw, speed=speed, frame_id=frame_id, auto_arm=auto_arm))
        if msg:
            raise MissionAbort("navigate to (%.2f, %.2f, %.2f %s) rejected: %s" % (x, y, z, frame_id, msg))
        start = self.now()
        self.sleep(0.3)
        while True:
            if during:
                during()
            p = self.safety_problem()
            if p:
                raise MissionAbort(p)
            if self.reached(tolerance):
                self._record()
                return True
            if self.now() - start > timeout:
                self.log("[drone] goto timeout (%.1f,%.1f,%.1f %s)" % (x, y, z, frame_id))
                self._record()
                return False
            self._record()
            self.sleep(0.1)

    def takeoff(self, z=1.0, speed=0.5, tolerance=0.2, timeout=15.0, during=None):
        """Arm and climb z metres. Raises MissionAbort if the drone refuses to arm / take off."""
        self.log("[drone] takeoff to %.2f m" % z)
        msg = self._rejected(self.go(x=0, y=0, z=z, yaw=NAN, speed=speed, frame_id="body", auto_arm=True))
        if msg:
            raise MissionAbort("takeoff rejected: %s" % msg)
        start = self.now()
        while self.now() - start < timeout:
            if during:
                during()
            p = self.safety_problem(check_position=False)    # markers may flicker right at the ground
            if p:
                raise MissionAbort(p)
            if self.reached(tolerance):
                self._record()
                return True
            self.sleep(0.1)
        if not self.telemetry().armed:
            raise MissionAbort("takeoff failed: drone did not arm (check PX4 pre-arm messages in QGC)")
        self.log("[drone] takeoff timeout - target height not reached within %.0f s, continuing" % timeout)
        return False

    def hover(self, seconds, during=None):
        end = self.now() + seconds
        while self.now() < end:
            if during:
                during()
            p = self.safety_problem()
            if p:
                raise MissionAbort(p)
            self.sleep(0.1)

    def land(self, timeout=20.0):
        """Land and wait for disarm. Returns True if the drone disarmed within `timeout`."""
        self.log("[drone] landing")
        msg = self._rejected(self._land())
        if msg:
            self.log("[drone] WARNING: land service refused (%s) - retrying once" % msg)
            self.sleep(0.5)
            msg = self._rejected(self._land())
            if msg:
                self.log("[drone] WARNING: land refused again (%s)" % msg)
                self._land_fallback()
        start = self.now()
        while self.telemetry().armed and self.now() - start < timeout:
            self.sleep(0.2)
        if self.telemetry().armed:
            self.log("[drone] WARNING: still armed %.0f s after the land command - take over with RC / kill switch" % timeout)
            return False
        self.log("[drone] landed")
        return True

    def _land_fallback(self):
        """The land service refused (it needs OFFBOARD). Real drone: ask the flight controller directly."""
        self.log("[drone] LAND WITH THE RC TRANSMITTER")

    def led(self, r=0, g=0, b=0, effect="fill"):
        pass

    def _record(self):
        t = self.telemetry(self.check_frame or "map")
        if not math.isnan(t.x):
            if not self.path or math.hypot(self.path[-1][0] - t.x, self.path[-1][1] - t.y) > 0.05:
                self.path.append((t.x, t.y, t.z))


class MissionAbort(Exception):
    """Stop now and land where we are."""


class ReturnHome(Exception):
    """Stop the mission, fly home, then land."""


# ============================================================================ REAL (ROS)
class TechnicDrone(DroneBase):
    def __init__(self, node_name="mission", init_node=True, **kw):
        import rospy
        self.rospy = rospy
        if init_node:
            rospy.init_node(node_name, disable_signals=True)
        try:
            from technic import srv
        except ImportError:                      # same API in COEX Clover images
            from clover import srv
        from std_srvs.srv import Trigger
        self.srv = srv
        self._get_telemetry = rospy.ServiceProxy("get_telemetry", srv.GetTelemetry)
        self._navigate = rospy.ServiceProxy("navigate", srv.Navigate)
        self._land_srv = rospy.ServiceProxy("land", Trigger)
        self._set_yaw = rospy.ServiceProxy("set_yaw", srv.SetYaw)
        rospy.wait_for_service("navigate", timeout=30)
        self._led = None
        try:                                     # LED strip: /led/set_effect (technic.srv.SetLEDEffect)
            rospy.wait_for_service("led/set_effect", timeout=1.0)
            self._led = rospy.ServiceProxy("led/set_effect", srv.SetLEDEffect)
        except Exception:
            self._led = None
        self._lock = threading.Lock()
        self._pose = {}                          # frame_id -> (telemetry, time) kept fresh by a background thread
        self._pose_threads = {}
        super(TechnicDrone, self).__init__(**kw)

    def pose_fast(self, frame_id):
        """Latest telemetry for the cameras without waiting: get_telemetry takes ~30 ms on the drone, and the
        perception loop needs it for every frame. A background thread refreshes it; the result is at most ~0.1 s old."""
        if frame_id not in self._pose_threads:
            def loop():
                while not self.rospy.is_shutdown():
                    try:
                        self._pose[frame_id] = (self.telemetry(frame_id), time.time())
                    except Exception:
                        time.sleep(0.2)
                    time.sleep(0.03)
            th = threading.Thread(target=loop, daemon=True)
            self._pose_threads[frame_id] = th
            th.start()
        hit = self._pose.get(frame_id)
        if hit and time.time() - hit[1] < 1.0:
            return hit[0]
        # No fresh answer: the frame is not available yet (before the markers are first seen get_telemetry blocks
        # for ~2 s per call). NEVER wait for it here - the perception loop would drop to one frame every 4 s.
        # "Position unknown" simply means this frame's detections are not placed on the map.
        return Telemetry(x=NAN, y=NAN, z=NAN, yaw=NAN, frame_id=frame_id)

    def go(self, x=0, y=0, z=0, yaw=NAN, speed=0.5, frame_id="aruco_map", auto_arm=False):
        with self._lock:
            return self._navigate(x=x, y=y, z=z, yaw=yaw, speed=speed, frame_id=frame_id, auto_arm=auto_arm)

    def telemetry(self, frame_id=""):
        with self._lock:
            t = self._get_telemetry(frame_id=frame_id)
        return self._fix_cell_voltage(t)

    def _fix_cell_voltage(self, t):
        """On the TECHNIC 6S (9 Nov 2026) get_telemetry gave cell_voltage == voltage (23.1 V) because the PX4 cell
        count is not set. A per-cell value > 4.6 V is impossible -> recompute it, else the low-battery
        landing would never trigger."""
        v, cv = t.voltage, t.cell_voltage
        if v > 0 and (math.isnan(cv) or cv > 4.6):
            n = self.battery_cells or max(1, int(math.ceil(v / 4.35)))
            if not self._cells_warned:
                self._cells_warned = True
                self.log("[battery] FC reports %.2f V per cell -> using %d cells%s: %.2f V/cell" % (
                    cv, n, "" if self.battery_cells else " (estimated - set safety.battery_cells)", v / n))
            t.cell_voltage = v / n
        return t

    def _land(self):
        with self._lock:
            return self._land_srv()

    MANUAL_MODES = ("MANUAL", "STABILIZED", "ACRO", "ALTCTL", "POSCTL", "RATTITUDE")

    def _land_fallback(self):
        """The TECHNIC land service only works in OFFBOARD. If the flight controller left OFFBOARD by itself
        (failsafe, lost position), switch it to AUTO.LAND directly. If the PILOT switched to a manual mode,
        leave the drone to the pilot."""
        mode = str(getattr(self.telemetry(), "mode", "") or "")
        if mode in self.MANUAL_MODES:
            self.log("[drone] flight mode is %s: the pilot has control - NOT interfering. Land with the RC." % mode)
            return
        if mode.startswith("AUTO.LAND") or mode.startswith("AUTO.RTL"):
            self.log("[drone] flight controller is already in %s" % mode)
            return
        try:
            import rospy
            from mavros_msgs.srv import SetMode
            r = rospy.ServiceProxy("/mavros/set_mode", SetMode)(base_mode=0, custom_mode="AUTO.LAND")
            self.log("[drone] flight mode was %s -> AUTO.LAND requested directly (%s)" % (mode or "?", "accepted" if r.mode_sent else "REFUSED - LAND WITH THE RC"))
        except Exception as e:
            self.log("[drone] could not request AUTO.LAND (%s) - LAND WITH THE RC TRANSMITTER" % e)

    def sleep(self, s):
        self.rospy.sleep(s)

    def now(self):
        return self.rospy.get_time()

    def led(self, r=0, g=0, b=0, effect="fill"):
        if self._led:
            try:
                self._led(effect=effect, r=r, g=g, b=b)
            except Exception:
                pass


# ============================================================================ MOCK (laptop)
class MockDrone(DroneBase):
    """
    Simulates a drone moving towards targets at `speed` (time can be accelerated with time_scale).
    Positions are in one world frame ("aruco_map"); "body" moves are relative to the current pose.
    Simulated time only advances in sleep() (virtual clock), so a slow / busy computer changes how long a
    test takes, but not what the drone does - mock runs are repeatable.
    """

    def __init__(self, time_scale=10.0, start=(0.0, 0.0, 0.0), voltage_drop_per_min=0.05, **kw):
        self.time_scale = time_scale
        self.pos = list(start)
        self.yaw = 0.0
        self.target = list(start)
        self.target_yaw = 0.0
        self.speed = 0.5
        self.armed = False
        self.mode = "POSCTL"
        self.cell_v = 4.15
        self.v_drop = voltage_drop_per_min
        self.sim_time = 0.0
        self._sim_lock = threading.Lock()
        super(MockDrone, self).__init__(**kw)

    def _step(self, dt=0.0):
        if dt <= 0:
            return
        with self._sim_lock:
            self._advance(dt)

    def _advance(self, dt):
        self.sim_time += dt
        if not self.armed:
            return
        d = [self.target[i] - self.pos[i] for i in range(3)]
        dist = math.sqrt(sum(v * v for v in d))
        step = self.speed * dt
        if dist <= step or dist < 1e-9:
            self.pos = list(self.target)
        else:
            self.pos = [self.pos[i] + d[i] / dist * step for i in range(3)]
        if not math.isnan(self.target_yaw):
            self.yaw = self.target_yaw
        self.cell_v -= self.v_drop * dt / 60.0
        if self.mode == "AUTO.LAND" and self.pos[2] <= 0.01:
            self.armed = False

    def go(self, x=0, y=0, z=0, yaw=NAN, speed=0.5, frame_id="aruco_map", auto_arm=False):
        if auto_arm:
            self.armed, self.mode = True, "OFFBOARD"
        self.speed = max(0.05, speed or 0.5)
        if frame_id == "body":
            c, s = math.cos(self.yaw), math.sin(self.yaw)
            self.target = [self.pos[0] + c * x - s * y, self.pos[1] + s * x + c * y, self.pos[2] + z]
            self.target_yaw = self.yaw + yaw if not math.isnan(yaw) else NAN
        elif frame_id == "navigate_target":
            self.target = [self.target[0] + x, self.target[1] + y, self.target[2] + z]
            self.target_yaw = yaw
        else:
            self.target = [x, y, z]
            self.target_yaw = yaw

    def telemetry(self, frame_id=""):
        if frame_id == "navigate_target":
            return Telemetry(x=self.pos[0] - self.target[0], y=self.pos[1] - self.target[1],
                             z=self.pos[2] - self.target[2], armed=self.armed, mode=self.mode)
        return Telemetry(x=self.pos[0], y=self.pos[1], z=self.pos[2], yaw=self.yaw, armed=self.armed,
                         mode=self.mode, cell_voltage=self.cell_v, voltage=self.cell_v * 4, frame_id=frame_id)

    def _land(self):
        self.mode = "AUTO.LAND"
        self.target = [self.pos[0], self.pos[1], 0.0]
        self.speed = 0.5

    def sleep(self, s):
        time.sleep(s / self.time_scale)
        self._step(s)

    def now(self):
        return self.sim_time

    def led(self, r=0, g=0, b=0, effect="fill"):
        self.log("[mock-led] %s (%d,%d,%d)" % (effect, r, g, b))


def make_drone(mock=False, **kw):
    return MockDrone(**kw) if mock else TechnicDrone(**kw)
