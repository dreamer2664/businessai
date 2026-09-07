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
DANGER = re.compile(r"\b(buy|pay|checkout|check out|place order|order now|purchase|confirm|send|post|publish|delete|remove|"
                    r"submit|subscribe|sign in|log in|login|register|agree|accept all|install|download|unsubscribe|"
                    r"transfer|donate|upgrade|start trial|add to cart|add to bag|add to basket)\b", re.I)

THINK_PROMPT = """You operate a computer screen for your owner, one small step at a time.
GOAL: %s

WHAT YOU DID SO FAR:
%s

WHAT IS ON THE SCREEN NOW (%s):
%s

Pick exactly ONE next step and answer with JSON only, no other text:
{"step": "click", "target": "<exact visible text of the button or link>"}
{"step": "type", "target": "<exact visible text of the field or its placeholder>", "text": "<what to type>", "enter": true|false}
{"step": "scroll", "direction": "down"|"up"}
{"step": "back"}
{"step": "open", "url": "https://..."}
{"step": "done", "answer": "<what you found / did, in one or two plain sentences with the concrete facts>"}
{"step": "ask", "question": "<one short question for the owner when you truly cannot decide>"}
{"step": "stop", "reason": "<why you cannot continue, e.g. login wall, captcha, nothing relevant on this page>"}
Rules: ONE object only. First check whether the screen already answers the goal — if yes, answer "done" with the facts
copied from the screen. Click only text that is really on the screen. Never invent facts. Never try to log in, pay or
pass a captcha — "stop" instead. Use "ask" only when two reasonable steps conflict, never to ask the owner the goal itself."""


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
    def run(self, goal, where="browser", start_url=None, allow=None):
        """Work towards `goal`. where: 'browser' | 'desktop'. Returns a plain-language report."""
        self.history = []
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
        while steps < MAX_STEPS:
            steps += 1
            seen = self._see(where)
            if seen.get("wall"):
                return self._finish(f"I stopped at step {steps}: the screen shows a {seen['wall']} — I never pass those. Please do that part yourself; I can continue after.", t0)
            decision = self._think(goal, seen)
            step = decision.get("step", "stop")
            self.log("operator_step", n=steps, step=step, target=str(decision.get("target") or decision.get("url") or decision.get("direction") or "")[:60])
            if step == "done":
                return self._finish(str(decision.get("answer") or "Done."), t0, steps)
            if step == "stop":
                return self._finish(f"I stopped: {decision.get('reason', 'no way forward')}.", t0, steps)
            if step == "ask":
                q = str(decision.get("question") or "How should I continue?")
                if self._similar(q, goal):
                    self.history.append("wanted to ask you the goal itself — continuing on my own")
                    decision = {"step": "scroll", "direction": "down"}
                    step = "scroll"
            if step == "ask":
                ans = self.ask_owner(q, ["Continue", "Stop"]) if self.ask_owner else None
                self.history.append(f"asked you: {q} → {ans}")
                if ans in (None, "Stop"):
                    return self._finish(f"Stopped after asking: {q}", t0, steps)
                continue
            if step == "click":
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
                result = self._act_click(where, target, seen, approved=target.lower() in allow)
            elif step == "type":
                result = self._act_type(where, str(decision.get("target") or ""), str(decision.get("text") or ""), bool(decision.get("enter")), seen)
            elif step == "scroll":
                result = self._act_scroll(where, str(decision.get("direction") or "down"))
            elif step == "back":
                result = self._act_back(where)
            elif step == "open":
                url = str(decision.get("url") or "")
                result = self._browser_open(url) if where == "browser" and url.startswith("http") else "cannot open URLs here"
            else:
                result = f"unknown step {step}"
            self.history.append(f"{step} {decision.get('target') or decision.get('url') or decision.get('direction') or ''} → {result}"[:200])
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

    # ---- see ---------------------------------------------------------------------------------
    def _see(self, where):
        out = {"where": where, "lines": [], "elements": "", "shot": None, "wall": ""}
        if where == "browser":
            def grab(b):
                b.snapshot()
                st = b.status()
                shot = b.page.screenshot(type="png", timeout=8000)
                try:
                    els = b.page.evaluate(_JS_TEXT_NAME)[:3000]
                except Exception:
                    els = b.extract_text()[:3000]
                items = [(it.get("n"), (it.get("label") or "")[:80], it.get("role", "")) for it in (b.items or [])]
                return st, shot, els, b.page.url, b.page.title(), items
            try:
                st, shot, els, url, title, items = self.tasks.on_hands(lambda: grab(self.tasks.browser()), timeout=60)
            except Exception as e:
                out["elements"] = f"(browser error: {str(e)[:80]})"
                return out
            out.update(shot=shot, elements=els, url=url, title=title, items=items)
            if st in ("captcha", "login"):
                out["wall"] = "captcha" if st == "captcha" else "login wall"
        else:
            shot = self.desktop.screenshot("see")
            out["shot"] = shot
        if self.eyes and out["shot"]:
            ls = self.eyes.lines(out["shot"]) if self.eyes.ocr else []
            out["lines"] = ls
            if not out["wall"] and self.eyes.installed() and (where == "desktop" or len(ls) < 6):
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
    def _think(self, goal, seen):
        hist = "\n".join(f"{i+1}. {h}" for i, h in enumerate(self.history[-6:])) or "(nothing yet)"
        prompt = THINK_PROMPT % (goal, hist, seen.get("where", ""), self._screen_text(seen))
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
                if j.get("step") == "done" and self._grounded(str(j.get("answer", "")), screen):
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
    def _similar(a, b):
        wa = set(re.findall(r"[a-z]{4,}", a.lower()))
        wb = set(re.findall(r"[a-z]{4,}", b.lower()))
        return bool(wa) and len(wa & wb) >= max(2, int(0.6 * len(wa)))

    @staticmethod
    def _grounded(answer, screen):
        """A 'done' answer must have its numbers/years and most of its long words on the screen."""
        nums = re.findall(r"\d[\d.,]*", answer)
        if nums and not all(n.strip(".,") in screen for n in nums):
            return False
        words = [w for w in re.findall(r"[a-z]{5,}", answer.lower()) if w not in ("found", "there", "which", "about", "their", "these", "those", "answer", "shows", "screen")]
        if not words:
            return bool(nums)
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
        return best_n if best >= 0.3 else None

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

    def _act_type(self, where, target, text, enter, seen):
        if any(k in text.lower() for k in ("password", "token", "cvv")):
            return "refused: I don't type passwords or card details"
        if where == "browser":
            n = self._element_number(seen, target)
            if n is None:
                return f"'{target}' is not a field on this page"
            try:
                r = self.tasks.on_hands(lambda: self.tasks.browser().type(n, text, enter=enter), timeout=60)
                return str(r)[:160] if r else f"typed into '{target}'"
            except Exception as e:
                return f"typing failed: {str(e)[:80]}"
        r = self.desktop.click_text(target)
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
