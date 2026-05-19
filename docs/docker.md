# Running CCC in Docker

A `Dockerfile` and `docker-compose.yml` ship in the repo root for users who
want to evaluate Claude Command Center without installing Python on the host
or running the launchd agent. **This is a trial install path, not the hero
path.** On macOS the canonical install remains `./run.sh` — several CCC
features only work when the server has direct access to the host (see
[Feature gaps](#feature-gaps) below).

## Quick start

```bash
git clone https://github.com/amirfish1/claude-command-center.git
cd claude-command-center
docker compose up --build
```

Then open <http://localhost:8090>.

Or build/run by hand without compose:

```bash
docker build -t claude-command-center .
docker run --rm \
  -p 127.0.0.1:8090:8090 \
  -v "$HOME/.claude:/root/.claude" \
  claude-command-center
```

## The mount you cannot skip

The dashboard exists to surface your Claude Code transcripts. Those live in
`~/.claude/projects/*.jsonl` on the host. Without
`-v "$HOME/.claude:/root/.claude"` (compose handles this for you), the
container sees an empty home and the kanban view is blank.

The mount is read-write because CCC also persists its own state under
`~/.claude/command-center/`. Append `:ro` if you want a strict
look-but-don't-touch trial — the UI loads, but actions that change state
(network config, marking sessions done, etc.) will fail.

## Networking and ports

- Inside the container CCC binds `0.0.0.0` (set as a `CCC_BIND_HOST` env in
  the Dockerfile). It has to — a container's loopback is private to its own
  network namespace, so a `127.0.0.1` bind inside the container is
  unreachable from the host.
- The compose file publishes the port as `127.0.0.1:8090:8090` so the
  dashboard stays loopback-only on the host. **Don't change this to
  `0.0.0.0:8090:8090` unless you understand
  [`SECURITY.md`](../SECURITY.md)** — CCC has no authentication and any
  reachable peer can run commands as you.

## Feature gaps

The Docker path runs a Linux container, so macOS-only glue is unavailable:

- **Jump to terminal** (AppleScript / `osascript`) — no-op.
- **Attach via system processes** — the container can't see host processes.
- **Claude Desktop deep links** — host-only URL scheme.
- **`./run.sh --install-service`** (launchd agent) — not applicable.
- **`gh`, `claude`, `pkood`, `vercel` CLIs** — not bundled. The server
  detects them at runtime; whichever ones you install inside the container
  light up the corresponding UI surfaces, but that's outside the scope of
  this image.

The **kanban view, transcript ingestion, session search, conversation
popouts, and the context-usage pill** all work as long as `~/.claude` is
mounted.

## Updating

```bash
git pull
docker compose up --build
```

There's no persistent state inside the image itself — everything that
matters lives in the mounted `~/.claude` volume on the host.
