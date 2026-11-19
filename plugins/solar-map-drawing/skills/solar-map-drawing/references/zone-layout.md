# Size-first placard zones

Use this before fitting a new work-order map. Finished output includes the cutline, warning wording and footer. Map-only and map-labeled retain this work-zone plan but omit finishing objects. The physical ordered item determines the frame; the source site's aspect ratio does not determine the artboard.

## Read the order before drawing

`chat_job.py prepare` now writes `order-layout-candidates.json` before map tracing. It reads readable packing-slip rows by their physical position, associating each item code with its SKU, explicit dimensions, source page/hash, hole request and branding restrictions. It does not classify every custom placard as a map. Match candidate rows to the actual map item, site identity and current drawing. Quantity two means two copies unless the order supplies two distinct maps.

Inspect the actual order row, especially custom sizes, wraparound rows, ranges, a missing item-code hyphen, mismatched SKUs and repeat rows with conflicting dimensions. A source typo such as a missing separator is flagged for visual confirmation. A scanned order may need visual reading; the helper must not substitute its PDF page dimensions or another job's size. Inch fractions, decimal inches and explicitly stated mm/cm/point dimensions are supported; bare `5 x 5` without units remains unconfirmed. Preserve width/height order unless the source establishes a rotated product orientation.

Copy the confirmed row into `placard.order`: `work_order`, `sku`, `item_code`, `nominal_size_in`, `source_page`, `source_sha256` and `order_row_evidence`. Copy any `holes_requested` or `branding_restricted` result. The source hash must match the extraction manifest. Keep leading zeros in the printed SKU; `4-55` does not become `04-650`. Product notes about a label elsewhere on the order do not govern this map's footer.

## Ordered size versus production cutline

`assets/placard-profiles.json` contains measured production sizes and physical finishing conventions. These are discrete profiles, not a universal percentage or a requirement to make every map square.

| Ordered item | Profile | Actual cutline, pt | Evidence |
| --- | --- | --- | --- |
| 04-651, 4 × 4 in | `stock-04-651` | 284.4 × 284.4 | Local template and finished artwork |
| 04-645, 4 × 6 in | `stock-04-645` | 284.4 × 428.4 | Older and recent matched orders/artwork |
| 04-650, 5 × 5 in | `stock-04-650` | 356.4 × 356.4 | Template and matched orders/artwork |
| Generic 5 × 5 in plastic map | `plastic-5-square` | 356.4 × 356.4 | Matched 4-55 map orders; warning must be supplied |
| 04-647, 5 × 6 in | `stock-04-647` | 356.4 × 428.4 | Local template |
| 04-644, 5 × 7 in | `stock-04-644` | 356.4 × 500.4 | Template and matched orders/artwork |
| 04-682, 5 × 7.75 in | `plastic-5x7.75` | 356.4 × 558 | Matched artwork; full height is intentional |
| TFS 04-1, 5.5 × 5.5 in | `tfs-5.5-square` | 392.4 × 392.4 | Repeated matched TFS production artwork |
| 04-649, 6.5 × 6.5 in | `stock-04-649` | 464.4 × 464.4 | Template and matched Scudder artwork |
| Custom 6.5 × 6.5 in plastic map | `plastic-6.5-square` | 464.4 × 464.4 | Matched custom 04-1 artwork; supply warning |
| 04-648, 8 × 8 in | `stock-04-648` | 572.4 × 572.4 | Local template |
| Plastic directory, 11 × 8.5 in | `directory-11x8.5` | 788.4 × 608.4 | Repeated matched Hoosier artwork |

The common 0.05-inch reduction applies to each listed dimension where measured. The 5 × 7.75 family demonstrates that it is not universal. Never subtract again from a measured actual cut size. Do not apply plastic sizing to an aluminum sign, different manufacturing process or unmeasured custom size. For another size/material, supply `production_size_pt` and `production_size_evidence` from an approved/measured source, with a reviewed `safe_inset_pt`; otherwise complete independent tracing and resolve the production size before full export. A SKU's usual size cannot override the current order's explicit custom dimensions.

## Zones and their authority

**Cutline and bleed:** retain the actual ordered/measured frame and confirmed shape. Laser placards retain the measured cyan `#00aeef` **0.001 pt** convention; the PDF specifies **1 pt flex-cut paths for metal and labels** and **10 pt bleed-border strokes for printed signs and labels**. Bleed follows the approved print template/color boundary outside the trim; it is not a heavier cutline, an inset or permission to enlarge the nominal trim size. Verify it in the print handoff; the basic SVG finisher does not automatically reconstruct stock warning-band colors or bleed artwork. Keep cut paths separate from print content. Rounded corners require `cutline.corner_radius_pt` and `shape_evidence`; holes require confirmed diameters/positions. SVG colors/layer tags require the production swatch/layer check in [Production process and colors](drawing-rules-production.md#production-process-and-colors).

**Warning/title:** determine the exact wording from the current source and ordered product. Known stock templates provide a fallback only when the source supplies no alternate header. Generic 04-1/24-1/4-55 sizes do not determine electrical wording. Match warning wording **and punctuation exactly**, including `CAUTION`, `CAUTION:`, `!CAUTION!`, and the presence/absence of a colon or period after `AS SHOWN`. Keep new/existing, partial-shutdown, energized-area and disconnect distinctions. Do not rewrite a shutdown statement to make it shorter. Keep each heading, warning paragraph and operational note as one editable text block under [Typography](drawing-rules-production.md#typography), with line breaks inside it. Wrap the supplied words at the chosen physical type size; the reserved zone grows when additional lines are needed. Do not shrink required type or force one boilerplate warning across customers.

Observed starting styles are `classic` (5-inch family, 38 pt heading / 15 pt text), `multiple_sources` (same heading with a shorter supplied body), `narrow_classic` (4-inch-wide family, 38 / 12), `large_classic` (6.5-inch family, 75 / 25 with the source's condensed body), `large_alternative` (8-inch template), `small_caution` (4-inch square), `tfs_caution` (20 / 13), `partial_shutdown` (20 / 13, two heading lines) and `directory` (30 pt corner title). Source-specific values can override the style. Apply the allowed [Typography](drawing-rules-production.md#typography) scale increments to `width_scale`, retaining physical height and editable text; this is a text-only horizontal matrix, never a transform on map strokes. Do not use condensation merely to squeeze an oversized layout.

**Operational notes / legends:** a supplied de-energizing statement can sit immediately below the header as `operational_note`. Source lower rapid-shutdown wording or a numbered legend belongs in `bottom_notes`, or `operational_note.placement: "bottom"`. These reserve space **above** the footer and reduce the map zone. This is separate from decorative template text; do not discard these notes when planning the map.

**Footer:** reserve the bottom **14 pt** by default. Website and part identifier use process-specific colors from [Production process and colors](drawing-rules-production.md#production-process-and-colors), **5 pt** text at **100% horizontal scale**, baseline **4.68 pt above the bottom**, and normally **18 pt** side margins. The identifier is the confirmed `SKU-WOdigits-item`, e.g. `04-650-123456-AC`. The full work-order prefix is not printed inside this identifier. Source branding restrictions can suppress `footer.website`; preserve the actual item-specific requirement. Do not enlarge, abbreviate or swap the SKU/WO to make a footer fit.

**Map and callouts:** the remaining work zone contains geometry, equipment, leaders, labels, roads and north. `layout.map_box` is only the geometry fit rectangle **inside** that zone; it is not the complete placard. Allocate local callout lanes after measuring their whole text blocks. Use the map's shape, equipment side and source qualifiers to decide between side columns, a compact row, or nearby stacks. Use the spacing, routing and crossing-gap rules in [Callouts](drawing-rules-callouts.md). When roads are present, reserve their full-span lanes around a reviewed `road_layout.drawing_area` inside the work zone; keep the geometry fit and callouts inside those lanes. Recompute this area when the ordered map size changes. Corner lots retain each source-confirmed road and its name; follow [Roads](drawing-rules-roads.md). A single fixed header percentage or a mandatory left/right callout column is not supported by the examples.

Most residential warnings occupy the full width. Directory titles can occupy a confirmed top-left or top-right corner while roads/callouts use the opposite corner: set `warning.position` and optionally `width_pt`. `work_regions` describe the available rectangles around that reserved corner. Do not place a path or label through the title. The actual map paths, text and arrowheads are checked against reserved zones, including hole clearances.

## Plan, then fit

```text
PYTHON SKILL/scripts/placard_layout.py analyze-order INPUT.pdf --work-order WO-123456 --output WORK/order-candidates.json
PYTHON SKILL/scripts/placard_layout.py plan WORK/scene.json --output WORK/zone-plan.json
```

Create a scene with confirmed order/warning metadata before choosing its geometry fit:

```json
{
  "job": {"work_order":"WO-123456","item_letter":"AC","item_evidence":"Order/map item AC","map_count":1},
  "placard": {
    "profile":"stock-04-650",
    "order": {
      "work_order":"WO-123456","sku":"04-650","item_code":"AC",
      "nominal_size_in":[5,5],"source_page":1,
      "source_sha256":"COPY THE ACTUAL SOURCE SHA256 FROM THE MANIFEST",
      "order_row_evidence":"Copy the exact selected order row here"
    },
    "warning": {
      "style":"multiple_sources","heading":"CAUTION:",
      "lines":["MULTIPLE SOURCES OF POWER"],"evidence":"Current source map header"
    }
  }
}
```

Use the plan's `cut_size_pt`, `work_zone`, optional `bottom_note_zone` and `work_regions` to add `layout.map_box` and output-point callouts. The renderer supplies the exact physical canvas; a conflicting `layout.size_pt` is rejected. The plan command is a planning result, not a completed map or automatic callout solver. If its first default geometry rectangle is unsuitable, choose another legal geometry fit and local callout lanes using the source. Keep the entire site's single rigid rotation and all fixed stroke weights.

If symbol density or required wording cannot fit, rearrange callout lanes and line breaks, maintaining [Typography](drawing-rules-production.md#typography) and [Equipment](drawing-rules-production.md#equipment). Use source-supported physical type hierarchy and available space. Never enlarge the cutline, relocate site features, drop panels/notes or reduce physical strokes to conceal a fit failure; report the unresolved fit.

Full render adds cutline, warnings and footer. `placard.include_chrome: false` is for an explicitly requested map-only export that still uses the ordered physical work zone. Old scenes without placard metadata remain supported for existing callout-only revisions; they are not size-verified full placards and are not the starting point for new orders. Preserve their geometry unless the user asks for a full conversion.

For multiple map items use the existing order scene. Every item keeps its own confirmed dimensions, warning, cutline and footer, even when sizes differ; all items remain separated and labeled on one shared SVG artboard. Labels sit outside the production cutlines. Do not scale finished placards to equal tile sizes.

## Review at the actual physical size

Check row/item identity, nominal versus actual dimensions, exact warning/notes, footer code, requested cutouts, reserved-zone fit and type readability. Then perform the existing geometry, equipment, north, leader and clean-vector review. `zone_check` reports containment checks; it does not establish engineering correctness or replace visual review of collisions between map elements. The output stays loose editable paths/text with no groups, clipping masks, invisible paths or duplicate strokes. Check type colors and the inclusive 10 pt engraving threshold against [Production process and colors](drawing-rules-production.md#production-process-and-colors). Review arrows against [Callouts](drawing-rules-callouts.md), including process-colored backing at every line crossing; check on-side cardinal solid/dashed street lanes with parallel names. Text-only rotation for road lettering is allowed; map paths/strokes remain baked. Header/footer graphics and type do not scale map stroke weights.


## Warning corrections and source-trace review

Equipment rules are consolidated in [Equipment](drawing-rules-production.md#equipment). Plan room for those source-bound boxes and direct callouts; use this document only to establish the available work zones.

The warning profiles are starting conventions. Respect explicit source/customer type sizes and hierarchy; a generic large header must not force false geometry or a new annotation style. Use [Production process and colors](drawing-rules-production.md#production-process-and-colors), including the inclusive 10 pt laser threshold. If the user requests a common paragraph across items, retain that exact paragraph on each named item, then place an additional MULTIPLE SOURCES OF POWER line **underneath**, in the requested small red type. This is a scoped user override; do not rewrite unrelated customers' electrical wording automatically.

Keep a fixed source trace of all roof corners/ridges/valleys/dormers/junctions and inspect an overlay before routing. Preserve these paths beneath the process-colored leader backing specified in [Callouts](drawing-rules-callouts.md); review the visible gap at every crossing at reading size.


## Selected output scope

The three entry skills share these profiles and the same renderer. Set `output_mode` on the scene/order and pass `--mode map-only|map-labeled|finished`. Finished output requires `placard` metadata and forces finishing on. The other modes suppress finishing without refitting geometry; map-only also suppresses all text, road names, north N, item headings and callout leaders. Labeled output retains map labels/notes and direct arrows, with no caution paragraph, cutline or footer. Keep map-specific address/room/shutdown qualifiers in map labels when needed, rather than losing them inside suppressed finishing metadata.

Unconfirmed requested holes are reported in `placard_layout.deferred_finishing` for map-only/labeled output; never invent hole geometry. They still block finished output. Known hole clearances can remain reserved in all modes. An unconfirmed manufacturing size cannot be advertised as a production cutline; for the two map stages only, use confirmed nominal order dimensions and an explicit reviewed work rectangle as described in `drawing-rules.md`. Source site identity and ordered size remain mandatory.
