"""Operator — the see → think → act loop (milestone 7: the agent works a screen by itself).

Given a goal in plain words ("find the price of the cheapest bamboo toothbrush set on this page and put one in the
cart"), it repeats:
    1. SEE   — screenshot + OCR lines (what is written where) + numbered page elements when a browser page is there
    2. THINK — the thinking model picks ONE next step as JSON: click <text> | type <text> | scroll down|up | back |
               open <url> | done <answer> | ask <question for the owner> | stop <reason>
    3. GUARD — every click goes through the safety guard: buttons that spend money, publish, delete, log in or
               submit are never clicked unless the owner approved that exact step on the phone (ask_owner callback)
    4. ACT   — browser (Playwright: numbered element click/type, exact and fast) or desktop (xdotool at the OCR
               coordinates) — same loop, different hands
    5. CHECK — what changed? (OCR diff) — fed back into the next THINK; no visible change twice in a row → rethink
Hard limits: MAX_STEPS steps, one goal at a time, every step logged with a screenshot, the live screen shows it.

The operator never types passwords, never solves CAPTCHAs, never passes a login wall: on those it stops and tells
the owner exactly where it stopped so a human can take over on the same screen.
"""
import json
import re
import time

from . import config
from .browser import _JS_TEXT as _JS_TEXT_NAME

MAX_STEPS = 12
MAX_PAGES = 5           # pages per multi-page (compare) goal
MAX_ASKS = 2            # questions to the owner per goal; more than that means I don't understand the goal
MAX_SECONDS = 900       # wall-clock budget per goal
DANGER = re.compile(r"\b(buy|pay|checkout|check out|place order|order now|purchase|confirm|send|post|publish|delete|remove|"
                    r"submit|subscribe|sign in|log in|login|register|agree|accept all|install|download|unsubscribe|"
                    r"transfer|donate|upgrade|start trial|add to cart|add to bag|add to basket)\b", re.I)

THINK_PROMPT = """You operate a computer screen for your owner, one small step at a time.
GOAL: %s

WHAT YOU DID SO FAR:
%s

WHAT IS ON THE SCREEN NOW (%s):
%s

Answer with exactly ONE JSON object for the next step:
{"step": "type", "target": "<name of a field from FIELDS YOU CAN TYPE IN>", "text": "<what to type>", "enter": true}
{"step": "click", "target": "<exact text from THINGS YOU CAN CLICK>"}
{"step": "scroll", "direction": "down"}
{"step": "back"}
{"step": "done", "answer": "<the facts copied from the screen that fulfil the goal>"}
{"step": "stop", "reason": "<why you cannot continue: login wall, captcha, nothing relevant here>"}
Examples:
- goal "find the price of the blue mug", screen text says "Blue mug — $4" → {"step": "done", "answer": "The blue mug costs $4."}
- goal "search the site for lamps", field "Search" exists → {"step": "type", "target": "Search", "text": "lamps", "enter": true}
- goal "open the shipping page", link "Shipping" exists → {"step": "click", "target": "Shipping"}
- goal "read the reviews", nothing about reviews on the screen yet → {"step": "scroll", "direction": "down"}
Rules: one object, nothing else. Use the screen only; never invent facts. To search for something, TYPE it into the search
field. Never log in, pay or pass a captcha — "stop" instead. Never ask the owner anything; decide yourself."""


class Operator:
    def __init__(self, planner, eyes=None, tasks=None, desktop=None, log=None, notify=None, ask_owner=None, viewer=None):
        self.planner = planner
        self.eyes = eyes
        self.tasks = tasks              # browser hands (Tasks.on_hands + Browser)
        self.desktop = desktop          # desktop hands
        self.log = log or (lambda kind, **f: None)
        self.notify = notify or (lambda t: None)
        self.ask_owner = ask_owner      # callable(question, options) -> label or None
        self.viewer = viewer
        self.history = []

    # ---- public --------------------------------------------------------------------------
    NEVER = re.compile(r"\b(sign in|log ?in|password|passcode|captcha|verify (?:i am|you are) (?:a )?human|enter (?:my|the) (?:card|credit card|iban|cvv)|"
                       r"pay(?:ment)? (?:with|by|using) (?:my )?(?:card|paypal)|checkout|check out|place (?:the |my )?order|complete (?:the |my )?(?:purchase|order))\b", re.I)

    def run(self, goal, where="browser", start_url=None, allow=None):
        """Work towards `goal`. where: 'browser' | 'desktop'. start_url may be a list of pages (compare goals).
        Returns a plain-language report."""
        self.history = []
        if self.NEVER.search(goal):
            return ("I stopped before starting: that goal means logging in, paying or handling a password/captcha, and I never do those by "
                    "myself. Do that step yourself, then give me the goal that comes after it.")
        if isinstance(start_url, (list, tuple)) and len(start_url) > 1 and where == "browser":
            return self._run_pages(goal, list(start_url))
        if isinstance(start_url, (list, tuple)):
            start_url = start_url[0] if start_url else None
        form = self._form_fields(goal)
        if form and where == "browser":
            return self._run_form(goal, form, start_url)
        allow = set(allow or [])            # labels the owner pre-approved for this goal
        t0 = time.time()
        steps = 0
        last_change = ""
        same_count = 0
        if where == "browser":
            if not self.tasks:
                return "I have no browser hands."
            if start_url:
                r = self._browser_open(start_url)
                self.history.append(f"opened {start_url} → {r}")
        elif where == "desktop":
            if not (self.desktop and self.desktop.available()):
                return "I have no desktop hands here (sh scripts/install_desktop.sh)."
            self.desktop.new_task(allow_actions=False)
        question = self._is_question(goal)
        wants_info = question or bool(re.search(r"\b(tell me|what|which|how many|how much|who|when|where|find out|report|list|read me|price of|cost of)\b", goal.lower()))
        acted = False
        prev_sig = None
        verify_next = False
        asks = 0
        before, last_action = None, ""
        while steps < MAX_STEPS:
            if time.time() - t0 > MAX_SECONDS:
                return self._finish("I stopped: this is taking too long. Tell me a more precise goal (or a page to start from) and I'll try again.", t0, steps)
            steps += 1
            seen = self._see(where)
            if seen.get("wall"):
                return self._finish(f"I stopped at step {steps}: the screen shows a {seen['wall']} — I never pass those. Please do that part yourself; I can continue after.", t0)
            if question or (wants_info and acted):                  # read first: is the answer already on the screen?
                verify_next = False
                ans = self._try_answer(goal, seen)
                if ans:
                    return self._finish(ans, t0, steps)
            elif verify_next:                                       # after an action: did it work?
                verify_next = False
                ev = self._verify(goal, last_action, before, seen)
                if ev:
                    return self._finish(f"Done — the screen now shows: {ev[:160]}", t0, steps)
            if acted and where == "browser" and self._lost(goal, before, seen) and steps < MAX_STEPS:
                self.history.append("that page has nothing to do with the goal — going back")
                self._act_back(where)
                acted = False
                prev_sig = ("back", "")
                continue
            decision = self._think(goal, seen)
            step = decision.get("step", "stop")
            if step == "type":
                tgt, txt = str(decision.get("target") or ""), str(decision.get("text") or "")
                if where == "browser":
                    n = self._element_number(seen, tgt)
                    role = next((r for k, _, r in seen.get("items", []) if k == n), "")
                    if n is not None and role not in ("textbox", "searchbox", "combobox", "textarea"):
                        decision, step = {"step": "click", "target": tgt}, "click"        # it's a link/button, not a field
                elif not txt.strip() or txt.strip().lower() == tgt.strip().lower() or DANGER.search(tgt):
                    decision, step = {"step": "click", "target": tgt}, "click"            # "type 'Add to cart' into 'Add to cart'" = a click
            if question and step in ("click", "type") and DANGER.search(str(decision.get("target", ""))):
                decision, step = {"step": "scroll", "direction": "down"}, "scroll"      # no buying/submitting to answer a question
            sig = (step, str(decision.get("target") or decision.get("url") or decision.get("direction") or "").lower())
            if sig == prev_sig and step in ("click", "type"):
                self.history.append(f"not repeating '{sig[1]}' — looking further down instead")
                decision, step = {"step": "scroll", "direction": "down"}, "scroll"
                sig = (step, "down")
            prev_sig = sig
            self.log("operator_step", n=steps, step=step, target=str(decision.get("target") or decision.get("url") or decision.get("direction") or "")[:60])
            if step == "done":
                return self._finish(str(decision.get("answer") or "Done."), t0, steps)
            if step == "stop":
                return self._finish(f"I stopped: {decision.get('reason', 'no way forward')}.", t0, steps)
            if step == "ask":
                q = str(decision.get("question") or "How should I continue?")
                if self._similar(q, goal) or (question and q.rstrip("?").lower() in goal.lower()):
                    self.history.append("wanted to ask you the goal itself — continuing on my own")
                    decision = {"step": "scroll", "direction": "down"}
                    step = "scroll"
            if step == "ask":
                asks += 1
                if asks > MAX_ASKS:
                    return self._finish(f"I stopped: I would need to ask you again ({q}) and I don't want to nag — tell me more precisely what to do and I'll retry.", t0, steps)
                ans = self.ask_owner(q, ["Continue", "Stop"]) if self.ask_owner else None
                self.history.append(f"asked you: {q} → {ans}")
                if ans in (None, "Stop"):
                    return self._finish(f"Stopped after asking: {q}", t0, steps)
                continue
            if step in ("click", "type"):
                target = str(decision.get("target") or "")[:80]
                if not target:
                    self.history.append("wanted to click nothing — rethinking")
                    continue
                if DANGER.search(target) and target.lower() not in allow:
                    ok = self.ask_owner(f"On this screen I want to click “{target}”. This looks like a money/publish/sign-in step. Allowed?",
                                        ["Yes, click it", "No"]) if self.ask_owner else None
                    if ok != "Yes, click it":
                        self.history.append(f"did NOT click '{target}' (not approved)")
                        return self._finish(f"I stopped before clicking “{target}” because you did not approve it.", t0, steps)
                    allow.add(target.lower())
                if step == "click":
                    result = self._act_click(where, target, seen, approved=target.lower() in allow)
                else:
                    result = self._act_type(where, target, str(decision.get("text") or ""), bool(decision.get("enter")), seen, approved=target.lower() in allow)
            elif step == "scroll":
                result = self._act_scroll(where, str(decision.get("direction") or "down"))
            elif step == "back":
                result = self._act_back(where)
            elif step == "open":
                url = str(decision.get("url") or "")
                result = self._browser_open(url) if where == "browser" and url.startswith("http") else "cannot open URLs here"
            else:
                result = f"unknown step {step}"
            short = str(result).replace("\n", " ")
            short = re.sub(r"^URL: \S+\s+TITLE: ([^\n]{0,60}?)\s+TABS:.*$", r"page: \1", short)[:120]
            what = f"typed into '{decision.get('target', '')}': {decision.get('text', '')}" if step == "type" else \
                   f"{step} {decision.get('target') or decision.get('url') or decision.get('direction') or ''}"
            self.history.append(f"{what} → {short}")
            if step in ("click", "type") and not str(result).startswith(("refused", "could not", "'", "click failed", "typing failed")):
                verify_next = True
                acted = True
                before = seen
                last_action = f"{'clicked' if step == 'click' else 'typed into'} \"{decision.get('target', '')}\"" + (f" the text \"{decision.get('text', '')}\"" if step == "type" else "")
            if result == last_change:
                same_count += 1
                if same_count >= 2:
                    self.history.append("nothing changed twice — trying something else")
            else:
                same_count = 0
            last_change = result
            if self.viewer:
                try:
                    self.viewer.step(f"operator: {step} {decision.get('target', '')}", "", goal[:60], "ok", 1, None)
                except Exception:
                    pass
        return self._finish(f"I used my {MAX_STEPS} steps without finishing. Last things I saw: {self.history[-1] if self.history else '-'}", t0, steps)

    # ---- multi-page goals ---------------------------------------------------------------------
    def _run_pages(self, goal, urls):
        """Read the same question off several pages, then answer once across all of them (compare / which is cheapest)."""
        t0 = time.time()
        findings = []
        for i, u in enumerate(urls[:MAX_PAGES], 1):
            r = self._browser_open(u)
            self.history.append(f"opened page {i}: {u} → {r}")
            if r != "opened":
                findings.append((u, "(could not open)"))
                continue
            seen = self._see("browser")
            if seen.get("wall"):
                findings.append((u, f"({seen['wall']} — skipped)"))
                continue
            fact = self._try_answer(f"{goal} (about THIS page only; give the concrete figures/words)", seen) or \
                   self._try_answer(re.sub(r"\b(which|what)\b.*?\b(cheapest|best|fastest|lowest|highest|most|least)\b", "what is the price / value asked about", goal, flags=re.I), seen)
            findings.append((seen.get("title") or u, fact or "(nothing relevant on this page)"))
            self.history.append(f"page {i} ({(seen.get('title') or u)[:40]}): {fact or 'nothing relevant'}"[:200])
        table = "\n".join(f"- {t[:70]}: {f}" for t, f in findings)
        try:
            raw = self.planner.chat("You compare findings from several web pages for your owner. Use only the findings given; never add outside knowledge.",
                                    f"GOAL: {goal}\n\nFINDINGS (one line per page):\n{table}\n\nAnswer the goal in one or two plain sentences, naming the page(s) and the figures. "
                                    f"If the findings do not settle it, say which page lacks the information.", max_tokens=120, timeout=200)
            summary = raw.strip()
            if not self._grounded(summary, table.lower(), goal):
                summary = "Here is what each page says (I could not settle the comparison from that):"
        except Exception as e:
            self.log("operator_compare_failed", error=str(e)[:80])
            summary = "Here is what each page says:"
        return self._finish(f"{summary}\n{table}", t0, len(findings))

    # ---- forms --------------------------------------------------------------------------------
    @staticmethod
    def _form_fields(goal):
        """'fill the form: name = Anna Rossi, email = anna@x.it, message = Hi' → {'name': 'Anna Rossi', ...}; {} when not a form goal."""
        m = re.search(r"\b(?:fill(?: in| out)?|complete|enter)\b.*?(?:form|fields?|enquiry|inquiry|request)?\s*[:\-–—]\s*(.+)$", goal, re.I | re.S)
        if not m:
            return {}
        body = m.group(1)
        fields = {}
        for part in re.split(r"\s*[;,\n]\s*(?=[A-Za-z][A-Za-z /_-]{0,30}\s*[=:])", body):
            mm = re.match(r"\s*([A-Za-z][A-Za-z /_-]{0,30}?)\s*[=:]\s*(.+?)\s*$", part, re.S)
            if mm:
                fields[mm.group(1).strip().lower()] = mm.group(2).strip().strip('"\'')
        return fields

    def _run_form(self, goal, fields, start_url):
        """Type the given values into the matching fields, never press send: the owner gets a screenshot-style summary and decides."""
        t0 = time.time()
        if start_url:
            self.history.append(f"opened {start_url} → {self._browser_open(start_url)}")
        seen = self._see("browser")
        if seen.get("wall"):
            return self._finish(f"I stopped: the page shows a {seen['wall']}.", t0, 1)
        if any(k in ("password", "card number", "cvv", "iban", "passcode") for k in fields):
            return self._finish("I don't type passwords, card numbers or bank details — please do that part yourself.", t0, 1)
        done, missing = [], []
        for key, val in fields.items():
            n = self._field_number(seen, key)
            if n is None:
                missing.append(key)
                continue
            r = self._act_type("browser", key, val, False, seen, field_n=n)
            ok = not str(r).startswith(("typing failed", "refused", "'"))
            (done if ok else missing).append(key if ok else f"{key} ({r[:40]})")
            self.history.append(f"typed into '{key}': {val[:40]} → {'ok' if ok else r[:60]}")
        after = self._see("browser")
        send = next((lab for _, lab, role in after.get("items", []) if role == "button" and DANGER.search(lab or "")), None)
        report = f"I filled in {len(done)} field(s): {', '.join(done) or '-'}."
        if missing:
            report += f"\nI could not find: {', '.join(missing)}."
        if send:
            report += f"\nThe form is ready but NOT sent — the “{send}” button is untouched. Check it on the live screen and tell me “/do click {send}” if it should go out."
        else:
            report += "\nI did not find a send/submit button on this page."
        return self._finish(report, t0, len(fields) + 1)

    def _field_number(self, seen, key):
        """The [n] of the typing field whose label best matches key ('email' → 'E-mail address')."""
        k = re.sub(r"[^a-z0-9]", "", key.lower())
        alias = {"email": ("email", "mail"), "name": ("name", "yourname", "fullname", "nome"), "phone": ("phone", "tel", "mobile"),
                 "message": ("message", "comment", "enquiry", "inquiry", "text", "messaggio"), "company": ("company", "business", "azienda", "organisation", "organization"),
                 "subject": ("subject", "topic"), "quantity": ("quantity", "qty", "amount"), "website": ("website", "url", "site"), "city": ("city", "town"), "country": ("country",)}
        wanted = alias.get(k, (k,))
        best, best_n = 0, None
        for n, label, role in seen.get("items", []):
            if role not in ("textbox", "textarea", "searchbox", "combobox", "select"):
                continue
            lab = re.sub(r"[^a-z0-9]", "", (label or "").lower())
            for w in wanted:
                if lab == w:
                    return n
                if w in lab or (lab and lab in w):
                    sc = len(w) / max(len(lab), len(w))
                    if sc > best:
                        best, best_n = sc, n
        return best_n if best >= 0.3 else None

    # ---- see ---------------------------------------------------------------------------------
    def _see(self, where):
        out = {"where": where, "lines": [], "elements": "", "shot": None, "wall": ""}
        if where == "browser":
            def grab(b):
                banner = b.dismiss_banner() if hasattr(b, "dismiss_banner") else ""
                b.snapshot()
                st = b.status()
                shot = b.page.screenshot(type="png", timeout=8000)
                try:
                    full = b.page.evaluate(_JS_TEXT_NAME)
                except Exception:
                    full = b.extract_text()
                items = [(it.get("n"), (it.get("label") or "")[:80], it.get("role", "")) for it in (b.items or [])]
                return st, shot, full[:12000], b.page.url, b.page.title(), items, banner
            try:
                st, shot, full, url, title, items, banner = self.tasks.on_hands(lambda: grab(self.tasks.browser()), timeout=60)
            except Exception as e:
                out["elements"] = f"(browser error: {str(e)[:80]})"
                return out
            if banner:
                self.history.append(f"closed a cookie banner ({banner})")
            out.update(shot=shot, elements=full[:3000], fulltext=full, url=url, title=title, items=items)
            if st in ("captcha", "login"):
                out["wall"] = "captcha" if st == "captcha" else "login wall"
            elif any((lab or "").lower() in ("password", "passwort", "contraseña", "mot de passe") and role == "textbox" for _, lab, role in items) \
                    and len(items) <= 8 and len(full) < 600:
                out["wall"] = "login wall"                                  # a bare sign-in form and nothing else
        else:
            shot = self.desktop.screenshot("see")
            out["shot"] = shot
        if self.eyes and out["shot"] and (where == "desktop" or len(out.get("fulltext") or "") < 300):
            ls = self.eyes.lines(out["shot"]) if self.eyes.ocr else []
            out["lines"] = ls
            if where == "desktop":
                # every line of text on the screen is something I can click on (by its words) — same shape as browser items
                out["items"] = [(i + 1, l["text"], "text") for i, l in enumerate(ls[:80])]
                words = " ".join(l["text"].lower() for l in ls)
                if re.search(r"\b(i'?m not a robot|captcha|verify you are human|checking your browser)\b", words):
                    out["wall"] = "captcha"
                elif re.search(r"\bpassword\b", words) and re.search(r"\b(sign in|log in|login)\b", words) and len(ls) < 25:
                    out["wall"] = "login wall"
            if not out["wall"] and self.eyes.installed() and len(ls) < 6:
                d = self.eyes.describe(out["shot"])
                out["description"] = d["summary"]
                if d["kind"] == "captcha" or "captcha" in d["warnings"]:
                    out["wall"] = "captcha"
                elif d["kind"] == "login" or "login wall" in d["warnings"]:
                    out["wall"] = "login wall"
        return out

    def _screen_text(self, seen):
        if seen.get("where") == "browser" and seen.get("elements"):
            return f"page: {seen.get('title', '')} — {seen.get('url', '')}\n{seen['elements']}"
        parts = []
        if seen.get("description"):
            parts.append("looks like: " + seen["description"])
        for l in seen.get("lines", [])[:60]:
            parts.append(l["text"])
        return "\n".join(parts)[:3500] or "(blank screen)"

    # ---- think -----------------------------------------------------------------------------
    def _think_view(self, goal, seen):
        """What the thinker gets to see: typing fields, clickable things (goal-relevant first), then a text excerpt."""
        items = seen.get("items") or []
        if not items:
            return self._screen_text(seen)
        if seen.get("where") == "desktop":
            return ("SCREEN (my own screen; every line below is text I can click on by its words; to type, click a field first):\n"
                    + "\n".join(f'"{lab[:70]}"' for _, lab, _ in items[:60]))
        stop = {"the", "and", "for", "what", "which", "when", "does", "how", "many", "find", "out", "tell", "with", "from", "this", "that",
                "are", "was", "were", "has", "have", "who", "where", "why", "much", "there", "about", "into", "page", "site", "open",
                "click", "search", "first", "sentence", "article", "product", "its", "then", "please", "put", "one"}
        keys = {w for w in re.findall(r"[a-z0-9]{3,}", goal.lower()) if w not in stop}
        fields, clicks = [], []
        for n, label, role in items:
            lab = re.sub(r"\s+", " ", label or "").strip()
            if not lab:
                continue
            if role in ("textbox", "searchbox", "combobox", "textarea"):
                fields.append(lab)
            else:
                rel = sum(1 for k in keys if k in lab.lower())
                clicks.append((-rel, 0 if role == "button" else 1, lab))
        clicks.sort()
        seen_labels, click_labels = set(), []
        for _, _, lab in clicks:
            if lab.lower() in seen_labels:
                continue
            seen_labels.add(lab.lower())
            click_labels.append(lab[:60])
            if len(click_labels) >= 30:
                break
        text = re.sub(r"\[\s*\d+\s*\]\s*", "", seen.get("fulltext") or seen.get("elements") or "")
        text = re.sub(r"\n\s*\n+", "\n", text).strip()[:1400]
        parts = [f"PAGE: {seen.get('title', '')} — {seen.get('url', '')}"]
        parts.append("FIELDS YOU CAN TYPE IN: " + (", ".join(f'"{f[:50]}"' for f in fields[:8]) or "(none)"))
        parts.append("THINGS YOU CAN CLICK: " + (", ".join(f'"{c}"' for c in click_labels) or "(none)"))
        parts.append("PAGE TEXT (start):\n" + text)
        return "\n".join(parts)

    def _obvious_step(self, goal, seen):
        """Cheap rules for the most common first moves (no model call): search goals → type into the search field."""
        m = re.search(r"\b(?:search|look up|look for|find)\b[^'\"“]*['\"“]([^'\"”]{2,60})['\"”]", goal, re.I) or \
            re.search(r"\bsearch(?: for)?\s+([a-z0-9 -]{2,40}?)\s+(?:on|in|at)\b", goal, re.I)
        if not m:
            # a button whose whole label is inside the goal ("Buy the set now" → button "Buy now") is the obvious click
            gw = set(re.findall(r"[a-z0-9]+", goal.lower()))
            best = None
            for n, label, role in seen.get("items") or []:
                lw = [w for w in re.findall(r"[a-z0-9]+", (label or "").lower()) if w not in ("the", "a", "to", "in", "on")]
                if role == "button" and 1 <= len(lw) <= 3 and all(w in gw for w in lw) and not any(h.lower().startswith(f"click {label.lower()}") for h in self.history):
                    if best is None or len(lw) > best[0]:
                        best = (len(lw), label)
            if best and (best[0] >= 2 or len(best[1]) >= 4):
                return {"step": "click", "target": best[1]}
            mo = re.match(r"^\s*(?:open|go to|click|click on|visit|show)\s+(?:the\s+)?['\"“]?([^'\"”,.]{2,50}?)['\"”]?(?:\s+(?:page|tab|link|button|section|product))?(?:\s+(?:and|then|,)\b|\s*$)", goal, re.I)
            if mo:
                want = mo.group(1).strip().lower()
                if not any(h.lower().startswith(f"click {want}") for h in self.history):
                    n = self._element_number(seen, want)
                    if n is not None:
                        label = next((lab for k, lab, _ in seen.get("items", []) if k == n), want)
                        return {"step": "click", "target": label}
            return None
        term = m.group(1).strip()
        if any(("typed into" in h and term.lower() in h.lower()) for h in self.history):
            return None                                                   # already searched
        for n, label, role in seen.get("items") or []:
            lab = (label or "").lower()
            if role in ("textbox", "searchbox", "combobox") and ("search" in lab or "find" in lab or lab == "q"):
                return {"step": "type", "target": label, "text": term, "enter": True}
        return None

    def _think(self, goal, seen):
        obvious = self._obvious_step(goal, seen)
        if obvious:
            return obvious
        hist = "\n".join(f"{i+1}. {h}" for i, h in enumerate(self.history[-6:])) or "(nothing yet)"
        prompt = THINK_PROMPT % (goal, hist, seen.get("where", ""), self._think_view(goal, seen))
        try:
            raw = self.planner.chat("You are a careful computer operator. Output one JSON object only.", prompt, max_tokens=120, timeout=200, stop=["\n\n"])
            cands = []
            for m in re.finditer(r"\{[^{}]*\}", raw, re.S):
                try:
                    j = json.loads(m.group(0))
                    if isinstance(j, dict) and j.get("step"):
                        cands.append(j)
                except Exception:
                    pass
            # small models often list several options: a grounded "done" wins, then the first actionable step
            screen = self._screen_text(seen).lower()
            for j in cands:
                if j.get("step") == "done" and self._grounded(str(j.get("answer", "")), screen, goal):
                    return j
            for j in cands:
                if j.get("step") in ("click", "type") and self._on_screen(str(j.get("target", "")), seen):
                    return j
            for j in cands:
                if j.get("step") in ("scroll", "back", "open", "ask", "stop"):
                    return j
            if cands:
                j = cands[0]
                if j.get("step") == "done":
                    return {"step": "stop", "reason": "the answer I wanted to give is not on the screen (I don't guess)"}
                return j
        except Exception as e:
            self.log("operator_think_failed", error=str(e)[:100])
        return {"step": "stop", "reason": "I could not decide the next step"}

    @staticmethod
    def _lost(goal, before, after):
        """True when the page before the click mentioned the goal's words and the new one mentions none of them (a wrong turn)."""
        if not before or not after or after.get("url") == before.get("url"):
            return False
        stop = {"the", "and", "for", "what", "which", "when", "does", "how", "many", "find", "out", "tell", "with", "from", "this", "that",
                "are", "was", "were", "has", "have", "who", "where", "why", "much", "there", "about", "into", "page", "site", "open", "click",
                "put", "one", "its", "then", "please", "add", "cart", "buy", "now", "search", "first", "sentence", "article", "product", "price", "cost"}
        keys = {w for w in re.findall(r"[a-z]{4,}", goal.lower()) if w not in stop}
        if not keys:
            return False
        txt_b = (before.get("fulltext") or before.get("elements") or "").lower() + " ".join((l or "").lower() for _, l, _ in before.get("items", []))
        txt_a = (after.get("fulltext") or after.get("elements") or "").lower() + " ".join((l or "").lower() for _, l, _ in after.get("items", []))
        hits_b = sum(1 for k in keys if k in txt_b)
        hits_a = sum(1 for k in keys if k in txt_a)
        return hits_b >= 1 and hits_a == 0

    @staticmethod
    def _is_question(goal):
        g = goal.strip().lower()
        return bool(re.match(r"^(what|which|when|where|who|how|why|is|are|does|do|can|find out|find|tell me|check|look up|read|list|show me|summari[sz]e|count)\b", g)) or g.endswith("?")

    def _try_answer(self, goal, seen):
        """Question goals: answer from the screen text only; '' when it is not there."""
        full = seen.get("fulltext") or ""
        screen = self._relevant(goal, full) if len(full) > 3000 else self._screen_text(seen)
        screen = re.sub(r"[ \t]{2,}", " ", re.sub(r"\[\s*\d+\s*\]\s*", "", screen))     # drop [n] element numbers: they confuse the reader
        screen = "\n".join(l for l in screen.splitlines()
                           if not re.match(r"^\s*(From Wikipedia|This article (needs|is about)|\(Redirected from|For other uses|Find sources:|Jump to|See our advice|Not to be confused)", l))
        # menu links and field values are not part of the page text but often carry the answer ("Cart (2)", "Quantity: 1")
        keys = {w for w in re.findall(r"[a-z0-9]{3,}", goal.lower())}
        extra = []
        for n, label, role in seen.get("items") or []:
            lab = (label or "").strip()
            if lab and any(k in lab.lower() for k in keys) and lab not in screen:
                extra.append(lab[:60])
        if extra:
            screen += "\nMenu / links on the page: " + ", ".join(extra[:12])
        if len(screen) < 40:
            return ""
        try:
            raw = self.planner.chat("You are a careful reader. Use only the given text. Never add outside knowledge.",
                                    f"TEXT:\n{screen[:3000]}\n\nUsing only the TEXT above: {goal}\nAnswer in one short sentence, quoting the exact words and figures from the text.",
                                    max_tokens=70, timeout=200)
        except Exception as e:
            self.log("operator_read_failed", error=str(e)[:80])
            return ""
        raw = raw.strip().splitlines()[0].strip().strip('"') if raw.strip() else ""
        if not raw or re.search(r"\b(not on screen|does not|doesn't|do not|no information|not mention|not provide|not specif|not state|not say|cannot be determined|unknown|unclear)\b", raw, re.I):
            return ""
        if re.search(r"\b(how many|how much|price|cost|when|year|date|number of|count)\b", goal.lower()) and not re.search(r"\d", raw):
            return ""                                               # a counting/price/date question needs a figure
        return raw if self._grounded(raw, screen.lower(), goal) else ""

    def _new_text(self, before, after):
        """Lines that appeared on the screen since `before` (what my last action changed)."""
        old = set(l.strip() for l in self._screen_text(before).splitlines()) if before else set()
        new = [l.strip() for l in self._screen_text(after).splitlines() if l.strip() and l.strip() not in old]
        new = [re.sub(r"\[\d+\]\s*", "", l) for l in new]
        return " | ".join(new)[:600]

    OUTCOME = [(r"\b(buy|purchase|order)\b", r"\b(order (?:placed|confirmed|number|complete)|thank you for your (?:order|purchase)|paid|payment (?:received|complete)|receipt|confirmation)\b"),
               (r"\b(cart|basket|bag)\b", r"\b(added to (?:cart|basket|bag)|in your (?:cart|basket|bag)|cart \(\d+\)|item added)\b"),
               (r"\b(subscribe|sign up|newsletter)\b", r"\b(subscribed|thank you|check your (?:e-?mail|inbox)|confirm)\b"),
               (r"\b(send|post|publish|submit|reply)\b", r"\b(sent|posted|published|submitted|thank you|received|delivered)\b")]

    def _verify(self, goal, action, before, after):
        """Action goals: did my last action finish the goal? Judged only by what newly appeared. Returns that text or ''."""
        new = self._new_text(before, after)
        if not new:
            return ""
        for goal_pat, proof_pat in self.OUTCOME:                       # "bought" needs an order confirmation, not just "added to cart"
            if re.search(goal_pat, goal, re.I):
                if not re.search(proof_pat, new, re.I):
                    return ""
                break
        try:
            raw = self.planner.chat("You judge whether a task is complete. Answer YES or NO.",
                                    f"I {action}. New text appeared on the screen:\n\"{new}\"\n\nMy task was: {goal}\nIs the task now done? Answer YES or NO.",
                                    max_tokens=5, timeout=200)
        except Exception:
            return ""
        return new if raw.strip().upper().startswith("YES") else ""

    @staticmethod
    def _relevant(goal, text, limit=2500):
        """The parts of a long page that best match the goal's rarer words (page order kept, neighbours included)."""
        lines = []
        for l in text.splitlines():
            l = l.strip()
            if not l:
                continue
            if len(l) > 300:                                            # long paragraphs → sentences
                lines.extend(x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", l) if x.strip())
            else:
                lines.append(l)
        if sum(len(l) for l in lines) <= limit:
            return "\n".join(lines)
        stop = {"the", "and", "for", "what", "which", "when", "does", "how", "many", "find", "out", "tell", "with", "from", "this",
                "that", "are", "was", "were", "has", "have", "who", "where", "why", "much", "there", "about", "into", "page", "site"}
        keys = {w for w in re.findall(r"[a-z0-9]{3,}", goal.lower()) if w not in stop}
        lows = [l.lower() for l in lines]
        df = {k: sum(1 for low in lows if k in low) for k in keys}      # rare goal words weigh more ("founded" ≫ "etsy")
        scored = []
        for i, low in enumerate(lows):
            sc = sum(1.0 / df[k] for k in keys if df[k] and k in low)
            scored.append((sc, i))
        keep, size = set(), 0
        # always keep the opening of the page (title + first real paragraph): "first sentence", "what is this page" goals
        for i, l in enumerate(lines[:40]):
            if size > 700:
                break
            if len(l) > 60 or i < 3:
                keep.add(i)
                size += len(l) + 1
        for sc, i in sorted(scored, key=lambda x: (-x[0], x[1])):
            if sc <= 0:
                break
            for j in (i, i - 1, i + 1):                                 # the neighbour often holds the value ("Founded" / "June 18, 2005")
                if 0 <= j < len(lines) and j not in keep and size + len(lines[j]) <= limit:
                    keep.add(j)
                    size += len(lines[j]) + 1
            if size >= limit - 40:
                break
        return "\n".join(lines[i] for i in sorted(keep))

    @staticmethod
    def _similar(a, b):
        wa = set(re.findall(r"[a-z]{4,}", a.lower()))
        wb = set(re.findall(r"[a-z]{4,}", b.lower()))
        return bool(wa) and len(wa & wb) >= max(2, int(0.6 * len(wa)))

    @staticmethod
    def _grounded(answer, screen, goal=""):
        """A 'done' answer must have its numbers/years and most of its long words on the screen (words echoed from the goal don't count)."""
        def norm(t):                                   # "12.90" == "12,90" == "12 90"; "1,000" == "1000"
            return re.sub(r"[.,\s]", "", t)
        screen_nums = {norm(n) for n in re.findall(r"\d[\d.,\s]*\d|\d", screen)}
        nums = [norm(n) for n in re.findall(r"\d[\d.,]*\d|\d", answer)]
        if nums and not all(n in screen_nums or n in norm(screen) for n in nums):
            return False
        stop = ("found", "there", "which", "about", "their", "these", "those", "answer", "shows", "screen", "contains", "costs", "pieces", "piece",
                "according", "states", "total", "price", "amount", "number", "years", "around", "approximately", "including", "currently")
        goal_words = set(re.findall(r"[a-z]{5,}", goal.lower()))
        words = [w for w in re.findall(r"[a-z]{5,}", answer.lower()) if w not in stop and w not in goal_words]
        if not words:
            return bool(nums) or bool(goal_words & set(re.findall(r"[a-z]{5,}", answer.lower())))
        return sum(1 for w in words if w in screen) >= max(1, int(0.6 * len(words)))

    def _on_screen(self, target, seen):
        want = target.lower().strip()
        if not want:
            return False
        if seen.get("items"):
            return any(want in (lab or "").lower() or (lab or "").lower() in want for _, lab, _ in seen["items"] if lab)
        return any(want in l["text"].lower() for l in seen.get("lines", []))

    # ---- act -------------------------------------------------------------------------------
    def _browser_open(self, url):
        try:
            return self.tasks.on_hands(lambda: (self.tasks.browser().open(url), "opened")[1], timeout=60)
        except Exception as e:
            return f"could not open: {str(e)[:80]}"

    def _element_number(self, seen, target):
        """Find the [n] of the page element whose label best matches target (browser mode)."""
        want = re.sub(r"\s+", " ", target.lower()).strip(" .")
        best, best_n = 0, None
        for n, label, role in seen.get("items", []):
            txt = re.sub(r"\s+", " ", (label or "").lower()).strip(" .")
            if not txt or n is None:
                continue
            if txt == want:
                return n
            if want in txt or txt in want:
                sc = min(len(want), len(txt)) / max(len(want), len(txt))
                if sc > best:
                    best, best_n = sc, n
        if best >= 0.3:
            return best_n
        # last resort: word overlap (the model paraphrased "Reusable make-up pads — € 8,90" as "Reusable make-up pads product")
        ww = set(re.findall(r"[a-z0-9]{3,}", want))
        cand = []
        for n, label, role in seen.get("items", []):
            tw = set(re.findall(r"[a-z0-9]{3,}", (label or "").lower()))
            if ww and tw and len(ww & tw) >= max(2, int(0.7 * min(len(ww), len(tw)))):
                cand.append((len(ww & tw) / len(ww | tw), n))
        if len(cand) == 1 or (cand and sorted(cand)[-1][0] > 0.5):
            return sorted(cand)[-1][1]
        return None

    def _act_click(self, where, target, seen, approved=False):
        if where == "browser":
            n = self._element_number(seen, target)
            if n is None:
                return f"'{target}' is not a clickable element on this page"
            def do(b):
                b.allow_actions = approved
                try:
                    return b.click(n)
                finally:
                    b.allow_actions = False
            try:
                r = self.tasks.on_hands(lambda: do(self.tasks.browser()), timeout=60)
                return str(r)[:160] if r else f"clicked '{target}'"
            except Exception as e:
                return f"click failed: {str(e)[:80]}"
        self.desktop.allow_actions = approved
        try:
            return self.desktop.click_text(target)
        finally:
            self.desktop.allow_actions = False

    def _act_type(self, where, target, text, enter, seen, approved=False, field_n=None):
        if any(k in text.lower() for k in ("password", "token", "cvv")):
            return "refused: I don't type passwords or card details"
        if where == "browser":
            n = field_n if field_n is not None else (self._field_number(seen, target) or self._element_number(seen, target))
            if n is None:
                return f"'{target}' is not a field on this page"
            try:
                r = self.tasks.on_hands(lambda: self.tasks.browser().type(n, text, enter=enter), timeout=60)
                return str(r)[:160] if r else f"typed into '{target}'"
            except Exception as e:
                return f"typing failed: {str(e)[:80]}"
        self.desktop.allow_actions = approved
        try:
            r = self.desktop.click_text(target)
        finally:
            self.desktop.allow_actions = False
        if r.startswith("could not") or r.startswith("refused"):
            return r
        return self.desktop.type(text, enter=enter)

    def _act_scroll(self, where, direction):
        if where == "browser":
            try:
                self.tasks.on_hands(lambda: self.tasks.browser().scroll(direction, 1), timeout=30)
                return f"scrolled {direction}"
            except Exception as e:
                return f"scroll failed: {str(e)[:60]}"
        return self.desktop.scroll(down=(direction != "up"))

    def _act_back(self, where):
        if where == "browser":
            try:
                self.tasks.on_hands(lambda: self.tasks.browser().back(), timeout=30)
                return "went back"
            except Exception as e:
                return f"back failed: {str(e)[:60]}"
        return self.desktop.key("alt+Left")

    def _finish(self, text, t0, steps=0):
        self.log("operator_done", steps=steps, secs=int(time.time() - t0))
        trail = "\n".join(f"  {i+1}. {h}" for i, h in enumerate(self.history[-8:]))
        return text + (f"\n\nWhat I did ({steps} steps, {int(time.time() - t0)} s):\n{trail}" if trail else "")
