# In-app bug report widget → GitHub issue

A floating **Report an issue** button for your web app that screenshots the
page client-side, posts everything to your backend, and opens a
fully-contextualized GitHub issue — screenshot embedded, debug context
pre-attached.

This is the production-facing sibling of the
[Annotate → UX-fixes queue](annotate-to-ux-fixes-queue.md) recipe: Annotate is
a localhost dev tool for *you*; this widget is for *your real users and staff*,
running in production behind your app's normal auth.

## What this gives you

A user hits a bug. Instead of a vague email ("the schedule is broken??"), you
get a GitHub issue that already contains:

- the user's description, typed into a small modal,
- a **screenshot of exactly what they were looking at** (captured client-side
  the moment they clicked the button — before the modal covers the page),
- page URL, user agent, viewport size + DPR + orientation, URL params,
- **the last element they tapped** before reporting (selector, label,
  coordinates, how many seconds before capture) — usually the button that
  misbehaved,
- any app-specific context your pages registered (selected filters, open
  modal, active record id),
- who submitted it and from which account/organization.

Because the issue lands in GitHub with reproduction context, it's immediately
actionable — by a human, or by a Claude Code session that watches the issue
queue.

## Why this design

- **Screenshot at click time, not submit time.** The capture happens when the
  user clicks the floating button, *before* the modal opens. What you see in
  the issue is the broken state, not your own report form.
- **Client-side capture (`html2canvas-pro`)** needs no browser permissions, no
  native APIs, works on mobile. Dynamic-import it so it stays out of your
  initial bundle. JPEG at ~0.85 quality keeps payloads reasonable.
- **The backend owns the fan-out.** The browser sends one JSON payload; the
  server decides what happens: upload screenshot to storage, create the GitHub
  issue, optionally email a notification. Adding a destination never touches
  the client.
- **GitHub issue creation is best-effort.** If the GitHub API call fails, the
  user still gets a success response — never block a bug *report* on the bug
  *tracker* being reachable.
- **Screenshot goes to storage, issue gets a URL.** GitHub's issues API does
  not accept file attachments, so upload the image to object storage (Supabase
  Storage, S3, whatever you have) and embed the public URL as
  `![screenshot](...)` in the issue body.

## Architecture

```
browser                          your backend                       destinations
┌─────────────────────┐  POST   ┌──────────────────────┐
│ floating FAB        │ ──────▶ │ /api/v1/bug-report   │ ──▶ object storage (screenshot → public URL)
│ click → html2canvas │  JSON   │ auth, validate,      │ ──▶ GitHub REST: POST /repos/{owner}/{repo}/issues
│ → modal → submit    │         │ enrich, fan out      │ ──▶ (optional) notification email
└─────────────────────┘         └──────────────────────┘
```

## The payload

What the widget sends to your backend:

```json
{
  "type": "problem",
  "description": "Save button does nothing on the schedule page",
  "screenshot": "data:image/jpeg;base64,....",
  "pageUrl": "https://app.example.com/dashboard/schedule?week=2026-06-08",
  "userAgent": "Mozilla/5.0 ...",
  "viewport": { "width": 390, "height": 844, "dpr": 3, "orientation": "portrait" },
  "searchParams": { "week": "2026-06-08" },
  "appContext": { "selectedView": "week", "openModal": null },
  "lastTap": {
    "selector": "button.save-btn",
    "label": "Save",
    "x": 312, "y": 88,
    "msBeforeCapture": 4200
  }
}
```

`type` is `"problem" | "feature"` — same widget doubles as a feature-request
box, and the server maps it to the `bug` / `enhancement` issue label.

## Step-by-step deployment

1. **Create a GitHub token** with `issues: write` on the target repo
   (fine-grained PAT or a GitHub App). Put it in your backend env:
   `GITHUB_TOKEN=ghp-test-XXXX` (never in client code) plus
   `GITHUB_REPO=yourname/yourrepo`.
2. **Pick screenshot storage** and create a bucket/prefix for bug reports
   (e.g. Supabase Storage bucket `bug-reports` with public read).
3. **Implement widget + route** — hand the prompt below to Claude Code in your
   repo.
4. **Smoke-test**: click the FAB, submit a test report, confirm the issue
   appears in GitHub with the screenshot rendering inline.
5. **Optional**: point a Claude Code session (or a CCC-managed worker) at the
   repo's issues to triage/fix incoming reports.

## The prompt

Paste this into Claude Code inside **your app's repo** (fill in the
ALL-CAPS placeholders):

```text
Add an in-app "Report an issue" widget to this project: a floating button that
screenshots the page, posts to our backend, and opens a GitHub issue.

## Client widget

1. A small draggable floating action button (FAB), rendered on authenticated
   pages. Persist its dragged position in localStorage. Distinguish drag from
   click with a ~5px movement threshold.
2. On click — BEFORE opening any modal — capture:
   - a screenshot of document.body using html2canvas-pro (dynamic import so it
     stays out of the initial bundle), scale = window.devicePixelRatio,
     exported as JPEG dataURL at 0.85 quality, ignoring the FAB element itself;
   - a context snapshot: page URL, viewport {width, height, dpr, orientation},
     URL search params, and the last tapped element (install a lightweight
     global click/tap tracker that records selector, role, label, text, x/y,
     element id, and timestamp — exclude taps on the FAB itself).
   If the screenshot fails, still open the modal — a report without a
   screenshot beats no report.
3. The modal: a type toggle (Problem / Feature request), a required description
   textarea, and a preview thumbnail of the captured screenshot. On submit,
   POST everything as JSON to /api/v1/bug-report. Show a success toast with
   the resulting issue URL if one comes back.
4. Optionally expose a global hook (e.g. window.__openBugReport = openFn) so
   other UI (menus, error boundaries) can trigger the same flow.

## Server route — POST /api/v1/bug-report

1. Require this app's normal auth; reject anonymous calls. Validate that
   description is non-empty and type is "problem" | "feature".
2. Decode the screenshot dataURL to a Buffer and upload it to STORAGE_CHOICE
   (bucket "bug-reports", filename from timestamp + submitter), getting back a
   public URL. Upload failure must not fail the request — degrade to a
   "(screenshot upload failed)" note.
3. Create a GitHub issue via the REST API:
     POST https://api.github.com/repos/${GITHUB_REPO}/issues
     headers: Authorization: Bearer ${GITHUB_TOKEN},
              Accept: application/vnd.github+json
     body: {
       "title": "[APP_NAME Problem] <first 80 chars of description>",
       "labels": ["bug"]  // or ["enhancement"] for feature requests
     }
   Issue body (markdown): the description, then a "### Context" table
   (submitted by, page URL, viewport, URL params, last tap, timestamp), an
   optional "### App context" json block, and "### Screenshot" with
   ![screenshot](<public URL>).
   GitHub failure is logged but non-blocking — the user still gets success.
4. GITHUB_REPO and GITHUB_TOKEN come from server env vars only; never expose
   them to the client. Respond with { sent: true, issueUrl }.
5. Optional: also send a notification email to BUG_REPORT_NOTIFY_EMAIL with
   the same content and the screenshot attached.

## Constraints
- No new client-visible secrets. The browser only ever talks to our own route.
- Match this codebase's existing conventions for components, routes, and auth
  helpers.
- Keep html2canvas-pro out of the main bundle (dynamic import on first click).

Verify end-to-end: run the app, submit a test report, and confirm a GitHub
issue exists with the screenshot rendering inline and correct labels.
```

## Hard-won details (from the reference implementation)

These came out of running this widget in production at
[BookYourMat](https://bookyourmat.com); steal them:

- **`msBeforeCapture` on the last tap is gold.** "User tapped *Save* 4.2s
  before reporting" usually *is* the repro.
- **Snapshot context before the modal opens**, then prefer the snapshot over
  live values at submit time — otherwise the URL/viewport describe your modal,
  not the bug.
- **Per-page app context hook**: let pages register a small
  `appContext` object (selected filters, open record). The widget includes
  whatever is registered at capture time. Cheap to add, massively shortens
  triage.
- **One email per recipient, not one email with N recipients** — a single bad
  address shouldn't block the others. Dedupe first.
- **Cap the GitHub issue title** (~80 chars from the description) and put the
  full text in the body; GitHub truncates ugly.
- **Different submitter kinds can fan out differently.** The reference routes
  staff reports to GitHub issues, but end-customer reports into the app's own
  inbox/escalation surface — customers shouldn't show up in your issue
  tracker raw. Start with everything → GitHub; split later if you have two
  audiences.
