"""Module C economic model: every number and chart in main.tex comes from this file.

Run:  python3 econ_model.py   (needs matplotlib)
Writes figures/fig_*.png and evidence_numbers.txt.
Base-case inputs are the team model economics/case1_fire.yaml (also shown in the dashboard Economics page);
this script adds the bottom-up resource bill, the option comparison on one scope, scenarios and sensitivity.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)

# ---------------------------------------------------------------- inputs (RUB, nominal)
USD, EUR = 82.7536, 92.3944          # CBR official rates, 10 Nov 2026
YEARS, RATE, OPEX_G = 5, 0.18, 0.07  # horizon, discount rate (key rate 14 % + 4 pp risk), OPEX escalation
RAMP = [0.6] + [1.0] * (YEARS - 1)   # share of benefits realised per year
RESIDUAL = 300_000                   # year-5 resale of 2 UAVs + ground kit

AIR_H, AIR_RATE = 60, 60_000         # baseline manned patrol hours / year, RUB per flight hour
AIR_SHARE = 0.5                      # share of patrol hours the UAV takes over
GROUND_TRIPS, TRIP_COST = 100, 8_000 # baseline ground-crew verification trips / year, RUB per trip
GROUND_SHARE = 0.5                   # share of trips replaced by UAV verification
FIRES, HA, RUB_HA = 2, 10, 150_000   # early detections / yr, ha saved per detection, damage RUB/ha

CAPEX = {"K1": 1_800_000, "K2": 1_200_000, "K3": 300_000, "K4": 200_000}
OPEX = {"O1": 900_000, "O2": 350_000, "O3": 150_000}

# K1 per-UAV breakdown (field version of the Module A prototype). Sourced items converted at CBR rates.
OPI5PRO = 216.99 * USD               # Orange Pi 5 Pro 8 GB, Amazon US (pricehistory.app)
TR256I = 218.99 * EUR                # Mileseey TR256i, AiO.lv
K1_UNIT = {"a": OPI5PRO + TR256I, "b": 50_000 - OPI5PRO - TR256I, "c": 450_000, "d": 150_000,
           "e": 120_000, "f": 130_000}
assert round(sum(K1_UNIT.values())) * 2 == CAPEX["K1"]

# Option B - COTS enterprise thermal drone, manual piloting, human video review (same scope)
M3T = 6_809 * USD                    # DJI Mavic 3T, Global Drone HQ list price
CAPEX_B = {"B1": 2 * M3T, "B2": 250_000, "B3": 150_000, "B4": 300_000, "B5": 200_000}
OPEX_B = {"P1": 1_800_000, "P2": 250_000, "P3": 150_000}


def npv(r, cfs):
    return sum(cf / (1 + r) ** t for t, cf in enumerate(cfs))


def irr(cfs, lo=-0.99, hi=10.0):
    if npv(lo, cfs) * npv(hi, cfs) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo, cfs) * npv(mid, cfs) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def payback(cfs, r=None):
    cum = cfs[0]
    for t in range(1, len(cfs)):
        cf = cfs[t] / (1 + r) ** t if r is not None else cfs[t]
        if cf > 0 and cum + cf >= 0:
            return t - 1 + (-cum) / cf
        cum += cf
    return None   # not paid back within the horizon


def benefits(air_h=AIR_H, air_rate=AIR_RATE, air_share=AIR_SHARE, fires=FIRES, rub_ha=RUB_HA, damage=True):
    b = {"S1": air_h * air_rate * air_share,
         "S2": GROUND_TRIPS * TRIP_COST * GROUND_SHARE,
         "S3": fires * HA * rub_ha if damage else 0.0}
    return b


def model(capex_k=1.0, opex_k=1.0, ben_k=1.0, rate=RATE, residual=RESIDUAL, **bkw):
    K = sum(CAPEX.values()) * capex_k
    O1 = sum(OPEX.values()) * opex_k
    B = sum(benefits(**bkw).values()) * ben_k
    cfs, rows = [-K], []
    for t in range(1, YEARS + 1):
        b, o = B * RAMP[t - 1], O1 * (1 + OPEX_G) ** (t - 1)
        s = residual if t == YEARS else 0
        cfs.append(b - o + s)
        rows.append((t, b, o, s, b - o + s, (b - o + s) / (1 + rate) ** t))
    n = npv(rate, cfs)
    return {"K": K, "O1": O1, "B": B, "cfs": cfs, "rows": rows, "npv": n, "irr": irr(cfs),
            "pb": payback(cfs), "dpb": payback(cfs, rate), "roi": (sum(cfs[1:]) - K) / K,
            "pi": (n + K) / K}


# ---------------------------------------------------------------- same-scope cost of ownership
def tco(capex, opex1, residual, replaced=True, rate=RATE):
    """5-year cost of delivering the same district service: own CAPEX/OPEX plus the patrol services still bought.
    The UAV takes over AIR_SHARE / GROUND_SHARE of the work with the same year-1 ramp as the benefit model."""
    own, svc, yearly = [], [], []
    for t in range(1, YEARS + 1):
        k = RAMP[t - 1] if replaced else 0.0
        own.append(opex1 * (1 + OPEX_G) ** (t - 1))
        svc.append(AIR0 * (1 - AIR_SHARE * k) + GROUND0 * (1 - GROUND_SHARE * k))
        yearly.append(own[-1] + svc[-1] - (residual if t == YEARS else 0))
    return {"capex": capex, "own_opex": sum(own), "services": sum(svc), "residual": residual,
            "total": capex + sum(yearly), "pv": capex + sum(c / (1 + rate) ** t for t, c in enumerate(yearly, 1)),
            "yearly": yearly}


AIR0, GROUND0 = AIR_H * AIR_RATE, GROUND_TRIPS * TRIP_COST
opt0 = tco(0, 0, 0, replaced=False)
optA = tco(sum(CAPEX.values()), sum(OPEX.values()), RESIDUAL)
optB = tco(sum(CAPEX_B.values()), sum(OPEX_B.values()), 0.1 * 2 * M3T)   # resale 10 % of drone price

base = model()
cash = model(damage=False)
scen = [("Base case (team model)", {}),
        ("S-1 Cash savings only (no avoided damage)", {"damage": False}),
        ("S-2 One early detection per year", {"fires": 1}),
        ("S-3 Three early detections per year", {"fires": 3}),
        ("All benefits $-30\\,\\%$", {"ben_k": 0.7}),
        ("OPEX $+30\\,\\%$", {"opex_k": 1.3}),
        ("CAPEX $+30\\,\\%$", {"capex_k": 1.3}),
        ("Discount rate 23\\,\\% (+5 pp)", {"rate": RATE + 0.05})]
def breakeven(f, lo=0.0, hi=20.0):
    for _ in range(100):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return hi


be_fires = breakeven(lambda x: model(fires=x)["npv"])
be_hours = breakeven(lambda h: model(damage=False, air_h=h)["npv"], 0, 1000)
be_ben = breakeven(lambda k: model(ben_k=k)["npv"], 0, 3)

# sensitivity (+-20 % on one parameter at a time)
tor = []
for name, lo_kw, hi_kw in [
        ("Avoided fire damage (3.0 M RUB/yr)", {"fires": FIRES * 0.8}, {"fires": FIRES * 1.2}),
        ("Aircraft patrol saving (1.8 M RUB/yr)", {"air_rate": AIR_RATE * 0.8}, {"air_rate": AIR_RATE * 1.2}),
        ("Operating cost (1.40 M RUB/yr)", {"opex_k": 1.2}, {"opex_k": 0.8}),
        ("Capital cost (3.50 M RUB)", {"capex_k": 1.2}, {"capex_k": 0.8}),
        ("Discount rate (18 %)", {"rate": RATE * 1.2}, {"rate": RATE * 0.8})]:
    tor.append((name, model(**lo_kw)["npv"], model(**hi_kw)["npv"]))

# scale-up: N districts, software K2 paid once, everything else per district
def region(n):
    K = n * (sum(CAPEX.values()) - CAPEX["K2"]) + CAPEX["K2"]
    O1, B = n * sum(OPEX.values()), n * base["B"]
    cfs = [-K] + [B * RAMP[t - 1] - O1 * (1 + OPEX_G) ** (t - 1) + (n * RESIDUAL if t == YEARS else 0)
                  for t in range(1, YEARS + 1)]
    cfs_c = [-K] + [n * cash["B"] * RAMP[t - 1] - O1 * (1 + OPEX_G) ** (t - 1) + (n * RESIDUAL if t == YEARS else 0)
                    for t in range(1, YEARS + 1)]
    return {"K": K, "npv": npv(RATE, cfs), "irr": irr(cfs), "pb": payback(cfs), "npv_cash": npv(RATE, cfs_c),
            "pb_cash": payback(cfs_c)}

# software-only retrofit: customer already owns PX4 multirotors; buys payload kit + integration + our software
RETRO_K = 2 * (K1_UNIT["a"] + K1_UNIT["b"] + K1_UNIT["f"]) + CAPEX["K2"] + CAPEX["K3"] + CAPEX["K4"]
retro = model(capex_k=RETRO_K / sum(CAPEX.values()))
retro_cash = model(capex_k=RETRO_K / sum(CAPEX.values()), damage=False)

# ---------------------------------------------------------------- self-checks
assert round(base["npv"]) == 6_205_125, base["npv"]          # matches economics/out/case1_fire.md
assert abs(npv(base["irr"], base["cfs"])) < 1
assert round(base["K"]) == 3_500_000 and round(base["O1"]) == 1_400_000 and round(base["B"]) == 5_200_000
assert optA["total"] < optB["total"]
assert abs((opt0["pv"] - optA["pv"]) - cash["npv"]) < 1   # cost comparison and cash-only NPV are the same calculation

# ---------------------------------------------------------------- evidence numbers
def f(v):
    return "n/a" if v is None else "{:,.0f}".format(v)


def p(v):
    return "n/a" if v is None else "%.1f %%" % (100 * v)


def y(v):
    return "not within 5 years" if v is None else "%.2f years" % v


L = ["BASE", "capex %s opex1 %s benefits %s" % (f(base["K"]), f(base["O1"]), f(base["B"])),
     "benefit items %s" % {k: f(v) for k, v in benefits().items()}]
for r in base["rows"]:
    L.append("year %d benefit %s opex %s resid %s cf %s dcf %s" % (r[0], f(r[1]), f(r[2]), f(r[3]), f(r[4]), f(r[5])))
cum = dcum = -base["K"]
for r in base["rows"]:
    cum += r[4]; dcum += r[5]
    L.append("  cumulative y%d %s discounted %s" % (r[0], f(cum), f(dcum)))
L += ["K1 per UAV %s (orange pi %s, tr256i %s)" % ({k: f(v) for k, v in K1_UNIT.items()}, f(OPI5PRO), f(TR256I))]
L += ["npv %s irr %s pb %s dpb %s roi %s pi %.2f" % (f(base["npv"]), p(base["irr"]), y(base["pb"]), y(base["dpb"]),
                                                    p(base["roi"]), base["pi"]),
      "breakeven fires/yr %.2f  breakeven benefit level %s  cash-only breakeven patrol hours/yr %.1f" % (be_fires, p(be_ben), be_hours), "", "CASH-ONLY"]
for r in cash["rows"]:
    L.append("year %d benefit %s opex %s cf %s" % (r[0], f(r[1]), f(r[2]), f(r[4])))
L += ["npv %s irr %s pb %s roi %s" % (f(cash["npv"]), p(cash["irr"]), y(cash["pb"]), p(cash["roi"])), "", "SCENARIOS"]
scen_rows = []
for name, kw in scen:
    m = model(**kw)
    scen_rows.append((name, m["npv"], m["irr"], m["pb"], m["dpb"]))
    L.append("%s | %s | %s | %s | %s" % (name, f(m["npv"]), p(m["irr"]), y(m["pb"]), y(m["dpb"])))
L += ["", "TORNADO"] + ["%s lo %s hi %s" % (n, f(a), f(b)) for n, a, b in tor]
L += ["", "TCO (5 yr, nominal / PV@18%)"]
for nm, o in (("Baseline", opt0), ("Option A ours", optA), ("Option B COTS", optB)):
    L.append("%s capex %s own_opex %s services %s resale %s total %s pv %s" % (
        nm, f(o["capex"]), f(o["own_opex"]), f(o["services"]), f(o["residual"]), f(o["total"]), f(o["pv"])))
    L.append("   yearly " + " ".join(f(c) for c in o["yearly"]))
L += ["saving A vs baseline %s (%s) pv %s" % (f(opt0["total"] - optA["total"]),
                                             p(1 - optA["total"] / opt0["total"]), f(opt0["pv"] - optA["pv"])),
      "saving B vs baseline %s (%s)" % (f(opt0["total"] - optB["total"]), p(1 - optB["total"] / opt0["total"])),
      "A vs B %s (%s)" % (f(optB["total"] - optA["total"]), p(1 - optA["total"] / optB["total"])),
      "optB capex %s  m3t unit %s  opexB %s" % (f(sum(CAPEX_B.values())), f(M3T), f(sum(OPEX_B.values()))),
      "", "RETROFIT capex %s npv %s irr %s pb %s | cash-only npv %s irr %s pb %s" % (
          f(RETRO_K), f(retro["npv"]), p(retro["irr"]), y(retro["pb"]), f(retro_cash["npv"]), p(retro_cash["irr"]), y(retro_cash["pb"])),
      "", "REGION"]
for n in (1, 3, 10):
    g = region(n)
    L.append("districts %d capex %s npv %s irr %s pb %s | cash-only npv %s pb %s" % (
        n, f(g["K"]), f(g["npv"]), p(g["irr"]), y(g["pb"]), f(g["npv_cash"]), y(g["pb_cash"])))
open(os.path.join(HERE, "evidence_numbers.txt"), "w").write("\n".join(L) + "\n")
print("\n".join(L))

# ---------------------------------------------------------------- figures (print, light surface)
BLUE, ORANGE, AQUA, YELLOW, GREY, INK, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8f8e88", "#0b0b0b", "#52514e"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": "#c9c8c2", "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#ecebe7", "grid.linewidth": 0.8, "axes.axisbelow": True})
M = 1e6

# 1. cash flow + cumulative
fig, ax = plt.subplots(figsize=(7.2, 3.2))
yrs_ = list(range(YEARS + 1))
ax.bar(yrs_, [c / M for c in base["cfs"]], width=0.55, color=BLUE, alpha=0.85, label="Net cash flow of the year")
cum, dcum, cs, ds = 0, 0, [], []
for t, c in enumerate(base["cfs"]):
    cum += c; dcum += c / (1 + RATE) ** t
    cs.append(cum / M); ds.append(dcum / M)
ax.plot(yrs_, cs, color=ORANGE, lw=2, marker="o", ms=5, label="Cumulative (simple)")
ax.plot(yrs_, ds, color=AQUA, lw=2, marker="s", ms=5, label="Cumulative (discounted, 18 %)")
ax.axhline(0, color=MUTED, lw=0.8)
for xv, lab, col in ((base["pb"], "simple payback %.2f yr" % base["pb"], ORANGE),
                     (base["dpb"], "discounted %.2f yr" % base["dpb"], AQUA)):
    ax.axvline(xv, color=col, lw=1, ls="--")
ax.text(base["pb"] - 0.05, 9.5, "payback\n%.2f yr" % base["pb"], ha="right", va="top", fontsize=8, color=INK)
ax.text(base["dpb"] + 0.05, 9.5, "discounted\n%.2f yr" % base["dpb"], ha="left", va="top", fontsize=8, color=INK)
ax.text(YEARS, ds[-1] - 0.5, "NPV %.2f M" % (base["npv"] / M), ha="center", va="top", fontsize=8, color=INK)
ax.set_xticks(yrs_); ax.set_xlabel("Year"); ax.set_ylabel("million RUB")
ax.legend(frameon=False, fontsize=8, loc="upper left")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_cashflow.png"), dpi=200); plt.close(fig)

# 2. TCO by option (stacked horizontal)
fig, ax = plt.subplots(figsize=(7.2, 2.6))
names = ["Baseline: aircraft +\nground patrol", "Option B: COTS thermal\ndrone, manual review", "Option A: autonomous\nNPU UAV (this project)"]
opts = [opt0, optB, optA]
for o in opts:
    o["capnet"] = o["capex"] - o["residual"]
parts = [("Capital (net of year-5 resale)", "capnet", BLUE), ("Own operating cost", "own_opex", AQUA),
         ("Remaining patrol services", "services", YELLOW)]
left = [0, 0, 0]
for lab, key, col in parts:
    vals = [o[key] / M for o in opts]
    ax.barh(names, vals, left=left, color=col, edgecolor="white", linewidth=2, height=0.55, label=lab)
    left = [a + b for a, b in zip(left, vals)]
for i, o in enumerate(opts):
    ax.text(o["total"] / M + 0.2, i, "%.2f M" % (o["total"] / M), va="center", fontsize=8, color=INK)
ax.set_xlabel("5-year cost of the same district service, million RUB (nominal)")
ax.set_xlim(0, max(o["total"] for o in opts) / M * 1.15)
ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.3))
ax.grid(axis="y", visible=False)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_tco.png"), dpi=200); plt.close(fig)

# 3. tornado
tor_s = sorted(tor, key=lambda r: abs(r[2] - r[1]))
fig, ax = plt.subplots(figsize=(7.2, 3.3))
for i, (n, lo, hi) in enumerate(tor_s):
    ax.barh(i, (lo - base["npv"]) / M, left=base["npv"] / M, color=ORANGE, height=0.55)
    ax.barh(i, (hi - base["npv"]) / M, left=base["npv"] / M, color=BLUE, height=0.55)
    ax.text(min(lo, hi) / M - 0.08, i, "%.2f" % (min(lo, hi) / M), ha="right", va="center", fontsize=7.5, color=INK)
    ax.text(max(lo, hi) / M + 0.08, i, "%.2f" % (max(lo, hi) / M), ha="left", va="center", fontsize=7.5, color=INK)
ax.axvline(base["npv"] / M, color=INK, lw=1)
ax.set_yticks(range(len(tor_s))); ax.set_yticklabels([r[0] for r in tor_s])
ax.set_xlabel("NPV at 18 %, million RUB")
ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=ORANGE), plt.Rectangle((0, 0), 1, 1, color=BLUE)],
          labels=["parameter 20 % worse", "parameter 20 % better"], frameon=False, fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.22))
ax.set_xlim(base["npv"] / M - 2.2, base["npv"] / M + 2.2)
ax.grid(axis="y", visible=False)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_tornado.png"), dpi=200); plt.close(fig)

# 4. NPV vs early detections per year
fig, ax = plt.subplots(figsize=(7.2, 2.8))
xs = [i / 10 for i in range(0, 41)]
ax.plot(xs, [model(fires=x)["npv"] / M for x in xs], color=BLUE, lw=2)
ax.axhline(0, color=MUTED, lw=0.8)
ax.axvline(be_fires, color=ORANGE, lw=1, ls="--")
ax.plot([FIRES], [base["npv"] / M], "o", color=BLUE, ms=7, mec="white", mew=2)
ax.text(FIRES + 0.08, base["npv"] / M - 0.3, "base case: 2 / yr\nNPV %.2f M" % (base["npv"] / M), fontsize=8, va="top")
ax.text(be_fires + 0.08, 1.2, "break-even\n%.2f / yr" % be_fires, fontsize=8, color=INK)
ax.set_xlabel("Fires detected early per year (each saves 10 ha x 150 000 RUB/ha)")
ax.set_ylabel("NPV at 18 %, million RUB")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_breakeven.png"), dpi=200); plt.close(fig)

# 5. CAPEX and OPEX breakdown (two panels, one axis each)
fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 2.3), gridspec_kw={"width_ratios": [1.15, 1]})
for ax, items, title, col in ((a1, [("UAVs + payload (K1)", CAPEX["K1"]), ("Software (K2)", CAPEX["K2"]),
                                    ("Ground kit (K3)", CAPEX["K3"]), ("Training (K4)", CAPEX["K4"])], "CAPEX 3.50 M RUB (once)", BLUE),
                              (a2, [("Operator 0.5 FTE (O1)", OPEX["O1"]), ("Maintenance (O2)", OPEX["O2"]),
                                    ("Insurance, reg. (O3)", OPEX["O3"])], "OPEX 1.40 M RUB / year", AQUA)):
    names_ = [i[0] for i in items][::-1]; vals = [i[1] / M for i in items][::-1]
    ax.barh(names_, vals, color=col, height=0.6)
    for i, v in enumerate(vals):
        ax.text(v + 0.03, i, "%.2f" % v, va="center", fontsize=8, color=INK)
    ax.set_title(title, fontsize=9, loc="left", color=INK); ax.set_xlim(0, max(vals) * 1.3)
    ax.grid(axis="y", visible=False); ax.set_xlabel("million RUB")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_capex_opex.png"), dpi=200); plt.close(fig)

# 6. benefits: cash vs avoided damage
fig, ax = plt.subplots(figsize=(7.2, 1.9))
bi = benefits()
items = [("Avoided fire damage (S3)", bi["S3"], ORANGE), ("Fewer patrol flights (S1)", bi["S1"], BLUE),
         ("Fewer ground trips (S2)", bi["S2"], BLUE)][::-1]
ax.barh([i[0] for i in items], [i[1] / M for i in items], color=[i[2] for i in items], height=0.6)
for k, it in enumerate(items):
    ax.text(it[1] / M + 0.04, k, "%.2f M  (%.0f %%)" % (it[1] / M, 100 * it[1] / base["B"]), va="center", fontsize=8)
ax.set_xlim(0, 4); ax.set_xlabel("million RUB per year (full year)"); ax.grid(axis="y", visible=False)
ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=BLUE), plt.Rectangle((0, 0), 1, 1, color=ORANGE)],
          labels=["cash saving", "economic benefit (forest not burned)"], frameon=False, fontsize=8, loc="lower right")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_benefits.png"), dpi=200); plt.close(fig)

# 7. scenarios NPV
fig, ax = plt.subplots(figsize=(7.2, 2.9))
sr = [(n.replace("$-30\\,\\%$", "-30 %").replace("$+30\\,\\%$", "+30 %").replace("\\,\\%", " %"), v) for n, v, *_ in scen_rows][::-1]
ax.barh([r[0] for r in sr], [r[1] / M for r in sr], color=[BLUE if r[1] > 0 else ORANGE for r in sr], height=0.6)
for k, (n_, v) in enumerate(sr):
    ax.text(v / M + (0.15 if v > 0 else -0.15), k, "%.2f" % (v / M), va="center", ha="left" if v > 0 else "right", fontsize=8)
ax.axvline(0, color=INK, lw=0.8); ax.set_xlim(-4, 12.5); ax.set_xlabel("NPV at 18 %, million RUB")
ax.grid(axis="y", visible=False)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_scenarios.png"), dpi=200); plt.close(fig)

# 8. yearly cost of the same service (residual excluded)
fig, ax = plt.subplots(figsize=(7.2, 2.6))
yy = list(range(1, YEARS + 1))
for o, lab, col, mk in ((opt0, "Baseline: aircraft + ground patrol", GREY, "o"), (optB, "Option B: COTS thermal drone", ORANGE, "s"),
                        (optA, "Option A: this project", BLUE, "D")):
    vals = [(c + (o["residual"] if t == YEARS else 0)) / M for t, c in zip(yy, o["yearly"])]
    ax.plot(yy, vals, color=col, lw=2, marker=mk, ms=6, label=lab)
    ax.text(YEARS + 0.08, vals[-1], "%.2f" % vals[-1], va="center", fontsize=8)
ax.set_xticks(yy); ax.set_xlabel("Year"); ax.set_ylabel("million RUB / year"); ax.set_ylim(3.0, 5.6)
ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.18))
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_annual_cost.png"), dpi=200); plt.close(fig)

# 9. scale-up
fig, ax = plt.subplots(figsize=(7.2, 2.5))
ns = list(range(1, 11))
ax.plot(ns, [region(n)["npv"] / M for n in ns], color=BLUE, lw=2, marker="o", ms=5, label="Base case (with avoided damage)")
ax.plot(ns, [region(n)["npv_cash"] / M for n in ns], color=ORANGE, lw=2, marker="s", ms=5, label="Cash savings only")
ax.axhline(0, color=MUTED, lw=0.8)
for n in (1, 3, 10):
    ax.text(n, region(n)["npv"] / M + 3, "%.1f" % (region(n)["npv"] / M), ha="center", fontsize=8)
ax.set_xticks(ns); ax.set_xlabel("Districts (software developed once)"); ax.set_ylabel("NPV, million RUB")
ax.set_ylim(-15, 85); ax.legend(frameon=False, fontsize=8, loc="upper left")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_region.png"), dpi=200); plt.close(fig)

# 10. what one UAV costs (stacked single bar)
MAG = "#e87ba4"
fig, ax = plt.subplots(figsize=(7.2, 0.9))
segs = [("Payload kit: Orange Pi + TR256i + RGB + rangefinder", K1_UNIT["a"] + K1_UNIT["b"], ORANGE),
        ("Stock airframe + PX4 + GNSS", K1_UNIT["c"], BLUE), ("Long-range link + RC", K1_UNIT["d"], AQUA),
        ("Batteries + charger", K1_UNIT["e"], YELLOW), ("Assembly + acceptance", K1_UNIT["f"], MAG)]
left = 0
for lab, v, col in segs:
    ax.barh([0], [v / 1000], left=left, color=col, edgecolor="white", linewidth=2, height=0.5, label="%s  %.0f k" % (lab, v / 1000))
    left += v / 1000
ax.set_yticks([]); ax.set_xlim(0, 900); ax.set_xlabel("thousand RUB per UAV (total 900 k)"); ax.grid(axis="y", visible=False)
ax.legend(frameon=False, fontsize=7, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -1.0))
fig.savefig(os.path.join(FIG, "fig_uav_cost.png"), dpi=200, bbox_inches="tight"); plt.close(fig)
print("figures written to", FIG)
