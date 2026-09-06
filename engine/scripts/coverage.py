"""Knowledge-coverage probe: for MCQ questions, is the correct choice's text present in the top retrieved passages?
   python3 engine/scripts/coverage.py tests/banks/mcq_principles-marketing.jsonl pack.kdw [n_sample]"""
import json, subprocess, sys, random, re
bank, pack = sys.argv[1], sys.argv[2]; n = int(sys.argv[3]) if len(sys.argv) > 3 else 100
qs = [json.loads(l) for l in open(bank)]; random.seed(1); qs = random.sample(qs, min(n, len(qs)))
hit = 0
for q in qs:
    ans = q["choices"][q["answer"]].lower().strip(" .")
    if len(ans) < 4 or ans in ("all of the above", "none of the above", "both a and b", "true", "false"): n -= 1; continue
    out = subprocess.run(["release/kdr-brain-lite", "release/brain.kdr", "--wiki", pack, "wiki", q["q"]], capture_output=True, text=True).stdout
    try: d = json.loads(out); hay = " ".join(h.get("text", "") for h in d.get("hits", [])).lower() + " " + (d.get("sentence") or "").lower()
    except Exception: hay = ""
    key = re.sub(r"[^a-z0-9 ]", " ", ans); words = [w for w in key.split() if len(w) > 3]
    ok = ans in hay or (words and sum(w in hay for w in words) >= max(1, int(0.7 * len(words))))
    hit += ok
print(f"coverage {hit}/{n} = {100*hit/max(1,n):.0f}%  ({pack})")
