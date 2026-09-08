"""Questions about ME and about judgment — answered from what the agent actually knows about itself and the shop:

    "what are you doing right now?"           → the running job / idle state, honestly
    "why did you propose lowering the mug?"    → the proposal's own 'why' from the ledger
    "what would you change about the shop?"    → concrete list from the numbers (stock-outs, late orders, thin margins…)
    "if you were me, what would you do first?" → the first thing, with the reason
    "explain the numbers like I'm 5"           → the shop's P&L in a child's words
    "we made 300 euros this week, is that good?" → judged against the shop's own costs
    "how much would we make if we doubled the traffic?" → conversion × basket, honestly caveated
    "what's the plan for next week?"           → from to-dos, stock, proposals
    "can you handle the shop alone for a week?" → what I do alone, what needs the owner's tap

No model, no browsing. SelfTalk(store, inbox, memory, mind, pace, tasks_stats).reply(text) → str or None.
"""
import datetime as _dt
import re


def _eur(x):
    return f"€ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _num(s):
    return float(str(s).replace(".", "").replace(",", ".")) if re.search(r"\d\.\d{3}\b", str(s)) else float(str(s).replace(",", "."))


class SelfTalk:
    def __init__(self, store=None, inbox=None, memory=None, mind=None, pace=None, version=""):
        self.store = store
        self.inbox = inbox
        self.memory = memory
        self.mind = mind
        self.pace = pace
        self.version = version
        self.busy_text = lambda: None          # core sets this to a function returning Agent.busy

    RULES = [
        (r"^\W*(?:what are you (?:doing|up to|working on)(?: right now| now| at the moment)?|what(?:'s| is) (?:going on|happening)(?: right now| now)?|are you busy|cosa stai facendo|che fai(?: adesso)?)\W*$", "doing_now"),
        (r"\bwhy did you (?:propose|suggest|want to|recommend|prepare)\b(?P<what>.{3,80})|\bwhy (?:the|that|this) (?:proposal|suggestion|change)\b|\bperché hai proposto\b(?P<what2>.{3,80})", "why_proposal"),
        (r"\bwhat (?:happens|will happen|if) (?:if )?i (?:ignore|don't (?:answer|tap|approve|look at)|skip|leave) (?:the |your )?(?:proposals?|suggestions?|buttons?|questions?)\b|\bcan i ignore (?:the |your )?proposals\b", "ignore_proposals"),
        (r"\bwhat would you (?:change|improve|fix|do differently)\b.{0,30}?\b(?:shop|store|business|site|negozio|catalogue|catalog)\b|\bcosa cambieresti\b|\bwhat(?:'s| is) (?:wrong|broken|weak|missing) (?:with|in|about) (?:the |our |my )?(?:shop|store|business)\b|\bwhat are we doing wrong\b|\bwhere are we (?:weak|losing)\b", "what_change"),
        (r"\bif you were me\b|\bwhat would you do (?:first|today|now|in my (?:place|shoes))\b|\bwhat should i do first\b|\bal posto mio\b|\bwhat(?:'s| is) the (?:first|one) thing (?:i should|to) (?:do|fix)\b", "do_first"),
        (r"\b(?:biggest|main|real|top) (?:risk|danger|threat|problem|worry)s?\b.{0,20}?\b(?:for us|right now|now|for the shop|we have|today)\b|\bwhat (?:worries|scares) you\b|\bwhat could go wrong\b|\bqual è il rischio\b", "biggest_risk"),
        (r"\bwhat do you need from me\b|\bwhat do you need me (?:to do|for)\b|\bdo you need (?:anything|something) from me\b|\banything you need\b|\bdi cosa hai bisogno\b|\bcosa ti serve\b", "need_from_owner"),
        (r"\bexplain (?:the |our |these )?(?:numbers|figures|profit|report|results|margin|p&l|stats)\b.{0,30}?\b(?:like i'?m (?:5|five|a child|stupid|new)|simply|simple|in plain (?:words|english)|for dummies|slowly)\b|\b(?:numbers|figures) (?:in plain|simply|simple)\b|\bspiegami i numeri\b|\bi don'?t understand (?:the |these )?numbers\b", "eli5"),
        (r"\b(?:is|are) (?P<pct>\d+(?:[.,]\d+)?)\s*%?\s*(?:percent )?conversion (?:rate )?(?:good|bad|ok|okay|normal|fine|high|low|enough)\b|\bconversion (?:rate )?(?:of )?(?P<pct2>\d+(?:[.,]\d+)?)\s*%?\s*(?:—|-|,)?\s*(?:is that )?(?:good|bad|ok|normal|fine)\b", "conv_good"),
        (r"\bhow much (?:should|do) i (?:put|set|keep|save) (?:aside|away|apart)\b.{0,20}?\b(?:tax|taxes|tasse|the taxman|vat|iva|inps)\b|\bset aside for tax", "tax_aside"),
        (r"\bshould (?:i|we) hire\b|\bdo (?:i|we) need (?:an? )?(?:employee|assistant|help|someone|va|virtual assistant)\b|\bhire (?:someone|a person|help|an assistant)\b|\bassumere\b|\bdevo assumere\b", "hire"),
        (r"\bwhat (?:can|could|will|do) you do (?:for (?:the |my |our )?(?:shop|store|business)|today|tomorrow|this week)\b.{0,20}?\b(?:without me|alone|on your own|by yourself|while i'?m (?:away|out|at work))\b|\bwhat (?:can|could) you do (?:alone|on your own|by yourself|without me)\b|\bcosa (?:puoi|riesci a) fare da sol[oa]\b", "alone_today"),
        (r"\bcan you (?:handle|run|manage|look after|take care of|mind) (?:the |my |our )?(?:shop|store|business|everything)\b.{0,20}?\b(?:alone|by yourself|on your own|without me|for a (?:day|week|month)|while i'?m (?:away|on holiday|out))\b|\bcan i leave (?:the |you )?(?:shop|store)? ?(?:to|with) you\b|\bpuoi gestire (?:il |lo )?(?:negozio|shop) da sol[oa]\b", "handle_alone"),
        (r"\bhow do you (?:decide|choose|know|pick) (?:what|how) (?:to (?:answer|reply|say|write)|you (?:answer|reply))\b.{0,20}?\b(?:customers?|clienti|messages?|e-?mails?)\b|\bhow do you (?:answer|reply to|handle) (?:customers?|customer messages?|the inbox)\b|\bcome rispondi ai clienti\b", "how_answer"),
        (r"\bwhat do you do (?:when|if) (?:a )?customer (?:is|gets) (?:angry|rude|upset|furious|mad|aggressive)\b|\b(?:angry|rude|upset|furious) customers?\b.{0,20}?\b(?:what do you do|how do you|your approach)\b|\bcliente arrabbiato\b", "angry_customer"),
        (r"\bwhat do you know about (?:our|my|the) (?:customers|buyers|clients|clienti)\b|\bwho (?:are|is) (?:our|my) (?:customers|buyers|typical customer|audience)\b|\bwho buys from us\b|\bchi sono i nostri clienti\b", "know_customers"),
        (r"\bwhich (?:countries|markets|country|market) (?:should|could) we (?:sell|ship|open|go|expand) (?:to|in)? ?(?:next|now|first)?\b|\bwhere (?:should|could) we (?:expand|sell next|ship next)\b|\bnext (?:country|market) to (?:open|sell)\b|\bin quali paesi\b", "next_countries"),
        (r"\bwhat(?:'s| is) the plan for (?:next|this) (?:week|month)\b|\bplan for (?:next|this) week\b|\bwhat(?:'s| are) (?:we|you) (?:doing|going to do) (?:next|this) week\b|\bpiano per (?:la )?(?:prossima |questa )?settimana\b|\bnext week'?s plan\b", "week_plan"),
        (r"\b(?:summari[sz]e|sum up|recap|riassumi|riepiloga)\b.{0,15}?\b(?:the )?(?:last|past) (?P<n>\d+) days?\b|\b(?:last|past) (?P<n2>\d+) days? (?:in|summary|recap)\b|\bsummari[sz]e (?:the |this |last )?week\b", "summarize_days"),
        (r"\bhow (?:confident|sure|certain) are you\b|\bcan i trust (?:the |these |your )?(?:numbers|figures|data|report)\b|\bare (?:the |these |your )?numbers (?:right|correct|real|reliable|accurate)\b|\bquanto sei sicur[oa]\b", "confidence"),
        (r"\bwhat would a (?:good|great|normal|realistic|bad) (?:month|week|year|day) look like\b|\bwhat(?:'s| is) a (?:good|realistic) (?:month|week|target|goal)\b|\bwhat should we aim for\b|\bcosa sarebbe un buon mese\b", "good_month"),
        (r"\bwe (?:made|earned|took|did|sold|turned over)\s+(?:€|eur|euro)?\s*(?P<amt>\d+(?:[.,]\d+)?)\s*(?:€|eur|euros?|k)?\s+(?:this|last|in a|per|a|in one|of profit this|profit this|of sales this|in sales this)?\s*(?P<per>week|month|day|today|yesterday|settimana|mese)\b.{0,20}?\b(?:good|bad|ok|okay|normal|fine|enough|well|poor|decent|bene|buono)\b|\b(?:is|are)\s+(?:€|eur)?\s*(?P<amt2>\d+(?:[.,]\d+)?)\s*(?:€|eur|euros?)?\s+(?:a|per|in a|of profit a|of sales a)\s+(?P<per2>week|month|day)\s+(?:good|bad|ok|okay|normal|fine|enough|decent)\b", "is_amount_good"),
        (r"\b(?:how much|what) (?:would|could|will|do) we (?:make|earn|get|have|sell)\b.{0,30}?\b(?:if (?:we|i) )?(?:double|doubled|triple|tripled|halve|halved|10x|twice|two times|three times|\d+ ?x|\+\s*\d+ ?%|\d+ ?% more)\b.{0,15}?\b(?:traffic|visitors|visits|conversion|prices?|orders|sales|the shop)\b|\bif (?:we|i) (?:double|doubled|triple|tripled)\b.{0,15}?\b(?:traffic|visitors|visits|conversion|orders)\b.{0,30}?\b(?:how much|what|profit|make|earn)\b|\bdoubl(?:e|ing) (?:the )?(?:traffic|visitors|visits)\b", "what_if_traffic"),
        (r"\bwhat did you learn (?:this week|today|lately|recently|so far|from (?:the|your) (?:last )?jobs?)\b|\bwhat have you learn(?:ed|t)\b|\bcosa hai imparato\b|\banything (?:new )?you learn(?:ed|t)\b", "learned"),
    ]

    JOB_WORDS = re.compile(r"https?://|\b(research|compare|look up|write me a (?:doc|document|report)|document about)\b", re.I)

    def reply(self, t):
        low = t.lower().strip()
        if self.JOB_WORDS.search(low):
            return None
        for pat, name in self.RULES:
            m = re.search(pat, low, re.I)
            if m:
                try:
                    r = getattr(self, name)(t, m)
                except Exception:
                    r = None
                if r:
                    return r
        return None

    # ---- helpers --------------------------------------------------------------------------------
    def _n(self):
        try:
            return self.store.numbers()
        except Exception:
            return None

    def _paid(self, days=None):
        try:
            day = self.store.data.get("day", 0)
            return [o for o in self.store.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and (days is None or o.get("day", 0) > day - days)]
        except Exception:
            return []

    def _facts(self):
        """The shop's state as short facts, each tagged good/bad/neutral — reused by several answers."""
        st = self.store
        out = []
        if st is None:
            return out
        n = self._n() or {}
        day = st.data.get("day", 0)
        paid = self._paid()
        oos = [p for p in st.products() if p["stock"] == 0]
        low = [p for p in st.products() if 0 < p["stock"] <= 3]
        late = [o for o in st.data["orders"] if o["status"] == "paid" and day - o.get("day", day) >= 1]
        open_ = [o for o in st.data["orders"] if o["status"] == "paid"]
        props = [p for p in st.data.get("proposals", []) if p["status"] == "open"]
        new = []
        try:
            new = self.inbox.items("new") if self.inbox is not None else []
        except Exception:
            pass
        units = n.get("units", {})
        if oos:
            out.append(("bad", "sold out: " + ", ".join(p["name"].split(" (")[0] for p in oos) + " — every visitor who wanted one leaves", "restock"))
        if late:
            out.append(("bad", f"{len(late)} paid order(s) waiting longer than the promised next-day shipping", "ship"))
        elif open_:
            out.append(("neutral", f"{len(open_)} order(s) to ship today", "ship"))
        if new:
            out.append(("bad", f"{len(new)} customer message(s) unanswered", "inbox"))
        if low:
            out.append(("neutral", "low stock: " + ", ".join(f"{p['name'].split(' (')[0]} ({p['stock']})" for p in low), "reorder"))
        if props:
            out.append(("neutral", f"{len(props)} proposal(s) waiting for your tap", "proposals"))
        if paid:
            rev = n.get("revenue", 0)
            margin = n.get("profit", 0) / rev * 100 if rev else 0
            out.append(("good" if margin >= 40 else "bad", f"net margin {margin:.0f} % after goods, shipping and fees" + ("" if margin >= 40 else " — thin"), "margin"))
            conv = n.get("conversion", 0)
            out.append(("good" if conv >= 1.5 else "bad", f"conversion {conv:.1f} % ({len(paid)} orders from {n.get('visits', 0)} visits)" + ("" if conv >= 1.5 else " — under the 1.5–3 % a small shop should see"), "conversion"))
            if len(units) >= 2:
                top = max(units.values()); share = top / sum(units.values())
                if share > 0.6:
                    out.append(("bad", f"one product is {share * 100:.0f} % of sales — a supplier hiccup stops the shop", "diversify"))
            emails = {}
            for o in paid:
                k = (o.get("customer") or {}).get("email") or str(o["n"])
                emails[k] = emails.get(k, 0) + 1
            rep = sum(1 for v in emails.values() if v > 1)
            if len(paid) >= 8:
                out.append(("bad" if not rep else "good", f"{rep} repeat buyer(s) out of {len(emails)} customers" + (" — nothing brings people back yet (no card in the parcel, no e-mail after 3 weeks)" if not rep else ""), "repeat"))
        else:
            out.append(("neutral", "no sales yet — the shop hasn't had a practice day", "run"))
        return out

    # ---- answers --------------------------------------------------------------------------------
    def doing_now(self, t, m):
        busy = None
        try:
            busy = self.busy_text()
        except Exception:
            pass
        if self.mind is not None and self.mind.job:
            return self.mind.status_line()
        if busy:
            return f"Right now: {busy}. Nothing else in the queue — ask me anything, quick things I answer alongside."
        bits = ["Nothing running — I'm waiting for you"]
        try:
            n = len(self.inbox.items("new")) if self.inbox is not None else 0
            if n:
                bits.append(f"{n} customer message(s) have drafts waiting for your tap")
        except Exception:
            pass
        try:
            props = [p for p in self.store.data.get("proposals", []) if p["status"] == "open"]
            if props:
                bits.append(f"{len(props)} store proposal(s) waiting")
        except Exception:
            pass
        try:
            items = self.memory.open_items() if self.memory else []
            if items:
                bits.append(f"{len(items)} thing(s) on your to-do list")
        except Exception:
            pass
        if self.pace is not None and getattr(self.pace, "has_quiet_time", lambda: False)():
            bits.append("you said you're away, so between checks I read and self-train")
        return "; ".join(bits) + ". Say the word and I start something."

    def why_proposal(self, t, m):
        st = self.store
        if st is None:
            return None
        what = (m.groupdict().get("what") or m.groupdict().get("what2") or "").strip(" ?.")
        props = list(reversed(st.data.get("proposals", [])))
        if not props:
            return "I haven't proposed anything for the shop yet — when I do, each proposal carries its reason and you see it before you tap."
        p = None
        prod = st.find_product(what) if what else None
        kind = ("price" if re.search(r"\b(price|lower|raise|cheaper|dearer|prezzo)\b", what) else "stock" if re.search(r"\b(stock|restock|reorder)\b", what) else
                "ship" if re.search(r"\b(ship|spedire)\b", what) else "refund" if "refund" in what else "cancel" if "cancel" in what else None)
        for x in props:
            if prod and str(x.get("target")) == prod["id"] and (kind is None or x["kind"] == kind):
                p = x; break
        if p is None:
            for x in props:
                if kind and x["kind"] == kind:
                    p = x; break
        if p is None:
            p = props[0]
        name = (st.product(p["target"]) or {}).get("name") if p["kind"] in ("price", "stock", "cost", "description") else f"order #{p['target']}" if p["kind"] in ("ship", "refund", "cancel") else p["target"]
        status = {"open": "still waiting for your tap", "applied": "you applied it", "rejected": "you said no"}.get(p["status"], p["status"])
        extra = ""
        if p["kind"] == "price" and st.product(p["target"]):
            pr = st.product(p["target"])
            cost = pr.get("cost", 0)
            try:
                new = float(p["change"])
                extra = (f" The maths: at {_eur(new)} the margin is {(new - cost - 0.029 * new - 0.30) / new * 100:.0f} % after fees vs {(pr['price'] - cost - 0.029 * pr['price'] - 0.30) / pr['price'] * 100:.0f} % at {_eur(pr['price'])}"
                         + (" — I only trade margin when the numbers say conversion is the problem." if new < pr["price"] else " — more per sale, and a ,90 ending keeps it looking cheap."))
            except Exception:
                pass
        return (f"That proposal ({p['kind']} · {name} → {p['change'] if p['kind'] not in ('product', 'page') else '…'}), {p['t'][:10]} — my reason at the time: “{p['why']}”. Status: {status}." + extra +
                "\nIf the reason doesn't convince you, say no — I learn from the answer (I keep a note of which kinds you accept).")

    def ignore_proposals(self, t, m):
        st = self.store
        props = [p for p in st.data.get("proposals", []) if p["status"] == "open"] if st is not None else []
        return ("Nothing breaks — a proposal is a suggestion, the shop never changes without your tap. What happens by kind:\n"
                "• price / stock / page changes: stay as they are; the shop keeps selling at the old numbers.\n"
                "• 'mark shipped': the order stays 'paid' — after a day I count it as late and it shows in your check-ins; the customer is the one who feels it.\n"
                "• refunds / cancellations: the customer keeps waiting, which is the one thing that turns into a chargeback or a 1-star review — those I nag you about.\n"
                "• customer reply drafts: nothing is sent; the inbox counts them as unanswered.\n"
                + (f"Right now {len(props)} are open: " + "; ".join(f"{p['kind']} {p['target']}" for p in props[:4]) + ". " if props else "Right now nothing is open. ")
                + "If you'd rather I stopped asking about a kind of thing, tell me (“don't propose price changes”) and I keep to it.")

    def what_change(self, t, m):
        facts = self._facts()
        bad = [f for f in facts if f[0] == "bad"]
        neutral = [f for f in facts if f[0] == "neutral"]
        if not facts or (len(facts) == 1 and facts[0][2] == "run"):
            return ("Too early for a verdict — no sales yet. What I'd change before the first customer: real product photos (not supplier ones), a 'ships from Bergamo in 1 day' line on every product, "
                    "and a free-shipping threshold just above the average basket. Then run practice days and ask me again.")
        fixes = {"restock": "restock (say “what do I need to reorder?”)", "ship": "ship what's waiting today (say “print the shipping labels”)", "inbox": "answer the inbox (/inbox — drafts are ready)",
                 "reorder": "reorder before it hits zero", "proposals": "decide the open proposals (/store)", "margin": "raise the thin prices or the shipping fee",
                 "conversion": "fix the product page (photos, shipping cost visible early) before buying traffic", "diversify": "push a second product in posts this week", "repeat": "a card with a code in every parcel + one e-mail after 3 weeks"}
        out = ["What I'd change, in order:"]
        i = 1
        for f in bad + neutral:
            out.append(f"{i}. {f[1]} → {fixes.get(f[2], 'fix it')}")
            i += 1
            if i > 5:
                break
        good = [f for f in facts if f[0] == "good"]
        if good:
            out.append("What I would NOT touch: " + "; ".join(f[1] for f in good) + ".")
        out.append("Things outside the numbers I'd also do: one short video a day for 30 days, and product photos in real rooms — nothing else moves a small shop as much.")
        return "\n".join(out)

    def do_first(self, t, m):
        facts = self._facts()
        order = {"inbox": 0, "ship": 1, "restock": 2, "proposals": 3, "reorder": 4, "margin": 5, "conversion": 6, "diversify": 7, "repeat": 8, "run": 9}
        why = {"inbox": "a waiting customer is the only thing that gets worse by the hour (reviews, chargebacks); everything else can wait a day",
               "ship": "shipping late breaks the promise on your own page, and late parcels are 80 % of 'where is my order' mails",
               "restock": "a sold-out product still listed loses the buyers you already paid to attract",
               "proposals": "they're decisions I already prepared — 2 minutes of taps",
               "reorder": "supplier lead time is 1–3 weeks; ordering now avoids the stock-out",
               "margin": "every sale at a thin margin makes a refund hurt three times",
               "conversion": "more traffic on a page that doesn't convert is money burned",
               "diversify": "one product carrying the shop is a single point of failure",
               "repeat": "a returning customer costs nothing to acquire",
               "run": "without sales data every other decision is a guess"}
        act = {"inbox": "open /inbox and tap the drafts", "ship": "say “print the shipping labels”, then “all shipped”", "restock": "say “what do I need to reorder?” and order today",
               "proposals": "open /store and decide", "reorder": "say “order 20 more <product>”", "margin": "say “should I raise prices?” and I show which ones", "conversion": "say “why is nobody buying the <product>?”",
               "diversify": "say “which product should I push this week?”", "repeat": "say “write the thank-you card text”", "run": "say “run a practice day”"}
        cand = sorted([f for f in facts if f[0] != "good"], key=lambda f: order.get(f[2], 9))
        if not cand:
            return "If I were you: nothing is on fire, so I'd spend today on one thing that compounds — a 30-second video of the best seller in a real room, posted today. Everything else is running."
        f = cand[0]
        second = f"\nSecond: {cand[1][1]} → {act.get(cand[1][2], '')}." if len(cand) > 1 else ""
        return f"If I were you, first: {f[1]}. Why: {why.get(f[2], '')}. How: {act.get(f[2], '')}.{second}\nThen stop looking at numbers for the day and post something."

    def biggest_risk(self, t, m):
        facts = self._facts()
        st = self.store
        risks = []
        for f in facts:
            if f[2] == "diversify":
                risks.append(("Concentration: " + f[1] + ". If that supplier is late by two weeks, sales stop.", "have a second supplier's sample on the shelf; push a second product now"))
            if f[2] == "restock":
                risks.append(("Stock-outs: " + f[1] + ".", "reorder today and set 'ships in X days' instead of hiding the product"))
            if f[2] == "inbox":
                risks.append(("Unanswered customers: " + f[1] + " — that's where chargebacks and 1-star reviews come from.", "answer today, even with 'I'm on it, answer by tomorrow'"))
            if f[2] == "margin":
                risks.append(("Thin margins: " + f[1] + " — one refund eats three sales.", "raise the thin prices by 5–10 % or charge real shipping"))
        if st is not None:
            try:
                paid = self._paid()
                if paid and len({o.get("country") for o in paid}) == 1:
                    risks.append(("All sales from one country — one platform or courier problem there stops everything.", "open shipping to a second country and post in that language"))
            except Exception:
                pass
        if not risks:
            risks.append(("The usual small-shop killer: everything depends on you (the only person who ships, answers and posts). One sick week = a broken promise on every page.",
                          "a backup shipper (friend/family) with pre-printed labels, and my drafts so customers always get an answer"))
        risks = risks[:2] + [("Cash: stock is paid up front, sales come later; with € 1.000 in stock a slow month is felt at once.", "reorder in small batches, never more than 4–6 weeks of stock")]
        out = ["Biggest risks right now, in order:"]
        for i, (r, fix) in enumerate(risks, 1):
            out.append(f"{i}. {r} → {fix}.")
        out.append("Not a risk today: legal basics (pages are honest), payment fraud (small tickets), competition (they don't know you exist yet).")
        return "\n".join(out)

    def need_from_owner(self, t, m):
        st = self.store
        needs = []
        try:
            new = self.inbox.items("new") if self.inbox is not None else []
            if new:
                needs.append(f"tap the {len(new)} customer reply draft(s) in /inbox")
        except Exception:
            pass
        try:
            props = [p for p in st.data.get("proposals", []) if p["status"] == "open"]
            if props:
                needs.append(f"decide the {len(props)} store proposal(s) (/store)")
            day = st.data.get("day", 0)
            open_ = [o for o in st.data["orders"] if o["status"] == "paid"]
            if open_:
                needs.append(f"ship {len(open_)} order(s) — I print the labels, you hand the parcels to GLS")
            oos = [p for p in st.products() if p["stock"] == 0]
            if oos:
                needs.append("order stock for " + ", ".join(p["name"].split(" (")[0] for p in oos) + " (money leaves your account, so that's yours)")
        except Exception:
            pass
        try:
            items = self.memory.open_items() if self.memory else []
            due = [x for x in items if x.get("due") and x["due"][:10] <= _dt.date.today().isoformat()]
            if due:
                needs.append(f"{len(due)} reminder(s) came due: " + "; ".join(re.sub(r" \(⏰ .*\)$", "", x["text"])[:40] for x in due[:2]))
        except Exception:
            pass
        always = ("Standing needs: a tap on anything that costs money, goes public or reaches a customer — I prepare, you approve. "
                  "Real product photos from you (I can't take them). And when you're away, tell me for how long — I plan around it.")
        if not needs:
            return "Nothing right now — no taps pending, nothing to ship, no stock at zero. " + always
        return "From you, today:\n" + "\n".join(f"• {x}" for x in needs) + "\n" + always

    def eli5(self, t, m):
        n = self._n()
        if not n or not n.get("orders"):
            return ("Like you're five: the shop is a lemonade stand. Nobody has bought lemonade yet, so there are no numbers to explain — "
                    "say “run a practice day” and pretend-customers come, then I explain what happened with real figures.")
        rev, cogs, ship, fees, profit = n["revenue"], n["cogs"], n["shipping_cost"], n["fees"], n["profit"]
        per = profit / n["orders"] if n["orders"] else 0
        return (f"Like you're five, with the real numbers:\n"
                f"• People gave us {_eur(rev)} for {n['orders']} orders — that's the money in the jar. 🫙\n"
                f"• But we had to buy the things first: {_eur(cogs)} went to the people who make them. 📦\n"
                f"• The postman wants money to carry the boxes: {_eur(ship)}. 🚚\n"
                f"• The card machine takes a tiny bite of every payment: {_eur(fees)}. 💳\n"
                f"• What's left in the jar is ours: {_eur(profit)} — about {_eur(per)} for every order" + (f", or {profit / rev * 100:.0f} cents of every euro." if rev else ".") + "\n"
                f"• {n['visits']} people looked in the window and {n['orders']} came in — {n['conversion']:.1f} out of 100. Normal for a small shop is 1 to 3.\n"
                + ("Bigger jar = more people looking in the window (posts, videos) or a bigger basket (bundles, free shipping over a number)." if n["conversion"] >= 1.5 else
                   "Fewer than 1–2 in 100 buy, so the window needs work before inviting more people: photos and the shipping price shown early."))

    def conv_good(self, t, m):
        pct = _num(m.group("pct") or m.group("pct2"))
        n = self._n() or {}
        mine = f" Yours is {n['conversion']:.1f} % so far." if n.get("orders") else ""
        if pct >= 5:
            verdict = f"{pct:g} % is excellent — above what most shops ever see (the average sits at 2–3 %). Check it's real: a small number of visits makes the % jump around; trust it after 500+ visits."
        elif pct >= 2.5:
            verdict = f"{pct:g} % is good — right at or above the 2–3 % average for online shops; for a new small shop it's very good."
        elif pct >= 1.5:
            verdict = f"{pct:g} % is normal — fine for a small shop. Gains come from the checkout (shipping cost visible early) and product photos, not from more traffic."
        elif pct >= 0.8:
            verdict = f"{pct:g} % is low but not broken — typical when traffic comes from cold ads or the shipping fee surprises people at checkout. Fix the page before buying more visitors."
        else:
            verdict = f"{pct:g} % is a problem — under 1 in 100 buys. Usually: wrong traffic (curious, not buyers), a price/shipping shock at checkout, or photos that don't sell. Fix before spending a euro on ads."
        return verdict + mine + " Two things to remember: mobile converts about half of desktop, and returning visitors convert 2–3× first-timers — so a newsletter box beats another ad."

    def tax_aside(self, t, m):
        n = self._n() or {}
        rev = n.get("revenue", 0)
        base = ("In regime forfettario (the normal start in Italy): put aside about 15 % of what comes in — that covers the 5 % flat tax on 40 % of turnover (≈ 2 % of sales) plus the INPS contributions, which are the real bill "
                "(a fixed ~€ 4.600/yr, ~€ 3.000 with the 35 % reduction, whatever you sell). ")
        if rev:
            base += f"On your {_eur(rev)} so far that's about {_eur(rev * 0.15)} set aside" + (f"; the INPS minimum alone is € 250/month, so under ~€ 1.700 of monthly sales the fixed part dominates." if rev < 1700 else ".")
        base += (" Outside forfettario (ordinary regime): set aside 22 % VAT on every sale (it's not your money) plus ~30 % of the profit for IRPEF and INPS. "
                 "Do it weekly into a separate account — never at the deadline. Ask a commercialista once (€ 300–600 for the set-up) — this is the one place where I want you to double-check me.")
        return base

    def hire(self, t, m):
        n = self._n() or {}
        paid = self._paid(7)
        wk = len(paid)
        return ("Hire someone? Not yet, by the numbers: " + (f"{wk} orders this week" if wk else "no steady orders yet") + " is about 20–40 minutes of packing a day — I already draft the customer replies, "
                "the labels and the posts, so your own time goes into packing and photos.\n"
                "When it starts to make sense: (1) 15+ parcels a day every day → a fulfilment service (from ~€ 2–3/order, no salary, no contract) before an employee; "
                "(2) you're turning down things that would grow sales (videos, a second channel) because of packing → a part-timer 2 h/day or a family member paid per parcel (€ 1–2); "
                "(3) customer messages > 30/day → a support person, but I handle drafts up to far more than that.\n"
                "In Italy an employee costs about 1,5–1,7× the net salary (contributions + TFR), so a € 800 net part-timer is ~€ 1.300/month — that needs ~€ 4.000/month extra margin. "
                "Rule of thumb: hire when you can pay 3 months of it from the last 3 months' profit. Ask me “are we profitable?” and you have the base number.")

    def alone_today(self, t, m):
        facts = self._facts()
        st = self.store
        do, ask = [], []
        for f in facts:
            if f[2] == "inbox":
                do.append(f"draft the replies to the {f[1].split(' ')[0]} waiting customer message(s) (sent after your tap)")
            if f[2] == "ship":
                do.append("print today's shipping labels and the packing slips, and mark the orders once you say they've gone")
            if f[2] == "restock":
                ask.append("the reorder — I compute the quantities, the purchase is yours")
            if f[2] == "proposals":
                ask.append("the open proposals — 10 seconds each")
        do += ["watch the store: new orders, messages, stock — and ping you only for the urgent ones",
               "prepare today's post (photo pick + caption) for your tap",
               "look at the week's numbers and put one concrete suggestion in the evening report",
               "study one thing the shop needs (I keep a list: packaging, the German market, ads) and file the useful part in Drive"]
        out = ["Today, without you, I can:"] + [f"• {x}" for x in do]
        if ask:
            out.append("What still needs your tap: " + "; ".join(ask) + ".")
        out.append("If you'd like me to go further while you're out — e.g. send routine replies myself (tracking, product questions) — say so once and I keep to exactly that.")
        return "\n".join(out)

    def handle_alone(self, t, m):
        return ("Mostly yes — with the rules you set. Alone I can: answer every customer within the hour with a draft that follows the policies (but the reply goes out only after your tap — "
                "if you want me to send the routine ones myself while you're away, say “send routine replies yourself” and I'll do just tracking/returns-info/product questions, never refunds or arguments); "
                "watch orders and print labels; keep the stock numbers right; post the day's post (again: after a tap, unless you pre-approve a week of posts before you go); "
                "run the numbers and send you an evening report; study when nothing is happening.\n"
                "What I can't do alone: physically ship (a friend with pre-printed labels solves it), decide money (refunds, reorders, price changes — I prepare, you tap, 10 seconds each from the phone), "
                "and phone calls with couriers.\n"
                "So a week away looks like: 10 minutes of taps a day from your phone, plus someone who drops parcels at GLS. Tell me the dates and I'll put the 'orders ship on <date>' note up if there's no shipper.")

    def how_answer(self, t, m):
        return ("How I decide what to answer a customer:\n"
                "1. I sort the message: where-is-my-order, return/refund, damaged/wrong item, product question, cancel/change, complaint, discount request, compliment, or 'other'.\n"
                "2. I look up what I'm allowed to know: the order (status, tracking, dates — only if the e-mail matches the order), the shop's own pages (shipping, returns, product details) — never anything I'd have to invent.\n"
                "3. I write the draft from a template for that kind, filled with the real facts, in the customer's language, and I run checks: no promises the policy doesn't make, no refund amount unless the policy gives it, "
                "no 'sorry' for things that aren't our fault without a fix attached, nothing about another customer's order.\n"
                "4. If a fact is missing (their order number, a photo of the damage) the draft asks for it instead of guessing.\n"
                "5. You get the draft with Approve / Edit / Reject. Nothing leaves without your tap; when you edit, I keep the edit as a lesson for that kind of message.\n"
                "Refunds, damage and angry messages I flag so you see them first. Say “show me the drafts” or /inbox to see them.")

    def angry_customer(self, t, m):
        return ("An angry customer, my routine:\n"
                "1. Answer fast — within the hour if I can, even if the answer is “I'm looking into it, you'll hear from me by <time today>”. Silence is what makes it worse.\n"
                "2. No defence in the first line. First: what they feel and what I'll do. “I'm sorry — that shouldn't have happened, and I'll sort it out today.”\n"
                "3. Then the facts, short, from the order — never argue about tone, never quote policy at them in the first message.\n"
                "4. Offer the fix that costs us least and them nothing: replacement or refund, their choice, no return of a broken item.\n"
                "5. I flag it to you before sending — you always see angry ones first, and anything with money in it needs your tap anyway.\n"
                "6. Afterwards I note the cause (packaging? late shipping? photo vs reality?) so the same anger doesn't come back next week.\n"
                "Abuse or threats: one calm reply, then stop replying and tell you; nobody has to take insults, and a paper trail beats a fight.")

    def know_customers(self, t, m):
        paid = self._paid()
        if not paid:
            return "Nothing yet — no orders, so no customers to describe. Once there are, I can tell you where they buy from, what they buy together, basket size and repeat rate (never names in posts or documents)."
        st = self.store
        countries = {}
        for o in paid:
            countries[o.get("country", "?")] = countries.get(o.get("country", "?"), 0) + 1
        top_c = sorted(countries.items(), key=lambda x: -x[1])
        rev = sum(o["total"] for o in paid)
        aov = rev / len(paid)
        emails = {}
        for o in paid:
            k = (o.get("customer") or {}).get("email") or str(o["n"])
            emails[k] = emails.get(k, 0) + 1
        rep = sum(1 for v in emails.values() if v > 1)
        pairs = {}
        for o in paid:
            names = sorted({l["name"].split(" (")[0] for l in o["lines"]})
            if len(names) >= 2:
                k = " + ".join(names[:2]); pairs[k] = pairs.get(k, 0) + 1
        multi = len([o for o in paid if sum(l["qty"] for l in o["lines"]) > 1])
        days = {}
        for o in paid:
            days[o.get("day", 0)] = days.get(o.get("day", 0), 0) + 1
        return (f"Our customers so far ({len(emails)} people, {len(paid)} orders):\n"
                f"• Where: " + ", ".join(f"{c} {n} ({n / len(paid) * 100:.0f} %)" for c, n in top_c[:4]) + ".\n"
                f"• Basket: {_eur(aov)} on average; {multi} of {len(paid)} orders had more than one item" + (f"; the pair that shows up most: {max(pairs, key=pairs.get)}" if pairs else "") + ".\n"
                f"• Loyalty: {rep} came back" + (" — early days." if not rep else ".") + "\n"
                f"• Rhythm: {len(paid) / max(1, len(days)):.1f} orders per selling day.\n"
                "What I don't know and would like to: how they found us (no analytics on the practice store) and their age/gender — an eco home range usually sells to women 25–45 buying for the home or as gifts; "
                "I'd verify that with a one-question e-mail after delivery. Names and e-mails stay in the store — never in posts or documents.")

    def next_countries(self, t, m):
        paid = self._paid()
        st = self.store
        have = []
        try:
            have = [r[0] for r in st.ship_rules()]
        except Exception:
            pass
        countries = {}
        for o in paid:
            countries[o.get("country", "?")] = countries.get(o.get("country", "?"), 0) + 1
        best_other = sorted(((c, n) for c, n in countries.items() if c not in ("IT",)), key=lambda x: -x[1])
        out = ["Next countries, in order of sense for a small Italian eco-home shop:"]
        out.append("1. Germany + Austria first (if not already strong): biggest EU market for eco/home goods, they pay for quality, PayPal and invoice payment matter, GLS delivers in 4–6 days; pages in German double conversion there.")
        out.append("2. France: strong on design/home, needs French pages and French customer replies (I write both); Colissimo/GLS 4–6 days.")
        out.append("3. Netherlands/Belgium: small but easy — English is fine, iDEAL/Bancontact as payment methods help.")
        out.append("4. Spain: price-sensitive, later. Switzerland/UK: only after that — customs paperwork and € 20+ shipping kill baskets under € 60.")
        if best_other:
            out.append(f"Your own data agrees or not: outside Italy you already sold in " + ", ".join(f"{c} ×{n}" for c, n in best_other[:3]) + " — start where the orders already come from.")
        if have:
            out.append(f"Currently open at checkout: {', '.join(have)}. Say “open shipping to <country> at <price>” and I prepare the rule; “translate the shipping page into German” and I do the page.")
        out.append("One at a time: open, translate the 4 help pages, post twice a week in that language, look at the numbers after 30 days.")
        return "\n".join(out)

    def week_plan(self, t, m):
        facts = self._facts()
        st = self.store
        out = ["Plan for the week:"]
        i = 1
        for f in [x for x in facts if x[0] != "good"][:3]:
            out.append(f"{i}. {f[1].split(' — ')[0]} → " + {"restock": "reorder Monday", "ship": "ship daily before the GLS pickup", "inbox": "answer today", "reorder": "reorder mid-week", "proposals": "decide them Monday", "margin": "adjust prices Tuesday, watch till Sunday",
                                                                 "conversion": "product page fixes (photos, shipping line) by Wednesday", "diversify": "push the second product in every post", "repeat": "thank-you card in every parcel from Monday", "run": "run a practice week"}.get(f[2], "handle"))
            i += 1
        out.append(f"{i}. Content: 5 posts (Mon–Fri), one short video, all on the best seller and one 'second' product — say “what should I post today?” each morning.")
        out.append(f"{i + 1}. Friday: numbers — say “how's the week going?” — and one decision from them (price, stock or post), not five.")
        try:
            items = self.memory.open_items() if self.memory else []
            if items:
                out.append("Your to-do list feeds in: " + "; ".join(re.sub(r" \(⏰ .*\)$", "", x["text"])[:40] for x in items[:3]) + (f" (+{len(items) - 3})" if len(items) > 3 else "") + ".")
        except Exception:
            pass
        out.append("Me, in the gaps: draft replies within the hour, evening report at 20:00, one study session a day on what the shop needs (packaging, ads, the German market).")
        return "\n".join(out)

    def summarize_days(self, t, m):
        n_days = int(m.group("n") or m.group("n2") or 7)
        st = self.store
        if st is None:
            return None
        day = st.data.get("day", 0)
        paid = self._paid(n_days)
        if not st.data["orders"]:
            return f"Last {n_days} days: no shop activity yet — the practice store hasn't run. Say “run a practice day”."
        rev = sum(o["total"] for o in paid)
        cogs = sum(l["qty"] * l.get("cost", 0) for o in paid for l in o["lines"])
        ship = sum(2.9 + 0.35 * sum(l["qty"] for l in o["lines"]) for o in paid)
        fees = sum(0.029 * o["total"] + 0.30 for o in paid)
        profit = rev - cogs - ship - fees
        units = {}
        for o in paid:
            for l in o["lines"]:
                units[l["name"].split(" (")[0]] = units.get(l["name"].split(" (")[0], 0) + l["qty"]
        best = max(units, key=units.get) if units else "—"
        visits = sum(v for d, v in st.data.get("visits", {}).items() if int(d) > day - n_days)
        bad = [o for o in st.data["orders"] if o.get("day", 0) > day - n_days and o["status"] in ("refunded", "cancelled")]
        oos = [p["name"].split(" (")[0] for p in st.products() if p["stock"] == 0]
        line3 = ("Problems: " + "; ".join(x for x in [f"{len(bad)} refund/cancel" if bad else "", "sold out: " + ", ".join(oos) if oos else "", f"{len([o for o in st.data['orders'] if o['status'] == 'paid'])} to ship" if any(o["status"] == "paid" for o in st.data["orders"]) else ""] if x)) if (bad or oos or any(o["status"] == "paid" for o in st.data["orders"])) else "Problems: none open — nothing late, nothing sold out."
        return (f"Last {n_days} days in 3 lines:\n"
                f"1. {len(paid)} orders, {_eur(rev)} sales, {_eur(profit)} profit ({profit / rev * 100:.0f} %) from {visits} visits ({len(paid) / visits * 100 if visits else 0:.1f} % bought).\n"
                f"2. Best seller: {best} ({units.get(best, 0)} sold); " + (f"{len(units)} products sold in total." if units else "nothing else sold.") + "\n"
                f"3. {line3}")

    def confidence(self, t, m):
        n = self._n() or {}
        return ("Honest answer, in layers:\n"
                f"• Orders, sales, stock, per-country split: exact — they come straight from the shop's own ledger ({n.get('orders', 0)} orders counted, nothing estimated).\n"
                "• Costs of goods: as good as the cost you gave me per product; if a supplier price changed and you didn't tell me, the margin is off by that much.\n"
                "• Shipping cost per parcel and payment fees: practice figures (€ 2,90 + € 0,35/item; 2,9 % + € 0,30) — realistic for a small Italian shop but not your real contract. Give me the real rates and I use them.\n"
                "• Conversion: exact for the practice store; in a real shop it depends on the analytics being set up right.\n"
                "• Forecasts ('if we doubled traffic', 'a good month'): educated guesses from small numbers — right in direction, ±30 % in size until there are a few hundred orders.\n"
                "• Law and tax: rules of thumb I checked against Italian/EU sources this year — right for the common case, still ask a commercialista for your own situation.\n"
                "If a number matters for a money decision, ask me “show me the maths” and I lay it out line by line.")

    def good_month(self, t, m):
        st = self.store
        n = self._n() or {}
        paid = self._paid()
        aov = (n.get("revenue", 0) / n["orders"]) if n.get("orders") else 25.0
        margin = (n.get("profit", 0) / n["revenue"]) if n.get("revenue") else 0.5
        conv = n.get("conversion", 2.0) or 2.0
        fixed = 250 + 30 + 20                                    # INPS minimum/month, domain+tools, boxes
        rows = []
        for label, orders in (("a quiet month", 40), ("a good month", 120), ("a great month", 300)):
            rev = orders * aov
            prof = rev * margin - fixed - orders * 1.0
            visits_needed = f"{int(orders / (conv / 100)):,}".replace(",", ".")
            rows.append(f"• {label}: ~{orders} orders ({orders // 30}–{orders // 30 + 1} a day) → {_eur(rev)} sales, about {_eur(prof)} left after goods, shipping, fees, boxes and the INPS minimum; needs ~{visits_needed} visits at {conv:.1f} % conversion")
        return ("What a month looks like, with your own basket and margin (" + f"{_eur(aov)} per order, {margin * 100:.0f} % net):\n" + "\n".join(rows) +
                "\nA 'good month' for a one-person shop is the middle one: it pays the taxman and leaves a real part-time income; the top one is where hiring/fulfilment questions start. "
                "The lever behind all three is visits — say “how do I get my first 100 followers?” or “ads budget?” for how.")

    def is_amount_good(self, t, m):
        amt = _num(m.group("amt") or m.group("amt2"))
        per = (m.group("per") or m.group("per2") or "week").lower()
        per_days = {"week": 7, "settimana": 7, "month": 30, "mese": 30, "day": 1, "today": 1, "yesterday": 1}.get(per, 7)
        n = self._n() or {}
        margin = (n.get("profit", 0) / n["revenue"]) if n.get("revenue") else 0.5
        sales_word = bool(re.search(r"\b(sales|turnover|sold|revenue|fatturato|venduto)\b", t.lower()))
        profit = amt if (not sales_word and re.search(r"\bprofit\b", t.lower())) else amt * margin
        month_profit = profit / per_days * 30
        fixed = 250 + 50
        if month_profit < fixed:
            verdict = f"For a start it's fine — for a business not yet: about {_eur(month_profit)} of profit a month (at your {margin * 100:.0f} % margin) doesn't yet cover the fixed bills (~{_eur(fixed)}: INPS minimum, domain, boxes)."
        elif month_profit < 1000:
            verdict = f"Good for month one or two: ~{_eur(month_profit)} profit a month (at your {margin * 100:.0f} % margin) covers the fixed bills and leaves pocket money. The next step is 3× that, which is traffic, not a new product."
        elif month_profit < 2500:
            verdict = f"Genuinely good: ~{_eur(month_profit)} profit a month is a real part-time income from a one-person shop."
        else:
            verdict = f"Very good: ~{_eur(month_profit)} profit a month — that's full-time money; start thinking about fulfilment and a second channel."
        kind_w = "profit" if (not sales_word and "profit" in t.lower()) else "sales"
        per_w = {"settimana": "week", "mese": "month", "today": "day", "yesterday": "day"}.get(per, per)
        return (f"{_eur(amt)} of {kind_w} in a {per_w}: {verdict} "
                f"Benchmarks: a new small shop typically does € 200–800 of sales a week in months 1–3; € 2.000+ a week by month 6 is a strong one. "
                "What matters more than the number: is it growing week on week (say “how are we doing compared to last week?”), and is the margin holding.")

    def what_if_traffic(self, t, m):
        n = self._n() or {}
        if not n.get("orders"):
            return "No sales data yet, so I'd be inventing it — run a few practice days and ask again; then I answer from the real conversion and basket."
        low = t.lower()
        factor = 2.0
        if re.search(r"\btripl|3 ?x|three times\b", low):
            factor = 3.0
        elif re.search(r"\bhalv", low):
            factor = 0.5
        elif re.search(r"\b10 ?x\b", low):
            factor = 10.0
        mp = re.search(r"\+?\s*(\d+)\s*%", low)
        if mp:
            factor = 1 + int(mp.group(1)) / 100
        what = "conversion" if "conversion" in low else "prices" if re.search(r"\bprices?\b", low) else "traffic"
        rev, orders, profit, visits = n["revenue"], n["orders"], n["profit"], n["visits"]
        aov = rev / orders
        unit_margin = profit / orders
        if what == "traffic":
            new_orders = orders * factor
            new_profit = new_orders * unit_margin
            cav = ""
            if factor > 1:
                cav = (" Two honest caveats: extra visitors convert worse than the first ones (new traffic is colder), so plan for 70–80 % of that; and ads to double traffic cost money — "
                       f"at ~€ 0,30–0,60 a visit you'd spend {_eur(visits * (factor - 1) * 0.3)}–{_eur(visits * (factor - 1) * 0.6)} to get it, which is {'more than' if visits * (factor - 1) * 0.45 > (new_profit - profit) else 'less than'} the extra profit. Free traffic (videos, posts) is the same maths without the bill.")
            return (f"Doubling the traffic" if factor == 2 else f"Traffic × {factor:g}") + f": {visits} → {int(visits * factor)} visits at the same {n['conversion']:.1f} % conversion = ~{int(new_orders)} orders instead of {orders}, " \
                   f"~{_eur(new_orders * aov)} sales, ~{_eur(new_profit)} profit (was {_eur(profit)}) — every extra order brings about {_eur(unit_margin)}." + cav
        if what == "conversion":
            new_orders = orders * factor
            return (f"Conversion × {factor:g} ({n['conversion']:.1f} % → {n['conversion'] * factor:.1f} %) with the same {visits} visits: ~{int(new_orders)} orders, ~{_eur(new_orders * unit_margin)} profit (was {_eur(profit)}). "
                    "That's the cheapest growth there is — it costs page work, not ad money: shipping price shown before checkout, real photos, a review or two, free shipping over a threshold. Realistic gains are +30–50 %, not ×2, unless something is badly broken today.")
        # prices
        new_rev = rev * factor
        lost = 0.15 if factor <= 1.1 else 0.3 if factor <= 1.25 else 0.5
        return (f"Prices × {factor:g}: if nobody blinked, {_eur(rev)} → {_eur(new_rev)} of sales and all of the extra {_eur(new_rev - rev)} is profit (costs stay). "
                f"But some buyers walk: at +{(factor - 1) * 100:.0f} % expect to lose ~{lost * 100:.0f} % of orders — profit becomes ~{_eur((orders * (1 - lost)) * (unit_margin + aov * (factor - 1)))} vs {_eur(profit)} now. "
                + ("Still a win — small rises on products with no direct comparison usually pay." if (orders * (1 - lost)) * (unit_margin + aov * (factor - 1)) > profit else "Not worth it at that size — try +5–10 % on the best seller only."))

    def learned(self, t, m):
        bits = []
        try:
            if self.mind is not None:
                txt = self.mind.lessons_text(limit=4)
                if txt and not txt.startswith("No lessons"):
                    bits.append(txt)
        except Exception:
            pass
        try:
            notes = self.memory.notes(limit=6, days=7) if self.memory else []
            if notes:
                bits.append("📚 Notes this week: " + "; ".join(dict.fromkeys(f"{r['kind']}: {r['topic'][:40]}" for r in notes)))
        except Exception:
            pass
        try:
            n = self._n() or {}
            if n.get("orders"):
                units = n.get("units", {})
                best = max(units, key=units.get) if units else None
                bits.append(f"🏪 From the shop: {best.split(' (')[0]} sells most; conversion runs at {n['conversion']:.1f} %; " + ("net margin is healthy." if n["revenue"] and n["profit"] / n["revenue"] >= 0.4 else "margin needs watching.") if best else "")
        except Exception:
            pass
        bits = [b for b in bits if b]
        if not bits:
            return "Nothing new this week — no jobs finished, no study sessions. Give me a task or an away-window and I'll have something to report."
        return "\n".join(bits)
