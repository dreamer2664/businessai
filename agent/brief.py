"""Understanding a request before doing it (milestone 13).

The owner writes in plain words. Before any work starts, the agent turns the message into a *brief*:
  goal        — what the owner wants, in one line
  pace        — how fast: "quick" (a few minutes), "normal", "slow" (use the time), plus an explicit deadline / budget
                ("in 10 minutes" → 10 min deadline; "I'm away 5 hours, take it slow" → 5 h budget)
  deliverable — what to hand back: an answer, a list, a document (with pictures/links), a file, a website …
  steps       — the to-do list the agent will follow (shown to the owner first, editable)
  kind        — which tool family does the work (research / seller_check / compare / visit / watch / build_site / chat / ask)

Pace words are parsed by rules (they must be reliable even without the thinking model); the goal, deliverable and steps
come from the thinking model when it is available, otherwise from rules. A brief is a dict; `text()` renders it for
Telegram. Deadlines are *reminders*, never a stop: the operator keeps the clock in front of it and reports when late.
"""
import json
import re
import time

PACE_PROMPT = """You turn the owner's message into a short work plan for a business assistant. Reply with one JSON object only:
{"goal": one line, what the owner wants;
 "deliverable": one of "answer" | "list" | "document" | "file" | "website" | "post" | "reply";
 "kind": one of "research" | "seller_check" | "compare" | "summarize" | "visit" | "watch" | "build_site" | "post" | "ask" | "chat";
 "steps": [3 to 7 short steps, each starting with a verb, concrete: which sites, what to check, what to write],
 "questions": [0 to 2 questions ONLY if something essential is missing (budget, country, size); else []]}
Rules: "reps"/"replicas"/"fakes" of brands are counterfeit — plan the research on the genuine or unbranded product instead
and say so in the goal. "seller_check" is for judging sellers/shops/listings (reviews, social pages, complaints, shipping,
origin, materials). "document" when the owner wants links, pictures or a walk-through. Never add a step that spends money,
logs in or posts publicly. Owner's message: """

# pace words → (pace, minutes)
_QUICK = r"\b(real quick|quick(ly)?|asap|right away|fast|hurry|in a hurry|subito|veloce|rapido)\b"
_SLOW = r"\b(take (it|your time) (real |really )?slow|take your time|no rush|no hurry|slowly|whenever|con calma|piano)\b"
_DEADLINE = r"\b(?:in|within|entro|tra)\s+(\d+|a|an|one|two|three|five|ten|fifteen|twenty|thirty|half an)\s*(min(?:ute)?s?|h(?:ou)?rs?|ore|minuti|day|days|giorni)\b"
_AWAY = r"\b(?:(?:i(?:'m| am| will be| ll be)|gonna be|going to (?:be|work)|at work|out|away|busy|sleeping|asleep)\D{0,40}?)(\d+|a|an|one|two|three|four|five|six|eight|ten|half an)\s*(h(?:ou)?rs?|ore|min(?:ute)?s?|minuti)\b"
_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8, "ten": 10, "fifteen": 15,
        "twenty": 20, "thirty": 30, "half an": 0.5}


def _minutes(n, unit):
    n = _NUM.get(n, None) if not str(n).isdigit() else int(n)
    if n is None:
        return None
    u = unit.lower()
    if u.startswith(("h", "ore")):
        return int(n * 60)
    if u.startswith(("day", "giorn")):
        return int(n * 60 * 24)
    return int(n)


_PACE_CLAUSES = [_QUICK, _SLOW, _DEADLINE, _AWAY,
                 r"\b(make it quick|i need it|i want it|i'?m (going to|gonna) (work|be out|be away|sleep)[^,.:;]*|take it (real |really )?slow|no rush)\b",
                 r"\b(for|in) (the next )?(\d+|a|an|one|two|three|four|five|six|eight|ten) ?(h(?:ou)?rs?|min(?:ute)?s?)\b"]
_LEAD = r"^(?:(?:hey|hi|hello|ciao|ok|okay|so|please|per favore|also|and|then|now|real quick|quick(?:ly)?|can you|could you|would you|will you|i want you to|i need you to|i'?d like you to|i want|i need|i'?d like|find me|find|get me|look for|search for|search|show me|tell me|give me|make me|please)[ ,:]+)+"


def topic_of(text):
    """The thing the request is about, without pace words, politeness and filler: 'hey, real quick find me some good
    cheap reps for nike slippers, i'm out for 3 hours' → 'reps for nike slippers'."""
    urls = re.findall(r"https?://\S+|\b[a-z0-9.-]+\.(?:com|it|de|fr|es|net|org|co|io|be|tv|me)(?:/\S*)?", text, re.I)
    low = " " + text.lower().strip() + " "
    for i, u in enumerate(urls):                                          # protect links from the punctuation split
        low = low.replace(u.lower(), f" URL{i} ")
    for pat in _PACE_CLAUSES:
        low = re.sub(pat, " ", low)
    low = re.sub(r"[.!?;:]+", ",", low)
    parts = [p.strip(" ,") for p in low.split(",") if p.strip(" ,")]
    parts = [p for p in parts if not re.fullmatch(r"(thanks?( you)?|please|asap|now|ok|okay|good luck|and|so)", p)]
    best = ""
    for p in parts:
        q = re.sub(_LEAD, "", p + " ").strip()
        q = re.sub(r"\b(some|a few|a couple of|good|cheap|reliable|trustworthy|best|nice|great|decent|quality|really|very|please|me|us)\b", " ", q)
        q = re.sub(r"\b(i'?m|i am|i will|i'?ll)\b.*$", "", q)
        q = re.sub(r"\s{2,}", " ", q).strip(" ,.-—")
        if len(q) > len(best):
            best = q
    for i, u in enumerate(urls):
        best = re.sub(f"url{i}", u, best, flags=re.I)
    return best or text.strip()


def parse_pace(text):
    """Rules only. Returns {"pace": quick|normal|slow, "deadline_min": int|None, "budget_min": int|None, "why": str}."""
    low = " " + text.lower() + " "
    out = {"pace": "normal", "deadline_min": None, "budget_min": None, "why": ""}
    m = re.search(_AWAY, low)
    if m:
        mins = _minutes(m.group(1), m.group(2))
        if mins and mins >= 30:
            out.update(pace="slow", budget_min=mins, why=f"you said you are away for about {mins // 60 if mins >= 60 else mins} {'hours' if mins >= 120 else 'hour' if mins >= 60 else 'minutes'}")
    m = re.search(_DEADLINE, low)
    if m:
        mins = _minutes(m.group(1), m.group(2))
        if mins:
            if out["budget_min"] and mins == out["budget_min"]:
                pass                                                    # "in 5 hours" already read as the away-time
            else:
                out.update(deadline_min=mins, why=f"you want it in {mins} minutes" if mins < 120 else f"you want it in {mins // 60} hours")
                out["pace"] = "quick" if mins <= 20 else out["pace"]
    if re.search(_QUICK, low) and out["pace"] != "slow":
        out["pace"] = "quick"
        out["why"] = out["why"] or "you said quick"
        out["deadline_min"] = out["deadline_min"] or 10
    if re.search(_SLOW, low):
        out["pace"] = "slow"
        out["why"] = out["why"] or "you said to take it slow"
    return out


def _rule_brief(text, pace):
    """No thinking model: a sensible brief from patterns."""
    low = text.lower()
    counterfeit = bool(re.search(r"\b(reps?|replicas?|fakes?|knock-?offs?|dupes?)\b", low)) and bool(re.search(r"\b(nike|adidas|gucci|louis|prada|rolex|jordan|yeezy|balenciaga|supreme|dior|chanel|apple)\b", low))
    goal = text.strip().rstrip(".!?")
    kind, deliverable = "ask", "answer"
    if re.search(r"\b(find|look for|search|cerca|trova)\b.*\b(seller|sellers|shop|shops|store|stores|supplier|suppliers|listing|listings|options?|deals?|cheap|good)\b", low) \
            or re.search(r"\b(reliable|trustworthy|legit|reviews?|complaints?)\b", low):
        kind, deliverable = "seller_check", "document"
    elif re.search(r"\b(compare|comparison|vs\.?|versus|which is (better|cheaper))\b", low):
        kind, deliverable = "compare", "document"
    elif re.search(r"\b(build|make|create)\b.*\b(website|web site|landing page|site)\b", low):
        kind, deliverable = "build_site", "website"
    elif re.search(r"\b(watch|video|youtube|youtu\.be|tiktok)\b", low):
        kind, deliverable = "watch", "list"
    elif re.search(r"https?://\S+", low) and re.search(r"\b(summari[sz]e|read|riassumi|tl;?dr)\b", low):
        kind, deliverable = "summarize", "answer"
    elif re.search(r"\b(open|go to|visit|check)\b.*\b(youtube|amazon|etsy|ebay|vinted|instagram|tiktok|google maps|\.com|\.it)\b", low):
        kind, deliverable = "visit", "answer"
    elif re.search(r"\b(research|find out|look into|learn about|how does|how do|what is the best way)\b", low):
        kind, deliverable = "research", "document" if re.search(r"\b(options?|list|links?|pictures?|images?|photos?|doc|document|walk me through)\b", low) else "answer"
    elif re.search(r"\b(post|caption|tweet|reel)\b", low):
        kind, deliverable = "post", "post"
    elif re.search(r"\b(hi|hello|hey|thanks|thank you|good (morning|evening|night)|ciao|grazie)\b", low) and len(low.split()) <= 6:
        kind, deliverable = "chat", "answer"
    if re.search(r"\b(doc|document|google docs?|walk me through|with (links|pictures|images))\b", low) and kind not in ("chat", "post", "build_site"):
        deliverable = "document"
    product = topic_of(text)
    if counterfeit:
        goal = f"{goal} — note: branded replicas are counterfeit, so I research genuine/unbranded options instead"
        product = re.sub(r"\b(reps?|replicas?|fakes?|knock-?offs?|dupes?)( of| for)?\b", "", product).strip()
        product = re.sub(r"\b(nike|adidas|gucci|louis vuitton|prada|rolex|jordan|yeezy|balenciaga|supreme|dior|chanel)\b", "", product).strip(" ,")
        product = re.sub(r"\s{2,}", " ", product).strip() or "the product"
        product = f"genuine or unbranded {product}"
    steps = {
        "seller_check": [f"Search for {product or 'the product'} on marketplaces and independent shops (3–6 candidates)",
                         "Open each listing: price, condition, photos, shipping cost/time, where it ships from, materials",
                         "Read the seller's reviews and complaints; look up their social media page and its comments",
                         "Judge reliability per seller (account age, ratings, response to complaints, red flags)",
                         "Write the document: one section per option with picture, link, verdict; a short ranking on top",
                         "If the store is open, offer to add the good ones to the shop with price and shipping"],
        "compare": [f"Find 3–5 sources for {product or 'the options'}", "Extract price, shipping, terms, ratings from each",
                    "Put them side by side and pick a winner with the reason", "Write the comparison with links"],
        "research": [f"Read 3–5 solid pages about {product or 'the topic'}", "Keep the facts and figures with their sources",
                     "Write a short report" + (" with links and pictures" if deliverable == "document" else "")],
        "build_site": ["Collect the brief: name, place, what they do, opening hours, contact", "Write the copy for home / about / services / contact",
                       "Build the pages (mobile-friendly, contact form, map link)", "Check every page in the browser and fix what looks wrong",
                       "Save the site to my library and send you the link"],
        "watch": ["Open the video(s) and read the captions", "Note the concrete ideas and figures", "Send you the list with timestamps"],
        "summarize": ["Open the page and read it fully", "Keep the key points with figures", "Write the summary"],
        "visit": ["Open the site", "Find the part the request is about", "Report what is there in plain words"],
        "post": ["Read the store's facts about the product", "Draft the post within the platform's limits", "Send it to you to approve"],
        "ask": ["Answer from my own knowledge", "If I don't know it well enough, look it up first"],
        "chat": [],
    }[kind]
    return {"goal": goal, "deliverable": deliverable, "kind": kind, "steps": steps, "questions": [], "counterfeit": counterfeit, "topic": product or goal}


class Brief:
    def __init__(self, planner=None, log=None):
        self.planner = planner
        self.log = log or (lambda kind, **f: None)

    def make(self, text):
        pace = parse_pace(text)
        b = _rule_brief(text, pace)
        if self.planner is not None and self.planner.installed() and b["kind"] not in ("chat",) and len(text.split()) >= 3:
            try:
                raw = self.planner.chat("You plan work for a business assistant. Output JSON only.", PACE_PROMPT + json.dumps(text), max_tokens=320, timeout=120)
                m = re.search(r"\{.*\}", raw, re.S)
                j = json.loads(m.group(0)) if m else {}
                if isinstance(j.get("steps"), list) and 2 <= len(j["steps"]) <= 8 and all(isinstance(s, str) and 3 < len(s) < 160 for s in j["steps"]):
                    b["steps"] = [s.strip().rstrip(".") for s in j["steps"]]
                if j.get("kind") in ("research", "seller_check", "compare", "summarize", "visit", "watch", "build_site", "post", "ask", "chat"):
                    if not (b["kind"] == "seller_check" and j["kind"] == "research"):        # rules see sellers better than the small model
                        b["kind"] = j["kind"]
                if j.get("deliverable") in ("answer", "list", "document", "file", "website", "post", "reply"):
                    b["deliverable"] = j["deliverable"] if not (b["deliverable"] == "document" and j["deliverable"] == "answer") else "document"
                if isinstance(j.get("goal"), str) and 5 < len(j["goal"]) < 200:
                    b["goal"] = j["goal"].strip()
                if isinstance(j.get("questions"), list):
                    b["questions"] = [q for q in j["questions"] if isinstance(q, str) and 5 < len(q) < 160][:2]
            except Exception as e:
                self.log("brief_model_error", error=str(e)[:120])
        b["pace"] = pace
        b["t"] = time.time()
        self.log("brief", task=b["kind"], deliverable=b["deliverable"], pace=pace["pace"], deadline=pace["deadline_min"], budget=pace["budget_min"], steps=len(b["steps"]))
        return b

    @staticmethod
    def text(b):
        """Render for Telegram: what I understood, the pace, the plan."""
        p = b["pace"]
        pace_line = {"quick": "⏱ quick", "slow": "🐢 slow — I'll use the time", "normal": "⏳ normal pace"}[p["pace"]]
        if p.get("deadline_min"):
            pace_line += f" · you want it in {p['deadline_min']} min — I'll keep a timer on my screen and tell you if I run late"
        if p.get("budget_min"):
            pace_line += f" · up to {p['budget_min'] // 60} h available — when I finish early I'll go on studying"
        out = [f"📋 What I understood: {b['goal']}", f"{pace_line}", f"📦 I'll hand you: {dict(answer='an answer', list='a list', document='a document with links and pictures', file='a file', website='a website', post='a post to approve', reply='a reply to approve')[b['deliverable']]}"]
        if b["steps"]:
            out.append("My plan:\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(b["steps"])))
        if b.get("questions"):
            out.append("Before I start: " + " ".join(b["questions"]))
        if b.get("counterfeit"):
            out.append("⚠️ Branded replicas are counterfeit (illegal to sell, fines even for buying in Italy) — I research genuine or unbranded options instead.")
        return "\n\n".join(out)
