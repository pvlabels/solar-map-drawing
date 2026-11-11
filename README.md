# Solar Map Drawing

A private workspace plugin that packages the Solar Map Drawing skill, its map workbench, reference guide, and vector assets. It produces editable solar facility maps from supplied site drawings. Follow `plugins/solar-map-drawing/skills/solar-map-drawing/SKILL.md` for its workflow and visual review requirements.

## Workspace setup

1. In ChatGPT workspace administration, open **Plugins > Add > Import marketplace** (or **Marketplaces**, depending on the interface).
2. Enter this repository's GitHub URL. Leave Path empty and leave Branch blank to follow the default branch. Authorize the GitHub connection if asked.
3. After import, configure the plugin's workspace availability. The coworker can install it from the workspace plugin directory unless it has been installed for them.
4. Start a new Codex chat and ask it to use the solar-map-drawing skill on a supplied site drawing.

The GitHub account used for the import must retain access to this private repository. Sharing the plugin within the workspace and inviting someone to this repository are separate actions.

## Requirements

The workbench uses Python, PyMuPDF (`pymupdf`), and Pillow (`pillow`). These dependencies must be available in the environment where the skill runs. See the skill instructions for the source inspection, rendering, and required visual checks.

## Updating

Edit the packaged files under `plugins/solar-map-drawing/skills/solar-map-drawing/`, commit the changes, and push them to the repository's default branch. GitHub marketplace sync checks for updates daily; an admin can use **Sync now** in the marketplace settings. Check the sync report and test the result in a new chat. Editing a separate personal copy of the skill does not change this repository automatically.

Do not add customer drawings, job output, credentials, or other confidential job files to this repository.