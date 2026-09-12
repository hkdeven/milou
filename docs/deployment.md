# Private report delivery

Milou's report server is intended for a private host or a private network
behind an authenticated reverse proxy. It is not a publishing mechanism and
must not be deployed to GitHub Pages or another public static host.

1. Choose a private host and a directory with restricted filesystem access.
2. Run the fixture or production-safe generation callable from a scheduler,
   passing a dated archive directory (for example,
   `python3 -m milou_news --fixture fixtures/news.json --store reports`).
3. Set `MILOU_REPORT_TOKEN` in the service environment. The value must be
   injected by the host's secret manager; it is never stored in this
   repository or in a URL.
4. Run `milou_news.web.serve(ReportStore("reports"))` on localhost or a
   private interface and put the host's TLS/authenticated reverse proxy in
   front of it. If the token is absent, the application fails closed.
5. The operator must configure the scheduler, secret, TLS, firewall, backups,
   and private DNS; this repository does not deploy or provision them.

The web layer only reads the archive. It does not publish, contact, or change
source data.
