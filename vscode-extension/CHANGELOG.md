# Changelog

All notable changes to the **Claude Command Center** VS Code
extension are tracked here. Format follows [Keep a
Changelog](https://keepachangelog.com).

## [0.1.0] - 2026-05-19

### Added
- Initial Marketplace release.
- Palette command `CCC: Spawn session` — POSTs the active workspace
  folder + a user-entered prompt to the local CCC server's
  `/api/sessions/spawn` endpoint.
- Palette command `CCC: Open dashboard` — opens the CCC UI in the
  default browser.
- Configurable host/port (`claudeCommandCenter.host`,
  `claudeCommandCenter.port`); defaults match CCC's `./run.sh`.
- Graceful non-modal toast when the local CCC server isn't running.
- Publisher id `amirfish`, MIT license, 128×128 icon, repository
  link, marketplace keywords (`claude code`, `agents`, `kanban`).
