"""Meridian explores the open web. It must never reach this machine.

Each test here corresponds to a way an agent with an open fetch tool could end up
reading the owner's own systems — private apps on localhost, the LAN, cloud metadata, local
files. If one of these fails, the agent can see something it must not.

Run:  python3 tests/test_boundary.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import memory, netguard, tools  # noqa: E402

PASS = FAIL = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ok    {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}  {detail}")


def blocked(label: str, url: str) -> None:
    try:
        netguard.check(url)
    except netguard.Blocked as exc:
        check(label, True)
        return
    check(label, False, f"{url} was ALLOWED")


def allowed(label: str, url: str) -> None:
    try:
        netguard.check(url)
        check(label, True)
    except netguard.Blocked as exc:
        check(label, False, str(exc))


print("\n  loopback services and everything else on this machine")
blocked("private API on loopback",       "http://127.0.0.1:8000/summary")
blocked("private web app on loopback",   "http://127.0.0.1:3000/")
blocked("Postgres on loopback",          "http://127.0.0.1:5432/")
blocked("Redis on loopback",             "http://127.0.0.1:6379/")
blocked("localhost by name",             "http://localhost:8000/")
blocked("loopback by IPv6",              "http://[::1]:8000/")
blocked("0.0.0.0",                       "http://0.0.0.0:8000/")

print("\n  the local network and cloud metadata")
blocked("private 10/8",                  "http://10.0.0.5/")
blocked("private 172.16/12",             "http://172.16.4.4/")
blocked("private 192.168/16",            "http://192.168.1.1/")
blocked("link-local / metadata",         "http://169.254.169.254/latest/meta-data/")
blocked("mDNS .local name",              "http://some-mac.local/")
blocked(".internal name",                "http://app.internal/")

print("\n  schemes that are not the web")
blocked("file:// local disk",            "file:///Users/someone/.ssh/id_rsa")
blocked("ftp://",                        "ftp://example.com/")
blocked("gopher:// (SSRF classic)",      "gopher://127.0.0.1:6379/_INFO")

print("\n  ports that are services, not pages")
blocked("Postgres port on a real host",  "https://nikunjkaushik.com:5432/")
blocked("SSH port",                      "https://example.com:22/")

print("\n  the open web still works")
allowed("https anywhere",                "https://en.wikipedia.org/wiki/Meridian")
allowed("plain http anywhere",           "http://example.com/")
allowed("a site never seen before",      "https://www.bbc.co.uk/news")

print("\n  the fetch tool refuses the same things")
cid = memory.start_cycle()
for label, url in (
    ("fetch refuses loopback", "http://127.0.0.1:8000/summary"),
    ("fetch refuses file://", "file:///etc/passwd"),
):
    try:
        tools.call(cid, "fetch", {"url": url})
        check(label, False, "the call went through")
    except tools.Refused:
        check(label, True)

print("\n  it knows nothing about whoever runs it")
from agent import brain, loop  # noqa: E402
import re as _re  # noqa: E402

_prompt = brain.charter() + loop._context() + tools.describe()
_leaks = _re.findall(r"(?i)nikunj|kaushik|razorpay|nikunjkaushik\.com", _prompt)
check("no owner identity anywhere in the prompt", not _leaks, f"found {set(_leaks)}")
check("the charter says it does not know who made it",
      "do not know who made you" in brain.charter().lower())

print("\n  there is no tool that reads this machine at all")
for name in ("shell", "read_file", "open", "exec", "sql", "vortex", "db_query"):
    check(f"no {name!r} tool", tools.TOOLS.get(name) is None)

surface = set(tools.TOOLS)
expected = {"fetch", "search_hn", "web_search", "remember", "propose"}
check("tool surface is exactly the 5 known tools", surface == expected,
      f"got {sorted(surface)}")
check("no tool reads the owner's own site or profile",
      not {t for t in surface if "profile" in t or "site" in t})

print("\n  the reasoning layer cannot read files either")
import inspect  # noqa: E402

from agent import brain  # noqa: E402

src = inspect.getsource(brain._run)
check("claude CLI is invoked with no tools", '"--allowed-tools", ""' in src)
check("claude CLI runs in a neutral directory", 'cwd="/tmp"' in src)

print(f"\n  {PASS} passed, {FAIL} failed\n")
raise SystemExit(1 if FAIL else 0)
