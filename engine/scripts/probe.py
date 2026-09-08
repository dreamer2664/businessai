"""Quick owner-talk probe: python3 engine/scripts/probe.py "question 1" "question 2" …  (or a file with one question per line).
Runs a throw-away Agent with a fake Telegram bot and 3 practice days, prints each answer; ❌ marks answers that fell to a
research job or a knowledge snippet instead of a real reply. Kept in the repo so a sandbox reset can't wipe it."""
import os, sys, re, shutil, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
STATE = os.environ.get("BAI_PROBE_STATE", "/tmp/bai_probe")
PORT = os.environ.get("BAI_PROBE_PORT", "8199")
if "--keep" not in sys.argv:
    shutil.rmtree(STATE, ignore_errors=True)
os.environ["BAI_STATE"] = STATE
os.environ["BAI_STORE_PORT"] = PORT
os.environ.pop("DISPLAY", None)
from agent import core


class FakeBot:
    def __init__(self):
        self.sent = []

    def get_me(self):
        return {"username": "fake"}

    def send(self, chat, text, buttons=None, **k):
        self.sent.append((text, buttons))
        return {"message_id": len(self.sent)}

    def __getattr__(self, n):
        return lambda *a, **k: None


core.Bot = lambda *a, **k: FakeBot()
A = core.Agent()
A.owner_id = 1
A.planner.available = lambda: False
A.planner.installed = lambda: False
A.tasks.run = lambda c: "fake report"
A.log = lambda *a, **k: None
for _ in range(3):
    A.store.simulate_day()

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(args) == 1 and os.path.exists(args[0]):
    QS = [l.strip() for l in open(args[0], encoding="utf-8") if l.strip() and not l.startswith("#")]
else:
    QS = args
for q in QS:
    A.last_brief = None
    A.mind.queue.clear()
    A.bot.sent.clear()
    try:
        r = A.respond(q)
    except Exception as e:
        r = f"EXCEPTION {type(e).__name__}: {e}"
    if r is None and A.bot.sent:
        r = "(sent) " + A.bot.sent[-1][0]
    r = (r or "None").replace("\n", " | ")
    bad = ("What I understood" in r and "I'll hand you" in r) or "look it up" in r or "knowledge pack" in r or r.startswith("EXCEPTION")
    print(("❌ " if bad else "   ") + q + "\n     → " + r[:220], flush=True)
