Three mobile toolbar fixes in one ship:

1. **Reverted the temporary blue Annotate button** — it had served its purpose as a cache-bust probe and the user confirmed new CSS reaches the browser.

2. **Topbar now fits one row on phones** instead of wrapping into a second row that pushed the back button off-screen. Hidden at `max-width: 950px`: Update pill, Report-a-bug, Annotate / Screen / Notes, Worktrees, Stats, Terminal, Vercel / localhost deploy pills, and the status-rail position toggle. None of these are phone-friendly anyway. The breadcrumb now flexes to fill remaining space; its category chip caps at 96px so the conv title gets visible room.

3. **Right status rail (Original ask / Activity / Files) defaults to collapsed on mobile.** The mobile viewport doesn't have the spare width to host the rail, and surfacing it pinches the conv reader into a narrow column. Boot-time check in `index.html` adds `status-rail-collapsed` when the viewport is ≤950px UNLESS the user has explicitly opened it (localStorage = '0'); the desktop default behavior is unchanged.
