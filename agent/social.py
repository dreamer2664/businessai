"""Social posts — drafted by the AI, approved by the owner, never published by itself (milestone 5, second half).

    /post <platform> <what it is about>      e.g.  /post instagram our new bamboo toothbrush set
    /post <what it is about>                 → platform "instagram" unless the text names one

Flow: the owner asks → the AI drafts a post from the store policy + the product facts it has (policy.products, learned notes)
→ hard checks (no invented prices, discounts, delivery promises, health/guarantee claims; platform length; hashtag count)
→ the owner taps Approve / Edit / Reject on the phone → approved text goes to state/posts.jsonl and comes back as copyable text.
Publishing through the platforms' official APIs comes later and will keep the same button gate.
"""
import datetime as _dt
import json
import re

from . import config

POSTS = config.STATE_DIR / "posts.jsonl"

PLATFORMS = {
    # max characters, max hashtags, style hint
    "instagram": (2200, 8, "one short hook line, 2-4 short sentences, a line break, then hashtags on their own line"),
    "facebook": (1500, 3, "conversational, 2-5 sentences, at most 3 hashtags, end with a question or a soft invitation"),
    "tiktok": (300, 5, "one punchy caption of 1-2 sentences, then up to 5 hashtags"),
    "x": (280, 2, "one or two sentences, at most 2 hashtags, no emoji spam"),
    "twitter": (280, 2, "one or two sentences, at most 2 hashtags, no emoji spam"),
    "linkedin": (1300, 3, "professional, 3-6 sentences, no more than 3 hashtags at the end"),
    "pinterest": (500, 4, "descriptive title-like first sentence, 2-3 sentences, keywords over hashtags"),
}

POST_PROMPT = """You write social media posts for a small online store.
STORE POLICY (facts you may state; never invent others):
%s

PLATFORM: %s — style: %s. Hard limit %d characters, at most %d hashtags.
RULES: write in the store's voice, plain and warm, no clickbait, no ALL CAPS words, at most 3 emoji. Never state a price, a
discount, a delivery time, a review count, a rating or a "best/#1" claim unless it is written in the policy above. Never make
health, safety, environmental or guarantee claims ("cures", "100%% safe", "saves the planet", "guaranteed"). Never mention a
competitor. Never write placeholders like [link] or [price]. If you know nothing about the product beyond the owner's words,
stay general and honest.

THE OWNER WANTS A POST ABOUT: %s
%s
Write only the post text."""


def now():
    return _dt.datetime.now().isoformat(timespec="seconds")


def _append(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _load(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


class Social:
    def __init__(self, planner=None, inbox=None, memory=None, log=None):
        self.planner = planner
        self.inbox = inbox            # for the store policy
        self.memory = memory
        self.log = log or (lambda kind, **f: None)
        config.ensure_dirs()

    # ---- parsing the owner's request ------------------------------------------------
    @staticmethod
    def parse(arg):
        """'/post instagram our new mug' → ('instagram', 'our new mug'); platform defaults to instagram."""
        a = arg.strip()
        m = re.match(r"(?:(?:on|for)\s+)?(instagram|insta|ig|facebook|fb|tiktok|x|twitter|linkedin|pinterest)\b[:,\s]*(.*)", a, re.I | re.S)
        if m:
            plat = {"insta": "instagram", "ig": "instagram", "fb": "facebook", "twitter": "x"}.get(m.group(1).lower(), m.group(1).lower())
            return plat, m.group(2).strip()
        m = re.search(r"\b(?:on|for)\s+(instagram|insta|ig|facebook|fb|tiktok|x|twitter|linkedin|pinterest)\b", a, re.I)
        if m:
            plat = {"insta": "instagram", "ig": "instagram", "fb": "facebook", "twitter": "x"}.get(m.group(1).lower(), m.group(1).lower())
            return plat, (a[:m.start()] + a[m.end():]).strip(" ,.")
        return "instagram", a

    # ---- drafting --------------------------------------------------------------------
    def draft(self, platform, topic):
        platform = platform if platform in PLATFORMS else "instagram"
        limit, max_tags, style = PLATFORMS[platform]
        policy = self.inbox.policy if self.inbox else {}
        facts = "\n".join(f"{k}: {v}" for k, v in policy.items() if k in ("store_name", "tone", "shipping", "returns", "products", "ships_to") and v)
        known = ""
        if self.memory:
            hits = self.memory.notes(topic, limit=2)
            if hits:
                known = "WHAT I HAVE LEARNED (use only if relevant, never invent beyond it):\n" + "\n".join(f"- {h['text'][:300]}" for h in hits)
        text = ""
        if self.planner and self.planner.installed():
            try:
                text = self.planner.chat("You are the social media writer of a small online store.",
                                         POST_PROMPT % (facts or "(none beyond the owner's words)", platform, style, limit, max_tags, topic[:400], known),
                                         max_tokens=min(320, limit // 3 + 60), temperature=0.4, timeout=240)
            except Exception as e:
                self.log("post_failed", error=str(e)[:100])
        text = self._sanitize(text, platform)
        checks = self._check(text, platform, topic, facts)
        if checks and self.planner and self.planner.installed():
            try:
                fixed = self.planner.chat("You are the social media writer of a small online store.",
                                          POST_PROMPT % (facts or "(none beyond the owner's words)", platform, style, limit, max_tags, topic[:400], known)
                                          + f"\n\nYour previous draft was rejected because it: {'; '.join(checks)}. Write a corrected post.",
                                          max_tokens=min(320, limit // 3 + 60), temperature=0.3, timeout=240)
                fixed = self._sanitize(fixed, platform)
                if len(self._check(fixed, platform, topic, facts)) < len(checks):
                    text, checks = fixed, self._check(fixed, platform, topic, facts)
            except Exception:
                pass
        note = ""
        if not text.strip():
            text = self._template(platform, topic, policy)
            checks = self._check(text, platform, topic, facts)
            note = "the thinking model was not available — this is a plain template"
        return {"platform": platform, "topic": topic, "text": text, "checks": checks, "note": note, "chars": len(text)}

    def _template(self, platform, topic, policy):
        name = policy.get("store_name") or "our store"
        tags = "" if platform in ("x", "linkedin") else "\n\n#" + re.sub(r"[^a-z0-9]+", "", (policy.get("store_name") or "shop").lower()) + " #newin"
        return f"New at {name}: {topic.strip().rstrip('.')}. Have a look and tell us what you think." + tags

    def _sanitize(self, text, platform):
        text = re.sub(r"\[[^\]]{1,40}\]", "", text or "").strip()
        text = re.sub(r"^(post|caption|here('s| is) (the|your) post)\s*:\s*", "", text, flags=re.I).strip()
        text = text.strip('"“” ')
        text = re.sub(r"!{2,}", "!", text)
        limit, max_tags, _ = PLATFORMS[platform]
        tags = re.findall(r"#\w+", text)
        if len(tags) > max_tags:                                          # keep the first N hashtags, drop the rest
            for t in tags[max_tags:]:
                text = text.replace(" " + t, "").replace(t, "")
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text

    def _check(self, text, platform, topic, facts):
        low = text.lower()
        limit, max_tags, _ = PLATFORMS[platform]
        allowed = (topic + " " + facts).lower()
        flags = []
        if len(text) > limit:
            flags.append(f"too long for {platform} ({len(text)} > {limit} characters)")
        if len(re.findall(r"#\w+", text)) > max_tags:
            flags.append(f"more than {max_tags} hashtags")
        for m in re.finditer(r"(?:[$€£]\s?\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s?(?:€|eur|usd|dollars?|euros?|gbp))", low):
            if m.group(0).replace(" ", "") not in allowed.replace(" ", ""):
                flags.append(f"states a price the owner did not give ({m.group(0).strip()})")
                break
        m = re.search(r"\b\d{1,2}\s?%\s?(off|discount|sale)|\b(sale|discount|coupon|promo code|free shipping)\b", low)
        if m and m.group(0) not in allowed:
            flags.append(f"promises '{m.group(0)}' which is not in the policy")
        m = re.search(r"\b(ships? (in|within) \d+|\d+[- ]day (delivery|shipping)|delivered (by|within)|arrives? (tomorrow|in \d+))\b", low)
        if m and m.group(0) not in allowed:
            flags.append("makes a delivery promise not in the policy")
        m = re.search(r"\b(cures?|heals?|100 ?% (safe|natural|effective)|guaranteed?|risk[- ]free|clinically|doctor[- ]recommended|saves? the planet|zero waste|carbon neutral|best in the world|#1|number one|the best [a-z]+ ever)\b", low)
        if m and m.group(0) not in allowed:
            flags.append(f"makes a claim we cannot back ('{m.group(0)}')")
        m = re.search(r"\b(\d[\d,.]*\+? (five|5)[- ]star|\d[\d,.]*\+? (happy customers|reviews|sold)|rated \d)", low)
        if m and m.group(0) not in allowed:
            flags.append(f"invents social proof ('{m.group(0)}')")
        if re.search(r"\[[^\]]+\]|\b(link in bio|shop now at) *$", text, re.M | re.I) and "link in bio" not in allowed:
            flags.append("contains a placeholder")
        caps = [w for w in re.findall(r"\b[A-Z]{4,}\b", text) if w not in ("LED", "USB", "SALE", "NEW")]
        if len(caps) > 1:
            flags.append("shouting in capitals")
        if len(re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", text)) > 3:
            flags.append("too many emoji")
        if re.search(r"\b(amazon|temu|shein|aliexpress|ikea|zara|h&m)\b", low) and not re.search(r"\b(amazon|temu|shein|aliexpress|ikea|zara|h&m)\b", allowed):
            flags.append("mentions a competitor")
        return flags

    # ---- decisions ---------------------------------------------------------------------
    def decide(self, pid, decision, draft, final_text=""):
        rec = {"t": now(), "id": pid, "platform": draft["platform"], "topic": draft["topic"], "decision": decision,
               "draft": draft["text"][:2500], "text": (final_text or "")[:2500]}
        _append(POSTS, rec)
        if self.memory and decision in ("approved", "edited"):
            self.memory.note("post", f"{draft['platform']} post: {draft['topic'][:80]}", final_text or "", [])
        return rec

    def stats(self):
        d = _load(POSTS)
        return {"decided": len(d), "approved": sum(1 for x in d if x["decision"] == "approved"),
                "edited": sum(1 for x in d if x["decision"] == "edited"), "rejected": sum(1 for x in d if x["decision"] == "rejected")}

    def status(self):
        s = self.stats()
        return f"social posts: {s['decided']} decided ({s['approved']} approved, {s['edited']} edited, {s['rejected']} rejected) — none published, no channel connected yet"
