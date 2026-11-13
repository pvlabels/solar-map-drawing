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

**Solar production outlines:** every countable source module is one closed convex four-corner path. Mark rooftop modules `mount_surface: "roof"` and ground modules `"ground"`; rooftop centers inside a complete building footprint are recognized when explicit metadata is absent. Open/overlapping building footprints need explicit roof metadata. After fitting, rooftop modules become rectangles of one common short/long size for the whole map, preserving each center, long-axis bearing, count and grouping. Portrait and landscape layouts swap the same dimensions. One common reduction solves 1 pt roof/wall clearance and avoids overlapping module interiors or near-parallel doubled strokes; exact shared edges/corners remain allowed. Rooftop modules never use unequal edge-by-edge squeezing. The report's `panel_clearance.uniform_rooftop` records the common output dimensions, scale, count and invariant 1.25 pt stroke. The original source polygons remain unchanged internally. Ground arrays retain existing edge-specific roof clearances and source representation; `module_insets_pt` records those edge adjustments, not rooftop standardization. A common-size collapse or crossing stops export rather than deleting modules or varying rooftop dimensions.

**Interior walls:** `wall` is a 1 pt path role, separate from the 2 pt exterior `building` role. A shared divider between attached wings is interior even when it was part of a source roof-section outline. Split the original commands without moving junctions; retain source evidence for each portion. `wall` paths participate in roof clearance and equipment mounting. Equipment on an open interior wall needs explicit `mount_structure` matching that wall's `structure_id`, `wall_segment`, `mount_side`, and perpendicular `wall_inward` pointing into the confirmed reference structure. Its rectangle remains 1.5 pt and exactly flush; the interior wall does not become 2 pt to support mounting.

**Equipment production rectangles:** create one equipment element per device, preserving its source glyph/target evidence. Output replaces all equipment paths, fill and strikes with one plain **unfilled 1.5 pt rectangle**. Set `mount_structure` to the building's `structure_id`, `wall_segment` to two source-coordinate points on its confirmed exterior perimeter, and `mount_side` to `outside` or `inside`. An explicitly indoor panel remains inside, touching the interior face of that exterior wall. Missing mounting metadata falls back to the nearest perimeter and source-center containment, so specify it when corners, multiple structures or wording make that ambiguous. Complete closed perimeters allow inferred wall faces; use the explicit open-perimeter metadata below when the source is genuinely cropped.

**Freestanding equipment:** use `mount_side: "freestanding"` only when confirmed by the source, as on a solar farm's transformer/inverter pad. The production rectangle is centered at the transformed source glyph's bounds center and never projected onto a building. No building is required. `box_size_pt` still sets physical dimensions; optional `box_rotation_deg` gives the box's source-frame angle before the shared map rotation (default 0). The report records `mount_side: "freestanding"`, unchanged source/production center, and null wall/structure fields. Freestanding boxes have no equipment/wall overlap exception. Do not apply this mode to a wall device simply to avoid resolving its mounting segment.

**Open/cropped building perimeter:** preserve source-confirmed open outline segments. For a device on such a perimeter, explicitly set `wall_segment`, `mount_side: "inside"` or `"outside"`, and `wall_inward: [dx,dy]`. The latter is a nonzero source-coordinate direction vector pointing into the building, perpendicular to that wall. The renderer rotates it with the site and uses the confirmed face without inventing closure across a crop edge. Without these fields it stops for source review. Example: a horizontal source wall at y=100 with the house below it can use `wall_segment: [[20,100],[160,100]], wall_inward: [0,1]`.

**Schematic array representation:** individual countable modules always use `solar`. Use `solar_field` for source-confirmed schematic tracker rows, hatching or array-footprint paths with no recoverable module divisions, accompanied by `representation_evidence` describing that source evidence. This role preserves open rows and concave footprint paths on a 1.25 pt stroke; it does not generate a module grid. `panel_clearance.module_count` counts only individual modeled modules, while `schematic_field_elements` counts schematic elements; do not report that as zero installed modules. Schematic array strokes still must have the production roof gap. If they intersect/approach roof strokes, the renderer requires an explicitly reviewed clearance adjustment rather than guessing an inset of a schematic field.

**Meaningful dashed boundaries:** for a straight `feature`, `context` or schematic field element, set `dash_pt: [6,3]` (example physical dash/gap lengths) and optional `dash_phase_pt: 0`. Select lengths that retain the source meaning at the final reading size; these numbers are not fixed house style. An odd-length list repeats, as in SVG. The renderer materializes gaps in physical points before cleanup, yielding separated editable vectors with no SVG dash attributes, masks or phase resets during Illustrator editing. Dash phase continues across corners and resets at each M. Dashes on filled shapes, equipment and individual modules are rejected. Curved dashed paths need a reviewed straight trace; original source curves remain in the internal evidence. Selected source paths with nonempty dashes raise a warning unless the scene supplies `dash_pt` or explains an intentional solid conversion with `dash_conversion_evidence`. Preserve partial-shutdown and fence meanings; a dashed boundary is separate from the device rectangles.

`box_size_pt: [12,10]` is the default symbol width along the wall and depth normal to it; choose another readable size for a crowded wall when needed. The 1.5 pt stroke is fixed. Its mounting path edge lies exactly on the wall centerline: the mounting offset is zero, not half either stroke width. The resulting equipment-edge/wall-edge overlap is the intentional exception to duplicate-stroke removal. Inside/outside equipment at the same along-wall position may share that mounting edge. Other equipment overlaps require a size or source-position correction. Interior strikes are trimmed out of the actual vectors; the mounting wall line is retained. No duplicate helper rectangle, opaque fill, clip path or mask is exported. Callouts should have `target_element` equal to the equipment ID plus the original source-coordinate `target` for evidence. The production arrow targets the rectangle center, choosing a perpendicular approach if a wall blocks the parallel one. The report's `equipment_rectangles` records original bounds, production center, wall contact, segment, side and size.

`callouts` use **output point coordinates** for x/y (text baseline) and `size_pt` (default 12). Text can be a string or array of lines. The optional `anchor` is `start`, `middle` or `end`. `width_scale` can reproduce source-confirmed condensed type (for example 0.81 for TFS Arial Narrow); this changes editable text width only, never map strokes. Its measured width is used for routing and alignment. Each `target` is a **source-coordinate point**, transformed with the map automatically. Choose `side` (`left`, `right`, `top`, `bottom`) for the leader's label attachment. Use `elbow_x` or `elbow_y` in output points for simple orthogonal routes, or explicit `via` output points for reviewed custom routing. An empty `via` gives a direct approach.

Every shaft segment, including the arrowhead approach, must be horizontal or vertical. `allow_45: true` permits an exact 45-degree diagonal on that particular leader when it helps; arbitrary diagonals are converted to right-angle elbows. Routing never changes the evidence target; equipment endpoint normalization follows its rectangle as described above. An empty `via` gives a straight line only at a permitted angle and with a valid text attachment. The report includes each rendered `shaft_route` for angle checks. Keep the final approach long enough for the head and target clearance, and review repairs for unnecessary corners or crossings.

For `side: left` or `right`, the initial segment must extend horizontally outward from the text by at least **6 pt** before turning. Aim for a short 6-10 pt tail where the nearby elbow permits; shift the text if its end nearly aligns with the vertical shaft. A side attachment must not become a vertical line beside the last character. `side: top` or `bottom` attaches at the actual text-block center and permits a straight centered vertical leader. The normal text gap is 4 pt. The renderer can add a dogleg to preserve a side tail, but prefer a clean label placement and one elbow. Example: for a right-side tail ending at `target_x`, set the text's right edge near `target_x - 4 - 8` and use a horizontal-then-vertical route. Source targets remain evidence; equipment `target_element` remaps only the production endpoint to the standardized box.

For nearby equipment callouts, add `group: "equipment-left"` (or another local group name) and a top-level layout entry:

```json
{
  "callout_layout": {
    "equipment-left": {"margin_x": 32, "anchor": "start", "gap_pt": 6}
  }
}
```

The renderer keeps the group's existing top-to-bottom order, aligns the text to that margin and stacks the complete text blocks with the same 6 pt gap. `anchor` can be `start` for a left margin or `end` for a right margin; optional `top` sets the first block's upper bound. Without a layout entry, grouped labels default to a shared left margin and 6 pt block gaps. Use consistent `size_pt` in a group, preserve all wording and source targets, and arrange separate nearby groups when a shared column would make leaders long. Review the resulting `text_bbox` values, routes and canvas fit. Old explicit `via` coordinates do not automatically move with the text; reroute those when grouping old labels.

`group` and `callout_layout` are scene layout metadata only. Final SVG exports are flattened into loose paths and text; stroke-only disconnected pieces are separate objects. No `g`, `defs`, `clipPath`, `mask`, invisible path or white clearance-underlay path is delivered. A source-confirmed horizontal type matrix may remain on an individual editable text node; all group translations and map geometry are baked. Finishing paths use their own semantic roles and fixed physical weights. `clearance: true` is the legacy background-cutting behavior. Review it carefully: preserve roof topology, prefer rerouting or physically trimmed leader crossings, and do not remove large roof/perimeter segments for annotations. Shared/reversed/partially coincident linear strokes and exact coincident cubic strokes are consolidated, retaining the greatest required stroke width; equipment mounting edges on wall paths are preserved. Shared module borders can therefore belong to one neighboring output path rather than to two closed output rectangles. Source scenes still retain individual closed modules for editing and counts. `export_cleanup` reports removed overlap segments/length, permitted equipment-wall edges and zero exported groups/clipping paths. Filled arrowheads and north-symbol cutouts remain visible vector artwork.

`target_gap_pt` sets the starting setback from the target coordinate, with a minimum of 3 pt. The renderer increases it when nearby strokes are within 2 pt of the arrowhead envelope. Review the drawn gap and target alignment together. If the setback puts the head on the far side of an intervening outline, change the final approach so it stops just outside the intended symbol. Keep the last bend at least the whole head depth (about 7.46 pt) plus 6 pt of visible straight shaft behind the final tip, in addition to its target setback. Keep 2 pt between entire heads and between any head and another leader. Intermediate jogs below 4 pt are rejected. Closely spaced targets may need different approaches or bounded longitudinal staggering; a valid angle alone does not establish clearance. Arrow 2 uses a 0.75 pt shaft and the bundled 100% outline. The 5 pt corridor cut into crossed background vectors can be disabled per leader with `clearance: false`; no white backing stroke is exported.

Place callouts close to their target groups, stagger labels as needed, and use the shortest clear route with few elbows. Keep text readable. For callout-only edits, preserve `elements`, `layout`, `alignment`, `north_arrow` and all source `target` coordinates; change only label placement and leader routing. Do not retrace or refit the map to compact callouts.

Optional plain `labels` use output coordinates and `size_pt`, without leaders. Array text outside its actual array footprint must instead be a `callout` with a target and canonical head. Bind it using `array_element` to its source-confirmed `solar`/`solar_field` ID; its tip cannot be pulled back to an intervening house edge. Text wholly inside its own array can omit a leader. Text is escaped as XML. There is no automatic semantic labeling or collision-routing solver; Codex lays out the labels and reviews the proof. The report warns about overlapping callout boxes, not every possible geometry/leader collision.

`north_arrow` uses output x/y for the needle tip, `height_pt` (default 34), and required `source_rotation_deg` (clockwise from up in displayed source coordinates). The renderer adds the site's rotation, then snaps the displayed result to the nearest multiple of 45 degrees when the difference is at most 10 degrees. Set `snap_tolerance_deg: 0` only for a specifically requested precise bearing. The internal report retains `north_direction.compensated_deg`, `display_deg`, the tolerance and mode. `display_rotation_deg` overrides the final bearing only with a required `display_rotation_evidence` explaining the user/source correction. The canonical symbol has a transparent left cutout, filled right half and upright N below. Do not use the customer's compass artwork. Omit this field and record uncertainty when no source direction is available.

`viewport` remains the source crop for diagnostic comparison and must stay within the source page. It is distinct from the final physical layout. `source-trace.svg` and `overlay.png` use the original orientation to verify tracing. The WO-named SVG and `map.png` show the aligned artwork with callouts and the canonical north symbol.

The renderer writes only the WO-named SVG to `--output` by default and prints its report to stdout. `--preview PATH` optionally writes one PNG to that path. `--diagnostics DIR` optionally writes `map.png`, `comparison.png`, `source-trace.svg`, `overlay.png`, `trace-transparent.png`, and `review.json` in a separate QA directory. Existing files are not deleted. Missing or changed source files cause an error before outputs are written. The report includes applied rotation, main structure, physical point weights, compensated/displayed north directions, output filename and source/output leader targets. Keep scenes/extraction data in the internal job folder for reuse, and deliver the SVG alone unless more is requested. It is not a native AI file. A scene with confirmed `placard` metadata produces a complete cutline/warning/footer layout; a legacy scene without it remains a map-only rendering and must not be claimed as a size-verified placard.


## Production lettering and roads

Every editable text object below **10 pt** exports in small-engraving red `#ed1c24`. Exactly 10 pt retains the regular artwork color. Leaders, road lines and other map strokes retain their specified color/weight; this is not permission to shrink readable text. Condensed type and parallel road lettering retain text-only matrices, preserving physical type height. Geometry matrices remain disallowed.

For a street, `roads` supplies a solid near edge and separated dashed outer strokes at 0.75 pt. Source endpoints participate in the single site transform, then the road alone snaps to the nearest cardinal axis around its center, retaining its length. The geometry fit uses the normalized road extent. The final road is always horizontal or vertical; no 45-degree street is allowed. A source curve or bend is redrawn schematically with horizontal/vertical legs, preserving the correct side and meaningful connection. Buildings and north are not changed to straighten the street.

```json
{"roads":[{"id":"street","points":[[890,100],[890,310]],
  "source_side":"right/front side of house","outer_offset_pt":-14,
  "evidence":"Source road on right; cardinal production street convention",
  "dash_pt":[18,18],"label":{"text":"SOURCE STREET","size_pt":7}}]}
```

The signed physical offset points away from the house. Lettering is automatically centered in the normalized lane and parallel to its 0/90-degree direction; old `label.x/y` values are accepted for old scenes but no longer position diagonal road text. Map-only suppresses the name. Do not select the same road edge again as a context path, and do not draw arbitrary-angle road segments manually. Street layout is schematic rather than surveyed, as explicitly requested by the user.

## Direct layout invariants

No generated numbered equipment key, separate equipment strip, new enlargement or simplified site overview is a default fit solution. Every device is a plain rectangle on its actual map and has a direct full-wording callout. Reproduce a source inset only when actually supplied, or create one only at the user's explicit request. Keep known individual modules on the actual site map; do not move their grid into a new detail to bypass a density check.

Trace the source roof graph, including every corner and shared junction, before laying out callouts. Preserve that trace internally and view a registration overlay. A plausible-looking replacement roof, guessed attached wing or broad gap cut through the roof is a failed trace.

`alignment.orientation_step_deg` defaults to 45. A reviewed value of 90 squares the selected main edge to a cardinal direction when a flat main structure gives a clearer direct-callout layout. Both retain one rigid site rotation; north compensates by that exact rotation. Do not rotate individual buildings or panels independently.

The 1 pt module clearance applies to roof/building strokes, not an invented 1 pt opening inside every module. Small source modules must still retain a visible interior opening and their 1.25 pt outline; opposing strokes cannot overlap. The renderer retains a 0.25 pt minimum visible opening as its collapse guard. This does not authorize deleting divisions, altering counts or using a schematic role for countable modules.


## Three output modes

Use scene/order `output_mode: "map-only"`, `"map-labeled"` or `"finished"`, or the equivalent `--mode` on `chat_job.py render`/`map_workbench.py render`. CLI mode overrides the stored mode for a revision without changing the scene file. An order mode applies to every child map, and mixed child modes are rejected unless an explicit order/CLI mode selects one scope.

`map-only` removes callouts, plain labels, source elements classified `leader`, road labels and north N before routing; multi-map visible headings are omitted too. It retains geometry, equipment, meaningful boundary strokes, road edges and the canonical north needle. `map-labeled` retains full direct map labels/leaders and north N but exports no placard chrome. `finished` requires confirmed `placard` metadata and exports its warning, notes, cutline, resolved holes and footer even if an older scene had `include_chrome: false`. The selected scene is copied internally; original source geometry/layout/evidence remains unchanged. Legacy callers without a mode preserve their prior behavior; new skill calls always select a mode.

The two map stages preserve planned work zones. Unknown finishing holes are deferred, not guessed. A new map-only/labeled job without a measured production profile can use confirmed nominal order dimensions for an explicitly identified editing canvas, plus `order_context` and a reviewed `layout.map_box`. This is map artwork, not a verified manufacturing cut size. Finished mode continues to reject unconfirmed physical production dimensions.
