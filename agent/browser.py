"""The agent's own browser (eyes + hands), driven by plain commands.

A headless Chromium controlled through Playwright. The agent never sees pixels
unless it asks for a screenshot: every page is rendered as clean, numbered text
("[3] link: Pricing", "[7] button: Add to cart", "[9] textbox: Search …"), and
actions refer to those numbers. That makes browsing reliable on a small CPU,
and every step is logged in readable form.

Rules built in (see docs/PLAN.md):
- Never solves CAPTCHAs or logs in by itself: when it meets one it stops and
  reports (owner is asked through Telegram by the caller).
- Read-only by default: form submission / clicks on pay-or-post-like controls
  require allow_actions=True from the caller (milestone 4+).
- Blocklist: no adult, gambling, or banking domains (BLOCKED).

Commands (Browser methods): open(url), tabs(), switch(i), close_tab(i), read(),
find(text), click(n), type(n, text, enter=False), scroll(dir), back(), forward(),
screenshot(path), search(query), links(), extract_text(), download_text(url).
"""
import json
import os
import re
import time
import urllib.parse

from . import config

BLOCKED = re.compile(r"(porn|xxx|casino|bet365|poker|bank(ing)?\.|paypal\.com/(signin|myaccount))", re.I)
CAPTCHA_HINTS = re.compile(r"(captcha|verify you are human|unusual traffic|are you a robot|cloudflare.*checking your browser|"
                           r"access denied|press and hold)", re.I)
LOGIN_HINTS = re.compile(r"(sign in to continue|log in to continue|please log in|create an account to)", re.I)
MAX_TEXT = 12000          # characters of page text handed to the planner per read()
INTERACTIVE = "a[href], button, input, select, textarea, [role=button], [role=link], [role=tab], [role=menuitem], [onclick], summary"

_JS_SNAPSHOT = r"""
(maxItems) => {
  const seen = new Set(); const items = []; let n = 0;
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const label = (el) => {
    let t = (el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') ||
             el.getAttribute('alt') || el.value || el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
    if (!t && el.tagName === 'INPUT') t = el.name || el.id || el.type || '';
    return t.slice(0, 80);
  };
  const role = (el) => {
    const tag = el.tagName.toLowerCase(); const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'a') return 'link'; if (tag === 'button' || type === 'submit' || type === 'button' || el.getAttribute('role') === 'button') return 'button';
    if (tag === 'input') return (type === 'checkbox' || type === 'radio') ? type : 'textbox';
    if (tag === 'textarea') return 'textbox'; if (tag === 'select') return 'select'; return el.getAttribute('role') || tag;
  };
  document.querySelectorAll('[data-bai]').forEach(e => e.removeAttribute('data-bai'));
  for (const el of document.querySelectorAll(%s)) {
    if (!vis(el)) continue; const lab = label(el); if (!lab && role(el) !== 'textbox') continue;
    const key = role(el) + '|' + lab + '|' + (el.getAttribute('href') || ''); if (seen.has(key)) continue; seen.add(key);
    n += 1; el.setAttribute('data-bai', String(n));
    items.push({n, role: role(el), label: lab, href: el.tagName === 'A' ? el.href : undefined,
                value: (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') ? (el.value || '') : undefined});
    if (n >= maxItems) break;
  }
  return items;
}
""" % json.dumps(INTERACTIVE)

_JS_TEXT = r"""
() => {
  const skip = new Set(['SCRIPT','STYLE','NOSCRIPT','SVG','IFRAME','NAV','FOOTER','HEADER','ASIDE','FORM','TEMPLATE']);
  const out = [];
  const walk = (node) => {
    if (node.nodeType === 3) { const t = node.textContent.replace(/\s+/g, ' ').trim(); if (t) out.push(t); return; }
    if (node.nodeType !== 1 || skip.has(node.tagName)) return;
    const s = getComputedStyle(node); if (s.display === 'none' || s.visibility === 'hidden') return;
    const tag = node.tagName; const block = /^(P|DIV|LI|H[1-6]|TR|TD|TH|BR|SECTION|ARTICLE|BLOCKQUOTE|PRE|DT|DD|OL|UL|TABLE|LABEL|OPTION)$/.test(tag);
    if (/^H[1-6]$/.test(tag)) out.push('\n' + '#'.repeat(+tag[1]) + ' ');
    if (block) out.push('\n'); if (tag === 'LI') out.push('• ');
    const b = node.getAttribute && node.getAttribute('data-bai'); if (b) out.push('[' + b + '] ');
    for (const c of node.childNodes) walk(c);
    if (block) out.push('\n');
  };
  const root = document.querySelector('main, article, [role=main]') || document.body; walk(root);
  return out.join(' ').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').replace(/ +/g, ' ').trim();
}
"""


class BrowserError(Exception):
    pass


class Browser:
    def __init__(self, headless=None, allow_actions=False, log=None, state_dir=None, viewer=None):
        """headless=None → visible window when a display exists (or BAI_HEADED=1), else invisible.
        viewer: agent.viewer.Viewer — receives a screenshot + a plain-words line after every step."""
        from playwright.sync_api import sync_playwright
        self.log = log or (lambda kind, **f: None)
        self.viewer = viewer
        if headless is None:
            want_headed = os.environ.get("BAI_HEADED", "").lower() in ("1", "true", "yes") or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
            headless = not want_headed
        self._pw = sync_playwright().start()
        launch = dict(args=["--disable-gpu", "--no-sandbox"])
        try:
            self._browser = self._pw.chromium.launch(headless=headless, slow_mo=0 if headless else 250, **launch)
        except Exception as e:
            if headless:
                raise
            self.log("browser_headed_unavailable", error=str(e)[:120])
            headless = True
            self._browser = self._pw.chromium.launch(headless=True, **launch)
        self.headless = headless
        self._ctx = self._browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US",
                                              user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"))
        self._ctx.set_default_timeout(20000)
        self.allow_actions = allow_actions
        self.state_dir = state_dir or (config.STATE_DIR / "browser")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.page = self._ctx.new_page()
        self.items = []
        self.history = []
        self.last_used = time.time()
        if self.viewer:
            self.viewer.browser_open = True

    def alive(self):
        try:
            return self._browser.is_connected() and bool(self._ctx.pages)
        except Exception:
            return False

    def _show(self, action=""):
        """Push the current tab to the live viewer (screenshot only while somebody is watching)."""
        self.last_used = time.time()
        if not self.viewer:
            return
        shot = None
        if self.viewer.watching():
            try:
                shot = self.page.screenshot(type="jpeg", quality=55, timeout=4000)
            except Exception:
                pass
        try:
            self.viewer.step(action, self.page.url, self.page.title()[:80], self.status(), len(self._ctx.pages), shot)
        except Exception:
            pass

    # ---- lifecycle -----------------------------------------------------
    def close(self):
        if self.viewer:
            self.viewer.browser_open = False
        try:
            self._ctx.close(); self._browser.close(); self._pw.stop()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # ---- tabs ----------------------------------------------------------
    def tabs(self):
        return [{"i": i, "title": p.title()[:60], "url": p.url, "active": p is self.page} for i, p in enumerate(self._ctx.pages)]

    def switch(self, i):
        self.page = self._ctx.pages[int(i)]
        self.page.bring_to_front()
        return self.read()

    def new_tab(self, url=None):
        self.page = self._ctx.new_page()
        return self.open(url) if url else "new empty tab"

    def close_tab(self, i=None):
        p = self._ctx.pages[int(i)] if i is not None else self.page
        p.close()
        self.page = self._ctx.pages[-1] if self._ctx.pages else self._ctx.new_page()
        return f"closed; {len(self._ctx.pages)} tab(s) open"

    # ---- navigation ----------------------------------------------------
    def _check(self, url):
        if BLOCKED.search(url):
            raise BrowserError(f"blocked domain: {url}")

    def open(self, url):
        if not re.match(r"^https?://", url):
            url = "https://" + url
        self._check(url)
        t0 = time.time()
        try:
            self.page.goto(url, wait_until="domcontentloaded")
            self.page.wait_for_load_state("networkidle", timeout=8000)
        except Exception as e:
            if "Timeout" not in type(e).__name__ and "timeout" not in str(e).lower():
                raise BrowserError(f"could not open {url}: {str(e)[:120]}")
        self.history.append(url)
        self.log("browser_open", url=url, ms=int((time.time() - t0) * 1000))
        self._show(f"Opened {url}")
        return self.read()

    def back(self):
        self.page.go_back(wait_until="domcontentloaded"); return self.read()

    def forward(self):
        self.page.go_forward(wait_until="domcontentloaded"); return self.read()

    ENGINES = {"brave": "https://search.brave.com/search?q={q}&source=web",
               "yahoo": "https://search.yahoo.com/search?p={q}",
               "bing": "https://www.bing.com/search?q={q}",
               "duckduckgo": "https://html.duckduckgo.com/html/?q={q}"}
    ENGINE_HOSTS = re.compile(r"brave\.com|yahoo\.com|bing\.com|duckduckgo|/search\?|admarketplace|r\.search\.|/ct\?", re.I)

    def search(self, query, engine=None):
        """Web search; returns the results page as text (links numbered). Tries the engines in turn and
        moves on when one shows a bot check or returns no results (headless visitors are often challenged)."""
        q = urllib.parse.quote_plus(query)
        order = [engine] if engine else ["brave", "yahoo", "bing", "duckduckgo"]
        last = ""
        for eng in order:
            try:
                last = self.open(self.ENGINES[eng].format(q=q))
            except BrowserError as e:
                last = str(e); continue
            if self.status() == "ok" and self._organic(limit=3):
                self.engine_used = eng
                return last
            self.log("search_engine_skip", engine=eng, reason=self.status())
        self.engine_used = None
        return last

    def _organic(self, limit=10):
        out, seen = [], set()
        for l in self.links(150):
            h = l.get("href") or ""
            if not h.startswith("http") or self.ENGINE_HOSTS.search(h) or h in seen:
                continue
            seen.add(h)
            out.append({"n": l["n"], "title": re.sub(r"^\S+ \S+ › .*?  ", "", l["text"])[:90], "url": h})
            if len(out) >= limit:
                break
        return out

    def search_results(self, query, limit=10):
        """Structured results: [{n, title, url}] with the search engine's own links filtered out."""
        self.search(query)
        return self._organic(limit)

    # ---- reading -------------------------------------------------------
    def snapshot(self, max_items=150):
        self.items = self.page.evaluate(_JS_SNAPSHOT, max_items)
        return self.items

    def status(self):
        """Detect walls the agent must not try to pass."""
        try:
            body = self.page.inner_text("body", timeout=3000)[:4000]
        except Exception:
            body = ""
        title = self.page.title()
        if CAPTCHA_HINTS.search(title) or CAPTCHA_HINTS.search(body):
            return "captcha"
        if LOGIN_HINTS.search(body):
            return "login"
        return "ok"

    def read(self, max_chars=MAX_TEXT):
        """The page as the agent sees it: header, wall status, numbered interactive items inline in the text."""
        self.snapshot()
        try:
            text = self.page.evaluate(_JS_TEXT)
        except Exception as e:
            text = f"(could not read page: {e})"
        st = self.status()
        head = f"URL: {self.page.url}\nTITLE: {self.page.title()}\nTABS: {len(self._ctx.pages)}  STATUS: {st}\n"
        if st != "ok":
            head += ("!! This page shows a CAPTCHA / bot check. I must not try to pass it — stop and ask the owner.\n"
                     if st == "captcha" else "!! This page asks for a login. I must not log in by myself — stop and ask the owner.\n")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n… (truncated; {len(text) - max_chars} more characters — use scroll or find)"
        if self.viewer:
            self.viewer.text = head + "\n" + text
        return head + "\n" + text

    def links(self, limit=60):
        self.snapshot()
        return [{"n": it["n"], "text": it["label"], "href": it.get("href")} for it in self.items if it["role"] == "link"][:limit]

    def find(self, needle, context=160):
        """Find text on the page; returns snippets around each match (case-insensitive)."""
        text = self.page.evaluate(_JS_TEXT)
        out, low, n = [], text.lower(), needle.lower()
        i = low.find(n)
        while i != -1 and len(out) < 10:
            out.append(text[max(0, i - context):i + len(needle) + context].replace("\n", " "))
            i = low.find(n, i + 1)
        return out or [f"'{needle}' not found on this page"]

    def extract_text(self):
        return self.page.evaluate(_JS_TEXT)

    def screenshot(self, path=None, full=False):
        path = str(path or self.state_dir / f"shot_{int(time.time())}.png")
        self.page.screenshot(path=path, full_page=full)
        return path

    # ---- acting --------------------------------------------------------
    def _el(self, n):
        loc = self.page.locator(f"[data-bai='{int(n)}']")
        if loc.count() == 0:
            self.snapshot()
            loc = self.page.locator(f"[data-bai='{int(n)}']")
            if loc.count() == 0:
                raise BrowserError(f"no element [{n}] on the current page (call read() again)")
        return loc.first

    def _item(self, n):
        for it in self.items:
            if it["n"] == int(n):
                return it
        return {}

    def click(self, n):
        it = self._item(n)
        lab = (it.get("label") or "").lower()
        if not self.allow_actions and re.search(r"\b(buy|pay|checkout|place order|purchase|submit|post|publish|send|delete|confirm|subscribe|order now)\b", lab):
            raise BrowserError(f"refusing to click '{it.get('label')}' — actions that buy/pay/post/submit need owner approval")
        el = self._el(n)
        before = len(self._ctx.pages)
        try:
            with self._ctx.expect_page(timeout=1500) as newp:
                el.click()
            self.page = newp.value
        except Exception:
            pass  # no new tab opened — normal click
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        self.log("browser_click", n=int(n), label=it.get("label"), role=it.get("role"), new_tab=len(self._ctx.pages) > before)
        self._show(f"Clicked '{it.get('label')}'")
        return self.read()

    def type(self, n, text, enter=False):
        it = self._item(n)
        el = self._el(n)
        el.click()
        el.fill("")
        el.type(text, delay=20)
        if enter:
            el.press("Enter")
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
        self.log("browser_type", n=int(n), label=it.get("label"), text=text[:80], enter=enter)
        self._show(f"Typed '{text[:40]}' into '{it.get('label')}'")
        return self.read() if enter else f"typed into [{n}] {it.get('label')!r}"

    def select(self, n, value):
        el = self._el(n)
        el.select_option(label=value)
        return f"selected {value!r} in [{n}]"

    def scroll(self, direction="down", pages=1):
        dy = 800 * pages * (1 if direction == "down" else -1)
        self.page.mouse.wheel(0, dy)
        time.sleep(0.4)
        self._show(f"Scrolled {direction}")
        return self.read()

    def download_text(self, url, max_chars=60000):
        """Fetch a document (html/txt/pdf) in the browser context and return its text."""
        self._check(url)
        r = self._ctx.request.get(url, timeout=30000)
        ctype = r.headers.get("content-type", "")
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            try:
                import io
                from pypdf import PdfReader
                rd = PdfReader(io.BytesIO(r.body()))
                txt = "\n".join((p.extract_text() or "") for p in rd.pages[:40])
            except Exception as e:
                txt = f"(pdf could not be read: {e})"
        else:
            txt = re.sub(r"<[^>]+>", " ", r.text())
            txt = re.sub(r"\s+", " ", txt)
        return txt[:max_chars]
