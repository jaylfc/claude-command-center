#!/usr/bin/env python3
"""Durable, numbered, stateful UX-fixes queue shared by CCC + BookYourMat.

The annotate tools (the CCC "Add to UX fixes queue" button and BookYourMat's
``/api/v1/annotate`` route) historically *injected* annotation text straight
into one named session, interrupting whatever long-running work that session
was doing and leaving no record a second session could see.

This module replaces that fire-and-forget behaviour with a single durable
queue file. Every annotation becomes a numbered item with a status that
survives sessions, so:

  * nothing is silently dropped (it's a row, not a paragraph in a transcript),
  * a human can refer to work by number ("take #7"),
  * multiple sessions can drain the queue in parallel by *claiming* items
    instead of being interrupted by pushes.

Storage: a single JSON file (``ux-fixes-queue.json``) next to
``annotations.json`` in the CCC state dir, so both the Python CCC server and
the separate BookYourMat Node process write the same machine-global file.

Concurrency: writers from different processes are serialised with an
``fcntl`` lock file; writes are atomic via temp-file + ``os.replace``.

Item shape::

    {
      "number": 7,                       # monotonic, human-facing id
      "id": "ann-20260607-130500-ab12",  # source annotation id (if any)
      "status": "open",                  # open | in_progress | closed
      "lane": "normal",                  # normal | express  (future routing)
      "source": "ccc",                   # ccc | bym
      "note": "...",                     # the user's request
      "text": "...",                     # full formatted prompt for a session
      "url": "...", "title": "...", "selector": "...",
      "screenshot_path": "...", "repo_path": "...",
      "claimed_by": null, "claimed_at": null, "closed_at": null,
      "created_at": "2026-06-07T20:05:00Z",
      "updated_at": "2026-06-07T20:05:00Z"
    }

The file holds ``{"counter": <int>, "items": [<item>, ...]}``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # POSIX cross-process locking; degrade gracefully if unavailable.
    import fcntl  # type: ignore
except Exception:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore

# Default location: ~/.claude/command-center/ux-fixes-queue.json — overridable
# so BookYourMat (or tests) can point at the same file explicitly.
_STATE_DIR = Path(
    os.environ.get("CCC_STATE_DIR")
    or (Path.home() / ".claude" / "command-center")
)
QUEUE_FILE = Path(os.environ.get("UX_FIXES_QUEUE_FILE") or (_STATE_DIR / "ux-fixes-queue.json"))
_LOCK_FILE = QUEUE_FILE.with_suffix(".lock")

VALID_STATUSES = ("open", "in_progress", "closed")
VALID_LANES = ("normal", "express")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _FileLock:
    """Best-effort cross-process advisory lock around the queue file."""

    def __init__(self, path: Path):
        self._path = path
        self._fh = None

    def __enter__(self):
        if fcntl is None:
            return self
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self._path, "w")
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        except OSError:
            self._fh = None
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()
                self._fh = None
        return False


def _empty_store() -> Dict[str, Any]:
    return {"counter": 0, "items": []}


def _load_unlocked() -> Dict[str, Any]:
    try:
        with open(QUEUE_FILE, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    data.setdefault("counter", 0)
    items = data.get("items")
    data["items"] = items if isinstance(items, list) else []
    return data


def _save_unlocked(data: Dict[str, Any]) -> None:
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(QUEUE_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, QUEUE_FILE)


def _clip(value: Any, max_len: int) -> str:
    s = "" if value is None else str(value)
    s = " ".join(s.split()) if max_len <= 240 else s  # keep prompts multi-line
    return s if len(s) <= max_len else s[:max_len].rstrip() + "…"


def enqueue(
    *,
    note: str,
    text: str = "",
    source: str = "ccc",
    annotation_id: str = "",
    url: str = "",
    title: str = "",
    selector: str = "",
    screenshot_path: str = "",
    repo_path: str = "",
    lane: str = "normal",
) -> Dict[str, Any]:
    """Append a new ``open`` item and return it (with its assigned number)."""
    note = _clip(note, 4000)
    if not note and not text:
        raise ValueError("note or text is required")
    lane = lane if lane in VALID_LANES else "normal"
    with _FileLock(_LOCK_FILE):
        data = _load_unlocked()
        data["counter"] = int(data.get("counter", 0)) + 1
        number = data["counter"]
        now = _now_iso()
        item = {
            "number": number,
            "id": str(annotation_id or ""),
            "status": "open",
            "lane": lane,
            "source": str(source or "ccc"),
            "note": note,
            "text": _clip(text or note, 24000),
            "url": _clip(url, 1000),
            "title": _clip(title, 200),
            "selector": _clip(selector, 1000),
            "screenshot_path": str(screenshot_path or ""),
            "repo_path": str(repo_path or ""),
            "claimed_by": None,
            "claimed_at": None,
            "closed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        data["items"].append(item)
        _save_unlocked(data)
        return item


def list_items(status: Optional[str] = None, lane: Optional[str] = None) -> List[Dict[str, Any]]:
    data = _load_unlocked()
    items = data.get("items", [])
    if status:
        items = [it for it in items if it.get("status") == status]
    if lane:
        items = [it for it in items if it.get("lane") == lane]
    return items


def get(number: int) -> Optional[Dict[str, Any]]:
    for it in _load_unlocked().get("items", []):
        if int(it.get("number", 0)) == int(number):
            return it
    return None


def claim_next(session_id: str, lane: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Atomically move the oldest ``open`` item to ``in_progress`` and return it.

    Express lane is preferred when no specific lane is requested, so urgent
    items jump the line. Returns ``None`` when nothing is open.
    """
    if not session_id:
        raise ValueError("session_id is required")
    with _FileLock(_LOCK_FILE):
        data = _load_unlocked()
        candidates = [it for it in data["items"] if it.get("status") == "open"]
        if lane:
            candidates = [it for it in candidates if it.get("lane") == lane]
        if not candidates:
            return None
        # express first, then oldest number.
        candidates.sort(key=lambda it: (0 if it.get("lane") == "express" else 1, int(it.get("number", 0))))
        item = candidates[0]
        item["status"] = "in_progress"
        item["claimed_by"] = str(session_id)
        item["claimed_at"] = _now_iso()
        item["updated_at"] = item["claimed_at"]
        _save_unlocked(data)
        return item


def update_status(number: int, status: str, session_id: str = "") -> Optional[Dict[str, Any]]:
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}")
    with _FileLock(_LOCK_FILE):
        data = _load_unlocked()
        for it in data["items"]:
            if int(it.get("number", 0)) == int(number):
                it["status"] = status
                now = _now_iso()
                it["updated_at"] = now
                if status == "in_progress" and session_id:
                    it["claimed_by"] = str(session_id)
                    it["claimed_at"] = now
                if status == "closed":
                    it["closed_at"] = now
                if status == "open":
                    it["claimed_by"] = None
                    it["claimed_at"] = None
                    it["closed_at"] = None
                _save_unlocked(data)
                return it
    return None


def close(number: int, session_id: str = "") -> Optional[Dict[str, Any]]:
    return update_status(number, "closed", session_id)


def next_item(
    session_id: str,
    close_number: Optional[int] = None,
    lane: Optional[str] = None,
) -> Dict[str, Any]:
    """Self-feeding loop step: optionally close the item just finished, then
    claim the next open one. Returns ``{"closed": <item|None>, "next": <item|None>}``.

    A worker session calls this when it finishes a ticket: it closes what it
    was on and immediately gets its next ticket's prompt without a human
    pushing anything. ``next`` is ``None`` when the queue is drained.
    """
    closed = None
    if close_number is not None:
        closed = close(int(close_number), session_id)
    nxt = claim_next(session_id, lane=lane)
    return {"closed": closed, "next": nxt}


# --------------------------------------------------------------------------- CLI
# Any session can pull/inspect work without going through the HTTP server:
#   python ux_fixes_queue.py list [open|in_progress|closed]
#   python ux_fixes_queue.py claim <session_id>
#   python ux_fixes_queue.py close <number> [session_id]
#   python ux_fixes_queue.py next <session_id> [closed_number]   # close+claim-next
#   python ux_fixes_queue.py show <number>

def _fmt(it: Dict[str, Any]) -> str:
    lane = "" if it.get("lane") == "normal" else f" [{it.get('lane')}]"
    who = f" → {it['claimed_by']}" if it.get("claimed_by") else ""
    return f"#{it.get('number'):>3} {it.get('status'):<11}{lane} ({it.get('source')}){who}  {it.get('note','')[:80]}"


def _main(argv: List[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[0])
        print("usage: list|claim|close|show — see module docstring")
        return 0
    cmd = argv[0]
    if cmd == "list":
        status = argv[1] if len(argv) > 1 else None
        items = list_items(status=status)
        if not items:
            print("(queue empty)")
            return 0
        for it in items:
            print(_fmt(it))
        return 0
    if cmd == "claim":
        if len(argv) < 2:
            print("usage: claim <session_id>", file=sys.stderr)
            return 2
        item = claim_next(argv[1])
        if not item:
            print("(nothing open)")
            return 0
        print(json.dumps(item, indent=2))
        return 0
    if cmd == "close":
        if len(argv) < 2:
            print("usage: close <number> [session_id]", file=sys.stderr)
            return 2
        item = close(int(argv[1]), argv[2] if len(argv) > 2 else "")
        print(json.dumps(item, indent=2) if item else f"(no item #{argv[1]})")
        return 0
    if cmd == "next":
        if len(argv) < 2:
            print("usage: next <session_id> [closed_number]", file=sys.stderr)
            return 2
        close_n = int(argv[2]) if len(argv) > 2 else None
        result = next_item(argv[1], close_number=close_n)
        nxt = result.get("next")
        if result.get("closed"):
            print(f"# closed #{result['closed']['number']}", file=sys.stderr)
        if not nxt:
            print("(queue drained — nothing open)")
            return 0
        # stdout = the next ticket's prompt the session should now work on.
        print(f"# now working UX fix #{nxt['number']}"
              + (f"  [{nxt['lane']}]" if nxt.get("lane") != "normal" else ""), file=sys.stderr)
        print(nxt.get("text") or nxt.get("note") or "")
        return 0
    if cmd == "show":
        if len(argv) < 2:
            print("usage: show <number>", file=sys.stderr)
            return 2
        item = get(int(argv[1]))
        print(json.dumps(item, indent=2) if item else f"(no item #{argv[1]})")
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
