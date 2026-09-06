"""Warm-up ladder scorer (needs browser + thinking model):  python3 engine/scripts/score_warmup.py [tests/warmup.txt] [--show]"""
import sys, time
sys.path.insert(0, ".")
from agent.planner import Planner
from agent.tasks import Tasks
qf = next((a for a in sys.argv[1:] if not a.startswith("--")), "tests/warmup.txt"); show = "--show" in sys.argv
P = Planner(); T = Tasks(planner=P)
if not P.installed():
    sys.exit("thinking model not installed: sh scripts/get_model.sh")
blocks, cur = {}, "misc"
for line in open(qf, encoding="utf-8"):
    line = line.rstrip("\n")
    if line.startswith("## "): cur = line[3:]; continue
    if not line or line.startswith("#") or "\t" not in line: continue
    task, *req = line.split("\t"); blocks.setdefault(cur, []).append((task, [r.lower().split("|") for r in req if r]))
tot = ok = 0; t0 = time.time(); notes = []
try:
    for b, tasks in blocks.items():
        bok = 0
        for task, reqs in tasks:
            t1 = time.time()
            out = (T.ask(task[4:]) or "") if task.startswith("ask ") else T.run(task)
            low = out.lower(); good = all(any(a in low for a in alts) for alts in reqs)
            bok += good; tot += 1; ok += good
            if show or not good: notes.append(f"  {'OK ' if good else 'MISS'} [{time.time()-t1:.0f}s] {task}\n      -> {out[:300]!r}")
        print(f"{b:58s} {bok:2d}/{len(tasks)}", flush=True)
    print(f"TOTAL {ok}/{tot}  ({time.time()-t0:.0f}s)"); print("\n".join(notes))
finally:
    P.stop(); T.on_hands(T.close_browser)
