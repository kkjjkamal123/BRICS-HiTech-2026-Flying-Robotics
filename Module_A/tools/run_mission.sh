#!/bin/bash
# Starts the Case 1 mission CLEANLY (the dashboard's Run mission button calls this on the drone):
#   1. an older mission script that is still running ON THE GROUND is stopped first (Ctrl+C, then harder),
#   2. if the motors are ARMED (a mission is flying) nothing is stopped and nothing new starts,
#   3. then the new mission starts with the dashboard's settings (--set KEY=VALUE ...).
#   bash tools/run_mission.sh [--set KEY=VALUE ...]
# Needs the ROS environment (source /opt/ros/noetic/setup.bash; source ~/technic_ws/devel/setup.bash).
cd "$(dirname "$0")/.." || exit 1

# python3 processes only, so this never matches the shell / ssh command that started this script
old_pids() { ps -C python3 -o pid=,args= | awk '/drone\/case1_fire\.py/ {print $1}'; }

armed_state() {     # prints armed / disarmed / unknown
    local out
    out=$(timeout 5 rostopic echo -n 1 /mavros/state/armed 2>/dev/null | head -1)
    case "$out" in
        *True*) echo armed ;;
        *False*) echo disarmed ;;
        *) echo unknown ;;
    esac
}

OLD=$(old_pids)
if [ -n "$OLD" ]; then
    STATE=$(armed_state)
    if [ "$STATE" = armed ]; then
        echo "A MISSION IS FLYING (motors armed, pid $OLD). Not stopping it and not starting another one."
        echo "Land it first (Land / Abort in the dashboard), then press Run mission again."
        exit 4
    fi
    if [ "$STATE" = unknown ]; then
        echo "Cannot read the arming state (mavros not answering). To be safe the old mission (pid $OLD) is NOT stopped"
        echo "and no new one starts. Check the drone, land / stop it, then press Run mission again."
        exit 4
    fi
    echo "[run] stopping the previous mission script (pid $OLD, motors disarmed) ..."
    kill -INT $OLD 2>/dev/null
    for _ in $(seq 1 30); do [ -z "$(old_pids)" ] && break; sleep 0.5; done
    if [ -n "$(old_pids)" ]; then kill -TERM $(old_pids) 2>/dev/null; sleep 2; fi
    if [ -n "$(old_pids)" ]; then kill -KILL $(old_pids) 2>/dev/null; sleep 1; fi
    if [ -n "$(old_pids)" ]; then
        echo "The old mission script would not stop (pid $(old_pids)) - not starting a second one."
        exit 5
    fi
    echo "[run] previous mission stopped - starting the new one"
fi

exec python3 -u drone/case1_fire.py --config config/case1_fire.yaml --autostart "$@"
