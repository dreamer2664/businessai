"""Score a knowledge pack with a question file (question<TAB>accepted|answers), extractive answers only.
   python3 engine/scripts/score_pack.py tests/business.txt release/business.kdw [--show]"""
import json, subprocess, sys, re, time, os
os.environ.setdefault("KDR_WIKI_READK", "3")
qf, pack = sys.argv[1], sys.argv[2]; show = "--show" in sys.argv
blocks, cur = {}, "misc"
for line in open(qf, encoding="utf-8"):
    line = line.rstrip("\n")
    if line.startswith("## "): cur = line[3:].strip(); continue
    if not line or line.startswith("#") or "\t" not in line: continue
    q, acc = line.split("\t", 1); blocks.setdefault(cur, []).append((q, [a.strip().lower() for a in acc.split("|")]))
tot = ok = 0; t0 = time.time(); fails = []
for b, qs in blocks.items():
    bok = 0
    for q, acc in qs:
        out = subprocess.run(["release/kdr-brain-lite", "release/brain.kdr", "--wiki", pack, "wiki", q], capture_output=True, text=True).stdout
        try: d = json.loads(out); ans = (d.get("answer") or ""); sent = d.get("sentence") or ""; conf = d.get("confidence", 0)
        except Exception: ans, sent, conf = "", "", 0
        hay = (ans + " " + sent).lower()
        good = any(a in hay for a in acc) and conf >= 0.3
        bok += good; tot += 1; ok += good
        if show or not good: fails.append(f"  {'OK ' if good else 'MISS'} {q} -> {ans[:70]!r} (conf {conf:.2f}) | {sent[:110]!r}")
    print(f"{b:32s} {bok:2d}/{len(qs)}")
print(f"TOTAL {ok}/{tot}  ({time.time()-t0:.0f}s)"); print("\n".join(fails))
