# Milou on a Mac

```
./mac/install.sh
```

That builds `~/Applications/Milou.app`. Double-click it and the console opens in
your browser, already signed in. Add `--login-item` to have it start when you
log in, and `--uninstall` to remove both.

## What it actually is

A small Python process bound to `127.0.0.1`, plus a browser tab. There is no
Dock icon and no window of its own — the app starts the server, opens a tab, and
gets out of the way, because pretending to be a native window it does not have
would be worse than not having one.

Nothing leaves the machine except the calls to Microsoft and Zoho that the
routines make on your behalf.

## Where things live

| What | Where | Why there |
|---|---|---|
| Sign-in tokens | your **Keychain**, service `milou` | the system already protects it, and you can inspect and revoke from Keychain Access |
| The console's own password | the same place, account `console` | so a double-clicked app needs no terminal |
| Configuration | `~/.milou/console.json`, mode 600 | it names your portal and project, not secrets |
| Log | `~/.milou/console.log` | |
| Reports | `reports/` in the repository | |

## Signing in

```
python3 -m milou_news.cli login outlook --config ~/.milou/console.json
python3 -m milou_news.cli login zoho    --config ~/.milou/console.json
python3 -m milou_news.cli login status
```

This opens a browser once. Milou keeps the refresh token and renews the access
token by itself from then on — the hourly expiry that made it unusable as a
background application is handled.

Add `--writes` to ask for the write permissions at the same time, so the consent
screen appears once instead of twice. Without it you get read-only access and
every action stays a rehearsal, which is the better way to start.

To sign out of everything: `python3 -m milou_news.cli login forget`.

## The one-time link

`Milou.app` opens `http://127.0.0.1:8080/?signin=…`. That is a secret in a URL,
which is a real cost — it lands in browser history. Three things make it an
acceptable trade for a local application, and all three are tested:

- it is **single use**, spent the moment the browser follows it;
- it **expires in five minutes**;
- it is **only honoured from this machine**, never from another host.

If you would rather not have it at all, start the app without `--open` and sign
in with the password from Keychain Access instead.

## A note on port 8080

If something else on your Mac already uses 8080, set `MILOU_PORT` before
installing:

```
MILOU_PORT=8390 ./mac/install.sh
```

## What this does not do

- It is not sandboxed, notarised or signed. It is a script in a bundle, which
  macOS will run because you built it locally, and which Gatekeeper would stop
  if you sent it to somebody else.
- It does not run when your Mac is asleep. For the routines to run on a cadence
  while you are away, that needs a machine that stays awake.
