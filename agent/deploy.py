"""Publish Meridian's journal to the live site.

A push to `main` on the site repo is a production deploy, so this is scoped as
tightly as it can be: it stages **exactly one path**, `agent.html`, verifies that
nothing else ended up staged, and aborts if anything did. The site repo has other
uncommitted work in it, and this must never carry that along by accident.

Meridian does not hold these powers. This module is run by the loop process, not
offered as a tool, so the agent cannot decide to deploy — it writes text, and the
machinery around it decides whether that text ships.
"""

from __future__ import annotations

import subprocess
from agent import publish

REPO = publish.SITE
#: The only paths this is ever allowed to touch.
ONLY = (
    "meridian/index.html",
    "meridian/favicon.svg",
    "meridian/favicon.ico",
    "meridian/favicon-32.png",
    "meridian/apple-touch-icon.png",
    "agent.html",
)


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True, timeout=120, check=check,
    )


def deploy() -> dict[str, object]:
    """Render, commit and push the journal page. Returns what happened."""
    if not (REPO / ".git").exists():
        return {"deployed": False, "reason": f"no git repo at {REPO}"}

    wrote = publish.write()
    if not wrote.get("written"):
        return {"deployed": False, "reason": wrote.get("reason", "nothing to write")}

    try:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if branch != "main":
            return {"deployed": False, "reason": f"on branch {branch!r}, not main"}

        # Stage only the journal paths, then prove nothing else came with them.
        _git("add", "--", *ONLY)
        staged = sorted(
            ln for ln in _git("diff", "--cached", "--name-only").stdout.splitlines()
            if ln.strip()
        )
        if set(staged) - set(ONLY):
            _git("restore", "--staged", "--", *ONLY, check=False)
            return {
                "deployed": False,
                "reason": f"refusing to push: staged {staged}, allowed {list(ONLY)}",
            }
        if not staged:
            return {"deployed": False, "reason": "nothing to commit"}

        _git("commit", "-m", "meridian: journal update")
        _git("push", "origin", "main")
    except subprocess.CalledProcessError as exc:
        return {
            "deployed": False,
            "reason": (exc.stderr or exc.stdout or str(exc)).strip()[:300],
        }

    return {"deployed": True, "paths": staged, "bytes": wrote.get("bytes")}
