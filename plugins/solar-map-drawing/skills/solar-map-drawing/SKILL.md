---
name: solar-map-drawing
description: Create a finished editable solar placard with a labeled site map, source-confirmed caution wording, cutline and footer. Use for complete placards; separate skills provide geometry-only or labeled-map output.
---

# Finished Solar Map

Draw the labeled map plus source-confirmed caution/header wording, operational warnings, measured production cutline, confirmed holes if ordered, and website/part-number footer. Resolve production-size, warning and hole-pattern conflicts before claiming a finished placard.

Use `output_mode: "finished"` in the scene/order and `--mode finished` when rendering. The user's explicit current output scope overrides the default of the invoked skill. Set the corresponding mode and continue; do not ask the user to repeat a clear choice. Reuse verified geometry when switching scope on the same source.

## Shared drawing rules and runtime

Read the [shared drawing rules](./references/drawing-rules.md) before drawing. They preserve all saved roof, rotation, north, equipment, panel-clearance, stroke-weight and clean-vector requirements. Read [chat workflow](./references/chat-workflow.md) for staging, [zone layout](./references/zone-layout.md) for ordered sizes and work zones, and [scene format](./references/scene-format.md) when constructing scenes. Read matching customer guidance only when relevant.

Resolve `CORE` to `.` relative to this skill directory, not the working directory. All three skills are bundled together. Use **the one shared copy** of `CORE/scripts/chat_job.py`, `map_workbench.py`, `placard_layout.py`, canonical arrow assets and production profiles. They need host-provided Python/PyMuPDF/Pillow; no separate app, shared folder or model API key. If shared files are missing, restore the complete plugin rather than guessing paths or using a different installation.

Prepare the attached PDF, confirm the order/item/size, inspect the source, trace its fixed geometry, plan its working zone and visually verify the result. For map-only and labeled output, retain the planned warning/footer zones while suppressing their artwork; use an explicitly nominal editing frame only when manufacturing size is unknown, as explained in the shared rules. Finishing-only unknown holes are deferred in these modes, while finished output requires them to be resolved.

```text
PYTHON CORE/scripts/chat_job.py prepare ATTACHMENT --workspace SESSION
PYTHON CORE/scripts/chat_job.py render JOB/scene.json --delivery DELIVERY --mode finished --diagnostics JOB/qa
```

For multiple maps, pass `JOB/order.json`; retain actual item codes, one shared artboard and one WO-named SVG. Map-only output has no visible item labels. Keep the preview and source overlay internal, verify the selected scope, and return the clickable SVG with only material source uncertainties. Save no PNG/report/ZIP in the drawing delivery folder.
