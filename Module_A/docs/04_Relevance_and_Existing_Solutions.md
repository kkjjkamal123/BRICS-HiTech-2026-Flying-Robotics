# 4. Project relevance and review of existing solutions

## 4.1 Target user and problem

**Target user:** a regional forest-protection service, i.e. the aerial forest protection unit (Avialesookhrana) or a forest district that has to watch remote, hard-to-reach forest for the start of fires.

**Problem:** large forest fires grow from small ignition sources: campfires, vehicles, smouldering debris. Today these are found by manned patrol flights, ground crews, watch towers with cameras, or satellite hot-spot products. Patrols are expensive and slow. Fixed cameras have blind spots in valleys and under canopy. Satellites only see fires that are already large, and only when they pass overhead. A small source found early, with exact coordinates, is the cheapest fire to put out.

**What our system changes in the operator's workflow:**

| Step | Today | With our UAV |
|---|---|---|
| Search | Patrol flight or tower operator watching video | The UAV flies a pre-planned survey route on its own |
| Detection | Human eye, or a camera/satellite alert with a large location error | Onboard thermal + RGB neural networks, ≥ 10 FPS, a confirmed source after 4 consistent views |
| Location | Approximate (tower bearing, satellite pixel of hundreds of metres) | Map coordinates of every source, shown live on the operator's map with type, temperature and time |
| Verification | A crew is sent out | The UAV descends over the source, hovers and saves a snapshot |
| Report | Manual | Automatic event log (time, coordinates, class, confidence, temperature) |

## 4.2 Evidence that the need is real

| # | Evidence | What it says | Source |
|---|---|---|---|
| E1 | UNEP / GRID-Arendal report *Spreading like Wildfire: The Rising Threat of Extraordinary Landscape Fires* (Feb 2022) | Extreme fires are projected to increase by up to **14 % by 2030, 30 % by 2050 and 50 % by 2100**. Today **less than 1 %** of fire-related spending goes to planning and prevention; the report recommends shifting two-thirds of spending to prevention and preparedness. | [UNEP report page](https://www.unep.org/resources/report/spreading-wildfire-rising-threat-extraordinary-landscape-fires); summary by [University of Oxford, 23 Feb 2022](https://www.geog.ox.ac.uk/news/2022/0223-wildfires.html) |
| E2 | Russian Aerial Forest Protection Service (Avialesookhrana) figures reported by Interfax, July 2024 | Almost **6,000 wildfire outbreaks on more than 3.5 million hectares** recorded in Russia by July 2024. | [Interfax, 10 Jul 2024](https://interfax.com/newsroom/top-stories/104191/) |
| E3 | Russian Forestry Agency figures reported by The Moscow Times | Wildfires cost Russia about **USD 100 million** in 2019 (firefighting costs only). | [The Moscow Times](https://www.themoscowtimes.com/2019/08/22/wildfires-have-cost-russia-100m-in-2019-forestry-authority-says-a66980) |
| E4 | Customer task statement: competition case "University 2035: Autonomous Forest Fire Monitoring", BRICS Hi-Tech Future Skills 2026 | Existing approaches need a lot of time and personnel, and visual inspection may miss concealed ignition sources at an early stage. Required: a UAV with a thermal camera and a neural network that finds a simulated campfire and a vehicle. | Official competition task document (HiTech 2026, Flying Robotics) |

E1 shows the global trend and that prevention/early detection is under-funded. E2 and E3 show the scale and cost in the customer's own country. E4 is the customer's own requirement.

## 4.3 Existing solutions

| | **A. Camera towers with automatic smoke detection** (e.g. Lesnoy Dozor, Russia) | **B. Satellite active-fire products** (NASA FIRMS, VIIRS 375 m) | **C. Thermal nanosatellite constellation** (OroraTech) | **D. Manually flown thermal drone** (e.g. DJI Matrice 30T) | **Our system** |
|---|---|---|---|---|---|
| Principle | Video / IR / thermal cameras on towers; software flags smoke and fire; an operator confirms | Thermal bands of polar-orbiting satellites; automatic hot-spot detection | Small satellites with thermal sensors, onboard fire detection | Pilot flies a drone with a radiometric thermal camera | Autonomous UAV, onboard thermal + RGB neural networks on an NPU |
| Spatial detail | Bearing and estimated distance from the tower | **375 m** pixel | **~200 m** ground sampling distance | cm-level image; location depends on pilot and laser rangefinder | Map coordinates of each source; required accuracy ≤ 0.5 m (to be confirmed by tape measurement in Module B) |
| Coverage / timing | Continuous, but only line of sight from the tower | 1–2 overpasses per satellite per day; fire must be large enough to raise the pixel temperature | Several passes a day; the company targets 30-minute revisit with a larger fleet | Only when a crew is on site; flight time ~41 min per battery set | On demand, a pre-planned route; one survey of our test field takes ~2–2.5 min |
| Main limitations | Blind zones in valleys and behind ridges; smoke must rise above the canopy; operator workload (one operator per ~10 cameras) | Coarse pixels: small campfires are below detection; cloud cover; latency of hours | Still ~200 m pixels; small sources are missed; subscription service | Needs a trained pilot; the operator must interpret the thermal image; no automatic logging | Short range and endurance of a small UAV; tested indoors only; needs a map for positioning (GNSS outdoors) |
| Source | [Lesnoy Dozor (Wikipedia)](https://en.wikipedia.org/wiki/Lesnoy_Dozor) | [NASA VIIRS 375 m active fire product](https://data.nasa.gov/dataset/viirs-noaa-20-jpss-1-375m-i-band-active-fire-product-nrt-vector-data) | [OroraTech constellation](https://ororatech.com/resources/news-blog/ororatech-launches-world-s-first-satellite-constellation-for-wildfire-detection-and-data-accumulation), [EGU26-5334 abstract](https://meetingorganizer.copernicus.org/EGU26/EGU26-5334.html) | [DJI Enterprise: wildfires](https://enterprise.dji.com/public-safety/wildfires) | This repository |

## 4.4 How our solution addresses these limitations

1. **Small sources:** satellites (B, C) resolve hundreds of metres; our UAV looks from 1.5 m (scaled up: tens of metres in the field) and finds individual heat sources of a few centimetres. Tested at the venue: the heat source and the flame lamp were detected in the survey flights, and the thermal network finds both on frames from flights it was not trained on (see [12_Test_Evidence.md](12_Test_Evidence.md)).
2. **No blind zones:** unlike a tower (A), the UAV flies over the area and looks straight down, so terrain and canopy edges do not hide the source.
3. **No pilot interpretation:** unlike a manual thermal drone (D), detection, confirmation, coordinates and logging are automatic. The operator starts the mission with one click and watches a live map.
4. **Two independent sensors:** the thermal neural network finds hot sources by shape, the measured temperature (°C) confirms them, and the RGB network recognises the flame. A false alarm needs to fool several of them.
5. **Edge processing:** all detection runs on the onboard NPU, so no video link to a data centre is needed. Only coordinates and events go to the ground station.

What the existing solutions do better and we do not claim to replace: satellites and towers cover huge areas continuously. Our UAV is a fast **verification and local-search tool** that is dispatched to an area flagged by those systems or by a patrol schedule.
