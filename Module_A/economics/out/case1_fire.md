# Economic efficiency - Case 1 - UAV ignition-source monitoring for a forestry district

**Customer / user:** Regional forestry service (Avialesookhrana / forest district)  
**Purpose:** Detect ignition sources (campfires, early fires) in hard-to-reach forest early, before large fires develop  
**Horizon:** 5 years, **discount rate:** 18.0% (key rate + project risk premium)

## 1. Cost and benefit items

| No. | Cost/benefit item | Description | Amount / year | Comment |
|---|---|---|---|---|
| 1 | Development / capital cost (one-time) | 2 UAVs with thermal + RGB camera, onboard NPU computer | 1 800 000 RUB |  |
| 2 | Development / capital cost (one-time) | Software development (navigation, AI detection, operator UI) | 1 200 000 RUB |  |
| 3 | Development / capital cost (one-time) | Ground station, batteries, chargers, transport cases | 300 000 RUB |  |
| 4 | Development / capital cost (one-time) | Operator training and certification | 200 000 RUB |  |
| 5 | Operating expense (per year) | Operator (0.5 FTE) incl. taxes | 900 000 RUB |  |
| 6 | Operating expense (per year) | Maintenance, spare parts, batteries | 350 000 RUB |  |
| 7 | Operating expense (per year) | Insurance, registration, data link | 150 000 RUB |  |
| 8 | Benefit / saving (per year) | Fewer manned patrol flights (60 h x 60 000 RUB/h x 50%) | 1 800 000 RUB | UAV replaces half of aircraft patrol hours |
| 9 | Benefit / saving (per year) | Avoided fire damage (earlier detection: ~2 fires/yr x 10 ha saved x 150 000 RUB/ha) | 3 000 000 RUB |  |
| 10 | Benefit / saving (per year) | Reduced ground-crew patrol time | 400 000 RUB |  |

**Totals:** CAPEX 3 500 000 RUB · OPEX 1 400 000 RUB/yr · Benefits 5 200 000 RUB/yr (year-1 basis)

## 2. Cash flow

| Year | Benefits | OPEX | Net cash flow | Cumulative | Discounted CF | Cum. discounted |
|---|---|---|---|---|---|---|
| 0 | | | -3 500 000 | -3 500 000 | -3 500 000 | -3 500 000 |
| 1 | 3 120 000 | 1 400 000 | 1 720 000 | -1 780 000 | 1 457 627 | -2 042 373 |
| 2 | 5 200 000 | 1 498 000 | 3 702 000 | 1 922 000 | 2 658 719 | 616 346 |
| 3 | 5 200 000 | 1 602 860 | 3 597 140 | 5 519 140 | 2 189 330 | 2 805 676 |
| 4 | 5 200 000 | 1 715 060 | 3 484 940 | 9 004 080 | 1 797 493 | 4 603 170 |
| 5 | 5 200 000 | 1 835 114 | 3 664 886 | 12 668 965 | 1 601 955 | 6 205 125 |

## 3. Efficiency indicators

| Indicator | Value | Meaning |
|---|---|---|
| Payback period (simple) | **1.48 years** | investment returned |
| Discounted payback | 1.77 years | with time value of money |
| ROI (5 yr) | **362.0%** | (total net benefit - investment) / investment |
| NPV @ 18.0% | **6 205 125 RUB** | > 0 = creates value |
| IRR | **74.1%** | > discount rate = feasible |
| Profitability index | 2.77 | PV of inflows / investment (>1 good) |
| Break-even benefits | 57.2% of plan | NPV = 0 if benefits fall to this level |

## 4. Sensitivity analysis

| Scenario | NPV | IRR | Payback |
|---|---|---|---|
| Base case | 6 205 125 RUB | 74.1% | 1.48 years |
| Benefits -30% | 1 855 552 RUB | 36.8% | 2.28 years |
| Benefits -20% | 3 305 409 RUB | 50.0% | 1.90 years |
| Benefits +20% | 9 104 840 RUB | 96.4% | 1.24 years |
| OPEX +30% | 4 727 749 RUB | 61.7% | 1.68 years |
| CAPEX +30% | 5 155 125 RUB | 56.1% | 1.76 years |
| Discount rate +5 pp | 5 102 709 RUB | 74.1% | 1.48 years |
| Worst case (benefits -30%, CAPEX +30%) | 805 552 RUB | 24.7% | 2.80 years |

## 5. Comparison with alternatives

| Solution | Cost per year | Notes |
|---|---|---|
| Manned aircraft patrol | 3 600 000 RUB | expensive per hour, weather limited |
| Fire watch towers + cameras | 2 500 000 RUB | fixed view, blind zones in valleys |
| Satellite monitoring | 500 000 RUB | detects only large fires, hours of delay |
| **Our UAV system** | 1 400 000 RUB (+ CAPEX 3 500 000 RUB once) | detects small ignition sources in real time with coordinates |

## 6. Conclusion

The project is **ECONOMICALLY FEASIBLE**: NPV 6 205 125 RUB > 0, IRR 74.1% vs discount rate 18.0%, payback 1.48 years.
It stays feasible as long as benefits are above 57.2% of the plan.

**Key factors:**
- number of fires detected early
- patrol hours replaced
- UAV availability (weather, batteries)

**Recommendations:**
- start with 1 district, scale to the region
- share UAVs between forestry and emergency services
- use the NPU onboard to avoid expensive data links

**Social effects:**
- less burned forest and CO2 emissions
- safety of firefighters and residents
- less smoke pollution for cities

*All amounts are assumptions for illustration - replace them with the customer's data.*
