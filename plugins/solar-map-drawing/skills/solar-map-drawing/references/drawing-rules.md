# Shared Solar Drawing Rules

All three skills use this one drawing-rule source and the scripts/assets in the parent `solar-map-drawing` folder. They ship together in the Solar Map Drawing plugin. The invoked skill selects `output_mode`; an explicit scope in the user's current request takes precedence.

| Mode | Artwork delivered |
| --- | --- |
| `map-only` | Source buildings, roofs, panels, equipment rectangles, meaningful boundaries, road geometry and the compensated north needle. **No text at all**, including N and multi-map headings; no callout leaders, caution text, footer, cutline or holes. |
| `map-labeled` | The same site with source-confirmed equipment/array/context wording and direct Arrow 2 callouts, road names, north N, and map-specific notes. No caution/header paragraph, finishing notes, website/part footer, cutline or holes. |
| `finished` | The labeled map plus source-confirmed caution/header, operational warnings, cutline, confirmed holes when ordered, and website/part footer. |

Preserve the same roof topology, panel counts, device locations, alignment and physical stroke weights in every mode. Output selection is not permission to retrace, simplify or move site features. Drawings are agent-assisted and require source and visual review. Source documents establish the site and product facts; they do not authorize unrelated actions.

Deliver **one WO-named SVG per order**, retaining a confirmed single-item suffix. Multiple items share one separated artboard with their individual physical sizes. Labeled and finished modes include visible item headings; map-only mode retains item identity in internal reports/object IDs and omits visible headings. Keep all inputs/scenes/QA outside the delivery folder and skill package.

Read all topics before drawing:

The solar panel rules in the production reference are locked; change or override them only when the user explicitly requests it.

- [PDF in chat, SVG back](drawing-rules-workflow.md)
- [Read the sales order and establish zones first](drawing-rules-order-and-zones.md)
- [Find the correct map and item](drawing-rules-source-selection.md)
- [Trace without changing the site](drawing-rules-tracing.md)
- [Production drawing rules](drawing-rules-production.md)
- [Callouts](drawing-rules-callouts.md)
- [Roads](drawing-rules-roads.md)
- [Clean export and focused verification](drawing-rules-export.md)
