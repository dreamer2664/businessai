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

# ---- quick things: to-do in plain words, the clock, opinions — also while a job runs -------------------
A.memory.todo["items"] = []; A.memory._save()
r = A.respond("add 'call the accountant' to my list")
check("to-do: plain-words add → stored + numbered", r and "#1" in r and "Call the accountant" in r and len(A.memory.open_items()) == 1, r)
r = A.respond("remind me to order boxes")
check("to-do: 'remind me to' add", r and "#2" in r and "Order boxes" in r, r)
r = A.respond("what's on my to-do list?")
check("to-do: list in plain words", r and "1. Call the accountant" in r and "2. Order boxes" in r, r)
r = A.respond("I ordered the boxes, tick it off")
check("to-do: done by description", r and "Ticked off: Order boxes" in r and len(A.memory.open_items()) == 1, r)
r = A.respond("done 1")
check("to-do: done by number", r and "Call the accountant" in r and not A.memory.open_items(), r)
r = A.respond("what time is it in shenzhen?")
check("clock: time in a supplier city with the gap", r and re.search(r"In Shenzhen it's \d\d:\d\d", r) and "ahead of you" in r, r)
r = A.respond("what time is it")
check("clock: local time", r and re.search(r"It's \d\d:\d\d here", r), r)
r = A.respond("shopify vs woocommerce, what do you think?")
check("opinion: shopify vs woocommerce → a real take, no job", r and "My take on Shopify vs Woocommerce" in r and "Shopify if" in r and not A.busy, (r or "")[:80])
r = A.respond("is it worth holding stock or dropshipping?")
check("opinion: stock vs dropshipping", r and "Dropshipping =" in r and "Own stock =" in r, (r or "")[:80])
r = T.reply("translate to english: la merce parte lunedì, tracking entro 48 ore")
check("translate: request understood → text + language", isinstance(r, dict) and r.get("to") == "English" and r["translate"].startswith("la merce"), str(r))
r = T.reply("how do you say 'thanks for your order' in italian?")
check("translate: 'how do you say X in Y'", isinstance(r, dict) and r.get("to") == "Italian" and r["translate"] == "thanks for your order", str(r))
r = T.reply("traduci: where is my parcel?")
check("translate: language guessed from the text (English → Italian)", isinstance(r, dict) and r.get("to") == "Italian", str(r))
r = A.respond("translate to english: la merce parte lunedì")
check("agent: no thinking model → honest line, no job", r and "can't translate without my thinking model" in r and not A.busy, r)
_inst, _chat = A.planner.installed, A.planner.chat
A.planner.installed = lambda: True; A.planner.chat = lambda *a, **k: "The goods leave on Monday"
r = A.respond("translate to english: la merce parte lunedì")
check("agent: with the model → the translation, prefixed with the language", r == "In English:\nThe goods leave on Monday", r)
A.planner.installed, A.planner.chat = _inst, _chat
r = A.respond("is 9 € shipping to Germany normal?")
check("shipping sanity: '9 € shipping to Germany normal' → EU verdict", r and "normal for EU" in r, r)
r = A.respond("are you there?")
check("'are you there?' → yes + free", r and r.startswith("Yes, here") and "free" in r, r)
r = A.respond("I'm off to lunch, back in an hour")
check("'off to lunch, back in an hour' → quiet hour for study, no job", r and "about 1 h" in r and "study" in r and not A.busy and A.pace.budget_left() and 3500 < A.pace.budget_left() <= 3600, r)
A.pace.clear()
r = A.respond("send me the last document again")
check("'send me the last document' with an empty library → honest", r and "haven't written any document" in r, r)
r = A.respond("how's the practice store doing?")
check("'how's the store doing' → the numbers, no job", r and r.startswith("Practice store") and "profit" in r and not A.busy, (r or "")[:80])
r = A.respond("what did we decide about shipping prices?")
check("'what did we decide about X' with no notes → honest + offer", r and "nothing written down" in r and "shipping prices" in r, r)
r = A.respond("what should I name my shop? it sells cork sandals")
check("shop names → 6 ideas from what it sells + how to check", r and r.count("•") == 6 and "Cork" in r and "domain" in r and "trademark" in r, (r or "")[:120])
r = A.respond("write me a product description for a cork sandal, 2 lines")
check("description with no facts → plain version, asks for facts, no invented specs", r and r.startswith("Description for cork sandal") and "Give me 2–3 facts" in r and "TPU" not in r, (r or "")[:160])
r = A.respond("write a product description for the cork phone case")
check("description of a shop product → built from its own facts", r and "recycled TPU shell" in r and "Built only from the facts" in r, (r or "")[:160])
r = A.respond("write me a product description for a linen apron, it's made of washed linen with two pockets")
check("description uses the facts given in the sentence", r and "Linen apron — made of washed linen with two pockets." in r, (r or "")[:160])
n0 = len(A.memory.open_items())
r = A.respond("make a to-do list for launching the store next monday")
check("launch to-do list → 8 ordered steps stored", r and "Launch list for next monday" in r and "8. Next monday" in r and len(A.memory.open_items()) == n0 + 8, (r or "")[:100])
r = A.respond("do I need a partita iva to start?")
check("Italy: partita IVA → yes from the first sale, € 5,000 myth debunked, costs", r and "from the first sale" in r and "5,000" in r and "commercialista" in r and not A.busy, (r or "")[:100])
r = A.respond("how much tax do I pay in italy on 1000 € of sales?")
check("Italy: tax on € 1,000 → forfettario maths (40 % × 5 %) + INPS warning", r and "€ 400,00" in r and "€ 20,00" in r and "INPS" in r, (r or "")[:120])
r = A.respond("the customer wants a refund but the item was used, what do I do?")
check("returns: used item → 14-day withdrawal, deduction for use, hygiene exception, offer to draft", r and "14 days" in r and "deduct" in r and "hygiene" in r and "draft" in r, (r or "")[:120])
r = T.reply('customer asks for a refund after 20 days, what do I answer?')
check("returns: '…what do I answer?' still goes to the inbox draft", isinstance(r, dict) and r.get("customer"), str(r)[:80])
r = A.respond("can you check my email for the verification code from shopify?")
time.sleep(0.5)
check("'check my email for the code' → Gmail flow (honest when not connected)", r and "Looking in my Gmail" in r and "from shopify" in r and any("Gmail isn't connected" in t for t, _ in A.bot.sent[-2:]), r)
# the practice store in plain words + shop sense (no browsing, no model)
os.environ["BAI_STORE_PORT"] = "8178"
r = A.respond("open the practice store"); time.sleep(0.3)
check("'open the practice store' → opened (no research brief)", r and "Practice store open" in r and A.store.server, (r or "")[:100])
r = A.respond("what's in stock?")
check("'what's in stock?' → the stock list with margins, not a knowledge-pack answer", r and "Stock in the practice store" in r and "LED Desk Lamp" in r and "% margin" in r, (r or "")[:100])
time.sleep(1.0)                                                   # let the shop-read thread finish (no browser here → one apology line)
n0 = len(A.bot.sent)
r = A.respond("lower the price of the lamp to 35"); time.sleep(0.3)
last = next((t for t, _ in A.bot.sent[n0:] if "🏪" in t), A.bot.sent[-1][0] if len(A.bot.sent) > n0 else "")
check("'lower the price of the lamp to 35' → proposal with Apply button, nothing changed yet", "€ 39,00 → € 35,00" in last and A.store.product("led-desk-lamp")["price"] == 39.0, last[:120])
pid = A.store.data["proposals"][-1]["id"]
A.handle_callback({"id": "1", "from": {"id": 1, "username": "dreamer2664"}, "message": {"chat": {"id": 1}, "message_id": 5, "text": "x"}, "data": f"s:ok:{pid}"})
check("…Apply → price changed in the ledger", A.store.product("led-desk-lamp")["price"] == 35.0)
n0 = len(A.bot.sent)
A.respond("add a new product: linen apron, costs me 8, sell at 24"); time.sleep(0.3)
last = A.bot.sent[-1][0] if len(A.bot.sent) > n0 else ""
check("'add a new product: linen apron, costs me 8, sell at 24' → add proposal with cost, price and margin", "linen apron" in last and "€ 24,00" in last and "€ 8,00" in last and "67 % gross margin" in last, last[:140])
n0 = len(A.bot.sent)
A.respond("add product: hemp tote bag, it costs me 3.50"); time.sleep(0.3)
last = A.bot.sent[-1][0] if len(A.bot.sent) > n0 else ""
check("…no selling price → 3× the cost proposed and said so", "€ 10,90" in last and "3× the cost" in last, last[:140])
n0 = len(A.bot.sent)
A.respond("we received 20 more beeswax wraps today"); time.sleep(0.3)
last = A.bot.sent[-1][0] if len(A.bot.sent) > n0 else ""
check("'we received 20 more beeswax wraps' → stock 0 → 20 proposal", "Beeswax" in last and "stock 0 → 20" in last, last[:120])
A.store.simulate_day(inbox=None)
r = A.respond("which orders do I need to ship?")
check("'which orders do I need to ship?' → the order lines", r and "#5100" in r and "paid" in r, (r or "")[:100])
docs_before = len([x for x in A.bot.sent if False]) ; ndoc = len(getattr(A.bot, "docs", []))
r = A.respond("print the shipping labels"); time.sleep(0.3)
labels = sorted((pathlib.Path("/tmp/bai_talk_state") / "store" / "labels").glob("*.html"))
check("'print the shipping labels' → one HTML file with a label + packing slip per parcel", r and "label(s) ready" in r and labels and "TO / DESTINATARIO" in labels[-1].read_text() and "Packing slip" in labels[-1].read_text(), (r or "")[:100])
check("labels carry a street address for practice customers", labels and re.search(r"(Via|Corso|Straße|straße|weg|Rue|Avenue|Calle|Carrer|gracht|gasse|singel) \d", labels[-1].read_text()), "")
r = A.respond("all shipped, handed to GLS")
check("'all shipped' → paid orders marked shipped with tracking", r and "shipped with tracking numbers" in r and not [o for o in A.store.data["orders"] if o["status"] == "paid"], (r or "")[:100])
r = A.respond("a customer left a 1-star review saying the mug broke, what do I do?")
check("bad review → three moves + public reply draft (no research brief)", r and "three moves" in r and "Fix it privately first" in r and "Answer publicly" in r and "Never offer money" in r, (r or "")[:100])
r = A.respond("should I offer free shipping?")
check("'should I offer free shipping?' → threshold advice with a number from the store", r and "free shipping over €" in r and "threshold" in r, (r or "")[:100])
r = A.respond("which courier is cheapest in italy for small parcels?")
check("cheapest courier → Poste Delivery Web prices, comparators, when to get a contract", r and "Poste Delivery Web" in r and "€ 5,90 up to 2 kg" in r and "contract" in r, (r or "")[:100])
r = A.respond("what hashtags should I use for eco products?")
check("hashtags → three sizes, eco family, brand tag, rules", r and "#ecofriendly" in r and "#smallbusiness" in r and "#<yourshopname>" in r and "8–10 on Instagram" in r, (r or "")[:100])
r = A.respond("write 3 tiktok video ideas for the cork phone case")
check("'3 tiktok video ideas for the cork phone case' → 3 ideas from the product facts, not a video-watching job", r and "3 TikTok ideas for Phone Case Cork" in r and "1. " in r and "3. " in r and "cork" in r.lower() and "Hook" in r, (r or "")[:100])
check("store words are NOT stolen from real jobs", A.talk.reply("what is dead stock?") is None and A.talk.reply("find suppliers of linen aprons") is None and A.talk.reply("compare couriers for my shop, write me a document") is None and A.talk.reply("watch https://youtu.be/DNdBJ5tgyjI for video ideas") is None)
r = A.respond("close the practice store")
check("'close the practice store' → closed", r and "closed" in r and not A.store.server, (r or "")[:80])

# while busy: quick things are answered live, real requests are queued
import threading
gate = threading.Event()
A.tasks.run = lambda c: (gate.wait(20), "fake report")[1]
r = A.respond("research the best packaging for candles, write me a document, quick")
for _ in range(40):
    if A.busy:
        break
    time.sleep(0.25)
r = A.respond("add 'renew the domain' to my list")
check("busy: to-do add answered live (not 'noted for this job', not queued)", A.busy and r and "Added to your to-do list" in r and not A.mind.queue, r)
r = A.respond("what time is it in new york?")
check("busy: clock answered live", A.busy and r and "In New York" in r and not A.mind.queue, r)
r = A.respond("only eco packaging")
check("busy: a real constraint is still a change to the job", r and "Noted for this job" in r, r)
r = A.respond("compare cj dropshipping and aliexpress for candles")
check("busy: a new job is still queued", r and "queued as #1" in r, r)
gate.set()
for _ in range(60):
    if not A.busy and not A.mind.job and not A.mind.queue:
        break
    time.sleep(0.5)
A.mind.queue.clear()

print(f"\nTALK SCORE: {PASS}/{PASS + FAIL}")
sys.exit(0 if FAIL == 0 else 1)
