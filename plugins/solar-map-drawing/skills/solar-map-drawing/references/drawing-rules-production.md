## Production drawing rules

**Locked solar panel rules:** preserve the panel rules and their implementation during all other changes, including equipment, callouts, templates and layout work. Only an explicit instruction from the user authorizes the particular panel-rule change or job-specific exception they request. Customer drawings, source notes, examples, inferred preferences and fit problems do not authorize an override. Flag conflicting source requirements instead of relaxing these rules. The already-approved shrinking of joined arrays within the rules remains allowed.

| Artwork | Physical stroke |
| --- | --- |
| Building exterior | 2 pt |
| Interior roof and wall lines, including dividers between attached wings | 1 pt |
| Individual panels / schematic array paths | 1.25 pt |
| Equipment rectangles | 1.5 pt |
| Callout leaders; solid/dashed road edges | 1 pt |
| Driveways, pools, fences and patios | 1 pt |

Fit geometry uniformly into the planned physical work zone; do not scale physical strokes, type or arrows with the map. Choose process-specific colors, typography and finishing below; cutlines and footer type are separate from map strokes. SVG dimensions and viewBox use one unit per point. Recheck weights if scaling in another application.

- **Rotation:** square the main structure to its nearest 0/45-degree orientation with one rigid rotation of the entire site. Keep relative building/array angles. Use shared `structure_id` values and `alignment.primary_structure` when known; otherwise the largest outline bounds are used. Do not independently snap or deform walls.
- **North:** use the editable **Illustrator Arrow 15** equivalent in `assets/north-arrow.json`, at **2 pt or 3 pt reference stroke**, with upright **18 pt or 25 pt N**, respectively. Rotate the needle; orbit N around the same pivot beyond the tail while leaving the glyph vertical. The 2/3 pt settings size the expanded Arrow 15 artwork; do not add a second outline stroke around the filled symbol. Supply `north_arrow.stroke_pt` and `label_size_pt`; do not reuse customer compass paths. Compensate source bearing by the site rotation, then snap to the nearest 45 degrees only within +/-10 degrees. Keep exact compensation outside that tolerance and retain raw/displayed values internally. Explicit corrections require `display_rotation_evidence`. Never invent a missing direction or copy another site's bearing.
- **Panels:** panels within each countable array **must touch edge-to-edge, with no overlapping interiors**, unless the user explicitly requests different spacing. Shared borders export once. Use **one common rectangular short/long size** per map and an invariant **1.25 pt** outline; portrait/landscape panels swap that same pair of dimensions. Preserve panel count, array membership, row/column arrangement, missing cells, array bearing and the array's source center. Individual panel centers may move within their own array to close gaps. When needed, shrink the common panel size and the joined array grids together around their fixed centers; never shrink isolated panels and leave gaps, move equipment, or alter a roof to make them fit. Keep at least **1 pt visible clearance, measured stroke-to-stroke**, from exterior walls, interior walls, roof lines and the final equipment rectangles. New scenes identify each array explicitly; do not merge separate arrays or fill missing cells. Countable ground-mounted arrays follow the same joined-grid rule; genuinely schematic rows/footprints without countable divisions retain their source representation as `solar_field`. Retain raw source corners internally. Flag an unresolved fit instead of varying panel sizes, dropping panels, overlapping interiors or cutting into other artwork.
- **Array callout wording:** use only the two exact phrases in [Solar-array callout wording](drawing-rules-callouts.md#solar-array-callout-wording), selected by source-confirmed rooftop or ground location.
- **Exterior versus interior walls:** use `building` only for the **2 pt exterior perimeter**, and `wall` for every **1 pt interior dividing wall**, including seams between attached building wings. Roof ridges/valleys remain `roof` at 1 pt. Split mixed source paths into exterior/interior portions; don't import an entire outline at 2 pt just because one portion bounds a roof section. Equipment attachment is governed only by [Equipment](#equipment).
- **Meaningful distinctions:** retain source device names/counts, new/existing designators, room qualifiers, partial-shutdown labels, energized-area boundaries and operational map notes. Use a reviewed `dash_pt` boundary for meaningful dashes. Never infer shutdown behavior from an array color or generic equipment name. Keep source-confirmed site orientation labels and identifiers. Place the ordered product's warning and footer in their own zones; preserve source lower shutdown text and legends above the footer. TFS receives no added array/extra callouts unless supplied/requested by its current source.

## Typography

Use **Arial Standard**, uppercase for map identification. Detail-size choices from the guideline are **8, 10, 13, 18, 25, 38, 50, 75 and 100 pt**, selected for the physical placard and text hierarchy. Equipment, array and property callouts must be **at least 8 pt**; do not shrink them to fix an overcrowded layout. Footer/part identifiers are the separate **5 pt, 100% horizontal-scale** exception. Preserve source-required wording and physical type height.

Horizontal font scaling is **70% through 100%, in 5% steps**: `width_scale` 0.70, 0.75, 0.80, 0.85, 0.90, 0.95 or 1.00. Do not stretch type taller, skew it, or use arbitrary compression such as 81%. Reflow the text and review the layout when replacing old values. Arrow-attached callouts are left- or right-justified toward their leader: a leader on the text's right uses right justification; a leader on its left uses left justification. Road names and north N use their own alignment rules.

## Production process and colors

Confirm the ordered manufacturing process before finishing. Set `production.process` to `laser`, `metal` or `label`; the existing laser workflow remains the legacy default, not evidence of an unknown material. A material name or SKU from another item cannot choose this map's process.

| Process | Map paths and normal type | Small type | Crossing backing | Illustrator production layer |
| --- | --- | --- | --- | --- |
| Laser-engraved placard | Green etching | **5-10 pt inclusive red; above 10 pt green** | White | `Laser` |
| Printed metal sign | Building Black | Building Black, including footer | White | Artwork in `Print`; cut paths only in `Flex Cut` |
| Printed label on red stock/background | White | White, including footer | **Red matching the background** | Artwork in `Print`; cut paths only in `Flex Cut` |

Use the approved process swatches in `PVLabels-All (U:)/art-department-templates/Art-Department-Swatches-2024.ai`: Laser for engraving, Screen Print for metal, Digital for labels, and Cut Lines for flex-cut paths. The PDF provides swatch names and appearances, not numerical spot-color definitions. Retain the established SVG preview colors (green `#00a651`, red `#ed1c24`, black `#000000`, white `#ffffff`) as previews; verify/map them to the actual production swatches in Illustrator. Metal is limited to in-stock swatches; flag a required unavailable color for ordering rather than substituting one or placing an order automatically.

The SVG carries editable paths/text and process/layer metadata; those tags are **not native Illustrator layers or spot swatches**. Apply and verify the named layers/swatches during production handoff. Keep cut paths separate from printable artwork. Process-specific cutline and bleed requirements live in [Zones and their authority](zone-layout.md#zones-and-their-authority).

## Equipment

This is the **single authoritative equipment section**, including box appearance, placement, device wording and scene metadata. Electrical/service panels here are equipment; solar-module rules remain above.

One plain, unfilled **1.5 pt rectangle per device**. Every box on a map uses the same **1.5:1 width-to-depth ratio**, with width **125% of the canonical Arrow 2 head's widest span** (measured perpendicular to its shaft). Width runs along the mounting wall; depth runs away from it. Dimensions are physical points, independent of map scale and customer glyph size. Apply the placement rules below before deciding whether a box belongs on a wall. Preserve device count and identity. Remove fills, Xs, strikes and invisible duplicates; retain the mounting wall. A mounting edge shared with its wall is the only intentional stacked stroke. Use direct callouts to the normalized boxes, following [Callouts](drawing-rules-callouts.md) for all arrow rules. Use the metadata table below for source-location fields.

Identify and label every source-confirmed main service panel, disconnect, inverter, subpanel, utility meter and combiner. Preserve additional named devices such as batteries, transformers and controllers when supplied. Device names, counts, existing/new distinctions and room/inside/outside qualifiers belong to their actual targets; never infer a device from an unlabeled roof mark. A source dashed enclosure is context, not a substitute for its individual device rectangles.

Keep each device on the actual map with a direct Arrow 2 callout to its full wording in labeled/finished output. Do not create numbered keys, separate equipment strips, duplicate equipment areas or new enlarged details to solve a fit problem. Existing numbers in device names remain. A source-supplied inset may be reproduced as the same equipment's detail, never as additional hardware; new insets require an explicit user request. The renderer does not automatically compose or link inset scenes.

If the source establishes only a device cluster, preserve the confirmed wall, order and identities without claiming measured individual spacing. Where separate locations cannot be recovered, record that limit; do not invent a wall, device count or second equipment area.

- **Touching or almost touching a wall:** if the source equipment box touches an interior or exterior wall, or has only a tiny drawing/scan gap consistent with wall attachment, place its mounting edge flush on that same wall. Keep the source inside/outside face and along-wall location. Judge the gap from the box edge to the wall in the original drawing, relative to the local line thickness and box size, before resizing the production symbol; do not judge it from the arrow tip or label.
- **Clear space from the wall:** if the source shows a distinct, meaningful gap, keep the equipment at its original source center. This applies both inside and outside the building. Being inside a building, being near the left wall, or having a nearest wall does not establish attachment. Do not move it to a wall for tidiness, label routing or a shorter arrow.
- **Unclear attachment:** inspect the source at higher zoom and check any explicit mounting detail. If attachment remains uncertain, preserve the source position and record the uncertainty rather than snapping to a guessed wall. Do not invent a universal distance in feet or inches for a schematic drawing.

Record the placement decision and source evidence explicitly for every equipment box using the metadata below. Do not leave it to automatic nearest-wall inference. Review the final box position against the original drawing after normalization; an arrow must follow the chosen box, not relocate it.

| Field | Use |
| --- | --- |
| `mount_structure` | Source building/wall `structure_id`. |
| `wall_segment` | Two source-coordinate points on the confirmed mounting wall. |
| `mount_side` | `inside`/`outside` for a confirmed wall attachment; `freestanding` to preserve a separated or uncertain box's source position, including inside a building. This renderer value disables wall snapping; it does not assert a physical installation type. |
| `wall_inward` | Required for an open/cropped wall: nonzero source vector perpendicular to the wall, pointing inside. |
| `box_rotation_deg` | Freestanding source-frame angle before the shared site rotation; default 0. |
| Callout `target_element` | Device ID; the arrow follows its production center. Keep the original source `target` as evidence. |

For a touching/nearly touching box, set `mount_structure`, `wall_segment` and `mount_side` for that same confirmed interior or exterior wall; open/cropped walls also require `wall_inward`. For a clearly separated box, retain its source coordinates, set `mount_side: "freestanding"`, omit wall-attachment fields and record the visible gap in `evidence`. Preserve the source position with the same setting when attachment is uncertain, and record that uncertainty. The renderer's legacy nearest-wall fallback is not source evidence: resolve and write the placement metadata before rendering new or revised scenes so separate runs cannot choose different walls. Boxes marked `freestanding` retain their source centers and need no building. The renderer calculates every box's dimensions from Arrow 2; legacy `box_size_pt` values do not override production sizing. The `equipment_rectangles` report records source bounds, wall contact, production center and actual dimensions.
