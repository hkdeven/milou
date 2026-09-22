# Changelog

All notable changes to Milou are recorded here. The living case study contains
the detailed reasoning and decisions behind each change.

## Unreleased

### Added

- Added the console (`milou_news/console.py`, `routines/console.md`) and started
  it with `milou serve`. Milou was a command line and a read-only view of stored
  reports; it is now something you open, with the routines on the left, any of
  them built on demand, and the two inbox actions reachable from the row they
  belong to. Reports are built by the routines that build them and rendered by
  the renderer the archive already used, so the console adds navigation and
  actions rather than a second way of producing reports.
- The action forms are server-rendered, and every recomputation is a round trip.
  That trades a request for the property that the sprint rule, the composed
  description and the reply's questions have exactly one implementation, in
  Python, rather than a browser copy free to drift from it — and it makes the
  console work in any viewer that can submit a form.
- Writes from the console are bounded three ways on top of the existing approval
  boundary: an authenticated session (a bearer token can read a report and is
  refused for an action, so a read credential cannot become a write credential),
  a per-session CSRF token compared in constant time, and a named approver. With
  no write credentials configured the console is fully usable and changes
  nothing; a rehearsal is reported as a rehearsal, never as a created ticket.
- Moved the application shell's stylesheet into `render_html.APP_STYLES`, so the
  prototype renders the product's own CSS instead of a copy of it.
- Added the live sprint tracker writer (`milou_news/worddoc.py`), now that the
  tracker is known to be a Word document stored online. A `.docx` is a zip
  containing `word/document.xml`, and the edit works on that markup as text,
  splicing in one paragraph cloned from the line above it so it inherits the
  section's numbering. Every other byte, and every other file in the zip, is
  carried across unchanged — parsing and re-serialising the XML would reorder
  attributes and drop namespace declarations Word put there deliberately. A
  missing sprint heading writes nothing, a repeat run writes nothing, a target
  that is not a `.docx` is refused before upload, and the previous bytes are kept
  first. It needs `MILOU_DOCUMENT_WRITE_TOKEN` (`Files.ReadWrite`), separate
  again from the mail and Zoho credentials, and stays inactive until
  `document_url` is configured.
- Made the ticket status a picker over the portal's own statuses. Zoho custom
  statuses are per-portal, so `statuses` is configuration and `ready_status`
  (default `Ready for Development`) is the one selected. A default outside the
  list is a configuration error, and a status outside the list cannot be
  approved: Zoho rejects an unknown status with an error that names no
  alternatives.
- Added a composed ticket description (`milou_news/intake.py`) with a fixed shape
  on every ticket: type, who requested it, who reported it, when it was reported,
  the project or record, a summarised context, and every document link shared in
  the thread. Bug reports carry two facts a change request does not — the
  reporter, who is usually not the sender, and the report date — and both are
  **required**, so a bug ticket cannot be created half-blind. Both are extracted
  from the wording where possible and marked as guesses; where nothing is found
  the field stays empty rather than being invented. Correcting any field
  re-composes the description, so the prose and the fields cannot disagree.
- Added the context reply: a second action on every email that replies to the
  whole thread asking for the full name of whoever reported or requested it, the
  project or record title, the date, and any documentation. The questions are
  derived from what is actually missing rather than from a template, and when
  nothing is missing it asks them to confirm the guesses instead. Recipients are
  reply-all minus the user's own address.
- Added the acknowledgement draft: after a ticket is created, a reply-all is
  left **in Outlook's Drafts** telling the thread the ticket number, that the
  development, release and change log can be followed against it, and the
  expected release date stated as the latest it should take. The number is a
  placeholder until Zoho allocates one. It is drafted, never sent, and a failed
  ticket leaves no draft.
- Added `MILOU_OUTLOOK_WRITE_TOKEN`, separate from the monitor's read token.
  Sending uses `Mail.Send` alone; editing the recipient list would need
  `Mail.ReadWrite`, so it is refused rather than silently requiring the wider
  grant. Owner is now a ticket field, defaulting to unassigned.
- Added `--draft-reply`, `--to`, `--dry-run`, `--reported-by`, `--reported-on`,
  `--requested-by`, `--record`, `--owner` and `--status` to the inbox monitor,
  and `routines/context-reply.md`.
- Added the first write capability, behind an explicit approval boundary: a Zoho
  ticket can be drafted from one email, carrying the email's scope, context and a
  link back to the source message. The plan describes exactly what would change
  and creates nothing until a named person approves it; approval is bound to the
  plan's contents, so editing it afterwards clears the approval.
- Added sprint scheduling (`milou_news/sprints.py`). Sprints start every
  Wednesday and a ticket belongs to the next Wednesday strictly after its
  creation day, so Tuesday work is picked up the next morning and Wednesday work
  waits a week. Tickets are created with status `Ready for Development`, tagged
  with the sprint (`2 OCT SPRINT`), and given an expected release date matching
  that sprint.
- Added the sprint tracker document line — the last four digits of the ticket
  number, a dash, and the title — built after creation, because the ticket
  number does not exist before then. A failed ticket writes no line.
- Added `--draft-ticket`, `--title`, `--approve` and `--ticket-config` to the
  inbox monitor, and a separate `MILOU_ZOHO_WRITE_TOKEN` so a read token can
  never perform a write.

- Added the read-only `zoho-projects-radar` routine, its contract, a sample
  portal fixture, and a Zoho Projects adapter. Comments are its top tier by
  design: a comment usually needs a response whether or not it is a direct
  question, so it is never demoted for lacking one. Endpoint paths are
  configuration with documented defaults, because Zoho's REST surface differs
  across portal API versions.
- Added cross-routine coverage (`milou_news/coverage.py`), so the same event is
  never reported by two routines. A routine publishes the record identifiers and
  titles it demonstrably reported plus the notification domains it makes
  redundant; the inbox monitor suppresses a notification only when it matches
  that evidence, counting it as `already reported by <routine>`. A notification
  from a covered domain that cannot be matched is counted separately and raised
  as a coverage gap rather than dropped, because that usually means the covering
  routine is missing a project, a permission, or a window.
- Added `--zoho-coverage` to the inbox monitor, and a `coverage.zoho` payload
  section so scheduled inbox runs de-duplicate the same way.
- Added `milou_news/render_text.py`, a shared Markdown renderer for any
  structured report, replacing the copy that lived in the inbox monitor.

- Added the read-only `outlook-inbox-monitor` routine, its contract, a sample
  mailbox fixture, and a Microsoft Graph adapter. It is built to replace opening
  the inbox rather than summarise it: output is capped (default 8 items), most
  mail is excluded by explicit rules, and exclusions are counted rather than
  listed so the reader can calibrate trust. Four things earn a line — a sender
  who states they are blocked, a request addressed directly to the user and
  unanswered, a promise in the user's own sent mail, and sent mail that asked
  something and has had no reply after a configurable number of business days.
  Each line states an action, quotes the sentence that triggered it, and says
  why it surfaced.
- Added `--follow-up-days` and `--max-items` so the monitor's thresholds are
  configuration rather than constants, overridable per run.
- Added a quoted-sentence line to rendered record rows, so a row can show the
  evidence that produced it rather than only naming it.

- Added report persistence to scheduled runs. `Scheduler.run_due` now accepts a
  report store and `run` accepts `--store`; the report is saved with its
  structure and its path recorded in the ledger's previously unused
  `report_path` column, so a run can be traced to what it produced. A storage
  failure is recorded as a run failure rather than passing silently.
- Added the structured report to `DispatchResult`, so a routine dispatched
  through the supervisor carries both formats rather than Markdown alone.

- Added structured reports for the remaining eight fixture-backed routines, so
  every routine renders as both Markdown and the HTML layout from one parse.
  Classification the routines already performed is now carried as tiers: stale
  work by urgency, Dependabot updates by severity ahead of age, commitments by
  how long they have gone unanswered, launches by stated confidence, travel by
  what is still unresolved, and Daily Wins keeps verified facts and inferred
  impact in separate tiers.
- Added `build_routine_report` and a canonical routine-to-builder registry, and
  wired structured reports through scheduled generation so a stored report keeps
  its structure however it was produced.
- Moved four entries that describe shipped work out of "Not implemented", where
  they had drifted, and dropped a stale note describing the GitHub Change Radar
  as a future slice after it shipped.

- Added fixture-backed Commitments and Follow-Up Tracker, Stale Work Finder,
  and Dependabot PR Triage routines, registry entries, canonical CLI paths,
  contracts, fixtures, and read-only tests/documentation.
- Added durable SQLite routine configuration and scheduler ledger with daily/
  weekly timezone-aware due calculation, enabled state, bounded visible retries,
  idempotency keys, read-only permission enforcement, and scheduler/status/run/
  ledger CLI commands.
- Added authenticated archive health/status JSON endpoints and scheduler
  configuration documentation.
- Made same-second archived routine reports distinct by including the routine
  name in stored filenames.

- Added a structured report model (`milou_news/report.py`) and an HTML renderer
  (`milou_news/render_html.py`) shared by every output format. Reports now order
  rows by consequence before recency, give each record field its own column,
  promote coverage/API/permission failures above the findings, and demote
  boilerplate to a footer. The GitHub Change Radar and the daily global AI news
  brief build structured reports; Markdown output is unchanged.
- Added `--format html` to the report CLI, structured storage in `ReportStore`,
  and the redesigned authenticated archive index, report, and sign-in pages. A
  report stored without structure still renders from its Markdown.
- Added the ranking breakdown, the region-diversity adjustment, and the
  de-duplication outcome to the daily brief as visible structure: each item
  shows the weighted contributions behind its score, items promoted for region
  coverage are marked as such, and a dropped duplicate names the account that
  survived and what it scored lower on.
- Declared the brief's ranking weights once (`WEIGHTS`, `NON_US_BONUS`,
  `MAX_SCORE`) so the ranker and the rendered score breakdown cannot drift, and
  added `partition_duplicates` to report which duplicate was dropped rather
  than only how many.
- Added a repository `.gitignore` so Python bytecode caches, local report
  archives, and scheduler database files stay out of version control.
- Added report signal-to-noise refinement: consistent KPI blocks, omission of
  empty activity sections/categories, concise no-activity reports, and
  separately visible coverage/API/permission warnings. Change Radar KPIs now
  include repositories scanned, change types, contributors, and high-risk
  counts.

- Added browser-friendly report authentication: a minimal root login form,
  constant-time token validation, short-lived server-side Secure/HttpOnly/
  SameSite session cookies, logout, and retained Bearer API/CLI support.
  Unconfigured tokens still fail closed and credentials are not emitted in
  URLs, HTML, or logs.
- Added the read-only, bounded GitHub Change Radar with authenticated `gh`
  CLI/API collection, explicit repository/organization scope, direct
  citations, categories, timestamps, visible failures, deterministic fixtures,
  tests, and a real-report CLI path. No token is exposed or stored.
- Clarified Allied-Steel-Buildings as the default/highest-priority organization
  scope, added non-user activity priority, bounded pagination/rate-limit
  visibility, expanded event fields and lifecycle categories, per-repository
  and per-author summaries, risk signals, and explicit coverage gaps without
  mention filtering.
- Added fixture-backed Launch Decoder, Launch Radar, and Travel Logistics
  Tracker routines with canonical CLI aliases, registry metadata, contracts,
  fixtures, cited uncertainty/unknowns, and read-only tests.
- Added deterministic supervisor planning/dispatch with explicit read-only
  permission checks, routing metadata, and failure visibility.
- Made `ReportStore` filenames collision-safe for same-second reports and
  normalized callable archive labels to canonical routine names.

- Added fixture-backed `daily-wins-recap` and
  `morning-brief-meeting-prep` routines, registry entries, CLI selection,
  callable storage, deterministic fixtures, contracts, and report output.

- Added a standard-library delivery slice with dated Markdown/JSON report
  persistence, fixture-backed generation callable/CLI storage, and a
  responsive bearer-authenticated index/archive that fails closed when its
  token is not configured.
- Added private-host/reverse-proxy deployment guidance without deploying or
  adding credentials.

- Added the first safe vertical slice of the daily global AI news brief:
  explicit routine registry, configured sources, injectable JSON fetching,
  freshness filtering, duplicate handling, explainable ranking, diversity
  selection, citation-linked Markdown output, fixtures, tests, and a CLI.
- Established the initial repository structure for Milou, a bounded
  supervisor/control plane over replaceable routines.
- Added the living automation case study under `docs/`.
- Added the supervisor architecture and safety boundaries.
- Added a routine contract and activation checklist under `routines/`.
- Added the project README and documentation workflow rule.
- Added a vetted initial source set for a global AI news brief.
- Added the proposed `daily-global-ai-news-brief` routine contract with
  ranking, geographic weighting, freshness, citation, uncertainty, and
  read-only requirements.
- Corrected the canonical GitHub repository identity to
  [`hkdeven/milou`](https://github.com/hkdeven/milou); Milou remains the
  supervisor agent name.
- Added the supplied Milou visual identity at `docs/assets/milou.png` and
  linked it from the canonical README.
- Refined the README image presentation to a smaller, left-aligned,
  text-wrapping figure without changing the source asset.
- Moved the image to the start of the introductory paragraph using inline
  left-float markup so the opening text wraps around it.
- Recorded the accepted manual README layout correction and the lesson to
  validate GitHub-rendered layout visually.

### Fixed

- A hand-edited ticket description was overwritten on the submission that
  approved it. Re-composition triggered on a narrative field being *supplied*,
  and a form submits every field, so the description someone edited and approved
  was replaced by a freshly composed one before the write — the text reviewed was
  not the text sent to Zoho. Re-composition now triggers on a value that actually
  changed, and each form carries the composed text it displayed so an edit can be
  told apart from a resubmission.
- An edited acknowledgement draft was discarded entirely: the textarea was
  editable but the field was not carried into the plan, so the mailbox got the
  originally composed text.
- An edited reply recipient list was accepted and then silently ignored. The
  send path posts to Graph's `replyAll`, which mails the thread's own recipients,
  so removing someone in the form and pressing Send would have shown one list and
  mailed another — including the person who had just been removed. An edited list
  now goes through a draft whose recipients are actually set, and the wider grant
  that needs is an operator decision rather than something inferred from the fact
  that somebody edited the field.

### Changed

- The inbox monitor now reads the full body of **one** message on demand, when a
  ticket or a reply is being drafted from it, rather than composing a description
  out of the 240-character preview. The monitor itself still stores nothing but
  the bounded preview, and the body is never written to the archive.
- Ranked the daily brief before de-duplicating it, so the highest-scoring
  account of a corroborated event survives. De-duplicating first kept whichever
  outlet appeared earliest in the configured source list, which discarded
  better-evidenced reporting purely because of source ordering: the EU
  evaluation guidance kept a regional summary over the originating outlet's
  account, which led on both evidence (0.95 vs 0.70) and significance (0.90 vs
  0.70). A dropped duplicate now names the account that survived, the scores
  behind that choice, and any signal the dropped account still leads on.

### Fixed

- Stopped describing a coverage gap as a mailbox access problem in the inbox
  monitor's alert; the two are now counted and named separately.

- Requested the authenticated user's activity from `/users/{username}/events`
  instead of `/user/events`. GitHub does not serve the latter, so every run
  recorded an HTTP 404 for that call and silently dropped the whole
  user-activity scope while reporting the gap only as a coverage warning. The
  radar already resolves the login from `/user`, so it now builds the documented
  path; when the login cannot be resolved the report says the feed was not
  requested rather than appearing to have checked it.

- Stopped a commit with no committer block from printing a literal
  `committer: None` as though it were a contributor name; the field is now
  omitted from both Markdown and HTML.

### Not implemented

- Live external integrations, credentials, and deployment remain intentionally
  out of scope; the runtime is read-only and uses fixture/mocked fetching in
  tests.
- Live activity/calendar integrations and deployment remain intentionally out
  of scope; these routines accept local fixtures only.
