# Module C - Economic Feasibility Assessment

Case 1, autonomous forest-fire monitoring UAV. Compiled report: [`Module_C_Economic_Assessment.pdf`](../Module_C_Economic_Assessment.pdf).

| File | Content |
|---|---|
| `main.tex` | report source (XeLaTeX; Overleaf: Menu -> Compiler -> XeLaTeX) |
| `econ_model.py` | economic model: every number, table value and chart in the report |
| `evidence_numbers.txt` | all values printed by the model |
| `figures/` | charts from the model, dashboard screenshot, flight photos from Module B |

Reproduce the numbers and charts:

```bash
pip install matplotlib
python3 econ_model.py
```

Base-case inputs are the same as [`Others/economics/case1_fire.yaml`](../Others/economics/case1_fire.yaml); the script checks
that its NPV matches that model (6 205 125 RUB).
