# Private report delivery

Milou's report server is intended for a private host or a private network
behind an authenticated reverse proxy. It is not a publishing mechanism and
must not be deployed to GitHub Pages or another public static host.

1. Choose a private host and a directory with restricted filesystem access.
2. Run the fixture or production-safe generation callable from a scheduler,
   passing a dated archive directory (for example,
   `python3 -m milou_news --fixture fixtures/news.json --store reports`).
3. Store the token outside the repository, for example in
   `$HOME/.config/milou/report-token`, with owner-only permissions. To load it
   without displaying it and restart the local server:

   ```sh
   TOKEN_FILE="$HOME/.config/milou/report-token"
   read -r MILOU_REPORT_TOKEN < "$TOKEN_FILE"
   export MILOU_REPORT_TOKEN
   python3 -c 'from milou_news.archive import ReportStore; from milou_news.web import serve; serve(ReportStore("reports"), host="127.0.0.1", port=8768)'
   ```

   If the file is missing, create it with a local secret generator and
   `umask 077`; never echo, paste, log, commit, or place the token in a URL.
4. Run `milou_news.web.serve(ReportStore("reports"))` on localhost or a
   private interface and put the host's TLS/authenticated reverse proxy in
   front of it. Open the root URL in a browser for the minimal login form;
   successful login creates a short-lived Secure, HttpOnly, SameSite=Strict
   session cookie. API and CLI clients retain `Authorization: Bearer ...`.
   The archive's Sign out button (or `POST /logout`) clears the session. If
   the token is absent, the application fails closed.
5. The operator must configure the scheduler, secret, TLS, firewall, backups,
   and private DNS; this repository does not deploy or provision them.

The web layer only reads the archive. It does not publish, contact, or change
source data. Tokens are accepted only in the login body or Authorization
header; they are never put in URLs, HTML, or logs. Keep TLS in front of any
non-localhost deployment because the session cookie is marked Secure.

For the current local demo, reports are stored in
`/tmp/milou-live-reports`. On macOS, open that directory with
`open /tmp/milou-live-reports`; substitute the configured archive directory
when using another local path. This shortcut does not read or expose tokens.
