# Multi-Session Coordination — Design Spec

**Date:** 2026-05-06  
**Status:** Approved  
**Branch:** feat/i-want-a-feature-that-i-can-select-multi

---

## Overview

Allow the user to select multiple sessions from the CCC conversation list and launch a structured coordination session among them. Each coordination opens a new, dedicated group-chat file (separate from the global `GROUP_CHAT.md`), supports two modes (git coordination and topic coordination), and includes a live-reader panel inside the CCC so the user can follow along and participate.

---

## Touch Points

```
~/.claude/skills/group-chat/SKILL.md   ← extend for chat=, mode=, topic= args
server.py                               ← add POST /api/coordinate
                                            add GET  /api/group-chat/read
                                            add POST /api/group-chat/post
static/index.html                       ← list multi-select + floating toolbar
                                            + coordinate modal
                                            + live-reader panel
```

---

## 1. Skill changes — `~/.claude/skills/group-chat/SKILL.md`

### New `$ARGUMENTS` parameters

| Arg | Type | Meaning |
|---|---|---|
| `chat=<path>` | optional | Use this file instead of the hardcoded `GROUP_CHAT.md`. When supplied by the server the path is always absolute. When absent the skill falls back to `/Users/amirfish/Apps/claude-command-center/GROUP_CHAT.md` — no regression for existing invocations. |
| `mode=topic\|git` | optional | `git` (default, or when absent) runs the existing logic unchanged. `mode=topic` activates the topic-mode phases described below. |
| `topic="<text>"` | optional | Decorative. Echoed in the session's first post so context is visible to all participants in the chat file. |

### Topic-mode Phase 0 (replaces hunk ownership)

Instead of running `git status` / `git diff`, each session describes what it is currently working on based on its recent conversation context. This becomes the "ownership claim" written into the chat (e.g. `working on: UI redesign for auth flow`). No git commands are issued in this phase.

### Topic-mode Phase B role table

Replaces the git hunk/commit table. Applied after classifying chat state (Phase A — unchanged):

| `chat_state` | Condition | Role | Action |
|---|---|---|---|
| `DONE` | — | done | C.0 — output `we're done` |
| `EXECUTING` | named executor, step not yet done | executor | C.5 — continue/complete step |
| `EXECUTING` | not executor | observer | C.0 |
| `CONSENSUS` | named executor | executor | C.5 — start step 1 |
| `CONSENSUS` | not executor | observer | C.0 |
| `PROPOSAL_PENDING` | haven't acked, agree | acker | C.3 |
| `PROPOSAL_PENDING` | haven't acked, disagree | counter | C.4 |
| `PROPOSAL_PENDING` | already acked | observer | C.0 |
| `OPEN_QUESTION` or `EMPTY` | no proposal exists | proposer | C.2 — post plan for the topic |
| `OPEN_QUESTION` or `EMPTY` | proposal exists but unresolved | observer or acker | per table |

### Topic-mode Phase C executor (replaces git commit steps)

Step entries are freeform task reports rather than git operations:

```markdown
## <date> — `<tag>` ▶ starting step <N>
Step <N>: <description of what will be done>.
— `<tag>`
```

```markdown
## <date> — `<tag>` ✅ step <N> done
Result: <one-sentence summary of outcome>. Moving to step <N+1>.
— `<tag>`
```

No `git add`, `git commit`, or `git push` steps. No push final step. `DONE` state is reached when all steps have `✅ done` entries and no follow-up question is open.

---

## 2. Server — new endpoints

All new endpoints follow existing CCC stdlib-only conventions (`urllib`, `http.server`, `json`). No new dependencies.

### POST `/api/coordinate`

**Request:**
```json
{
  "session_ids": ["abc123", "def456"],
  "topic": "Redesign the auth flow",
  "mode": "topic",
  "sessions_meta": [
    {"session_id": "abc123", "display_name": "auth-refactor", "cwd": "/Users/amirfish/Apps/foo"},
    {"session_id": "def456", "display_name": "ui-cleanup",    "cwd": "/Users/amirfish/Apps/foo"}
  ],
  "include_human": true
}
```

**Server logic:**
1. Slugify topic (lowercase, replace non-alphanumeric runs with `-`, max 60 chars).
2. Timestamp: `YYYYMMDD-HHMMSS` in local time.
3. Create `~/.claude/group-chats/` if it does not exist.
4. Write `~/.claude/group-chats/<slug>-<ts>.md` with header:
   ```markdown
   # Group Chat — <topic>
   **Started:** <full timestamp with day-of-week and timezone>
   **Mode:** <mode>
   **Participants:** `<display_name_1>`, `<display_name_2>`, human
   ```
   Omit `human` from Participants line if `include_human` is false.
5. For each `session_id`, call `_inject_text_into_session(sid, text)` where `text` is:
   ```
   /group-chat chat=/Users/<user>/.claude/group-chats/<slug>-<ts>.md topic="<topic>" mode=<mode>
   ```
   The server must use `os.path.expanduser("~")` when building the path — never pass a literal `~` since `$ARGUMENTS` in the skill receives the string verbatim without shell expansion.
6. Return:
```json
{
  "ok": true,
  "chat_path": "~/.claude/group-chats/<slug>-<ts>.md",
  "results": [
    {"session_id": "abc123", "ok": true},
    {"session_id": "def456", "ok": false, "error": "tty not found"}
  ]
}
```

If the file cannot be created, return `{"ok": false, "error": "<reason>"}` without injecting anything.

### GET `/api/group-chat/read?path=<url-encoded-path>`

- **Sandbox check:** path must resolve to within `~/.claude/group-chats/`. Reject anything outside with 403.
- Returns: `{"ok": true, "content": "<file contents>", "mtime": <unix timestamp float>}`
- If file does not exist: `{"ok": false, "error": "not found"}`

### POST `/api/group-chat/post`

**Request:**
```json
{
  "path": "~/.claude/group-chats/redesign-the-auth-flow-20260506-143022.md",
  "text": "Can you prioritize the SSO piece first?"
}
```

**Server logic:**
1. Same sandbox check as `/api/group-chat/read`.
2. Append to file:
   ```markdown

   ---

   ## <full timestamp> — Human

   <text>
   ```
3. Returns `{"ok": true}`.

---

## 3. UI — `static/index.html`

### 3a. List-row multi-select

- New state: `let selectedListIds = new Set();` — entirely separate from the kanban's `selectedCardIds`.
- In `renderConversationList`, each `.conv-item` gets a click handler:
  - Ctrl/Cmd/Shift + click → toggle `selectedListIds` membership + `.list-selected` CSS class.
  - Plain click when `selectedListIds.size > 0` → clear all selections, then open conversation as normal.
  - Plain click when nothing selected → open conversation as normal (no change).
- After each re-render, restore `.list-selected` class on rows whose IDs are in `selectedListIds`.

**CSS additions:**
```css
.conv-item.list-selected {
  border-left: 3px solid var(--accent);
  background: color-mix(in srgb, var(--accent) 8%, var(--surface));
}
```

### 3b. Floating selection toolbar

Rendered inside `#convListPanel`, positioned `sticky` at the bottom. Shown when `selectedListIds.size >= 2`, hidden otherwise.

```html
<div id="coordToolbar" class="coord-toolbar" style="display:none">
  <span class="coord-count"></span>
  <button id="coordBtn">Coordinate…</button>
  <button id="coordClear" title="Clear selection">✕</button>
</div>
```

- Count label: `"N sessions selected"`
- Clicking "Coordinate…" opens the modal.
- Clicking ✕ clears `selectedListIds` and re-renders list.

### 3c. Coordinate modal

Appended to `<body>`, hidden until triggered. Contains:

- **Topic field** — text input, autofocused, required, max 120 chars.
- **Mode toggle** — two radio buttons: `Topic coordination` / `Git coordination`. Default set by auto-detect on modal open: compare `cwd` values of all selected sessions using `rowRepoPath()`; if all share the same repo root → `git`; otherwise → `topic`. A small line beneath reads "Auto-detected from session workspaces" (or "All sessions share a repo" / "Sessions span multiple repos").
- **Participants list** — one checkbox row per selected session showing `display_name` + truncated `cwd`. Plus a "You (human)" row, checked by default.
- **Cancel** and **Start coordination** buttons.

On Start:
1. Validate topic is non-empty.
2. Collect checked session IDs + `include_human`.
3. POST `/api/coordinate`.
4. On success: close modal, open live-reader panel for `chat_path`.
5. On partial failure (some sessions unreachable): show per-session toast, still open reader.
6. On total failure (file creation failed): show inline error in modal, don't close.

### 3d. Live-reader panel

When coordination starts successfully, the conversation pane (`#convPane`) enters **group-chat reader mode**:

- Replaces normal conversation transcript content with:
  ```
  ┌────────────────────────────────────────────────┐
  │ [topic badge]  [mode badge]       [Close ✕]   │
  ├────────────────────────────────────────────────┤
  │                                                │
  │  (markdown-rendered content of .md file)       │
  │  auto-scrolls to bottom on new content         │
  │                                                │
  ├────────────────────────────────────────────────┤  ← only if include_human
  │ [text input: "Add to chat…"]     [Send]        │
  └────────────────────────────────────────────────┘
  ```
- Polls `/api/group-chat/read?path=<encoded>` every 3 seconds. Only re-renders if `mtime` changed.
- Send button (and Enter key in input) calls `POST /api/group-chat/post`, then immediately re-polls.
- Close button (`✕`) stops polling, clears reader mode, returns conv pane to its last-viewed conversation.

**Error states:**
- 3 consecutive poll failures → show `⚠ Lost connection to chat file` banner inside reader; polling continues.
- Inject failure for a session → `showOpToast("Could not reach \`<name>\` — check its terminal", "error")`.
- File creation failure → inline error in modal, modal stays open.

---

## 4. Data flow summary

```
Ctrl-click rows in #convList
  → selectedListIds grows → toolbar appears
    → user clicks "Coordinate…" → modal opens
      → auto-detect CWDs → default mode set
        → user fills topic, confirms participants, clicks Start
          → POST /api/coordinate
              → create ~/.claude/group-chats/<slug>-<ts>.md
              → _inject_text_into_session × N
              → return {ok, chat_path, results}
            → conv pane → reader mode (polls every 3s)
            → human can type → POST /api/group-chat/post
```

---

## 5. Out of scope (explicit non-goals)

- No multi-select in kanban view (already has its own selection for column moves).
- No persistent history of past group chats in the CCC UI (files exist on disk, accessible via file system).
- No streaming / websocket for the reader (3s poll is sufficient for markdown files of this size).
- No skill invocation for the `ccc-orchestration` skill — this uses the existing `group-chat` skill only.
