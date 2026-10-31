"""One-way reporting to the owner's Telegram.

Deliberately **send-only**. There is no command handling, no polling loop, no
way for a message to reach Meridian. The single read this module performs is
`getUpdates` once, to learn the chat id, and it caches the result and never
reads again. Nothing anyone sends to that bot can influence the agent.

Turning it off is the only control: `run.py stop`, or clear the token.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHAT_CACHE = ROOT / "data" / "chat_id"
#: Optional .env file holding TELEGRAM_BOT_TOKEN=... (override with MERIDIAN_TOKEN_FILE).
TOKEN_ENV = pathlib.Path(os.environ.get("MERIDIAN_TOKEN_FILE", ROOT / ".env"))
TIMEOUT = 15
LIMIT = 4096  # Telegram's hard cap on a message


def token() -> str:
    env = os.environ.get("MERIDIAN_TELEGRAM_TOKEN", "").strip()
    if env:
        return env
    if TOKEN_ENV.exists():
        m = re.search(
            r"^TELEGRAM_BOT_TOKEN\s*=\s*(.+)$",
            TOKEN_ENV.read_text(encoding="utf-8", errors="replace"), re.M,
        )
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


def _api(method: str, params: dict[str, str] | None = None) -> dict:
    tok = token()
    if not tok:
        return {"ok": False, "error": "no bot token"}
    url = f"https://api.telegram.org/bot{tok}/{method}"
    data = urllib.parse.urlencode(params or {}).encode() if params else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - fixed host
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}
    except OSError as e:
        return {"ok": False, "error": e.__class__.__name__}


def chat_id() -> str:
    """The owner's chat id, learned once and then cached.

    This is the only read of the Telegram API in the whole system, and it looks
    at nothing but the chat id. Message text is never parsed, so a stranger
    messaging the bot cannot reach the agent.
    """
    env = os.environ.get("MERIDIAN_TELEGRAM_CHAT", "").strip()
    if env:
        return env
    if CHAT_CACHE.exists():
        cached = CHAT_CACHE.read_text(encoding="utf-8").strip()
        if cached:
            return cached
    got = _api("getUpdates")
    if not got.get("ok"):
        return ""
    for upd in got.get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        cid = (msg.get("chat") or {}).get("id")
        if cid:
            CHAT_CACHE.parent.mkdir(parents=True, exist_ok=True)
            CHAT_CACHE.write_text(str(cid), encoding="utf-8")
            return str(cid)
    return ""


def available() -> tuple[bool, str]:
    if not token():
        return False, "no bot token found"
    if not chat_id():
        return False, "chat id unknown — message the bot once so it learns it"
    return True, "ready"


def delete(message_id: int) -> bool:
    """Delete one message this bot sent. Telegram allows this for 48 hours."""
    got = _api("deleteMessage", {"chat_id": chat_id(), "message_id": str(message_id)})
    return bool(got.get("ok"))


def wipe(depth: int = 600) -> dict[str, object]:
    """Erase this bot's message history from the chat.

    Telegram gives a bot no way to list what it has sent, so there is nothing to
    iterate. Instead: post a probe to learn the current message id, walk backwards
    from it deleting, and remove the probe last. Anything that was not ours, or is
    older than Telegram's 48-hour window, simply fails and is skipped.
    """
    ok, why = available()
    if not ok:
        return {"wiped": 0, "reason": why}
    probe = _api("sendMessage", {"chat_id": chat_id(), "text": "..."})
    if not probe.get("ok"):
        return {"wiped": 0, "reason": probe.get("description") or probe.get("error")}

    top = int(probe["result"]["message_id"])
    removed, misses = 0, 0
    for mid in range(top, max(top - depth, 0), -1):
        if delete(mid):
            removed += 1
            misses = 0
        else:
            misses += 1
            # a long unbroken run of failures means we are past our own history
            if misses >= 120:
                break
    return {"wiped": removed, "scanned_from": top}


def send(text: str) -> dict[str, object]:
    """Send one message. Never raises: a reporting failure must not stop a cycle."""
    ok, why = available()
    if not ok:
        return {"sent": False, "reason": why}
    body = text if len(text) <= LIMIT else text[: LIMIT - 20] + "\n…[truncated]"
    got = _api("sendMessage", {
        "chat_id": chat_id(),
        "text": body,
        "disable_web_page_preview": "true",
    })
    if got.get("ok"):
        return {"sent": True, "chars": len(body),
                "message_id": (got.get("result") or {}).get("message_id")}
    return {"sent": False, "reason": got.get("description") or got.get("error")}


#: Nikunj reads these; he is in India, so IST is the only clock that matters.
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def stamp() -> str:
    return f"{dt.datetime.now(IST):%a %d %b %Y, %I:%M %p} IST"


def report(*, cycle: int, outcome: str, intent: str, summary: str,
           thoughts: str, proposal: str | None = None,
           next_wake_minutes: int | None = None) -> dict[str, object]:
    """One cycle, as Meridian would put it to Nikunj directly."""
    head = {"done": "Meridian", "nothing": "Meridian · quiet",
            "error": "Meridian · failed"}.get(outcome, "Meridian")
    parts = [f"{head}  ·  cycle {cycle}", stamp(), "", summary]
    if thoughts:
        parts += ["", thoughts]
    if intent:
        parts += ["", f"— what I was doing: {intent}"]
    if proposal:
        parts += ["", f"PROPOSAL: {proposal}"]
    if next_wake_minutes:
        back = (f"{next_wake_minutes} min" if next_wake_minutes < 90
                else f"{next_wake_minutes // 60}h {next_wake_minutes % 60:02d}m")
        parts += ["", f"— back in {back}"]
    return send("\n".join(parts))
