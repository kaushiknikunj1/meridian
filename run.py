#!/usr/bin/env python3
"""Meridian — an autonomous agent working for Nikunj Kaushik.

    python3 run.py once        run a single cycle now, whatever the schedule says
    python3 run.py tick        run only if Meridian decided it is due (what launchd calls)
    python3 run.py loop        keep running, one cycle every INTERVAL
    python3 run.py status      what it has done, and what it is waiting on
    python3 run.py journal     the published page, rendered to stdout
    python3 run.py publish     write agent.html into the site repo
    python3 run.py deploy      write it, commit it, push it (deploys the live page)
    python3 run.py proposals   what it has left for you
    python3 run.py digest [h]  summarise the last h hours into one message and send it
    python3 run.py stop        ask a running loop to finish its cycle and exit
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent import deploy as deployer  # noqa: E402
from agent import loop, memory, publish, telegram  # noqa: E402

#: Seconds between cycles. Nikunj asked for every few minutes, so 5 is the
#: default. Note each cycle is two headless Claude calls, so at this cadence it
#: is roughly 576 calls a day against the subscription on this machine.
INTERVAL = int(os.environ.get("MERIDIAN_INTERVAL", 5 * 60))

def _flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


#: Write agent.html into the site repo after each cycle.
PUBLISH = _flag("MERIDIAN_PUBLISH")
#: Also commit and push it, which deploys the live page. Implies PUBLISH.
DEPLOY = _flag("MERIDIAN_DEPLOY")
STOP = ROOT / "data" / "STOP"


def _log(msg: str) -> None:
    print(f"[{memory.now()}] {msg}", flush=True)


def once(*, publish_after: bool = PUBLISH, respect_schedule: bool = False) -> int:
    """Run one cycle.

    With `respect_schedule`, this exits immediately and for free when Meridian
    is not due — launchd can then tick often while the agent keeps its own,
    self-chosen cadence without burning a model call to say "not yet".
    """
    if respect_schedule and loop.digest_due():
        _log("daily summary due")
        d = loop.send_digest()
        _log(f"  summary : {'sent' if d.get('sent') else d.get('reason')}"
             f" ({d.get('cycles', 0)} cycles)")

    if respect_schedule:
        due = memory.due_in_seconds()
        if due > 0:
            _log(f"not due for {due / 60:.0f} more min — sleeping")
            return 0
    _log("cycle starting")
    result = loop.cycle()
    if result["outcome"] == "error":
        _log(f"cycle {result['cycle']} failed: {result.get('error')}")
        return 1
    _log(f"cycle {result['cycle']}: {result['outcome']} "
         f"({result['steps']} tool call(s))"
         f"{' + proposal' if result.get('proposal') else ''}")
    _log(f"  intent  : {result.get('intent', '')}")
    _log(f"  summary : {result['summary']}")
    if result.get("thoughts"):
        _log(f"  thoughts: {result['thoughts']}")
    sent = result.get("reported") or {}
    _log(f"  telegram: {'sent' if sent.get('sent') else sent.get('reason')}")
    _log(f"  next    : it chose {result.get('next_wake_minutes')} min "
         f"({result.get('next_wake_at', '')[:16]}Z)")
    if DEPLOY:
        shipped = deployer.deploy()
        _log(f"  site    : {'deployed' if shipped.get('deployed') else shipped.get('reason')}")
    elif publish_after:
        wrote = publish.write()
        _log(f"  page    : {'written, not pushed' if wrote.get('written') else wrote.get('reason')}")
    else:
        _log("  page    : not published (MERIDIAN_PUBLISH is off)")
    return 0


def run_loop() -> int:
    STOP.parent.mkdir(parents=True, exist_ok=True)
    STOP.unlink(missing_ok=True)
    ok, why = telegram.available()
    _log(f"Meridian is running. One cycle every {INTERVAL}s. Telegram: {why}.")
    _log(f"Stop with: python3 run.py stop   (or touch {STOP})")
    if ok:
        telegram.send(
            "Meridian is now running.\n\n"
            f"A cycle every {INTERVAL // 60} minutes. You will hear from me every "
            "cycle, including the quiet ones. This channel is one-way — I do not "
            "read anything sent here. Stop me with: python3 run.py stop"
        )
    while True:
        try:
            once()
        except KeyboardInterrupt:
            _log("interrupted — stopping")
            return 0
        except Exception as exc:  # noqa: BLE001 - the loop must outlive one bad cycle
            _log(f"cycle raised {exc.__class__.__name__}: {exc}")
        if STOP.exists():
            STOP.unlink(missing_ok=True)
            _log("stop requested — exiting")
            return 0
        slept = 0
        while slept < INTERVAL:
            time.sleep(min(20, INTERVAL - slept))
            slept += 20
            if STOP.exists():
                STOP.unlink(missing_ok=True)
                _log("stop requested — exiting")
                return 0


def status() -> int:
    cycles = memory.recent_cycles(10)
    props = memory.open_proposals(10)
    notes = memory.notes()
    print(f"\n  Meridian — {len(memory.recent_cycles(10000))} cycles run, "
          f"{len(props)} open proposal(s), {len(notes)} note(s)\n")
    if not cycles:
        print("  Nothing yet. Run:  python3 run.py once\n")
        return 0
    for c in cycles:
        mark = {"done": "*", "nothing": "·", "error": "!"}.get(c["outcome"], "?")
        print(f"  {mark} {c['started_at'][:16]}  {(c['summary'] or '')[:88]}")
    if props:
        print("\n  Waiting on you:")
        for p in props:
            print(f"    [{p['kind']}] {p['title'][:88]}")
    print()
    return 0


def proposals() -> int:
    props = memory.open_proposals(50)
    if not props:
        print("\n  Nothing waiting on you.\n")
        return 0
    for p in props:
        print(f"\n  #{p['id']}  [{p['kind']}]  {p['title']}")
        print(f"      {p['created_at'][:16]}")
        for line in (p["body"] or "").splitlines():
            print(f"      {line}")
    print()
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "once":
        return once()
    if cmd == "tick":
        # what launchd calls: cheap no-op unless Meridian decided it is due
        return once(respect_schedule=True)
    if cmd == "loop":
        return run_loop()
    if cmd == "status":
        return status()
    if cmd == "proposals":
        return proposals()
    if cmd == "journal":
        print(publish.render())
        return 0
    if cmd == "publish":
        print(publish.write())
        return 0
    if cmd == "deploy":
        print(deployer.deploy())
        return 0
    if cmd == "digest":
        hours = float(sys.argv[2]) if len(sys.argv) > 2 else loop.DIGEST_EVERY_HOURS
        out = loop.send_digest(hours)
        print(f"  {'sent' if out.get('sent') else out.get('reason')}"
              f"  ({out.get('cycles', 0)} cycles over {hours:g}h)")
        if out.get("text"):
            print()
            for line in out["text"].splitlines():
                print("  " + line)
        return 0
    if cmd == "telegram":
        ok, why = telegram.available()
        print(f"  telegram: {why}")
        if ok:
            print(" ", telegram.send(
                "Test from Meridian. If you are reading this, reporting works.\n"
                "This channel is one-way — nothing you send here reaches me."))
        return 0 if ok else 1
    if cmd == "stop":
        STOP.parent.mkdir(parents=True, exist_ok=True)
        STOP.touch()
        print("  stop requested — the loop will exit after its current cycle")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
