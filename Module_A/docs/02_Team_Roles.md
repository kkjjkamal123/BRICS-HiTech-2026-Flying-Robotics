# 2. Team roles

Team from Chennai Institute of Technology, BRICS Hi-Tech Future Skills 2026, Flying Robotics.

| Participant | Role | Responsibilities | Contribution to the implementation |
|---|---|---|---|
| **Kamalesh Vadivelu Syamala** (ECE) | Flight software, safety and integration lead | Mission state machine and survey planning; PX4 / MAVROS / SKYRIS integration; GPS-denied navigation on the ArUco map; safety layer (geofence, map-boundary check, battery, marker loss, land fallback); thermal camera driver; NPU deployment; operator dashboard; flight tests | `drone/`, `common/` (safety, geometry, tracker, UI link), `tools/` (thermal node, flight tests), `dashboard/`, `setup/`, flight testing and logs |
| **Bejin Paul Josephin Paul Benjamin** (Mechanical) | Computer vision, mechanical design and documentation lead | Datasets and training of the detection models; camera calibration checks; thermal camera mount and CAD; economic model; documentation and presentation | `train/`, `models/`, `datasets/`, `cad/`, `economics/`, `docs/` |

Both team members take part in flight tests at the venue: one operates the ground station (BRICS Dashboard), the other is the safety pilot with the RC transmitter and the kill switch (channel 8).
