# Public telemetry aggregates

This page is the planned home for the quarterly aggregate report —
install counts by version, platform mix, engine mix, and active-day
distribution. None of those numbers exist yet.

## Status: collection not active

The Cloudflare Worker that receives the daily ping is **not yet
deployed**. The default endpoint URL baked into `server.py` —

```
https://telemetry.claude-command-center.workers.dev/v1/ping
```

— resolves to a hostname that does not currently exist, so DNS lookup
fails and the client silently skips the ping (by design; see
[`telemetry.md`](telemetry.md)).

This means:

- Even opted-in clients are not transmitting data anywhere.
- No aggregates can be produced until the Worker is live.
- When the Worker is deployed, this page will publish the first
  aggregate, the deploy commit SHA of the Worker, and the date the
  collection started.

If you opted in expecting your ping to land somewhere useful: it
isn't, yet. Sorry. This is honest pre-launch plumbing.

## When this changes

This file will be updated alongside the Worker deploy. Expect at
minimum:

- Deploy SHA of the Worker (so the IP-drop guarantee is auditable).
- First-aggregate publish date.
- Cadence (target: quarterly).
- A link to the raw aggregate JSON.

Until then, treat the telemetry feature as a contract being put in
writing before any bytes flow.
