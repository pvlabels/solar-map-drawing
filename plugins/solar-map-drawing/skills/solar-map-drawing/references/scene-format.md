# Workbench commands and scene format

For new work orders, read [zone-layout.md](zone-layout.md) first and add `placard` metadata tied to the exact sales-order item and source hash. The physical canvas comes from the confirmed production profile. The generic geometry example below illustrates source coordinates and is a legacy map-only example; do not copy its arbitrary canvas size as a new placard. New full output includes the cutline, source-confirmed warning and footer, with `zone_check` enforcing the reserved areas.

Requires Python 3.10+, `pymupdf`, and `Pillow`. No network requests are made by the workbench. Use the host-provided Python/file executor; do not assume a particular machine path, Python launcher or bundled interpreter.

```powershell
python PATH_TO_SKILL/scripts/map_workbench.py inspect "input.pdf" --output "tmp/solar-map-drawing/job/inspection"
python PATH_TO_SKILL/scripts/map_workbench.py extract "input.pdf" --page 3 --clip 100 120 600 500 --output "tmp/solar-map-drawing/job/source"
python PATH_TO_SKILL/scripts/map_workbench.py render "tmp/solar-map-drawing/job/scene.json" --output "Outputs/job"
# Optional internal visual check (does not populate the delivery folder):
python PATH_TO_SKILL/scripts/map_workbench.py render "tmp/solar-map-drawing/job/scene.json" --output "Outputs/job" --preview "tmp/solar-map-drawing/job/preview.png"
# Full QA only for initial/changed geometry or unresolved source details:
python PATH_TO_SKILL/scripts/map_workbench.py render "tmp/solar-map-drawing/job/scene.json" --output "Outputs/job" --diagnostics "tmp/solar-map-drawing/job/qa"
```

PDF-compatible Illustrator files and raster image files can also be opened. The inspection is the authority for page dimensions. For an image, its displayed point dimensions may differ from its pixel dimensions. For cropped `source.png`, approximate conversion is `page_x = crop_x0 + pixel_x * crop_width / preview_width` and similarly for y. Use actual preview dimensions from the manifest, not dimensions of an automatically resized chat image.

`manifest.json` retains the source file path/hash, one-based page number, page rotation, crop, text, and unclassified PDF paths. Each D-prefixed ID refers to its original page path index, so it stays stable across different crops of the same unchanged PDF. A path may include several disconnected subpaths. Cubic curves and quadrilateral corners are retained. Path bboxes can intersect the crop even when the visible stroke is elsewhere; inspect candidates before selecting them. Source PDF clipping, opacity, masks, fill behavior and hidden layers are not fully reconstructed by this simplified renderer. The source preview is the visibility reference.

Create `JOB/scene.json` in writable session storage using this structure (illustrative IDs and coordinates). For chat attachments, use the `job_dir` returned by `chat_job.py prepare`. New extraction manifests keep `source` relative to the manifest directory, so the complete job can move between machines; legacy absolute source paths remain supported in their original environment.

```json
{
  "job": {"work_order": "WO-288697", "map_count": 1},
  "manifest": "source/manifest.json",
  "viewport": [100, 120, 600, 500],
  "color": "#00a651",
  "alignment": {"primary_structure": "house"},
  "layout": {"size_pt": [576, 450], "map_box": [150, 110, 500, 390]},
  "uncertainties": [],
  "elements": [
    {"id": "house-outline", "structure_id": "house", "role": "building", "source_ids": ["D00001", "D00002"]},
    {"id": "roof-ridges", "role": "roof", "source_ids": ["D00003"]},
    {"id": "module-01", "role": "solar", "kind": "polygon", "points": [[220,240],[240,240],[240,275],[220,275]], "evidence": "Traced from upper-left module in the source crop."},
    {"id": "disconnect", "role": "equipment", "kind": "polygon", "points": [[198,280],[202,280],[202,284],[198,284]], "evidence": "Small mark touching left wall beside the disconnect callout."}
  ],
  "callouts": [
    {"text": ["AC DISCONNECT"], "x": 190, "y": 40, "size_pt": 12, "side": "left", "elbow_x": 110, "target": [198,282]}
  ],
  "north_arrow": {"x": 60, "y": 300, "height_pt": 34, "source_rotation_deg": 0}
}
```

Roles: `building`, `roof`, `wall`, `solar`, `solar_field`, `equipment`, `context`, `leader`, `feature`. Do not select source `north` paths; use the canonical `north_arrow` instead. Exterior perimeter uses `building` at 2 pt; interior dividers use `wall` at 1 pt, and ridges/valleys use `roof` at 1 pt. Panels/schematic arrays use 1.25 pt; equipment always uses 1.5 pt. Split source paths containing both an exterior and an interior wall. Shared source paths retain their coordinates until a single site rotation and uniform fit are applied. An element can select one or several paths. Each source path can be used once. Individual source modules may share edges; final export automatically retains only one visible stroke on a shared edge while preserving the source scene for revisions.

`job.work_order` is the WO number, such as `WO-288697` (or `288697`). If omitted, a reliable `WO-...` source filename is used. For one map, render the scene directly. Its SVG is named for the work order, with an item suffix only when explicitly supplied or present in the source filename.

For multiple maps, save each map scene with its own source crop and source-confirmed `job.item_letter` and `job.item_evidence`. For example, item B's scene can use `{"work_order":"WO-288697","map_count":2,"item_letter":"B","item_evidence":"Map marked B on page 4, matching order line 288697-B"}`. Then save an order scene listing every map scene, with paths relative to the order JSON.

Despite the legacy field name `item_letter`, source-confirmed codes support one to three letters followed by zero to three digits, such as `AC`, `BD`, `CZ` or `A1`. Supply `item_evidence` for these explicitly; do not infer a multi-letter item from a customer abbreviation in a filename. Order layout uses alphabetic item order (Z then AA), with numeric suffixes sorted numerically (A2 before A10). Printed quantity and repeated proofs do not create additional maps.

```json
{
  "job": {"work_order": "WO-288697", "map_count": 2},
  "maps": ["A/scene.json", "B/scene.json"]
}
```

Pass `order.json` to the same `render` command. It produces one `WO-288697.svg` with separate maps headed `WO-288697-A` and `WO-288697-B`. The renderer lays them out in item order with a gutter, bakes their translations into coordinates and retains physical dimensions. The exported paths/text are loose, with `data-map` attributes for source association, and no grouping or clipping masks. Diagnostics retain per-item source comparisons and overlays. Text-only placards and duplicate sheets do not increase the map count.

`structure_id` groups all building-outline fragments for the same structure. Provide the complete perimeter, splitting any source paths that mix exterior and interior edges. `alignment.primary_structure` chooses the main building; if omitted, the largest group's bounding area wins. The renderer chooses a representative dominant main wall and rotates it to its nearest multiple of 45 degrees. All buildings, roof lines, panels, equipment, and callout target points receive exactly the same transform. Relative angles between structures stay intact. `alignment.enabled: false` is reserved for explicitly requested raw diagnostic proofs; standard map output rotates automatically.

`layout.size_pt` is the physical output width and height. `map_box` is `[left, top, right, bottom]` in output points. It contains the uniformly fitted geometry; reserve surrounding space for callouts. Without `layout`, the source viewport is also the physical output canvas. The map's fit scale does not scale strokes, text, arrowheads, or the north symbol. Output uses point dimensions and baked coordinates, avoiding scaled SVG groups that would change stroke thickness.

For hand-traced geometry use `polygon`, `polyline`, or `path`. `path` takes `commands`, arrays beginning with `M` (two coordinates), `L` (two), `C` (six), or `Z` (none). Example circle: four cubic Bezier arcs and `Z`. For any manually specified geometry, `evidence` is required. Optional `solid: true` fills a symbol. For complex cutouts or holes, author and review the SVG explicitly instead of assuming the simple filled-path renderer will preserve source fill rules.

**Solar production outlines:** every countable module is one closed convex four-corner source path. Use `mount_surface: "roof"` or `"ground"`; centers inside a complete building footprint identify rooftop modules when metadata is absent. Open/overlapping footprints need explicit surface metadata. All countable modules use one common rectangular short/long size per map at **1.25 pt**, with portrait/landscape orientations swapping the same pair. Within each array, neighboring panels **share exact edges without interior overlap**. Shrink the common module size and each joined grid together about its original array center to retain at least **1 pt visible stroke-to-stroke clearance from exterior/interior walls, roof lines and normalized equipment rectangles**. Panel centers may move within their source array; preserve count, cells, missing positions, group membership and array bearing. Do not move the array center, roof or equipment. Keep the original source polygons unchanged internally. Report dimensions, scale, arrays, cells, anchors and exceptions under `panel_clearance.uniform_modules`; `uniform_rooftop` remains a compatibility alias. `centers_preserved` is false because compaction can move individual modules; `array_anchors_preserved` is true. Collapse, ambiguous cells or an unresolved clearance stops export.

**Array identity and cells:** for new scenes, give every panel a source-confirmed `array_id`. Distinct IDs remain separate even when close. Prefer one element per panel. Optional `array_cell: [long_axis_index, short_axis_index]` gives integer grid positions along the array's canonical long-edge axis and its perpendicular. The long axis points right when mostly horizontal, or down when mostly vertical; its perpendicular is `[-uy, ux]`. Supply cells on every panel in that array when using them; duplicate cells are rejected. Stepped/missing cells stay empty. Without cells the renderer infers only an unambiguous regular source grid. Legacy scenes without IDs may infer clearly adjacent, same-bearing arrays without crossing roof/wall lines; verify the reported grouping. Separate mixed bearings into source-confirmed groups rather than guessing a new layout.

**Explicit spacing exception:** default `array_gap_pt: 0` means exact shared borders. A positive `array_gap_pt` is the requested visible space between panel strokes; all panels in that array must carry the same value plus `array_spacing_authorization: "user"` and `array_spacing_evidence` quoting the user's explicit request. The panel rules are locked: customer artwork, source notes and examples alone cannot authorize an exception. Mere gaps in customer artwork do not request spacing. Use `production.roof_gap_pt` and `production.equipment_gap_pt` for larger clearances; neither may be below 1 pt. Equipment clearance uses the final 1.5 pt rectangles, not their customer glyphs. Array-bound callout targets follow the chosen module's production center while retaining `source_target` as evidence.

**Interior walls:** `wall` is the interior-divider role, distinct from exterior `building` and roof `roof`. Split mixed source commands without moving junctions and retain evidence. For mounting on interior or open/cropped walls, use the [Equipment metadata](drawing-rules-production.md#equipment).

Equipment fields, placement decisions and report interpretation are defined together in [Equipment](drawing-rules-production.md#equipment).

**Schematic array representation:** individual countable modules always use `solar`. Use `solar_field` for source-confirmed schematic tracker rows, hatching or array-footprint paths with no recoverable module divisions, accompanied by `representation_evidence` describing that source evidence. This role preserves open rows and concave footprint paths on a 1.25 pt stroke; it does not generate a module grid. `panel_clearance.module_count` counts only individual modeled modules, while `schematic_field_elements` counts schematic elements; do not report that as zero installed modules. Schematic array strokes still must have the production roof gap. If they intersect/approach roof strokes, the renderer requires an explicitly reviewed clearance adjustment rather than guessing an inset of a schematic field.

**Meaningful dashed boundaries:** for a straight `feature`, `context` or schematic field element, set `dash_pt: [6,3]` (example physical dash/gap lengths) and optional `dash_phase_pt: 0`. Select lengths that retain the source meaning at the final reading size; these numbers are not fixed house style. An odd-length list repeats, as in SVG. The renderer materializes gaps in physical points before cleanup, yielding separated editable vectors with no SVG dash attributes, masks or phase resets during Illustrator editing. Dash phase continues across corners and resets at each M. Dashes on filled shapes, equipment and individual modules are rejected. Curved dashed paths need a reviewed straight trace; original source curves remain in the internal evidence. Selected source paths with nonempty dashes raise a warning unless the scene supplies `dash_pt` or explains an intentional solid conversion with `dash_conversion_evidence`. Preserve partial-shutdown and fence meanings; a dashed boundary is separate from the device rectangles.

`callouts` use **output point coordinates** for x/y (text baseline) and `size_pt` (default 13, minimum 8). Text can be a string or array of lines. The optional `anchor` is `start`, `middle` or `end`. `width_scale` can reproduce source-confirmed condensed type (for example 0.80 for condensed source type); this changes editable text width only, never map strokes. Its measured width is used for routing and alignment. Each `target` is a **source-coordinate point**, transformed with the map automatically. Choose `side` (`left`, `right`, `top`, `bottom`) for the leader's label attachment. Use `elbow_x` or `elbow_y` in output points for simple orthogonal routes, or explicit `via` output points for reviewed custom routing. An empty `via` gives a direct approach.

Follow [Callouts](drawing-rules-callouts.md) for arrow style, routing angles, text attachments and all clearances. `allow_45: true` enables an exact 45-degree segment for that leader. The renderer normalizes routes without changing source target evidence and reports the final `shaft_route`; `target_element` binds the production endpoint to the equipment rectangle.

For nearby equipment callouts, add `group: "equipment-left"` (or another local group name) and a top-level layout entry:

```json
{
  "callout_layout": {
    "equipment-left": {"margin_x": 32, "anchor": "start", "gap_pt": 6}
  }
}
```

The renderer keeps the group's existing top-to-bottom order, aligns the text to that margin and stacks the complete text blocks with the same 6 pt gap. `anchor` can be `start` for a left margin or `end` for a right margin; optional `top` sets the first block's upper bound. Without a layout entry, grouped labels default to a shared left margin and 6 pt block gaps. Use consistent `size_pt` in a group, preserve all wording and source targets, and arrange separate nearby groups when a shared column would make leaders long. Review the resulting `text_bbox` values, routes and canvas fit. Old explicit `via` coordinates do not automatically move with the text; reroute those when grouping old labels.

`group` and `callout_layout` are scene layout metadata only; see [Clean export](drawing-rules-export.md) for final SVG structure. Shared module borders may belong to one neighboring output path while scenes retain individual closed modules. `export_cleanup` reports removed duplicate strokes and preserved leader backing strokes.

`target_gap_pt` requests the starting target setback; the renderer enforces the minimum and head clearances in [Callouts](drawing-rules-callouts.md). Legacy `clearance` is accepted for compatibility but no longer disables crossing gaps. Every rendered shaft has the required editable process-colored backing, recorded as `clearance: true` and `backing_width_pt` in its report. Background geometry is not cut for leader crossings.

For callout-only edits, preserve `elements`, `layout`, `alignment`, `north_arrow` and source `target` coordinates; change only label placement and routing.

When creating or revising an array identification label, normalize its `text` to the exact [solar-array callout wording](drawing-rules-callouts.md#solar-array-callout-wording) before measuring text or routing leaders. Select the phrase using source-confirmed roof/ground placement (`mount_surface` where supplied); retain extra operational wording separately as map notes, not as additions to the array phrase.

Optional plain `labels` use output coordinates and `size_pt`, without leaders. Array text outside its actual array footprint must instead be a `callout` with a target and canonical head. Bind it using `array_element` to its source-confirmed `solar`/`solar_field` ID; its tip cannot be pulled back to an intervening house edge. Text wholly inside its own array can omit a leader. Text is escaped as XML. There is no automatic semantic labeling or collision-routing solver; Codex lays out the labels and reviews the proof. The report warns about overlapping callout boxes, not every possible geometry/leader collision.

`north_arrow` uses output x/y for the needle tip, `stroke_pt` (2 or 3, default 3), optional `label_size_pt` (18 or 25; defaults to 18 for 2 pt and 25 for 3 pt), and required `source_rotation_deg` (clockwise from up in displayed source coordinates). The renderer adds the site's rotation, then snaps the displayed result to the nearest multiple of 45 degrees when the difference is at most 10 degrees. Set `snap_tolerance_deg: 0` only for a specifically requested precise bearing. The internal report retains `north_direction.compensated_deg`, `display_deg`, the tolerance and mode. `display_rotation_deg` overrides the final bearing only with a required `display_rotation_evidence` explaining the user/source correction. Legacy `height_pt` selects the 2 pt preset below 28 pt or the 3 pt preset otherwise; use explicit `stroke_pt` for revised scenes. The Arrow 15 symbol has a transparent left cutout, filled right half and an upright N whose position orbits with the needle, as specified in [Production drawing rules](drawing-rules-production.md). Rotate the N center's offset from the needle tip by the final displayed bearing (after compensation, snapping or an evidenced override), then place unrotated text at that position. Retain a fixed offset radius for a given symbol size and keep the glyph beyond the tail with visible separation. Do not rotate the letter or anchor it below the rotated bounds. Map-only output still omits N. Do not use the customer's compass artwork. Omit this field and record uncertainty when no source direction is available.

`viewport` remains the source crop for diagnostic comparison and must stay within the source page. It is distinct from the final physical layout. `source-trace.svg` and `overlay.png` use the original orientation to verify tracing. The WO-named SVG and `map.png` show the aligned artwork with callouts and the canonical north symbol.

The renderer writes only the WO-named SVG to `--output` by default and prints its report to stdout. `--preview PATH` optionally writes one PNG to that path. `--diagnostics DIR` optionally writes `map.png`, `comparison.png`, `source-trace.svg`, `overlay.png`, `trace-transparent.png`, and `review.json` in a separate QA directory. Existing files are not deleted. Missing or changed source files cause an error before outputs are written. The report includes applied rotation, main structure, physical point weights, compensated/displayed north directions, output filename and source/output leader targets. Keep scenes/extraction data in the internal job folder for reuse, and deliver the SVG alone unless more is requested. It is not a native AI file. A scene with confirmed `placard` metadata produces a complete cutline/warning/footer layout; a legacy scene without it remains a map-only rendering and must not be claimed as a size-verified placard.


## Production lettering and roads

Production text sizes, allowed `width_scale` values and per-process colors are defined in [Production drawing rules](drawing-rules-production.md#typography). Set `production.process` to `laser`, `metal` or `label`; optional `production.ink_color` / `background_color` must be approved six-digit SVG preview colors. Laser small type is red through 10 pt inclusive; metal/label small type retains its process ink. Native swatches, print bleed and Illustrator layer assignment still require production handoff verification.

Follow [Roads](drawing-rules-roads.md) for source identity, corner lots, full-area spans and proportional layout. New/revised road scenes declare a `road_layout.drawing_area` in **final output points** and each road's final `layout_side`. This rectangle frames the usable map-and-callout area within the work zone; it excludes warning/footer/operational-note and hole-clearance zones. Its boundary includes the outer road strokes. Keep `layout.map_box` inside the road lanes with space for labels and callouts.

```json
{
  "road_layout": {
    "drawing_area": [12, 110, 344, 332],
    "lane_width_ratio": 0.065
  },
  "roads": [
    {"id": "side-street", "source_side": "left side of house",
     "layout_side": "left", "evidence": "Current source shows the left street",
     "label": {"text": "SIDE STREET", "size_pt": 8}},
    {"id": "front-street", "source_side": "front/bottom side of house",
     "layout_side": "bottom", "evidence": "Current source shows the corner street",
     "label": {"text": "FRONT STREET", "size_pt": 8}}
  ]
}
```

Allowed `layout_side` values are `left`, `right`, `top`, `bottom`, assigned from the source relationship after the shared site rotation. `source_side` and `evidence` remain mandatory; optional source `points` are evidence and do not set the extended output length. Do not infer the final side from a street name. The helper supports one street per side; more complex same-side roads/junctions require an explicit reviewed layout.

The lane width is `lane_width_ratio` times the shorter drawing-area dimension (default 0.065), with a 10 pt readability minimum. Road strokes and dash/gap lengths follow [Roads](drawing-rules-roads.md): 1 pt with `[20,24]` physical-point dashes. Legacy `dash_ratios` no longer rescales the pattern. Drawing-area endpoints account for half the stroke width. Adjacent solid edges join at corners; dashed edges span the outer boundary. Names are centered in their own lanes and oriented outward except on top; map-only suppresses names.

Full-span roads are composed after the source site's fit, so extending them cannot rescale or distort buildings, panels or equipment. Recompute `drawing_area` from the planned work zone whenever the map size changes. Review every road/name against reserved zones and the site's actual side relationships.

Legacy scenes without `road_layout` retain the two-source-point helper, signed `outer_offset_pt` and optional `dash_pt`. That helper snaps each segment to a cardinal axis while retaining its center and length; it does **not** implement full-area extension. Migrate new/revised road layouts to the explicit drawing-area form. Old `label.x/y` values do not set label placement. Do not duplicate helper edges as context paths.

## Direct layout invariants

Follow the single [Equipment section](drawing-rules-production.md#equipment) for direct callouts, source clusters and source-supplied details. Do not duplicate those rules here.

Trace the source roof graph, including every corner and shared junction, before laying out callouts. Preserve that trace internally and view a registration overlay. A plausible-looking replacement roof, guessed attached wing or broad gap cut through the roof is a failed trace.

`alignment.orientation_step_deg` defaults to 45. A reviewed value of 90 squares the selected main edge to a cardinal direction when a flat main structure gives a clearer direct-callout layout. Both retain one rigid site rotation; north compensates by that exact rotation. Do not rotate individual buildings or panels independently.

The 1 pt module clearance applies to roof/building strokes, not an invented 1 pt opening inside every module. Small source modules must still retain a visible interior opening and their 1.25 pt outline; opposing strokes cannot overlap. The renderer retains a 0.25 pt minimum visible opening as its collapse guard. This does not authorize deleting divisions, altering counts or using a schematic role for countable modules.


## Three output modes

Use scene/order `output_mode: "map-only"`, `"map-labeled"` or `"finished"`, or the equivalent `--mode` on `chat_job.py render`/`map_workbench.py render`. CLI mode overrides the stored mode for a revision without changing the scene file. An order mode applies to every child map, and mixed child modes are rejected unless an explicit order/CLI mode selects one scope.

`map-only` removes callouts, plain labels, source elements classified `leader`, road labels and north N before routing; multi-map visible headings are omitted too. It retains geometry, equipment, meaningful boundary strokes, road edges and the canonical north needle. `map-labeled` retains full direct map labels/leaders and north N but exports no placard chrome. `finished` requires confirmed `placard` metadata and exports its warning, notes, cutline, resolved holes and footer even if an older scene had `include_chrome: false`. The selected scene is copied internally; original source geometry/layout/evidence remains unchanged. Legacy callers without a mode preserve their prior behavior; new skill calls always select a mode.

The two map stages preserve planned work zones. Unknown finishing holes are deferred, not guessed. A new map-only/labeled job without a measured production profile can use confirmed nominal order dimensions for an explicitly identified editing canvas, plus `order_context` and a reviewed `layout.map_box`. This is map artwork, not a verified manufacturing cut size. Finished mode continues to reject unconfirmed physical production dimensions.
