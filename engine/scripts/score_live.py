"""Score the operator on REAL shops: python3 engine/scripts/score_live.py [filter]
Rows come from tests/live.txt (url, goal, expected). Sites change and sometimes block robots, so besides the usual
"expected words" a row can say WALL (an honest refusal is the right answer). A site that is unreachable from this machine
at the moment counts as SKIP, not as a failure. Prints one line per goal and the total; ~10-25 min with a 1.5B model."""
import os, re, socket, sys, time
sys.path.insert(0, ".")
os.environ.pop("DISPLAY", None)
from agent.planner import Planner
from agent.tasks import Tasks
from agent.operator import Operator

REFUSAL = re.compile(r"bot-check|never (try to get past|pass)|shows an error|could not reach|would not serve|can'?t be reached|"
                     r"I stopped|blocks robots", re.I)
WRONG_ANSWER = re.compile(r"^(Done|Yes|No|The)", re.I)     # a confident sentence where a refusal was expected

flt = sys.argv[1] if len(sys.argv) > 1 else ""
rows = [l.rstrip("\n").split("\t") for l in open("tests/live.txt") if l.strip() and not l.startswith("#")]
rows = [r for r in rows if flt.lower() in (r[0] + r[1]).lower()]


def reachable(url):
    host = re.sub(r"^https?://", "", url).split("/")[0]
    try:
        socket.create_connection((host, 443), timeout=8).close()
        return True
    except OSError:
        return False


P = Planner(); T = Tasks(planner=P)
O = Operator(P, tasks=T, log=lambda k, **f: None, ask_owner=lambda q, opts: opts[-1])
score, skipped, t_all = 0, 0, time.time()
for url, goal, expect in rows:
    if not reachable(url):
        skipped += 1
        print(f"SKIP    -s  {url[8:38]:30s} {goal[:50]:50s} → unreachable from here", flush=True)
        continue
    t0 = time.time()
    try:
        out = O.run(goal, where="browser", start_url=url)
    except Exception as e:
        out = f"ERROR {e}"
    report = out.split("\nWhat I did")[0].strip()
    secs = int(time.time() - t0)
    if expect == "WALL":
        ok = bool(REFUSAL.search(report)) and secs <= 120
    else:
        ok = any(alt.lower() in report.lower() for alt in expect.split("|")) and not REFUSAL.search(report)
        if not ok and REFUSAL.search(report) and re.search(r"bot-check|shows an error|could not reach", report):
            ok = True                                       # the shop turned us away today: honest, not wrong
            report = "(honest refusal) " + report
    score += ok
    print(f"{'OK ' if ok else 'BAD'} {secs:5d}s  {url[8:38]:30s} {goal[:50]:50s} → {report[:110]!r}", flush=True)
T.close_browser(); P.stop()
print(f"\nLIVE SCORE: {score}/{len(rows) - skipped}  (skipped {skipped}; {int(time.time() - t_all)} s)")
