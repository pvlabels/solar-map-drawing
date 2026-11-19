## Trace without changing the site

For vectors, select reviewed source IDs from `manifest.json` / `path-atlas.png`. Preserve exact coordinates, curves and closures. Split paths that mix roofs, leaders, glyphs or sheet furniture, copying source commands with evidence. Separate the entire exterior perimeter from roof interiors so their weights remain correct.

For raster/sketch inputs, trace in displayed page coordinates with shared roof junction vertices. Preserve concavities, offsets, raw panel corners, stepped/missing cells and equipment attachment locations. The final rooftop rectangles use the common-size production rule below; the original trace remains the evidence. Regularize rough marks only enough to clarify intent and record the interpretation; do not claim survey accuracy. Ruled paper or photo perspective is not roof geometry. For hybrids, the rendered image is the visibility reference; PDF clipping/hidden layers may not appear in path extraction.

Every added element needs a source ID or `evidence`. Do not assume rectangles are panels, loops are buildings or interior marks are ridges. Preserve genuinely cropped outlines as open segments; do not close across a crop edge. Avoid global merging, minimum-area deletion and bounding-box replacement of tilted panels. Source traces remain unchanged internally.

Roof accuracy is a topology check: follow every perimeter corner, ridge, valley, dormer and shared junction against the source at high zoom. Do not sketch a plausible roof from its bounding box, merge an attached wing into a guessed outline, or change/delete roof paths to fit wording. Compare the fixed trace with the source before adding callouts. Preserve the underlying roof/perimeter paths at leader crossings and apply the process-colored backing required by [Callouts](drawing-rules-callouts.md).

After tracing, apply [Equipment](drawing-rules-production.md#equipment) for all device representation, placement, direct wording and source-detail rules. A fit problem never authorizes moving a device or changing the source trace.
