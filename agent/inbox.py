"""Customer messages & social posts — drafted by the AI, approved by the owner (milestone 5).

Nothing here sends anything by itself. The flow is:
   message arrives (state/inbox.jsonl)  →  classify (intent, urgency, facts needed)
   →  draft a reply from the store policy + knowledge  →  owner taps Approve / Edit / Reject on the phone
   →  approved text is handed to the channel adapter (for now: written to state/outbox.jsonl and shown)
Every decision is remembered (state/inbox_decisions.jsonl) and the score set tests/inbox.txt measures the drafts:
   correct intent, policy respected, right tone, no invented facts (order numbers, dates, refunds never promised).

Store policy lives in state/policy.json — the owner sets it once (/policy) and every draft obeys it.

Channels come later (email/IMAP, Shopify Inbox, Instagram/Facebook via official APIs); today's adapters:
   "practice" — sample messages loaded with /inbox practice, replies go to state/outbox.jsonl only.
"""
import datetime as _dt
import json
import re

from . import config

INBOX = config.STATE_DIR / "inbox.jsonl"
OUTBOX = config.STATE_DIR / "outbox.jsonl"
DECISIONS = config.STATE_DIR / "inbox_decisions.jsonl"
POLICY = config.STATE_DIR / "policy.json"

DEFAULT_POLICY = {
    "store_name": "our store",
    "owner_name": "",
    "tone": "friendly, short, honest; no exclamation marks in a row; never blame the customer",
    "shipping": "standard delivery 7-15 business days; tracking number sent by email when the parcel ships",
    "returns": "30 days from delivery for unused items; customer pays return shipping unless the item is faulty or wrong",
    "refunds": "refund issued within 5 business days after the returned item arrives; faulty/wrong items refunded or replaced at once, no return needed for items under 10 EUR",
    "ships_to": "",
    "products": "",
    "discounts": "no discount codes given out in chat; newsletter subscribers get 10% on the first order",
    "escalate": "legal threats, chargeback mentions, injuries or safety complaints, press/influencer requests, anything about personal data",
    "sign_off": "Best regards,\nCustomer care",
}

KINDS = ["where_is_my_order", "return_or_refund", "damaged_or_wrong", "product_question", "cancel_or_change",
         "discount_request", "complaint", "compliment", "spam_or_scam", "partnership_or_press", "other"]

CLASSIFY_PROMPT = """Classify a customer message for an online store. Reply with one JSON object only:
{"kind": KIND, "urgency": "low|normal|high", "needs": [facts the reply needs but the message doesn't give, e.g. "order number"], "escalate": true|false}
KIND is one of: %s
escalate=true when the message mentions lawyers, chargebacks, injury/safety, press/influencers, personal-data requests, or is abusive.
Message: """ % ", ".join(KINDS)

DRAFT_PROMPT = """You write replies to customers of a small online store on behalf of the owner.
STORE POLICY (obey exactly; never promise anything not covered here):
%s

RULES: plain, warm, 3-6 sentences, no bullet lists, no numbered steps. If the customer gave an order number, repeat it once
(e.g. "order 51410") so they know you have it; never mention any other number. You do NOT have access to orders, so you never know if a
parcel has shipped, where it is, or whether a cancellation is still possible: say what you will do ("I will check order 48213
and send you the tracking / options within one business day"). Never write placeholders like [tracking link] or [name]. Never
invent order numbers, dates, tracking numbers, prices or stock levels — if the reply needs a fact you don't have, ask the customer
for it. Never offer a refund, replacement or discount unless the policy above allows it for this exact situation. Apologise at
most once. Do not write a sign-off; it is added automatically.

CUSTOMER MESSAGE (%s, from %s):
%s

Write only the reply text. This is a new, unrelated conversation."""


def now():
    return _dt.datetime.now().isoformat(timespec="seconds")


def _append(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _load(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


class Inbox:
    def __init__(self, planner=None, brain=None, memory=None, log=None):
        self.planner = planner
        self.brain = brain
        self.memory = memory
        self.log = log or (lambda kind, **f: None)
        config.ensure_dirs()
        self.policy = self.load_policy()

    # ---- policy ------------------------------------------------------------
    def load_policy(self):
        try:
            p = json.loads(POLICY.read_text(encoding="utf-8"))
            return {**DEFAULT_POLICY, **p}
        except Exception:
            return dict(DEFAULT_POLICY)

    def set_policy(self, key, value):
        if key not in DEFAULT_POLICY:
            return f"Unknown policy field '{key}'. Fields: {', '.join(DEFAULT_POLICY)}"
        self.policy[key] = value
        POLICY.write_text(json.dumps(self.policy, ensure_ascii=False, indent=1), encoding="utf-8")
        return f"Policy updated: {key} = {value}"

    POLICY_HELP = {"ships_to": "countries you deliver to, e.g. 'EU countries, UK, Switzerland' (empty = I'll say the owner will confirm)",
                   "products": "facts about your products the AI may quote, e.g. 'LED lamp: 8 h battery, 3 brightness levels' (empty = I defer product questions to you)"}

    def policy_text(self):
        out = []
        for k, v in self.policy.items():
            if k == "sign_off":
                continue
            if k == "ships_to" and not v:
                out.append("ships_to: UNKNOWN — never state which countries we ship to; say the owner will confirm")
            elif k == "products" and not v:
                out.append("products: NO PRODUCT FACTS AVAILABLE — never state specifications, materials, sizes or battery life")
            else:
                out.append(f"{k}: {v}")
        return "\n".join(out)

    # ---- messages ------------------------------------------------------------
    def add(self, channel, sender, text, subject="", ref=None):
        existing = {r["id"] for r in _load(INBOX)}
        base = int(_dt.datetime.now().timestamp() * 1000) % 10 ** 8
        mid = ref or str(base)
        while mid in existing:
            base += 1
            mid = str(base)
        rec = {"id": mid, "t": now(), "channel": channel,
               "from": sender, "subject": subject, "text": text.strip(), "status": "new"}
        _append(INBOX, rec)
        return rec

    def items(self, status=None):
        rows = _load(INBOX)
        st = {}
        for d in _load(DECISIONS):
            st[d["id"]] = d["decision"]
        out = []
        for r in rows:
            r["status"] = st.get(r["id"], "new")
            if status is None or r["status"] == status:
                out.append(r)
        return out

    def get(self, mid):
        return next((r for r in self.items() if r["id"] == mid), None)

    # ---- understanding + drafting ----------------------------------------------
    def classify(self, text):
        low = text.lower()
        quick = None
        if re.search(r"\b(where is|where's|track|tracking|hasn't arrived|not arrived|still waiting|when will .* arrive|delivery status)\b", low):
            quick = "where_is_my_order"
        elif re.search(r"\b(broken|damaged|arrived (broken|damaged)|wrong (item|size|colou?r|product)|missing (part|item)|doesn't work|defective|faulty|came empty|box was open|package (was )?empty|nothing inside)\b", low):
            quick = "damaged_or_wrong"
        elif re.search(r"\b(return|refund|money back|send it back)\b", low):
            quick = "return_or_refund"
        elif re.search(r"\b(cancel|change (my|the) (order|address)|update .* address)\b", low):
            quick = "cancel_or_change"
        elif re.search(r"\b(discount|coupon|promo code|voucher|cheaper|\d+ ?% off|price match|bulk price)\b", low):
            quick = "discount_request"
        elif re.search(r"\b(physical (shop|store)|showroom|visit (your|the) (shop|store)|opening hours|where are you (based|located)|which country are you)\b", low):
            quick = "other"
        elif re.search(r"\b(collab\w*|influencer|sponsor\w*|followers|press|journalist|partnership|wholesale (inquiry|enquiry|order))\b", low):
            quick = "partnership_or_press"
        elif re.search(r"\b(seo services|guaranteed ranking|first page of google|crypto|bitcoin|earn \$|click here|verify your account|suspended)\b", low):
            quick = "spam_or_scam"
        elif re.search(r"\b(do you ship|ship to|shipping to|how long does|is it|does it|can it|what (size|material|colou?rs?)|how (big|heavy|many)|battery|compatible|waterproof|dimensions|in stock|available)\b", low) and "?" in text:
            quick = "product_question"
        elif re.search(r"\b(love|great|amazing|best purchase|thank you so much|thanks!)\b", low) and not re.search(r"\b(but|however|unfortunately|broken|late)\b", low):
            quick = "compliment"
        escalate = bool(re.search(r"\b(lawyer|attorney|legal action|sue|chargeback|dispute with my bank|injur|hurt|burn|fire|allerg|gdpr|delete my data|personal data)\b", low))
        needs = []
        if quick in ("where_is_my_order", "return_or_refund", "damaged_or_wrong", "cancel_or_change") and not re.search(r"#?\b\d{4,}\b", text):
            needs.append("order number")
        if quick == "damaged_or_wrong" and not re.search(r"\b(photo|picture|attached|image)\b", low):
            needs.append("photo of the damage")
        result = {"kind": quick or "other", "urgency": "high" if escalate or quick == "damaged_or_wrong" else "normal", "needs": needs, "escalate": escalate}
        if quick is None and self.planner and self.planner.installed():
            try:
                raw = self.planner.chat("You classify customer messages. Output JSON only.", CLASSIFY_PROMPT + json.dumps(text[:1200]), max_tokens=80, stop=["\n\n"])
                j = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
                if j.get("kind") in KINDS:
                    result["kind"] = j["kind"]
                result["urgency"] = j.get("urgency", result["urgency"]) if j.get("urgency") in ("low", "normal", "high") else result["urgency"]
                result["needs"] = list(dict.fromkeys(result["needs"] + [str(n) for n in j.get("needs", [])][:3]))
                if j.get("escalate") and re.search(r"\b(lawyer|legal|chargeback|bank|injur|hurt|rash|allerg|data|police|report|fraud|scam)\b", low):
                    result["escalate"] = True
            except Exception as e:
                self.log("classify_fallback", error=str(e)[:80])
        return result

    def draft(self, rec):
        """Draft a reply for one inbox record → dict(kind, urgency, escalate, needs, text, checks)."""
        c = self.classify(rec["text"])
        if c["kind"] == "spam_or_scam":
            return {**c, "text": "", "checks": [], "note": "no reply (spam)"}
        if c["escalate"] or c["kind"] == "partnership_or_press":
            hold = ("Thank you for your message. I am passing it to the owner personally, who will get back to you within one business day.\n\n"
                    + self.policy["sign_off"])
            return {**c, "text": hold, "checks": [], "note": "holding reply only — owner must handle this one"}
        facts = ""
        if c["kind"] == "product_question":
            about_shipping = bool(re.search(r"\b(ship|deliver|delivery|shipping)\b", rec["text"].lower()))
            have = (self.policy.get("ships_to") if about_shipping else self.policy.get("products")) or ""
            if not have.strip():                                            # nothing to answer from → defer, never guess
                text = self._sanitize(self._template(c))
                c["note"] = "no product/shipping facts in the policy — deferring to the owner (set them with /policy)"
                return {**c, "text": text, "checks": []}
            facts = have
        needs = ("\nMISSING FACTS you must ask the customer for: " + ", ".join(c["needs"])) if c["needs"] else ""
        if c["kind"] == "discount_request":
            needs += "\nTHIS IS A DISCOUNT REQUEST: state the discount policy plainly (no codes in chat; newsletter subscribers get 10% on the first order). Do not ask for an order number. Do not say 'sure' or 'I can help with that'."
        if c["kind"] == "return_or_refund" and re.search(r"\bafter \d+ days|\d+ days ago|too late\b", rec["text"].lower()):
            needs += "\nTHE CUSTOMER ASKS ABOUT THE RETURN WINDOW: state the window from the returns policy explicitly (30 days from delivery) and do not say 'of course'."
        extra = f"\nBACKGROUND FACTS you may use (do not quote sources): \n{facts}" if facts else ""
        text = None
        if self.planner and self.planner.installed():
            try:
                text = self.planner.chat("You are the customer-care writer of a small online store.",
                                         DRAFT_PROMPT % (self.policy_text() + needs + extra, c["kind"].replace("_", " "), rec.get("from", "customer"), rec["text"][:1500]),
                                         max_tokens=260, temperature=0.2, timeout=240)
            except Exception as e:
                self.log("draft_failed", error=str(e)[:100])
        if not text:
            text = self._template(c)
        text = self._sanitize(text)
        checks = self._check(text, c, rec["text"])
        if checks and self.planner and self.planner.installed():
            try:                                                           # one repair round with the problems spelled out
                fixed = self.planner.chat("You are the customer-care writer of a small online store.",
                                          DRAFT_PROMPT % (self.policy_text() + needs + extra, c["kind"].replace("_", " "), rec.get("from", "customer"), rec["text"][:1500])
                                          + f"\n\nYour previous draft was rejected because it: {'; '.join(checks)}. Write a corrected reply.",
                                          max_tokens=260, temperature=0.2, timeout=240)
                fixed = self._sanitize(fixed)
                if len(self._check(fixed, c, rec["text"])) < len(checks):
                    text, checks = fixed, self._check(fixed, c, rec["text"])
            except Exception:
                pass
        if checks:                                                          # still unsafe → the plain template (always policy-true)
            tmpl = self._sanitize(self._template(c))
            if not self._check(tmpl, c, rec["text"]):
                text, checks = tmpl, []
                c["note"] = "model draft failed the checks; using the safe template"
        return {**c, "text": text, "checks": checks}

    def _template(self, c):
        p = self.policy
        body = {
            "where_is_my_order": f"Thank you for reaching out, and sorry for the wait. Standard delivery takes {p['shipping'].split(';')[0].replace('standard delivery ', '')}. I will check your order and send you the tracking details within one business day" + ("." if not c["needs"] else " — could you send me your order number first?"),
            "return_or_refund": f"Thank you for your message. Our returns policy: {p['returns']}. {p['refunds'].split(';')[0].capitalize()}. Please send me your order number and I will start the return for you.",
            "damaged_or_wrong": "I am sorry your order did not arrive as it should. " + ("Please send me " + " and ".join(("your " + n) if n == "order number" else "a " + n for n in c["needs"]) + ", and I will sort out a replacement or refund straight away." if c["needs"] else "I will sort out a replacement or refund straight away and confirm the details within one business day."),
            "cancel_or_change": "Thank you for letting me know. I will check whether your order has already left the warehouse: if not, it will be cancelled and refunded; if it has, I will send you the return options. You will hear from me within one business day" + ("." if not c["needs"] else " — please send me your order number first."),
            "discount_request": f"Thank you for asking. {p['discounts'].split(';')[-1].strip().capitalize()}.",
            "product_question": "Thank you for your question. I want to give you a precise answer, so I will check this with the owner and come back to you within one business day.",
            "complaint": "I am sorry about your experience. Could you tell me a little more (and your order number, if you have one) so I can put this right?",
            "compliment": "Thank you so much, that made our day. Enjoy your order, and do get in touch any time.",
        }.get(c["kind"], "Thank you for your message. I will check this with the owner and come back to you within one business day.")
        return body

    def _sanitize(self, text):
        text = re.sub(r"\[[^\]]{1,40}\]", "", text)                       # placeholders like [tracking link]
        text = re.sub(r"!{2,}", "!", text)
        lines = [l.rstrip() for l in text.strip().splitlines()]
        first = self.policy["sign_off"].splitlines()[0].strip(" ,").lower()
        cut = len(lines)
        for i, l in enumerate(lines):                                      # drop any sign-off the model wrote
            ll = l.strip(" ,/").lower()
            if ll.startswith(("best regards", "kind regards", "regards", "sincerely", "warm regards", "best,", "cheers")) or ll == first:
                cut = i
                break
        body = "\n".join(lines[:cut]).strip()
        body = re.sub(r"\n{3,}", "\n\n", body)
        return body + "\n\n" + self.policy["sign_off"]

    def _check(self, text, c, source=""):
        """Automatic safety checks on a draft — shown to the owner next to the Approve button."""
        low = text.lower()
        flags = []
        allowed = set(re.findall(r"\d{3,}", source or "")) | set(re.findall(r"\d{3,}", self.policy_text()))
        foreign = [n for n in set(re.findall(r"\d{3,}", text)) if n not in allowed]
        if foreign:
            flags.append(f"contains a number the customer never gave: {', '.join(foreign)}")
        if re.search(r"\b(order|tracking) (number|no\.?|#)\s*[:#]?\s*[a-z0-9]{5,}", low):
            flags.append("mentions a specific order/tracking number — verify it")
        if re.search(r"\b(full refund|refund(ed)?|replacement)\b", low) and c["kind"] not in ("damaged_or_wrong", "return_or_refund", "cancel_or_change"):
            flags.append("promises a refund/replacement outside the return/damage cases")
        if re.search(r"\b\d{1,2}%\s*(off|discount)|\b(code|coupon)\s+[A-Z0-9]{4,}\b", text) and "newsletter" not in low:
            flags.append("offers a discount not in the policy")
        if re.search(r"\b(within|in) \d+ (hours?|days?)\b", low) and not re.search(r"one business day|5 business days|7-15 business days|30 days", low):
            flags.append("makes a time promise not in the policy")
        if re.search(r"\[[^\]]+\]|\bhere: *$|:\s*\.", text, re.M):
            flags.append("contains a placeholder or a dangling blank")
        if re.search(r"\b(find|here is|attached is) (the|your) tracking\b", low):
            flags.append("pretends to provide a tracking number")
        if c["kind"] == "damaged_or_wrong" and "tracking" in low:
            flags.append("talks about tracking in a damage case — the customer already has the parcel")
        if c["kind"] == "return_or_refund" and re.search(r"\bof course!?\b", low) and "30 days" not in low:
            flags.append("says 'of course' to a return without stating the 30-day window")
        if not (self.policy.get("ships_to") or "").strip() and re.search(r"\b(we|i) (do|don't|do not|can|cannot|can't)?\s*(ship|deliver) to\b", low):
            flags.append("states a shipping destination that is not in the policy")
        if not (self.policy.get("products") or "").strip() and re.search(r"\b(battery|hours|watt|waterproof|adjustable|made of|material|dimensions|cm\b|kg\b|grams?)\b", low):
            flags.append("invents product details")
        if re.search(r"\b(has (been )?shipped|is on its way|will arrive (on|by)|arrives? (tomorrow|on)|track it here|has been dispatched|we're working on your order)\b", low):
            flags.append("claims to know the order status — it doesn't")
        if re.search(r"\b(i'll|i will|we'll|we will|have) cancel+ed|(i'll|i will|we will) cancel\b|is (now )?cancel+ed\b", low):
            flags.append("promises a cancellation without checking if it shipped")
        if c["kind"] == "discount_request" and (re.search(r"\b(check your eligibility|get back to you as soon as possible|order number|sure, i can)\b", low) or "newsletter" not in low):
            flags.append("discount reply must state the policy (newsletter 10%) and nothing else")
        if len(text) > 1200:
            flags.append("too long")
        for n in c["needs"]:
            key = {"order number": "order number", "photo of the damage": "photo"}.get(n, n.split()[0])
            if key not in low:
                flags.append(f"does not ask for: {n}")
        if re.search(r"^\s*(\d+\.|-|•)\s", text, re.M):
            flags.append("uses a list — should be plain sentences")
        return flags

    # ---- decisions --------------------------------------------------------------
    def decide(self, mid, decision, final_text=None, note=""):
        rec = {"t": now(), "id": mid, "decision": decision, "text": final_text or "", "note": note}
        _append(DECISIONS, rec)
        if decision in ("approved", "edited") and final_text:
            m = self.get(mid) or {}
            _append(OUTBOX, {"t": now(), "id": mid, "channel": m.get("channel", "practice"), "to": m.get("from", ""), "text": final_text})
        if self.memory and decision in ("approved", "edited"):
            self.memory.note("reply", f"{decision} reply to {mid}", final_text or "", [])
        return rec

    def status(self):
        st = self.stats()
        return (f"customer messages: {len(self.items('new'))} waiting · {st['decisions']} decided "
                f"({st['approved']} approved, {st['edited']} edited, {st['rejected']} rejected)")

    def stats(self):
        d = _load(DECISIONS)
        n = len(d)
        appr = sum(1 for x in d if x["decision"] == "approved")
        edit = sum(1 for x in d if x["decision"] == "edited")
        rej = sum(1 for x in d if x["decision"] == "rejected")
        return {"decisions": n, "approved": appr, "edited": edit, "rejected": rej,
                "approval_rate": (appr / n) if n else 0.0}

    # ---- practice set --------------------------------------------------------------
    PRACTICE = [
        ("anna.k@example.com", "Order 48213 still not here", "Hi, I ordered a bamboo toothbrush set on the 2nd (order 48213) and it still hasn't arrived. Where is it?"),
        ("marco@example.com", "", "The mug arrived broken, the handle is off. What now? Order #51190, photo attached."),
        ("lisa.m@example.com", "return", "I want to return the yoga mat, I don't like the colour. Can I get my money back?"),
        ("tom_b@example.com", "", "Do you ship to Switzerland and how long does it take?"),
        ("julia@example.com", "cancel", "Please cancel my order, I changed my mind. Order 51302."),
        ("dave99@example.com", "", "Is there any discount code? Your competitor is cheaper."),
        ("sam@example.com", "", "Love the phone case, best purchase this year, thanks!!"),
        ("influencer.zoe@example.com", "collab", "Hi! I have 80k followers on Instagram, would love to collaborate on a sponsored post. What can you offer?"),
        ("angry.customer@example.com", "", "This is the second time your product arrived late. If I don't get a refund today I'll do a chargeback with my bank."),
        ("seo.pro@example.com", "Rank #1 guaranteed", "We can put your website on the first page of Google in 7 days, guaranteed. Reply for prices."),
        ("kim@example.com", "", "The dog leash I got is the wrong size (I ordered L, got S). Order 50877."),
        ("paul@example.com", "", "How long does the battery of the LED desk lamp last and is the light adjustable?"),
    ]

    def load_practice(self):
        added = 0
        have = {r["text"] for r in self.items()}
        for sender, subject, text in self.PRACTICE:
            if text not in have:
                self.add("practice", sender, text, subject)
                added += 1
        return added
