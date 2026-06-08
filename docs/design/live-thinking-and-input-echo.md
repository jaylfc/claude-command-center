# Work item: live thinking + input-echo lifecycle

Status: **proposed** (not implemented). Captured from a dogfooding session.

## Problem

1. **No "Claude is thinking" signal in CCC.** The terminal TUI shows live
   `✻ Thinking…`; CCC shows nothing during the quiet stretch between input
   delivery and the first tool/output.
2. **Thinking text looked gone.** In a long-running / `--resume` session the
   persisted `~/.claude/projects/<slug>/<id>.jsonl` thinking blocks are
   **signature-only** — the reasoning text is stripped (see Findings). So
   scrollback can't show it.
3. **The send echo is ambiguous.** A safely-delivered message and a
   maybe-lost one both render as the same italic "sending…".

## Findings (measured, 2026-06-08)

- A thinking block has two parts: the reasoning **text** and a ~1.9 KB
  cryptographic **signature** (used for multi-turn integrity — you must send
  the signed block back to continue a turn that used thinking).
- The **persisted transcript strips thinking text on resume**: older turns
  keep only the signature. A *fresh* `claude -p` turn keeps its text in both
  stdout and the just-written transcript; it's stripped on the next
  resume/persist cycle. So thinking text is **ephemeral**, not absent.
- The **stdout stream** CCC live-tails carries thinking **text** in the final
  assistant message — even *without* `--include-partial-messages`.
- `--include-partial-messages` turns the coarse per-turn stream into the raw
  API delta stream: `content_block_start/stop` (thinking begins/ends),
  `text_delta`, and `thinking_delta` (carries the live reasoning text).

### Size / volume of `--include-partial-messages` (one short thinking turn)

| | lines | bytes |
|---|---|---|
| without flag | 33 | 37 KB |
| with flag | 78 | 58 KB |

≈ **2.4× events, +56% bytes**, scaling with how much Claude thinks. This is
the **stdout stream** (CCC's live tail / spawn log), **not** the durable
`~/.claude/projects` transcript, which stores final messages regardless of
the output-format flag.

## Tiers

### Tier 1 — cheap win (no flag)
Capture end-of-turn thinking **text** from the existing stdout stream's
assistant message (it's there before stripping), and persist it CCC-side so
scrollback keeps it. Gives readable thinking for live, CCC-spawn-streamed
headless sessions without the delta firehose.

Already shipped as a precursor: signature-only turns render a compact
`🧠 thought` marker; text-bearing turns get the expandable `💭 Thinking`
toggle (server `_parse_conversation_event`, client thinking render).

### Tier 2 — echo ↔ thinking lifecycle
Fuse the three-state send echo with the thinking/active signal so the echo
becomes a live turn status:

```
sending…  →  thinking…  →  done
```

- `sending…` — in flight, no ACK (may fail; keeps the not-acknowledged timer).
- `thinking…` — flip here when the session goes **active** after delivery
  (not the instant of ACK — there's a beat between "delivered" and "thinking").
- `done` — turn completes (the `result` event we already see, or the thinking
  block lands).

Works **without** `--include-partial-messages` (turn-start ≈ delivery,
turn-end = the existing `result` event). Partial-messages just makes the
start/stop precise instead of inferred. Builds on the existing
`markPendingSendDelivered` (state 2) work.

### Tier 3 — opt-in `--include-partial-messages`
True live token-by-token thinking (`✻ Thinking…` feel) + precise begin/end.
Gate behind a setting because of the 2.4× stream volume.

## Why not just always do Tier 3

1. **2.4× stream volume** → more parsing + far more frequent UI repaints (the
   WKWebView is CPU-sensitive on hot paths).
2. **Scoped** — only live, CCC-spawn-streamed *headless* sessions. Nothing for
   terminal sessions, scrollback, or sessions CCC didn't spawn.
3. **Persistence** — to keep thinking in scrollback, CCC must capture + store
   it itself (transcript strips it on resume). New CCC-side store.
4. **Re-spawn required** — the flag is set at spawn time.
5. **Complexity** — full delta-protocol handling (start/delta/stop, accumulate,
   reassemble).

## Recommendation

Do Tier 1 + Tier 2 first (cheap, broad, no firehose). Make Tier 3 an opt-in
setting for users who want the live token-by-token experience.
