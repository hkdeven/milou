"""Turning failures into sentences a person can act on.

Every adapter in this project can fail in the same handful of ways, and left to
themselves they each reported it in the vocabulary of the thing that failed:
``Graph /me returned HTTP 401 Unauthorized``. That is accurate and it is not
useful. It says nothing about what the reader should do, and 401 in particular
almost always means one specific, fixable, *expected* thing — the access token
aged out, because Microsoft and Zoho access tokens last about an hour.

So the knowledge of what a failure means lives here, once, and the adapters
describe what they were doing rather than how the wire complained.

Three rules hold for every message:

* **Name the cause, not the code.** A status number can stay in the sentence as
  corroboration; it is never the whole sentence.
* **Say what to do next**, when there is something to do. A message that ends
  at the diagnosis makes the reader go and look it up.
* **Never include a credential**, or anything that could carry one. These
  functions take a variable *name*, never a value, and no response body is ever
  quoted back — a rejected request can echo the token that was rejected.
"""

from typing import Optional

#: Where the answer lives when a message cannot be self-contained.
RUNBOOK = "docs/going-live.md"

#: Human labels for the field names the action plans carry, so a person is
#: never asked for `reported_by`.
LABELS = {
    "title": "Title",
    "status": "Status",
    "owner": "Owner",
    "tag": "Sprint tag",
    "release_date": "Expected release date",
    "requested_by": "Requested by",
    "reported_by": "Reported by",
    "reported_on": "Reported on",
    "record": "Project / record",
    "description": "Description",
    "context": "Context",
    "to": "To",
    "cc": "Cc",
    "subject": "Subject",
    "body": "Message",
    "heading": "Sprint heading",
}


def label(name: str) -> str:
    """The name this field is given on screen."""
    return LABELS.get(name, str(name).replace("_", " ").strip().capitalize())


def labels(names) -> str:
    """``Reported by and Reported on`` — a list a person can read aloud."""
    readable = [label(name) for name in names]
    if not readable:
        return ""
    if len(readable) == 1:
        return readable[0]
    return "%s and %s" % (", ".join(readable[:-1]), readable[-1])


def missing_token(service: str, env_var: str, doing: str) -> str:
    """No credential at all. The commonest first-run failure."""
    return ("%s needs a %s credential and none is configured. Set %s in the "
            "environment before starting Milou — see %s."
            % (doing[:1].upper() + doing[1:], service, env_var, RUNBOOK))


def http_failure(service: str, doing: str, code: int, reason: str = "",
                 env_var: str = "", scope: str = "") -> str:
    """What an HTTP status from an upstream service actually means here.

    ``doing`` is a phrase like "reading your mailbox", so the sentence starts
    with the thing the reader recognises rather than with a path.
    """
    code = int(code or 0)
    tail = " (HTTP %d%s)" % (code, " " + reason if reason else "")

    if code == 401:
        fix = ("Get a fresh token and set %s again" % env_var) if env_var \
            else "Sign in again to get a fresh token"
        return ("%s rejected the request because the access token is not valid. "
                "%s access tokens expire after about an hour, so this is most "
                "likely an expired one rather than a wrong one. %s — see %s.%s"
                % (service, service, fix, RUNBOOK, tail))
    if code == 403:
        want = (" It needs %s." % scope) if scope else ""
        return ("%s accepted the token but refused this request, which means the "
                "token is valid and does not carry the permission for %s.%s "
                "Add the scope to the app registration, consent to it, and get a "
                "new token — see %s.%s" % (service, doing, want, RUNBOOK, tail))
    if code == 404:
        return ("%s could not find what was asked for while %s. Usually that is a "
                "portal, project or item id that does not exist or was renamed, "
                "rather than a permission problem.%s" % (service, doing, tail))
    if code == 429:
        return ("%s is rate-limiting Milou and declined this request while %s. "
                "Nothing is wrong; wait a few minutes and run it again.%s"
                % (service, doing, tail))
    if 500 <= code < 600:
        return ("%s had an internal failure while %s. This is their side, not "
                "your configuration — retrying later usually works.%s"
                % (service, doing, tail))
    if code == 400:
        return ("%s rejected the request as malformed while %s. That normally "
                "means a configured endpoint or field name does not match this "
                "portal's API version; the endpoints are configuration, so they "
                "can be corrected without a code change.%s" % (service, doing, tail))
    return "%s refused the request while %s.%s" % (service, doing, tail)


def unreachable(service: str, doing: str, reason: str = "") -> str:
    return ("Could not reach %s while %s%s. Check the machine's network "
            "connection; nothing was changed."
            % (service, doing, ": %s" % reason if reason else ""))


def unreadable(service: str, doing: str) -> str:
    return ("%s replied while %s, but the response was not something Milou could "
            "read. That usually means a proxy or sign-in page answered instead of "
            "the API." % (service, doing))


def timed_out(service: str, doing: str, seconds) -> str:
    return ("%s did not answer within %s seconds while %s. Nothing was changed; "
            "try again." % (service, seconds, doing))


def not_configured(setting: str, why: str, example: str = "") -> str:
    """A missing or wrong value in the console configuration file."""
    return ("`%s` is not set in your console configuration, and %s.%s See %s."
            % (setting, why, " For example: %s." % example if example else "", RUNBOOK))


def out_of_range(setting: str, low, high, why: str = "") -> str:
    return ("`%s` must be between %s and %s.%s"
            % (setting, low, high, " " + why if why else ""))


def internal(detail: str) -> str:
    """A caller mistake, not an operator mistake. Say so, so nobody goes hunting.

    These are reachable only by wiring Milou up wrongly in code. Labelling them
    keeps someone from searching their Azure tenant for a problem that is a
    missing argument.
    """
    return ("Milou was wired up incorrectly: %s. This is a bug rather than "
            "something wrong with your configuration or your credentials." % detail)
