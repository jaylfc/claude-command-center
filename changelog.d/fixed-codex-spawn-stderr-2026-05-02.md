- Codex spawns now run `codex exec --ephemeral` so CCC's fire-and-watch
  path does not trigger Codex CLI's post-run "thread not found" rollout
  persistence warning. The Codex log viewer also suppresses that benign
  warning, stdin notices, and startup plugin-manifest warnings when
  rendering existing spawn logs.
