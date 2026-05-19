# Roadmap

_Last updated: 2026-05-19_

## How to read this

This file is the single public answer to "is this thing maintained, and
is the feature I want planned?". It groups work by status and theme,
and every entry links to the issue or commit that proves the claim. No
dates. Roadmaps that lie age badly — this one is meant to age well.

- **Shipped** — landed on `main`, reflected in the CHANGELOG.
- **In progress** — actively being worked on or staged in `[Unreleased]`.
- **Planned** — accepted, has a tracking issue, not started.
- **Under consideration** — open question. React or comment on the
  linked issue if you want it; that's the vote signal.
- **Out of scope** — explicitly not happening. Listed so you don't
  have to ask.

A reaction is a signal, not a contract. The maintainer reserves the
right to ship un-voted items and skip high-voted ones when scope,
security, or maintainability arguments override. One reaction per
account; brigading does not help.

For the granular per-release log, see
[`CHANGELOG.md`](../CHANGELOG.md). For the long-form "why" behind
several of these, see the README.

---

## Shipped

The capabilities a fresh `git clone` gives you today.

### Core orchestration
- Kanban over every live and dormant Claude Code, Codex, and Gemini
  CLI session on the machine — terminal-spawned, headless, or
  dashboard-launched.
- Attach without configuration: Claude's own on-disk transcripts
  (`~/.claude/projects/*.jsonl`) plus two installed hooks
  (`post-tool-use`, `stop`) are the source of truth.
- Headless spawn with stdin-pipe follow-up — keep talking to a
  `claude -p` session from the browser, no terminal needed.
- Resume-on-demand — injecting into a dormant session auto-spawns
  a headless `claude --resume` to deliver the message.
- Split conversations: drag any sidebar session onto the right or
  bottom of the open conversation to view two transcripts side by
  side, each with its own input bar.

### Multi-engine support
- [Multi-orchestrator stance surfaced in README + repo description](https://github.com/amirfish1/claude-command-center/issues/53) —
  Claude Code, Codex, and Gemini CLI treated as first-class peers in
  positioning.
- Per-engine spawn from the dashboard for all three engines.
- Codex JSONL ingestion, Gemini chat JSON ingestion, per-session model
  picker for Claude and Codex.
- See the [engine support matrix](../README.md#engine-support) for what
  is first-class vs. partial per engine.

### GitHub integration
- Issue → session → verify → close pipeline. Starting a session from
  an issue auto-adds `claude-in-progress` and self-assigns. Verify
  closes the issue with a commit-SHA comment. Drag to Archived closes
  as "not planned".
- Issue body + comments rendered inside the dashboard (no iframe;
  GitHub blocks that).

### Workflow
- [In-app update notification + one-click self-update](https://github.com/amirfish1/claude-command-center/issues/3).
- [Per-repo service lifecycle + quick app-window launcher](https://github.com/amirfish1/claude-command-center/issues/2).
- [In-dashboard template gallery (5 starter templates)](https://github.com/amirfish1/claude-command-center/issues/46).
- [Kanban board toggle visibility fix](https://github.com/amirfish1/claude-command-center/issues/44).
- Auto-fix-deploy — optionally polls Vercel, spawns a `/fix-deploy`
  session on new production ERRORs (deduped by commit SHA).
- AI-assisted title regeneration on cards (`✨` button, Haiku by
  default).
- "Open in Claude Desktop" — third destination button beside
  Jump/Launch, resumes the current session in the Claude Desktop GUI
  via the `claude://resume` deep link.
- Local TTS, conversation popouts, PWA installable app, resizable
  status rail, slash-command picker — see
  [`changelog.d/`](../changelog.d/) for the full list.

### Skill
- `ccc-orchestration` Claude Code skill ships with the server. One
  session can spawn, inject into, and synchronously ask sibling
  sessions over plain HTTP. URL written to
  `~/.claude/command-center/port.txt` so the skill discovers the
  running instance automatically.

---

## In progress

Staged in `[Unreleased]` or actively being worked on. Subject to
change before the next tag.

- Bug-report modal screenshots — `screencapture -i` area selector,
  preview in modal, embedded in the issue body via a dedicated
  `bug-screenshots` branch.
- Sibling-worktree detection in the workspace strip — surface
  `🌿 +N worktrees` when other worktrees exist for the session's
  repo, with `[agent]` markers for subagent/orchestration locks.
- Effective-workspace inference from tool calls — second pill on the
  workspace strip when the launch cwd disagrees with where the
  session is actually writing files.
- "Last interacted" indicator on cards — italic "Last interacted Xm
  ago" stamp, persisted to disk, used as a sort key so a card you
  just typed into bubbles to the top.
- Kanban rename: `Planning` → `Icebox`, with the transient
  "live but no tool fired yet" half folded back into `Working`. See
  [`docs/kanban-rules.md`](kanban-rules.md).
- Conversation pane styling pass — Claude Desktop look (chat bubbles,
  SF Pro / system-ui, antialiased), collapsed tool-call groups,
  inline tool-result rendering.

---

## Planned

Accepted, has a tracking issue, not started.

### Distribution
- [One-command install (curl | sh + Homebrew tap)](https://github.com/amirfish1/claude-command-center/issues/45) —
  the friction between "found the repo" and "running locally" is the
  main install-funnel leak today. Both paths needed; tap is the
  durable one.
- [Dockerfile + docker-compose.yml (trial install path)](https://github.com/amirfish1/claude-command-center/issues/54) —
  trial-only path. CCC is built for macOS and won't fully replace the
  native install, but a container lets curious users see the UI
  without touching their host.
- [VS Code extension v0.1.0](https://github.com/amirfish1/claude-command-center/issues/52) —
  publisher id, palette command, screenshot. A second front door
  beside the browser UI.
- [Static GH Pages demo with seeded mock data](https://github.com/amirfish1/claude-command-center/issues/49) —
  let someone click around the UI in 5 seconds without installing
  anything. Mock data baked in; no server.

### Multi-engine parity
- [Aider / OpenCode session adapters + first-class Codex JSONL ingestion](https://github.com/amirfish1/claude-command-center/issues/57) —
  the ingestion layer is engine-agnostic; this issue tracks the
  remaining adapter work to bump Codex from "partial" to first-class
  and add Aider + OpenCode behind the same interface.

### Refactoring & tests
- [Code split of server.py and static/index.html (tracking)](https://github.com/amirfish1/claude-command-center/issues/56) —
  both files are large on purpose so the whole product is readable in
  an afternoon. That tradeoff bends eventually; this is the tracking
  issue for when it does.
- [Session classifier test suite (kickoff)](https://github.com/amirfish1/claude-command-center/issues/55) —
  `good first issue`. CCC has near-zero tests today. The classifier
  ("which kanban column does this session belong in?") is the
  highest-leverage place to start.

### Workflow
- [Worktree env-setup hook (.ccc/worktree-init)](https://github.com/amirfish1/claude-command-center/issues/47) —
  run a per-repo init script when CCC creates a worktree, so the
  spawn lands in a working dev environment (deps installed, .env
  copied, etc.).

### UX
- [README hero rewrite (tagline + GIF + News + Star History)](https://github.com/amirfish1/claude-command-center/issues/51) —
  the GitHub landing-page conversion problem. Pure docs.
- [Chromeless app-window launcher for CCC](https://github.com/amirfish1/claude-command-center/issues/17) —
  open the dashboard as an app window instead of a browser tab on
  macOS.
- [Multi-repo view: surface sessions from multiple repos at once](https://github.com/amirfish1/claude-command-center/issues/1) —
  CCC scopes to one repo at a time today. The original multi-repo
  rail was removed (see
  `changelog.d/removed-multi-repo-rail-2026-05-09.md`); this is the
  re-think.

### Telemetry
- [Anonymous opt-in telemetry (5-field daily ping)](https://github.com/amirfish1/claude-command-center/issues/48) —
  installs vs. active users is currently a guess. Five fields, opt-in,
  off by default, documented in `SECURITY.md` before the first byte
  ships.

---

## Under consideration

Open questions. If you want one of these, react on the linked issue
or leave a comment with your use case. That's the signal that decides
order.

- Linux / Windows. Currently **Out of scope** below — the macOS
  AppleScript glue is why attach and jump-to-terminal work
  end-to-end. If demand for Linux outweighs that, the tradeoff is on
  the table; today it does not.
- A hosted multi-user mode. Also **Out of scope** today; CCC is a
  local dev tool. Open an issue with the threat model you have in
  mind if you disagree.
- Electron / native wrap. Browser is the UI on purpose; the question
  is whether a tray-app shim is worth maintaining alongside.

No tracking issues for these on purpose — file one if you want to
push the conversation forward.

---

## Out of scope

Listed so nobody wastes a PR.

- **Linux / Windows.** macOS-specific AppleScript glue is load-bearing
  for terminal attach and jump-to-terminal. Porting means stubbing
  those out.
- **Multi-user / network-exposed mode.** CCC is a local dev tool with
  no auth. `CCC_BIND_HOST=0.0.0.0` is opt-in and prints a warning;
  every trusted origin can run commands as you. See
  [`SECURITY.md`](../SECURITY.md).
- **Electron / native wrap.** Browser is the UI on purpose. The
  chromeless launcher (above) is the compromise.
- **Owning execution.** CCC attaches to Claude Code / Codex / Gemini
  CLI's on-disk state rather than wrapping them. Tools that want to
  own execution exist; this is the other side of that tradeoff.
- **A bundler / npm in the UI.** `static/index.html` is a single-file
  vanilla-JS app by design. Don't split it into modules without a
  strong reason — see [`CLAUDE.md`](../CLAUDE.md).

---

## How this file stays honest

- New work lands as a `changelog.d/` snippet, which gets rolled into
  `CHANGELOG.md` at release time by `scripts/release.py`.
- This file is bumped by hand at release boundaries — entries move
  from **Planned** → **In progress** → **Shipped** as they land, and
  the "Last updated" date at the top is the audit trail.
- If you spot a discrepancy between this file and the issue tracker,
  open an issue. The tracker is the source of truth.
