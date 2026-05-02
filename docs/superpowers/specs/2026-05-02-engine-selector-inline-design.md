# Engine selector — inline next to new-session inputs

## Problem

Picking the spawn engine (Claude vs Codex) currently requires opening the
topbar **View ▾** menu and changing the **Engine** submenu — buried two
clicks away from where the user is actually typing the new-session prompt.

The new-session **modal** (`#nsmEngineSelect`) already has the selector
inline next to its textarea, so the modal flow is fine. The two other
new-session entry points don't:

1. **Inline bottom input bar** (`#convInput`) — what shows when the user
   clicks **+ New session** in the sidebar.
2. **Kanban toolbar input** (`#kptNewSession`) — top of the Kanban board.

Both currently read engine from `#kptEngineSelect` (the View ▾ submenu),
so changing engine for these flows requires a side-trip to the menu.

## Goal

Pick the engine from the same row as the new-session prompt input, in
both the inline bottom bar and the Kanban toolbar. No menu side-trip.

## Design

### New DOM nodes

- `#convInputEngineSelect` — `<select>` inside `.conv-input-bar`,
  occupying the **same slot the Esc button uses** (mutually exclusive
  with Esc by mode: Esc only shows for live sessions; engine selector
  only shows in `__new__` mode). Layout in new-session mode becomes
  `[input...] [engine ▾] [>] [tty-label]`.
- `#kptToolbarEngineSelect` — `<select>` in the Kanban toolbar, between
  `#kptNewSession` and the `Run` button. Layout becomes
  `[Search] [↻] [New session prompt…] [engine ▾] [Run] [board view] …`.
  Always visible (Kanban toolbar is always for spawning new sessions).

Both styled to match the existing `#nsmEngineSelect` (small dark `<select>`
with `claude` / `codex` options).

### Removed

- The **View ▾ → Engine** submenu entry (`#kptEngineSelect` and its
  surrounding `<label>`). Now redundant.

`#kptEngineSelect` references throughout the JS get replaced with a
single `getCurrentEngine()` helper that reads from `localStorage` (the
authoritative source of truth) and falls back to `'claude'`.

### Single source of truth

`localStorage.ccc.spawnEngine` stays the persisted value. On `change`,
each selector writes to localStorage and updates every other selector's
`.value` so they all stay in sync. A small helper:

```js
function setSpawnEngine(v) {
  if (v !== 'claude' && v !== 'codex') return;
  try { localStorage.setItem('ccc.spawnEngine', v); } catch (_) {}
  [$convInputEngineSelect, $kptToolbarEngineSelect, $nsmEngineSelect]
    .forEach(s => { if (s && s.value !== v) s.value = v; });
}
function getSpawnEngine() {
  try {
    const v = localStorage.getItem('ccc.spawnEngine');
    if (v === 'claude' || v === 'codex') return v;
  } catch (_) {}
  return 'claude';
}
```

### Codex-availability probe

`refreshCodexAvailability()` already greys/disables the codex option in
`kptEngineSelect` and `nsmEngineSelect`. It's extended to include the
two new selectors, and the "fall back to claude if codex disappeared"
branch goes through `setSpawnEngine('claude')` so all four nodes update.

### Spawn-time wiring

- `spawnFromInlineInput()` reads engine via `getSpawnEngine()`.
- Kanban `Run` handler reads engine via `getSpawnEngine()`.
- Modal `nsmSubmit` continues to read from `nsmEngineSelect.value`
  (already inline, already correct).

### `updateInputBar()` change

Add a branch: when `isNewSession` is true, show
`#convInputEngineSelect` and hide `#convEscBtn`. Otherwise hide the
selector. Esc visibility logic is unchanged for non-new-session modes.

### Empty-state copy

The "Start a new session" empty state currently reads
`$kptEngineSelect.value` to render "Type a prompt below … to spawn a
fresh **Claude** agent." Switch it to `getSpawnEngine()`.

## Out of scope

- Backend changes — engine routing already exists (`/api/sessions/spawn`
  vs `/api/sessions/spawn-codex`).
- Modal selector — already inline.
- The `engine` field on registry entries / `_record_spawn_to_registry`
  / availability probe endpoint — all unchanged.

## Testing

- Smoke test (`tests/test_smoke.py`) — import only, no behavior. No
  change required.
- Manual:
  - Sidebar **+ New session** → bottom bar shows `engine ▾` in place of
    Esc; switching it persists across reloads.
  - Type prompt → spawn hits the matching endpoint (`spawn` vs
    `spawn-codex`).
  - Switch engine in Kanban toolbar → bottom bar selector mirrors it.
  - Open new-session modal → its `nsmEngineSelect` reflects the same
    value.
  - With Codex CLI uninstalled, all three selectors show "codex
    (unavailable)" and fall back to claude.
  - View ▾ menu no longer has an Engine entry.

## CHANGELOG

`changelog.d/changed-engine-selector-inline-2026-05-02.md`:

> Engine picker (claude vs codex) now sits inline next to the new-session
> prompt in the sidebar input bar and the Kanban toolbar, instead of
> being buried in the View ▾ menu.
