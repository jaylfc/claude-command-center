Flow edges (the curved lines connecting child nodes to their parent object/repo) are now first-class objects you can manipulate:

- **Click an edge to select it.** Selected edges thicken and turn orange so they stand out from the rest of the board.
- **Backspace / Delete with an edge selected** removes the parent assignment; the child falls back to its default repo group (or no parent). Skipped automatically when focus is in a text field so the shortcut doesn't hijack typing.
- **Drag any edge to reconnect it.** Pointer-down on the line starts a reparent drag — a dashed ghost line follows the cursor, candidate parent nodes light up orange, and dropping on one re-links the child to that new parent. Drop outside any node to cancel. Cycle-prevention: a node can't become its own ancestor.
- **Click background or hit Escape** to clear the edge selection.

Edges now render as `<g class="flow-edge">` carrying a wide invisible hit path on top of the thin visible line — clicking the visible 1.6px stroke is unreasonably hard, so the hit-target widens to 14px while staying invisible.
