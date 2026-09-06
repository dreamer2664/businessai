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
import contextlib
import re
import threading
import time
import urllib.parse

from . import config
from .browser import Browser, BrowserError

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

    def __init__(self, log=None, notify=None, brain=None, viewer=None):
        self.log = log or (lambda kind, **f: None)
        self.notify = notify or (lambda text: None)
        self.brain = brain
        self.viewer = viewer
        self._browser = None
        self._lock = threading.Lock()

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
            self.close_browser()
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
        for title, url, ks in opened:
            report.append(f"\n{title}\n{url}\n" + "\n".join(f"• {s}" for s in ks))
        report.append(f"\n({len(opened)} pages read in {time.time() - t0:.0f}s)")
        return "\n".join(report)

    def summarize(self, url, max_points=8):
        with self._session() as b:
            if url.lower().endswith(".pdf"):
                text = b.download_text(url); title = url
            else:
                b.open(url)
                if b.status() != "ok":
                    return f"{url}: page shows a {b.status()} wall — I stopped (I don't pass CAPTCHAs/logins)."
                title = b.page.title(); text = b.extract_text()
        heads = [h for h in (clean(l).strip("# ").strip() for l in text.split("\n") if l.startswith("#")) if 3 < len(h) < 80][:12]
        topic = " ".join(re.findall(r"[A-Za-z]+", title)[:6])
        ks = key_sentences(text, topic, limit=max_points) or key_sentences(text, " ".join(heads[:3]), limit=max_points)
        out = [f"Summary of: {title}", url]
        if heads:
            out.append("Sections: " + " | ".join(heads))
        out += [f"• {s}" for s in ks] or ["(no clear key sentences found — page may be mostly images/scripts)"]
        out.append(f"({len(text)} characters read)")
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
        return "\n".join(out)

    def exam(self, bank, n=40):
        from .mcq import run_bank
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok, tot = run_bank(bank, n=n)
        return f"Exam {bank.split('/')[-1]}: {ok}/{tot} correct ({100*ok/max(1,tot):.0f}%) — offline, knowledge brain only.\n{buf.getvalue().strip()}"

    # ---- dispatcher ----------------------------------------------------
    def run(self, command):
        """'research <topic>' | 'compare <product>' | 'summarize <url>' | 'exam [n]'"""
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
            elif cmd == "exam":
                n = int(arg) if arg.strip().isdigit() else 40
                out = self.exam(str(config.ROOT / "tests/banks/mcq_principles-marketing.jsonl"), n)
            else:
                out = "Tasks I can do: research <topic> · compare <product> · summarize <url> · exam [n]"
        except Exception as e:  # noqa
            out = f"Task failed: {type(e).__name__}: {str(e)[:200]}"
        self.log("task_done", cmd=cmd, ms=int((time.time() - t0) * 1000), chars=len(out))
        return out
