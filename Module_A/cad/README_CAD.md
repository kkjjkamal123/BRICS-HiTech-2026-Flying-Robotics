# CAD - TR256i thermal camera mounts + TECHNIC 6S model (Autodesk Fusion)

## Files (`cad/out/`)
| File | What |
|---|---|
| `TR256i_mount_down.stl` / `.step` | **Case 1** mount: thermal camera looking DOWN. 21.5 g PETG. **Print this.** |
| `TR256i_mount_forward.stl` / `.step` | **Case 4** mount: thermal camera looking FORWARD. 23.3 g. |
| `TECHNIC6S_with_thermal_mount_assembly.step` | Full drone: frame, all electronics, **64 wires**, thermal mount fitted |
| `TECHNIC6S_wiring_diagram.pdf` | Wiring diagram + connection table (every connection from the SKYRIS guide) |
| `technic6s_electronics_*.png`, `technic6s_wiring_side.png` | Close-ups of the electronics and wiring (guard/props/legs hidden) |
| `technic6s_guard_landing_gear.png` | Prop guard (4 clip-on guards + jumpers) and landing gear (mount + TPU leg) |
| `BRICS_aerial_robotics_CAD.f3d` | Fusion archive of everything (open in Fusion: File > Open > Open from my computer) |
| `Drawing_TR256i_mount_*.pdf` | A3 technical drawings generated from the real model edges |
| `render_*.png`, `technic6s_*.png` | Renders for the presentation / technical description |

## Print settings
PETG (PLA+ also fine indoors), 0.2 mm layers, **4 walls**, 30 % gyroid, **flat mounting face on the bed, no supports**.
DOWN mount: ~1 h on a typical printer. Check: the TR256i must slide in with light force (crush ribs); if too tight, change
`rib_int` 0.15 -> 0.10 at the top of `fusion_thermal_mount.py` and re-run.

## Assembly (Case 1)
1. Slide the TR256i into the cradle from the open end, lens facing out of the window, until it touches the stop wall.
2. Plug the USB-C cable (USB-C to USB-A to the Orange Pi). Zip-tie the cable through the 2 slots of the anchor tab.
3. Put the mount under the centre plate (behind the main camera, cable towards the rear). Pass two 15 mm velcro straps
   through the wing slots and around the bottom plate / arms. Pull tight. (Or zip ties / M3 screws in the slots.)
4. Check: nothing in the lens window, landing legs still the lowest point (the TR256i mount sits ~17 mm above the ground in the model).
5. `python3 tools/thermal_probe.py` on the drone -> camera works.

## How the mount was verified (Fusion script `fusion_verify_mount.py`)
single solid · mass < 30 g · TR256i touches ONLY the 4 crush ribs (interference analysis) · 56 deg lens cone clear for 45 lens
positions (lens position on the real module is unknown) · only overhangs are the 2.2 mm lips (prints without supports) ·
every plate slot has a free strap path · STL watertight, volume = model.

## TECHNIC 6S model - how it was made (honest note)
SKYRIS does not publish CAD. The model follows the **SKYRIS assembly guide** step by step (offline copy in `offline/docs`):
* **Frame:** arm and battery-plate outlines imported from the guide's vector figures (2.svg, 15_11.svg); scale from known hole
  patterns (30.5 mm FC stack -> 1.32 mm per drawing unit, M3 holes = 3.1 mm, motor bells 28 mm). Motors +-86.1/+-96.0 mm,
  35 mm alu standoffs, 6" props.
* **Electronics, real board sizes:** ESC 4in1 + PX4 FC 30.5 mm stack (M3x6 M-F + M3x8 F-F nylon standoffs, dampers),
  ELRS receiver taped on the top plate, MR30 motor connectors, XT60 in its mount on the battery plate, 4S battery + strap,
  Orange Pi 5 Pro 89x56 under the frame (connectors down, HDMI to the rear) on the printed mount, SKYRIS Shield V2 on the
  40-pin header with the 30 mm cooler, LED ring (58 x WS2812) on 4 LED mounts, WiFi antenna in the rear holder,
  35 mm nylon standoffs to the camera plate with the USB camera (front) and VL53L1X, our TR256i mount under the camera plate.
* **Wiring (every wire is a separate swept body):** ESC-FC 8-pin; 4 x ESC pigtail -> MR30 -> motor phases along the arms;
  ESC -> XT60 (through the battery-plate slot) -> battery lead; balance lead; FC TELEM1 -> ELRS; FC TELEM2 -> shield UART0
  (through a slot in both centre plates); ESC -> shield V IN; cooler -> 5V; LED -> shield LED; VL53L1X -> I2C;
  camera USB and TR256i USB -> Orange Pi USB-A; WiFi coax; ELRS antenna. 64 wires in 22 cables.
* **Landing gear (guide step 3 + 6):** under each motor the spacer + 'landing-gear mount' held by 2 x M3x20 that go into the
  motor's own holes; the fin-shaped TPU leg ('Ножка') is pushed into the mount slot and locked with an M3x14. Foot 76 mm
  below the arms, curling inwards under the arm.
* **Prop guard (guide step 7):** 4 x 'Защита пропеллера' clipped onto the arm ends (clip + optional M3x12, 2 rails, tall
  curved outer band 28 mm high with a post at each end, 15.8 mm outside the prop tips), joined by 2 short + 2 long jumper
  bars screwed (M3x8) onto the posts. Overall about 357 x 382 mm.
* **Checked:** interference analysis of all 265 bodies: 0 unintended overlaps, every wire touches only its own connectors,
  no wire buried in a part. Ground clearance of the thermal mount ~17 mm.
* Guard and leg shapes are drawn from the guide's figures (no published dimensions): outline and fit are right,
  the exact curves are approximate.
* Connector and chip positions on the boards are representative (board outlines and connector bodies are real sizes);
  main dimensions +-3 %. The exact FC/ESC brand is not named in the guide - the model uses the 30.5 mm PX4 stack it shows.

## Rebuild / change dimensions
Edit the measurements at the top of `fusion_thermal_mount.py` (use calipers on the real TR256i!), open Fusion, then:
```
.venv/bin/python cad/build_all_cad.py
```
(or in Fusion: Utilities > Scripts and Add-Ins > run `fusion_thermal_mount.py`, then `fusion_verify_mount.py`).
