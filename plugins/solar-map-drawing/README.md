# Solar Map Drawing

Version 3.4.1. Shared plugin for PDF attachments and editable, physically sized solar map placard SVG downloads.

## Three skills in one plugin

Attach the PDF in a file-capable ChatGPT Work/Codex chat and select:

| Skill shown in the picker | Invocation | Result |
| --- | --- | --- |
| Solar Map Only | `$solar-map-only` | Geometry, equipment, road edges and north needle; zero text/callouts and no finishing. |
| Solar Map With Labels | `$solar-map-labeled` | The map with equipment/array/context wording and direct arrows; no caution paragraph, cutline or footer. |
| Finished Solar Map | `$solar-map-drawing` | Labeled map plus source-confirmed caution/notes, production cutline, confirmed requested holes and footer. |

The original `$solar-map-drawing` invocation remains the finished version for existing prompts. An explicit current request overrides the selected skill's default. All three use one maintained drawing-rule reference, one renderer, the same assets and saved physical stroke weights. They preserve source geometry, panels, equipment and orientation. The renderer enforces scope with `output_mode` / `--mode`; map-only omits N and multi-map headings as well as all other text. Multiple maps stay separated on one artboard with item identity recorded internally; labeled/finished versions also display their item headings.

Only the WO-named SVG is delivered. Previews, comparisons and job data stay internal. The plugin needs host-provided Python/PyMuPDF/Pillow, with session-local setup where available. It requires no model API key, separate app or shared folder. This release preserves the existing plugin identity and sharing audience. Installation does not provision an executor, and account usage limits still apply.

## Size-first layout

The order helper associates readable packing-slip rows with their item code, SKU, explicit dimensions, source hash and production-profile candidates. Confirm the actual map item visually. Quantity does not create additional maps. Source page dimensions and the site's aspect ratio do not set the placard size.

Twelve measured size profiles and source-specific warning styles provide starting points. The common 0.05-inch production reduction is not universal: the measured 5 by 7.75 family retains its full height. Unknown sizes/materials require confirmed production dimensions. Warning length, corner titles and lower notes change the available map/callout region. Footer identifiers retain the exact SKU, WO digits and item code. Requested holes require confirmed dimensions and positions. The renderer rejects artwork crossing reserved zones instead of enlarging the cutline or clipping away content. It does not automatically solve callout placement or certify electrical wording.

Physical strokes, typography and process-specific colors follow [Production drawing rules](skills/solar-map-drawing/references/drawing-rules-production.md); cutline/bleed requirements follow [Zones](skills/solar-map-drawing/references/zone-layout.md). The SVG contains loose editable artwork with process-colored leader backing. Native Illustrator swatches/layers and print bleed need a verified production handoff.

Panels within each countable array share exact edges without overlapping interiors. The renderer compacts and, if necessary, shrinks joined grids about fixed array centers while retaining counts, bearings and missing cells. It checks 1 pt visible clearance to exterior/interior walls, roof lines and normalized equipment rectangles. Individual panel centers may shift within their own array. Explicit array IDs/cells disambiguate source groups; requested panel spacing needs recorded evidence. Shared borders export once at 1.25 pt. Schematic source fields remain schematic. Run `python -m unittest discover -s tests -v` from the repository root for the panel-fitting checks.

## Callout and road review corrections

Use the shared [Callouts rules](skills/solar-map-drawing/references/drawing-rules-callouts.md) for Arrow 2, routing and process-colored crossing gaps, and [Roads](skills/solar-map-drawing/references/drawing-rules-roads.md) for full-area corner roads and outward street names. See [Equipment](skills/solar-map-drawing/references/drawing-rules-production.md#equipment) for the single source of device styling, placement and metadata.

## Runtime

The chat host must expose the attachment and provide Python 3.10+ file execution. PyMuPDF and Pillow are needed for PDF extraction and visual review. The adapter checks these packages and can install missing ones into session storage when package downloads are permitted. This uses the host runtime; it does not require the user's computer to have Python when the host provides a hosted Python executor.

Installing a plugin does not provision an executor or guarantee these capabilities in every chat. If a host lacks Python or cannot obtain the packages, use a file-capable Work/Codex session. No remote rendering service or external model endpoint is included. The agent still interprets and traces geometry; the helper is not an unattended PDF-to-map recognizer. Generated output must be visually checked.

The package contains the maintained skill, portable attachment helper, original renderer, scene/chat/zone references, measured size profiles, canonical arrow assets, dependency constraints and icon. It contains no customer PDFs, scenes, job data, credentials, virtual environments or dependencies. New jobs resolve source paths relative to their manifests. Revisions in a later chat may require reattaching the source and job materials because chat scratch storage is not permanent.

## Maintain

The three entry skills live in `skills/solar-map-only`, `skills/solar-map-labeled` and `skills/solar-map-drawing`. Shared instructions are `skills/solar-map-drawing/references/drawing-rules.md`; scripts/assets/references remain under that core folder. Package/install all three together; do not distribute only one wrapper. Plugin metadata and this file live in `plugins/solar-map-drawing`. Build with `tools/build_solar_plugin.py`; it combines those sources into a clean versioned ZIP. Update the same hosted plugin ID, preserving its audience, and read back the new release. Local folder edits alone do not update the hosted plugin. GitHub automatic sync is a separate setup and is not configured by this release.


## Customer-art direct layout

The single [Equipment section](skills/solar-map-drawing/references/drawing-rules-production.md#equipment) governs device representation and source-bound placement. Roof tracing must preserve corners, facets and shared junctions against a source overlay. Warning wording and punctuation must match the current customer artwork.


## Uniform rooftop panels, interior walls and cardinal streets

All rooftop panels on each map have the same rectangular short/long dimensions and 1.25 pt strokes, allowing portrait/landscape rotation. The shared renderer retains original centers/counts and reduces one common size for clearance rather than shrinking individual panels differently. Ground arrays retain their source representation. Shared internal building dividers use the `wall` role at 1 pt; only exterior perimeters use 2 pt, and all equipment remains 1.5 pt. Streets are schematic horizontal/vertical paths only, retaining the correct side of the property. These rules apply to all three skills.

## Version 3.4.0: consolidated map guidelines

Integrated the user-approved MAP GUIDLINES.pdf requirements into the existing rule topics. Equipment style, placement and scene metadata now have one authoritative section. The PDF takes precedence for strokes, typography, process-specific colors and finishing; existing site fidelity, north-label orbit and exact array identification phrases remain. See the shared drawing-rule index for ownership and production handoff limits.

## Version 3.4.1: intact wrapped text

Each multiline callout, label or paragraph remains one editable text object with internal line breaks. Separate logical blocks remain separate. Export cleanup and multi-map translation preserve all lines and their spacing.
