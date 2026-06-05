"Active Group chat" pill no longer lingers after the user stops orchestration. Two fixes in `gcShouldShowActivePill`:

1. **Hard short-circuit on paused / closed / orchestrator-off.** A chat with `status === 'paused'`, `paused === true`, or `orchestrator_timer_active === false` returns false from the show-gate immediately — the pill claims "active right now"; the moment the user clicks Stop, the pill must respect that, not coast on the trigger-freshness window.

2. **Dropped `last_mtime` from the freshness calc.** It's the chat file's stat mtime which the server bumps on metadata writes (name_map updates, polled sidecar writes), not real message arrivals. The label-side code already filtered it out for the same reason; the show/hide gate now matches.

Plus an optimistic local patch in `setGroupChatPaused` so the pill drops within one render tick of the Stop click instead of waiting for the next 15s `gcActive` poll to land.
