"""Toolkit version (single source of truth: the VERSION file in the toolkit root). Python 3.8 compatible."""
import os

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BUILD = 2          # bump with every release that is handed out (also used as CFBundleVersion of the .app)


def _read():
    try:
        with open(os.path.join(_ROOT, "VERSION")) as f:
            return f.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


__version__ = _read()
