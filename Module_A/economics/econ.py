#!/usr/bin/env python3
"""
econ.py - Module C economic efficiency in one command.

  python economics/econ.py economics/case1_fire.yaml
  -> economics/out/case1_fire.md    (tables for the report / slides)
     economics/out/case1_fire.xlsx  (live Excel formulas: NPV(), IRR(), payback - opens in Excel/Numbers)
     economics/out/case1_fire.csv

Computes: CAPEX, yearly OPEX/benefits (with growth), net cash flow, cumulative + discounted cash flow,
simple & discounted payback, ROI, NPV, IRR, profitability index, break-even benefit level,
sensitivity table (benefits -30%/-20%/+20%, OPEX +30%, CAPEX +30%, discount rate +5 pp), alternatives.
Edit the YAML numbers (they are ILLUSTRATIVE assumptions) - everything else is automatic.
"""
import os
import sys

import yaml


def npv(rate, cfs):
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cfs))


def irr(cfs, lo=-0.99, hi=10.0):
    f_lo, f_hi = npv(lo, cfs), npv(hi, cfs)
    if f_lo * f_hi > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        f = npv(mid, cfs)
        if f_lo * f <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f
    return (lo + hi) / 2


def payback(cfs, rate=None):
    cum = cfs[0]
    for t in range(1, len(cfs)):
        cf = cfs[t] / ((1 + rate) ** t) if rate is not None else cfs[t]
        if cum + cf >= 0 and cf > 0:
            return t - 1 + (-cum) / cf
        cum += cf
    return None


def model(cfg, benefit_k=1.0, opex_k=1.0, capex_k=1.0, rate_add=0.0):
    years = int(cfg.get("years", 5))
    r = cfg["discount_rate"] + rate_add
    g_b, g_o = cfg.get("benefit_growth", 0.0), cfg.get("opex_growth", 0.0)
    capex = sum(i["amount"] for i in cfg["capex"]) * capex_k
    opex1 = sum(i["amount"] for i in cfg["opex"]) * opex_k
    ben1 = sum(i["amount"] for i in cfg["benefits"]) * benefit_k
    ramp = cfg.get("ramp_up", [1.0])            # e.g. [0.6, 1.0]: 60% of benefits in year 1
    rows, cfs = [], [-capex]
    for t in range(1, years + 1):
        k = ramp[t - 1] if t - 1 < len(ramp) else ramp[-1]
        b = ben1 * k * (1 + g_b) ** (t - 1)
        o = opex1 * (1 + g_o) ** (t - 1)
        resid = cfg.get("residual_value", 0) if t == years else 0
        cf = b - o + resid
        cfs.append(cf)
        rows.append((t, b, o, resid, cf))
    total_net = sum(cfs[1:])
    res = {"capex": capex, "opex1": opex1, "ben1": ben1, "rate": r, "rows": rows, "cfs": cfs,
           "npv": npv(r, cfs), "irr": irr(cfs), "payback": payback(cfs), "dpayback": payback(cfs, r),
           "roi": (total_net - capex) / capex if capex else None,
           "pi": (npv(r, cfs) + capex) / capex if capex else None}
    return res


def breakeven_benefit(cfg):
    lo, hi = 0.0, 10.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if model(cfg, benefit_k=mid)["npv"] > 0:
            hi = mid
        else:
            lo = mid
    return hi


def fmt(v, cur=""):
    if v is None:
        return "n/a"
    return "{:,.0f}{}".format(v, (" " + cur) if cur else "").replace(",", " ")


def pct(v):
    return "n/a" if v is None else "%.1f%%" % (100 * v)


def yrs(v):
    return "not within horizon" if v is None else "%.2f years" % v


def report(cfg, name):
    cur = cfg.get("currency", "RUB")
    m = model(cfg)
    L = ["# Economic efficiency - %s" % cfg.get("title", name), "",
         "**Customer / user:** %s  " % cfg.get("customer", ""),
         "**Purpose:** %s  " % cfg.get("purpose", ""),
         "**Horizon:** %d years, **discount rate:** %s (%s)" % (cfg.get("years", 5), pct(cfg["discount_rate"]), cfg.get("rate_note", "")),
         "", "## 1. Cost and benefit items", "", "| No. | Cost/benefit item | Description | Amount / year | Comment |", "|---|---|---|---|---|"]
    n = 1
    for grp, label in (("capex", "Development / capital cost (one-time)"), ("opex", "Operating expense (per year)"), ("benefits", "Benefit / saving (per year)")):
        for i in cfg[grp]:
            L.append("| %d | %s | %s | %s | %s |" % (n, label, i["item"], fmt(i["amount"], cur), i.get("comment", "")))
            n += 1
    L += ["", "**Totals:** CAPEX %s · OPEX %s/yr · Benefits %s/yr (year-1 basis)" % (fmt(m["capex"], cur), fmt(m["opex1"], cur), fmt(m["ben1"], cur)),
          "", "## 2. Cash flow", "", "| Year | Benefits | OPEX | Net cash flow | Cumulative | Discounted CF | Cum. discounted |", "|---|---|---|---|---|---|---|",
          "| 0 | | | %s | %s | %s | %s |" % (fmt(-m["capex"]), fmt(-m["capex"]), fmt(-m["capex"]), fmt(-m["capex"]))]
    cum, dcum = -m["capex"], -m["capex"]
    for t, b, o, resid, cf in m["rows"]:
        cum += cf
        d = cf / (1 + m["rate"]) ** t
        dcum += d
        L.append("| %d | %s | %s | %s | %s | %s | %s |" % (t, fmt(b), fmt(o), fmt(cf), fmt(cum), fmt(d), fmt(dcum)))
    be = breakeven_benefit(cfg)
    L += ["", "## 3. Efficiency indicators", "", "| Indicator | Value | Meaning |", "|---|---|---|",
          "| Payback period (simple) | **%s** | investment returned |" % yrs(m["payback"]),
          "| Discounted payback | %s | with time value of money |" % yrs(m["dpayback"]),
          "| ROI (%d yr) | **%s** | (total net benefit - investment) / investment |" % (cfg.get("years", 5), pct(m["roi"])),
          "| NPV @ %s | **%s** | > 0 = creates value |" % (pct(m["rate"]), fmt(m["npv"], cur)),
          "| IRR | **%s** | > discount rate = feasible |" % pct(m["irr"]),
          "| Profitability index | %.2f | PV of inflows / investment (>1 good) |" % (m["pi"] or 0),
          "| Break-even benefits | %s of plan | NPV = 0 if benefits fall to this level |" % pct(be),
          "", "## 4. Sensitivity analysis", "", "| Scenario | NPV | IRR | Payback |", "|---|---|---|---|"]
    for label, kw in [("Base case", {}), ("Benefits -30%", {"benefit_k": 0.7}), ("Benefits -20%", {"benefit_k": 0.8}),
                      ("Benefits +20%", {"benefit_k": 1.2}), ("OPEX +30%", {"opex_k": 1.3}), ("CAPEX +30%", {"capex_k": 1.3}),
                      ("Discount rate +5 pp", {"rate_add": 0.05}), ("Worst case (benefits -30%, CAPEX +30%)", {"benefit_k": 0.7, "capex_k": 1.3})]:
        s = model(cfg, **kw)
        L.append("| %s | %s | %s | %s |" % (label, fmt(s["npv"], cur), pct(s["irr"]), yrs(s["payback"])))
    if cfg.get("alternatives"):
        L += ["", "## 5. Comparison with alternatives", "", "| Solution | Cost per year | Notes |", "|---|---|---|"]
        for a in cfg["alternatives"]:
            L.append("| %s | %s | %s |" % (a["name"], fmt(a["annual_cost"], cur), a.get("notes", "")))
        L.append("| **Our UAV system** | %s (+ CAPEX %s once) | %s |" % (fmt(m["opex1"], cur), fmt(m["capex"], cur), cfg.get("our_notes", "")))
    feasible = m["npv"] > 0 and (m["irr"] or 0) > m["rate"]
    L += ["", "## 6. Conclusion", "",
          "The project is **%s**: NPV %s %s 0, IRR %s vs discount rate %s, payback %s." % (
              "ECONOMICALLY FEASIBLE" if feasible else "NOT FEASIBLE under these assumptions", fmt(m["npv"], cur),
              ">" if m["npv"] > 0 else "<=", pct(m["irr"]), pct(m["rate"]), yrs(m["payback"])),
          "It stays feasible as long as benefits are above %s of the plan." % pct(be), ""]
    for k in ("key_factors", "recommendations", "social_effects"):
        if cfg.get(k):
            L.append("**%s:**" % k.replace("_", " ").capitalize())
            L += ["- %s" % x for x in cfg[k]]
            L.append("")
    L.append("*All amounts are assumptions for illustration - replace them with the customer's data.*")
    return "\n".join(L), m


def write_xlsx(cfg, m, path):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        print("(openpyxl not installed - skipping .xlsx)")
        return None
    wb = Workbook()
    ws = wb.active
    ws.title = "Model"
    bold = Font(bold=True)
    fill = PatternFill("solid", fgColor="FFF2CC")
    ws["A1"] = cfg.get("title", "Economic model")
    ws["A1"].font = Font(bold=True, size=14)
    ws["A3"], ws["B3"] = "Discount rate", cfg["discount_rate"]
    ws["A4"], ws["B4"] = "Benefit growth / yr", cfg.get("benefit_growth", 0.0)
    ws["A5"], ws["B5"] = "OPEX growth / yr", cfg.get("opex_growth", 0.0)
    ws["A6"], ws["B6"] = "Horizon (years)", int(cfg.get("years", 5))
    for c in ("B3", "B4", "B5", "B6"):
        ws[c].fill = fill
    r = 8
    sums = {}
    for grp, label in (("capex", "CAPEX (one-time)"), ("opex", "OPEX per year"), ("benefits", "Benefits per year")):
        ws.cell(r, 1, label).font = bold
        r += 1
        first = r
        for i in cfg[grp]:
            ws.cell(r, 1, i["item"])
            ws.cell(r, 2, i["amount"]).fill = fill
            ws.cell(r, 3, i.get("comment", ""))
            r += 1
        ws.cell(r, 1, "Total " + label).font = bold
        ws.cell(r, 2, "=SUM(B%d:B%d)" % (first, r - 1)).font = bold
        sums[grp] = "B%d" % r
        r += 2
    years = int(cfg.get("years", 5))
    ramp = cfg.get("ramp_up", [1.0])
    hdr = r
    for j, h in enumerate(["Year", "Ramp-up", "Benefits", "OPEX", "Residual", "Net cash flow", "Discounted CF", "Cumulative CF"]):
        ws.cell(hdr, 1 + j, h).font = bold
    ws.cell(hdr + 1, 1, 0)
    ws.cell(hdr + 1, 6, "=-%s" % sums["capex"])
    ws.cell(hdr + 1, 7, "=F%d" % (hdr + 1))
    ws.cell(hdr + 1, 8, "=F%d" % (hdr + 1))
    for t in range(1, years + 1):
        rr = hdr + 1 + t
        ws.cell(rr, 1, t)
        ws.cell(rr, 2, ramp[t - 1] if t - 1 < len(ramp) else ramp[-1]).fill = fill
        ws.cell(rr, 3, "=%s*B%d*(1+$B$4)^(A%d-1)" % (sums["benefits"], rr, rr))
        ws.cell(rr, 4, "=%s*(1+$B$5)^(A%d-1)" % (sums["opex"], rr))
        ws.cell(rr, 5, cfg.get("residual_value", 0) if t == years else 0).fill = fill
        ws.cell(rr, 6, "=C%d-D%d+E%d" % (rr, rr, rr))
        ws.cell(rr, 7, "=F%d/(1+$B$3)^A%d" % (rr, rr))
        ws.cell(rr, 8, "=H%d+F%d" % (rr - 1, rr))
    last = hdr + 1 + years
    r = last + 2
    f0, f1 = "F%d" % (hdr + 1), "F%d:F%d" % (hdr + 2, last)
    for label, formula in [("NPV", "=NPV(B3,%s)+%s" % (f1, f0)), ("IRR", "=IRR(F%d:F%d)" % (hdr + 1, last)),
                           ("ROI", "=(SUM(%s)+%s)/-%s" % (f1, f0, f0)),
                           ("Simple payback (years, approx.)", "=-%s/AVERAGE(%s)" % (f0, f1)),
                           ("Profitability index", "=(NPV(B3,%s))/-%s" % (f1, f0))]:
        ws.cell(r, 1, label).font = bold
        ws.cell(r, 2, formula).font = bold
        r += 1
    ws.column_dimensions["A"].width = 42
    for col in "BCDEFGH":
        ws.column_dimensions[col].width = 16
    s2 = wb.create_sheet("Sensitivity")
    s2.append(["Scenario", "NPV", "IRR", "Payback (years)"])
    for label, kw in [("Base case", {}), ("Benefits -30%", {"benefit_k": 0.7}), ("Benefits -20%", {"benefit_k": 0.8}),
                      ("Benefits +20%", {"benefit_k": 1.2}), ("OPEX +30%", {"opex_k": 1.3}), ("CAPEX +30%", {"capex_k": 1.3}),
                      ("Discount rate +5 pp", {"rate_add": 0.05})]:
        s = model(cfg, **kw)
        s2.append([label, round(s["npv"]), s["irr"], s["payback"]])
    s2.column_dimensions["A"].width = 30
    wb.save(path)
    return path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for p in sys.argv[1:]:
        cfg = yaml.safe_load(open(p))
        name = os.path.splitext(os.path.basename(p))[0]
        out = os.path.join(os.path.dirname(os.path.abspath(p)), "out")
        os.makedirs(out, exist_ok=True)
        md, m = report(cfg, name)
        open(os.path.join(out, name + ".md"), "w").write(md + "\n")
        with open(os.path.join(out, name + ".csv"), "w") as f:
            f.write("year,net_cash_flow\n0,%.0f\n" % m["cfs"][0] + "".join("%d,%.0f\n" % (t, cf) for t, _, _, _, cf in m["rows"]))
        x = write_xlsx(cfg, m, os.path.join(out, name + ".xlsx"))
        print("=" * 60)
        print("%s: NPV %s | IRR %s | payback %s | ROI %s" % (name, fmt(m["npv"], cfg.get("currency", "")), pct(m["irr"]), yrs(m["payback"]), pct(m["roi"])))
        print("-> %s/%s.md%s" % (out, name, (" + .xlsx" if x else "")))


if __name__ == "__main__":
    main()
