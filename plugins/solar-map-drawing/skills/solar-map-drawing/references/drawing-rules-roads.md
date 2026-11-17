## Roads

Draw streets **only at 0, 90, 180 or 270 degrees in the final output**. Preserve the source-confirmed road count, names, property sides and meaningful connections. Corner lots can have **two roads on adjacent sides**; retain additional roads when the source shows them. Do not invent a second road because a house looks like a corner lot.

**Full drawing-area span:** roads frame the usable map-and-callout drawing area, not just the house footprint. A side road runs its full available height and a top/bottom road its full available width. Plan that area inside the ordered work zone, below/around the warning or title and above the footer/lower notes, with the required production and hole clearances. Do not extend through those reserved zones or across the entire source PDF page. Map-only/labeled output uses the same planned area even when finishing is suppressed.

Use the reviewed ROADS-EXAMPLE.ai pattern as the layout convention: solid inner edges alongside the site, parallel dashed edges outside, and separate names between them. Its three-sided arrangement demonstrates the same approach as a two-road corner; reproduce only the sides established by the current source. At a shared corner, join the solid inner edges cleanly and carry the dashed outer edges to the drawing-area boundary. Avoid overlapping duplicate strokes or lines cutting through the adjoining road's name.

**Scale with the map drawing area:** recompute road lengths, lane spacing and dash/gap lengths when that area changes size. Do not retain a short source segment or fixed miniature road beside a larger map. Use one consistent lane proportion for roads on the same map, with enough width for readable names. Keep the established **0.75 pt physical road strokes** and readable text sizing; do not scale building/panel/equipment strokes or move site features to fit roads. Road geometry is schematic, not surveyed.

Use `road_layout.drawing_area` and an explicit final `layout_side` per road for new or revised road layouts; see [scene format](scene-format.md#production-lettering-and-roads). Fit the source buildings/panels inside the remaining area with callout room. Road extensions are generated in output coordinates and must not drive a second fit or change the source geometry.

In labeled/finished output, keep each name within its own lane, parallel to the horizontal/vertical road and clear of corner junctions; map-only omits names. Type below 10 pt remains red. Do not replace a side road with a bottom caption or select the same road edge again as a context path.

For source bends/curves, use reviewed horizontal/vertical legs and preserve meaningful connections. The four-side frame helper covers straight streets around a drawing area; a more complex junction needs a reviewed explicit layout. Never rotate, skew or simplify buildings, roofs or panels, or change north, just to square a road.
