#!/usr/bin/env python3
"""Everyday talk — the questions an owner types that need a direct answer, not a job (milestone 20 polish).

Run: python3 engine/scripts/score_talk.py [--show]
"""
import os, re, sys, time, shutil, pathlib, threading
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.pop("DISPLAY", None)
os.environ["BAI_STATE"] = "/tmp/bai_talk_state"
shutil.rmtree("/tmp/bai_talk_state", ignore_errors=True)
show = "--show" in sys.argv

from agent.talk import Talk
from agent import core

PASS = FAIL = 0
def check(name, ok, detail=""):
    global PASS, FAIL
    PASS += bool(ok); FAIL += (not ok)
    print(("✅" if ok else "❌"), name, ("" if ok or not detail else f"— {detail}"))

T = Talk()
r = T.reply("what can you do for me?")
check("'what can you do' → plain-words menu", r and "Here's what I do" in r and "seller" in r and "website" in r)
r = T.reply("ok thanks, that's all for now")
check("'thanks, that's all' → goodbye, no menu", r and "talk later" in r.lower() and "Here's what I do" not in r, r)
check("'thanks!' → you're welcome", "welcome" in (T.reply("thanks!") or ""))
check("greeting → hello + question back", "What do you need" in (T.reply("hey, how's it going?") or ""))
check("greeting with a request attached is NOT swallowed", T.reply("hi, research shipping days") is None and T.reply("hey can you check this seller? https://x.com/a") is None)
r = T.reply("how much should I charge for a candle that costs me 4 euros to make?")
check("pricing: three price points from the cost", r and "€ 9,90" in r and "€ 11,90" in r and "€ 15,90" in r, (r or "")[:200])
check("pricing: margin after payment fee shown", r and re.search(r"keep € \d+,\d\d per sale \(\d+ % margin\)", r))
r2 = T.reply("a candle costs me 4 euros and shipping 3.50, what price?")
check("pricing: shipping added to the landed cost", r2 and "€ 7,50 landed" in r2, (r2 or "")[:120])
r = T.reply("is 3.9 euro shipping too much for italy?")
check("shipping sanity: € 3,90 Italy → normal range", r and "normal range" in r and "€ 3,90" in r, r)
r = T.reply("is €14 delivery ok for italy?")
check("shipping sanity: € 14 Italy → high", r and "high side" in r, r)
r = T.reply("is €9.90 delivery ok for germany?")
check("shipping sanity: € 9,90 Germany → normal for EU", r and "normal for EU" in r, r)
r = T.reply("customer says the parcel arrived broken, what do I answer?")
check("customer words → handed to the inbox (not answered by guessing)", isinstance(r, dict) and r.get("customer") == "the parcel arrived broken", str(r))
r = T.reply('a customer wrote "where is my order, it\'s been 10 days" — how do I reply?')
check("quoted customer text extracted whole (apostrophe inside)", isinstance(r, dict) and r.get("customer") == "where is my order, it's been 10 days", str(r))
r = T.reply("I want to sell handmade candles online, where do I start?")
check("'where do I start' → numbered first steps as a to-do list", isinstance(r, dict) and len(r["todo"]) == 7 and "handmade candles" in r["text"] and "1. " in r["text"], str(r)[:120])
check("real jobs are left alone", all(T.reply(m) is None for m in ["find me 3 suppliers of soy wax in europe", "research shipping days, take it slow",
                                                                     "build a website for a bakery in Bergamo", "what's a good margin for dropshipping?",
                                                                     "compare aliexpress vs cj dropshipping", "stop", "what are you doing?"]))
check("commands are left alone", T.reply("/status") is None and T.reply("/research x") is None)

# ---- through the agent: customer words become an inbox draft with buttons; to-dos are stored -------------
class FakeBot:
    def __init__(self, *a, **k): self.sent = []; self.docs = []
    def get_me(self): return {"username": "bot", "id": 1}
    def send(self, chat, text, buttons=None, **k): self.sent.append((text, buttons)); return {"message_id": len(self.sent)}
    def __getattr__(self, n): return lambda *a, **k: None
core.Bot = lambda *a, **k: FakeBot()
A = core.Agent(); A.owner_id = 1; A.planner.available = lambda: False; A.planner.installed = lambda: False
r = A.respond("customer says the parcel arrived broken, what do I answer?")
for _ in range(40):
    if any(b for _, b in A.bot.sent if b):
        break
    time.sleep(0.25)
drafts = [(t, b) for t, b in A.bot.sent if b]
check("agent: customer words → draft with Approve/Edit/Reject", drafts and "my draft" in drafts[-1][0] and any("r:ok:" in btn[1] for row in drafts[-1][1] for btn in row), str(drafts[-1][0][:100]) if drafts else str(A.bot.sent[-2:]))
check("agent: the draft is about damage (right kind)", drafts and "damaged" in drafts[-1][0].lower(), drafts[-1][0][:80] if drafts else "")
r = A.respond("I want to sell handmade candles online, where do I start?")
check("agent: first steps stored as to-dos", r and "to-do list" in r and len(A.memory.open_items()) >= 7, str(len(A.memory.open_items())))
r = A.respond("remind me what you did today")
check("agent: today's recap mentions the waiting customer message", r and "Today (" in r and "customer message" in r, r)
r = A.respond("hey, how's it going?")
check("agent: greeting knows what's waiting", r and "customer message" in r and "open to-do" in r, r)
r = A.respond("how much should I charge for a mug that costs me 3.20?")
check("agent: pricing answered directly (no plan, no job)", r and "Pricing mug" in r and "What I understood" not in r and not A.busy, (r or "")[:80])

print(f"\nTALK SCORE: {PASS}/{PASS + FAIL}")
sys.exit(0 if FAIL == 0 else 1)
