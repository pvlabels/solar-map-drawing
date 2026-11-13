# Solar Map Drawing

Version **3.1.0** packages three skills in the same private workspace plugin:

| Skill | Invocation | Output |
| --- | --- | --- |
| Solar Map Only | `$solar-map-only` | Site geometry without text or callout leaders. |
| Solar Map With Labels | `$solar-map-labeled` | Map wording and direct arrows, without placard finishing. |
| Finished Solar Map | `$solar-map-drawing` | Labeled map, source-confirmed caution wording, cutline and footer. |

All three use the shared rules, renderer and vector assets under `plugins/solar-map-drawing/skills/solar-map-drawing/`. Rooftop modules share one size per map at 1.25 pt; interior walls are 1 pt, exterior perimeters 2 pt, and streets are horizontal or vertical. The original skill name remains the finished version. The host must provide Python/file execution; no separate model API key is required. Source interpretation and visual review remain agent-assisted.

## Workspace setup

1. In ChatGPT workspace administration, open **Plugins > Add > Import marketplace** (or **Marketplaces**, depending on the interface).
2. Enter this repository's GitHub URL. Leave Path empty and leave Branch blank to follow the default branch. Authorize the GitHub connection if asked.
3. After import, configure the plugin's workspace availability. The coworker can install it from the workspace plugin directory unless it has been installed for them.
4. Start a new file-capable chat, attach the source PDF, and select the skill matching the desired output from the table above.

The GitHub account used for the import must retain access to this private repository. Sharing the plugin within the workspace and inviting someone to this repository are separate actions.

## Requirements

The workbench uses Python, PyMuPDF (`pymupdf`), and Pillow (`pillow`). These dependencies must be available in the environment where the skill runs. See the skill instructions for the source inspection, rendering, and required visual checks.

## Updating

Edit the packaged skills under `plugins/solar-map-drawing/skills/`, retaining the shared core and all three entry skills together. Update the plugin version, commit the changes, and push them to this repository's default branch. GitHub marketplace sync checks for updates daily; an admin can use **Sync now** in the marketplace settings. Check the sync report and test the result in a new chat. Editing a separate personal copy of the skill does not change this repository automatically.

Do not add customer drawings, job output, credentials, or other confidential job files to this repository.