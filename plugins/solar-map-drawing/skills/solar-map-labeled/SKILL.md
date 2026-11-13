---
name: solar-map-labeled
description: Create an editable solar site SVG with equipment, array and context labels and direct arrows. Use for labeled maps without caution wording, cutline or footer.
---

# Solar Map With Labels

Draw the map with full source-confirmed equipment/array/context wording, direct Arrow 2 leaders, road names, north N and map-specific qualifiers/notes. Omit caution/header paragraphs, finishing warnings, cutline, holes, website and part-number footer.

Use `output_mode: "map-labeled"` in the scene/order and `--mode map-labeled` when rendering. The user's explicit current output scope overrides the default of the invoked skill. Set the corresponding mode and continue; do not ask the user to repeat a clear choice. Reuse verified geometry when switching scope on the same source.

## Shared drawing rules and runtime

Read the [shared drawing rules](../solar-map-drawing/references/drawing-rules.md) before drawing. They preserve all saved roof, rotation, north, equipment, panel-clearance, stroke-weight and clean-vector requirements. Read [chat workflow](../solar-map-drawing/references/chat-workflow.md) for staging, [zone layout](../solar-map-drawing/references/zone-layout.md) for ordered sizes and work zones, and [scene format](../solar-map-drawing/references/scene-format.md) when constructing scenes. Read matching customer guidance only when relevant.

Resolve `CORE` to `../solar-map-drawing` relative to this skill directory, not the working directory. All three skills are bundled together. Use **the one shared copy** of `CORE/scripts/chat_job.py`, `map_workbench.py`, `placard_layout.py`, canonical arrow assets and production profiles. They need host-provided Python/PyMuPDF/Pillow; no separate app, shared folder or model API key. If shared files are missing, restore the complete plugin rather than guessing paths or using a different installation.

Prepare the attached PDF, confirm the order/item/size, inspect the source, trace its fixed geometry, plan its working zone and visually verify the result. For map-only and labeled output, retain the planned warning/footer zones while suppressing their artwork; use an explicitly nominal editing frame only when manufacturing size is unknown, as explained in the shared rules. Finishing-only unknown holes are deferred in these modes, while finished output requires them to be resolved.

```text
PYTHON CORE/scripts/chat_job.py prepare ATTACHMENT --workspace SESSION
PYTHON CORE/scripts/chat_job.py render JOB/scene.json --delivery DELIVERY --mode map-labeled --diagnostics JOB/qa
```

For multiple maps, pass `JOB/order.json`; retain actual item codes, one shared artboard and one WO-named SVG. Map-only output has no visible item labels. Keep the preview and source overlay internal, verify the selected scope, and return the clickable SVG with only material source uncertainties. Save no PNG/report/ZIP in the drawing delivery folder.
