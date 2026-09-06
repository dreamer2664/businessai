"""Score browsing tasks: python3 engine/scripts/score_browse.py [tests/browse.txt] [--show]"""
import re, sys, time
sys.path.insert(0, ".")
from agent.tasks import Tasks
qf = next((a for a in sys.argv[1:] if not a.startswith("--")), "tests/browse.txt"); show = "--show" in sys.argv
T = Tasks(log=lambda k, **f: None)  # no planner: scores the raw browsing layer
blocks, cur = {}, "misc"
for line in open(qf, encoding="utf-8"):
    line = line.rstrip("\n")
    if line.startswith("## "): cur = line[3:]; continue
    if not line or line.startswith("#") or "\t" not in line: continue
    task, *req = line.split("\t"); blocks.setdefault(cur, []).append((task, [r.lower().split("|") for r in req if r]))
tot = ok = 0; t0 = time.time(); fails = []
for b, tasks in blocks.items():
    bok = 0
    for task, reqs in tasks:
        t1 = time.time(); out = T.run(task); low = out.lower()
        good = all(any(a in low for a in alts) for alts in reqs)
        bok += good; tot += 1; ok += good
        if show or not good: fails.append(f"  {'OK ' if good else 'MISS'} [{time.time()-t1:.0f}s] {task}\n      -> {out[:400]!r}")
    print(f"{b:40s} {bok:2d}/{len(tasks)}", flush=True)
print(f"TOTAL {ok}/{tot}  ({time.time()-t0:.0f}s)"); print("\n".join(fails))
