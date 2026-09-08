#!/usr/bin/env python3
"""Documents as deliverables (Phase 2, milestone 14b): "research X, write me a document" must end with a real document
(summary, one card per page with picture + link + key points, sources) handed over as a file — not a chat dump.
Runs entirely on local pages (tests/pages) with the search engine stubbed.

Run: python3 engine/scripts/score_docs.py [--show]
"""
import os, re, sys, time, shutil, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.pop("DISPLAY", None)
os.environ["BAI_STATE"] = "/tmp/bai_docs_state"
shutil.rmtree("/tmp/bai_docs_state", ignore_errors=True)
show = "--show" in sys.argv

from agent.tasks import Tasks
from agent import library, core

PASS = FAIL = 0
def check(name, ok, detail=""):
    global PASS, FAIL
    PASS += bool(ok); FAIL += (not ok)
    print(("✅" if ok else "❌"), name, ("" if ok or not detail else f"— {detail}"))

PAGES = ROOT / "tests" / "pages"
def results_for(names):
    return lambda q, n=10: [{"url": "file://" + str(PAGES / p), "title": p} for p in names]

# ---- 1. research → document ---------------------------------------------------------------------
T = Tasks(log=lambda k, **f: None)
def run_research():
    b = T.browser(); b.search_results = results_for(["shipping.html", "faq.html", "supplier_a.html", "supplier_b.html", "product_lamp.html"])
    return T.research("shipping days", n_pages=4, want_doc=True)
t0 = time.time()
out = T.on_hands(run_research, timeout=200)
dt = time.time() - t0
if show:
    print(out)
check("research: chat reply is short and points to the document", "the document has the key points" in out and len(out) < 400, out[:120])
check("research: a document was written", T.last_doc and pathlib.Path(T.last_doc).exists(), str(T.last_doc))
html = open(T.last_doc, encoding="utf-8").read() if T.last_doc else ""
check("research: one card per page read (3)", html.count("class=opt") == 3, str(html.count("class=opt")))
check("research: every card links its page", len(re.findall(r'class=src><a href="file://', html)) == 3 and "supplier_a.html" in html and "faq.html" in html, str(re.findall(r'href="([^"]{0,60})', html)[:3]))
check("research: key points are the page's own sentences", "2–3 business days" in html or "2-3 business days" in html, "")
check("research: sources listed", "Sources" in html or "sources" in html.lower())
check("research: in the library index", any("shipping days" in r.get("title", "").lower() for r in library.recent(5)), str(library.recent(2)))
check("research: quick (< 30 s on local pages)", dt < 30, f"{dt:.0f}s")

# ---- 1b. the owner adds something mid-way → one more page on it, marked in the document ------------
def run_research_change():
    b = T.browser()
    calls = []
    def sr(q, n=10):
        calls.append(q)
        if "returns" in q.lower():                                # the change query → a page the first pass did not open
            return results_for(["faq.html", "supplier_a.html"])(q, n)
        return results_for(["supplier_a.html", "supplier_b.html"])(q, n)
    b.search_results = sr
    T.owner_change = "also look at the returns"
    out = T.research("shipping days", n_pages=2, want_doc=True)
    return out, calls
outc, calls = T.on_hands(run_research_change, timeout=200)
htmlc = open(T.last_doc, encoding="utf-8").read() if T.last_doc else ""
check("change: a second search was made for what the owner added", any("returns" in c.lower() for c in calls), str(calls))
check("change: the reply says the addition was covered", "You added “also look at the returns”" in outc and "1 page(s) on it" in outc, outc[:200])
check("change: the extra page is in the document, marked ➕", "➕" in htmlc and "faq.html" in htmlc and "you added: also look at the returns" in htmlc, str(re.findall(r"➕[^<]{0,40}", htmlc)[:2]))
check("change: cleared after the job", T.owner_change == "")

# ---- 2. no document when nothing matched (honest, no empty file) ---------------------------------
def run_empty():
    b = T.browser(); b.search_results = results_for(["about.html", "blog.html"])
    return T.research("quantum chromodynamics", n_pages=2, want_doc=True)
out2 = T.on_hands(run_empty, timeout=120)
check("research: nothing matched → no empty document, honest line", T.last_doc is None and "0 pages read" in out2 and "No document this time" in out2, out2[:160])

# ---- 3. compare → document with a table ------------------------------------------------------------
def run_compare():
    b = T.browser(); b.search_results = results_for(["supplier_a.html", "supplier_b.html", "supplier_c.html"])
    return T.compare_suppliers("bamboo toothbrush", n_pages=3, want_doc=True)
out3 = T.on_hands(run_compare, timeout=200)
if show:
    print(out3)
html3 = open(T.last_doc, encoding="utf-8").read() if T.last_doc else ""
check("compare: document with a side-by-side table", T.last_doc and "Side by side" in html3 and "<table" in html3, str(T.last_doc))
check("compare: every supplier row has a link", html3.count("<a href") >= 3, str(html3.count("<a href")))
check("compare: chat reply is one line pointing to the document", "in the document" in out3 and out3.count("\n") <= 3, out3[:120])
T.on_hands(T.close_browser, timeout=30)

# ---- 4. through the agent: the owner gets the file (and the ✅ line) ---------------------------------
class FakeBot:
    def __init__(self, *a, **k): self.sent = []; self.docs = []
    def get_me(self): return {"username": "bot", "id": 1}
    def send(self, chat, text, buttons=None, **k): self.sent.append((text, buttons)); return {"message_id": len(self.sent)}
    def send_document(self, chat, path, caption=None, **k): self.docs.append((str(path), caption or ""))
    def __getattr__(self, n): return lambda *a, **k: None
core.Bot = lambda *a, **k: FakeBot()
A = core.Agent(); A.owner_id = 1; A.planner.available = lambda: False; A.planner.installed = lambda: False
orig_browser = A.tasks.browser
def patched():
    b = orig_browser(); b.search_results = results_for(["shipping.html", "faq.html", "supplier_a.html", "supplier_b.html"]); return b
A.tasks.browser = patched
r = A.respond("research shipping days from italian suppliers, make me a document with links")
plan = A.bot.sent[-1][0] if A.bot.sent else (r or "")
check("agent: document request shows the plan and promises the document", "document" in plan.lower() and "Shall I go?" in plan, plan[:120])
A.handle_callback({"id": "1", "from": {"id": 1, "username": "dreamer2664"}, "message": {"chat": {"id": 1}, "message_id": 5}, "data": "b:go"})
for _ in range(120):
    if A.bot.docs:
        break
    time.sleep(0.5)
check("agent: the .html document is sent as a file", A.bot.docs and A.bot.docs[-1][0].endswith(".html") and os.path.exists(A.bot.docs[-1][0]), str(A.bot.docs))
check("agent: ✅ line before the file", any(t.startswith("✅") for t, _ in A.bot.sent), [t[:40] for t, _ in A.bot.sent[-3:]])
lib = A.respond("/library")
check("agent: /library lists it", "shipping days" in lib.lower(), lib[:160])
A.tasks.on_hands(A.tasks.close_browser, timeout=30)

print(f"\nDOCS SCORE: {PASS}/{PASS + FAIL}")
sys.exit(0 if FAIL == 0 else 1)
