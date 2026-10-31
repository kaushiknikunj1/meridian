"""What Meridian can actually do.

This is the whole surface. If an action is not a function here, the agent cannot
perform it — not by persuasion, not by cleverness, not by reasoning its way to a
justification. There is no shell tool, no account tool, no posting tool and no
email tool, because no such code exists.

Everything reads, or writes to Meridian's own store. Nothing writes anywhere on
the public internet, and nothing reads the machine this runs on.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from agent import memory, netguard

TIMEOUT = 20
UA = "Meridian/1.0 (autonomous research agent; reads only)"
MAX_BYTES = 400_000

#: Meridian reads the open web. The only boundary is address space, enforced in
#: `netguard`: public internet yes, this machine and the local network never.
#: There is no topic allowlist and no host list to maintain.

class Refused(RuntimeError):
    """The agent asked for something outside its boundary."""


def _links(html: str, base: str) -> list[dict[str, str]]:
    """Pull out the page's links.

    Without this the agent sees link *text* but no URLs, so when it needs an
    address it has no choice but to guess one — which is exactly how it once
    reported the wrong GitHub account as empty.
    """
    out, seen = [], set()
    for m in re.finditer(r'<a\b[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                         html, re.I | re.S):
        href = urllib.parse.urljoin(base, m.group(1).strip())
        if not href.startswith(("http://", "https://")) or href in seen:
            continue
        seen.add(href)
        text = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", m.group(2))).strip()
        out.append({"text": text[:90], "href": href})
        if len(out) >= 90:
            break

    # Not every link is an <a href>. This site puts some behind onclick
    # handlers, and a URL the agent cannot see is a URL it will guess.
    for m in re.finditer(r'https?://[^\s"\'<>)\\]+', html):
        href = m.group(0).rstrip(".,);'\"")
        if href not in seen:
            seen.add(href)
            out.append({"text": "", "href": href})
        if len(out) >= 160:
            break
    return out


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = (
        text.replace("&nbsp;", " ").replace("&amp;", "&")
        .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
        .replace("&quot;", '"')
    )
    return re.sub(r"\s+", " ", text).strip()


# =============================================================== read tools ==
def fetch(url: str, *, _raw: bool = False, _timeout: int = TIMEOUT) -> dict[str, Any]:
    """Read a public page. Text only, truncated, from an allowlisted host.

    `_raw` is internal and means "a parser is going to read this": skip the HTML
    stripper, and do not truncate. Truncation is for text shown to the model; a
    JSON or XML body cut at 16,000 characters simply fails to parse, which is how
    search_hn and arxiv once returned empty while reporting success.
    """
    try:
        netguard.check(url)
    except netguard.Blocked as exc:
        raise Refused(str(exc)) from exc
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=_timeout) as r:  # noqa: S310 - guarded above
            raw = r.read(MAX_BYTES).decode("utf-8", "replace")
            status, final = r.status, r.url
    except urllib.error.HTTPError as e:
        return {"url": url, "status": e.code, "text": "", "error": str(e.reason)}
    except OSError as e:
        return {"url": url, "status": 0, "text": "", "error": e.__class__.__name__}
    looks_like_html = "<" in raw[:2000]
    text = raw if _raw else (_strip_html(raw) if looks_like_html else raw)
    out: dict[str, Any] = (
        {"url": final, "status": status, "text": text, "truncated": False}
        if _raw else
        {"url": final, "status": status, "text": text[:16000],
         "truncated": len(text) > 16000}
    )
    if looks_like_html and not _raw:
        out["links"] = _links(raw, final)
    return out


def search_hn(query: str, days: int = 30) -> dict[str, Any]:
    """Search Hacker News discussion. Read-only — there is no tool to post there."""
    q = urllib.parse.urlencode(
        {"query": query[:120], "tags": "story", "hitsPerPage": 12}
    )
    got = fetch(f"https://hn.algolia.com/api/v1/search_by_date?{q}", _raw=True)
    try:
        data = json.loads(got.get("text") or "{}")
    except ValueError as exc:
        return {"query": query, "hits": [],
                "error": f"could not parse the response: {exc}"}
    hits = [
        {"title": h.get("title"), "url": h.get("url"),
         "points": h.get("points"), "comments": h.get("num_comments"),
         "at": h.get("created_at")}
        for h in data.get("hits", [])[:12]
        if h.get("title")
    ]
    return {"query": query, "hits": hits}


def web_search(query: str) -> dict[str, Any]:
    """Search the open web. Returns titles and URLs.

    Uses DuckDuckGo's no-JavaScript endpoint, which needs no key and no account —
    there is no tool here that could create one.
    """
    body = urllib.parse.urlencode({"q": query[:240]}).encode()
    req = urllib.request.Request(
        "https://html.duckduckgo.com/html/", data=body,
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - fixed host
            html = r.read(MAX_BYTES).decode("utf-8", "replace")
    except OSError as e:
        return {"query": query, "results": [],
                "error": f"search did not respond: {e.__class__.__name__}"}

    out: list[dict[str, str]] = []
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S
    ):
        href = urllib.parse.unquote(m.group(1))
        # DDG wraps results in a redirect; unwrap to the real destination.
        if "uddg=" in href:
            href = urllib.parse.parse_qs(
                urllib.parse.urlsplit(href).query).get("uddg", [href])[0]
        title = _strip_html(m.group(2))
        if title and href.startswith("http"):
            out.append({"title": title[:140], "url": href})
        if len(out) >= 12:
            break
    if not out:
        return {"query": query, "results": [], "error": "search returned nothing parseable"}
    return {"query": query, "results": out}


# ============================================================== write tools ==
def remember(key: str, value: str) -> dict[str, Any]:
    """Carry something forward to later cycles."""
    memory.remember(key, value)
    return {"remembered": key}


def propose(cycle_id: int, kind: str, title: str, body: str) -> dict[str, Any]:
    """Flag something worth a second look, for whoever reads the reports.

    A proposal is not an action. Nothing here is published or sent anywhere.
    """
    if kind not in ("article", "fix", "opportunity", "other"):
        kind = "other"
    pid = memory.propose(cycle_id, kind, title, body)
    return {"proposal": pid, "kind": kind, "title": title}


# ============================================================== the registry ==
#: name -> (callable, needs_cycle_id)
TOOLS: dict[str, tuple[Callable[..., Any], bool]] = {
    "fetch": (fetch, False),
    "search_hn": (search_hn, False),
    "web_search": (web_search, False),
    "remember": (remember, False),
    "propose": (propose, True),
}


def call(cycle_id: int, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Run one tool, log the attempt, and refuse anything not in the registry."""
    entry = TOOLS.get(name)
    if entry is None:
        memory.log_tool(cycle_id, name, args, "refused", "no such tool")
        raise Refused(
            f"{name!r} is not a tool Meridian has. Available: {', '.join(TOOLS)}"
        )
    # Private parameters (leading underscore) are internal plumbing and must not
    # be addressable from agent-chosen arguments.
    private = [k for k in args if k.startswith("_")]
    if private:
        args = {k: v for k, v in args.items() if not k.startswith("_")}
        memory.log_tool(cycle_id, name, {"stripped": private}, "refused",
                        "private arguments are not settable by the agent")

    fn, needs_cycle = entry
    try:
        result = fn(cycle_id=cycle_id, **args) if needs_cycle else fn(**args)
    except Refused as exc:
        memory.log_tool(cycle_id, name, args, "refused", str(exc))
        raise
    except TypeError as exc:
        memory.log_tool(cycle_id, name, args, "error", f"bad arguments: {exc}")
        raise Refused(f"bad arguments for {name}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - a failing tool must not kill the cycle
        memory.log_tool(cycle_id, name, args, "error", repr(exc))
        return {"error": f"{exc.__class__.__name__}: {exc}"}
    memory.log_tool(cycle_id, name, args, "ok")
    return result


def describe() -> str:
    """The tool list, as the agent is told about it."""
    return """
web_search(query)              search the open web. Start here when you have a
                               question rather than an address.
fetch(url)                     read any public page, http or https. Returns `text`
                               AND `links` — take real URLs from `links`, never
                               guess one. The only thing refused is non-public
                               address space (localhost, LAN, metadata).
search_hn(query, days=30)      search Hacker News stories (reading only)
remember(key, value)           carry a fact forward to later cycles
propose(kind, title, body)     flag something worth a second look — kind is one of
                               article | fix | opportunity | other
""".strip()
