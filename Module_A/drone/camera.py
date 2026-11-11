"""
Camera sources. All return frames with the drone pose at capture time, and can convert a pixel
to map coordinates.

  RosCamera(topic='main_camera/image_raw_throttled')     TECHNIC main camera (exact TF projection)
  CvCamera(device=1)                                       any USB camera, e.g. a thermal camera
  MockCamera(drone, scene)                                 renders a fake top-down scene (laptop tests)

frame = cam.get()  ->  dict(img=..., stamp=..., pose=(x, y, z, yaw)) or None
cam.pixel_to_map(u, v, frame) -> (x, y, z) in aruco_map, or None

Python 3.8 compatible.
"""
import math
import os
import sys
import threading
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common.geometry import nadir_pixel_to_ground, pixel_ray, quat_to_R, ray_to_ground  # noqa: E402
from common.thermal import colorize, decode_p2  # noqa: E402

DEFAULT_K = np.array([[332.0, 0, 320.0], [0, 332.0, 240.0], [0, 0, 1]])   # ~88 deg HFOV @ 640x480


class CameraBase(object):
    K = DEFAULT_K
    D = None
    map_frame = "aruco_map"

    def __init__(self, drone=None, ground_z=0.0, image_up_is_forward=True, orientation="down", target_distance=1.0):
        self.drone = drone
        self.ground_z = ground_z
        self.image_up_is_forward = image_up_is_forward
        self.orientation = orientation          # "down" (TECHNIC main camera) or "forward" (inspection camera)
        self.target_distance = target_distance  # forward camera: distance to the inspected structure (m)

    def _pose(self):
        if self.drone is None:
            return None
        fast = getattr(self.drone, "pose_fast", None)
        t = fast(self.map_frame) if fast else self.drone.telemetry(self.map_frame)
        return (t.x, t.y, t.z, t.yaw)

    def pixel_to_ray(self, u, v, frame):
        """World ray (origin xyz, unit direction) through pixel (u, v)."""
        pose = frame.get("pose")
        if pose is None or any(math.isnan(p) for p in pose):
            return None
        x, y, z, yaw = pose
        r = pixel_ray(u, v, self.K, self.D)
        if self.orientation == "forward":
            fwd, left, up = 1.0, -r[0], -r[1]
        else:   # down: image up = forward
            if self.image_up_is_forward:
                fwd, left, up = -r[1], -r[0], -1.0
            else:
                fwd, left, up = r[1], r[0], -1.0
        c, s = math.cos(yaw), math.sin(yaw)
        d = np.array([c * fwd - s * left, s * fwd + c * left, up])
        return np.array([x, y, z]), d / np.linalg.norm(d)

    correction = None      # (M, scale) found by common/selfcal.py: true mounting rotation and lens scale

    def floor_direction(self, u, v):
        """Direction of pixel (u, v) on the floor per metre of height, under the CONFIGURED mounting: (fwd0, left0)."""
        r = pixel_ray(u, v, self.K, self.D)
        return (-r[1], -r[0]) if self.image_up_is_forward else (r[1], r[0])

    def pixel_to_map(self, u, v, frame):
        pose = frame.get("pose")
        if pose is None or any(math.isnan(p) for p in pose):
            return None
        if self.orientation == "forward":
            return forward_pixel_to_world(u, v, self.K, pose, self.target_distance, self.D)
        if self.correction is not None:
            from common.selfcal import project
            f0, l0 = self.floor_direction(u, v)
            x, y = project((pose[0], pose[1], pose[3], pose[2] - self.ground_z, f0, l0), self.correction[0], self.correction[1])
            return (x, y, self.ground_z)
        x, y = nadir_pixel_to_ground(u, v, self.K, pose[0], pose[1], pose[2], pose[3],
                                     ground_z=self.ground_z, D=self.D,
                                     cam_forward_is_image_up=self.image_up_is_forward)
        return (x, y, self.ground_z)


def forward_pixel_to_world(u, v, K, pose, distance, D=None):
    """Forward-looking camera: point at horizontal `distance` along the pixel's ray. Returns (x, y, z)."""
    r = pixel_ray(u, v, K, D)                 # optical: x right, y down, z forward
    fwd, left, up = 1.0, -r[0], -r[1]
    x, y, z, yaw = pose
    c, s = math.cos(yaw), math.sin(yaw)
    k = distance / math.sqrt(fwd * fwd + left * left)
    return (x + k * (c * fwd - s * left), y + k * (s * fwd + c * left), z + k * up)


def imgmsg_to_bgr(msg):
    """sensor_msgs/Image -> BGR numpy image, without cv_bridge (cv_bridge does not import on the TECHNIC image:
    it was built against an older numpy than the one installed)."""
    enc = msg.encoding.lower()
    ch = {"bgr8": 3, "rgb8": 3, "mono8": 1, "8uc1": 1, "bgra8": 4, "rgba8": 4, "8uc3": 3}.get(enc)
    if ch is None:
        raise ValueError("unsupported image encoding %r" % msg.encoding)
    a = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)[:, :msg.width * ch]
    a = a.reshape(msg.height, msg.width, ch) if ch > 1 else a.reshape(msg.height, msg.width)
    if enc == "rgb8":
        return cv2.cvtColor(a, cv2.COLOR_RGB2BGR)
    if enc == "rgba8":
        return cv2.cvtColor(a, cv2.COLOR_RGBA2BGR)
    if enc == "bgra8":
        return cv2.cvtColor(a, cv2.COLOR_BGRA2BGR)
    if ch == 1:
        return cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)
    return a.copy()


class RosCamera(CameraBase):
    """Subscribes to a ROS image topic and keeps the latest frame. Uses TF for exact projection."""

    def __init__(self, drone, topic="main_camera/image_raw_throttled", info_topic="main_camera/camera_info",
                 optical_frame="main_camera_optical", use_tf=True, **kw):
        super(RosCamera, self).__init__(drone, **kw)
        import rospy
        import tf2_ros
        from sensor_msgs.msg import CameraInfo, Image
        self.rospy = rospy
        self.optical_frame = optical_frame
        self.use_tf = use_tf
        self._lock = threading.Lock()
        self._frame = None
        self._last = None
        try:
            info = rospy.wait_for_message(info_topic, CameraInfo, timeout=5)
            self.K = np.array(info.K).reshape(3, 3)
            self.D = np.array(info.D) if len(info.D) else None
        except Exception:
            rospy.logwarn("camera_info not received - using default K")
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer)
        rospy.Subscriber(topic, Image, self._cb, queue_size=1, buff_size=2 ** 24)

    def _cb(self, msg):
        img = imgmsg_to_bgr(msg)
        with self._lock:
            self._frame = {"img": img, "stamp": msg.header.stamp, "pose": None, "t": time.time()}
            self._last = self._frame

    def peek(self):
        """Newest frame for the live view. Does not consume it: detection still gets every frame once."""
        with self._lock:
            return self._last

    def get(self):
        with self._lock:
            f = self._frame
            self._frame = None          # each frame is processed once
        if f is None:
            return None
        f["pose"] = self._pose()
        return f

    def pixel_to_ray(self, u, v, frame):
        if self.use_tf:
            try:
                tr = self.tf_buffer.lookup_transform(self.map_frame, self.optical_frame, frame["stamp"],
                                                     self.rospy.Duration(0.2))
                q, p = tr.transform.rotation, tr.transform.translation
                d = quat_to_R(q.x, q.y, q.z, q.w).dot(pixel_ray(u, v, self.K, self.D))
                return np.array([p.x, p.y, p.z]), d / np.linalg.norm(d)
            except Exception:
                pass
        return CameraBase.pixel_to_ray(self, u, v, frame)

    def pixel_to_map(self, u, v, frame):
        if self.use_tf:
            try:
                tr = self.tf_buffer.lookup_transform(self.map_frame, self.optical_frame, frame["stamp"],
                                                     self.rospy.Duration(0.2))
                q, p = tr.transform.rotation, tr.transform.translation
                R = quat_to_R(q.x, q.y, q.z, q.w)
                pt = ray_to_ground(np.array([p.x, p.y, p.z]), R, pixel_ray(u, v, self.K, self.D), self.ground_z)
                if pt is not None:
                    return (float(pt[0]), float(pt[1]), float(pt[2]))
            except Exception:
                pass
        return super(RosCamera, self).pixel_to_map(u, v, frame)


class RosThermalCamera(CameraBase):
    """
    Thermal camera through tools/thermal_node.py, which owns the USB device and publishes real temperatures.
    Subscribes to the deg C map (32FC1); frame['temp'] = deg C, frame['img'] = false-colour picture.
    """

    def __init__(self, drone, topic="thermal/temp", hfov_deg=56.0, K=None, timeout=8.0, **kw):
        super(RosThermalCamera, self).__init__(drone, **kw)
        import rospy
        from sensor_msgs.msg import Image
        self._lock = threading.Lock()
        self._frame = None
        self._last = None
        rospy.Subscriber(topic, Image, self._cb, queue_size=1, buff_size=2 ** 22)
        t_end = time.time() + timeout
        while self._last is None and time.time() < t_end and not rospy.is_shutdown():
            time.sleep(0.05)
        if self._last is None:
            raise RuntimeError("no thermal data on topic '%s' - is the thermal camera plugged in and the thermal node "
                               "running?  (sudo systemctl status brics-thermal)" % topic)
        h, w = self._last["temp"].shape
        if K is not None:
            self.K = np.array(K).reshape(3, 3)
        else:
            fx = (w / 2.0) / math.tan(math.radians(hfov_deg or 56.0) / 2)
            self.K = np.array([[fx, 0, w / 2.0], [0, fx, h / 2.0], [0, 0, 1]])
        print("[camera] thermal camera via ROS topic %s: RAW temperature mode (deg C), %dx%d" % (topic, w, h))

    def _cb(self, msg):
        temp = np.frombuffer(msg.data, dtype=np.float32).reshape(msg.height, msg.width).copy()
        f = {"img": colorize(temp), "temp": temp, "stamp": msg.header.stamp, "pose": None, "t": time.time()}
        with self._lock:
            self._frame = f
            self._last = f

    def peek(self):
        with self._lock:
            return self._last

    def get(self):
        with self._lock:
            f, self._frame = self._frame, None
        if f is None:
            return None
        f["pose"] = self._pose()
        return f


class CvCamera(CameraBase):
    """
    Any OpenCV camera (USB thermal camera, webcam, video file). Grabs in a background thread.
    thermal:  none  - normal camera
              auto  - try the raw P2/TC001 temperature format, fall back to a plain image   (recommended)
              p2    - require the raw format (frame['temp'] = deg C)
              plain - thermal camera that only gives a picture (brightness = heat)
    """

    def __init__(self, drone=None, device=0, width=None, height=None, K=None, hfov_deg=None, thermal="none", **kw):
        super(CvCamera, self).__init__(drone, **kw)
        self.thermal = thermal
        self.raw = False
        backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
        if thermal in ("auto", "p2"):
            self.cap = cv2.VideoCapture(device, backend)
            self.cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
            ok, raw = self.cap.read()
            img, temp = decode_p2(raw) if ok else (None, None)
            if img is not None:
                self.raw = True
                print("[camera] thermal camera %s: RAW temperature mode (deg C)" % device)
            else:
                self.cap.release()
                if thermal == "p2":
                    raise RuntimeError("camera %s does not give the raw P2/TC001 temperature format" % device)
                print("[camera] thermal camera %s: raw format not found -> brightness mode" % device)
        if not self.raw:
            self.cap = cv2.VideoCapture(device, backend) if thermal != "none" else cv2.VideoCapture(device)
            if width:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            if height:
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._frame, self._lock, self._run = None, threading.Lock(), True
        self._last = None
        f = self._read()
        if f is None:
            raise RuntimeError("cannot open camera %s" % device)
        h, w = f["img"].shape[:2]
        if K is not None:
            self.K = np.array(K).reshape(3, 3)
        else:
            fx = (w / 2.0) / math.tan(math.radians(hfov_deg or 56.0) / 2)
            self.K = np.array([[fx, 0, w / 2.0], [0, fx, h / 2.0], [0, 0, 1]])
        threading.Thread(target=self._loop, daemon=True).start()

    def _read(self):
        ok, img = self.cap.read()
        if not ok:
            return None
        if self.raw:
            vis, temp = decode_p2(img)
            if vis is None:
                return None
            return {"img": vis, "temp": temp, "stamp": None, "t": time.time()}
        return {"img": img, "stamp": None, "t": time.time()}

    def _loop(self):
        while self._run:
            f = self._read()
            if f is not None:
                with self._lock:
                    self._frame = f
                    self._last = f
            else:
                time.sleep(0.05)

    def peek(self):
        """Newest frame for the live view. Does not consume it: detection still gets every frame once."""
        with self._lock:
            return self._last

    def get(self):
        with self._lock:
            f, self._frame = self._frame, None
        if f is None:
            return None
        f["pose"] = self._pose()
        return f


class MockCamera(CameraBase):
    """
    Renders what a downward camera would see above a flat floor with objects on it.
    scene: list of dicts {name, x, y, r (radius m), color [B,G,R]} in aruco_map metres.
    Use it to test detection + coordinate projection end-to-end without hardware.
    """

    def __init__(self, drone, scene, width=640, height=480, background=None, noise=6, thermal="none", hfov_deg=None,
                 focal_error=1.0, flipped=False, pose_noise=0.0, **kw):
        """focal_error / flipped rehearse a badly calibrated real camera: the picture is rendered with the TRUE
        lens and mounting, but positions are computed with the ASSUMED ones (focal length x focal_error, picture
        turned 180 deg), exactly like a wrong field-of-view value or an upside-down camera on the drone."""
        super(MockCamera, self).__init__(drone, **kw)
        self.thermal = thermal not in (None, "none")
        if self.thermal and width == 640:
            width, height = 256, 192
        self.scene, self.w, self.h, self.noise = scene, width, height, noise
        fx = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2) if hfov_deg else 332.0 * width / 640.0
        self.K_true = np.array([[fx, 0, width / 2.0], [0, fx, height / 2.0], [0, 0, 1]])
        self.up_true = self.image_up_is_forward
        fa = fx * float(focal_error)                                       # what the mission believes
        self.K = np.array([[fa, 0, width / 2.0], [0, fa, height / 2.0], [0, 0, 1]])
        if flipped:
            self.image_up_is_forward = not self.image_up_is_forward
        self.pose_noise = float(pose_noise)      # metres (1 sigma) of position jitter; heading jitter = 0.6 rad per metre
        self._rng = np.random.RandomState(7)
        self.bg = background
        self._last = 0

    def render(self, pose):
        if self.orientation == "forward":
            return self.render_forward(pose)
        x, y, z, yaw = pose
        img = np.full((self.h, self.w, 3), (95, 105, 100), np.uint8)
        if self.bg is not None:
            img = cv2.resize(self.bg, (self.w, self.h))
        hgt = max(0.05, z - self.ground_z)
        f = self.K_true[0, 0]
        c, s = math.cos(yaw), math.sin(yaw)
        for o in self.scene:
            if o.get("rgb_visible", True) is False:
                continue
            dx, dy = o["x"] - x, o["y"] - y
            fwd = c * dx + s * dy             # world -> body
            left = -s * dx + c * dy
            if self.up_true:
                u = self.K_true[0, 2] + (-left) / hgt * f
                v = self.K_true[1, 2] + (-fwd) / hgt * f
            else:
                u = self.K_true[0, 2] + left / hgt * f
                v = self.K_true[1, 2] + fwd / hgt * f
            r = max(1, int(o.get("r", 0.1) / hgt * f))
            if -r < u < self.w + r and -r < v < self.h + r:
                cv2.circle(img, (int(u), int(v)), r, tuple(int(k) for k in o.get("color", (0, 0, 255))), -1)
        if self.noise:
            img = cv2.add(img, np.random.randint(0, self.noise, img.shape, dtype=np.uint8))
        return img

    def render_temp(self, pose):
        """Temperature map (deg C) of the floor: ambient 22 C + objects that have a 'temp' field."""
        x, y, z, yaw = pose
        t = np.full((self.h, self.w), 22.0, np.float32) + np.random.randn(self.h, self.w).astype(np.float32) * 0.3
        if self.orientation == "forward":
            f = self.K_true[0, 0]
            c, s = math.cos(yaw), math.sin(yaw)
            for o in self.scene:
                if "temp" not in o:
                    continue
                dx, dy, dz = o["x"] - x, o["y"] - y, o.get("z", 1.0) - z
                fwd, left = c * dx + s * dy, -s * dx + c * dy
                if fwd <= 0.1:
                    continue
                u, v = self.K_true[0, 2] + (-left) / fwd * f, self.K_true[1, 2] + (-dz) / fwd * f
                r = max(1, int(o.get("r", 0.1) / fwd * f))
                if -r < u < self.w + r and -r < v < self.h + r:
                    cv2.circle(t, (int(u), int(v)), r, float(o["temp"]), -1)
            return cv2.GaussianBlur(t, (5, 5), 0)
        hgt = max(0.05, z - self.ground_z)
        f = self.K_true[0, 0]
        c, s = math.cos(yaw), math.sin(yaw)
        for o in self.scene:
            if "temp" not in o:
                continue
            dx, dy = o["x"] - x, o["y"] - y
            fwd, left = c * dx + s * dy, -s * dx + c * dy
            k = 1.0 if self.up_true else -1.0       # same convention as render() / pixel_to_map()
            u = self.K_true[0, 2] + k * (-left) / hgt * f
            v = self.K_true[1, 2] + k * (-fwd) / hgt * f
            r = max(1, int(o.get("r", 0.1) / hgt * f))
            if -r < u < self.w + r and -r < v < self.h + r:
                cv2.circle(t, (int(u), int(v)), r, float(o["temp"]), -1)
        return cv2.GaussianBlur(t, (5, 5), 0)

    def get(self):
        if self.drone is None:
            return None
        pose = self._pose()
        seen = pose                               # what the mission is told (the picture uses the true pose)
        if self.pose_noise:
            n = self._rng.randn(4) * self.pose_noise
            seen = (pose[0] + n[0], pose[1] + n[1], pose[2] + 0.5 * n[2], pose[3] + 0.6 * n[3])
        if self.thermal:
            temp = self.render_temp(pose)
            return {"img": colorize(temp), "temp": temp, "stamp": None, "pose": seen, "t": time.time()}
        return {"img": self.render(pose), "stamp": None, "pose": seen, "t": time.time()}

    def render_forward(self, pose):
        """Forward camera view: objects have x, y, z (centre height) and r."""
        x, y, z, yaw = pose
        img = np.full((self.h, self.w, 3), (170, 150, 120), np.uint8)
        f = self.K[0, 0]
        c, s = math.cos(yaw), math.sin(yaw)
        for o in self.scene:
            dx, dy, dz = o["x"] - x, o["y"] - y, o.get("z", 1.0) - z
            fwd = c * dx + s * dy
            left = -s * dx + c * dy
            if fwd <= 0.1:
                continue
            u = self.K[0, 2] + (-left) / fwd * f
            v = self.K[1, 2] + (-dz) / fwd * f
            r = max(1, int(o.get("r", 0.1) / fwd * f))
            if -r < u < self.w + r and -r < v < self.h + r:
                cv2.circle(img, (int(u), int(v)), r, tuple(int(k) for k in o.get("color", (0, 0, 255))), -1)
        if self.noise:
            img = cv2.add(img, np.random.randint(0, self.noise, img.shape, dtype=np.uint8))
        return img
