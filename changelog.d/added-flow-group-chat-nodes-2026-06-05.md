Group chats are now first-class nodes on the Flow workspace alongside repos and objects:

- **Render**: every entry in the existing `_gcActiveChats` cache shows up as a cyan-accented `flow-node-group-chat` card with the chat's topic, participant count, status, and last-activity timestamp.
- **"+ Group chat" toolbar button** sits next to "+ Object". Click it and the existing new-group-chat dialog (window-prompt for the name, `/api/coordinate` POST) runs; once `pollGcActive` refreshes, the new node appears on the board automatically.
- **Drag a session node onto a group-chat node** to add the session as a participant — same outcome as dragging a conv-list row onto a chat row in the sidebar. The session card snaps back to its repo cluster (sessions stay under their repo for layout purposes; the chat just registers the participation via `/api/group-chats/add-participant`).
- **Click a group-chat node** to open the chat reader through the existing `openGroupChatReader` entry point.

All three node kinds (repo / object / group-chat) participate in the Organize layout the same way — they anchor at their current position and the overlap resolver minimises movement.
