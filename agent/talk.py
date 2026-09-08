"""Talk — the everyday questions an owner asks in plain words, answered directly (milestone 20 polish).

Before a message is turned into a job, this layer catches the things that need no browsing at all:

  • "what can you do?"                       → a short menu in plain words
  • "thanks, that's all" / "bye"             → a short goodbye, no menu, no job
  • "what did you do today?"                 → recap from the journal, lessons, notes and library
  • "how much should I charge for X that costs me Y?"  → the pricing maths (2.5× / 3× / 4×, fee, margin)
  • "is € 3.90 shipping too much for Italy?" → a grounded rule of thumb
  • "customer says … what do I answer?"      → treated as a customer message: a draft with Approve/Edit/Reject
  • "where do I start selling X online?"     → the standard first steps, offered as a to-do list

Everything here is rules + arithmetic; nothing is invented. Returns None when the message is not one of these,
so the normal understanding (brief → plan → job) takes over.
"""
import datetime as _dt
import json
import re

_MONEY = r"(?:€|eur|euro|euros|\$|usd|£)?\s*(\d+(?:[.,]\d+)?)\s*(?:€|eur|euro|euros|\$|usd|£|k)?"


def _num(s):
    return float(s.replace(",", "."))


def _eur(x):
    return f"€ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class Talk:
    CAN_DO = re.compile(r"^\W*(what (can|could) you do|what do you do|what are you (able|good) (to|at)|how can you help|cosa (sai|puoi) fare|che cosa fai|what else can you do)\b", re.I)
    BYE = re.compile(r"^\W*((ok(ay)?|alright|great|perfect|cool|thanks?|thank you|grazie|ty|thx)[\s,!.]*)*(that'?s all( for now)?|bye|goodbye|see you|talk later|ciao|a dopo|good night|buonanotte|nothing else|no more for now|later)\b", re.I)
    THANKS = re.compile(r"^\W*(thanks?( you)?( a lot| so much)?|grazie( mille)?|ty|thx|perfect|great job|well done|nice work|good job)\W*$", re.I)
    TODAY = re.compile(r"\b(what (did|have) you (do|done|work(ed)? on|been up to)( today| so far| this morning)?|remind me what you did|recap( of)? (today|the day)|what happened today|cosa hai fatto( oggi)?|daily recap|summary of (today|your day))\b", re.I)
    PRICE = re.compile(r"\b(how much (should|can|do) i (charge|sell|price|ask)|what (price|should i charge)|(sell|retail) price for|quanto (dovrei|posso) (chiedere|far pagare)|a che prezzo)\b", re.I)
    COST = re.compile(r"\b(?:costs?(?: me)?|cost price|i pay|buy (?:it )?(?:for|at)|mi costa|pago)\s*" + _MONEY, re.I)
    SHIP_OK = re.compile(r"\b(?:is|are)\s*" + _MONEY + r"\s*(?:shipping|delivery|spedizione)\s*(?:too (?:much|expensive|high)|ok|fine|reasonable|fair|a lot)", re.I)
    CUSTOMER = re.compile(r"\b(?:a |the |my )?(?:customer|client|buyer|cliente)s?\s+(?:says?|wrote|writes|asks?|is asking|complain(?:s|ed)?|messaged|emailed|sent|dice|scrive|chiede)\b(?P<inner>.{0,400}?)(?:what (?:do|should|can) i (?:answer|reply|say|tell|write)|how (?:do|should) i (?:answer|reply|respond)|cosa (?:rispondo|gli dico|le dico)|what now)\b", re.I | re.S)
    START = re.compile(r"\b(where (do|should) i (start|begin)|how (do|should|can) i (start|begin|get started)|i want to (start|sell|open)|voglio (vendere|aprire|iniziare)|da dove (comincio|inizio|parto))\b", re.I)
    OPINION_IT = re.compile(r"\b(che ne pensi|cosa ne pensi|secondo te)\b", re.I)

    def __init__(self, memory=None, mind=None, library=None, inbox=None, store=None, log=None):
        self.memory = memory
        self.mind = mind
        self.library = library
        self.inbox = inbox
        self.store = store
        self.log = log or (lambda kind, **f: None)

    # ---- entry --------------------------------------------------------------------------------
    GREET = re.compile(r"^\W*(hi|hello|hey|yo|ciao|buongiorno|buonasera|good (morning|afternoon|evening)|morning|evening)\b[\s,!.]*(there|bot|mate|man)?[\s,!.]*(how'?s it going|how are you|how are things|what'?s up|come va|tutto bene|all good)?\W*$", re.I)

    def reply(self, text):
        """The direct answer, or a dict {"customer": <their message>} / {"todo": [...], "text": ...} for the agent to act on, or None."""
        t = (text or "").strip()
        if not t or t.startswith("/"):
            return None
        low = t.lower()
        if self.GREET.match(t):
            return self.greet()
        if self.CAN_DO.search(t):
            return self.can_do()
        if self.BYE.match(t) and len(low.split()) <= 8:
            return self.bye()
        if self.THANKS.match(t):
            return "You're welcome. I'm here when you need the next thing."
        if self.TODAY.search(t):
            return self.today()
        m = self.CUSTOMER.search(t)
        if m:
            return {"customer": self._customer_text(t, m)}
        if self.PRICE.search(t) or (self.COST.search(t) and re.search(r"\b(price|charge|sell|margin|markup|prezzo)\b", low)):
            p = self.pricing(t)
            if p:
                return p
        m = self.SHIP_OK.search(t)
        if m:
            return self.shipping_ok(_num(m.group(1)), t)
        if self.START.search(t) and re.search(r"\b(sell|selling|shop|store|online|business|vendere|negozio|dropship)", low):
            return self.start_plan(t)
        return None

    # ---- answers -------------------------------------------------------------------------------
    def can_do(self):
        shop = " · the practice shop (/store)" if self.store is not None else ""
        return ("Here's what I do, in plain words:\n"
                "• Look things up on the web and hand you a proper document (links, pictures, key points) — “research X, write me a document”\n"
                "• Check sellers deeply before you buy — page, reviews, social pages, complaints, shipping — “is this seller ok? <link>” or “find me reliable suppliers of X”\n"
                "• Compare suppliers side by side — “compare suppliers of X”\n"
                "• Read a page or a video for you — paste a link\n"
                "• Answer customers — forward me their message, I draft the reply, you approve\n"
                "• Draft social posts and rehearse posting on a practice network — “rehearse posting about X”\n"
                "• Build a full website for a business — “build a website for <place>” (and train on random real places)\n"
                "• Price things — “how much should I charge for X that costs me Y?”\n"
                "• Study on my own when you're away (PDFs, business videos → my Drive library)" + shop + "\n"
                "Pace words work: “make it quick, 10 minutes” or “I'm at work 5 hours, take it slow”. Say “stop” or “what are you doing?” any time.")

    def greet(self):
        """Hello with a one-line status: what's waiting, what I did last — so the owner knows where we stand."""
        hour = _dt.datetime.now().hour
        hello = "Good morning!" if 5 <= hour < 12 else "Good afternoon!" if 12 <= hour < 18 else "Good evening!"
        bits = []
        try:
            new = len(self.inbox.items("new")) if self.inbox else 0
            if new:
                bits.append(f"{new} customer message(s) wait for your tap (/inbox)")
        except Exception:
            pass
        try:
            from . import mind as _m
            last = (_m._load(_m.LESSONS) or [None])[-1]
            if last:
                bits.append(f"last job: {last.get('kind', '?')} “{last.get('goal', '')[:40]}” ({'done' if last.get('delivered') else 'not delivered'})")
        except Exception:
            pass
        try:
            n = len(self.memory.open_items()) if self.memory else 0
            if n:
                bits.append(f"{n} open to-do(s)")
        except Exception:
            pass
        return hello + " All good here." + (" " + " · ".join(bits) + "." if bits else "") + " What do you need — a search, a seller check, a document, a website, or just a question?"

    def bye(self):
        n = 0
        try:
            n = len(self.memory.open_items()) if self.memory else 0
        except Exception:
            pass
        tail = f" You have {n} open to-do(s); I'll keep studying quietly." if n else " I'll keep studying quietly and ping you only if something needs you."
        return "Alright — talk later." + tail

    def today(self):
        day = _dt.date.today().isoformat()
        parts = []
        try:
            from . import mind as _m
            jobs = [r for r in _m._load(_m.LESSONS) if r.get("t", "")[:10] == day]
            if jobs:
                parts.append(f"• {len(jobs)} job(s) finished: " + "; ".join(f"{j.get('kind', '?')} “{j.get('goal', '')[:50]}”" + ("" if j.get("delivered") else " (not delivered)") for j in jobs[-6:]))
            jl = [r for r in _m._load(_m.JOURNAL) if r.get("t", "")[:10] == day]
            if jl and not jobs:
                parts.append(f"• {len(jl)} step(s) worked today, last: {jl[-1].get('what', '')[:80]}")
        except Exception:
            pass
        try:
            docs = [d for d in (self.library.recent(20) if self.library else []) if str(d.get("t", ""))[:10] == day]
            if docs:
                parts.append("• documents written: " + "; ".join(d.get("title", "?")[:50] for d in docs[:5]))
        except Exception:
            pass
        try:
            notes = self.memory.notes(limit=30, days=1) if self.memory else []
            kinds = {}
            for r in notes:
                kinds.setdefault(r.get("kind", "note"), []).append(r.get("topic", ""))
            for k, topics in list(kinds.items())[:5]:
                parts.append(f"• {k}: " + "; ".join(dict.fromkeys(t[:40] for t in topics))[:160])
        except Exception:
            pass
        try:
            if self.inbox:
                new = len(self.inbox.items("new"))
                if new:
                    parts.append(f"• {new} customer message(s) waiting for your tap (/inbox)")
        except Exception:
            pass
        if not parts:
            return "Nothing finished yet today — no jobs, no documents. Give me something to do, or I'll study in the quiet time."
        return f"Today ({day}):\n" + "\n".join(parts)

    def pricing(self, text):
        m = self.COST.search(text)
        if not m:
            return None
        cost = _num(m.group(1))
        if cost <= 0:
            return None
        ship = 0.0
        ms = re.search(r"(?:shipping|delivery|postage|spedizione)\D{0,20}" + _MONEY, text, re.I)
        if ms:
            ship = _num(ms.group(1))
        landed = cost + ship
        rows = []
        for mult, label in ((2.5, "safe minimum for handmade / dropshipping"), (3.0, "typical"), (4.0, "premium / strong brand")):
            price = round(landed * mult + 0.49, 0) - 0.10          # X,90 style
            fee = price * 0.029 + 0.30
            profit = price - landed - fee
            rows.append(f"• {label}: sell at {_eur(price)} → after the ~2.9 % + € 0,30 payment fee you keep {_eur(profit)} per sale ({profit / price * 100:.0f} % margin)")
        item = re.search(r"\bfor (?:a |an |the )?([a-z][a-z \-]{2,40}?)(?: that| which| costing| cost| at| for|\?|$)", text, re.I)
        name = item.group(1).strip() if item else "it"
        return (f"Pricing {name} at a cost of {_eur(cost)}" + (f" + {_eur(ship)} shipping" if ship else "") + f" ({_eur(landed)} landed):\n" + "\n".join(rows) +
                "\n\nRule of thumb: 2.5–4× the landed cost; below 2× you can't absorb ads, returns and a discount. If competitors sell far below "
                f"{_eur(landed * 2.5)}, the product is the problem, not the price. Want me to check what others charge? Say “compare prices for {name}”.")

    def shipping_ok(self, amount, text):
        low = text.lower()
        it = re.search(r"\b(italy|italia|it)\b", low)
        eu = re.search(r"\b(eu|europe|germany|france|spain|europa)\b", low)
        if it or not eu:
            verdict = ("that's in the normal range — Italian shops typically charge € 3,90–6,90 for a parcel and go free above € 39–49." if 3 <= amount <= 7
                       else "that's cheap — most Italian shops charge € 3,90–6,90 (you may be subsidising it)." if amount < 3
                       else "that's on the high side — Italian shoppers expect € 3,90–6,90, or free above a threshold (€ 39–49 is common).")
        else:
            verdict = ("that's normal for EU delivery — € 6,90–9,90 is typical for a small parcel to Germany/France/Spain." if 5 <= amount <= 10
                       else "that's cheap for EU delivery — small parcels usually cost the shop € 6–9." if amount < 5
                       else "that's high for the EU — shoppers expect € 6,90–9,90 or free above ~€ 60.")
        return (f"{_eur(amount)} shipping: {verdict}\nWhat matters more than the number: show it before checkout, and offer a free-shipping threshold "
                "a bit above your average order — it lifts the basket size.")

    def start_plan(self, text):
        m = re.search(r"\b(?:sell|selling|vendere)\s+(?:my |our )?([a-z][a-z \-]{2,50}?)(?:\s+online|\s+on\b|\s*[,.?!]|$)", text, re.I)
        what = (m.group(1).strip() if m else "products")
        if what in ("products", "things", "stuff", "online"):
            what = "products"
        todo = [f"Pick 3–5 {what} to start with (not 30) and write one honest sentence per product" if what != "products" else "Pick one niche and 3–5 products to start with (not 30) — say “research product ideas for <niche>”",
                f"Find out what similar {what} sell for — say “compare prices for {what}”",
                f"Work out your prices: cost + shipping × 2.5–4 — say “how much should I charge for {what} that costs me …”",
                "Take clear photos on a plain background (phone is fine, daylight, 3 angles)",
                "Choose where to sell: your own shop (Shopify/WooCommerce/Etsy for handmade) — I can build the website",
                "Write the shipping + returns rules once (EU: 14-day withdrawal, 2-year guarantee) — I draft them",
                "Open the social pages and rehearse a first post with me before going live"]
        head = f"Starting to sell {what} online" if what != "products" else "Starting an online shop"
        return {"todo": todo, "text": f"{head} — here's the order I'd do it in, and I've put it on our to-do list:\n" +
                "\n".join(f"{i + 1}. {s}" for i, s in enumerate(todo)) + "\n\nTell me which step you want me to do first."}

    # ---- helpers -------------------------------------------------------------------------------
    def _customer_text(self, text, m):
        """Pull the customer's words out of 'a customer says the parcel arrived broken, what do I answer?'."""
        inner = m.group("inner").strip(" :,-–—\"“”'")
        quoted = re.search(r"[\"“«](.{8,400}?)[\"”»]", text)
        if quoted:
            return quoted.group(1).strip()
        inner = re.sub(r"^(that|me|us)\s+", "", inner, flags=re.I)
        return inner or text
