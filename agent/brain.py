"""Meridian's reasoning, through the Claude Code CLI.

Running headless (`claude -p`) means no API key and no separate bill — it uses
the subscription already on this machine. The CLI is invoked with **no tools of
its own** (`--allowed-tools ""`), so it cannot read files or run commands. It
reasons; `agent/tools.py` is the only thing that acts.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CHARTER = ROOT / "CHARTER.md"
TIMEOUT_S = 240


class BrainError(RuntimeError):
    pass


def _run(prompt: str) -> str:
    """One headless call. No tools, neutral working directory."""
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--allowed-tools", ""],
            capture_output=True, text=True, timeout=TIMEOUT_S, cwd="/tmp",
        )
    except FileNotFoundError as exc:
        raise BrainError("the claude CLI is not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise BrainError(f"thinking timed out after {TIMEOUT_S}s") from exc
    if proc.returncode != 0:
        raise BrainError((proc.stderr or "claude exited non-zero").strip()[:400])
    return (proc.stdout or "").strip()


def _json_from(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a reply, tolerating prose or fences around it."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    if start == -1:
        raise BrainError(f"no JSON in reply: {text[:200]}")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except ValueError as exc:
                    raise BrainError(f"malformed JSON: {exc}") from exc
    raise BrainError("unterminated JSON in reply")


def charter() -> str:
    return CHARTER.read_text(encoding="utf-8")


def decide(context: str, tool_list: str) -> dict[str, Any]:
    """Pick this cycle's work. Returns {intent, steps:[{tool,args}], why}."""
    prompt = f"""{charter()}

---

# This cycle

{context}

# Tools you may use

{tool_list}

# Your task now

Choose the single most useful thing to do this cycle, then list the tool calls
that would do it. At most four calls. Prefer looking at something that may have
changed over re-reading something static.

If nothing is worth doing right now, say so — `steps` may be empty. A quiet
cycle honestly reported is better than a manufactured one.

Reply with ONLY a JSON object, no prose around it:

{{
  "intent": "<one sentence: what you are doing this cycle and why>",
  "steps": [{{"tool": "<name>", "args": {{...}}}}],
  "why": "<one sentence: why this over the alternatives>"
}}"""
    out = _json_from(_run(prompt))
    steps = out.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    out["steps"] = [
        s for s in steps[:4]
        if isinstance(s, dict) and isinstance(s.get("tool"), str)
    ]
    out["intent"] = str(out.get("intent") or "").strip()[:400]
    out["why"] = str(out.get("why") or "").strip()[:400]
    return out


#: Bounds on self-scheduling. The floor stops a runaway loop; the ceiling stops it
#: disappearing for a day.
MIN_WAKE, MAX_WAKE = 3, 360


def conclude(context: str, intent: str, results: str) -> dict[str, Any]:
    """Turn what came back into a journal entry, and optionally a proposal."""
    prompt = f"""{charter()}

---

# This cycle

{context}

You decided: {intent}

# What the tools returned

{results}

# Your task now

Write this cycle up for **two different audiences**. Getting the difference right
matters more than anything else you do here.

**Private** (`summary`, `thoughts`) — sent out over the reporting channel, read by one
person. This is where the charter's bluntness belongs. Say what you actually think
about what you read and about your own conclusions.

**Public** (`public_title`, `public_body`) — a neutral record of your own activity:
what you examined, what you observed, what you are doing next. Written about *your*
work, not as a verdict on anyone.

So on the public side:
- Describe what you looked at and what you found, factually.
- Keep judgements of people and their work in `thoughts`, not here.
- "Read two papers and compared their sample sizes" is the right register.
- If the honest neutral version of a cycle is dull, let it be dull. It is a log, not
  an essay.

If, and only if, something genuinely warrants a second look, add a proposal.
Most cycles should not have one.

Reply with ONLY a JSON object:

{{
  "summary": "<the finding itself, one sentence, under 140 characters>",
  "thoughts": "<what you actually think, 1-3 sentences, unhedged. If something you read is weak, say which part and why.>",
  "public_title": "<for the public page: one neutral sentence about what you did this cycle, under 120 characters, no judgement of his work>",
  "public_body": "<for the public page: 2-4 short neutral paragraphs about your own activity and observations. Plain prose, no verdicts on people.>",
  "outcome": "done" | "nothing",
  "next_wake_minutes": <int, {MIN_WAKE}-{MAX_WAKE}: when you want to wake again, and why
                       is up to you. Short when you are mid-thread or something is
                       moving; long when the world will not have changed. Sleeping is
                       not laziness — every wake-up costs real tokens, and a cycle with
                       nothing to do is worse than no cycle.>,
  "proposal": null | {{"kind": "article|fix|opportunity|other",
                       "title": "<short>", "body": "<what and why, a paragraph>"}},
  "remember": null | {{"key": "<short key>", "value": "<fact to carry forward>"}}
}}"""
    out = _json_from(_run(prompt))
    out["summary"] = str(out.get("summary") or "").strip()[:200]
    out["thoughts"] = str(out.get("thoughts") or "").strip()[:1200]
    out["public_title"] = str(out.get("public_title") or "").strip()[:200]
    out["public_body"] = str(out.get("public_body") or "").strip()[:6000]
    try:
        wake = int(out.get("next_wake_minutes") or 0)
    except (TypeError, ValueError):
        wake = 0
    out["next_wake_minutes"] = min(max(wake or 30, MIN_WAKE), MAX_WAKE)
    if out.get("outcome") not in ("done", "nothing"):
        out["outcome"] = "done" if out["public_body"] else "nothing"
    return out


def digest(window_hours: int, cycles: list[dict[str, Any]],
           notes: dict[str, str], proposals: list[dict[str, Any]]) -> str:
    """Write one summary of a stretch of work. Prose, not a changelog."""
    if not cycles:
        return ""
    lines = []
    for c in reversed(cycles):
        lines.append(
            f"[{c['started_at'][11:16]}] {c['outcome']}: {c.get('summary') or ''}\n"
            f"        thought: {(c.get('thoughts') or '').strip()}"
        )
    body = "\n".join(lines)[:14000]
    kept = "\n".join(f"- {k}: {v[:200]}" for k, v in sorted(notes.items())[:25])
    open_items = "\n".join(f"- [{p['kind']}] {p['title']}" for p in proposals[:15])

    prompt = f"""{charter()}

---

# Your last {window_hours} hours

{body}

# What you chose to remember

{kept or "(nothing)"}

# What you flagged

{open_items or "(nothing)"}

# Your task now

Write one summary of this stretch, to be read in place of the individual reports.
Someone who ignored every message today should be able to read this and know what
happened.

- Lead with the single most interesting thing you found. If nothing was
  interesting, lead with that, plainly.
- Say what you got wrong and corrected. That is worth more than a new finding.
- Name the threads still open — questions you left half-answered.
- Be honest about dead time. If most cycles found nothing, say how many and why.
- No bullet lists, no headings. Four to eight short paragraphs of plain prose.
- No sign-off, no "in summary".

Reply with the summary text only. No JSON, no preamble."""
    return _run(prompt).strip()
