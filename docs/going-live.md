# Going live

Everything is built. Nothing is connected. This is the list of what only you can
do, in the order that keeps each step verifiable on its own.

Read the whole thing before starting step 1 — there is one piece of engineering
still missing (step 3), and knowing about it changes how you'd plan the rest.

---

## Step 0 — see it running, 5 minutes, no credentials

```
MILOU_REPORT_TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
export MILOU_REPORT_TOKEN
python3 -m milou_news.cli serve --config console.example.json --fixtures
```

Open `http://127.0.0.1:8080`, paste the token, and click through. It prints the
token to your terminal; that is the sign-in password.

This proves the application works before any of your real systems are involved.
Both actions run, and both change nothing.

---

## Step 1 — the three answers I still need

These are configuration, not code. Copy `console.example.json` to
`console.json` and fill in:

| Setting | What it is | Where to find it |
|---|---|---|
| `ticket.portal` | your Zoho portal name | the portal name in your Zoho Projects URL |
| `ticket.project` | which project new tickets file into | the numeric id in the project's URL |
| `ticket.project_name` | its display name | shown on the ticket form |
| `ticket.statuses` | **every** custom status your portal has, in picker order | Zoho Projects → Setup → Task Status |
| `ticket.ready_status` | the one selected by default | must be one of the above, exactly |
| `ticket.document_url` | the share link to the sprint tracker `.docx` | Word → Share → Copy link |
| `zoho.me` | your Zoho account email | so the radar knows which items are yours |
| `approver` | your name | stamped on every approval |
| `ticket.signature` | your name | signs the reply and the acknowledgement |

`statuses` must match Zoho **exactly**, character for character. A status that
is not in the list is refused at the approval gate, on purpose: Zoho rejects an
unknown custom status with an error that names no alternatives, which is
miserable to debug at write time.

The tracker document must be a `.docx`. If it is still a `.doc`, open it in Word
and save it as `.docx` first — writing `.docx` bytes over a `.doc` would
destroy it, so the writer refuses before uploading.

---

## Step 2 — read access

### Outlook (Microsoft Graph)

You need an Azure app registration. In the Azure portal → Microsoft Entra ID →
App registrations → New registration:

- **Supported account types:** accounts in this organizational directory only.
- **Authentication:** add a platform → Mobile and desktop applications, and turn
  on **Allow public client flows**. This is a desktop app signing in as you; it
  has no client secret and no ability to act without you.
- **API permissions:** Microsoft Graph → **Delegated** → `Mail.Read`. Nothing
  else yet. Grant consent.

That is the whole read scope. `Mail.Read` cannot send, reply, flag, move,
archive or mark anything read.

### Zoho Projects

Zoho API Console → Self Client → generate a token with these scopes
(read only):

```
ZohoProjects.portals.READ
ZohoProjects.projects.READ
ZohoProjects.activities.READ
ZohoProjects.tasks.READ
```

Then:

```
export MILOU_OUTLOOK_TOKEN=...   # Graph access token
export MILOU_ZOHO_TOKEN=...      # Zoho access token
python3 -m milou_news.cli serve --config console.json
```

Both actions are still rehearsals — no write tokens exist yet — but every report
is now reading your real systems. **Spend a few days here.** This is the part
worth being slow about: the inbox monitor's whole value is what it refuses to
show you, and the only way to know whether it refuses the right things is to
watch it against real mail while nothing can act.

---

## Step 3 — signing in

Access tokens from Microsoft and Zoho expire after about an hour, so Milou does
not hold one. You sign in once in a browser and it keeps the **refresh** token,
exchanging it for a fresh access token before each request.

```
./mac/install.sh
python3 -m milou_news.cli login outlook --config ~/.milou/console.json
python3 -m milou_news.cli login zoho    --config ~/.milou/console.json
python3 -m milou_news.cli login status
```

The tokens go into your **Keychain** (service `milou`), so they are somewhere
the system already protects and you can inspect or revoke from Keychain Access.
On anything that is not a Mac they fall back to a file created 0600, which is
re-checked on every read and refused if it ever became readable by others.

Two things to know:

- The redirect comes back to `http://localhost:8765/callback` on this machine,
  so the authorisation code never passes through anyone else's server. Add that
  URI to the app registration under **Mobile and desktop applications**.
- Microsoft is a **public client with PKCE** — there is no client secret to
  store. Zoho's OAuth does require one; put it in `MILOU_ZOHO_CLIENT_SECRET` for
  the single `login zoho` command, after which it is kept with the tokens.

Add `--writes` to either command to request the write permissions at the same
time, so the consent screen appears once rather than twice. Leave it off to
start: read-only access keeps every action a rehearsal.

`mac/README.md` covers the application itself.

---

## Step 4 — turning on writes, one at a time

Each write has its own credential so you can enable them independently and stop
after any of them. Do them in this order — it is ordered by how reversible the
mistake is.

### 4a. The acknowledgement draft — safest, start here

Add `Mail.ReadWrite` (delegated) to the app registration.

```
export MILOU_OUTLOOK_WRITE_TOKEN=...
```

This lets Milou leave a draft in your Drafts folder. Nothing is sent. Create one
ticket, then look in Outlook: the draft should be there, addressed correctly,
with the ticket number filled in. If it looks wrong, delete it — that is the
whole blast radius.

Note that `Mail.ReadWrite` also permits modifying and deleting mail. Milou only
ever creates a draft, but the grant is wider than the use. If that bothers you,
set `ticket.acknowledge: false` and skip this one.

### 4b. The Zoho ticket

Add `ZohoProjects.tasks.CREATE` to the Zoho token's scopes.

```
export MILOU_ZOHO_WRITE_TOKEN=...
```

Create one ticket in a **test project first**, not your live one — point
`ticket.project` at a scratch project, make a ticket, check every field landed
where you expected, then switch the config to the real project.

This is where the REST paths are least certain: the Zoho adapter is written
against the documented shape but has never run against a live portal, and
Zoho's REST surface differs across portal API versions. If the first create
fails, send me the error and the endpoint is configuration
(`zoho.endpoints`) — it does not need a code change.

### 4c. The sprint tracker document

Add `Files.ReadWrite.All` (delegated) if the tracker lives on a SharePoint team
site, or `Files.ReadWrite` if it is in your own OneDrive.

```
export MILOU_DOCUMENT_WRITE_TOKEN=...
```

**Make a copy of the tracker and point `document_url` at the copy for the first
run.** This is the only thing Milou touches that you cannot undo from inside
Milou. It splices in one paragraph and copies every other byte unchanged, it
refuses when the sprint heading is missing, it does nothing on a repeat run, and
it keeps the previous bytes — but a Word document you have maintained by hand is
worth one careful rehearsal against a copy.

Check that the new line landed under the right sprint heading and inherited the
bullet formatting of the line above it. Then repoint at the real document.

### 4d. Sending the context reply

`Mail.Send` (delegated) covers it, and is already implied if you did 4a.

This is the only action that puts something in front of other people
irreversibly. Do it last, and read the first few before pressing Send.

Leave `allow_recipient_edits: false` unless you specifically need to change who
a reply goes to. With it off, an edited recipient list is refused rather than
sent.

---

## Step 5 — running it continuously

Once step 3 exists, the scheduler already handles cadence:

```
python3 -m milou_news.cli run --config scheduler.json --store reports
```

Put that on a cron entry or a launchd job. The console reads whatever the
scheduler stored, so the two fit together without further work.

**On a Mac**, `./mac/install.sh --login-item` does this with launchd instead,
and `mac/README.md` explains the parts.

**Where to run it:** your own machine is the right answer for now. The server
binds `127.0.0.1` and is not built to be exposed — there are no user accounts,
"approved by" is a name typed into a form rather than an identity the server can
verify, and the session token is a single shared secret. If you later want it
reachable from your phone, that is a real piece of work (TLS, a reverse proxy,
and a rethink of what "approved by" means), not a config flag. Do not port
forward it.

---

## What "live" looks like when you are done

- The inbox monitor tells you who is blocked on you, in about eight lines, and
  you stop opening Outlook to find out.
- A ticket that used to be ten minutes of copying is a form you correct and
  approve.
- The people who asked get a number they can follow, so they stop asking you.

---

## Honest state of each piece

| Piece | Status |
|---|---|
| Console, reports, forms, approval boundary | built, 293 tests, driven in a browser |
| Outlook read adapter | written to the documented Graph shape, **never run against a live mailbox** |
| Zoho read + write adapter | written to the documented shape, **never run against a live portal**, endpoints are configuration |
| Word tracker writer | tested against constructed `.docx` files, **never run against your tracker** |
| Mail send / draft | verified against Microsoft's current permission docs, **never sent a real message** |
| Token refresh | **not built** — see step 3 |
| Multi-user, remote access, TLS | not built, and out of scope as designed |

The first live run of each adapter is the first time that code meets the real
service. Expect one round of endpoint corrections per system, and do each one
against a scratch target.
