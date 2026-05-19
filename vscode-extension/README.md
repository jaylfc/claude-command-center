# Claude Command Center for VS Code

Spawn and watch Claude Code sessions from inside VS Code. This
extension is a thin client over [Claude Command
Center](https://github.com/amirfish1/claude-command-center) (CCC) — a
local dashboard that runs `claude` headlessly, tracks sessions across
repos, and exposes a small HTTP API on loopback.

This is v0.1.0 — intentionally minimal. The whole extension is two
palette commands. A full webview replacement for the CCC dashboard is
out of scope; for now it opens the dashboard in your default browser.

## Prerequisites

- VS Code 1.80 or newer.
- A locally running CCC server. From a clone of
  [claude-command-center](https://github.com/amirfish1/claude-command-center):

  ```bash
  ./run.sh         # binds 127.0.0.1:8090 by default
  PORT=9000 ./run.sh   # alternative port
  ```

  See `SECURITY.md` in the CCC repo before exposing the server beyond
  loopback. Default is loopback-only and that's the supported config
  for this extension.
- The `claude` CLI installed on `$PATH` (required by CCC itself, not
  by this extension directly).

## Commands

Both commands appear in the palette (Cmd/Ctrl+Shift+P):

- **CCC: Spawn session** — prompts for an initial message, then POSTs
  to `/api/sessions/spawn` with the active editor's workspace folder
  as `cwd`. On success, offers to open the dashboard.
- **CCC: Open dashboard** — opens the configured CCC URL in your
  default browser.

If CCC isn't running, the spawn command shows a single non-modal
toast pointing you at `./run.sh`. No modal blocks, no retries.

## Configuration

Two settings under **Claude Command Center**:

| Setting | Default | Notes |
|---|---|---|
| `claudeCommandCenter.host` | `127.0.0.1` | Loopback recommended. |
| `claudeCommandCenter.port` | `8090` | Matches `run.sh`'s default. Override if you run with `PORT=…`. |

## Building from source

```bash
cd vscode-extension
npm install
npm run compile           # tsc → out/extension.js
npx vsce package          # produces claude-command-center-0.1.0.vsix
code --install-extension claude-command-center-0.1.0.vsix
```

If you don't have `vsce` globally, `npx @vscode/vsce package` works
too — it's already declared in `devDependencies`.

## Publishing

Tag-driven via `.github/workflows/publish-vscode-extension.yml` in
the CCC repo: pushing a tag matching `vscode-v*` runs `vsce publish`
using the `VSCE_PAT` repository secret. The publisher id in
`package.json` must match the one that owns the PAT.

## License

MIT. See `LICENSE` in this directory.
