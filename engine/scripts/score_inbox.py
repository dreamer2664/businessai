"""Score customer-reply drafts: python3 engine/scripts/score_inbox.py [tests/inbox.txt] [--show]"""
import re, sys, time
sys.path.insert(0, ".")
from agent.planner import Planner
from agent.brain import Brain
from agent.inbox import Inbox
qf = next((a for a in sys.argv[1:] if not a.startswith("--")), "tests/inbox.txt"); show = "--show" in sys.argv
P = Planner(); I = Inbox(planner=P, brain=Brain())
blocks, cur = {}, "misc"
for line in open(qf, encoding="utf-8"):
    line = line.rstrip("\n")
    if line.startswith("## "): cur = line[3:]; continue
    if not line or line.startswith("#") or "\t" not in line: continue
    parts = (line.split("\t") + ["", "", ""])[:4]
    blocks.setdefault(cur, []).append(parts)
tot = ok = 0; t0 = time.time(); notes = []
try:
    for b, rows in blocks.items():
        bok = 0
        for msg, kind, must, mustnot in rows:
            t1 = time.time()
            d = I.draft({"id": "t", "from": "tester@example.com", "text": msg})
            low = d["text"].lower()
            kind_ok = kind == "*" or d["kind"] in kind.split("|") or (d.get("escalate") and kind == "*")
            if kind == "*": kind_ok = bool(d.get("escalate")) or d["kind"] in ("partnership_or_press",)
            must_ok = all(any(a.strip() in low for a in grp.split("|")) for grp in [must] if grp) if must else True
            not_ok = not (mustnot and re.search(mustnot, low))
            flags_ok = not d["checks"]
            if d["kind"] == "spam_or_scam": not_ok = (d["text"] == ""); must_ok = True
            good = kind_ok and must_ok and not_ok and flags_ok
            bok += good; tot += 1; ok += good
            why = [] if good else [w for w, v in (("kind=" + d["kind"], not kind_ok), ("missing must", not must_ok), ("has must-not", not not_ok), ("flags:" + ";".join(d["checks"]), not flags_ok)) if v]
            if show or not good: notes.append(f"  {'OK ' if good else 'MISS'} [{time.time()-t1:.0f}s] {msg[:70]}\n      {why} -> {d['text'][:260]!r}")
        print(f"{b:60s} {bok:2d}/{len(rows)}", flush=True)
    print(f"TOTAL {ok}/{tot}  ({time.time()-t0:.0f}s)"); print("\n".join(notes))
finally:
    P.stop()
