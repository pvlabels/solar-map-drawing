# Solar Map Drawing

Version **3.4.0** packages three skills in the same plugin:

| Skill | Invocation | Output |
| --- | --- | --- |
| Solar Map Only | `$solar-map-only` | Site geometry without text or callout leaders. |
| Solar Map With Labels | `$solar-map-labeled` | Map wording and direct arrows, without placard finishing. |
| Finished Solar Map | `$solar-map-drawing` | Labeled map, source-confirmed caution wording, cutline and footer. |

All three use the shared rules, renderer and vector assets under `plugins/solar-map-drawing/skills/solar-map-drawing/`. Panels within each countable array touch edge-to-edge without overlapping interiors, unless explicitly specified otherwise. Joined grids can shrink around their fixed array centers to keep 1 pt visible clearance from walls, roof lines and equipment. Modules share one size per map at 1.25 pt; interior walls are 1 pt, exterior perimeters 2 pt, and streets are horizontal or vertical. Equipment boxes use a common 1.5:1 ratio sized from the canonical Arrow 2 head. The original skill name remains the finished version. The host must provide Python/file execution; no separate model API key is required. Source interpretation and visual review remain agent-assisted.

## Changes in 3.4.0

Integrated the user-approved MAP GUIDLINES.pdf into the existing rule sections, with PDF specifications taking precedence over conflicting older settings. Equipment style, placement and metadata now live in [one authoritative section](plugins/solar-map-drawing/skills/solar-map-drawing/references/drawing-rules-production.md#equipment).

- 1 pt Arrow 2 leaders and roads, with 20 pt dash / 24 pt gap road patterns.
- Arial typography, 8 pt minimum callouts, 5 pt footer, and 70%-100% horizontal scaling in 5% steps.
- Separate laser, metal and label colors, backing colors, cutline weights and layer metadata.
- Arrow 15 north presets with upright orbiting N, outward street names, and the JK Solar street requirement.
- Required/omitted callout guidance, source-only YOU ARE HERE markers, and exact warning punctuation.

Native Illustrator layers, process swatches and 10 pt print bleed need production handoff verification; SVG metadata does not create those native features. The source PDF and its customer examples are not included in this repository.

Run `python -m unittest discover -s tests -v` and `pwsh -File scripts/check-drawing-rules.ps1`.

## Workspace setup

1. In ChatGPT workspace administration, open **Plugins > Add > Import marketplace** (or **Marketplaces**, depending on the interface).
2. Enter this repository's GitHub URL. Leave Path empty and leave Branch blank to follow the default branch. Authorize the GitHub connection if asked.
3. After import, configure the plugin's workspace availability. The coworker can install it from the workspace plugin directory unless it has been installed for them.
4. Start a new file-capable chat, attach the source PDF, and select the skill matching the desired output from the table above.

The GitHub account used for the import must be able to read this repository. Sharing the plugin within the workspace and inviting someone to this repository are separate actions.

## Requirements

The workbench uses Python, PyMuPDF (`pymupdf`), and Pillow (`pillow`). These dependencies must be available in the environment where the skill runs. See the skill instructions for the source inspection, rendering, and required visual checks.

## Updating

Edit the packaged skills under `plugins/solar-map-drawing/skills/`, retaining the shared core and all three entry skills together. Update the plugin version, commit the changes, and push them to this repository's default branch. GitHub marketplace sync checks for updates daily; an admin can use **Sync now** in the marketplace settings. Check the sync report and test the result in a new chat. Editing a separate personal copy of the skill does not change this repository automatically.

Do not add customer drawings, job output, credentials, or other confidential job files to this repository.
