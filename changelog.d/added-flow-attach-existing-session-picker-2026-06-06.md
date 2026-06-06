"+" on a repo or object node in the Flow workspace now opens a session picker instead of immediately creating a draft. The picker shows:

- **+ Create a new draft session here** at the top (the original behavior — one click, same as before).
- **Search box** — fuzzy-matches against display name, first message, session id, repo / folder label, and engine name.
- **Include archived** checkbox (on by default per user ask).
- **Scrollable session list** — up to 200 results sorted by most recent activity; click a row to attach.

Clicking a session sets `flowNodeParents[<session-node-id>] = <parent-node-id>` so it nests under the object/repo on the next render, and pins it to the flow board so an archived session attached this way stays visible regardless of the toolbar's archive toggle.
