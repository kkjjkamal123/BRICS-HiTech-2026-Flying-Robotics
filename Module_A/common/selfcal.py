"""
Self-calibration of a downward camera from its own detections (pure maths, no ROS).

Problem on the real drone: the thermal camera's mounting direction and field of view are not known exactly. With a
wrong value, the same fire is projected to a different floor position in every frame, smeared along the flight
path (a camera turned 180 deg doubles the error instead of cancelling it).

Idea: a fire does not move. For the RIGHT camera orientation and lens scale all its views land on one point; for a
wrong one they smear. So we try the four possible mounting rotations (0 / 90 / 180 / 270 deg), solve the best lens
scale for each in closed form, and keep the combination whose views agree best - but only when the evidence is
clear, otherwise nothing changes.

An observation is (drone x, drone y, yaw, height above the floor, fwd0, left0, weight), where fwd0 / left0 are the
object's direction in the picture under the configured mounting (image up = drone forward), per metre of height.
"""
import math

ROTATIONS = [("as configured", ((1.0, 0.0), (0.0, 1.0))),
             ("turned 90 deg left", ((0.0, -1.0), (1.0, 0.0))),
             ("turned 180 deg", ((-1.0, 0.0), (0.0, -1.0))),
             ("turned 90 deg right", ((0.0, 1.0), (-1.0, 0.0)))]
IDENTITY = (ROTATIONS[0][1], 1.0)


def project(obs, M, scale):
    """Floor position of one observation under mounting rotation M and lens scale."""
    ax, ay, yaw, hgt, f0, l0 = obs[:6]
    fwd = (M[0][0] * f0 + M[0][1] * l0) * scale * hgt
    left = (M[1][0] * f0 + M[1][1] * l0) * scale * hgt
    c, s = math.cos(yaw), math.sin(yaw)
    return ax + c * fwd - s * left, ay + s * fwd + c * left


def _spread(groups, M, scale=None):
    """Weighted squared spread of the projected views, summed over objects. scale=None -> also solve the best
    lens scale (closed form: the spread is quadratic in it). Returns (spread, scale)."""
    centred = []
    for obs in groups:
        w = [o[6] for o in obs]
        sw = sum(w)
        a, b = [], []
        for o in obs:
            a.append((o[0], o[1]))
            bx, by = project((0.0, 0.0) + tuple(o[2:6]), M, 1.0)
            b.append((bx, by))
        am = (sum(wi * p[0] for wi, p in zip(w, a)) / sw, sum(wi * p[1] for wi, p in zip(w, a)) / sw)
        bm = (sum(wi * p[0] for wi, p in zip(w, b)) / sw, sum(wi * p[1] for wi, p in zip(w, b)) / sw)
        for wi, pa, pb in zip(w, a, b):
            centred.append((wi, pa[0] - am[0], pa[1] - am[1], pb[0] - bm[0], pb[1] - bm[1]))
    if scale is None:
        ab = sum(w * (ax * bx + ay * by) for w, ax, ay, bx, by in centred)
        bb = sum(w * (bx * bx + by * by) for w, ax, ay, bx, by in centred)
        scale = min(2.0, max(0.5, -ab / bb)) if bb > 1e-9 else 1.0
    v = sum(w * ((ax + scale * bx) ** 2 + (ay + scale * by) ** 2) for w, ax, ay, bx, by in centred)
    return v, scale


def solve(groups, current=IDENTITY, min_obs=12, min_travel=0.5):
    """
    groups: one list of observations per physical object seen by this camera.
    Returns (M, scale, text) for a clearly better calibration than `current`, or None to keep `current`.
    """
    good = []
    for obs in groups:
        if len(obs) < min_obs:
            continue
        xs, ys = [o[0] for o in obs], [o[1] for o in obs]
        if math.hypot(max(xs) - min(xs), max(ys) - min(ys)) < min_travel:
            continue                                   # the drone did not move: every hypothesis looks the same
        good.append(obs)
    if not good:
        return None
    sw = sum(o[6] for obs in good for o in obs)
    v_now, _ = _spread(good, current[0], current[1])
    rms_now = math.sqrt(v_now / sw)
    best = None
    for name, M in ROTATIONS:
        v, s = _spread(good, M)
        if best is None or v < best[0]:
            best = (v, M, s, name)
    v, M, s, name = best
    rms = math.sqrt(v / sw)
    same = (M == current[0]) and abs(s - current[1]) < 0.08
    if same or rms_now < 0.08 or rms > 0.6 * rms_now:
        return None                                    # already consistent, or no clearly better explanation
    return M, s, "camera %s, lens scale x%.2f: views of the same object now agree to %.2f m (were %.2f m)" % (name, s, rms, rms_now)


def weighted_position(obs, M, scale):
    sw = sum(o[6] for o in obs)
    pts = [project(o, M, scale) for o in obs]
    return (sum(o[6] * p[0] for o, p in zip(obs, pts)) / sw, sum(o[6] * p[1] for o, p in zip(obs, pts)) / sw)
