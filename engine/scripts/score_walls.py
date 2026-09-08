#!/usr/bin/env python3
"""CAPTCHA behaviour — try, then try something else (Phase 2, milestone 15).

A local site (tests/walls/server.py) has three kinds of pages: a checkbox wall that passes when ticked, a wall that never
passes, and open pages. The AI must:
  • pass the checkbox by itself during research and use the page,
  • skip the impossible wall and carry on with the other pages (no dead end, no owner nag),
  • when the owner asked for THAT page (/visit, summarize), try, then ask the owner for one tap, and accept a "Skip it",
  • report honestly.

Run: python3 engine/scripts/score_walls.py [--show]
"""
import os, re, sys, time, threading, pathlib, shutil, importlib.util
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.pop("DISPLAY", None)
os.environ["BAI_STATE"] = "/tmp/bai_walls_state"
shutil.rmtree("/tmp/bai_walls_state", ignore_errors=True)
show = "--show" in sys.argv
PORT = 8089

spec = importlib.util.spec_from_file_location("walls", ROOT / "tests" / "walls" / "server.py")
walls = importlib.util.module_from_spec(spec); spec.loader.exec_module(walls)
srv = walls.serve(PORT)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{PORT}"

from agent.tasks import Tasks
from agent.accounts import Accounts

PASS = FAIL = 0
def check(name, ok, detail=""):
    global PASS, FAIL
    PASS += bool(ok); FAIL += (not ok)
    print(("✅" if ok else "❌"), name, ("" if ok or not detail else f"— {detail}"))

logs = []
notes = []
asked = []
def fake_ask(question, options=None, timeout=0):
    asked.append((question, options))
    return "Skip it"

T = Tasks(log=lambda k, **f: logs.append((k, f)))
T.notify = lambda t: notes.append(t)
acc = Accounts(google=None, log=lambda k, **f: logs.append((k, f)), notify=lambda t: notes.append(t), ask=fake_ask)
T.accounts = acc

# ---- 1. research: easy wall passed alone, hard wall skipped, open page used ---------------------
walls.STATE["passed"].clear()
def run_research():
    b = T.browser()
    b.search_results = lambda q, n=10: [{"url": f"{BASE}/easy/carrier", "title": "carrier"},
                                        {"url": f"{BASE}/hard/europe", "title": "europe"},
                                        {"url": f"{BASE}/open/customs", "title": "customs"}]
    b.ENGINE_HOSTS = re.compile(r"$^")
    return T.research("shipping days", n_pages=3)
t0 = time.time()
out = T.on_hands(run_research, timeout=180)
dt = time.time() - t0
if show:
    print(out)
kinds = [k for k, _ in logs]
check("research: checkbox wall passed by itself", "captcha_passed" in kinds and any("Passed the security check" in n for n in notes), str(kinds))
check("research: the walled article was read after passing", "Carrier guide" in out or "2 to 3 business days" in out, out[:200])
check("research: impossible wall skipped, not fatal", "captcha_skipped" in kinds and "customs" in out.lower() or "12 to 20" in out, out[:200])
check("research: the owner was NOT asked for a tap (page not essential)", not asked, str(asked))
check("research: 2 pages read", "2 pages read" in out, re.findall(r"\(\d+ pages read[^)]*\)", out))
check("research: no exceptions logged", not any(k.endswith("_error") for k in kinds), str([k for k in kinds if k.endswith("_error")]))
check("research: finished in reasonable time", dt < 90, f"{dt:.0f}s")
check("stats: tried 2, passed 1, skipped 1", T.captcha_stats["tried"] == 2 and T.captcha_stats["passed"] == 1 and T.captcha_stats["skipped"] == 1, str(T.captcha_stats))

# ---- 2. visit an essential page behind the impossible wall → try, ask once, accept the skip ----
logs.clear(); notes.clear(); asked.clear()
out2 = T.on_hands(lambda: T.visit(f"{BASE}/hard/carrier"), timeout=120)
if show:
    print(out2)
check("visit: owner asked exactly once with tap buttons", len(asked) == 1 and asked[0][1] == ["Done", "Skip it"], str(asked))
check("visit: the question names the site and the 🧩", asked and "🧩" in asked[0][0] and "127.0.0.1" in asked[0][0], asked[0][0] if asked else "")
check("visit: honest reply after the skip", "couldn't get past" in out2 and "asked you" in out2, out2[:160])

# ---- 3. summarize a page behind the easy wall → passed alone, summary delivered -----------------
walls.STATE["passed"].clear(); logs.clear(); asked.clear()
out3 = T.on_hands(lambda: T.summarize(f"{BASE}/easy/europe"), timeout=120)
if show:
    print(out3)
check("summarize: easy wall passed, page summarized", "Europe delivery" in out3 and ("4 to 6" in out3 or "shipping days" in out3.lower()), out3[:160])
check("summarize: owner not bothered", not asked, str(asked))

# ---- 4. the browser still refuses to be a login robot --------------------------------------------
check("login walls untouched: status() still reports 'login' pages separately", "login" in open(ROOT / "agent" / "browser.py").read() and "LOGIN_HINTS" in open(ROOT / "agent" / "browser.py").read())

T.on_hands(T.close_browser, timeout=30)
srv.shutdown()
print(f"\nWALLS SCORE: {PASS}/{PASS + FAIL}")
sys.exit(0 if FAIL == 0 else 1)
