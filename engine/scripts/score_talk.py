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
                                                                     "compare aliexpress vs cj dropshipping", "stop"]))
r = T.reply("what are you doing?")
check("'what are you doing?' when idle → honest 'nothing running' line (while busy, core answers from the running job)", isinstance(r, str) and r.startswith("Nothing running"), (r or "")[:80])
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
from agent.social import Social
check("'make a tiktok post about our mugs' → tiktok + 'our mugs' (post, not a video to watch)", Social.parse("make a tiktok post about our mugs") == ("tiktok", "our mugs") and Social.parse("write me a post for facebook about the new lamp, quick") == ("facebook", "the new lamp") and A.briefer.make("make a tiktok post about our mugs")["kind"] == "post")
check("store words are NOT stolen from real jobs", A.talk.reply("what is dead stock?") is None and A.talk.reply("find suppliers of linen aprons") is None and A.talk.reply("compare couriers for my shop, write me a document") is None and A.talk.reply("watch https://youtu.be/DNdBJ5tgyjI for video ideas") is None)
r = A.respond("close the practice store")
check("'close the practice store' → closed", r and "closed" in r and not A.store.server, (r or "")[:80])
# the store's own numbers in answers (a practice day already ran above)
r = A.respond("how many orders did we get this week?")
check("'how many orders this week?' → count + sales from the ledger, no research", r and re.match(r"Orders this week: \d+", r) and "in sales" in r, (r or "")[:100])
r = A.respond("what's our best seller?")
check("'best seller?' → product, units, margin, stock left", r and r.startswith("Best seller so far:") and "sold" in r and "left)" in r, (r or "")[:120])
r = A.respond("how much profit did we make so far?")
check("'profit so far?' → profit with goods/shipping/fees breakdown", r and r.startswith("Profit so far:") and "payment fees" in r, (r or "")[:100])
r = A.respond("what's our conversion rate?")
check("'conversion rate?' → % from visits and orders + what's normal", r and "Conversion so far:" in r and "1–3 %" in r, (r or "")[:100])
r = A.respond("give me a summary of the week")
check("'summary of the week' → the numbers, best sellers, to-ship, low stock", r and r.startswith("Practice store — this week") and "conversion" in r, (r or "")[:100])
r = A.respond("how much is shipping to germany?")
check("'shipping to germany?' → the shop's own rule (€ 6,90, 4–6 days), not a web search", r and "Shipping to DE: € 6,90" in r and "4–6 business days" in r, (r or "")[:100])
r = A.respond("quanto costa spedire in svizzera?")
check("'spedire in svizzera?' → not offered (EU only)", r and "don't ship to Switzerland" in r and "EU" in r, (r or "")[:100])
r = A.respond("how long until the toothbrushes sell out at this pace?")
check("'how long until X sells out?' → days of stock from the last 7 days' sales", r and r.startswith("Bamboo Toothbrush Set") and ("days of stock" in r or "no sell-out in sight" in r), (r or "")[:120])
r = A.respond("if I sell 40 mugs a month at 14.90 with cost 5.60, how much do I make?")
check("'if I sell 40 mugs a month…' → per sale, per month, per year with fees and shipping", r and "per sale: € 14,90 − cost € 5,60 − payment fee € 0,73 = € 8,57" in r and "per month: € 342,72" in r and "per year" in r, (r or "")[:160])
check("small maths answered inline", A.talk.reply("what's 15% of 89?") == "15 % of 89 = 13.35" and A.talk.reply("120 + 22%").startswith("120 + 22 % = 146.40") and A.talk.reply("what's 89 * 1.22?") == "89 * 1.22 = 108.58" and A.talk.reply("what's 2026?") is None)
r = A.respond("remind me tomorrow at 9 to call the supplier")
item = A.memory.todo["items"][-1]
check("'remind me tomorrow at 9 to call the supplier' → dated to-do (not 'Morrow at 9…')", r and r.startswith("Reminder set for") and "09:00: call the supplier" in r and item.get("due", "").endswith("T09:00") and item["text"].startswith("Call the supplier"), (r or "")[:100])
item["due"] = "2000-01-01T00:00"; A.memory._save(); n0 = len(A.bot.sent)
A.reminders_due(); A.reminders_due()
check("due reminder pinged once", sum(1 for t, _ in A.bot.sent[n0:] if t.startswith("⏰ Reminder: Call the supplier")) == 1)
r = A.respond("write a thank-you note to put in the parcels")
check("thank-you note for the parcels → ready text with the shop name", r and "Thank-you card" in r and "Green Nest" in r and "review" in r, (r or "")[:80])
r = A.respond("scrivi un biglietto di ringraziamento da mettere nei pacchi")
check("…in Italian when asked in Italian", r and "Biglietto" in r and "Grazie per aver scelto Green Nest" in r, (r or "")[:80])
r = A.respond("how do I answer a customer who wants to cancel?")
check("'how do I answer a customer who wants to cancel?' → the rule per case + offer to draft", r and "Order not shipped" in r and "14 days" in r and "draft" in r, (r or "")[:100])
# owner questions answered from the shop's own data (round 2)
n0 = len(A.bot.sent); r = A.respond("the supplier raised the mug cost to 6.50, what now?")
sent = [t for t, _ in A.bot.sent[n0:]]
check("'supplier raised the mug cost to 6.50' → cost proposal with the margin effect + Apply button", r is None and sent and "cost € 5,60 → € 6,50" in sent[-1] and "62 % → 56 %" in sent[-1] and A.bot.sent[-1][1], (sent or [""])[-1][:100])
r = A.respond("which product should I push this week?")
check("'which product should I push?' → margin × stock × sales pick, low-stock ones excluded", r and r.startswith("Push ") and "margin per sale" in r and "Don't push" in r and "LED Desk Lamp" in r.split("Don't push")[1], (r or "")[:100])
r = A.respond("how are we doing compared to last week?")
check("'compared to last week' on day 1 → honest 'no previous week yet'", r and "no previous week" in r, (r or "")[:100])
r = A.respond("what did customers complain about?")
check("'what did customers complain about?' → grouped from the inbox with a fix per kind", r and (r.startswith("Complaints in the inbox") or "none is a complaint" in r), (r or "")[:100])
n0 = len(A.bot.sent); r = A.respond("add a product: linen apron, cost 9, sell 24.90, 20 in stock")
check("'add a product … 20 in stock' → the proposal keeps the stock number", r is None and "Stock starts at 20" in A.bot.sent[-1][0], A.bot.sent[-1][0][:100])
n0 = len(A.bot.sent); r = A.respond("lower the lamp price to 34")
check("'lower the lamp price to 34' (price after the product) → proposal", r is None and "LED Desk Lamp Nordic: price" in A.bot.sent[-1][0] and "→ € 34,00" in A.bot.sent[-1][0], A.bot.sent[-1][0][:100])
r = A.respond("can you write the shipping policy page?")
check("'write the shipping policy page' → the shop's real rules, not an article", r and r.startswith("Shipping page") and "€ 3,90" in r and "Germany" in r, (r or "")[:100])
r = A.respond("what should I write on the about page of my shop?")
check("'about page' → a fill-the-blanks About text", r and "About page" in r and "[year]" in r, (r or "")[:100])
r = A.respond("quick, 10 minutes: give me 5 captions for the mug")
check("'5 captions for the mug' → 5 captions from the product facts + hashtags", r and r.startswith("5 captions for Stoneware Coffee Mug") and "5. " in r and "invented" not in r and "Hashtags:" in r, (r or "")[:100])
r = A.respond("what should our prices be for black friday?")
check("'prices for black friday' → per-product discount that keeps ~45 % margin + Omnibus rule", r and "Sale prices" in r and "→ −" in r and "Omnibus" in r, (r or "")[:100])
r = A.respond("is 14.90 too much for a mug?")
check("'is 14.90 too much for a mug?' → margin verdict from the shop's cost + 'compare prices'", r and "58 % margin" in r and "compare prices" in r, (r or "")[:100])
r = A.respond("how much stock should I order of the toothbrushes?")
check("'how much stock should I order of X?' → reorder quantity from the sales pace", r and r.startswith("Bamboo Toothbrush Set") and ("order about" in r or "no reorder needed" in r), (r or "")[:100])
r = A.respond("what's the cheapest way to ship a mug to france?")
check("'cheapest way to ship … to france' → courier prices incl. abroad line", r and r.startswith("Cheapest way to ship") and "Abroad" in r, (r or "")[:100])
r = A.respond("should I offer free returns?")
check("'should I offer free returns?' → a clear rule with the economics", r and r.startswith("Free returns") and "faulty" in r, (r or "")[:100])
r = A.respond("what do I say to a customer asking where the order is?")
check("'what do I say to a customer asking where the order is?' → the three cases", r and "Not shipped yet" in r and "Lost" in r, (r or "")[:100])
r = A.respond("how many mugs do we have left?")
check("'how many mugs do we have left?' → that product only", r and r.startswith("Stoneware Coffee Mug 350 ml:") and "in stock" in r, (r or "")[:100])
r = A.respond("what's our average order value?")
check("'average order value?' → AOV from the ledger + the two levers", r and r.startswith("Average order") and "items per order" in r, (r or "")[:100])
r = A.respond("mi fai un riassunto della settimana?")
check("'riassunto della settimana' → the week summary from the ledger", r and r.startswith("Practice store — this week"), (r or "")[:100])
r = A.respond("che prodotto conviene spingere?")
check("'che prodotto conviene spingere?' → Italian push pick", r and r.startswith("Spingi "), (r or "")[:100])
r = A.respond("how many emails are waiting?")
check("'how many emails are waiting?' → inbox count, not an article on e-mail marketing", r and ("customer message(s) waiting" in r or r.startswith("Nothing waiting")), (r or "")[:100])
r = A.respond("what's on my plate today?")
check("'what's on my plate today?' → to-dos + orders to ship + messages + low stock in one list", r and r.startswith("Today (") and "thing(s)" in r, (r or "")[:100])
# round 3: orders by number, late ones, who bought, margins, stock value, growth questions
r = A.respond("the lamp is out of stock, what do I tell people who ask?")
check("'X is out of stock, what do I tell people?' → a ready script, never 'soon'", r and "sold out right now" in r and "notify me" in r, (r or "")[:100])
r = A.respond("a customer wants to pay by bank transfer, is that ok?")
check("'bank transfer ok?' → yes with the three rules", r and r.startswith("Bank transfer") and "ship only when the money" in r, (r or "")[:100])
r = A.respond("someone ordered 10 mugs, should I give a discount?")
check("'someone ordered 10 mugs, discount?' → the maths from the shop's cost + a rule", r and r.startswith("10 × Stoneware Coffee Mug") and "−10 %" in r, (r or "")[:100])
r = A.respond("how do I get my first customers?")
check("'how do I get my first customers?' → ordered plan, cheapest first", r and r.startswith("First customers") and "What NOT to do" in r, (r or "")[:100])
r = A.respond("I have 200 euros for ads, where do I put them?")
check("'I have 200 euros for ads' → test budget plan tied to a product with stock", r and r.startswith("€ 200,00 for ads") and "ONE platform" in r and "reserve" in r, (r or "")[:100])
r = A.respond("write an instagram bio for the shop")
check("'write an instagram bio' → three bios with the shop name", r and r.startswith("Instagram bio for Green Nest") and "3. " in r, (r or "")[:100])
r = A.respond("what's the vat on a 14.90 mug?")
check("'vat on a 14.90 mug' → € 2,69 VAT, net € 12,21, forfettario note", r and "€ 2,69 is VAT" in r and "€ 12,21" in r and "forfettario" in r, (r or "")[:100])
r = A.respond("how much did we pay in fees?")
check("'how much did we pay in fees?' → from the ledger at 2,9 % + € 0,30", r and r.startswith("Payment fees") and "2,9 % + € 0,30" in r, (r or "")[:100])
A.store.simulate_day(); paid_ = [o for o in A.store.data["orders"] if o["status"] == "paid"]
if paid_:
    n_ = paid_[0]["n"]; n0 = len(A.bot.sent); r = A.respond(f"cancel order {n_}")
    check("'cancel order <n>' → proposal with customer, items, refund + Cancel button", r is None and f"Cancel order #{n_}" in A.bot.sent[-1][0] and A.bot.sent[-1][1], A.bot.sent[-1][0][:100])
else:
    check("'cancel order <n>' → proposal (no paid order to test on)", False)
shipped_ = [o for o in A.store.data["orders"] if o["status"] in ("shipped", "delivered")]
n_ = shipped_[0]["n"] if shipped_ else (paid_[0]["n"] if paid_ else 0)
r = A.respond(f"refund order {n_}, the mug arrived broken")
check("'refund order <n>, arrived broken' → refund proposal with the reason", r is None and f"Refund order #{n_}" in A.bot.sent[-1][0] and "reason:" in A.bot.sent[-1][0], A.bot.sent[-1][0][:100])
r = A.respond("cancel order 99999")
check("'cancel order 99999' → no such order", r and "no order #99999" in r, (r or "")[:100])
r = A.respond("what are our shipping days?")
check("'what are our shipping days?' → the shop's rules", r and "Our shipping prices" in r and "1 business day" in r, (r or "")[:100])
r = A.respond("which orders are late?")
check("'which orders are late?' → read from the ledger", r and (r.startswith("Nothing is late") or r.startswith("Late to ship") or "No orders yet" in r), (r or "")[:100])
r = A.respond("who bought the lamp?")
check("'who bought the lamp?' → orders for that product (or nobody yet)", r and (r.startswith("LED Desk Lamp Nordic — ") or r.startswith("Nobody has bought")), (r or "")[:100])
r = A.respond("what's my margin on the cork case?")
check("'what's my margin on the cork case?' → gross, after fee, with free shipping", r and r.startswith("Phone Case Cork at € 19,90") and "69 %" in r and "after the payment fee" in r, (r or "")[:100])
n0 = len(A.bot.sent); r = A.respond("set free shipping over 49")
check("'set free shipping over 49' → shipping-rule proposal (checkout + page) with an Apply button", r is None and "Free shipping in IT over € 49,00" in A.bot.sent[-1][0] and any("s:ok:" in b[1] for row in (A.bot.sent[-1][1] or []) for b in row), A.bot.sent[-1][0][:100])
r = A.respond("why did nobody buy the wraps?")
check("'why did nobody buy the wraps?' → out of stock is the first reason", r and "OUT OF STOCK" in r, (r or "")[:100])
r = A.respond("how much money is tied up in stock?")
check("'how much money is tied up in stock?' → value at cost + days of stock per product", r and r.startswith("Stock: €") and "tied up at cost" in r and "days of stock" in r or "of stock" in (r or ""), (r or "")[:100])
r = A.respond("what did we sell yesterday?")
check("'what did we sell yesterday?' → units from the ledger (or nothing)", r and (r.startswith("Sold yesterday") or r.startswith("Nothing sold yesterday")), (r or "")[:100])
r = A.respond("what should I post today?")
check("'what should I post today?' → one product + one angle + why, no post job started", r and r.startswith("Post today:") and "Why this product" in r and not A.mind.job, (r or "")[:100])
r = A.respond("make the shop bilingual")
check("'make the shop bilingual' → honest explanation of the two ways", r and r.startswith("Bilingual shop"), (r or "")[:100])
r = A.respond("translate the returns page into german")
check("'translate the returns page into german' → takes the real page text (model off here → honest)", r and "30 days of delivery" in r, (r or "")[:100])
# round 4: check-ins and sloppy forms
r = A.respond("how r we doing")
check("'how r we doing' → the shop's state: what needs the owner, rest fine", r and ("need you" in r or r.startswith("All fine") or r.startswith("All quiet")), (r or "")[:100])
r = A.respond("did anything happen while I was away?")
check("'did anything happen while I was away?' → same check-in, no research job", r and ("need you" in r or r.startswith("All")) and not A.mind.job, (r or "")[:100])
r = A.respond("stock ok?")
check("'stock ok?' → only the stock line", r and ("low/out of stock" in r or r.startswith("Stock is fine")), (r or "")[:100])
r = A.respond("any orders to ship?")
check("'any orders to ship?' → only the shipping line", r and ("order(s) to ship" in r or r.startswith("Nothing to ship")), (r or "")[:100])
r = A.respond("is anyone waiting for a reply?")
check("'is anyone waiting for a reply?' → inbox line only", r and ("customer message(s) waiting" in r or r.startswith("Nobody is waiting")), (r or "")[:100])
check("sloppy forms: 'howmany orders did we get', 'best seller??', 'profit?', 'total sales so far'",
      (A.respond("howmany orders did we get") or "").startswith("Orders so far") and (A.respond("best seller??") or "").startswith("Best seller") and (A.respond("profit?") or "").startswith("Profit so far") and (A.respond("total sales so far") or "").startswith("Practice store"))
r = A.respond("how many lamps sold?")
check("'how many lamps sold?' → units + money + stock left", r and r.startswith("LED Desk Lamp Nordic:") and "sold so far" in r and "left" in r, (r or "")[:100])
r = A.respond("when did we last sell a lamp?")
check("'when did we last sell a lamp?' → the last order for it", r and (r.startswith("Last LED Desk Lamp Nordic sale") or r.startswith("We haven't sold")), (r or "")[:100])
r = A.respond("spedizione in francia quanto costa")
check("'spedizione in francia quanto costa' → € 6,90 rule", r and "Shipping to FR: € 6,90" in r, (r or "")[:100])
# round 5: shopkeeper situations (agent/advice.py)
for _ in range(120):                                              # the shop-read thread from 'open the practice store' must be over first
    if not A.busy:
        break
    time.sleep(0.5)
A.mind.queue.clear()
for q, must in [("the courier lost a parcel, what do I do?", ["Courier lost a parcel", "claim"]),
                ("a customer says they never got the parcel but tracking says delivered", ["proof of delivery", "refund"]),
                ("a customer wants an invoice", ["invoice", "codice fiscale"]),
                ("how do I handle a return?", ["Handling a return", "14 days"]),
                ("someone wants to buy 100 cork cases for their company", ["100 × Phone Case Cork", "deposit"]),
                ("an influencer asked for a free lamp in exchange for a post", ["influencer", "Red flags"]),
                ("what do I do about a chargeback?", ["chargeback", "evidence"]),
                ("should I open a tiktok shop?", ["TikTok Shop", "organic videos"]),
                ("do I need insurance?", ["Insurance", "Product liability"]),
                ("how do I package the mugs so they don't break?", ["Packing Stoneware Coffee Mug", "bubble wrap"]),
                ("what's a good name for a newsletter?", ["Newsletter names for Green Nest", "1. "]),
                ("can you write the newsletter?", ["Newsletter draft", "Subject:", "unsubscribe"]),
                ("what time should I post?", ["When to post", "Instagram"]),
                ("how often should I post?", ["How often to post", "a day for the first 30 days"]),
                ("what's our return rate?", ["Return/refund rate", "%"]),
                ("which country buys most?", ["Sales by country", "IT"]),
                ("which day of the week sells best?", ["weekday", "orders"]),
                ("what do you think of the shop so far?", ["Honestly:", "Numbers:"]),
                ("I'm thinking of adding candles to the shop, good idea?", ["Adding candles", "Test small"]),
                ("should I raise prices?", ["Raise prices?", "Omnibus"]),
                ("tell me a joke", ["Back to work"]),
                ("I'm bored", ["Pick one"]),
                ("someone copied my photos and description", ["copyright", "48 h"]),
                ("I listed the lamp at the wrong price and someone ordered", ["Wrong price", "Refund immediately"]),
                ("where do I buy cheap boxes?", ["Boxes and packing", "RAJA"]),
                ("how do I take product photos with my phone?", ["Product photos", "window"]),
                ("I'm going on holiday for two weeks, what do I do with the shop?", ["holiday", "banner"]),
                ("do I need a cookie banner?", ["GDPR", "Cookie banner"]),
                ("a customer asks where the mugs are made, what do I say?", ["Where is it made", "truth"])]:
    r = A.respond(q); A.last_brief = None; A.mind.queue.clear()
    check(f"advice: {q!r}", r and all(x in r for x in must) and not A.mind.job, (r or "")[:100])
A.weather = lambda place, when="now": f"weather stub {place} {when}"
r = A.respond("what's the weather in bergamo")
check("'what's the weather in bergamo' → Open-Meteo lookup (stubbed here), no research job", r == "weather stub Bergamo now", r)
r = A.respond("will it rain in milan tomorrow?")
check("'will it rain in milan tomorrow?' → tomorrow's forecast", r == "weather stub Milan tomorrow", r)
# round 6: decisions and shop numbers in the owner's words
for q, need in [("someone ordered 2 lamps but we only have 3, should I keep one back?", ["Ship the order in full", "in stock"]),
                ("what should I write on the package / packing slip?", ["Packing slip", "card"]),
                ("a customer asks for a discount code, do we have any?", ["one code, one purpose", "Reply to the customer"]),
                ("should I offer gift wrapping?", ["paid option", "2,90"]),
                ("which product makes us the most money?", ["Most money", "gross margin"]),
                ("are we profitable?", ["Profit", "net margin"]),
                ("how much did we spend on shipping this month?", ["to the courier", "customers paid"]),
                ("how many customers do we have?", ["different people", "Countries"]),
                ("write an out of office reply for the shop email", ["Subject:", "Oggetto:"]),
                ("what if amazon sells the same mug cheaper?", ["Amazon sells it cheaper", "Stoneware Coffee Mug"]),
                ("should I sell on etsy too?", ["Sell on Etsy too?", "Fees"]),
                ("should I be on amazon?", ["Not yet", "GTIN"]),
                ("how do I get my first 100 followers?", ["First 100 followers", "Don't: buy followers"]),
                ("a customer left a 1-star review saying shipping was slow, what do I reply?", ["slow shipping", "Draft"]),
                ("can I ship to switzerland?", ["Not yet", "Switzerland"]),
                ("how long does it take to ship to germany?", ["4–6 business days", "Monday"]),
                ("what's the cheapest product we sell?", ["Cheapest: Bamboo Toothbrush Set", "add-on"]),
                ("what's the most expensive product?", ["Most expensive: LED Desk Lamp", "in stock"]),
                ("a customer says the mug is chipped, should I refund or replace?", ["Refund or replace?", "Stoneware Coffee Mug"]),
                ("temu sells the cork case for 4 euros, what do I do?", ["Temu sells it cheaper", "Phone Case Cork"])]:
    A.last_brief = None; A.mind.queue.clear()
    r = A.respond(q)
    r = r if isinstance(r, str) else ""
    check(f"round 6: '{q[:60]}'", all(x in r for x in need), r[:120].replace("\n", " | "))
# round 7: orders, catalogue facts, availability, quotes, two requests in one message
n1 = A.store.data["orders"][0]["n"]
for q, need in [(f"what's the status of order {n1}?", [f"Order #{n1}", "•"]),
                (f"did we ship {n1}?", [f"order #{n1}", "placed"]),
                (f"what's the total of order {n1}?", [f"Order #{n1}: total", "shipping"]),
                ("who is our best customer?", ["Best customers so far", "order(s)"]),
                ("any refunds this week?", ["refunds", "this week"]),
                ("did we lose money on any order?", ["lost money", "so far"]),
                ("how much is a lamp with shipping to france?", ["LED Desk Lamp Nordic to FR", "6,90"]),
                ("what do we charge for 2 mugs to spain?", ["2 × Stoneware Coffee Mug 350 ml to ES", "= €"]),
                ("is the lamp still available?", ["LED Desk Lamp Nordic", "in stock"]),
                ("when will the wraps be back?", ["Beeswax Food Wraps", "0 left"]),
                ("what do I need to reorder?", ["Reorder list", "order ~"]),
                ("give me the top 3 things to do today", ["Top 3 for today", "1."]),
                ("a customer asks if the mug is dishwasher safe", ["Stoneware Coffee Mug 350 ml", "dishwasher", "For the customer"]),
                ("does the lamp come with a charger?", ["LED Desk Lamp Nordic", "no power adapter"]),
                ("how heavy is the parcel for 2 mugs?", ["2 × Stoneware Coffee Mug", "kg"]),
                ("sold anything today?", ["today"]),
                ("how many items did we sell in total?", ["Items sold so far", "per order"]),
                ("how many orders yesterday?", ["Orders yesterday"]),
                ("how's the week going?", ["Practice store", "orders"]),
                ("how much stock do we have in total, in euros?", ["Stock: €", "at cost"])]:
    A.last_brief = None; A.mind.queue.clear()
    r = A.respond(q)
    r = r if isinstance(r, str) else ""
    check(f"round 7: '{q[:60]}'", all(x in r for x in need), r[:120].replace("\n", " | "))
A.last_brief = None; A.mind.queue.clear(); A.bot.sent.clear()
r = A.respond("lower the lamp to 35 and remind me tomorrow at 9 to call the supplier")
check("two requests in one message → both done (price proposal sent + reminder set)", isinstance(r, str) and "Reminder set" in r and any("35" in x[0] and "Apply" in x[0] for x in A.bot.sent), (r or "")[:100] + " | " + " || ".join(x[0][:60] for x in A.bot.sent[-2:]))
r = A.respond("mark the lamp as sold out")
check("'mark the lamp as sold out' → stock proposal or already-out note", (r is None and "sold out" in A.bot.sent[-1][0]) or (isinstance(r, str) and "sold out" in r), (r or A.bot.sent[-1][0])[:100])
# round 8: the shipping table is live — free-shipping threshold, price per country, opening a country
A.last_brief = None; A.mind.queue.clear(); A.bot.sent.clear()
r = A.respond("free shipping over 50")
props_ = [p for p in A.store.data["proposals"] if p["status"] == "open" and p["kind"] == "shipping"]
check("'free shipping over 50' → a shipping proposal (checkout + page), with the basket maths", r is None and props_ and "Free shipping in IT over € 50,00" in A.bot.sent[-1][0] and "average basket" in A.bot.sent[-1][0], A.bot.sent[-1][0][:120])
if props_:
    A.store.apply(props_[-1]["id"])
check("applied → checkout charges € 3,90 under 50 and € 0 over 50", A.store.shipping_for("IT", 45) == 3.9 and A.store.shipping_for("IT", 55) == 0.0, f"{A.store.shipping_for('IT', 45)} / {A.store.shipping_for('IT', 55)}")
check("applied → the shipping page says 'free over € 50,00'", "free over € 50,00" in A.store.data["pages"]["shipping"], A.store.data["pages"]["shipping"][:80])
A.bot.sent.clear()
r = A.respond("open shipping to switzerland at 19.90")
props_ = [p for p in A.store.data["proposals"] if p["status"] == "open" and p["kind"] == "shipping"]
check("'open shipping to switzerland at 19.90' → proposal", r is None and props_ and "CH" in A.bot.sent[-1][0] and "19,90" in A.bot.sent[-1][0], A.bot.sent[-1][0][:100])
if props_:
    A.store.apply(props_[-1]["id"])
check("applied → CH is shippable at € 19,90 and on the page", A.store.shipping_for("CH", 10) == 19.9 and "Switzerland · € 19,90" in A.store.data["pages"]["shipping"], A.store.data["pages"]["shipping"][-160:])
r = A.respond("how much is shipping to switzerland?")
check("'shipping to switzerland?' now answers from the live table", isinstance(r, str) and "Shipping to CH: € 19,90" in r, (r or "")[:80])
# ---- round 9: about me and about judgment (selftalk.py) ----
A.last_brief = None; A.mind.queue.clear(); A.bot.sent.clear()
r = A.respond("what are you doing right now?")
check("'what are you doing right now?' → honest idle/busy line, not a lookup", isinstance(r, str) and ("Nothing running" in r or "Right now:" in r) and "look it up" not in r, (r or "")[:80])
r = A.respond("why did you propose lowering the price of the lamp?")
check("'why did you propose lowering the price of the lamp?' → the proposal's own reason from the ledger", isinstance(r, str) and "my reason at the time" in r and "LED Desk Lamp" in r and "margin" in r, (r or "")[:120])
r = A.respond("what happens if I ignore the proposals?")
check("'what happens if I ignore the proposals?' → nothing changes without a tap, by kind", isinstance(r, str) and "never changes without your tap" in r and "refunds" in r, (r or "")[:80])
r = A.respond("what would you change about the shop?")
check("'what would you change about the shop?' → ordered list from the store's own facts", isinstance(r, str) and r.startswith("What I'd change, in order:") and "1. " in r and "→" in r, (r or "")[:100])
r = A.respond("if you were me, what would you do first?")
check("'if you were me, what would you do first?' → one first thing with why + how", isinstance(r, str) and r.startswith("If I were you") and "Why:" in r and "How:" in r, (r or "")[:100])
r = A.respond("what's the biggest risk for us right now?")
check("'biggest risk right now?' → ranked risks with a fix each", isinstance(r, str) and "Biggest risks right now" in r and "1. " in r and "→" in r and "Cash" in r, (r or "")[:100])
r = A.respond("what do you need from me?")
check("'what do you need from me?' → pending taps/shipping/stock or 'nothing' + standing needs", isinstance(r, str) and ("From you, today:" in r or "Nothing right now" in r) and "Standing needs" in r, (r or "")[:100])
r = A.respond("explain the numbers like I'm 5")
check("'explain the numbers like I'm 5' → jar story with the real figures", isinstance(r, str) and "money in the jar" in r and "€" in r and "out of 100" in r, (r or "")[:100])
r = A.respond("is 3% conversion good?")
check("'is 3% conversion good?' → judged against the 2–3 % benchmark, with ours", isinstance(r, str) and "3 % is good" in r and "Yours is" in r, (r or "")[:100])
r = A.respond("how much should I put aside for taxes?")
check("'how much should I put aside for taxes?' → forfettario 15 % rule + INPS, from our sales", isinstance(r, str) and "15 %" in r and "INPS" in r and "set aside" in r, (r or "")[:100])
r = A.respond("should I hire someone?")
check("'should I hire someone?' → not yet, with the thresholds and the Italian cost factor", isinstance(r, str) and r.startswith("Hire someone? Not yet") and "1,5–1,7×" in r, (r or "")[:100])
r = A.respond("can you handle the shop alone for a week?")
check("'can you handle the shop alone for a week?' → what I do alone vs what needs a tap", isinstance(r, str) and r.startswith("Mostly yes") and "can't do alone" in r, (r or "")[:100])
r = A.respond("what can you do for the shop today without me?")
check("'what can you do for the shop today without me?' → store-specific list, not the generic capabilities", isinstance(r, str) and r.startswith("Today, without you, I can:") and "watch the store" in r, (r or "")[:100])
r = A.respond("how do you decide what to answer to customers?")
check("'how do you decide what to answer to customers?' → the 5-step routine", isinstance(r, str) and "I sort the message" in r and "Approve / Edit / Reject" in r, (r or "")[:100])
r = A.respond("what do you do when a customer is angry?")
check("'what do you do when a customer is angry?' → the angry-customer routine (not the capabilities list)", isinstance(r, str) and r.startswith("An angry customer") and "Answer fast" in r, (r or "")[:100])
r = A.respond("what do you know about our customers?")
check("'what do you know about our customers?' → countries, basket, loyalty from the ledger", isinstance(r, str) and "Our customers so far" in r and "Where:" in r and "Basket:" in r, (r or "")[:100])
r = A.respond("which countries should we sell to next?")
check("'which countries should we sell to next?' → ordered markets + what's open at checkout", isinstance(r, str) and "Germany + Austria first" in r and "Currently open at checkout" in r, (r or "")[:100])
r = A.respond("what's the plan for next week?")
check("'what's the plan for next week?' → numbered plan with content + Friday numbers", isinstance(r, str) and r.startswith("Plan for the week:") and "Content:" in r and "Friday" in r, (r or "")[:100])
r = A.respond("summarize the last 7 days in 3 lines")
check("'summarize the last 7 days in 3 lines' → exactly the 3 lines from the ledger", isinstance(r, str) and "in 3 lines" in r and "1. " in r and "2. Best seller" in r and "3. Problems" in r, (r or "")[:100])
r = A.respond("how confident are you about the numbers?")
check("'how confident are you about the numbers?' → layered honesty (exact / given / practice / guess)", isinstance(r, str) and "Honest answer, in layers" in r and "exact" in r and "educated guesses" in r, (r or "")[:100])
r = A.respond("what would a good month look like?")
check("'what would a good month look like?' → quiet/good/great month from our basket and margin", isinstance(r, str) and "a quiet month" in r and "a good month" in r and "visits at" in r, (r or "")[:100])
r = A.respond("we made 300 euros this week, is that good?")
check("'we made 300 euros this week, is that good?' → judged via monthly profit vs fixed bills", isinstance(r, str) and r.startswith("€ 300,00 of sales in a week") and "profit a month" in r and "Benchmarks" in r, (r or "")[:100])
r = A.respond("how much would we make if we doubled the traffic?")
check("'how much would we make if we doubled the traffic?' → conversion × basket maths with caveats", isinstance(r, str) and r.startswith("Doubling the traffic") and "orders instead of" in r and "caveats" in r, (r or "")[:100])
r = A.respond("what did you learn this week?")
check("'what did you learn this week?' → from lessons/notes/shop, never a lookup", isinstance(r, str) and "look it up" not in r and ("From the shop" in r or "Notes this week" in r or "Nothing new this week" in r), (r or "")[:100])
r = A.respond("what are we doing wrong?")
check("'what are we doing wrong?' → same honest change list", isinstance(r, str) and "What I'd change" in r, (r or "")[:80])
# ---- round 10: judgment questions answered from the ledger (selftalk.py) ----
A.last_brief = None; A.mind.queue.clear(); A.bot.sent.clear()
r = A.respond("is the shop making money?")
check("'is the shop making money?' → yes/not yet + the P&L line", isinstance(r, str) and (r.startswith("Yes — Profit") or r.startswith("Not yet — Profit")), (r or "")[:80])
r = A.respond("are you sure about that?")
check("'are you sure about that?' → knows the last answer was ledger numbers (exact) and what is softer", isinstance(r, str) and "ledger" in r and "softer" in r, (r or "")[:100])
r = A.respond("what's our best selling product and why?")
check("'best selling product and why?' → the best seller with share + reasons from the numbers", isinstance(r, str) and r.startswith("Best seller:") and "Why, as far as the numbers can tell" in r, (r or "")[:100])
r = A.respond("how long until we break even?")
check("'how long until we break even?' → stock at cost + set-up vs profit pace", isinstance(r, str) and ("Break-even, on what I can see" in r or r.startswith("Already there")) and "stock at cost" in r, (r or "")[:100])
r = A.respond("how many orders do we need to make 1000 euros a month?")
check("'how many orders for 1000 a month?' → orders/day + visits needed from our basket and conversion", isinstance(r, str) and r.startswith("To make € 1.000,00 of sales a month") and "orders a month" in r and "visits a month" in r, (r or "")[:120])
r = A.respond("is anything urgent?")
check("'is anything urgent?' → ranked urgent list or an honest 'nothing urgent'", isinstance(r, str) and (r.startswith("Urgent, most first:") or r.startswith("Nothing urgent")), (r or "")[:80])
r = A.respond("did anyone complain?")
check("'did anyone complain?' → from the inbox of the last 7 days", isinstance(r, str) and ("complaint" in r.lower() or "message" in r.lower()) and "look it up" not in r, (r or "")[:80])
r = A.respond("what would you do with 200 euros?")
check("'what would you do with 200 euros?' → ordered spending plan (stock first, cards, ad test)", isinstance(r, str) and r.startswith("With € 200,00, in this order:") and "thank-you cards" in r, (r or "")[:100])
r = A.respond("how do I get more reviews?")
check("'how do I get more reviews?' → the ranked playbook, no research job", isinstance(r, str) and r.startswith("More reviews") and "5–7 days after delivery" in r, (r or "")[:80])
r = A.respond("give me one idea to sell more this week")
check("'one idea to sell more this week' → one concrete idea from the store's data", isinstance(r, str) and r.startswith("One idea for this week:") and "say “" in r, (r or "")[:100])
r = A.respond("what mistakes did I make this week?")
check("'what mistakes did I make this week?' → from the ledger (late orders, stock-outs…) or an honest none", isinstance(r, str) and ("Mistakes this week, from the numbers" in r or r.startswith("None I can see")), (r or "")[:80])
r = A.respond("what do customers ask most?")
check("'what do customers ask most?' → counted kinds from the inbox, or the usual top three", isinstance(r, str) and ("What customers ask most" in r or "usual top three" in r), (r or "")[:80])
r = A.respond("why did sales drop?")
check("'why did sales drop?' → checks the ledger first ('they didn't' or the causes)", isinstance(r, str) and (r.startswith("They didn't, by the ledger") or r.startswith("Sales down:") or r.startswith("Too early")), (r or "")[:80])
r = A.respond("are prices too high?")
check("'are prices too high?' → judged by conversion + per-product margin lines", isinstance(r, str) and ("by the numbers" in r or r.startswith("Possibly") or r.startswith("No sales yet")) and "Rule I use" in r, (r or "")[:100])
r = A.respond("what's your goal for the shop?")
check("'what's your goal for the shop?' → its own goals, in order, with our numbers", isinstance(r, str) and r.startswith("My goal for the shop, in order:") and "NOT optimising" in r, (r or "")[:80])
# ---- round 11: follow-ups, feelings, preferences that change behaviour ----
A.last_brief = None; A.mind.queue.clear(); A.bot.sent.clear()
r = A.respond("show me the maths")
check("'show me the maths' → the P&L line by line from the ledger", isinstance(r, str) and "line by line" in r and "profit =" in r and "conversion:" in r, (r or "")[:100])
A.respond("is the shop making money?")
r = A.respond("hmm not convinced")
check("'hmm not convinced' after a numbers answer → separates solid counts from arguable conclusions, proposes a test", isinstance(r, str) and "What's solid" in r and "run it for a week" in r, (r or "")[:100])
r = A.respond("I'm tired of this, nothing sells")
check("'I'm tired of this, nothing sells' → straight talk with the shop's own facts, no lookup", isinstance(r, str) and ("I get it" in r or "I hear you" in r) and "look it up" not in r, (r or "")[:100])
r = A.respond("be honest with me")
check("'be honest with me' → bad/good/size from the ledger", isinstance(r, str) and r.startswith("Honest") and "The size:" in r, (r or "")[:100])
r = A.respond("what would you do differently than last week?")
check("'what would you do differently than last week?' → from the ledger (or 'no full week yet')", isinstance(r, str) and ("Differently than last week" in r or "There isn't a full 'last week' yet" in r), (r or "")[:100])
r = A.respond("give me a pep talk")
check("'give me a pep talk' → facts-based encouragement", isinstance(r, str) and r.startswith("Pep talk") and "post" in r.lower(), (r or "")[:100])
r = A.respond("what's the most important number to watch?")
check("'most important number to watch?' → one number chosen from the shop's stage", isinstance(r, str) and r.startswith("One number to watch right now:"), (r or "")[:100])
r = A.respond("how much did we lose on refunds?")
check("'how much did we lose on refunds?' → fees/postage/goods from the ledger", isinstance(r, str) and ("Nothing lost on refunds" in r or "Total lost:" in r), (r or "")[:100])
r = A.respond("customer paid twice")
check("'customer paid twice' → the double-charge routine", isinstance(r, str) and r.startswith("Double payment") and "chargeback" in r, (r or "")[:100])
r = A.respond("write the e-mail to past customers")
check("'write the e-mail to past customers' → a ready e-mail with subject, code and unsubscribe", isinstance(r, str) and "Subject:" in r and "BACK10" in r and "unsubscribe" in r, (r or "")[:100])
r = A.respond("write the review request e-mail")
check("'write the review request e-mail' → ready e-mail, 5–7 days after delivery", isinstance(r, str) and "Review request e-mail" in r and "{review link}" in r, (r or "")[:100])
r = A.respond("prepare the ad test")
check("'prepare the ad test' → concrete campaign with budget and stop rules (or restock first)", isinstance(r, str) and ("Stop rules on day 7" in r or "restock first" in r), (r or "")[:100])
r = A.respond("how much should I spend on ads?")
check("'how much should I spend on ads?' → the small-budget plan, no lookup", isinstance(r, str) and "Start small" in r and "my plan" in r, (r or "")[:100])
r = A.respond("show me the drafts")
check("'show me the drafts' → the waiting drafts (or none) from the inbox", isinstance(r, str) and ("draft(s) waiting" in r or r.startswith("No drafts waiting")), (r or "")[:100])
A.bot.sent.clear()
r = A.respond("add the bundle")
check("'add the bundle' → new-product proposal pairing best seller + slowest item, X,90 price", r is None and A.bot.sent and "Bundle" in A.bot.sent[-1][0] and ",90" in A.bot.sent[-1][0], (A.bot.sent[-1][0] if A.bot.sent else str(r))[:120])
r = A.respond("order 20 more lamps")
check("'order 20 more lamps' → purchase line + to-do (never buys by itself)", isinstance(r, str) and "your money" in r and "20 × LED Desk Lamp Nordic" in r and "to-do list" in r, (r or "")[:100])
r = A.respond("do you remember what I told you about the supplier?")
check("'do you remember what I told you about the supplier?' → finds the to-do about the supplier", isinstance(r, str) and "What I have from you about" in r and "supplier" in r, (r or "")[:100])
r = A.respond("do you remember what I told you about the warehouse?")
check("'…about the warehouse?' → honest 'nothing written down' + how to make me keep it", isinstance(r, str) and r.startswith("Honestly, no"), (r or "")[:80])
r = A.respond("call the supplier tomorrow")
check("'call the supplier tomorrow' (no 'remind me') → a dated reminder", isinstance(r, str) and r.startswith("Reminder set for") and "call the supplier" in r, (r or "")[:100])
A.bot.sent.clear()
A.store.apply(next(p["id"] for p in reversed(A.store.data["proposals"]) if p["kind"] == "stock" and p["status"] == "open")) if any(p["kind"] == "stock" and p["status"] == "open" for p in A.store.data["proposals"]) else None
lamp_before = A.store.product("led-desk-lamp")["stock"]
r = A.respond("the lamp is back in stock, 12 pieces")
check("'the lamp is back in stock, 12 pieces' → stock proposal", r is None and A.bot.sent and "LED Desk Lamp Nordic: stock" in A.bot.sent[-1][0] and "12" in A.bot.sent[-1][0], (A.bot.sent[-1][0] if A.bot.sent else str(r))[:100])
r = A.respond("stop proposing price changes")
check("'stop proposing price changes' → preference stored, review() no longer proposes prices", isinstance(r, str) and r.startswith("Understood") and "price" in A.talk.selftalk.muted() and not any(p["kind"] == "price" for p in A.store.review(mute=A.talk.selftalk.muted())), (r or "")[:80] + " | " + str(A.talk.selftalk.muted()))
r = A.respond("send routine replies yourself")
check("'send routine replies yourself' → preference stored, refunds still need a tap", isinstance(r, str) and r.startswith("OK — from now on") and A.memory.pref("auto_routine") is True and "Still yours to approve" in r, (r or "")[:80])
A.bot.sent.clear()
o_ = next((o for o in A.store.data["orders"] if o["status"] == "shipped"), None) or A.store.data["orders"][0]
A.inbox.add("store", "auto-test@example.com", f"Hi, where is my order #{o_['n']}? Still waiting for the tracking.", subject="where is it")
A.process_inbox()
auto_ = [t for t, b in A.bot.sent if t.startswith("📤 Sent by me")]
check("routine 'where is my order' → sent by me and shown to the owner afterwards (no buttons)", bool(auto_) and "tracking" in auto_[-1].lower(), (auto_[-1][:120] if auto_ else " | ".join(t[:60] for t, _ in A.bot.sent[-2:])))
A.bot.sent.clear()
A.inbox.add("store", "auto-test2@example.com", "The mug arrived broken, I want a refund. Photo attached.", subject="broken")
A.process_inbox()
check("'damaged + refund' is NOT routine → still a draft with Approve/Edit/Reject", any(b and any("r:ok:" in btn[1] for row in b for btn in row) for _, b in A.bot.sent) and not any(t.startswith("📤 Sent by me") for t, _ in A.bot.sent), " | ".join(t[:60] for t, _ in A.bot.sent[-2:]))
r = A.respond("ask me everything again")
check("'ask me everything again' → both preferences off", isinstance(r, str) and r.startswith("Done:") and not A.memory.pref("auto_routine") and not A.talk.selftalk.muted(), (r or "")[:100])
r = A.respond("fix them")
check("'fix them' → labels / reorder proposals / drafts in one go", isinstance(r, str) and (r.startswith("On it") or r.startswith("There's nothing broken")), (r or "")[:100])
r = A.respond("customer says the mug arrived broken, photo attached")
check("forwarded customer sentence without 'what do I answer' → inbox draft + asks for the photo", r is None and "photo" in A.bot.sent[-1][0].lower(), A.bot.sent[-1][0][:100])
r = A.respond("does temu sell the cork case cheaper?")
check("'does temu sell X cheaper?' is a lookup, not a rule of thumb", isinstance(r, str) and ("look it up" in r or "What I understood" in r), (r or "")[:80])
for _ in range(240):                                                 # that lookup runs as a (fake) job — let it finish
    if not A.busy and not A.mind.job:
        break
    time.sleep(0.5)
else:
    A.busy = None; A.mind.job = None                                 # safety reset: a slow sandbox must not fail the next checks
A.last_brief = None; A.mind.queue.clear()
A.domain_check = lambda dom: f"stub {dom}"
r = A.respond("can you check if the domain greennest.it is free?")
check("'is the domain greennest.it free?' → registry lookup (no browser job)", r == "stub greennest.it", r)

# while busy: quick things are answered live, real requests are queued
import threading
for _ in range(120):                                              # the shop-read thread from 'open the practice store' must be over first
    if not A.busy:
        break
    time.sleep(0.5)
A.mind.queue.clear()
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
