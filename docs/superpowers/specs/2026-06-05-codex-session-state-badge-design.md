# Codex session state badge — design

**Date:** 2026-06-05
**Status:** Approved (pending spec review)

## Problem

Codex sessions show **no live "working…" indicator** in CCC, even while they
are actively generating. Worse, a session that genuinely freezes mid-turn also
shows nothing — indistinguishable from one that finished. The UI cannot be
trusted to reflect codex session state.

### Root cause (verified)

A codex session is marked **live** only when its session id appears **on a live
process command line** (`codex --resume <sid>` / agy `--conversation <sid>`) or
the session was spawned by CCC. See `_live_engine_session_ids()` and
`_archive_session_is_live()` (server.py).

But codex sessions launched through the **Codex.app `codex app-server` pool**
(one shared process — observed PID 85070, a child of CCC's `server.py`) never
put a session id on any command line. The pool shows only
`codex app-server --listen stdio://`; its worker pairs expose a cwd, no SID.
Only the pool process holds the rollout file open (confirmed via `lsof`).

Therefore `_archive_session_is_live(<pool-codex-sid>)` returns **False**, which
makes `_codex_activity_fields_from_tail(tail, live=False)` return all-None →
no badge on the row **and** no "working…" line in the conversation pane. Both
surfaces read the same `is_live` gate, so both go dark.

Separately, even when a session *is* live, a stale/stuck tool returns blank
(`_codex_stale_tool_fields` short-circuits `_codex_activity_fields_from_tail`),
so a frozen session looks identical to an idle one.

### Why process CPU can't fix it

The pool process CPU (PID 85070) is **aggregate across all codex sessions** — it
cannot be attributed to one session. The only per-session truth is the rollout
jsonl: `~/.codex/sessions/YYYY/MM/DD/rollout-*-<sid>.jsonl`. State must be
derived from that file's mtime + tail events, not from process CPU.

## Goals

- A codex session's true state is visible on **both** the conversation **row**
  (Flow/list card) and at the top of the open conversation **pane**.
- Four explicit states, no silent "blank": Working / Idle / Stuck / Offline.
- Mirror the existing Claude sidecar-field shape and rendering path where
  practical; do not disturb the Claude path.
- "Overshoot" (per user): render the full state machine in the pane in
  addition to the existing working/idle line, since that line is unreliable
  today. We can trim later.

## Non-goals

- No per-session process attribution from CPU (impossible with the pool model).
- No changes to Claude/Gemini/Cursor/Antigravity state logic.
- No hook installation into Codex (codex does not run Claude Code hooks).

## State machine

Computed per codex session that is **recently active** (rollout mtime within the
last ~24h). Older archived rows emit no state (stay clean).

"Mid-turn" = `pending_tool` set, or `last_event_type` ∈ {user, assistant}
(i.e. no `task_complete` closing the turn). Evaluated in priority order; the
first matching row wins.

| State | Condition | Chip |
|---|---|---|
| **Offline** | no codex `app-server` pool process running AND no per-session live process | red (`flow-chip offline`) |
| **Stuck** | mid-turn AND rollout mtime age ≥ `CCC_CODEX_STALE_TOOL_SEC` (default **900s** / 15 min) | amber, no pulse (`flow-chip stuck`) |
| **Working** | mid-turn AND rollout mtime age < 900s | gold (`flow-chip working`); **pulses** when age < `CCC_CODEX_FRESH_SEC` (default **40s**), steady otherwise |
| **Idle** | not mid-turn (last event `task_complete` / clean turn boundary) | muted/grey (`flow-chip idle`) |

Notes:
- **One state boundary** (900s) separates Working from Stuck — no gap. A session
  abandoned mid-turn (crash, no `task_complete`) reads Working until 900s, then
  flips to Stuck. The common freeze cause — pool death — is caught immediately
  by **Offline**, independent of timing.
- **40s is cosmetic only**: it toggles the pulse animation (actively writing vs
  quietly generating), never the state. This avoids false "Stuck" on a long
  model generation that legitimately writes nothing for a minute.
- **Stuck** reuses the existing `CCC_CODEX_STALE_TOOL_SEC` threshold (15 min).
- **Offline** is per-row (user decision): when the shared pool dies, every
  recently-active codex row shows its own "Offline" chip. No global banner.
- The CLI-resume model (codex with a SID on the command line) keeps working as
  today; the liveness fix is additive.

## Design

### Backend (server.py — stdlib only, no new deps)

1. **`_codex_session_recently_active(sid) -> bool`** (new)
   - Resolve rollout path (`_resolve_codex_rollout_path`); return True if its
     mtime is within the recent window (~24h). Cheap `stat`, no JSONL walk.

2. **`_codex_pool_alive() -> bool`** (new, cached like `_ENGINE_LIVE_TTL`)
   - True if any `codex app-server` process is running (the Codex.app pool or a
     CCC-spawned one). One `ps`-backed scan, cached.

3. **Liveness fix** — in `_archive_session_is_live()` / the codex branch of
   `_live_engine_session_ids()`: a codex session also counts as live when
   `_codex_session_recently_active(sid)` AND `_codex_pool_alive()`. This closes
   the pool-model gap without trusting Claude sidecars (preserves the existing
   anti-pollution defense for non-Claude engines).

4. **`_codex_row_state(tail, mtime, now, pool_alive, has_live_proc) -> str`**
   (new, **pure function** → unit-testable): returns one of
   `"working" | "idle" | "stuck" | "offline"` per the table above. Keeping this
   pure and side-effect-free is the key testability boundary.

5. **Emit `codex_state`** (+ `codex_fresh` bool, age < `CCC_CODEX_FRESH_SEC`,
   for the pulse-vs-steady cosmetic) in the session payload (live-activity entry
   + `/api/session-status` codex branch). `_codex_activity_fields_from_tail` is
   extended so the stale case yields `codex_state="stuck"` (not blank) and the
   clean case yields `codex_state="idle"`; the caller sets `"offline"` when the
   pool is down. Existing `sidecar_*` fields stay as-is for backward compat.

### Frontend (static/app.js + static/app.css)

6. **Row chip** — in `flowSessionChipsHtml()`, for codex engine rows, render a
   chip driven by `c.codex_state`:
   - `working` → existing gold pulse chip (now actually lights up).
   - `stuck` → new `flow-chip stuck` (amber, no animation), title "Stalled —
     no rollout activity for N min".
   - `idle` → new `flow-chip idle` (muted), title "Idle — last turn complete".
   - `offline` → new `flow-chip offline` (red), title "Codex engine offline".

7. **Conversation pane** — render the same `codex_state` badge at the top of the
   open pane, **in addition to** the existing working/idle line (overshoot).
   Reuse the `/api/session-status` poll already running there.

8. **CSS** — add `.flow-chip.stuck`, `.flow-chip.idle`, `.flow-chip.offline`
   following the existing `.flow-chip.working` pattern (color tokens, no new
   animation except the existing pulse for working).

## Data flow

```
~/.codex/sessions/.../rollout-*-<sid>.jsonl  (mtime + tail events)
        │
        ├─ _resolve_codex_rollout_path / _extract_codex_tail_meta  (existing)
        │
   _codex_row_state(tail, mtime, now, pool_alive, has_live_proc)   (new, pure)
        │
   codex_state  ──►  /api/sessions/live-activity   ──►  flowSessionChipsHtml (row chip)
                └─►  /api/session-status           ──►  pane badge + working/idle line
```

## Error handling

- Missing/unreadable rollout file → `codex_state = null` → no chip (fail quiet,
  never break the list — matches existing `try/except` liveness fallback).
- `ps` scan failure in `_codex_pool_alive` → fall back to cached value, default
  to "alive" (avoid false-Offline storms; a dead pool re-detects on next tick).
- All new helpers wrapped so a codex-state error never breaks the session list.

## Testing

- **Unit:** `_codex_row_state` is pure — assert each of the 4 states from
  synthetic `(tail, mtime, now, pool_alive, has_live_proc)` inputs.
- **Smoke:** `tests/test_smoke.py` still imports `server.py` clean.
- **Manual:** with a live pool codex session, confirm the row chip pulses
  `working` and the pane shows the badge; kill the pool and confirm `offline`;
  let a tool hang past the stale threshold and confirm `stuck`.

## Rollout

- Server + static change → ships on `git push origin main` (no DMG/release).
- Env knobs: `CCC_CODEX_FRESH_SEC` (default 40), `CCC_CODEX_STALE_TOOL_SEC`
  (existing, default 900).
