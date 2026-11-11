"""
Knowledge base for every problem statement (PS): texts + defaults used by Mission Studio and make_docs.py
to generate the complete solution (config, documents, presentation) automatically.
A 'custom' PS is built from the user's answers with the same structure.
"""

TEAM = [
    ("Kamalesh Vadivelu Syamala", "Flight software & safety lead",
     "Mission state machine, navigation (ArUco map, offboard), PX4/QGroundControl setup, kill switch, flight tests, deployment"),
    ("Bejin Paul Josephin Paul Benjamin", "Computer vision, AI & documentation lead",
     "Dataset, model training and export (ONNX/RKNN), camera calibration, detection tuning, economics, reports and presentation"),
]

BASE_COMPONENTS = [
    ("TECHNIC 6S quadcopter frame (<= 10 inch)", "Airframe with prop guards", "Diagonal <= 10\", indoor-safe", "Competition platform, meets size rule"),
    ("PX4 flight controller", "Stabilisation, EKF2 state estimation, motor control", "PX4 autopilot, MAVLink", "Proven open-source autopilot, OFFBOARD mode for autonomy"),
    ("Orange Pi 5 Pro (RK3588S)", "Onboard computer: ROS, mission, computer vision, AI", "8-core CPU, 6 TOPS NPU", "Real-time AI on board, no dependence on a radio link"),
    ("Main camera (AR0234)", "ArUco localisation + object detection", "Global shutter, calibrated", "Sharp images in motion, accurate marker pose"),
    ("ArUco marker field + VPE", "Indoor positioning (no GPS indoors)", "aruco_map frame, vision pose to EKF2", "cm-level indoor position, required for repeatable autonomy"),
    ("Optical flow / rangefinder", "Velocity and height backup", "", "Stability if markers are briefly lost"),
    ("RC transmitter + receiver", "Manual override and KILL SWITCH", "enough channels incl. kill switch", "Mandatory safety requirement"),
    ("LED strip", "Visual alarm / status signalling", "RGB, /led/set_effect", "Operator sees detections instantly"),
    ("Ground station laptop + web UI", "Operator control, live view, reports", "Wi-Fi, browser at :8090", "One-button operation, no software to install for the operator"),
    ("Software: ROS Noetic, Python, OpenCV, YOLO (ONNX/RKNN)", "Autonomy + AI stack", "", "Open, fast to develop, runs on the NPU"),
]

COMMON_DECISIONS = [
    ("Onboard AI (ONNX on CPU / RKNN on NPU) instead of streaming video to the ground",
     "Works without a reliable radio link, lower latency, scales to many drones"),
    ("Objects confirmed only after N detections + merged by position (tracker)",
     "Removes false alarms from single bad frames; one object = one report"),
    ("Pixel -> map coordinates using camera intrinsics + TF (or triangulation)",
     "The customer receives exact coordinates, not just pictures"),
    ("Mission as a state machine with safety supervisor",
     "Predictable behaviour; low battery / lost markers / leaving the geofence / operator abort / time limit always land the drone"),
    ("Configuration in one YAML file",
     "The same code adapts to a new field, object or customer in minutes, without programming"),
    ("Training pipeline from any dataset format + venue data collection",
     "Model can be retrained on real venue images on day C1 for maximum accuracy"),
]

COMMON_REQUIREMENTS = [
    ("Stable takeoff and hover at mission height", "Take off, hover 30 s, log pose", "Drift < 0.15 m, no oscillation"),
    ("Autonomous route flight in aruco_map", "Run mission, compare path.csv to the plan", "All waypoints reached within 0.2 m"),
    ("Operator control (start / return / land / abort) from the web UI", "Press each button during a flight", "Reaction < 1 s; RETURN flies home and lands, LAND / ABORT land in place"),
    ("Safety: low battery / lost markers / geofence / time limit", "Simulate each condition (mock + real low-voltage threshold)", "Drone lands automatically, reason logged"),
    ("Mission report generated automatically", "Finish a mission", "report.html + CSV with objects, coordinates, snapshots"),
    ("Mission duration within the 10-minute slot", "Measure flight time", "< 9 min incl. takeoff and landing"),
]

CASES = {
    "case1": {
        "title": "Autonomous detection of ignition sources (forest fire monitoring)",
        "partner": "ANO \"University 2035\"",
        "short": "Forest fire",
        "script": "drone/case1_fire.py", "config": "config/case1_fire.yaml", "econ": "economics/case1_fire.yaml",
        "mission_type": "survey", "classes": ["fire", "smoke", "car"],
        "problem": "Large forest fires start from small ignition sources (campfires, cars, sparks) in hard-to-reach "
                   "territory. Patrols take a lot of time and people, and visual inspection does not find hidden "
                   "ignition sources early enough.",
        "customer": "Regional forestry service / emergency services",
        "solution": "An autonomous UAV flies a survey route over the forest area, analyses RGB and thermal images "
                    "on board with a neural network (YOLO) and a thermal hot-spot detector, confirms each ignition "
                    "source over several frames, descends to inspect it, and reports its exact coordinates with a "
                    "photo to the operator in real time.",
        "characteristics": ["Autonomous survey of a given area (lawnmower pattern with camera-footprint overlap)",
                            "TR256i thermal camera (256x192, 25 Hz) reads real temperatures: anything > 60 C is a potential ignition source - "
                            "finds heat sources that are INVISIBLE to a normal camera (IR heaters, smouldering spots)",
                            "Detection classes: fire / flame, smoke, car (RGB + YOLO) and thermal hot-spots",
                            "Real-time onboard inference (ONNX CPU / RKNN NPU)",
                            "Object coordinates in the map frame, accuracy ~5-10 cm in tests",
                            "Alarm: LED + operator UI alert + inspection hover",
                            "Automatic HTML/CSV report with map and snapshots"],
        "decisions": [("Thermal detection in degrees Celsius (raw sensor data), not image brightness",
                       "A fixed physical threshold (60 C) is independent of lighting and colours, needs no training and gives no false alarms from bright objects"),
                      ("Combined detectors: thermal + YOLO + colour fallback",
                       "Thermal for hidden/early fires, neural network for object type (car, smoke), colour detector works without training"),
                      ("Inspection hover after confirmation", "Second, closer look reduces false alarms and gives a better photo for the operator")],
        "requirements": [("Detect ignition source (simulated flame) on the route", "Place target at 5 positions, 5 flights", ">= 90% detected, 0 false alarms"),
                         ("Report coordinates of the ignition source", "Compare reported vs measured position", "Error < 0.3 m"),
                         ("Alarm to operator", "Observe UI + LED when a fire is confirmed", "Alert shown < 2 s after confirmation")],
        "risks": ["Venue lighting changes colours -> HSV tuned on site, model fine-tuned on venue images",
                  "Small objects at altitude -> survey altitude 1.2-1.5 m, tiling for small objects"],
        "qa": [("How do you avoid false alarms?", "Confirmation over >= 3 frames, merging by position, inspection hover, confidence threshold tuned on validation data."),
               ("Why thermal + RGB?", "Thermal finds hot spots hidden by smoke or vegetation; RGB + YOLO identifies the object type."),
               ("How does it scale to a real forest?", "GNSS/RTK instead of ArUco, fixed-wing or long-endurance UAV, same software pipeline and reports; mesh/LTE link for alerts.")],
    },
    "case2": {
        "title": "Automatic counting of weed plants and digital infestation map",
        "partner": "GEOSAERO LLC",
        "short": "Weed counting",
        "script": "drone/case2_weeds.py", "config": "config/case2_weeds.yaml", "econ": "economics/case2_weeds.yaml",
        "mission_type": "photos", "classes": ["weed", "crop"],
        "problem": "Agronomists must process huge field areas (up to 10 000 ha per day). Manual identification and "
                   "counting of weeds is slow and expensive and limits the accuracy of agronomic analysis.",
        "customer": "Agro-holdings, farms, agronomy service providers",
        "solution": "The UAV flies a photo grid over the plot, stopping for sharp images with exact pose. An "
                    "algorithm detects weeds in every photo (YOLO trained on weed/crop or vegetation-index "
                    "segmentation), projects them to metres, merges duplicates from overlapping photos, counts "
                    "them and produces a digital weed-infestation heat map for spot spraying.",
        "characteristics": ["Photo grid survey with configurable overlap and spacing",
                            "Weed vs crop detection (YOLO) or vegetation index (ExG) without training",
                            "Tiled inference for very small plants in large images",
                            "Duplicate-free count across overlapping photos (merge radius 8 cm)",
                            "Heat map (weeds per cell) + CSV with coordinates of every plant",
                            "Works on a single aerial image of a plot as well"],
        "decisions": [("Stop-and-shoot photo grid instead of continuous video", "No motion blur, exact pose per photo -> accurate positions and no double counting"),
                      ("Detection on metric map + merging", "Counting physical plants, not detections")],
        "requirements": [("Count weeds on the test plot", "Compare automatic count to manual count", "Count error < 10%"),
                         ("Weed positions on the map", "Compare 5 weeds to tape-measured positions", "Error < 0.1 m"),
                         ("Infestation map generated", "Run analysis after landing", "Heat map + CSV produced automatically")],
        "risks": ["Weed and crop look similar -> train on venue images, use multispectral if available",
                  "Overlap too small -> photo_spacing and overlap configurable"],
        "qa": [("How do you avoid counting one weed twice?", "Every detection is projected to field coordinates; detections closer than the merge radius are one plant."),
               ("Can it process a single orthophoto?", "Yes, weed_map.py works on one big image with tiling and gives weeds per m2 if the ground resolution is known."),
               ("What is the output for the farmer?", "A heat map and a CSV/GIS layer that can be loaded into a sprayer as a prescription map.")],
    },
    "case3": {
        "title": "Swarm detection and monitoring of the Red Palm Weevil",
        "partner": "Agro-technological consortium (UAE)",
        "short": "Swarm",
        "script": "drone/case3_swarm_agent.py", "config": "config/case3_swarm.yaml", "econ": "economics/case3_swarm.yaml",
        "mission_type": "survey", "classes": ["infected", "healthy"],
        "problem": "The red palm weevil destroys date palm plantations (losses up to 30% of the harvest). Visual "
                   "signs appear too late, when the tree cannot be saved. Early detection over large plantations is needed.",
        "customer": "Date-palm plantation operators",
        "solution": "A swarm of 3-5 small UAVs shares one plantation: a planner splits it into zones and hands them "
                    "out on request, so the drones distribute the work autonomously and take over the zone of a "
                    "failed drone. Each drone detects stress signs (thermal / spectral / AI) and reports the "
                    "infected tree's coordinates; reports are merged into one 'treatment needed' alert.",
        "characteristics": ["3-5 drones, work-queue zone distribution, automatic re-assignment on failure",
                            "Collision avoidance by altitude layers + separate zones",
                            "Heartbeat monitoring, RETURN ALL / ABORT ALL",
                            "Fallback: static strips if the planner link is lost",
                            "Merged alerts with coordinates, swarm dashboard"],
        "decisions": [("Work-queue (pull) zone assignment instead of fixed split", "Faster drones do more, failures are absorbed automatically"),
                      ("Altitude layers per drone", "Simple, verifiable collision avoidance without inter-drone sensing"),
                      ("Each drone fully autonomous with fallback strip", "Swarm still completes the mission if the network fails")],
        "requirements": [("Zones distributed automatically to all drones", "Run with 3 drones, watch dashboard", "All zones done, each drone >= 1 zone"),
                         ("Failed drone's zone re-assigned", "Stop one drone mid-mission", "Its zone is completed by another drone"),
                         ("Infected tree detected and reported once", "One infected tree model among healthy ones", "One alert with coordinates error < 0.3 m")],
        "risks": ["Wi-Fi network for several drones -> AUTO mode + one router, tested before flights",
                  "Indoor space for 3+ drones -> altitude layers, conservative speeds"],
        "qa": [("What if one drone fails?", "No heartbeat for 8 s -> its zone returns to the queue and another drone finishes it."),
               ("How do drones avoid each other?", "Separate zones and different altitude layers (e.g. 1.2 / 1.6 / 2.0 m)."),
               ("Why a swarm?", "Coverage time drops ~N times and the system survives a single drone failure.")],
    },
    "case4": {
        "title": "Autonomous inspection of power transmission lines and energy facilities",
        "partner": "PJSC Rosseti / State Corporation Rosatom",
        "short": "Power lines",
        "script": "drone/case4_powerline.py", "config": "config/case4_powerline.yaml", "econ": "economics/case4_powerline.yaml",
        "mission_type": "orbit", "classes": ["overheating", "insulator_damage", "support_deformation", "wire_sag", "corona"],
        "problem": "Power lines and energy facilities are long and hard to reach. Foot patrols and helicopter flights "
                   "are slow and expensive and do not detect hidden defects such as overheating early.",
        "customer": "Grid companies (Rosseti), energy facility operators (Rosatom)",
        "solution": "The UAV automatically flies an arc around each support at several heights and along the spans, always on "
                    "one side of the line so it never crosses the wires, with "
                    "the inspection camera facing the structure. Thermal and AI detectors find overheating, damaged "
                    "insulators, deformed supports and wire sag; each defect is located in 3D by triangulation from "
                    "several viewpoints and reported with severity, location (support/span) and a photo.",
        "characteristics": ["Automatic orbit + span inspection plan from tower coordinates",
                            "Forward-looking TR256i thermal camera: overheated contacts/wires detected above 45 C (real temperatures)",
                            "Defect classes: overheating, insulator damage, support deformation, wire sag, corona",
                            "3D localisation by multi-view triangulation (< 1 cm in simulation)",
                            "Severity classification and location naming (support k / span i-j)",
                            "Ground-station report for the dispatcher"],
        "decisions": [("Multi-view triangulation instead of assumed distance", "Correct 3D position and no duplicate defects from different viewpoints"),
                      ("Arcs at several heights + span pass, all on one side of the line", "Supports and the full wire length are seen without ever crossing the wires (collision risk)")],
        "requirements": [("Full fly-around of the mock-up", "Run mission, compare path to plan", "All orbit points reached, distance to tower >= 1 m, path never crosses the wires"),
                         ("Detect specified defects", "Place each defect type on the mock-up", ">= 90% detected, correct type"),
                         ("Defect coordinates and location", "Compare with measured positions", "Error < 0.2 m, correct support/span")],
        "risks": ["Forward camera needed -> mount/tilt camera, orientation: forward in config",
                  "Flying near structures -> orbit radius >= 1 m, low speed, kill switch"],
        "qa": [("How do you know where the defect is in 3D?", "Every detection is a ray from the camera; rays from different orbit points intersect at the defect (least squares)."),
               ("How do you detect overheating?", "Thermal camera hot-spot detection relative to the background, plus AI classes for visual defects."),
               ("How does it work on a real line?", "GNSS/RTK waypoints from tower coordinates, same orbit/span planner, BVLOS permits.")],
    },
}


def custom_case(title, problem, customer, objects, mission_type, solution=None):
    """Build a PS description for a NEW problem statement from a few answers."""
    objects = [o.strip() for o in objects if o.strip()]
    mt_text = {"survey": "flies a survey pattern over the area with a downward camera",
               "photos": "takes a grid of sharp photos with exact positions and analyses them",
               "orbit": "circles around each target structure with the camera facing it",
               "waypoints": "flies a defined route of waypoints"}.get(mission_type, "flies an autonomous route")
    return {
        "title": title, "partner": "", "short": title[:20], "script": "drone/generic_mission.py",
        "config": None, "econ": None, "mission_type": mission_type, "classes": objects,
        "problem": problem, "customer": customer,
        "solution": solution or ("An autonomous UAV %s, detects %s on board with a neural network (and classic "
                                 "computer-vision fallbacks), confirms each object over several frames, locates it in "
                                 "map coordinates and reports it to the operator with a photo and an automatic report."
                                 % (mt_text, ", ".join(objects) or "the target objects")),
        "characteristics": ["Autonomous mission type: %s" % mission_type,
                            "Detection classes: %s" % ", ".join(objects),
                            "Real-time onboard inference, object coordinates in the map frame",
                            "Operator web UI, alarms, automatic HTML/CSV report"],
        "decisions": [], "requirements": [("Detect target objects", "Place targets at 5 positions, 5 flights", ">= 90% detected"),
                                          ("Report object coordinates", "Compare to measured positions", "Error < 0.3 m")],
        "risks": ["Venue conditions differ from training data -> collect venue images and fine-tune on day C1"],
        "qa": [("How do you avoid false alarms?", "Multi-frame confirmation, merging by position, tuned confidence threshold.")],
    }
