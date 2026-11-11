#!/bin/bash
# Full self-test (works offline). Same checks as tests/run_all_tests.py - see there for the options:
#   bash tests/run_all_tests.sh              everything (includes a 3-epoch training run, a few minutes)
#   bash tests/run_all_tests.sh --no-train   skip training (uses an existing model for the predict check)
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
exec $PY tests/run_all_tests.py "$@"
