"""Regression test for per-session engine-detection memoisation.

`_detect_session_engine` falls through to expensive probes — `_is_gemini_session`
JSON-parses every Gemini chat on disk — so for a Claude session it scans the
whole Gemini store. This ran per-session on every `/api/sessions/live-activity`
poll and per-participant on every group-chat open. A session's engine is
immutable, so the result is memoised: non-"claude" forever, "claude" with a
short TTL (a just-spawned non-Claude session's store may appear a beat later).
"""
import server


def test_claude_result_served_from_cache(monkeypatch):
    calls = {"n": 0}
    real = server._detect_session_engine_uncached

    def counting(sid):
        calls["n"] += 1
        return real(sid)

    monkeypatch.setattr(server, "_detect_session_engine_uncached", counting)
    with server._engine_detect_lock:
        server._ENGINE_DETECT_CACHE.clear()

    sid = "deadbeef-0000-0000-0000-000000000000"  # no engine store -> claude
    e1 = server._detect_session_engine(sid)
    e2 = server._detect_session_engine(sid)
    assert e1 == e2 == "claude"
    assert calls["n"] == 1  # second call served from cache, no re-probe


def test_claude_cached_with_ttl(monkeypatch):
    monkeypatch.setattr(server, "_detect_session_engine_uncached", lambda sid: "claude")
    with server._engine_detect_lock:
        server._ENGINE_DETECT_CACHE.clear()
    monkeypatch.setattr(server.time, "time", lambda: 1000.0)
    server._detect_session_engine("s-claude")
    _engine, expiry = server._ENGINE_DETECT_CACHE["s-claude"]
    assert expiry == 1000.0 + server._ENGINE_DETECT_TTL  # re-checked after TTL


def test_non_claude_cached_forever(monkeypatch):
    monkeypatch.setattr(server, "_detect_session_engine_uncached", lambda sid: "codex")
    with server._engine_detect_lock:
        server._ENGINE_DETECT_CACHE.clear()
    assert server._detect_session_engine("s-codex") == "codex"
    engine, expiry = server._ENGINE_DETECT_CACHE["s-codex"]
    assert engine == "codex"
    assert expiry is None  # definitive — never expires


def test_empty_session_id_is_claude(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(
        server, "_detect_session_engine_uncached",
        lambda sid: calls.__setitem__("n", calls["n"] + 1) or "codex",
    )
    assert server._detect_session_engine("") == "claude"
    assert calls["n"] == 0  # short-circuits before the cache / probe
