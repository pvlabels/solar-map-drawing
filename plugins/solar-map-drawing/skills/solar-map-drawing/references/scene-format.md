# Workbench commands and scene format

Requires Python 3.10+, `pymupdf`, and `Pillow`. No network requests are made by the workbench. Use an installed Python or the bundled runtime; on this project machine `python` works while the `py -3` launcher does not find an interpreter.

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

Create `tmp/solar-map-drawing/job/scene.json` using this structure (illustrative IDs and coordinates):

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

Roles: `building`, `roof`, `solar`, `equipment`, `context`, `leader`, `feature`. Do not select source `north` paths; use the canonical `north_arrow` instead. Perimeter, interior roof, panel and equipment roles receive 2, 1, 1.25 and 1.5 physical points respectively. Shared source paths retain their coordinates until a single site rotation and uniform fit are applied. An element can select one or several paths. Each source path can be used once; this prevents repeated path reuse. Adjacent modules can still share edges; consolidate coincident edges only as a separate, verified production step.

`job.work_order` is the WO number, such as `WO-288697` (or `288697`). If omitted, a reliable `WO-...` source filename is used. For one map, render the scene directly. Its SVG is named for the work order, with an item suffix only when explicitly supplied or present in the source filename.

For multiple maps, save each map scene with its own source crop and source-confirmed `job.item_letter` and `job.item_evidence`. For example, item B's scene can use `{"work_order":"WO-288697","map_count":2,"item_letter":"B","item_evidence":"Map marked B on page 4, matching order line 288697-B"}`. Then save an order scene listing every map scene, with paths relative to the order JSON.

```json
{
  "job": {"work_order": "WO-288697", "map_count": 2},
  "maps": ["A/scene.json", "B/scene.json"]
}
```

Pass `order.json` to the same `render` command. It produces one `WO-288697.svg` with separate map groups headed `WO-288697-A` and `WO-288697-B`. The renderer lays the maps out in item order with a gutter and retains their physical dimensions. For diagnostics, it saves a shared preview plus per-item source comparisons and overlays in the QA directory. Text-only placards and duplicate sheets do not increase the map count.

`structure_id` groups all building-outline fragments for the same structure. Provide the complete perimeter, splitting any source paths that mix exterior and interior edges. `alignment.primary_structure` chooses the main building; if omitted, the largest group's bounding area wins. The renderer chooses a representative dominant main wall and rotates it to its nearest multiple of 45 degrees. All buildings, roof lines, panels, equipment, and callout target points receive exactly the same transform. Relative angles between structures stay intact. `alignment.enabled: false` is reserved for explicitly requested raw diagnostic proofs; standard map output rotates automatically.

`layout.size_pt` is the physical output width and height. `map_box` is `[left, top, right, bottom]` in output points. It contains the uniformly fitted geometry; reserve surrounding space for callouts. Without `layout`, the source viewport is also the physical output canvas. The map's fit scale does not scale strokes, text, arrowheads, or the north symbol. Output uses point dimensions and baked coordinates, avoiding scaled SVG groups that would change stroke thickness.

For hand-traced geometry use `polygon`, `polyline`, or `path`. `path` takes `commands`, arrays beginning with `M` (two coordinates), `L` (two), `C` (six), or `Z` (none). Example circle: four cubic Bezier arcs and `Z`. For any manually specified geometry, `evidence` is required. Optional `solid: true` fills a symbol. For complex cutouts or holes, author and review the SVG explicitly instead of assuming the simple filled-path renderer will preserve source fill rules.

`callouts` use **output point coordinates** for x/y (text baseline) and `size_pt` (default 12). Text can be a string or array of lines. The optional `anchor` is `start`, `middle` or `end`. Each `target` is a **source-coordinate point**, transformed with the map automatically. Choose `side` (`left`, `right`, `top`, `bottom`) for the leader's label attachment. Use `elbow_x` or `elbow_y` in output points for simple orthogonal routes, or explicit `via` output points for reviewed custom routing. An empty `via` gives a direct approach.

`target_gap_pt` sets the starting setback from the target coordinate, with a minimum of 3 pt. The renderer increases it when nearby strokes are within 2 pt of the arrowhead envelope. Review the drawn gap and target alignment together. If the setback puts the head on the far side of an intervening outline, change the final approach so it stops just outside the intended symbol. Keep the final segment long enough for the setback and the shaft's approximately 5.30 pt inset behind the tip. Arrow 2 uses a 0.75 pt shaft and the bundled 100% outline. The 5 pt white clearance under the shaft can be disabled per leader with `clearance: false`.

Place callouts close to their target groups, stagger labels as needed, and use the shortest clear route with few elbows. Keep text readable. For callout-only edits, preserve `elements`, `layout`, `alignment`, `north_arrow` and all source `target` coordinates; change only label placement and leader routing. Do not retrace or refit the map to compact callouts.

Optional plain `labels` use output coordinates and `size_pt`, without leaders. Text is escaped as XML. There is no automatic semantic labeling or collision-routing solver; Codex lays out the labels and reviews the proof. The report warns about overlapping callout boxes, not every possible geometry/leader collision.

`north_arrow` uses output x/y for the needle tip, `height_pt` (default 34), and required `source_rotation_deg` (clockwise from up in displayed source coordinates). The renderer adds the site's rotation, then snaps the displayed result to the nearest multiple of 45 degrees when the difference is at most 10 degrees. Set `snap_tolerance_deg: 0` only for a specifically requested precise bearing. The internal report retains `north_direction.compensated_deg`, `display_deg`, the tolerance and mode. `display_rotation_deg` overrides the final bearing only with a required `display_rotation_evidence` explaining the user/source correction. The canonical symbol has a transparent left cutout, filled right half and upright N below. Do not use the customer's compass artwork. Omit this field and record uncertainty when no source direction is available.

`viewport` remains the source crop for diagnostic comparison and must stay within the source page. It is distinct from the final physical layout. `source-trace.svg` and `overlay.png` use the original orientation to verify tracing. The WO-named SVG and `map.png` show the aligned artwork with callouts and the canonical north symbol.

The renderer writes only the WO-named SVG to `--output` by default and prints its report to stdout. `--preview PATH` optionally writes one PNG to that path. `--diagnostics DIR` optionally writes `map.png`, `comparison.png`, `source-trace.svg`, `overlay.png`, `trace-transparent.png`, and `review.json` in a separate QA directory. Existing files are not deleted. Missing or changed source files cause an error before outputs are written. The report includes applied rotation, main structure, physical point weights, compensated/displayed north directions, output filename and source/output leader targets. Keep scenes/extraction data in the internal job folder for reuse, and deliver the SVG alone unless more is requested. It is not a native AI file or a completed placard template.
