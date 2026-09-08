#!/usr/bin/env python3
"""Eyes on listings — does the AI notice when the photo contradicts the text?  (Phase 2, milestone 15)

Two layers:
  1. judgement (no model needed): the words the eyes produce → flag or not, and the "is this a flat graphic?" filter
  2. live (only when the vision model is installed): the fake marketplace with REAL photos — a Vinted listing that says
     "New without tags" while the photo shows a worn shoe must be flagged; a genuinely new sneaker must not.

Run: python3 engine/scripts/score_eyes_listing.py [--show]
"""
import os, re, sys, time, shutil, tempfile, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.pop("DISPLAY", None)
os.environ["BAI_STATE"] = "/tmp/bai_eyes_score"
shutil.rmtree("/tmp/bai_eyes_score", ignore_errors=True)
show = "--show" in sys.argv

from agent.sellers import photo_verdict, photo_is_graphic, extract_facts, SellerCheck
from agent.tasks import Tasks

PASS = FAIL = 0
def check(name, ok, detail=""):
    global PASS, FAIL
    PASS += bool(ok); FAIL += (not ok)
    print(("✅" if ok else "❌"), name, ("" if ok or not detail else f"— {detail}"))

MARKET = ROOT / "tests" / "market"

# ---- 1. judgement from words -----------------------------------------------------------
cases = [
    ("wear on an item listed new → flag", "The shoe shows signs of wear and tear, including a slightly worn sole and a scuff mark.", "New without tags", True),
    ("wear on an item listed used → fine", "The shoe shows signs of wear and tear, including a noticeable dent on the toe.", "Used - good", False),
    ("a hole on a used item → still flag (damage)", "The shoe shows a hole near the sole and a torn lining.", "Used - good", True),
    ("brand new photo, listed new → fine", "The image shows white sneakers that appear to be brand new, as there are no visible signs of wear or damage.", "New", False),
    ("no condition given, 'used' words only → fine", "The mug appears used, with a chipped rim and stains inside.", "", False),
    ("no condition given, broken → flag", "The mug appears used, with a chipped rim and a crack.", "", True),
    ("empty answer → fine", "", "New", False),
    ("'no visible signs of use' listed new → fine", "The item shows no visible signs of use or damage.", "Like new", False),
]
for name, ans, cond, want in cases:
    got = bool(photo_verdict(ans, cond))
    check("judge: " + name, got == want, f"got {got} for {ans[:50]!r}")
v = photo_verdict("The shoe shows signs of wear, including a worn sole.", "New without tags")
check("judge: flag starts with the eye and quotes the sentence", v.startswith("👁 ") and "worn sole" in v, v)

# ---- 2. graphic filter -------------------------------------------------------------------
for f, want in (("slipper_a.jpg", True), ("slipper_b.jpg", True), ("slipper_c.jpg", True), ("worn_shoe.jpg", False), ("worn_shoe2.jpg", False), ("new_shoe.jpg", False)):
    data = (MARKET / f).read_bytes()
    check(f"graphic filter: {f} → {'graphic' if want else 'photo'}", photo_is_graphic(data) == want)
import io
from PIL import Image
_tiny = io.BytesIO(); Image.open(MARKET / "worn_shoe.jpg").resize((48, 40)).save(_tiny, "JPEG")
check("graphic filter: tiny image (48 px) counts as graphic", photo_is_graphic(_tiny.getvalue()) is True)
check("graphic filter: garbage bytes never raise", photo_is_graphic(b"not an image") is False)

# ---- 3. the listed condition is read wherever the page says "Condition: …" --------------
facts = extract_facts((MARKET / "listing_b.html").read_text(), "file:///x/listing_b.html")
check("facts: 'Condition: New without tags' read from the listing", facts.get("Condition (as listed)") == "New without tags", str(facts.get("Condition (as listed)")))
facts_a = extract_facts((MARKET / "listing_a.html").read_text(), "file:///x/listing_a.html")
check("facts: no condition invented for a normal shop page", "Condition (as listed)" not in facts_a, str(facts_a.get("Condition (as listed)")))

# ---- 4. live: real photos through the whole seller check (only with the model installed) ----
try:
    from agent.eyes import Eyes
    E = Eyes(log=lambda k, **f: None)
    live = E.installed()
except Exception:
    E, live = None, False
if not live:
    print("ℹ️ vision model not installed here — live part skipped (install with /eyes install); counting the offline checks only")
else:
    stage = pathlib.Path(tempfile.mkdtemp(prefix="eyes_market_"))
    for f in MARKET.iterdir():
        shutil.copy(f, stage / f.name)
    # the Vinted listing claims "New without tags" but its photo is a worn shoe; the shop listing gets a real new sneaker
    (stage / "listing_b.html").write_text((stage / "listing_b.html").read_text().replace("slipper_b.jpg", "worn_shoe.jpg"))
    (stage / "listing_a.html").write_text((stage / "listing_a.html").read_text().replace("slipper_a.jpg", "new_shoe.jpg"))
    BASE = "file://" + str(stage) + "/"
    T = Tasks(log=lambda k, **f: None)
    fails = []
    S = SellerCheck(T, planner=None, log=lambda k, **f: fails.append(k) if k.endswith("failed") else None, viewer=None, pace=None, eyes=E)

    def fake_run():
        b = T.browser()
        def search_results(query, limit=10):
            b.open(BASE + "search.html")
            links = [{"n": l["n"], "title": l["text"], "url": l["href"]} for l in b.links(50) if l.get("href")]
            if "reviews" in query:
                links.sort(key=lambda r: 0 if "review" in r["url"] else 1)
            return links[:limit]
        b.search_results = search_results
        real_open = b.open
        def open_(url):
            if "instagram.com" in url or "facebook.com" in url:
                return real_open(BASE + "social_corkstep.html")
            return real_open(url)
        b.open = open_
        b.ENGINE_HOSTS = re.compile(r"$^")
        return S.run("cork slippers", n=4)

    t0 = time.time()
    path, summary, options = T.on_hands(fake_run, timeout=400)
    T.on_hands(T.close_browser, timeout=30)
    E.stop()
    dt = time.time() - t0
    if show:
        print(summary)
        for o in options:
            print("-", o.get("seller"), o.get("grade"), "| eyes:", (o.get("eyes") or "")[:120])
    a = next((o for o in options if "listing_a" in o["url"]), {}); bb = next((o for o in options if "listing_b" in o["url"]), {})
    check("live: no eyes/image failures logged", not fails, str(fails))
    check("live: worn shoe listed 'New without tags' → flagged", bool(bb.get("eyes")), str(bb.get("eyes")))
    check("live: the flag names what was seen (wear/scuff/worn)", bool(re.search(r"worn|wear|scuff|scratch", bb.get("eyes") or "", re.I)), str(bb.get("eyes")))
    check("live: new sneaker → not flagged", not a.get("eyes"), str(a.get("eyes")))
    check("live: contradiction is the first con in the verdict", bool(bb.get("cons")) and bb["cons"][0].startswith("the photo contradicts the listing"), str(bb.get("cons"))[:120])
    html = open(path, encoding="utf-8").read() if path else ""
    check("live: document tells the owner about the photo", "photo contradicts" in html and "👁" in html)
    check("live: whole check under 90 s with the eyes on", dt < 90, f"{dt:.0f}s")
    shutil.rmtree(stage, ignore_errors=True)

print(f"\nEYES-LISTING SCORE: {PASS}/{PASS + FAIL}")
