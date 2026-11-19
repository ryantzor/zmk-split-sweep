# nice!view on the Sweep

The Sweep wires a key to every header pin except D0, so the nice!view is
soldered to D0 and the three pads on the underside of the nice!nano v2:

| nice!view | nice!nano v2 |
|---|---|
| GND | GND |
| VCC | VCC (3.3V) |
| SCL (SCK) | D0 / P0.08 |
| SDA (MOSI) | P1.07 (underside) |
| CS | P1.02 (underside) |

The build makes `cradio_left_view-nice_nano-zmk.uf2` alongside the normal
left firmware; flash that one once the display is wired.

The screen shows the active layer's emblem drawing itself, stroke by stroke, the layer name, battery,
and connection. `display.json` picks the animation and name per layer and how
it animates (`layer-change`: draws once after switching layers and stays; `active`: redraws every few seconds while typing;
`off`). Animations are folders of 68×68 PBM frames in `art/`, the last frame being the finished picture;
`tools/make_elements.py` draws the nation emblems (air, water, earth, fire) as if scratched with a stick, and a plain Bluetooth symbol, and the build turns the
frames into C with `tools/build_art.py`.
