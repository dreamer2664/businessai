"""Thinking score (milestone 20): the agent knows what it is doing mid-job (status / why / hurry / stop / change / queue),
keeps a journal from the live-screen events, reflects after each job (lesson), and uses lessons in the next plan.
Pure-Python with a fake slow job (no browser). Run:  python3 engine/scripts/score_mind.py --show | tail -40"""
import os
import shutil
import sys
import threading
import time

os.environ["BAI_STATE"] = "/tmp/bai_mind_state"
os.environ.pop("DISPLAY", None)
shutil.rmtree(os.environ["BAI_STATE"], ignore_errors=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent import core                                    # noqa: E402
from agent.mind import Mind                               # noqa: E402
from agent.pace import Pace                               # noqa: E402

SHOW = "--show" in sys.argv
checks = []


def check(name, ok, note=""):
    checks.append((name, bool(ok)))
    if SHOW or not ok:
        print(("✅" if ok else "❌"), name, ("— " + str(note)[:120]) if note else "")


class FakeBot:
    def __init__(self, *a, **k):
        self.sent = []

    def get_me(self):
        return {"username": "bot", "id": 1}

    def send(self, chat, text, buttons=None, **k):
        self.sent.append((text, buttons))
        return {"message_id": len(self.sent)}

    def __getattr__(self, n):
        return lambda *a, **k: None


t_start = time.time()

# ---- 1) the Mind alone -------------------------------------------------------------------------------------------
P = Pace(log=lambda k, **f: None)
M = Mind(planner=None, log=lambda k, **f: None, pace=P)
P.set({"pace": "normal", "deadline_min": 10, "budget_min": None, "why": ""}, "find reliable suppliers of bamboo toothbrushes")
M.begin("find reliable suppliers of bamboo toothbrushes", "seller_check", ["Search for candidates", "Open each listing", "Read reviews", "Judge", "Write the document"])
M.on_event("plan_step", {"n": 2, "text": "reading listing 1/4: EcoBrush"})
M.on_event("browser_open", {"url": "https://ecobrush.example/listing"})
M.on_event("task_wall", {"url": "https://etsy.com/x", "wall": "captcha"})
st = M.status_line()
check("status: goal, step, elapsed, right-now, next", all(x in st for x in ("bamboo", "step 2 of 5", "Right now: reading", "Next: Read reviews")), st)
check("status: time left from the owner's clock", "min left" in st, st)
check("status: snags mentioned", "captcha wall" in st, st)
kinds = {m: M.interrupt(m)[0] for m in ["what are you doing?", "how long still?", "why?", "hurry up", "stop", "thanks!", "only italian sellers", "compare aliexpress vs cj for shipping to italy", "a che punto sei?", "sbrigati"]}
check("interrupt: status questions (en + it)", kinds["what are you doing?"] == "status" and kinds["how long still?"] == "status" and kinds["a che punto sei?"] == "status", kinds)
check("interrupt: why / hurry / stop / chat", (kinds["why?"], kinds["hurry up"], kinds["stop"], kinds["thanks!"]) == ("why", "hurry", "stop", "chat"), kinds)
check("interrupt: hurry in Italian", kinds["sbrigati"] == "hurry", kinds["sbrigati"])
check("interrupt: short constraint = change of course, long request = new job", kinds["only italian sellers"] == "change" and kinds["compare aliexpress vs cj for shipping to italy"] == "new", kinds)
check("hurry flips the pace to the short path", P.hurry() and P.mode == "quick")
why = M.why_line()
check("why: names the owner's ask and the reason for the step", "bamboo" in why and len(why) > 60, why)
rec = M.reflect("document with 3 options sent", delivered=True)
check("reflect: lesson written, job cleared", rec and rec["lesson"] and M.job is None, rec and rec["lesson"])
check("reflect: hurried job → lesson says send a first version sooner", "sooner" in rec["lesson"], rec["lesson"])
P.set({"pace": "quick", "deadline_min": 10, "budget_min": None, "why": ""}, "x")
M.begin("check vinted seller", "seller_check", ["a", "b"])
M.snag("captcha wall")
rec2 = M.reflect("Task failed: captcha", delivered=False)
check("reflect: failed on a CAPTCHA → lesson about trying another site first", "CAPTCHA" in rec2["lesson"] and "another site" in rec2["lesson"], rec2["lesson"])
adv = M.advice("seller_check")
check("advice: both lessons come back for the next seller check, newest first", len(adv) == 2 and "CAPTCHA" in adv[0], adv)
check("lessons text lists them", "What I learned" in M.lessons_text() and "CAPTCHA" in M.lessons_text())
check("stats line", "2 jobs" in M.stats_text() and "1 delivered" in M.stats_text(), M.stats_text())

# ---- 2) through the agent: a slow fake job + messages while it runs ------------------------------------------------
core.Bot = lambda *a, **k: FakeBot()
A = core.Agent()
A.owner_id = 1
A.planner.available = lambda: False
A.planner.installed = lambda: False
gate = threading.Event()


def slow_task(command):                                    # replaces tasks.run: waits until the test lets it finish
    A.viewer.plan_step(1, "reading page 2")
    A.log("browser_open", url="https://example.org/page2", ms=800)
    gate.wait(20)
    if A.pace.should_stop():
        return "Stopped early: here is what I had — 2 pages read."
    return "Report: epacket is a shipping option … (fake)"


A.tasks.run = slow_task
r = A.respond("research how epacket works for shipments to italy")
check("job starts and shows the plan", r and "What I understood" in r, (r or "")[:80])
time.sleep(1.0)
s1 = A.respond("what are you doing?")
check("mid-job 'what are you doing?' → live status, job not interrupted", s1 and "I'm on:" in s1 and "epacket" in s1 and A.busy, s1)
s2 = A.respond("why?")
check("mid-job 'why?' → reason", s2 and "you asked" in s2.lower(), s2)
s3 = A.respond("hurry up")
check("mid-job 'hurry up' → acknowledged + short path", s3 and "Speeding up" in s3 and A.pace.hurry(), s3)
s4 = A.respond("only sellers that ship from italy")
check("mid-job constraint → noted for this job", s4 and "Noted for this job" in s4 and A.mind.job.get("change"), s4)
s5 = A.respond("compare aliexpress vs cj dropshipping for shipping times to italy")
check("mid-job new request → queued, not refused", s5 and "queued as #1" in s5 and len(A.mind.queue) == 1, s5)
s6 = A.respond("ok")
check("mid-job 'ok' → silence (no chatter)", s6 is None, s6)
s7 = A.respond("stop")
check("mid-job 'stop' → stop flag + honest line", s7 and "Stopping" in s7 and A.pace.should_stop(), s7)
gate.set()
for _ in range(40):
    if any("Stopped early" in t for t, _ in A.bot.sent):
        break
    time.sleep(0.5)
check("the job hands over what it had", any("Stopped early" in t for t, _ in A.bot.sent), [t[:60] for t, _ in A.bot.sent[-3:]])
time.sleep(2.5)
check("queued request started by itself after the job", any("Now the request you queued" in t for t, _ in A.bot.sent) and (A.busy or A.last_brief or any("aliexpress" in t.lower() for t, _ in A.bot.sent[-3:])), [t[:70] for t, _ in A.bot.sent[-3:]])
check("reflection written for the stopped job", any(r_.get("goal", "").startswith("research how epacket") or "epacket" in r_.get("goal", "") for r_ in __import__("agent.mind", fromlist=["_load"])._load(__import__("agent.mind", fromlist=["LESSONS"]).LESSONS)))
lt = A.respond("/lessons")
check("/lessons shows it", "What I learned" in lt and "research" in lt, lt[:160])
st_ = A.status_text()
check("status shows thinking stats", "thinking:" in st_ and "jobs reflected" in st_)
# a second research shows the lesson in its plan
for _ in range(40):                                        # let the queued compare job finish (the fake task returns at once)
    if not A.busy and not A.mind.job:
        break
    time.sleep(0.5)
A.mind.queue.clear()
A.last_brief = None
A.tasks.run = lambda c: "fake report"
r2 = A.respond("research the best shipping options from china to italy, write me a document") or (A.bot.sent[-1][0] if A.bot.sent else "")
check("next plan of the same kind carries 'From last time'", "From last time" in r2, r2[-200:])
gate.set()
time.sleep(1)

ok = sum(1 for _, o in checks if o)
print(f"\nSCORE mind {ok}/{len(checks)}  ({time.time() - t_start:.0f}s)")
sys.exit(0 if ok == len(checks) else 1)
