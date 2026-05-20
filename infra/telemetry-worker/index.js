// Telemetry Worker — receives the daily opt-in ping from CCC's server.py.
//
// Contract lives in /docs/telemetry.md; this file is the only code path
// that touches the wire. Three rules it must honor:
//   1. Drop the source IP before persistence (read-only check, never logged).
//   2. Drop unknown fields silently (forward-compat with old clients).
//   3. Reject mistyped or missing-required fields with 400 (never crash).
//
// Bound resources at deploy time (see ../README.md):
//   env.DB — Cloudflare D1 database with a `pings` table.
//
// The Worker is intentionally tiny — adding behaviour here is a privacy
// surface change and should be reviewed alongside the public contract.

const ALLOWED_PLATFORMS = new Set([
  "aix", "cygwin", "darwin", "freebsd", "haiku", "linux",
  "netbsd", "openbsd", "sunos", "win32", "wasi", "emscripten",
]);
const ALLOWED_ENGINES = new Set(["claude", "codex", "gemini"]);
const SEMVER_RE = /^\d+\.\d+\.\d+(?:[-.+][\w.-]+)?$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function validate(body) {
  if (!body || typeof body !== "object") return "body must be a JSON object";
  if (body.schema_version !== 1) return "schema_version must be 1";
  if (typeof body.install_id !== "string" || !UUID_RE.test(body.install_id)) {
    return "install_id must be a uuidv4";
  }
  if (typeof body.version !== "string" || !SEMVER_RE.test(body.version)) {
    return "version must be semver";
  }
  if (typeof body.platform !== "string" || !ALLOWED_PLATFORMS.has(body.platform)) {
    return "platform must be a known sys.platform value";
  }
  if (typeof body.engines !== "string") return "engines must be a string";
  const engines = body.engines === "" ? [] : body.engines.split(",");
  for (const e of engines) {
    if (!ALLOWED_ENGINES.has(e)) return `unknown engine: ${e}`;
  }
  if (typeof body.last_active_date !== "string" ||
      (body.last_active_date !== "" && !DATE_RE.test(body.last_active_date))) {
    return "last_active_date must be YYYY-MM-DD or empty";
  }
  return null;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/v1/ping") {
      return new Response("not found", { status: 404 });
    }
    if (request.method !== "POST") {
      return new Response("method not allowed", { status: 405 });
    }
    // Touch but do not log/store the source IP. The whole point of the
    // Worker living between client and storage is this drop.
    // eslint-disable-next-line no-unused-vars
    const _droppedIp = request.headers.get("CF-Connecting-IP");
    let body;
    try {
      body = await request.json();
    } catch (_) {
      return new Response("invalid json", { status: 400 });
    }
    const err = validate(body);
    if (err) return new Response(err, { status: 400 });
    try {
      await env.DB.prepare(
        "INSERT INTO pings (received_at, install_id, version, platform, engines, last_active_date) " +
        "VALUES (?, ?, ?, ?, ?, ?)"
      ).bind(
        new Date().toISOString(),
        body.install_id,
        body.version,
        body.platform,
        body.engines,
        body.last_active_date || ""
      ).run();
    } catch (_) {
      // Don't leak storage errors to the caller. The client retries
      // tomorrow anyway; logging here is best-effort.
      return new Response("", { status: 500 });
    }
    return new Response(null, { status: 204 });
  },
};
