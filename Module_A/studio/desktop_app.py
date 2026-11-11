#!/usr/bin/env python3
"""
BRICS Mission Studio - native desktop application (Qt / PySide6). macOS .app and Windows .exe.

The app only contains the GUI. All work is done by the toolkit folder (brics_toolkit/) and its own Python
environment, so the toolkit can be updated without rebuilding the app.
"""
# --- stdlib modules used by the backend (studio/studio.py is loaded from the toolkit folder at runtime;
#     importing them here makes PyInstaller bundle them)
import glob  # noqa: F401
import http.server  # noqa: F401
import json
import os
import re
import shlex  # noqa: F401
import shutil  # noqa: F401
import subprocess
import sys
import threading  # noqa: F401
import time
import urllib.parse  # noqa: F401
import urllib.request  # noqa: F401
import uuid  # noqa: F401
import webbrowser

import markdown  # noqa: F401
import markdown.extensions.fenced_code  # noqa: F401
import markdown.extensions.tables  # noqa: F401
import yaml  # noqa: F401
from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPalette, QTextCursor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

APP_NAME = "BRICS Mission Studio"
APP_VERSION = "1.1.0"           # GUI version (the toolkit version is read from <toolkit>/VERSION at runtime)
DEFAULT_ROOTS = [os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 os.path.expanduser("~/Desktop/brics_toolkit"), os.path.expanduser("~/brics_toolkit"),
                 "C:\\brics_toolkit", os.path.expanduser("~\\Desktop\\brics_toolkit"), os.path.expanduser("~\\Documents\\brics_toolkit")]


# ============================================================================ locate toolkit
def is_toolkit(p):
    return bool(p) and os.path.exists(os.path.join(p, "studio", "cases.py")) and os.path.exists(os.path.join(p, "studio", "studio.py"))


def find_toolkit(settings):
    cands = [os.environ.get("BRICS_ROOT"), settings.value("root")]
    exe = os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
    d = os.path.dirname(exe)
    for _ in range(6):                          # app/exe placed inside (or next to) the toolkit folder
        cands += [d, os.path.join(d, "brics_toolkit")]
        d = os.path.dirname(d)
    cands += DEFAULT_ROOTS
    for c in cands:
        if c and is_toolkit(c):
            return os.path.abspath(c)
    return None


# ============================================================================ small UI helpers
def btn(text, cb=None, kind="", big=False):
    b = QPushButton(text)
    b.setProperty("kind", kind)
    if big:
        b.setProperty("big", True)
        b.setMinimumHeight(44)
    if cb:
        b.clicked.connect(cb)
    b.setCursor(Qt.PointingHandCursor)
    return b


def h(*ws, stretch=False):
    w = QWidget()
    w.setObjectName("row")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    for x in ws:
        lay.addWidget(x) if isinstance(x, QWidget) else lay.addLayout(x)
    if stretch:
        lay.addStretch(1)
    return w


def title(text, sub=None):
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 8)
    t = QLabel(text)
    t.setObjectName("h1")
    v.addWidget(t)
    if sub:
        s = QLabel(sub)
        s.setWordWrap(True)
        s.setObjectName("sub")
        v.addWidget(s)
    return w


def group(name, *widgets):
    g = QGroupBox(name)
    v = QVBoxLayout(g)
    for w in widgets:
        v.addWidget(w) if isinstance(w, QWidget) else v.addLayout(w)
    return g


class CaseCard(QFrame):
    """Clickable card with word-wrapped text."""

    def __init__(self, head, body, foot, selected, on_click):
        super().__init__()
        self.setObjectName("casecard")
        self.setProperty("sel", selected)
        self.setCursor(Qt.PointingHandCursor)
        self.on_click = on_click
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        for txt, name in ((head, "cardhead"), (body, "cardbody"), (foot, "cardfoot")):
            l = QLabel(txt)
            l.setWordWrap(True)
            l.setObjectName(name)
            v.addWidget(l)
        v.addStretch(1)
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def mousePressEvent(self, e):
        self.on_click()


class PathPicker(QWidget):
    """Line edit + 'Folder…' + 'File…' buttons with native dialogs."""

    def __init__(self, placeholder="folder or .zip", files="Datasets (*.zip *.yaml);;All files (*)", folder=True, file=True):
        super().__init__()
        self.setObjectName("row")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        lay.addWidget(self.edit, 1)
        self.filt = files
        if folder:
            lay.addWidget(btn("Folder…", self.pick_dir, "ghost"))
        if file:
            lay.addWidget(btn("File…", self.pick_file, "ghost"))

    def start(self):
        t = self.edit.text().strip()
        return t if t and os.path.exists(t) else os.path.expanduser("~/Downloads")

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose folder", self.start())
        if d:
            self.edit.setText(d)

    def pick_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose file", self.start(), self.filt)
        if f:
            self.edit.setText(f)

    def text(self):
        return self.edit.text().strip()

    def setText(self, t):
        self.edit.setText(t or "")


def scroll_page(*widgets):
    inner = QWidget()
    v = QVBoxLayout(inner)
    v.setContentsMargins(22, 16, 22, 16)
    v.setSpacing(12)
    for w in widgets:
        v.addWidget(w)
    v.addStretch(1)
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(inner)
    return sa, v


LIMITS = {"altitude": (0.3, 3.0), "speed": (0.05, 2.0), "safety.max_time": (30, 600), "safety.min_cell_voltage": (3.2, 4.0),
          "swarm.n_drones": (1, 10)}


def parse_quick(key, text):
    """Validate one quick-settings field. Raises ValueError with a message the operator understands."""
    t = text.strip()
    if key in ("area", "home"):
        val = [float(x) for x in t.split(",") if x.strip()]
        need = 4 if key == "area" else 2
        if len(val) != need:
            raise ValueError("%s needs %d numbers separated by commas" % (key, need))
        if key == "area" and (val[0] >= val[2] or val[1] >= val[3]):
            raise ValueError("area must be x0, y0, x1, y1 with x0 < x1 and y0 < y1")
        return val
    if key in ("supports", "targets"):
        val = [[float(x) for x in s.split(",")] for s in t.split(";") if s.strip()]
        if not val or any(len(v) != 2 for v in val):
            raise ValueError("%s: write x, y pairs separated by ';'  e.g. 1.5, 2 ; 4.5, 2" % key)
        return val
    if key == "swarm.planner_url":
        if t and not re.match(r"^https?://[A-Za-z0-9.\-]+(:\d+)?/?$", t):
            raise ValueError("planner URL must look like http://192.168.1.10:8000")
        return t
    val = int(t) if key == "swarm.n_drones" else float(t)
    lo, hi = LIMITS.get(key, (None, None))
    if lo is not None and not lo <= val <= hi:
        raise ValueError("%s = %s is outside the safe range %s .. %s" % (key, t, lo, hi))
    return val


def parse_metrics(md):
    m = re.search(r"\|\s*\*\*all\*\*\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*\*\*([\d.]+)\*\*\s*\|\s*([\d.]+)", md or "")
    if m:
        return {"P": m.group(1), "R": m.group(2), "mAP50": m.group(3), "mAP50-95": m.group(4)}
    m = re.search(r"top1 accuracy \|\s*([\d.]+)", md or "")
    return {"top1": m.group(1)} if m else {}


# ============================================================================ main window
class Studio(QMainWindow):
    STEPS = ["1  Problem statement", "2  Data & AI model", "3  Mission setup", "4  Simulation test", "5  Economics",
             "6  Documents", "7  Drone & flight", "⚡ AUTOPILOT", "?  Help & self-test"]

    def __init__(self, B, root):
        super().__init__()
        self.B, self.root = B, root
        self.watchers = {}           # job id -> callback
        self.cur_job = None
        self.toolkit_version = self.read_version()
        self.setWindowTitle("%s %s" % (APP_NAME, APP_VERSION))
        self.resize(1360, 900)
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # top bar
        top = QFrame()
        top.setObjectName("top")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 8, 16, 8)
        logo = QLabel("🚁  BRICS Mission Studio")
        logo.setObjectName("logo")
        self.proj_label = QLabel("")
        self.proj_label.setObjectName("proj")
        tl.addWidget(logo)
        tl.addSpacing(20)
        tl.addWidget(self.proj_label, 1)
        tl.addWidget(btn("⚡ AUTOPILOT", lambda: self.go(7), "yellow", big=True))
        outer.addWidget(top)
        # env warning
        self.env_banner = QLabel("")
        self.env_banner.setObjectName("banner")
        self.env_banner.setWordWrap(True)
        self.env_banner.hide()
        outer.addWidget(self.env_banner)
        # body: nav | pages ; console under
        split = QSplitter(Qt.Vertical)
        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(230)
        for s in self.STEPS:
            self.nav.addItem(QListWidgetItem(s))
        self.nav.currentRowChanged.connect(self.go)
        bl.addWidget(self.nav)
        self.stack = QStackedWidget()
        bl.addWidget(self.stack, 1)
        split.addWidget(body)
        split.addWidget(self.build_console())
        split.setSizes([640, 240])
        outer.addWidget(split, 1)
        self.pages = [self.page_ps, self.page_data, self.page_mission, self.page_test, self.page_econ,
                      self.page_docs, self.page_drone, self.page_auto, self.page_help]
        for _ in self.pages:
            self.stack.addWidget(QWidget())
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(700)
        self.check_env()
        self.nav.setCurrentRow(1 if self.B.load_project() else 0)

    # ------------------------------------------------------------------ infrastructure
    def read_version(self):
        try:
            with open(os.path.join(self.root, "VERSION")) as f:
                return f.read().strip() or "?"
        except OSError:
            return "?"

    def check_env(self):
        py = self.B.PY
        ok = os.path.exists(py) and (os.path.sep in py)
        if not ok:
            if sys.platform.startswith("win"):
                txt = "⚠ The AI environment is not installed on this PC yet. Go to 'Help & self-test' → 'Install AI environment (offline)'."
            else:
                txt = "⚠ The toolkit Python environment (.venv) is missing. Go to 'Help & self-test' → 'Install AI environment (offline)'."
            self.env_banner.setText(txt)
            self.env_banner.show()
        else:
            self.env_banner.hide()

    def build_console(self):
        w = QWidget()
        w.setObjectName("console")
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 4, 8, 6)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("<b>Jobs</b>"))
        self.job_combo = QComboBox()
        self.job_combo.setMinimumWidth(380)
        self.job_combo.activated.connect(lambda i: setattr(self, "cur_job", self.job_combo.itemData(i)))
        bar.addWidget(self.job_combo)
        self.job_status = QLabel("")
        bar.addWidget(self.job_status)
        bar.addStretch(1)
        bar.addWidget(btn("Stop job", self.stop_job, "ghost"))
        v.addLayout(bar)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("log")
        self.log.setPlainText("Ready. Every action runs here with a live log.")
        v.addWidget(self.log, 1)
        return w

    def run(self, action, args=None, done=None):
        if not self.B.load_project() and action not in ("selftest",):
            QMessageBox.information(self, APP_NAME, "Choose a problem statement first (step 1).")
            return None
        title, fn = self.B.ACTIONS[action]
        args = dict(args or {})
        job = self.B.start_job(title, lambda j: fn(j, args))
        self.cur_job = job.id
        if done:
            self.watchers[job.id] = done
        self.refresh_jobs()
        return job

    def tick(self):
        for jid, cb in list(self.watchers.items()):
            j = self.B.JOBS.get(jid)
            if j and j.status != "running":
                del self.watchers[jid]
                self.refresh_jobs()
                try:
                    cb(j)
                except Exception as e:
                    self.log.appendPlainText("GUI callback error: %s" % e)
        if self.cur_job and self.cur_job in self.B.JOBS:
            j = self.B.JOBS[self.cur_job]
            text = "\n".join(j.lines[-600:])
            if text != getattr(self, "_last_log", None):
                sb = self.log.verticalScrollBar()
                at_bottom = sb.value() >= sb.maximum() - 20
                self._last_log = text
                self.log.setPlainText(text)
                if at_bottom:
                    self.log.moveCursor(QTextCursor.End)
            col = {"running": "#e9c46a", "done": "#52d18a", "failed": "#ff6b6b"}[j.status]
            self.job_status.setText("<span style='color:%s'><b>%s</b></span>  %ds" % (col, j.status.upper(),
                                                                                       int((j.ended or time.time()) - j.started)))
        if self.stack.currentIndex() == 7:
            self.update_autopilot()

    def refresh_jobs(self):
        js = sorted(self.B.JOBS.values(), key=lambda x: -x.started)[:20]
        self.job_combo.blockSignals(True)
        self.job_combo.clear()
        for j in js:
            self.job_combo.addItem("%s - %s" % (j.title, j.status), j.id)
            if j.id == self.cur_job:
                self.job_combo.setCurrentIndex(self.job_combo.count() - 1)
        self.job_combo.blockSignals(False)

    def stop_job(self):
        j = self.B.JOBS.get(self.cur_job)
        if j and j.proc and j.proc.poll() is None:
            j.proc.terminate()
            j.log("(stopped by user)")

    def project(self):
        return self.B.load_project()

    def need_project(self):
        if self.project():
            return True
        sa, v = scroll_page(title("Choose a problem statement first"), btn("Go to step 1", lambda: self.nav.setCurrentRow(0), "green"))
        self.set_page(sa)
        return False

    def set_page(self, w):
        i = self.stack.currentIndex()
        old = self.stack.widget(i)
        self.stack.insertWidget(i, w)
        self.stack.setCurrentIndex(i)
        self.stack.removeWidget(old)
        old.deleteLater()

    def go(self, i):
        if i < 0:
            return
        if self.nav.currentRow() != i:
            self.nav.setCurrentRow(i)
            return
        self.stack.setCurrentIndex(i)
        p = self.project()
        self.proj_label.setText(("Project:  " + str(p.get("title", p["slug"]))) if p else "No problem statement selected - start at step 1")
        try:
            self.pages[i]()
        except Exception as e:                 # a broken config / project file must not leave a dead page
            import traceback
            self.log.appendPlainText(traceback.format_exc())
            sa, v = scroll_page(title("Could not open this page", "%s: %s" % (type(e).__name__, e)),
                                QLabel("Usually a config or project file is missing or has a YAML error. Fix it in step 3 "
                                       "(Full configuration) or choose the problem statement again in step 1. Details are in the log below."),
                                h(btn("Go to step 1", lambda: self.nav.setCurrentRow(0), "green"),
                                  btn("Go to step 3", lambda: self.nav.setCurrentRow(2)), stretch=True))
            self.set_page(sa)

    def open_file(self, rel):
        f = rel if os.path.isabs(rel) else os.path.join(self.root, rel)
        if os.path.exists(f):
            QDesktopServices.openUrl(QUrl.fromLocalFile(f))
        else:
            QMessageBox.warning(self, APP_NAME, "Not found:\n%s" % f)

    def terminal(self, what, **kw):
        p = self.project()
        try:
            cmd = self.B.terminal_commands(p, what, kw.get("ip", "10.42.0.1"), kw.get("id", 0), kw.get("folder", ""), kw.get("classes"), kw.get("extra"))
        except (ValueError, TypeError) as e:
            return QMessageBox.warning(self, APP_NAME, str(e))
        self.B.open_terminal(cmd)
        self.log.appendPlainText("[terminal] " + cmd)

    # ------------------------------------------------------------------ 1 problem statement
    def page_ps(self):
        p = self.project()
        grid = QGridLayout()
        grid.setSpacing(12)
        for k, (key, c) in enumerate(self.B.CASES.items()):
            sel = bool(p and p["case"] == key)
            card = CaseCard(("✔  " if sel else "") + c["title"], c["problem"][:230] + "…",
                            "Partner: %s   ·   mission: %s\nObjects: %s" % (c["partner"], c["mission_type"], ", ".join(c["classes"])),
                            sel, lambda kk=key: self.new_project(kk))
            grid.addWidget(card, k // 2, k % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        cards = QWidget()
        cards.setLayout(grid)
        # custom PS
        self.c_title, self.c_partner, self.c_customer, self.c_objects = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.c_title.setPlaceholderText("e.g. Autonomous search for lost people")
        self.c_objects.setPlaceholderText("person, backpack")
        self.c_problem = QPlainTextEdit()
        self.c_problem.setMaximumHeight(80)
        self.c_mt = QComboBox()
        for k, t in (("survey", "survey - search an area (camera down)"), ("photos", "photos - photo grid + counting / map"),
                     ("orbit", "orbit - inspect structures (camera forward)"), ("waypoints", "waypoints - route / patrol")):
            self.c_mt.addItem(t, k)
        f = QFormLayout()
        f.addRow("Title", self.c_title)
        f.addRow("Partner", self.c_partner)
        f.addRow("Problem (from the task)", self.c_problem)
        f.addRow("Customer", self.c_customer)
        f.addRow("Objects to detect", self.c_objects)
        f.addRow("Mission type", self.c_mt)
        custom = group("➕  New / unknown problem statement - the studio builds the solution for it", f,
                       h(btn("Create solution for this PS", self.new_custom, "green", big=True), stretch=True))
        projs = QListWidget()
        projs.setMaximumHeight(140)
        for pr in self.B.list_projects():
            it = QListWidgetItem("%s     [%s]     model: %s" % (pr.get("title", pr["slug"]), pr.get("case", "?"), pr.get("model") or "-"))
            it.setData(Qt.UserRole, pr["slug"])
            projs.addItem(it)
        projs.itemDoubleClicked.connect(lambda it: self.open_project(it.data(Qt.UserRole)))
        sa, v = scroll_page(title("1 · Select the problem statement", "Click the case they gave you, or describe a NEW problem statement below."),
                            cards, custom, group("Existing projects (double-click to open)", projs))
        self.set_page(sa)

    def new_project(self, key):
        self.B.new_project(key)
        self.nav.setCurrentRow(1)

    def new_custom(self):
        t = self.c_title.text().strip()
        if not t:
            QMessageBox.warning(self, APP_NAME, "Give the problem statement a title.")
            return
        self.B.new_project("custom", {"title": t, "partner": self.c_partner.text(), "problem": self.c_problem.toPlainText(),
                                      "customer": self.c_customer.text(), "objects": self.c_objects.text(),
                                      "mission_type": self.c_mt.currentData()})
        self.nav.setCurrentRow(1)

    def open_project(self, slug):
        pr = self.B.load_project(slug)
        if not pr:
            return QMessageBox.warning(self, APP_NAME, "This project file cannot be read any more.")
        self.B.save_project(pr)
        self.nav.setCurrentRow(1)

    # ------------------------------------------------------------------ 2 data & model
    def page_data(self):
        if not self.need_project():
            return
        p = self.project()
        self.ds = PathPicker("their dataset: .zip or folder (YOLO / COCO / VOC / CSV / class folders)")
        self.ds.setText(os.path.join(self.root, p["dataset"]) if p.get("dataset") else "")
        self.q = QComboBox()
        self.q.addItems(["fast", "balanced", "best"])
        self.q.setCurrentIndex(1)
        self.hours = QDoubleSpinBox()
        self.hours.setRange(0, 24)
        self.hours.setSingleStep(0.25)
        self.hours.setSpecialValueText("no limit")
        self.imgsz = QComboBox()
        self.imgsz.addItems(["auto (640)", "416", "640", "960"])
        self.arch = QComboBox()
        self.arch.addItem("YOLO11 (most compatible)", "yolo11")
        self.arch.addItem("YOLO26 (newest)", "yolo26")
        self.aerial = QCheckBox("top-down drone images (aerial augmentation)")
        f = QFormLayout()
        f.addRow("Dataset", self.ds)
        f.addRow("Quality", self.q)
        f.addRow("Max training hours", self.hours)
        f.addRow("Image size", self.imgsz)
        f.addRow("Architecture", self.arch)
        f.addRow("", self.aerial)
        a = group("A.  Dataset → trained model", f, h(btn("1. Check / convert dataset", self.prepare, "blue"),
                                                      btn("2. Train best model", self.train, "green", big=True), stretch=True),
                  QLabel("Trains on the GPU if available, validates (precision / recall / mAP), exports ONNX, checks it, and puts it in the mission."))
        # models table
        models = self.B.list_models()
        t = QTableWidget(len(models), 6)
        t.setHorizontalHeaderLabels(["Model", "mAP50", "Precision", "Recall", "NPU (RKNN)", ""])
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, m in enumerate(models):
            md_file = os.path.join(self.root, "models", m["name"], "metrics.md")
            mt = parse_metrics(open(md_file).read() if os.path.exists(md_file) else "")
            cur = p.get("model") and os.path.dirname(p["model"]).endswith(m["name"])
            for c, val in enumerate([m["name"] + ("   ◀ in use" if cur else ""), mt.get("mAP50", mt.get("top1", "-")),
                                     mt.get("P", "-"), mt.get("R", "-"), "yes" if m["rknn"] else "-"]):
                t.setItem(r, c, QTableWidgetItem(val))
            if m["onnx"]:
                t.setCellWidget(r, 5, btn("Use in mission", lambda _=False, o=m["onnx"]: self.use_model(o), "green"))
        t.setMinimumHeight(60 + 34 * max(1, len(models)))
        mg = group("Trained models", t if models else QLabel("none yet"))
        # B. unlabeled
        self.lf = PathPicker("folder of images", folder=True, file=False)
        self.alm = QComboBox()
        for k, tx in (("hsv", "colour (flames / markers)"), ("exg", "vegetation (plants)"), ("thermal", "thermal hot spots"), ("model", "existing model")):
            self.alm.addItem(tx, k)
        self.all = QLineEdit()
        self.all.setPlaceholderText("class name (e.g. fire)  or  model path for 'existing model'")
        f2 = QFormLayout()
        f2.addRow("Image folder", self.lf)
        f2.addRow("Auto-label method", self.alm)
        f2.addRow("Class / model", self.all)
        b = group("B.  Only images, no labels?", f2, h(btn("Auto-label", self.autolabel), btn("Open labelling tool", self.label_tool),
                                                       btn("Train on this folder", lambda: (self.ds.setText(self.lf.text()), self.train()), "green"), stretch=True),
                  QLabel("Labelling tool keys: 1-9 class · drag = box · right-click = delete · d next · a back · u undo · q save & quit"))
        # C. video
        self.vid = PathPicker("video file or frames folder", files="Videos (*.mp4 *.mov *.avi *.mkv);;All files (*)")
        self.vout = QLineEdit(os.path.join(self.root, "datasets", p["slug"] + "_frames"))
        f3 = QFormLayout()
        f3.addRow("Video / frames", self.vid)
        f3.addRow("Output folder", self.vout)
        c = group("C.  Videos → images", f3, h(btn("Extract sharp, non-duplicate frames",
                                                   lambda: self.run("extract", {"inputs": [self.vid.text()], "out": self.vout.text()},
                                                                    lambda j: self.lf.setText(self.vout.text()))), stretch=True))
        # D. synthetic
        self.so = PathPicker("labelled dataset with the objects", file=False)
        self.so.setText(os.path.join(self.root, p["dataset"]) if p.get("dataset") else "")
        self.sb = PathPicker("photos of the venue floor / field WITHOUT objects", file=False)
        f4 = QFormLayout()
        f4.addRow("Objects (labelled)", self.so)
        f4.addRow("Backgrounds", self.sb)
        d = group("D.  Few labelled images → 1000 synthetic (copy-paste)", f4, h(btn("Generate 1000 images", self.synth), stretch=True))
        sa, v = scroll_page(title("2 · Data & AI model", "Current model in the mission: %s" % (p.get("model") or "none (classic detectors only)")), a, mg, b, c, d)
        self.set_page(sa)

    def prepare(self):
        if not self.ds.text():
            return QMessageBox.warning(self, APP_NAME, "Choose the dataset first.")
        self.run("prepare", {"inputs": [self.ds.text()]},
                 lambda j: QMessageBox.information(self, "Dataset", j.result.get("report") or "See the log.") if j.status == "done" else None)

    def train(self):
        data = self.ds.text() or (self.project() or {}).get("dataset")
        if not data:
            return QMessageBox.warning(self, APP_NAME, "Choose the dataset first.")
        imgsz = self.imgsz.currentText()
        self.run("train", {"data": data, "quality": self.q.currentText(), "hours": self.hours.value() or None,
                           "imgsz": None if imgsz.startswith("auto") else imgsz, "arch": self.arch.currentData(),
                           "aerial": self.aerial.isChecked()}, lambda j: self.go(1) if self.nav.currentRow() == 1 else None)

    def use_model(self, onnx):
        self.B.apply_model(self.project(), os.path.join(self.root, onnx))
        QMessageBox.information(self, APP_NAME, "The mission now uses:\n%s" % onnx)
        self.go(1)

    def autolabel(self):
        m = self.alm.currentData()
        self.run("autolabel", {"folder": self.lf.text(), "method": m, "label": self.all.text(), "model": self.all.text()})

    def label_tool(self):
        folder = self.lf.text()
        if not folder:
            return QMessageBox.warning(self, APP_NAME, "Choose the image folder first.")
        classes = self.all.text().split() if self.all.text() and self.alm.currentData() != "model" else (self.B.case_of(self.project()).get("classes") or ["object"])
        try:
            subprocess.Popen([self.B.PY, os.path.join(self.root, "train", "label_tool.py"), folder, "--classes"] + classes, cwd=self.root)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, "Cannot start the labelling tool:\n%s" % e)

    def synth(self):
        p = self.project()
        out = os.path.join(self.root, "datasets", p["slug"] + "_synth")
        self.run("synth", {"objects": self.so.text(), "backgrounds": self.sb.text(), "out": out, "n": 1000},
                 lambda j: self.ds.setText(out) if j.status == "done" else None)

    # ------------------------------------------------------------------ 3 mission
    def page_mission(self):
        if not self.need_project():
            return
        p = self.project()
        cfgp = os.path.join(self.root, p["config"])
        txt = open(cfgp).read()
        try:
            g = yaml.safe_load(txt) or {}
            yaml_err = None
        except yaml.YAMLError as e:          # still show the editor so the error can be fixed here
            g, yaml_err = {}, str(e)
        if not isinstance(g, dict):
            g, yaml_err = {}, "the file is not a YAML mapping"
        self.f = {}
        form = QFormLayout()

        def add(key, label, val):
            e = QLineEdit(str(val))
            self.f[key] = e
            form.addRow(label, e)
        if g.get("area"):
            add("area", "Area x0, y0, x1, y1 (m, aruco_map)", ", ".join(str(x) for x in g["area"]))
        if g.get("supports"):
            add("supports", "Tower positions  x,y ; x,y …", " ; ".join("%s, %s" % tuple(s[:2]) for s in g["supports"]))
        if g.get("targets"):
            add("targets", "Targets  x,y ; x,y …", " ; ".join("%s, %s" % tuple(s[:2]) for s in g["targets"]))
        if g.get("home"):
            add("home", "Home (landing) x, y", ", ".join(str(x) for x in g["home"]))
        add("altitude", "Altitude (m)", g.get("altitude", 1.5))
        add("speed", "Speed (m/s)", g.get("speed", 0.4))
        add("safety.max_time", "Max mission time (s)", (g.get("safety") or {}).get("max_time", 540))
        add("safety.min_cell_voltage", "Land below cell voltage (V)", (g.get("safety") or {}).get("min_cell_voltage", 3.5))
        if g.get("swarm"):
            add("swarm.n_drones", "Number of drones", g["swarm"].get("n_drones", 3))
            add("swarm.planner_url", "Planner URL (this laptop)", g["swarm"].get("planner_url", ""))
        quick = group("Quick settings", form, h(btn("Save quick settings", self.save_quick, "green"), stretch=True))
        if yaml_err:
            quick = group("⚠  YAML error - fix it in the editor below and press Save YAML", QLabel(yaml_err))
        self.yaml_edit = QPlainTextEdit(txt)
        self.yaml_edit.setFont(QFont("Menlo" if sys.platform == "darwin" else "Consolas", 11))
        self.yaml_edit.setMinimumHeight(430)
        full = group("Full configuration (YAML) - detectors, cameras, inspection, tracker, safety, swarm, mock scene", QLabel(p["config"]),
                     self.yaml_edit, h(btn("Save YAML", self.save_yaml, "green"), btn("Reload", lambda: self.go(2), "ghost"),
                                       btn("Next: simulation test →", lambda: self.nav.setCurrentRow(3)), stretch=True))
        sa, v = scroll_page(title("3 · Mission setup", self.B.case_of(p)["solution"]), quick, full)
        self.set_page(sa)

    def save_quick(self):
        p = self.project()
        cfgp = os.path.join(self.root, p["config"])
        cfg = yaml.safe_load(open(cfgp)) or {}
        try:
            for k, e in self.f.items():
                val = parse_quick(k, e.text())
                cur = cfg
                ks = k.split(".")
                for kk in ks[:-1]:
                    if not isinstance(cur.get(kk), dict):
                        cur[kk] = {}
                    cur = cur[kk]
                cur[ks[-1]] = val
        except ValueError as ex:
            return QMessageBox.warning(self, APP_NAME, "Check the values: %s" % ex)
        self.B._write(cfgp, yaml.safe_dump(cfg, sort_keys=False))
        self.go(2)

    def save_yaml(self):
        try:
            yaml.safe_load(self.yaml_edit.toPlainText())
        except Exception as e:
            return QMessageBox.warning(self, APP_NAME, "YAML error:\n%s" % e)
        self.B._write(os.path.join(self.root, self.project()["config"]), self.yaml_edit.toPlainText())
        QMessageBox.information(self, APP_NAME, "Saved.")

    # ------------------------------------------------------------------ 4 test
    def page_test(self):
        if not self.need_project():
            return
        self.test_res = QTextBrowser()
        self.test_res.setMinimumHeight(220)
        self.test_res.setOpenExternalLinks(True)
        g = group("Simulated mission (real mission code + simulated drone and camera, no hardware)",
                  h(btn("▶  Run simulated mission", self.mock, "green", big=True),
                    btn("Open live operator view (:8090)", lambda: webbrowser.open("http://localhost:8090"), "ghost"),
                    btn("Swarm dashboard (:8000)", lambda: webbrowser.open("http://localhost:8000"), "ghost") if self.project()["case"] == "case3" else QWidget(),
                    stretch=True), self.test_res)
        self.report_btn = btn("📄  Open mission report", lambda: self.open_file(self.last_report), "blue")
        self.report_btn.setEnabled(False)
        sa, v = scroll_page(title("4 · Simulation test", "Checks the flight plan, detection pipeline, coordinates, safety logic and the report."),
                            g, h(self.report_btn, stretch=True))
        self.set_page(sa)

    def mock(self):
        self.test_res.setHtml("<i>running…</i>")

        def done(j):
            s = j.result.get("summary") or {}
            ok = j.status == "done"
            html = "<h3 style='color:%s'>%s</h3>" % ("#52d18a" if ok else "#ff6b6b", "Mission finished" if ok else "Problem - see the log")
            if s:
                html += "<table cellpadding=4><tr><td>Result</td><td><b>%s</b></td></tr><tr><td>Flight time (simulated)</td><td>%s s</td></tr>" \
                        "<tr><td>Distance</td><td>%s m</td></tr><tr><td>Objects</td><td>%s</td></tr></table>" % (
                            s.get("result"), s.get("duration_s"), s.get("distance_m"), s.get("counts"))
            self.test_res.setHtml(html)
            if j.result.get("report"):
                self.last_report = j.result["report"]
                self.report_btn.setEnabled(True)
        self.run("mock", {}, done)

    # ------------------------------------------------------------------ 5 economics
    def page_econ(self):
        if not self.need_project():
            return
        p = self.project()
        self.econ_edit = QPlainTextEdit(open(os.path.join(self.root, p["econ"])).read())
        self.econ_edit.setFont(QFont("Menlo" if sys.platform == "darwin" else "Consolas", 11))
        self.econ_edit.setMinimumHeight(380)
        self.econ_res = QTextBrowser()
        self.econ_res.setMinimumHeight(420)
        md = os.path.join(self.root, "economics", "generated", "out", p["slug"] + ".md")
        if os.path.exists(md):
            self.econ_res.setHtml(self.B.md_to_html(open(md).read()))
        sa, v = scroll_page(title("5 · Economic efficiency (Module C)", "Edit customer, CAPEX, OPEX, benefits, discount rate → Calculate. "
                                  "Gives payback, ROI, NPV, IRR, sensitivity, break-even, alternatives and an Excel file with live formulas."),
                            group("Inputs (YAML)", self.econ_edit, h(btn("Save & calculate", self.econ, "green", big=True),
                                                                      btn("Open Excel file", lambda: self.open_file(os.path.join("economics", "generated", "out", p["slug"] + ".xlsx")), "ghost"),
                                                                      stretch=True)),
                            group("Result", self.econ_res))
        self.set_page(sa)

    def econ(self):
        p = self.project()
        try:
            yaml.safe_load(self.econ_edit.toPlainText())
        except Exception as e:
            return QMessageBox.warning(self, APP_NAME, "YAML error:\n%s" % e)
        open(os.path.join(self.root, p["econ"]), "w").write(self.econ_edit.toPlainText())
        self.run("econ", {}, lambda j: self.econ_res.setHtml(self.B.md_to_html(j.result.get("md", "")) or "see log"))

    # ------------------------------------------------------------------ 6 documents
    def page_docs(self):
        if not self.need_project():
            return
        p = self.project()
        d = os.path.join(self.root, "deliverables", p["slug"])
        files = QListWidget()
        files.setMinimumHeight(260)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                it = QListWidgetItem(("📁  " if os.path.isdir(os.path.join(d, f)) else "📄  ") + f)
                it.setData(Qt.UserRole, os.path.join(d, f))
                files.addItem(it)
        files.itemDoubleClicked.connect(lambda it: self.open_file(it.data(Qt.UserRole)))
        prev = QTextBrowser()
        prev.setMinimumHeight(420)
        tr = os.path.join(d, "05_Test_Report.md")
        if os.path.exists(tr):
            prev.setSearchPaths([d])
            prev.setHtml(self.B.md_to_html(open(tr).read()))
        sa, v = scroll_page(title("6 · Documents & presentation", "Technical description + block diagram, team roles, components, test programme, test report "
                                  "(latest run + model metrics), economics, operating instructions, expert Q&A, Presentation (PPTX + PDF), GitHub repository."),
                            h(btn("Generate all documents", lambda: self.run("docs", {}, lambda j: self.go(5)), "green", big=True),
                              btn("Open Presentation.pptx", lambda: self.open_file(os.path.join(d, "Presentation.pptx")), "blue"),
                              btn("Open ALL_DOCUMENTS.pdf", lambda: self.open_file(os.path.join(d, "ALL_DOCUMENTS.pdf")), "blue"),
                              btn("Open folder", lambda: self.open_file(d), "ghost"), stretch=True),
                            group("Files (double-click to open)", files), group("Preview - test report", prev))
        self.set_page(sa)

    # ------------------------------------------------------------------ 7 drone
    def page_drone(self):
        if not self.need_project():
            return
        p = self.project()
        self.ip = QLineEdit("10.42.0.1")
        self.did = QSpinBox()
        self.did.setRange(0, 9)
        f = QFormLayout()
        f.addRow("Drone IP", self.ip)
        if p["case"] == "case3":
            f.addRow("Drone id (0..n-1)", self.did)
        conn = group("Connection - join the drone Wi-Fi  technic-xxxx  (Wi-Fi password: see the SKYRIS documentation). User: orangepi", f)
        npu = group("1.  Faster AI on the NPU (optional)",
                    h(btn("Convert model to RKNN + use it", lambda: self.run("rknn", {"use": True})), btn("Start Docker", lambda: self.terminal("colima"), "ghost"), stretch=True),
                    QLabel("If RKNN gives problems on the drone, select the .onnx model again in step 2 (CPU - always works)."))
        self.tdev = QSpinBox()
        self.tdev.setRange(0, 9)
        self.tdev.setValue(1)
        thermal = group("Thermal camera (TR256i) - plug it into the Orange Pi, then test",
                        h(QLabel("video device"), self.tdev,
                          btn("Test thermal camera on drone", lambda: self.terminal("thermal_probe", ip=self.ip.text(), extra={"device": self.tdev.value()})),
                          btn("Test on this computer", lambda: self.run("thermal_local", {}), "ghost"), stretch=True),
                        QLabel("Shows which /dev/video it is, whether it gives real temperatures (deg C), and the config lines to use. "
                               "Point it at a hand (~34 C) or the IR heater (>100 C)."))
        self.ar = {k: QDoubleSpinBox() for k in ("size", "dx", "dy")}
        for k, v in (("size", 0.33), ("dx", 0.85), ("dy", 0.85)):
            self.ar[k].setRange(0.05, 3.0)
            self.ar[k].setSingleStep(0.01)
            self.ar[k].setDecimals(3)
            self.ar[k].setValue(v)
        self.ar_n = QSpinBox()
        self.ar_n.setRange(1, 30)
        self.ar_n.setValue(10)
        aruco = group("ArUco marker field - MEASURE the real field (venue: 10x10 markers, 30-35 cm, 70-100 cm apart)",
                      h(QLabel("marker size m"), self.ar["size"], QLabel("spacing x m"), self.ar["dx"], QLabel("spacing y m"), self.ar["dy"],
                        QLabel("markers per row"), self.ar_n, stretch=True),
                      h(btn("Write ArUco map on drone", lambda: self.terminal("aruco_map", ip=self.ip.text(), extra={
                          "size": self.ar["size"].value(), "dx": self.ar["dx"].value(), "dy": self.ar["dy"].value(),
                          "nx": self.ar_n.value(), "ny": self.ar_n.value(), "first": 0})), stretch=True))
        dep = group("2.  Copy code + models to the drone", h(btn("Deploy to drone", lambda: self.terminal("deploy", ip=self.ip.text()), "green"), stretch=True))
        flyw = [btn("▶  Start mission on drone", lambda: self.terminal("run_drone", ip=self.ip.text(), id=self.did.value()), "green", big=True),
                btn("Open operator panel (START / LAND / ABORT)", lambda: webbrowser.open("http://%s:8090" % self.ip.text()), "blue")]
        if p["case"] == "case3":
            flyw = [btn("Start swarm planner here", lambda: self.run("planner", {})), btn("Swarm dashboard", lambda: webbrowser.open("http://localhost:8000"), "ghost")] + flyw
        fly = group("3.  Fly", h(*flyw, stretch=True), QLabel("Safety: RC kill switch in hand, markers visible, battery charged. The mission refuses to start if pre-flight checks fail."))
        after = group("4.  After the flight", h(btn("Copy flight results to this computer", lambda: self.terminal("fetch_runs", ip=self.ip.text())),
                                                btn("Open SSH terminal", lambda: self.terminal("ssh", ip=self.ip.text()), "ghost"), stretch=True),
                      QLabel("Then regenerate the documents (step 6) - the test report will use the real flight."))
        sa, v = scroll_page(title("7 · Drone & flight", "Steps that need the drone password open a terminal window."), conn, thermal, aruco, npu, dep, fly, after)
        self.set_page(sa)

    # ------------------------------------------------------------------ 8 autopilot
    def page_auto(self):
        if not self.need_project():
            return
        p = self.project()
        self.ads = PathPicker("dataset (optional - empty = classic detectors / current model)")
        self.ads.setText(os.path.join(self.root, p["dataset"]) if p.get("dataset") else "")
        self.aq = QComboBox()
        self.aq.addItems(["fast", "balanced", "best"])
        self.aq.setCurrentIndex(1)
        self.ah = QDoubleSpinBox()
        self.ah.setRange(0, 24)
        self.ah.setSingleStep(0.25)
        self.ah.setSpecialValueText("no limit")
        self.aarch = QComboBox()
        self.aarch.addItem("YOLO11", "yolo11")
        self.aarch.addItem("YOLO26", "yolo26")
        self.aaer = QCheckBox("top-down drone images")
        self.arknn = QCheckBox("also convert to RKNN for the NPU (Docker must be available)")
        f = QFormLayout()
        f.addRow("Dataset", self.ads)
        f.addRow("Quality", self.aq)
        f.addRow("Max training hours", self.ah)
        f.addRow("Architecture", self.aarch)
        f.addRow("", self.aaer)
        f.addRow("", self.arknn)
        self.asteps = QListWidget()
        self.asteps.setMinimumHeight(220)
        self.ares = QLabel("")
        self.auto_job = getattr(self, "auto_job", None)
        sa, v = scroll_page(title("⚡ AUTOPILOT - complete solution in one click",
                                  "For: %s\n(dataset → train → export) → simulation test → economics → all documents + presentation + GitHub repo." % p["title"]),
                            group("Settings", f, h(btn("⚡  RUN AUTOPILOT", self.autopilot, "yellow", big=True), stretch=True)),
                            group("Progress", self.asteps, self.ares),
                            h(btn("Open documents (step 6)", lambda: self.nav.setCurrentRow(5), "blue"), stretch=True))
        self.set_page(sa)
        self.update_autopilot()

    def autopilot(self):
        j = self.run("autopilot", {"dataset": self.ads.text(), "quality": self.aq.currentText(), "hours": self.ah.value() or None,
                                   "aerial": self.aaer.isChecked(), "rknn": self.arknn.isChecked(), "arch": self.aarch.currentData()},
                     lambda jj: None)
        if j:
            self.auto_job = j.id

    def update_autopilot(self):
        if not getattr(self, "auto_job", None) or not hasattr(self, "asteps"):
            return
        j = self.B.JOBS.get(self.auto_job)
        try:
            if j is None or not self.asteps.isVisible():
                return
        except RuntimeError:
            return
        steps, k = j.result.get("steps", []), j.result.get("step", 0)
        self.asteps.clear()
        for i, s in enumerate(steps):
            mark = "✔ " if i < k else ("▶ " if i == k and j.status == "running" else "   ")
            it = QListWidgetItem(mark + s)
            it.setForeground(QColor("#52d18a" if i < k else ("#e9c46a" if i == k and j.status == "running" else "#8b9bab")))
            self.asteps.addItem(it)
        if j.status == "done":
            self.ares.setText("<h3 style='color:#52d18a'>✅ Solution complete - see step 6 (Documents)</h3>")
        elif j.status == "failed":
            self.ares.setText("<h3 style='color:#ff6b6b'>❌ Stopped - see the log below</h3>")

    # ------------------------------------------------------------------ 9 help
    def page_help(self):
        txt = QLabel("<ol><li><b>Step 1</b>: click the case they gave you (or describe a NEW problem statement).</li>"
                     "<li><b>Step 2</b>: choose their dataset → <b>Train</b>. No dataset? Fly once (frames are saved), extract frames, auto-label, fix in the labelling tool, train.</li>"
                     "<li><b>Step 3</b>: measure the field → area / towers / altitude.</li><li><b>Step 4</b>: simulation test.</li>"
                     "<li><b>Step 5</b>: economics numbers → calculate.</li><li><b>Step 6</b>: documents + presentation.</li>"
                     "<li><b>Step 7</b>: deploy and fly; copy results back; regenerate documents.</li></ol>"
                     "<p>Or after step 1 (and 3) press <b>⚡ AUTOPILOT</b>.</p>")
        txt.setWordWrap(True)
        envw = group("Environment", QLabel("%s %s  ·  toolkit version %s\nToolkit folder:  %s\nPython used for the work:  %s" % (
                         APP_NAME, APP_VERSION, self.toolkit_version, self.root, self.B.PY)),
                     h(btn("Install AI environment (offline)", self.install_env, "blue"), btn("Change toolkit folder…", self.change_root, "ghost"), stretch=True))
        sa, v = scroll_page(title("Help & self-test"),
                            group("Self-test", h(btn("Run self-test (no training, a few minutes)", lambda: self.run("selftest", {}), "green"), stretch=True),
                                  QLabel("Should end with  '... passed, 0 failed'.")),
                            group("Typical flow at the venue", txt), envw,
                            group("Manuals (offline)", h(btn("Toolkit manual", lambda: self.open_file("README.md")),
                                                         btn("TECHNIC 6S documentation", lambda: self.open_file(os.path.join("offline", "docs", "docs.skyris.ru", "technic6S", "index.html"))), stretch=True)))
        self.set_page(sa)

    def install_env(self):
        if sys.platform.startswith("win"):
            self.B.open_terminal(r"setup\setup_windows.bat")
        else:
            self.B.open_terminal("bash setup/install_laptop.sh")

    def change_root(self):
        d = QFileDialog.getExistingDirectory(self, "Choose the brics_toolkit folder", self.root)
        if d and is_toolkit(d):
            QSettings("BRICS", "MissionStudio").setValue("root", d)
            QMessageBox.information(self, APP_NAME, "Saved. Restart the app.")
        elif d:
            QMessageBox.warning(self, APP_NAME, "That folder is not the toolkit (studio/cases.py missing).")


# ============================================================================ style + main
STYLE = """
QWidget{background:#0f1720;color:#e6edf3;font-size:14px}
#top{background:#1d3557} #top QLabel{background:transparent} #logo{font-size:20px;font-weight:bold} #proj{color:#cfe3f5}
#banner{background:#7a2e00;color:#fff;padding:8px 14px;font-weight:bold}
#nav{background:#17212b;border:0;font-size:15px;padding-top:8px} #nav::item{padding:12px 16px;color:#9fb0c0;border-left:3px solid transparent}
#nav::item:selected{background:#1f2b38;color:#fff;border-left:3px solid #2a9d8f}
#h1{font-size:23px;font-weight:bold;background:transparent} #sub{color:#8b9bab;background:transparent}
QGroupBox{background:#17212b;border:1px solid #243444;border-radius:9px;margin-top:16px;padding:14px 12px 10px 12px;font-weight:bold}
QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 6px;color:#cfe3f5}
QGroupBox QLabel{background:transparent;font-weight:normal;color:#9fb0c0}
QPushButton{background:#457b9d;color:#fff;border:0;border-radius:6px;padding:8px 14px}
QPushButton:hover{background:#5a92b4} QPushButton:disabled{background:#2c3e50;color:#6b7b8b}
QPushButton[kind="green"]{background:#2a9d8f} QPushButton[kind="green"]:hover{background:#33b5a5}
QPushButton[kind="yellow"]{background:#e9c46a;color:#000;font-weight:bold} QPushButton[kind="yellow"]:hover{background:#f4d58d}
QPushButton[kind="ghost"]{background:transparent;border:1px solid #456} QPushButton[kind="ghost"]:hover{background:#1f2b38}
QPushButton[big="true"]{font-size:16px;font-weight:bold;padding:10px 22px}
#casecard{background:#1f2b38;border:2px solid #2d3d4d;border-radius:10px}
#casecard:hover{border-color:#5a7a9a} #casecard[sel="true"]{border-color:#2a9d8f;background:#1d3a3a}
#casecard QLabel{background:transparent} #cardhead{font-size:16px;font-weight:bold;color:#fff} #cardbody{color:#b8c6d4;font-size:13px} #cardfoot{color:#8ecae6;font-size:12px}
#row,QCheckBox{background:transparent}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QPlainTextEdit,QTextBrowser,QListWidget,QTableWidget{background:#0b1118;border:1px solid #2d3d4d;border-radius:6px;padding:6px;selection-background-color:#2a9d8f}
QHeaderView::section{background:#1f2b38;color:#cfe3f5;border:0;padding:6px}
QTableWidget{gridline-color:#243444}
#console{background:#05090d} #console QLabel{background:transparent}
#log{background:#05090d;color:#b9d4ea;font-family:Menlo,Consolas,monospace;font-size:12px;border:0}
QScrollArea{border:0}
QSplitter::handle{background:#234}
"""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in ((QPalette.Window, "#0f1720"), (QPalette.WindowText, "#e6edf3"), (QPalette.Base, "#0b1118"),
                      (QPalette.Text, "#e6edf3"), (QPalette.Button, "#1f2b38"), (QPalette.ButtonText, "#e6edf3"),
                      (QPalette.Highlight, "#2a9d8f"), (QPalette.ToolTipBase, "#1f2b38"), (QPalette.ToolTipText, "#e6edf3")):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
    icon = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "icon.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    settings = QSettings("BRICS", "MissionStudio")
    root = find_toolkit(settings)
    while not root:
        QMessageBox.information(None, APP_NAME, "Please choose the 'brics_toolkit' folder (the one with studio/, drone/, train/ …).")
        d = QFileDialog.getExistingDirectory(None, "Choose the brics_toolkit folder", os.path.expanduser("~"))
        if not d:
            return 0
        if is_toolkit(d):
            root = d
            settings.setValue("root", d)
    os.environ["BRICS_ROOT"] = root
    sys.path.insert(0, root)
    from studio import studio as backend          # loaded from the toolkit folder
    w = Studio(backend, root)
    w.show()
    if os.environ.get("BRICS_SCREENSHOT"):         # for automated visual checks
        def snap():
            for i in [int(x) for x in os.environ.get("BRICS_SCREENSHOT_PAGES", "0").split(",")]:
                w.nav.setCurrentRow(i)
                app.processEvents()
                w.grab().save(os.environ["BRICS_SCREENSHOT"].replace(".png", "_%d.png" % i))
            app.quit()
        QTimer.singleShot(1200, snap)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
