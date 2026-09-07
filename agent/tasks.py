"""Read-only browsing tasks (milestone 2): research jobs the agent runs by itself in
its own browser and reports back. No planner model yet — each task is a small,
deterministic procedure built on Browser + the knowledge brain:

  research(topic)            search → open the best 3 non-forum pages → extract the
                             definitions/steps/numbers → short report with sources
  compare_suppliers(product) search supplier directories → collect names, claims,
                             prices/shipping mentions → table
  summarize(url)             open a page or PDF and return the key points
  exam(bank, n)              sit an offline MCQ bank (agent/mcq.py) and report the score

Every task returns a text report; run_task() also logs and can notify the owner.
"""
import concurrent.futures
import contextlib
import re
import threading
import time
import urllib.parse

from . import config
from .browser import Browser, BrowserError
from . import video

FORUM = re.compile(r"reddit\.com|quora\.com|facebook\.com|youtube\.com|tiktok\.com|instagram\.com|pinterest\.|x\.com|twitter\.com|linkedin\.com/posts", re.I)
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def clean(text):
    """Strip the browser's element numbers ([12]) and bullets from extracted text."""
    return re.sub(r"\s*\[\d+\]\s*", " ", text)


def key_sentences(text, topic, limit=6):
    """Pick sentences that define or quantify the topic: contain topic words + a definition/number cue."""
    text = clean(text)
    tw = set(w[:6] for w in re.findall(r"[a-z0-9]+", topic.lower()) if len(w) > 2)
    out, seen = [], set()
    for para in text.split("\n"):
        para = para.strip("•# ").strip()
        if len(para) < 60 or para.lower().startswith(("cookie", "we use", "sign up", "subscribe", "©")):
            continue
        for s in SENT.split(para):
            s = s.strip()
            if not (60 <= len(s) <= 320):
                continue
            sw = set(w[:6] for w in re.findall(r"[a-z0-9]+", s.lower()))
            hit = len(tw & sw)
            cue = bool(re.search(r"\b(is|are|means|refers|typically|usually|average|percent|%|\d+|should|steps?|because|costs?)\b", s, re.I))
            if hit >= max(1, len(tw) // 2) and cue and s[:60].lower() not in seen:
                if re.match(r"^(home|blog|guide|complete guide|what's|what is)\b", s, re.I) and not re.search(r"\d", s):
                    continue                      # breadcrumb / headline echo, not a fact
                if re.search(r"\b(click here|sign up|my (course|program)|i found|let me be upfront|alternative that delivers)\b", s, re.I):
                    continue                      # sales pitch
                seen.add(s[:60]); out.append((bool(re.search(r"\d", s)) + bool(re.search(r"\b(is|are|means|refers)\b", s)), s))
    out.sort(key=lambda x: -x[0])
    return [s for _, s in out[:limit]]


class Tasks:
    IDLE_CLOSE = 600          # seconds; the browser window stays open between tasks, then closes itself

    @staticmethod
    def _mem_available_mb():
        try:
            for line in open("/proc/meminfo"):
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
        except Exception:
            pass
        return 99999

    def _release_page(self):
        """Before thinking: park the page (normal) or close the browser (low-memory machines, < 2.5 GB available)."""
        b = self._browser
        if b is None or not b.alive():
            return
        if self.low_mem:
            self.close_browser()
        else:
            b.park()

    def __init__(self, log=None, notify=None, brain=None, viewer=None, planner=None, memory=None, eyes=None):
        self.log = log or (lambda kind, **f: None)
        self.eyes = eyes
        self.notify = notify or (lambda text: None)
        self.brain = brain
        self.viewer = viewer
        self.planner = planner
        self.memory = memory
        self._browser = None
        self._lock = threading.Lock()
        self.low_mem = self._mem_available_mb() < 2500
        if self.low_mem:
            self.log("low_memory_mode", available_mb=self._mem_available_mb())
        # Playwright's sync API is bound to the thread that created the browser, so ALL browser work runs on
        # this one long-lived "hands" thread; public methods submit to it and wait.
        self._hands = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="hands")

    def on_hands(self, fn, *a, timeout=None, **kw):
        """Run fn(*a, **kw) on the hands thread and return its result (callable from any thread)."""
        if threading.current_thread().name.startswith("hands"):
            return fn(*a, **kw)
        return self._hands.submit(fn, *a, **kw).result(timeout=timeout)

    def screenshot(self):
        """JPEG bytes of the current tab, or None when the browser is closed."""
        def _shot():
            b = self._browser
            if not (b and b.alive()):
                return None
            return b.page.screenshot(type="jpeg", quality=60, timeout=6000), b.page.title()[:80], b.page.url
        return self.on_hands(_shot, timeout=20)

    # ---- one browser, reused (so the owner can watch one window instead of a flicker of new ones) ----
    def browser(self):
        if self._browser is None or not self._browser.alive():
            self._browser = Browser(log=self.log, viewer=self.viewer)
        return self._browser

    def close_browser(self):
        if self._browser is not None:
            try:
                self._browser.close()
            finally:
                self._browser = None

    def tick(self):
        """Call periodically: closes the browser after IDLE_CLOSE seconds without a task."""
        b = self._browser
        if b is not None and not self._lock.locked() and time.time() - b.last_used > self.IDLE_CLOSE:
            self._hands.submit(self.close_browser)
            self.log("session_closed")

    @contextlib.contextmanager
    def _session(self):
        with self._lock:
            b = self.browser()
            try:
                yield b
            except Exception:
                self.close_browser()          # a broken browser is not reused
                raise

    # ---- tasks ---------------------------------------------------------
    def research(self, topic, n_pages=3):
        t0 = time.time()
        report = [f"Research: {topic}"]
        # 1) what the local pack already knows
        if self.brain and self.brain.ready:
            local = self.brain.ask(topic)
            if local:
                report.append("From my knowledge pack:\n" + local)
        # 2) the web
        opened = []
        with self._session() as b:
            try:
                results = b.search_results(topic, 12)
            except BrowserError as e:
                return "\n".join(report + [f"(web search failed: {e})"])
            for r in results:
                if len(opened) >= n_pages or FORUM.search(r["url"]):
                    continue
                try:
                    b.open(r["url"])
                    st = b.status()
                    if st != "ok":
                        self.log("task_wall", url=r["url"], wall=st); continue
                    text = b.extract_text()
                except BrowserError:
                    continue
                ks = key_sentences(text, topic)
                if ks:
                    opened.append((b.page.title()[:80] or r["url"], r["url"], ks))
        brief = None
        self._release_page()
        if opened and self.planner and self.planner.installed():
            try:
                brief = self.planner.brief(topic, opened)
            except Exception as e:
                self.log("brief_failed", error=str(e)[:100])
        if brief:
            report = [f"Research: {topic}\n\n{brief}", "\nPages I read:"] + [f"[{i+1}] {t} — {u}" for i, (t, u, _) in enumerate(opened)]
        else:
            for title, url, ks in opened:
                report.append(f"\n{title}\n{url}\n" + "\n".join(f"• {s}" for s in ks))
        report.append(f"({len(opened)} pages read in {time.time() - t0:.0f}s)")
        out = "\n".join(report)
        if self.memory and opened:
            self.memory.note("research", topic, brief or out, [u for _, u, _ in opened])
        return out

    def summarize(self, url, max_points=8):
        with self._session() as b:
            if url.lower().endswith(".pdf"):
                text = b.download_text(url); title = url
            else:
                b.open(url)
                if b.status() != "ok":
                    return f"{url}: page shows a {b.status()} wall — I stopped (I don't pass CAPTCHAs/logins)."
                title = b.page.title(); text = b.extract_text()
        self._release_page()
        heads = [h for h in (clean(l).strip("# ").strip() for l in text.split("\n") if l.startswith("#")) if 3 < len(h) < 80][:12]
        topic = " ".join(re.findall(r"[A-Za-z]+", title)[:6])
        ks = key_sentences(text, topic, limit=max_points) or key_sentences(text, " ".join(heads[:3]), limit=max_points)
        out = [f"Summary of: {title}", url]
        if heads:
            out.append("Sections: " + " | ".join(heads))
        if self.planner and self.planner.installed() and len(text) > 200:
            try:
                summary = self.planner.chat(
                    "You summarize web pages for a busy store owner. Plain words, no fluff.",
                    f"PAGE: {title}\n\n{clean(text)[:6000]}\n\nGive: one sentence on what the page is, then 3-6 bullet points with the most useful concrete facts (numbers, steps, warnings).",
                    max_tokens=260)
                out.append(summary)
                out.append(f"({len(text)} characters read)")
                res = "\n".join(out)
                if self.memory:
                    self.memory.note("summary", title or url, summary, [url])
                return res
            except Exception as e:
                self.log("summary_failed", error=str(e)[:100])
        out += [f"• {s}" for s in ks] or ["(no clear key sentences found — page may be mostly images/scripts)"]
        out.append(f"({len(text)} characters read)")
        if self.memory:
            self.memory.note("summary", title or url, "\n".join(ks), [url])
        return "\n".join(out)

    def compare_suppliers(self, product, n_pages=3):
        rows = []
        with self._session() as b:
            queries = [f"{product} dropshipping supplier", f"{product} wholesale supplier Europe"]
            seen = set()
            for q in queries:
                try:
                    results = b.search_results(q, 10)
                except BrowserError:
                    continue
                for r in results:
                    if r["url"] in seen or FORUM.search(r["url"]) or len(rows) >= n_pages * 2:
                        continue
                    seen.add(r["url"])
                    try:
                        b.open(r["url"])
                        if b.status() != "ok":
                            continue
                        text = b.extract_text()
                    except BrowserError:
                        continue
                    dom = urllib.parse.urlparse(r["url"]).netloc.replace("www.", "")
                    prices = re.findall(r"(?:€|\$|£)\s?\d+(?:[.,]\d+)?", text)[:5]
                    ship = re.findall(r"\b\d+\s?(?:-|to)\s?\d+\s?(?:business )?days\b", text, re.I)[:3]
                    moq = re.findall(r"\bMOQ\b[^.]{0,60}|\bminimum order[^.]{0,60}", text, re.I)[:2]
                    kind = "directory/list" if re.search(r"\b(best|top \d+|list of)\b", (b.page.title() or ""), re.I) else "supplier/site"
                    rows.append((dom, kind, (b.page.title() or "")[:70], ", ".join(prices) or "-", ", ".join(ship) or "-", "; ".join(m.strip() for m in moq) or "-"))
        if not rows:
            return f"Supplier comparison for {product}: nothing readable found (search blocked or pages behind walls)."
        out = [f"Supplier comparison: {product}", "site | kind | page | prices seen | shipping times | MOQ notes"]
        out += [" | ".join(r) for r in rows]
        out.append("Note: read-only research; nothing was contacted or ordered.")
        if self.memory:
            self.memory.note("suppliers", product, "\n".join(out[2:-1]), [f"https://{r[0]}" for r in rows])
        return "\n".join(out)

    def exam(self, bank, n=40, seed=1):
        """Sit n questions. Retrieval solver first; the thinking model (with the retrieved passages as evidence) decides."""
        import json as _json, random
        from .mcq import MCQSolver
        qs = [_json.loads(l) for l in open(bank, encoding="utf-8") if l.strip()]
        random.seed(seed)
        qs = random.sample(qs, min(n, len(qs)))
        S = MCQSolver()
        use_llm = bool(self.planner and self.planner.installed())
        ok = ok_ret = 0
        t0 = time.time()
        for i, q in enumerate(qs):
            idx, conf, _ = S.answer(q["q"], q["choices"])
            ok_ret += idx == q["answer"]
            if use_llm:
                d = S.brain(q["q"])
                ev = "\n".join(f"[{h.get('title', '')}] {h.get('text', '')}" for h in d.get("hits", [])[:5])
                try:
                    li, lconf, _ = self.planner.mcq(q["q"], q["choices"], ev + f"\n(retrieval solver suggests {'ABCDEFGH'[idx]}, confidence {conf:.2f})")
                    idx = li
                except Exception:
                    pass
            ok += idx == q["answer"]
            if self.viewer:
                self.viewer.task = f"exam {i+1}/{len(qs)} — {ok} right so far"
        mode = "thinking model + knowledge brain" if use_llm else "knowledge brain only"
        return (f"Exam {bank.split('/')[-1]}: {ok}/{len(qs)} correct ({100*ok/len(qs):.0f}%) — {mode}, {time.time()-t0:.0f}s.\n"
                f"(retrieval alone would have scored {ok_ret}/{len(qs)})")

    def ask(self, question):
        """Answer from what I already know (knowledge pack + my notes), written by the thinking model."""
        ev, titles = [], []
        if self.brain and self.brain.ready:
            hits = []
            for pack in self.brain.refresh():
                d = self.brain.ask_raw(question, pack) or {}
                for h in d.get("hits", [])[:5]:
                    h["_pack"] = pack.rsplit("/", 1)[-1]
                    hits.append(h)
            hits.sort(key=lambda h: -float(h.get("score", 0)))
            for h in hits[:6]:
                tag = " (learned by me)" if h["_pack"].startswith("learned") else ""
                ev.append(f"[{h.get('title', '')}{tag}] {h.get('text', '')}")
                titles.append(h.get("title", ""))
        if self.memory:
            rec = self.memory.recall(question)
            if rec:
                ev.append(rec)
        if not ev:
            return None
        if self.planner and self.planner.installed():
            try:
                return self.planner.answer(question, "\n".join(ev))
            except Exception as e:
                self.log("answer_failed", error=str(e)[:100])
        return self.brain.ask(question) if self.brain and self.brain.ready else None

    SITES = {"youtube": "https://www.youtube.com/feed/trending", "amazon": "https://www.amazon.com/gp/bestsellers",
             "ebay": "https://www.ebay.com/trending", "etsy": "https://www.etsy.com/trending", "aliexpress": "https://www.aliexpress.com",
             "shopify": "https://www.shopify.com", "google trends": "https://trends.google.com/trending?geo=US",
             "reddit": "https://www.reddit.com/r/dropship/", "tiktok": "https://www.tiktok.com/discover",
             "temu": "https://www.temu.com", "alibaba": "https://www.alibaba.com", "product hunt": "https://www.producthunt.com"}

    NEEDS_LOGIN = {"youtube": "YouTube hides its trending/recommendation feeds from visitors without an account or cookies",
                   "tiktok": "TikTok shows nothing to a browser without an account", "reddit": "Reddit blocks automated browsers"}

    def _look_at_page(self, shot, question=None):
        """Eyes on a screenshot when the page text is useless: OCR lines + one vision answer. '' if the eyes are off."""
        if not (self.eyes and shot):
            return ""
        try:
            d = self.eyes.describe(shot)
            if d["kind"] in ("captcha", "login") or any(w in ("captcha", "login wall") for w in d["warnings"]):
                return f"it shows a {d['kind'] if d['kind'] in ('captcha', 'login') else 'login'} wall — I stopped (I never pass CAPTCHAs or log in)."
            parts = [f"• {d['summary']}" if d["summary"] else ""]
            words0 = " ".join(l["text"].lower() for l in self.eyes.lines(shot)) if self.eyes.ocr else ""
            if re.search(r"try searching to get started|start watching videos", words0):
                return ("YouTube shows me an empty home page ('Try searching to get started') because I'm not signed in — there is no "
                        "trending list on it. Ask me to /watch <topic> instead: I search videos directly and read their captions.")
            if question:
                ans = self.eyes.look(shot, question + " Answer only from what is visible; say 'not visible' if it is not on the screen.", max_tokens=140)
                if ans:
                    parts.append(f"• {ans}")
            words = self.eyes.lines(shot) if self.eyes.ocr else []
            good = [l["text"] for l in words if len(l["text"]) > 12][:10]
            if good:
                parts.append("• Text I can read on it: " + " | ".join(good)[:600])
            parts.append("(seen with my eyes, not read from the page — treat as approximate)")
            return "\n".join(p for p in parts if p)
        except Exception as e:
            self.log("look_failed", error=str(e)[:100])
            return ""

    def visit(self, site, question=""):
        """Go to a site (name or URL), read what is on it, and answer the owner's question from the page — grounded."""
        key = site.lower().strip(" .?")
        url = site if re.match(r"^https?://", site) else self.SITES.get(key) or self.SITES.get(key.replace("the ", "")) or None
        if not url:
            url = "https://" + re.sub(r"[^a-z0-9.-]", "", key) + ("" if "." in key else ".com")
        with self._session() as b:
            try:
                b.open(url)
            except BrowserError as e:
                return f"I couldn't open {url}: {e}"
            st = b.status()
            title, final = b.page.title(), b.page.url
            if st != "ok":
                return f"I opened {final} but it shows a {st} wall, so I stopped (I never pass CAPTCHAs or log in). Screenshot: /screen"
            text = clean(b.extract_text())
            if len(text) < 300:
                b.scroll("down", 2)
                text = clean(b.extract_text())
            lines = [l.strip(" #•") for l in text.splitlines() if len(l.strip(" #•")) > 2]
            thin = len(lines) < 8 or bool(re.search(r"try searching to get started|start watching videos|sign in to|log in to see", text, re.I))
            shot = b.page.screenshot(type="png", timeout=8000) if (thin and self.eyes) else None
        self._release_page()
        page = "\n".join(lines)[:3500]
        note = self.NEEDS_LOGIN.get(key.split()[0]) if key.split() else None
        if thin:
            seen = self._look_at_page(shot, question) if shot else ""
            if seen:
                out = f"{title} — {final}\n\nThe page text is empty for me, so I looked at the screen instead:\n{seen}"
            else:
                out = (f"{title} — {final}\n\nThe page shows almost nothing to me" + (f": {note}." if note else " (empty or script-only page).") +
                       " I won't guess at its contents. Screenshot: /screen")
            if self.memory:
                self.memory.note("visit", f"{site}: {question}"[:120], out, [final])
            return out
        if self.planner and self.planner.installed():
            try:
                q = question or "What is on this page? List the main items or headlines."
                ans = self.planner.chat(
                    "You read a web page for your owner and answer ONLY with items that appear word-for-word in the page text. "
                    "Number the items. If the page text does not contain what was asked, reply exactly: NOT ON PAGE",
                    f"PAGE TITLE: {title}\nURL: {final}\nPAGE TEXT:\n{page}\n\nOWNER ASKED: {q}", max_tokens=220, timeout=150)
                # grounding check: every listed item must really occur in the page text
                low = page.lower()
                items = [re.sub(r"^\d+[.)]\s*", "", l).strip(" \"'") for l in ans.splitlines() if re.match(r"^\d+[.)]", l.strip())]
                bad = [i for i in items if len(i) > 3 and i.lower()[:40] not in low]
                if "NOT ON PAGE" in ans or (items and len(bad) > len(items) // 2):
                    ans = ("What was asked is not on this page as I see it" + (f" ({note})" if note else "") +
                           ". Here is what the page actually shows:\n" + "\n".join(f"• {l}" for l in lines[:12]))
                out = f"{title} — {final}\n\n{ans}"
            except Exception as e:
                self.log("visit_answer_failed", error=str(e)[:100])
                out = f"{title} — {final}\n\n" + "\n".join(f"• {l}" for l in lines[:25])
        else:
            out = f"{title} — {final}\n\n" + "\n".join(f"• {l}" for l in lines[:25])
        if self.memory:
            self.memory.note("visit", f"{site}: {question}"[:120], out, [final])
        return out

    def watch(self, what, n_videos=1):
        """'Watch' a video (URL/id) or the best video for a topic by reading its captions; summarize with the model."""
        vid = video.url_id(what)
        if vid:
            picks = [{"id": vid, "title": ""}]
        else:
            try:
                picks = [v for v in video.search(what, 8) if v["id"]][:n_videos + 3]
            except Exception as e:
                return f"YouTube search failed: {str(e)[:100]}"
            if not picks:
                return f"No videos found for '{what}'."
        out, done = [], 0
        for v in picks:
            if done >= n_videos:
                break
            try:
                text, meta = video.transcript(v["id"])
            except Exception as e:
                self.log("transcript_error", id=v["id"], error=str(e)[:100])
                continue
            title = meta.get("title") or v.get("title") or v["id"]
            url = f"https://www.youtube.com/watch?v={v['id']}"
            if len(text) < 400:
                self.log("video_no_captions", id=v["id"])
                continue
            done += 1
            mins = meta.get("seconds", 0) // 60
            head = f"▶ {title} — {meta.get('channel', '')} ({mins} min, {'auto' if meta.get('auto') else 'human'} captions)\n{url}"
            summary = None
            if self.planner and self.planner.installed():
                self._release_page()
                try:
                    summary = self.planner.chat(
                        "You watched a business video for your owner (you have its transcript). Plain words, no hype.",
                        f"TITLE: {title}\nTRANSCRIPT (may be auto-generated, no punctuation):\n{text[:7000]}\n\n"
                        "Give: one sentence on what the video is about, then 4-6 bullet points with the concrete, useful claims "
                        "(numbers, steps, warnings). Finish with one line: 'Trust: ' and whether the speaker is selling something.",
                        max_tokens=320, timeout=240)
                except Exception as e:
                    self.log("watch_summary_failed", error=str(e)[:100])
            if not summary:
                summary = "Transcript excerpt: " + text[:900]
            out.append(head + "\n" + summary)
            if self.memory:
                self.memory.note("video", title, summary, [url])
        if not out:
            return f"I found videos for '{what}' but none had readable captions, so I couldn't watch them."
        return "\n\n".join(out)

    def study(self, goal):
        return self.on_hands(self._study, goal)

    def _study(self, goal):
        """One self-directed study session on a learning goal: pick an angle not yet covered, research it, keep the note."""
        angles_done = goal.get("angles", [])
        angle = goal["topic"]
        if self.planner and self.planner.installed():
            try:
                raw = self.planner.chat("You plan research for a small online-store owner. Output one line only.",
                                        f"Learning goal: {goal['topic']}\nAlready researched angles: {angles_done or 'none'}\n"
                                        "Give ONE new web-search query (max 10 words) about a different aspect of this goal "
                                        "(e.g. costs, how it works, best options, risks, how to start). It MUST keep the goal's key words.",
                                        max_tokens=30, stop=["\n"])
                cand = raw.strip().strip('"')
                keys = [w for w in re.findall(r"[a-z]{4,}", goal["topic"].lower()) if w not in ("with", "from", "about", "that", "this")]
                if cand and sum(k in cand.lower() for k in keys) >= max(1, len(keys) // 2):
                    angle = cand
                else:
                    angle = f"{goal['topic']} " + ["how it works", "costs and pricing", "best options compared", "risks and problems", "how to start", "reviews"][len(angles_done) % 6]
            except Exception:
                pass
        out = self.research(angle)
        self.memory.studied(goal["id"], angle)
        return angle, out

    # ---- dispatcher ----------------------------------------------------
    def run(self, command):
        return self.on_hands(self._run, command)

    def _run(self, command):
        """'research <topic>' | 'compare <product>' | 'summarize <url>' | 'visit <site> [, question]' | 'exam [n]'"""
        cmd, _, arg = command.strip().partition(" ")
        cmd = cmd.lower()
        t0 = time.time()
        self.log("task_start", cmd=cmd, arg=arg)
        try:
            if cmd == "research" and arg:
                out = self.research(arg)
            elif cmd in ("compare", "suppliers") and arg:
                out = self.compare_suppliers(arg)
            elif cmd in ("summarize", "summarise", "read") and arg:
                out = self.summarize(arg)
            elif cmd in ("watch", "video") and arg:
                out = self.watch(arg)
            elif cmd in ("visit", "open", "goto") and arg:
                site, _, question = arg.partition("|")
                out = self.visit(site.strip(), question.strip())
            elif cmd == "exam":
                n = int(arg) if arg.strip().isdigit() else 40
                out = self.exam(str(config.ROOT / "tests/banks/mcq_principles-marketing.jsonl"), n)
            else:
                out = "Tasks I can do: research <topic> · compare <product> · summarize <url> · visit <site> | <question> · watch <video url or topic> · exam [n]"
        except Exception as e:  # noqa
            out = f"Task failed: {type(e).__name__}: {str(e)[:200]}"
        self.log("task_done", cmd=cmd, ms=int((time.time() - t0) * 1000), chars=len(out))
        return out
