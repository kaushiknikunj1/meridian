"""One cycle of Meridian's life: look at where things stand, decide, act, write.

The shape matters. The model decides and writes; it never acts. Acting is
`tools.call`, which only knows a fixed set of functions. So the worst a bad
decision can produce is a wasted read and an honest journal entry saying so.
"""

from __future__ import annotations

import json
import textwrap
from typing import Any

from agent import brain, memory, telegram, tools


def _context() -> str:
    """What Meridian knows as it wakes up."""
    recent = memory.recent_cycles(8)
    notes = memory.notes()
    props = memory.open_proposals(8)

    parts = [f"Today is {memory.now()[:10]} (UTC)."]

    due = memory.due_in_seconds()
    if recent:
        parts.append(
            f"\nYou chose to wake now. You decide when you wake next — "
            f"anything from {brain.MIN_WAKE} minutes to {brain.MAX_WAKE}."
        )
        parts.append("\nYour last few cycles, newest first:")
        for c in recent:
            parts.append(
                f"  {c['started_at'][:16]}  [{c['outcome']}]  "
                f"{(c['summary'] or '').strip()[:150]}"
            )
    else:
        parts.append("\nThis is your first cycle. You have no history yet.")

    if notes:
        parts.append("\nWhat you have chosen to remember:")
        for k, v in sorted(notes.items())[:25]:
            parts.append(f"  {k}: {v[:220]}")

    if props:
        parts.append("\nThings you have already flagged (do not repeat these):")
        for p in props:
            parts.append(f"  [{p['kind']}] {p['title'][:120]}")

    return "\n".join(parts)


def _run_steps(cycle_id: int, steps: list[dict[str, Any]]) -> str:
    """Execute the chosen calls and render what came back for the write-up."""
    if not steps:
        return "(no tool calls — you judged there was nothing worth doing)"
    chunks = []
    for step in steps:
        name = step.get("tool", "")
        args = step.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        try:
            result = tools.call(cycle_id, name, args)
            body = json.dumps(result, indent=2, default=str)
        except tools.Refused as exc:
            body = f"REFUSED: {exc}"
        chunks.append(
            f"--- {name}({', '.join(f'{k}={v!r}' for k, v in args.items())[:160]})\n"
            f"{textwrap.shorten(body, 7000, placeholder=' …[truncated]')}"
        )
    return "\n\n".join(chunks)


def cycle() -> dict[str, Any]:
    """Run exactly one cycle. Always returns; never raises into the scheduler."""
    cycle_id = memory.start_cycle()
    ctx = _context()

    try:
        plan = brain.decide(ctx, tools.describe())
    except brain.BrainError as exc:
        memory.finish_cycle(
            cycle_id, intent="(could not think)", outcome="error",
            summary=f"Thinking failed: {exc}", detail="",
        )
        telegram.report(cycle=cycle_id, outcome="error", intent="",
                        summary=f"I could not think this cycle: {exc}", thoughts="")
        return {"cycle": cycle_id, "outcome": "error", "error": str(exc)}

    results = _run_steps(cycle_id, plan["steps"])

    try:
        verdict = brain.conclude(ctx, plan["intent"], results)
    except brain.BrainError as exc:
        memory.finish_cycle(
            cycle_id, intent=plan["intent"], outcome="error",
            summary=f"Could not write up the cycle: {exc}", detail="",
        )
        telegram.report(cycle=cycle_id, outcome="error", intent=plan["intent"],
                        summary=f"I did the work but could not write it up: {exc}",
                        thoughts="")
        return {"cycle": cycle_id, "outcome": "error", "error": str(exc)}

    prop = verdict.get("proposal")
    if isinstance(prop, dict) and prop.get("title"):
        tools.call(cycle_id, "propose", {
            "kind": str(prop.get("kind", "other")),
            "title": str(prop.get("title"))[:200],
            "body": str(prop.get("body", ""))[:8000],
        })

    note = verdict.get("remember")
    if isinstance(note, dict) and note.get("key"):
        tools.call(cycle_id, "remember", {
            "key": str(note["key"]), "value": str(note.get("value", "")),
        })

    wake_in = int(verdict.get("next_wake_minutes", 30))
    wake_at = memory.set_next_wake(wake_in)

    memory.finish_cycle(
        cycle_id,
        intent=plan["intent"],
        outcome=verdict["outcome"],
        summary=verdict["summary"],
        thoughts=verdict.get("thoughts", ""),
        public_title=verdict.get("public_title", ""),
        public_body=verdict.get("public_body", ""),
    )

    # Every cycle is reported, including the quiet ones. Reporting is best-effort:
    # an outage on the channel must never stop the agent working.
    sent = telegram.report(
        cycle=cycle_id,
        outcome=verdict["outcome"],
        intent=plan["intent"],
        summary=verdict["summary"],
        thoughts=verdict.get("thoughts", ""),
        proposal=(prop or {}).get("title") if isinstance(prop, dict) else None,
        next_wake_minutes=wake_in,
    )

    return {
        "cycle": cycle_id,
        "outcome": verdict["outcome"],
        "intent": plan["intent"],
        "summary": verdict["summary"],
        "thoughts": verdict.get("thoughts", ""),
        "steps": len(plan["steps"]),
        "proposal": bool(prop),
        "reported": sent,
        "next_wake_minutes": wake_in,
        "next_wake_at": wake_at,
    }


DIGEST_EVERY_HOURS = 24


def digest_due() -> bool:
    return memory.hours_since_digest() >= DIGEST_EVERY_HOURS


def send_digest(window_hours: float = DIGEST_EVERY_HOURS) -> dict[str, Any]:
    """Summarise a stretch of work into one message and send it.

    Costs one model call. Runs at most once a day, so the per-cycle reports can
    stay short without the day as a whole becoming unreadable.
    """
    cycles = memory.cycles_since(window_hours)
    if not cycles:
        memory.mark_digest_sent()
        return {"sent": False, "reason": "no cycles in the window"}

    try:
        text = brain.digest(
            int(window_hours), cycles,
            memory.notes(), memory.open_proposals(20),
        )
    except brain.BrainError as exc:
        return {"sent": False, "reason": f"could not write it: {exc}"}
    if not text:
        memory.mark_digest_sent()
        return {"sent": False, "reason": "nothing to say"}

    done = sum(1 for c in cycles if c["outcome"] == "done")
    header = (f"Daily summary \u00b7 {telegram.stamp()}\n"
              f"{len(cycles)} cycles, {done} with something to report\n")
    out = telegram.send(header + "\n" + text)
    if out.get("sent"):
        memory.mark_digest_sent()
    return {**out, "cycles": len(cycles), "text": text}
