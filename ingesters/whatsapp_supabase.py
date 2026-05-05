"""WhatsApp → Claude Code push wake-up via Supabase Realtime.

Phase 0 of the event-bus design. Subscribes to changes on a
``public.feedback`` table populated by an upstream WhatsApp / Twilio
webhook, and on each row whose ``status`` becomes ``'acked'`` POSTs a
configurable wake-up text into a target Claude Code session through
CCC's ``/api/inject-input`` endpoint. Sub-second push replacing minute-
scale polling.

Runs as its own long-lived process. **Not** imported by ``server.py`` —
``server.py`` is intentionally stdlib-only. This adapter has its own
runtime deps (``supabase-py``); install into a dedicated venv (see
project notes) and start with ``python -m ingesters.whatsapp_supabase``.

Configuration (env vars or CLI flags, CLI wins):

    SUPABASE_URL              project URL (e.g. https://abc.supabase.co)
    SUPABASE_KEY              service_role key (typical: the feedback
                              table's RLS only grants SELECT to
                              authenticated users, so anon would see
                              zero realtime rows)
    CCC_INJECT_URL            default http://127.0.0.1:8090/api/inject-input
    CCC_TARGET_SESSION_ID     UUID of the Claude session to wake up
    CCC_INJECT_TEXT           wake-up prompt (required)

Why we listen for both INSERT and UPDATE with ``status=eq.acked``:
the typical webhook flow is INSERT a row with default ``status='new'``,
then UPDATE to ``'acked'`` after the auto-ack succeeds — meaning the
"ready to process" signal is the UPDATE, not the INSERT. Listening to
both keeps the adapter correct if a future webhook inserts directly
with ``'acked'``. We dedupe by row id with a 60s TTL so secondary
UPDATEs that happen while status is still ``acked`` don't double-fire.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from typing import Any

try:
    from realtime import AsyncRealtimeClient
    from supabase import acreate_client
except ImportError as exc:  # pragma: no cover - import-time guard
    sys.stderr.write(
        "ingesters/whatsapp_supabase.py needs supabase-py.\n"
        "Install into a venv:\n"
        "  uv venv .venv-ingest\n"
        "  uv pip install --python .venv-ingest/bin/python supabase\n"
        "  .venv-ingest/bin/python -m ingesters.whatsapp_supabase\n"
        f"\nImport error: {exc}\n"
    )
    raise

LOG = logging.getLogger("whatsapp_supabase")

# Realtime connect URL is derived from the project URL by replacing
# https:// with wss:// and appending /realtime/v1. supabase-py builds
# this internally when using its full client; we use the realtime client
# directly to keep this file dependency-light at runtime.
_DEFAULT_INJECT_URL = "http://127.0.0.1:8090/api/inject-input"
_DEDUPE_TTL_SEC = 60.0


class Daemon:
    def __init__(
        self,
        *,
        supabase_url: str,
        supabase_key: str,
        inject_url: str,
        target_session_id: str,
        inject_text: str,
    ):
        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_key = supabase_key
        self.inject_url = inject_url
        self.target_session_id = target_session_id
        self.inject_text = inject_text
        self._recent: dict[str, float] = {}
        self._stop = asyncio.Event()

    async def run(self) -> None:
        LOG.info(
            "starting · project=%s session=%s inject=%s",
            self._project_ref(),
            self.target_session_id,
            self.inject_url,
        )
        await self._replay_backlog()
        await self._subscribe_forever()

    # ── inject path ───────────────────────────────────────────────────

    def _inject(self, reason: str) -> None:
        """POST the wake-up text into the target Claude session.

        Synchronous on purpose — runs from the realtime callback thread
        and only takes a few ms locally.
        """
        body = json.dumps(
            {"session_id": self.target_session_id, "text": self.inject_text}
        ).encode("utf-8")
        req = urllib.request.Request(
            self.inject_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                payload_text = resp.read().decode("utf-8", errors="replace")
            try:
                resp_json = json.loads(payload_text)
            except json.JSONDecodeError:
                resp_json = {}
            if resp_json.get("submitted") is False:
                LOG.warning(
                    "inject typed-but-not-submitted · reason=%s · grant osascript "
                    "Accessibility (System Settings > Privacy & Security > "
                    "Accessibility) to enable auto-submit · detail=%s",
                    reason,
                    (resp_json.get("detail") or "").splitlines()[0][:160],
                )
            else:
                LOG.info("inject ok · reason=%s · resp=%s", reason, payload_text[:200])
        except urllib.error.URLError as exc:
            LOG.error("inject failed · reason=%s · err=%s", reason, exc)

    def _should_emit(self, row_id: str) -> bool:
        """Drop a row id we've already woken on within the dedupe TTL."""
        now = time.monotonic()
        # Cheap GC — a real implementation would use a proper cache, but
        # this dict stays small (one entry per inbound message per minute).
        for k, t in list(self._recent.items()):
            if now - t > _DEDUPE_TTL_SEC:
                del self._recent[k]
        if row_id in self._recent:
            return False
        self._recent[row_id] = now
        return True

    # ── backlog (one-shot REST) ───────────────────────────────────────

    async def _replay_backlog(self) -> None:
        """Replay any acked rows that haven't been replied to yet.

        Fires once on startup so a daemon restart doesn't lose events
        that landed while it was down. Same dedupe window applies.
        """
        try:
            client = await acreate_client(self.supabase_url, self.supabase_key)
            resp = (
                await client.table("feedback")
                .select("id,body,status,reply_sent_at,created_at")
                .eq("status", "acked")
                .is_("reply_sent_at", "null")
                .order("created_at", desc=False)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — log + continue, daemon still useful
            LOG.warning("backlog query failed (continuing): %s", exc)
            return
        rows = resp.data or []
        LOG.info("backlog · %d acked rows pending reply", len(rows))
        for row in rows:
            rid = row.get("id") or ""
            if rid and self._should_emit(rid):
                self._inject(reason=f"backlog id={rid[:8]}")

    # ── realtime ──────────────────────────────────────────────────────

    def _project_ref(self) -> str:
        # https://<ref>.supabase.co  →  <ref>
        host = self.supabase_url.split("://", 1)[-1]
        return host.split(".", 1)[0]

    def _ws_endpoint(self) -> str:
        ref = self._project_ref()
        return f"wss://{ref}.supabase.co/realtime/v1"

    async def _subscribe_forever(self) -> None:
        """Connect, subscribe to feedback INSERT/UPDATE, auto-reconnect.

        ``AsyncRealtimeClient`` already handles reconnect internally
        (``auto_reconnect=True``, exponential backoff up to ``max_retries``).
        We wrap that in our own outer loop so that even if the client
        gives up after max_retries the daemon recovers — networks come
        back, laptops wake from sleep, etc.
        """
        attempt = 0
        while not self._stop.is_set():
            attempt += 1
            try:
                await self._subscribe_once()
                # Clean exit (stop set) — fall out of the loop.
                if self._stop.is_set():
                    return
                # Otherwise the listen loop ended without an explicit stop
                # (server closed the socket cleanly, etc.) — reconnect.
                LOG.warning("realtime listen ended without stop; reconnecting")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                LOG.error("realtime error (attempt %d): %s", attempt, exc)
            # Outer backoff in case AsyncRealtimeClient's inner reconnect
            # hits its max_retries and surfaces.
            backoff = min(60.0, 2.0 * attempt)
            LOG.info("reconnecting in %.1fs", backoff)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass

    async def _subscribe_once(self) -> None:
        client = AsyncRealtimeClient(
            self._ws_endpoint(),
            token=self.supabase_key,
            auto_reconnect=True,
        )
        await client.connect()
        LOG.info("realtime · connected to %s", self._ws_endpoint())

        def on_state(state: Any, err: Exception | None) -> None:
            if err is not None:
                LOG.warning("realtime · state=%s err=%s", state, err)
            else:
                LOG.info("realtime · state=%s", state)

        def on_change(payload: dict[str, Any]) -> None:
            try:
                data = payload.get("data") or {}
                event_type = data.get("type") or payload.get("event") or "?"
                record = data.get("record") or {}
                rid = record.get("id") or ""
                status = record.get("status") or ""
                LOG.info(
                    "realtime · %s id=%s status=%s body=%r",
                    event_type,
                    rid[:8],
                    status,
                    (record.get("body") or "")[:60],
                )
                if status != "acked" or not rid:
                    return
                if not self._should_emit(rid):
                    LOG.info("realtime · dedup id=%s (within %.0fs)", rid[:8], _DEDUPE_TTL_SEC)
                    return
                self._inject(reason=f"{event_type} id={rid[:8]}")
            except Exception as exc:  # noqa: BLE001 — never crash the WS loop
                LOG.exception("realtime callback error: %s", exc)

        channel = client.channel("ccc:whatsapp:feedback")
        channel.on_postgres_changes(
            "INSERT",
            schema="public",
            table="feedback",
            filter="status=eq.acked",
            callback=on_change,
        )
        channel.on_postgres_changes(
            "UPDATE",
            schema="public",
            table="feedback",
            filter="status=eq.acked",
            callback=on_change,
        )
        await channel.subscribe(on_state)

        # ``connect()`` already spawned the internal reader + heartbeat
        # tasks (``_listen``, ``_heartbeat``) and ``auto_reconnect=True``
        # handles transient drops. We just have to keep the coroutine
        # alive until we're told to stop — and bail out if the socket
        # stays disconnected long enough that the inner reconnect ran
        # out of retries.
        try:
            disconnected_since: float | None = None
            poll = 5.0
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=poll)
                except asyncio.TimeoutError:
                    pass
                if not client.is_connected:
                    if disconnected_since is None:
                        disconnected_since = time.monotonic()
                        LOG.warning("realtime · socket disconnected; awaiting auto-reconnect")
                    elif time.monotonic() - disconnected_since > 30.0:
                        LOG.error("realtime · still disconnected after 30s; forcing outer reconnect")
                        return
                else:
                    if disconnected_since is not None:
                        LOG.info("realtime · socket reconnected")
                    disconnected_since = None
        finally:
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass

    # ── lifecycle ─────────────────────────────────────────────────────

    def request_stop(self) -> None:
        if not self._stop.is_set():
            LOG.info("stop requested")
            self._stop.set()


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="whatsapp_supabase",
        description="Phase-0 push adapter: Supabase Realtime → CCC inject.",
    )
    p.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    p.add_argument("--supabase-key", default=os.environ.get("SUPABASE_KEY"))
    p.add_argument(
        "--inject-url",
        default=os.environ.get("CCC_INJECT_URL", _DEFAULT_INJECT_URL),
    )
    p.add_argument(
        "--session-id",
        default=os.environ.get("CCC_TARGET_SESSION_ID"),
        help="UUID of the Claude Code session to inject into.",
    )
    p.add_argument(
        "--inject-text",
        default=os.environ.get("CCC_INJECT_TEXT"),
        help="Literal prompt text to inject (required).",
    )
    p.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return p


async def _amain(args: argparse.Namespace) -> int:
    missing = [
        name
        for name, val in (
            ("--supabase-url / SUPABASE_URL", args.supabase_url),
            ("--supabase-key / SUPABASE_KEY", args.supabase_key),
            ("--session-id / CCC_TARGET_SESSION_ID", args.session_id),
            ("--inject-text / CCC_INJECT_TEXT", args.inject_text),
        )
        if not val
    ]
    if missing:
        sys.stderr.write("missing required config: " + ", ".join(missing) + "\n")
        return 2

    daemon = Daemon(
        supabase_url=args.supabase_url,
        supabase_key=args.supabase_key,
        inject_url=args.inject_url,
        target_session_id=args.session_id,
        inject_text=args.inject_text,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, daemon.request_stop)
        except NotImplementedError:  # pragma: no cover — windows
            pass

    await daemon.run()
    return 0


def main() -> int:
    args = _build_argparser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s · %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
