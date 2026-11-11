# Economic efficiency - Case 4 - UAV inspection of 300 km of power lines

**Customer / user:** Grid company (Rosseti branch) / energy facility operator  
**Purpose:** Autonomous detection of overheating, damaged insulators, deformed supports and wire sag  
**Horizon:** 5 years, **discount rate:** 18.0% (key rate + risk premium)

## 1. Cost and benefit items

| No. | Cost/benefit item | Description | Amount / year | Comment |
|---|---|---|---|---|
| 1 | Development / capital cost (one-time) | 3 UAVs with thermal + RGB (+ lidar option) | 6 000 000 RUB |  |
| 2 | Development / capital cost (one-time) | Inspection software (AI defects, reports to dispatcher) | 2 000 000 RUB |  |
| 3 | Development / capital cost (one-time) | Training, certification, ground stations | 500 000 RUB |  |
| 4 | Operating expense (per year) | 2 operators incl. taxes | 1 800 000 RUB |  |
| 5 | Operating expense (per year) | Maintenance, batteries, insurance | 700 000 RUB |  |
| 6 | Benefit / saving (per year) | Helicopter patrols replaced (300 km x 2/yr x 15 000 RUB/km x 70%) | 6 300 000 RUB |  |
| 7 | Benefit / saving (per year) | Foot patrol labour saved | 2 000 000 RUB |  |
| 8 | Benefit / saving (per year) | Avoided outage (1/yr x 3 000 000 RUB undelivered energy + repair) | 3 000 000 RUB |  |

**Totals:** CAPEX 8 500 000 RUB · OPEX 2 500 000 RUB/yr · Benefits 11 300 000 RUB/yr (year-1 basis)

## 2. Cash flow

| Year | Benefits | OPEX | Net cash flow | Cumulative | Discounted CF | Cum. discounted |
|---|---|---|---|---|---|---|
| 0 | | | -8 500 000 | -8 500 000 | -8 500 000 | -8 500 000 |
| 1 | 7 910 000 | 2 500 000 | 5 410 000 | -3 090 000 | 4 584 746 | -3 915 254 |
| 2 | 11 300 000 | 2 675 000 | 8 625 000 | 5 535 000 | 6 194 341 | 2 279 086 |
| 3 | 11 300 000 | 2 862 250 | 8 437 750 | 13 972 750 | 5 135 475 | 7 414 562 |
| 4 | 11 300 000 | 3 062 608 | 8 237 392 | 22 210 142 | 4 248 755 | 11 663 317 |
| 5 | 11 300 000 | 3 276 990 | 8 823 010 | 31 033 152 | 3 856 619 | 15 519 936 |

## 3. Efficiency indicators

| Indicator | Value | Meaning |
|---|---|---|
| Payback period (simple) | **1.36 years** | investment returned |
| Discounted payback | 1.63 years | with time value of money |
| ROI (5 yr) | **365.1%** | (total net benefit - investment) / investment |
| NPV @ 18.0% | **15 519 936 RUB** | > 0 = creates value |
| IRR | **78.7%** | > discount rate = feasible |
| Profitability index | 2.83 | PV of inflows / investment (>1 good) |
| Break-even benefits | 52.2% of plan | NPV = 0 if benefits fall to this level |

## 4. Sensitivity analysis

| Scenario | NPV | IRR | Payback |
|---|---|---|---|
| Base case | 15 519 936 RUB | 78.7% | 1.36 years |
| Benefits -30% | 5 780 691 RUB | 42.9% | 2.05 years |
| Benefits -20% | 9 027 106 RUB | 55.4% | 1.73 years |
| Benefits +20% | 22 012 766 RUB | 100.7% | 1.14 years |
| OPEX +30% | 12 881 765 RUB | 69.3% | 1.49 years |
| CAPEX +30% | 12 969 936 RUB | 59.1% | 1.65 years |
| Discount rate +5 pp | 12 866 497 RUB | 78.7% | 1.36 years |
| Worst case (benefits -30%, CAPEX +30%) | 3 230 691 RUB | 29.3% | 2.55 years |

## 5. Comparison with alternatives

| Solution | Cost per year | Notes |
|---|---|---|
| Helicopter patrol | 9 000 000 RUB | expensive, risky for crew |
| Foot patrol | 3 000 000 RUB | slow, cannot see hot contacts |
| **Our UAV system** | 2 500 000 RUB (+ CAPEX 8 500 000 RUB once) | thermal + AI finds hidden defects; report with coordinates |

## 6. Conclusion

The project is **ECONOMICALLY FEASIBLE**: NPV 15 519 936 RUB > 0, IRR 78.7% vs discount rate 18.0%, payback 1.36 years.
It stays feasible as long as benefits are above 52.2% of the plan.

**Key factors:**
- km of lines covered
- defects found before failure
- helicopter hour price

**Recommendations:**
- integrate reports with the grid's asset-management system
- BVLOS permits for long lines

**Social effects:**
- fewer blackouts for consumers
- worker safety (no climbing / helicopters)
- fire risk from lines reduced

*All amounts are assumptions for illustration - replace them with the customer's data.*
