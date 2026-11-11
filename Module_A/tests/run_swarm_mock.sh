#!/bin/bash
# Simulates a 3-drone swarm on one laptop: planner + 3 mocked agents (same as tests/run_swarm_mock.py).
# Dashboard: http://localhost:8000   Drone UIs: http://localhost:8090, 8091, 8092
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
CFG=${CFG:-config/case3_swarm.yaml}
exec $PY tests/run_swarm_mock.py --config "$CFG" --scale "${SCALE:-15}" "$@"
