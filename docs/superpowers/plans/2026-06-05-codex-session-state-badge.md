# Codex Session State Badge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a codex session's true live state (Working / Idle / Stuck / Offline) visible on both the conversation row and the open conversation pane, derived from the rollout jsonl instead of the broken command-line-SID liveness check.

**Architecture:** Backend adds a pure state classifier (`_codex_row_state`) plus two cheap probes (`_codex_pool_alive`, rollout-mtime recency), fixes codex liveness for the app-server pool model, and emits a `codex_state` (+ `codex_fresh`) field through the existing `/api/sessions/live-activity` and `/api/session-status` payloads. Frontend renders a chip on the row and a badge in the pane from that field.

**Tech Stack:** Python 3 stdlib only (`server.py`), vanilla JS (`static/app.js`), CSS (`static/app.css`), `unittest` (`tests/`).

**Spec:** `docs/superpowers/specs/2026-06-05-codex-session-state-badge-design.md`

---

## File Structure

- **Modify** `server.py`:
  - New helpers near the codex activity block (~line 15835): `_codex_fresh_threshold_s`, `_codex_recent_window_s`, `_codex_row_state` (pure), `_codex_state_fields`.
  - New cached probe near the liveness cache (~line 2398): `_codex_pool_alive` + its module cache.
  - Liveness fix in `_archive_session_is_live` (~2454-2482).
  - Emit fields in `_live_activity_entry_for_session` codex branch (~2550) and add keys to `_LIVE_ACTIVITY_FIELD_KEYS` (~2485).
  - Emit fields in `/api/session-status` codex branch (~32927-32934).
- **Create** `tests/test_codex_state.py`: pure-function unit tests (new pattern — repo currently has only import/smoke tests).
- **Modify** `static/app.js`: row chip in `flowSessionChipsHtml` (~7770), pane badge via new `updateCodexStateBadge` + `liveStatus` fields (~1839).
- **Modify** `static/app.css`: `.flow-chip.stuck/.idle/.offline`, `.flow-chip.working.steady`, `.conv-codex-state` (~4398).
- **Modify** `tests/test_smoke.py`: wiring assertions for the new server helpers + static strings.
- **Add** `changelog.d/added-codex-session-state-badge.md` (Tier B).

---

## Task 1: Pure state classifier `_codex_row_state`

**Files:**
- Modify: `server.py` (add helpers after `_codex_activity_fields_from_tail`, ~line 15916)
- Test: `tests/test_codex_state.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_codex_state.py`:

```python
import importlib
import sys
import unittest


class TestCodexRowState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for mod in ("server", "morning", "morning_store"):
            sys.modules.pop(mod, None)
        cls.server = importlib.import_module("server")

    def test_empty_tail_returns_none(self):
        self.assertIsNone(self.server._codex_row_state({}, 100.0, 100.0, True, False))

    def test_offline_when_pool_dead_and_no_live_proc(self):
        tail = {"last_event_type": "assistant"}
        self.assertEqual(
            self.server._codex_row_state(tail, 100.0, 100.0, False, False),
            "offline",
        )

    def test_live_proc_overrides_dead_pool(self):
        tail = {"pending_tool": "shell"}
        self.assertEqual(
            self.server._codex_row_state(tail, 100.0, 100.0, False, True),
            "working",
        )

    def test_working_when_mid_turn_and_fresh(self):
        tail = {"pending_tool": "shell"}
        self.assertEqual(
            self.server._codex_row_state(tail, 1000.0, 1010.0, True, False),
            "working",
        )

    def test_working_via_assistant_tail(self):
        tail = {"last_event_type": "user"}
        self.assertEqual(
            self.server._codex_row_state(tail, 1000.0, 1010.0, True, False),
            "working",
        )

    def test_stuck_when_mid_turn_and_past_stale_threshold(self):
        tail = {"pending_tool": "shell"}
        # age = 1000s > default 900s stale threshold
        self.assertEqual(
            self.server._codex_row_state(tail, 0.0, 1000.0, True, False),
            "stuck",
        )

    def test_idle_when_turn_complete(self):
        tail = {"last_event_type": "result"}
        self.assertEqual(
            self.server._codex_row_state(tail, 1000.0, 1010.0, True, False),
            "idle",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/amirfish/Apps/claude-command-center && python3 -m pytest tests/test_codex_state.py -v`
Expected: FAIL — `AttributeError: module 'server' has no attribute '_codex_row_state'`.

- [ ] **Step 3: Write the minimal implementation**

In `server.py`, immediately after `_codex_activity_fields_from_tail` (ends ~line 15915), add:

```python
def _codex_fresh_threshold_s():
    try:
        v = float(os.environ.get("CCC_CODEX_FRESH_SEC", "40"))
    except (TypeError, ValueError):
        v = 40.0
    return max(0.0, v)


def _codex_recent_window_s():
    try:
        v = float(os.environ.get("CCC_CODEX_RECENT_SEC", str(24 * 3600)))
    except (TypeError, ValueError):
        v = float(24 * 3600)
    return max(0.0, v)


def _codex_row_state(tail, mtime, now, pool_alive, has_live_proc):
    """Classify one codex session into working / idle / stuck / offline.

    Pure function (no I/O) so it is unit-testable. Caller applies the
    recency gate and resolves pool/liveness/mtime before calling.

    Priority: offline (engine down) > stuck (mid-turn, stale) >
    working (mid-turn, fresh) > idle (turn complete).
    """
    if not tail:
        return None
    mid_turn = bool(tail.get("pending_tool")) or (
        tail.get("last_event_type") in ("user", "assistant")
    )
    if not pool_alive and not has_live_proc:
        return "offline"
    if mid_turn:
        try:
            age = max(0.0, float(now) - float(mtime or 0))
        except (TypeError, ValueError):
            age = 0.0
        if age >= _codex_stale_tool_threshold_s():
            return "stuck"
        return "working"
    return "idle"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/amirfish/Apps/claude-command-center && python3 -m pytest tests/test_codex_state.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_codex_state.py
git commit --only tests/test_codex_state.py server.py -m "feat(codex): pure state classifier _codex_row_state

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Pool-alive probe + state-fields orchestrator

**Files:**
- Modify: `server.py` (cache near ~2398; `_codex_pool_alive` near the new helpers; `_codex_state_fields` after `_codex_row_state`)
- Test: `tests/test_codex_state.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_codex_state.py` (before `if __name__`):

```python
class TestCodexPoolAlive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for mod in ("server", "morning", "morning_store"):
            sys.modules.pop(mod, None)
        cls.server = importlib.import_module("server")

    def test_pool_alive_true_when_app_server_running(self):
        srv = self.server
        srv._codex_pool_alive_cache["ts"] = 0.0
        orig = srv.find_live_codex_processes
        srv.find_live_codex_processes = lambda: [
            {"pid": 1, "command": "/opt/homebrew/bin/codex app-server --listen stdio://"}
        ]
        try:
            self.assertTrue(srv._codex_pool_alive(now=1000.0))
        finally:
            srv.find_live_codex_processes = orig
            srv._codex_pool_alive_cache["ts"] = 0.0

    def test_pool_alive_false_when_no_app_server(self):
        srv = self.server
        srv._codex_pool_alive_cache["ts"] = 0.0
        orig = srv.find_live_codex_processes
        srv.find_live_codex_processes = lambda: [
            {"pid": 1, "command": "codex --resume abc123"}
        ]
        try:
            self.assertFalse(srv._codex_pool_alive(now=1000.0))
        finally:
            srv.find_live_codex_processes = orig
            srv._codex_pool_alive_cache["ts"] = 0.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/amirfish/Apps/claude-command-center && python3 -m pytest tests/test_codex_state.py::TestCodexPoolAlive -v`
Expected: FAIL — `module 'server' has no attribute '_codex_pool_alive_cache'`.

- [ ] **Step 3: Write the minimal implementation**

(a) Near the liveness cache (`server.py:2397-2398`, right after `_ENGINE_LIVE_TTL = 4.0`), add:

```python
_codex_pool_alive_cache = {"ts": 0.0, "alive": True}
```

(b) After the `_codex_row_state` helpers from Task 1, add:

```python
def _codex_pool_alive(now=None):
    """True when a `codex app-server` pool process is running.

    Cached for _ENGINE_LIVE_TTL like the engine-live scan. On any error,
    fall back to the last value (default True) so a transient ps failure
    never flips every codex row to a false 'offline'.
    """
    now = now if now is not None else time.time()
    cached = _codex_pool_alive_cache
    if now - cached["ts"] < _ENGINE_LIVE_TTL:
        return cached["alive"]
    try:
        alive = False
        for p in find_live_codex_processes():
            if "app-server" in (p.get("command") or ""):
                alive = True
                break
    except Exception:
        return cached["alive"]
    _codex_pool_alive_cache["ts"] = now
    _codex_pool_alive_cache["alive"] = alive
    return alive


def _codex_state_fields(sid, now=None):
    """Resolve {codex_state, codex_fresh} for one codex session id.

    Applies the recency gate (no chip for sessions whose rollout hasn't
    been touched within _codex_recent_window_s). Fails quiet to nulls.
    """
    fields = {"codex_state": None, "codex_fresh": False}
    if not sid:
        return fields
    try:
        path = _resolve_codex_rollout_path(sid)
        if not path:
            return fields
        mtime = os.path.getmtime(path)
    except OSError:
        return fields
    now = now if now is not None else time.time()
    if (now - mtime) > _codex_recent_window_s():
        return fields
    try:
        tail = _extract_codex_tail_meta(path) or {}
        pool_alive = _codex_pool_alive(now)
        has_live_proc = sid in _live_engine_session_ids()
        state = _codex_row_state(tail, mtime, now, pool_alive, has_live_proc)
    except Exception:
        return fields
    fields["codex_state"] = state
    if state == "working":
        fields["codex_fresh"] = (now - float(mtime)) < _codex_fresh_threshold_s()
    return fields
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/amirfish/Apps/claude-command-center && python3 -m pytest tests/test_codex_state.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git commit --only server.py tests/test_codex_state.py -m "feat(codex): pool-alive probe + codex_state field resolver

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Fix codex liveness for the app-server pool model

**Files:**
- Modify: `server.py` — `_archive_session_is_live` (~2454-2482)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_codex_state.py`:

```python
class TestCodexPoolLiveness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for mod in ("server", "morning", "morning_store"):
            sys.modules.pop(mod, None)
        cls.server = importlib.import_module("server")

    def test_recently_active_pool_codex_counts_live(self):
        srv = self.server
        sid = "test-pool-sid"
        saved = {
            "is_codex": srv._is_codex_session,
            "is_cursor": srv._is_cursor_session,
            "is_gemini": srv._is_gemini_session,
            "is_antigravity": srv._is_antigravity_session,
            "fields": srv._codex_state_fields,
            "ids": srv._live_engine_session_ids,
        }
        srv._is_codex_session = lambda s: s == sid
        srv._is_cursor_session = lambda s: False
        srv._is_gemini_session = lambda s: False
        srv._is_antigravity_session = lambda s: False
        # Recently active (any non-None codex_state) but no command-line proc.
        srv._codex_state_fields = lambda s, now=None: {"codex_state": "working", "codex_fresh": True}
        srv._live_engine_session_ids = lambda: frozenset()
        try:
            self.assertTrue(srv._archive_session_is_live(sid))
        finally:
            srv._is_codex_session = saved["is_codex"]
            srv._is_cursor_session = saved["is_cursor"]
            srv._is_gemini_session = saved["is_gemini"]
            srv._is_antigravity_session = saved["is_antigravity"]
            srv._codex_state_fields = saved["fields"]
            srv._live_engine_session_ids = saved["ids"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/amirfish/Apps/claude-command-center && python3 -m pytest tests/test_codex_state.py::TestCodexPoolLiveness -v`
Expected: FAIL — `_archive_session_is_live` returns False (pool model not yet recognized).

- [ ] **Step 3: Write the minimal implementation**

In `server.py`, change the final return of `_archive_session_is_live` (currently `return session_id in _live_engine_session_ids()`) to:

```python
    if session_id in _live_engine_session_ids():
        return True
    # Pool-model codex (Codex.app `codex app-server`) puts no session id on
    # any command line, so the resume-arg scan above misses it. A codex
    # session whose rollout was written recently (non-None codex_state) and
    # whose engine pool is up is live.
    if _is_codex_session(session_id):
        return _codex_state_fields(session_id).get("codex_state") is not None
    return False
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/amirfish/Apps/claude-command-center && python3 -m pytest tests/test_codex_state.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git commit --only server.py tests/test_codex_state.py -m "fix(codex): count pool-model sessions as live via rollout recency

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Emit codex_state through both API payloads

**Files:**
- Modify: `server.py` — `_LIVE_ACTIVITY_FIELD_KEYS` (~2485), `_live_activity_entry_for_session` codex branch (~2550), `/api/session-status` codex branch (~32927-32934)

- [ ] **Step 1: Add the field keys to the live-activity allow-list**

Locate the `_LIVE_ACTIVITY_FIELD_KEYS = (` tuple (starts ~server.py:2485). Add these two entries inside the tuple (after `"last_event_type",` or at the end, before the closing `)`):

```python
    "codex_state",
    "codex_fresh",
```

- [ ] **Step 2: Emit in the live-activity codex branch**

In `_live_activity_entry_for_session`, the codex branch currently ends with:

```python
        entry["last_event_type"] = tail.get("last_event_type")
```

Add immediately after that line (still inside `if engine == "codex":`):

```python
        entry.update(_codex_state_fields(session_id))
```

- [ ] **Step 3: Emit in the /api/session-status codex branch**

In the `if is_codex_status:` block (~server.py:32927-32934), after:

```python
                status.update(_codex_stale_tool_fields(tail))
```

add:

```python
                status.update(_codex_state_fields(sid))
```

- [ ] **Step 4: Verify import + smoke still clean**

Run: `cd /Users/amirfish/Apps/claude-command-center && python3 -c "import server; print('ok')" && python3 -m pytest tests/test_smoke.py -q`
Expected: prints `ok`; smoke tests PASS.

- [ ] **Step 5: Commit**

```bash
git commit --only server.py -m "feat(codex): expose codex_state in live-activity + session-status

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Row chip rendering (frontend)

**Files:**
- Modify: `static/app.js` — `flowSessionChipsHtml` (~7770-7814)
- Modify: `static/app.css` — after `.flow-chip.counter` (~4396)

- [ ] **Step 1: Gate the generic activity block to non-codex rows and add the codex chip**

In `static/app.js`, inside `flowSessionChipsHtml(c)`, find:

```javascript
    const wipActive = c.is_live && (
      !!c.pending_spawn || !!c.pending_tool || !!c.sidecar_in_flight
        || c.sidecar_status === 'active'
    );
    if (c.needs_approval || c.question_waiting) {
      chips.push('<span class="flow-chip waiting" title="Paused waiting for your input">WAITING</span>');
    } else if (wipActive) {
      const label = liveTool ? String(liveTool).slice(0, 16) : 'WIP';
      chips.push('<span class="flow-chip working" title="Agent is working' + (liveTool ? ' — ' + escapeAttr(String(liveTool)) : '') + '">' + escapeHtml(label) + '</span>');
    }
```

Replace it with:

```javascript
    const isCodexRow = c.source === 'codex' || c.engine === 'codex';
    const wipActive = c.is_live && (
      !!c.pending_spawn || !!c.pending_tool || !!c.sidecar_in_flight
        || c.sidecar_status === 'active'
    );
    if (isCodexRow && c.codex_state) {
      const st = c.codex_state;
      if (st === 'working') {
        const label = liveTool ? String(liveTool).slice(0, 16) : 'Working';
        const steady = c.codex_fresh ? '' : ' steady';
        chips.push('<span class="flow-chip working' + steady + '" title="Codex is working' + (liveTool ? ' — ' + escapeAttr(String(liveTool)) : '') + '">' + escapeHtml(label) + '</span>');
      } else if (st === 'stuck') {
        chips.push('<span class="flow-chip stuck" title="Stalled — no rollout activity past the stale threshold">Stuck</span>');
      } else if (st === 'offline') {
        chips.push('<span class="flow-chip offline" title="Codex engine offline — sessions paused">Offline</span>');
      } else if (st === 'idle') {
        chips.push('<span class="flow-chip idle" title="Idle — last turn complete">Idle</span>');
      }
    } else if (c.needs_approval || c.question_waiting) {
      chips.push('<span class="flow-chip waiting" title="Paused waiting for your input">WAITING</span>');
    } else if (wipActive) {
      const label = liveTool ? String(liveTool).slice(0, 16) : 'WIP';
      chips.push('<span class="flow-chip working" title="Agent is working' + (liveTool ? ' — ' + escapeAttr(String(liveTool)) : '') + '">' + escapeHtml(label) + '</span>');
    }
```

- [ ] **Step 2: Add the CSS for the new chip states**

In `static/app.css`, after the `.flow-chip.counter { color: var(--text-2); }` line (~4396), add:

```css
  .flow-chip.working.steady { animation: none; }
  .flow-chip.stuck   { background: rgba(230, 160, 60, 0.16); color: #e0a83c; border-color: rgba(230, 160, 60, 0.45); }
  .flow-chip.idle    { color: var(--text-2); }
  .flow-chip.offline { background: rgba(220, 80, 80, 0.15); color: #e06c6c; border-color: rgba(220, 80, 80, 0.45); }
```

- [ ] **Step 3: Manual verification**

Run the app (`./run.sh` or the existing dev server) and open the dashboard with a live codex session.
Expected: the codex row shows a pulsing gold `Working` chip while generating; `Idle` after `task_complete`; quit Codex.app's engine and confirm `Offline`.
(If no live codex session is handy, temporarily force `c.codex_state` in the browser console on a codex row's data to confirm each chip renders.)

- [ ] **Step 4: Commit**

```bash
git commit --only static/app.js static/app.css -m "feat(codex): row chip for Working/Idle/Stuck/Offline state

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Conversation-pane state badge (frontend)

**Files:**
- Modify: `static/app.js` — `liveStatus` fetch callback (~1839-1861), the 1s ticker that calls `updateLiveToolStrip` (search for `updateLiveToolStrip()` call site), new `updateCodexStateBadge` function
- Modify: `static/app.css` — `.conv-codex-state` rules

- [ ] **Step 1: Capture the new fields in `liveStatus`**

In `static/app.js`, in the `/api/session-status` fetch callback where `liveStatus = { ... }` is built (~1839-1861), add these two entries inside the object literal (after `sidecarInFlight: ...,`):

```javascript
        codexState: data.codex_state || null,
        codexFresh: !!data.codex_fresh,
```

- [ ] **Step 2: Add the badge renderer**

In `static/app.js`, immediately after the `updateLiveToolStrip` function definition (it ends before the next `function`), add:

```javascript
  function updateCodexStateBadge() {
    const $view = (typeof getConvView === 'function') ? getConvView() : null;
    if (!$view) return;
    const st = liveStatus.codexState;  // only set for codex sessions (server-gated)
    let badge = $view.querySelector('.conv-codex-state');
    if (!st) { if (badge) badge.remove(); return; }
    const LABELS = { working: 'Working', idle: 'Idle', stuck: 'Stuck', offline: 'Offline' };
    const TITLES = {
      working: 'Codex is working',
      idle: 'Idle — last turn complete',
      stuck: 'Stalled — no rollout activity past the stale threshold',
      offline: 'Codex engine offline — sessions paused',
    };
    const steady = (st === 'working' && !liveStatus.codexFresh) ? ' steady' : '';
    if (!badge) {
      badge = document.createElement('div');
      $view.appendChild(badge);
    }
    badge.className = 'conv-codex-state state-' + st + steady;
    badge.title = TITLES[st] || '';
    badge.innerHTML = '<span class="ccs-dot"></span><span class="ccs-label">' + escapeHtml(LABELS[st] || st) + '</span>';
  }
```

- [ ] **Step 3: Call the renderer on the same ticker**

Find the call site `updateLiveToolStrip();` (the 1s ticker). Add directly after it:

```javascript
    updateCodexStateBadge();
```

- [ ] **Step 4: Add the badge CSS**

In `static/app.css`, after the codex chip rules from Task 5, add:

```css
  .conv-codex-state {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 11px; line-height: 1; padding: 3px 8px;
    border-radius: 999px; border: 1px solid var(--border);
    background: var(--surface-2); color: var(--text-2);
  }
  .conv-codex-state .ccs-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .conv-codex-state.state-working { color: #f2cc60; animation: ccc-flow-chip-pulse 1.6s ease-in-out infinite; }
  .conv-codex-state.state-working.steady { animation: none; }
  .conv-codex-state.state-stuck   { color: #e0a83c; }
  .conv-codex-state.state-idle    { color: var(--text-2); }
  .conv-codex-state.state-offline { color: #e06c6c; }
```

- [ ] **Step 5: Manual verification**

Open a codex conversation in the pane.
Expected: a state badge appears at the top of the pane (in addition to the existing working/idle tool line), updating live as the session works / completes / stalls / engine goes offline.

- [ ] **Step 6: Commit**

```bash
git commit --only static/app.js static/app.css -m "feat(codex): conversation-pane state badge alongside live line

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Wiring smoke assertions + changelog

**Files:**
- Modify: `tests/test_smoke.py`
- Create: `changelog.d/added-codex-session-state-badge.md`

- [ ] **Step 1: Write the failing smoke assertion**

Add a new test class to `tests/test_smoke.py`:

```python
class TestCodexStateWiring(unittest.TestCase):
    def test_server_exposes_codex_state_helpers(self):
        for mod in ("server", "morning", "morning_store"):
            sys.modules.pop(mod, None)
        server = importlib.import_module("server")
        for name in ("_codex_row_state", "_codex_state_fields", "_codex_pool_alive"):
            self.assertTrue(hasattr(server, name), name)

    def test_static_renders_codex_state(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent
        js = (root / "static" / "app.js").read_text()
        css = (root / "static" / "app.css").read_text()
        self.assertIn("codex_state", js)
        self.assertIn("updateCodexStateBadge", js)
        self.assertIn("flow-chip.offline", css)
        self.assertIn("conv-codex-state", css)
```

- [ ] **Step 2: Run it**

Run: `cd /Users/amirfish/Apps/claude-command-center && python3 -m pytest tests/test_smoke.py::TestCodexStateWiring -v`
Expected: PASS (helpers exist from Tasks 1-2; static strings exist from Tasks 5-6). If it fails, the corresponding earlier task is incomplete — fix there.

- [ ] **Step 3: Add the changelog snippet (Tier B)**

Create `changelog.d/added-codex-session-state-badge.md`:

```markdown
Codex sessions now show a live state badge (Working / Idle / Stuck / Offline) on the conversation row and in the conversation pane, derived from the rollout log — fixing pool-model codex sessions that previously showed no activity indicator.
```

- [ ] **Step 4: Full test run**

Run: `cd /Users/amirfish/Apps/claude-command-center && python3 -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git commit --only tests/test_smoke.py changelog.d/added-codex-session-state-badge.md -m "test(codex): wiring assertions + changelog for state badge

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review Notes

- **Spec coverage:** Working/Idle/Stuck/Offline (Task 1 classifier + Tasks 5/6 render); liveness fix (Task 3); rollout-truth source, not CPU (Task 2 `_codex_state_fields`); both row + pane (Tasks 5, 6); recently-active gate (Task 2 recency window); env knobs `CCC_CODEX_FRESH_SEC` / `CCC_CODEX_STALE_TOOL_SEC` (Tasks 1-2). All covered.
- **Priority order** matches spec (offline > stuck > working > idle) in `_codex_row_state`.
- **No Claude-path changes:** the generic activity block is gated `isCodexRow` only — Claude/Gemini/Cursor rows keep the original `wipActive` branch.
- **Names consistent across tasks:** `_codex_row_state`, `_codex_state_fields`, `_codex_pool_alive`, `_codex_pool_alive_cache`, `codex_state`, `codex_fresh`, `updateCodexStateBadge`, `.conv-codex-state`, `.flow-chip.stuck/.idle/.offline`.
