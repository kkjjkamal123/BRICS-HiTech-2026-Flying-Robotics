"""
Universal detector used everywhere (laptop + Orange Pi + simulator).

One interface, many backends:
  - "yolo"     : any trained model (.pt via ultralytics, .onnx via onnxruntime / cv2.dnn,
                 *_rknn_model folder or .rknn via ultralytics/rknnlite, *_ncnn_model via ultralytics)
  - "hsv"      : colour threshold (flame / red / orange / any colour)   -> needs NO training
  - "thermal"  : hot-spot threshold on a thermal image                  -> needs NO training
  - "exg"      : vegetation (Excess-Green index) segmentation            -> needs NO training
  - "aruco"    : ArUco marker detection (IDs as classes)

Every detector returns a list of dicts:
  {"name": str, "cls": int, "conf": float, "box": [x1,y1,x2,y2], "center": [u,v], "area": float,
   "source": "<detector name>"}

Python 3.8 compatible (ROS Noetic on the Orange Pi). Only numpy + cv2 are required.
"""
import ast
import glob
import math
import os

import cv2
import numpy as np


# ----------------------------------------------------------------------------- helpers
def _det(name, cls, conf, x1, y1, x2, y2, source):
    x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
    return {
        "name": str(name), "cls": int(cls), "conf": float(conf),
        "box": [x1, y1, x2, y2],
        "center": [(x1 + x2) / 2.0, (y1 + y2) / 2.0],
        "area": max(0.0, x2 - x1) * max(0.0, y2 - y1),
        "source": source,
    }


def letterbox(img, size):
    """Resize keeping aspect ratio and pad to size x size (same as ultralytics). Returns img, scale, (padx, pady)."""
    h, w = img.shape[:2]
    s = min(size / float(h), size / float(w))
    nh, nw = int(round(h * s)), int(round(w * s))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    out = np.full((size, size, 3), 114, dtype=np.uint8)
    px, py = (size - nw) // 2, (size - nh) // 2
    out[py:py + nh, px:px + nw] = resized
    return out, s, (px, py)


def draw(img, dets, color=(0, 255, 0)):
    """Draw detections on a copy of img."""
    out = img.copy()
    for d in dets:
        x1, y1, x2, y2 = [int(v) for v in d["box"]]
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        label = "%s %.2f" % (d["name"], d["conf"])
        cv2.putText(out, label, (x1, max(12, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return out


def nms(dets, iou=0.5):
    """Class-wise NMS for merged results (e.g. after tiling)."""
    if not dets:
        return dets
    keep = []
    by_cls = {}
    for d in dets:
        by_cls.setdefault(d["name"], []).append(d)
    for _, group in by_cls.items():
        boxes = [[d["box"][0], d["box"][1], d["box"][2] - d["box"][0], d["box"][3] - d["box"][1]] for d in group]
        scores = [d["conf"] for d in group]
        idx = cv2.dnn.NMSBoxes(boxes, scores, 0.0, iou)
        for i in np.array(idx).flatten().tolist():
            keep.append(group[i])
    return keep


# ----------------------------------------------------------------------------- YOLO
class YoloDetector(object):
    """
    Loads any exported YOLO (v8 / 11) model. Picks the best available runtime automatically.
      model: path to .pt / .onnx / .rknn / *_rknn_model / *_ncnn_model
    """

    def __init__(self, model, conf=0.35, iou=0.5, imgsz=None, classes=None, names=None,
                 runtime="auto", name="yolo", task=None):
        self.model_path = model
        self.conf, self.iou = conf, iou
        self.classes = set(classes) if classes else None     # keep only these class names
        self.source = name
        self.imgsz = imgsz
        self.task = task
        self.names = names
        self.backend = None
        if not os.path.exists(model):
            raise FileNotFoundError("Model not found: %s" % model)
        self.meta_dir = None
        if os.path.isdir(model) and runtime in ("auto", "rknnlite"):
            rk = sorted(glob.glob(os.path.join(model, "*.rknn")))
            if rk:                                  # ultralytics export folder: best_rknn_model/
                self.meta_dir = model
                self.model_path = model = rk[0]
        if runtime == "auto":
            runtime = self._pick_runtime(model)
        self.runtime = runtime
        getattr(self, "_load_" + runtime)()

    # ---- runtime selection
    @staticmethod
    def _pick_runtime(model):
        m = model.rstrip("/")
        if m.endswith(".onnx"):
            try:
                import onnxruntime  # noqa: F401
                return "onnxruntime"
            except ImportError:
                return "cvdnn"
        if m.endswith(".rknn"):
            return "rknnlite"
        return "ultralytics"     # .pt, *_rknn_model, *_ncnn_model, openvino ...

    def _load_ultralytics(self):
        from ultralytics import YOLO
        self.backend = YOLO(self.model_path, task=self.task)
        self.names = self.names or self.backend.names
        self.task = self.task or getattr(self.backend, "task", "detect")

    def _load_onnxruntime(self):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
        inp = self.sess.get_inputs()[0]
        self.input_name = inp.name
        shp = inp.shape
        self.imgsz = self.imgsz or (shp[2] if isinstance(shp[2], int) else 640)
        meta = self.sess.get_modelmeta().custom_metadata_map
        self._read_meta(meta)

    def _load_cvdnn(self):
        self.net = cv2.dnn.readNetFromONNX(self.model_path)
        self.imgsz = self.imgsz or 640
        self._read_meta({})

    def _load_rknnlite(self):
        from rknnlite.api import RKNNLite
        self.rk = RKNNLite()
        if self.rk.load_rknn(self.model_path) != 0:
            raise RuntimeError("load_rknn failed")
        try:
            ret = self.rk.init_runtime(core_mask=RKNNLite.NPU_CORE_0_1_2)   # all 3 NPU cores (RK3588)
        except Exception:
            ret = -1
        if ret != 0 and self.rk.init_runtime() != 0:
            raise RuntimeError("init_runtime failed")
        meta = {}
        mdir = self.meta_dir or os.path.dirname(self.model_path)
        mfile = os.path.join(mdir, "metadata.yaml")
        if os.path.exists(mfile):                  # names / imgsz / task written by the ultralytics export
            import yaml
            m = yaml.safe_load(open(mfile)) or {}
            meta = {k: repr(v) if k != "task" else v for k, v in m.items() if k in ("names", "imgsz", "task")}
        self.tail = None
        tail = os.path.join(mdir, "tail.onnx")      # INT8 exports: head decoded on CPU
        if os.path.exists(tail):
            import onnxruntime as ort
            self.tail = ort.InferenceSession(tail, providers=["CPUExecutionProvider"])
        self._read_meta(meta)
        self.imgsz = self.imgsz or 640

    def _read_meta(self, meta):
        if self.names is None and "names" in meta:
            self.names = ast.literal_eval(meta["names"])
        if self.task is None and "task" in meta:
            self.task = meta["task"]
        if "imgsz" in meta and not self.imgsz:
            self.imgsz = ast.literal_eval(meta["imgsz"])[0]
        if self.names is None:
            # look for names.txt next to the model (written by train.py)
            p = os.path.join(os.path.dirname(self.model_path), "names.txt")
            if os.path.exists(p):
                self.names = {i: l.strip() for i, l in enumerate(open(p)) if l.strip()}
        if self.names is None:
            self.names = {}
        if isinstance(self.names, list):
            self.names = dict(enumerate(self.names))
        self.task = self.task or "detect"

    # ---- inference
    def __call__(self, img):
        if self.runtime == "ultralytics":
            return self._run_ultralytics(img)
        if self.runtime == "rknnlite":           # NPU takes uint8 RGB directly: skip the float conversion
            lb, s, pad = letterbox(img, self.imgsz)
            ys = self.rk.inference(inputs=[np.ascontiguousarray(lb[:, :, ::-1])[None]])
            if self.tail is not None:
                feeds = {t.name: v.astype(np.float32) for t, v in zip(self.tail.get_inputs(), ys)}
                ys = self.tail.run(None, feeds)
            if self.task == "classify":
                return self._postprocess_cls(ys[0], img.shape)
            return self._postprocess_det(ys[0], s, pad, img.shape)
        blob, s, pad = self._preprocess(img)
        if self.runtime == "onnxruntime":
            out = self.sess.run(None, {self.input_name: blob})[0]
        elif self.runtime == "cvdnn":
            self.net.setInput(blob)
            out = self.net.forward()
        else:  # rknnlite: NHWC uint8 input
            nhwc = (blob[0].transpose(1, 2, 0) * 255).astype(np.uint8)[None]
            ys = self.rk.inference(inputs=[nhwc])
            if self.tail is not None:
                feeds = {t.name: v.astype(np.float32) for t, v in zip(self.tail.get_inputs(), ys)}
                ys = self.tail.run(None, feeds)
            out = ys[0]
        if self.task == "classify":
            return self._postprocess_cls(out, img.shape)
        return self._postprocess_det(out, s, pad, img.shape)

    def _preprocess(self, img):
        lb, s, pad = letterbox(img, self.imgsz)
        blob = lb[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        return np.ascontiguousarray(blob), s, pad

    def _keep(self, name):
        return self.classes is None or name in self.classes

    def _postprocess_det(self, out, s, pad, shape):
        out = np.asarray(out)
        if out.ndim == 3:
            out = out[0]
        if out.shape[-1] == 6 and out.shape[0] != 6:
            return self._postprocess_end2end(out, s, pad, shape)   # YOLO26 / NMS-free: (300, 6)
        if out.shape[0] < out.shape[1]:          # YOLOv8/11: (4+nc, N) -> (N, 4+nc)
            out = out.T
        boxes, scores = out[:, :4], out[:, 4:]
        if scores.shape[1] == 0:
            return []
        cls = scores.argmax(1)
        conf = scores[np.arange(len(cls)), cls]
        m = conf >= self.conf
        boxes, cls, conf = boxes[m], cls[m], conf[m]
        if len(conf) == 0:
            return []
        cx, cy, w, h = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        x1 = (cx - w / 2 - pad[0]) / s
        y1 = (cy - h / 2 - pad[1]) / s
        x2 = (cx + w / 2 - pad[0]) / s
        y2 = (cy + h / 2 - pad[1]) / s
        H, W = shape[:2]
        x1, x2 = np.clip(x1, 0, W), np.clip(x2, 0, W)
        y1, y2 = np.clip(y1, 0, H), np.clip(y2, 0, H)
        res = []
        # class-aware NMS (offset trick)
        rects = np.stack([x1 + cls * 4096, y1, x2 - x1, y2 - y1], 1).tolist()
        idx = cv2.dnn.NMSBoxes(rects, conf.tolist(), self.conf, self.iou)
        for i in np.array(idx).flatten().tolist():
            name = self.names.get(int(cls[i]), str(int(cls[i])))
            if self._keep(name):
                res.append(_det(name, cls[i], conf[i], x1[i], y1[i], x2[i], y2[i], self.source))
        return res

    def _postprocess_end2end(self, out, s, pad, shape):
        """YOLO26 end-to-end head: rows of [x1, y1, x2, y2, score, class] in letterboxed pixels, NMS already done."""
        H, W = shape[:2]
        res = []
        for x1, y1, x2, y2, conf, k in out:
            if conf < self.conf:
                continue
            name = self.names.get(int(k), str(int(k)))
            if not self._keep(name):
                continue
            bx1 = np.clip((x1 - pad[0]) / s, 0, W)
            by1 = np.clip((y1 - pad[1]) / s, 0, H)
            bx2 = np.clip((x2 - pad[0]) / s, 0, W)
            by2 = np.clip((y2 - pad[1]) / s, 0, H)
            res.append(_det(name, k, conf, bx1, by1, bx2, by2, self.source))
        return res

    def _postprocess_cls(self, out, shape):
        p = np.asarray(out).reshape(-1)
        if p.min() < 0 or abs(p.sum() - 1) > 0.05:     # logits -> softmax
            e = np.exp(p - p.max())
            p = e / e.sum()
        i = int(p.argmax())
        name = self.names.get(i, str(i))
        if p[i] < self.conf or not self._keep(name):
            return []
        H, W = shape[:2]
        return [_det(name, i, p[i], 0, 0, W, H, self.source)]

    def _run_ultralytics(self, img):
        r = self.backend.predict(img, conf=self.conf, iou=self.iou, imgsz=self.imgsz or 640, verbose=False)[0]
        res = []
        if getattr(r, "probs", None) is not None and r.boxes is None:
            i = int(r.probs.top1)
            c = float(r.probs.top1conf)
            name = self.names[i]
            if c >= self.conf and self._keep(name):
                H, W = img.shape[:2]
                res.append(_det(name, i, c, 0, 0, W, H, self.source))
            return res
        if r.boxes is None:
            return res
        for b, c, k in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(), r.boxes.cls.cpu().numpy()):
            name = self.names[int(k)]
            if self._keep(name):
                res.append(_det(name, k, c, b[0], b[1], b[2], b[3], self.source))
        return res


# ----------------------------------------------------------------------------- classic CV (no training)
class HSVDetector(object):
    """
    Colour blobs. ranges: list of [[hmin,smin,vmin],[hmax,smax,vmax]] (OpenCV hue 0..179).
    Default = red/orange "flame" colours.
    """
    FLAME = [[[0, 120, 150], [22, 255, 255]], [[165, 120, 150], [179, 255, 255]]]

    def __init__(self, ranges=None, min_area=150, label="flame", name="hsv", max_area=None):
        self.ranges = ranges or self.FLAME
        self.min_area, self.max_area = min_area, max_area
        self.label, self.source = label, name

    def mask(self, img):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        m = np.zeros(img.shape[:2], np.uint8)
        for lo, hi in self.ranges:
            m |= cv2.inRange(hsv, tuple(lo), tuple(hi))
        k = np.ones((5, 5), np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
        return m

    def __call__(self, img):
        return _blobs(self.mask(img), self.min_area, self.max_area, self.label, self.source)


class ThermalDetector(object):
    """
    Hot spots in a thermal image (grey or false-colour).
    mode="absolute": pixel brightness >= threshold (0..255)
    mode="percentile": brighter than the given percentile AND at least `min_delta` above the median.
    """

    def __init__(self, threshold=200, mode="absolute", percentile=99.5, min_delta=40,
                 min_area=30, label="hotspot", name="thermal", threshold_c=60.0, max_c=None):
        self.threshold, self.mode, self.percentile, self.min_delta = threshold, mode, percentile, min_delta
        self.min_area, self.label, self.source = min_area, label, name
        self.threshold_c, self.max_c = threshold_c, max_c     # mode 'celsius': real temperatures (raw thermal cameras)

    def mask(self, img):
        if img.dtype.kind == "f":                 # temperature map in deg C
            m = img >= self.threshold_c
            if self.max_c is not None:
                m &= img <= self.max_c
            return m.astype(np.uint8) * 255
        g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        g = cv2.GaussianBlur(g, (5, 5), 0)
        if self.mode == "percentile":
            t = max(np.percentile(g, self.percentile), np.median(g) + self.min_delta)
        else:
            t = self.threshold
        return (g >= t).astype(np.uint8) * 255

    def __call__(self, img):
        if img.dtype.kind == "f":                 # deg C map
            dets = _blobs(self.mask(img), self.min_area, None, self.label, self.source)
            for d in dets:
                x1, y1, x2, y2 = [int(v) for v in d["box"]]
                tmax = float(img[y1:y2 + 1, x1:x2 + 1].max())
                d["max_temp_c"] = tmax
                d["conf"] = float(min(1.0, 0.5 + (tmax - self.threshold_c) / 100.0))
            return dets
        g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        dets = _blobs(self.mask(img), self.min_area, None, self.label, self.source)
        for d in dets:   # confidence = how hot relative to max
            x1, y1, x2, y2 = [int(v) for v in d["box"]]
            d["conf"] = float(g[y1:y2 + 1, x1:x2 + 1].max()) / 255.0
            d["max_value"] = float(g[y1:y2 + 1, x1:x2 + 1].max())
        return dets


class ExGDetector(object):
    """
    Vegetation detector using Excess Green index (2g - r - b) + Otsu threshold.
    Finds every green plant blob. Use it to count plants with no training,
    or to auto-label plants before training a weed-vs-crop model.
    """

    def __init__(self, min_area=60, max_area=None, label="plant", name="exg", fixed_threshold=None):
        self.min_area, self.max_area, self.label, self.source = min_area, max_area, label, name
        self.fixed = fixed_threshold

    def mask(self, img):
        f = img.astype(np.float32) + 1e-6
        s = f.sum(2)
        b, g, r = f[:, :, 0] / s, f[:, :, 1] / s, f[:, :, 2] / s
        exg = 2 * g - r - b
        exg8 = cv2.normalize(exg, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        if self.fixed is not None:
            _, m = cv2.threshold(exg8, self.fixed, 255, cv2.THRESH_BINARY)
        else:
            _, m = cv2.threshold(exg8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        k = np.ones((3, 3), np.uint8)
        return cv2.morphologyEx(m, cv2.MORPH_OPEN, k)

    def __call__(self, img):
        return _blobs(self.mask(img), self.min_area, self.max_area, self.label, self.source)


class ArucoDetector(object):
    """ArUco markers (for tests / fallback). Each marker -> class 'aruco_<id>'."""

    def __init__(self, dictionary="DICT_4X4_250", name="aruco"):
        d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))
        if hasattr(cv2.aruco, "ArucoDetector"):
            self.det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())
            self._detect = lambda g: self.det.detectMarkers(g)
        else:
            p = cv2.aruco.DetectorParameters_create()
            self._detect = lambda g: cv2.aruco.detectMarkers(g, d, parameters=p)
        self.source = name

    def __call__(self, img):
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        corners, ids, _ = self._detect(g)
        res = []
        if ids is None:
            return res
        for c, i in zip(corners, ids.flatten()):
            pts = c.reshape(-1, 2)
            x1, y1 = pts.min(0)
            x2, y2 = pts.max(0)
            res.append(_det("aruco_%d" % i, i, 1.0, x1, y1, x2, y2, self.source))
        return res


def _blobs(mask, min_area, max_area, label, source):
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2:]
    res = []
    for c in cnts:
        a = cv2.contourArea(c)
        if a < min_area or (max_area and a > max_area):
            continue
        x, y, w, h = cv2.boundingRect(c)
        conf = min(1.0, 0.5 + a / (4.0 * max(min_area, 1) * 10))
        d = _det(label, 0, conf, x, y, x + w, y + h, source)
        M = cv2.moments(c)
        if M["m00"] > 0:
            d["center"] = [M["m10"] / M["m00"], M["m01"] / M["m00"]]
        d["area"] = float(a)
        res.append(d)
    return res


# ----------------------------------------------------------------------------- tiling (small objects in big images)
def detect_tiled(detector, img, tile=640, overlap=0.2, iou=0.5):
    """Run detector on overlapping tiles + full image; merge with NMS. Great for tiny weeds in big aerial images."""
    H, W = img.shape[:2]
    if H <= tile and W <= tile:
        return detector(img)
    step = int(tile * (1 - overlap))
    dets = []
    for y in list(range(0, max(1, H - tile), step)) + [max(0, H - tile)]:
        for x in list(range(0, max(1, W - tile), step)) + [max(0, W - tile)]:
            for d in detector(img[y:y + tile, x:x + tile]):
                b = d["box"]
                dets.append(_det(d["name"], d["cls"], d["conf"], b[0] + x, b[1] + y, b[2] + x, b[3] + y, d["source"]))
    return nms(dets, iou)


# ----------------------------------------------------------------------------- factory
class MultiDetector(object):
    """Runs several detectors and concatenates results. Each may read a different image key."""

    def __init__(self, detectors):
        self.detectors = detectors     # list of (detector, image_key, tiled)

    def __call__(self, images):
        """images: dict key->image (e.g. {'rgb': frame, 'thermal': tframe}) or a single image."""
        if not isinstance(images, dict):
            images = {"rgb": images}
        out = []
        self._calls = getattr(self, "_calls", 0) + 1
        for det, key, tiled in self.detectors:
            every = getattr(det, "every", 1)
            if every > 1 and self._calls % every:
                continue          # `every: N` in the config: this (slower / less urgent) detector runs on every Nth frame
            img = images.get(key)
            if img is None:
                continue
            if isinstance(det, ThermalDetector) and det.mode != "celsius" and (key + "_temp") in images:
                continue          # real temperatures available -> skip the brightness fallback for this camera
            res = detect_tiled(det, img, tiled) if tiled else det(img)
            temp = images.get(key + "_temp")
            if temp is not None and not isinstance(det, ThermalDetector):
                res = _with_temperature(res, img, temp, getattr(det, "min_temp_c", None))
            for d in res:
                d["image"] = key
            out += res
        return out


def _with_temperature(dets, img, temp, min_temp_c=None):
    """A neural network ran on a thermal picture that also has a deg C map: give every box its hottest temperature
    (`max_temp_c`, shown on the map) and drop boxes that are colder than `min_temp_c` - a number for every class,
    or {class: deg C} for some classes only, e.g. {fire: 100}: the network finds the source, the temperature confirms it."""
    temp = np.asarray(temp)
    if temp.ndim != 2:
        return dets
    sy, sx = temp.shape[0] / float(img.shape[0]), temp.shape[1] / float(img.shape[1])
    kept = []
    for d in dets:
        x1, y1, x2, y2 = d["box"]
        r0, c0 = max(0, int(y1 * sy)), max(0, int(x1 * sx))
        r1, c1 = max(r0 + 1, int(math.ceil(y2 * sy))), max(c0 + 1, int(math.ceil(x2 * sx)))
        a = temp[r0:r1, c0:c1]
        if a.size:
            d["max_temp_c"] = float(a.max())
            need = min_temp_c.get(d["name"]) if isinstance(min_temp_c, dict) else min_temp_c
            if need is not None and d["max_temp_c"] < float(need):
                continue
        kept.append(d)
    return kept


def build_detector(cfg, base_dir="."):
    """
    Build from config (YAML/dict). Example:
      detectors:
        - type: yolo
          model: models/fire/best.onnx
          conf: 0.4
          classes: [fire, smoke]      # optional filter
        - type: hsv
          label: flame
          min_area: 200
        - type: thermal
          image: thermal              # which camera image to use
          threshold: 210
    """
    items = cfg.get("detectors", cfg) if isinstance(cfg, dict) else cfg
    built = []
    for c in items:
        c = dict(c)
        t = c.pop("type")
        key = c.pop("image", "rgb")
        tiled = c.pop("tile", 0)
        every = max(1, int(c.pop("every", 1)))
        min_temp_c = c.pop("min_temp_c", None)      # yolo on a thermal picture: confirm boxes with the deg C map
        if t == "yolo":
            m = c.pop("model")
            if not os.path.isabs(m):
                m = os.path.join(base_dir, m)
            d = None
            # Orange Pi NPU: models/x/best.onnx is replaced by models/x/best_rknn_model when that folder exists and
            # the RKNN runtime is installed (about 5x faster than the CPU). Anywhere else the .onnx is used.
            npu = m[:-5] + "_rknn_model" if m.endswith(".onnx") else None
            if npu and os.path.isdir(npu):
                try:
                    import rknnlite.api  # noqa: F401
                    d = YoloDetector(npu, **c)
                    print("[detector] %s: running on the NPU (%s)" % (os.path.basename(os.path.dirname(m)) or m, os.path.basename(npu)))
                except ImportError:
                    d = None
                except Exception as e:
                    print("[detector] NPU model %s failed (%s) - using the CPU model" % (npu, e))
                    d = None
            if d is None:
                try:
                    d = YoloDetector(m, **c)
                except Exception as e:  # keep the mission alive with the remaining detectors
                    print("[detector] WARNING: cannot load %s (%s) - skipped" % (m, e))
                    continue
        elif t == "hsv":
            d = HSVDetector(**c)
        elif t == "thermal":
            d = ThermalDetector(**c)
        elif t == "exg":
            d = ExGDetector(**c)
        elif t == "aruco":
            d = ArucoDetector(**c)
        else:
            raise ValueError("unknown detector type %s" % t)
        d.every = every
        d.min_temp_c = min_temp_c
        built.append((d, key, tiled))
    # `min_temp_c: {fire: fire_c}` = the same threshold as the thermal rule (so the dashboard's fire temperature
    # setting moves both together)
    fire_c = next((d.threshold_c for d, _, _ in built if isinstance(d, ThermalDetector) and d.mode == "celsius"), 100.0)
    for d, _, _ in built:
        mt = getattr(d, "min_temp_c", None)
        if mt == "fire_c":
            d.min_temp_c = fire_c
        elif isinstance(mt, dict):
            d.min_temp_c = {k: (fire_c if v == "fire_c" else v) for k, v in mt.items()}
    return MultiDetector(built)
