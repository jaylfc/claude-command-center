# Telemetry Worker

Minimal Cloudflare Worker that receives the daily opt-in ping from
`server.py` (see [`docs/telemetry.md`](../../docs/telemetry.md) for the
full contract). The source lives here, in this repo, so the IP-drop
guarantee is auditable.

## What it does

- Accepts `POST /v1/ping` with a JSON body matching the documented
  5-field schema (plus `schema_version`).
- Drops any unknown fields silently. Rejects requests where the listed
  fields fail type validation.
- **Drops the source IP** before writing anywhere durable. The Worker
  reads `request.headers.get("CF-Connecting-IP")` only to ignore it.
- Appends a row to a Cloudflare D1 table (or KV, depending on what we
  end up provisioning at deploy time).
- Returns `204 No Content` on success, `400` on shape errors, `405`
  on wrong method. Never returns row counts or any other state to the
  caller.

That's the entire surface.

## Status

**Not deployed.** As of this commit there is no `telemetry.claude-
command-center.workers.dev` zone. The placeholder URL the client posts
to DNS-fails silently — by design — so the client doesn't spam logs
while we get the infra ready.

When the Worker is deployed, [`docs/telemetry-public.md`](
../../docs/telemetry-public.md) will be updated with the deploy SHA
and first-aggregate date.

## Deploying

The Worker is intentionally tiny (~40 LOC) and uses zero npm
dependencies — `wrangler deploy` is the only step.

```bash
cd infra/telemetry-worker
npm install -g wrangler                # one-time
wrangler login                         # one-time, opens browser
wrangler d1 create ccc-telemetry       # one-time, capture DB id
# Add the D1 binding to wrangler.toml (omitted from this repo until deploy)
wrangler d1 execute ccc-telemetry --command "CREATE TABLE IF NOT EXISTS pings (id INTEGER PRIMARY KEY AUTOINCREMENT, received_at TEXT, install_id TEXT, version TEXT, platform TEXT, engines TEXT, last_active_date TEXT)"
wrangler deploy
```

The `wrangler.toml` is intentionally absent from this repo so the D1
binding (which contains a database id) doesn't leak. Generate it
locally at deploy time; the commit that adds it should be paired with
the doc updates in `telemetry-public.md`.

## Aggregating

The aggregate query that drives the public page (target: quarterly):

```sql
SELECT
  substr(received_at, 1, 10) AS date,
  version,
  platform,
  COUNT(DISTINCT install_id) AS installs
FROM pings
WHERE received_at >= date('now', '-90 days')
GROUP BY date, version, platform
ORDER BY date DESC;
```

No per-install rows are ever published. The Worker stores
`install_id` to support **deduplication only** (so a chatty client
can't inflate "installs"); aggregates always go through `COUNT
(DISTINCT install_id)`.

## Why this lives in the same repo

The Worker's privacy guarantees are only worth what the source backs
up. Keeping the code beside `server.py` means anyone auditing the
client can audit the server in one `git clone`. If we ever split this
out, the split itself is a breaking change to the trust contract and
should be documented in `telemetry-public.md` first.
