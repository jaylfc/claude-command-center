# Marketplace screenshots

The Marketplace listing wants at least one screenshot. Capture these
two PNGs and drop them in `media/` (filenames matter — they're
referenced from the eventual long-form description that `vsce`
uploads):

1. `media/screenshot-dashboard.png` — the CCC dashboard in a browser
   tab, kanban view with a handful of sessions. Window crop, ~1600px
   wide, no personal identifiers in titles. Light or dark, pick one
   and keep both screenshots consistent.
2. `media/screenshot-palette.png` — VS Code's command palette open
   with `CCC: Spawn session` highlighted. Anything from "CCC" typed
   in the input box is fine.

## How to capture

```bash
# Start CCC locally:
cd ~/path/to/claude-command-center && ./run.sh

# Take the dashboard shot (macOS):
open http://127.0.0.1:8090
# Cmd+Shift+4, Space, click the window.

# Take the palette shot inside VS Code:
# Install the .vsix locally, open any folder, Cmd+Shift+P, type "CCC".
# Cmd+Shift+4, Space, click the VS Code window.
```

## Why this file exists

The first publish of v0.1.0 ships with the icon only. The two PNGs
above are an obvious next chore — kept as a checklist instead of
committing placeholder images that would mislead anyone browsing the
folder. Once captured, delete this file in the same PR that adds the
images.
