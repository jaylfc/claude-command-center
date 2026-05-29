Two conversation-list QA fixes:

1. `WIP` badge no longer fires just because a linked GitHub issue carries the `claude-in-progress` label — that's not a liveness signal and made idle sessions read as actively running. The GH state now renders as a separate muted `issue: in progress` chip. Also tightened the codex/gemini/antigravity "open turn" heuristic from 30 minutes to 5 so an idle session no longer flags WIP for half an hour after the last message.

2. In Progress section now shows a footer like `+ 42 older sessions hidden by 7d — show All` when the 1d/7d window is filtering rows out, so sessions outside the window don't read as "disappeared". Clicking the footer flips the window to "all".
