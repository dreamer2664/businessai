"""Score the seller check on a fake local marketplace (no internet, no model needed):
python3 engine/scripts/score_sellers.py [--show]
Checks: candidates found & forum skipped · facts grounded (price, shipping, origin, materials, rating) · pictures embedded ·
reviews read from a second page · social page read · verdict order (good seller first, complaint-ridden seller last) ·
document saved in the library with options + sources · brief → plan → pace wiring · deadline reminder.
"""
import os, re, sys, time, json
sys.path.insert(0, ".")
os.environ.pop("DISPLAY", None)
os.environ["BAI_STATE"] = "/tmp/bai_sellers_state"
from agent.tasks import Tasks
from agent.sellers import SellerCheck, extract_facts, reliability
from agent.brief import Brief, parse_pace
from agent.pace import Pace
from agent.viewer import Viewer
from agent import library

show = "--show" in sys.argv
BASE = "file://" + os.path.abspath("tests/market") + "/"
ok = 0; total = 0
def check(name, cond, detail=""):
    global ok, total
    total += 1; ok += bool(cond)
    print(f"{'OK  ' if cond else 'MISS'} {name}" + (f"  — {detail}" if (detail and (show or not cond)) else ""), flush=True)

# ---- 1. pure functions -----------------------------------------------------------------
f = extract_facts(open("tests/market/listing_a.html").read().replace("<b>", "").replace("</b>", ""), BASE + "listing_a.html")
check("facts: price", f.get("Price") == "€ 24,90", str(f.get("Price")))
check("facts: origin", "Porto" in f.get("Ships from / origin", ""), f.get("Ships from / origin"))
check("facts: materials", "cork" in f.get("Materials", "").lower(), f.get("Materials"))
check("facts: rating", f.get("Rating") == "4.7/5", f.get("Rating"))
check("facts: delivery", "2-4" in f.get("Delivery time", ""), f.get("Delivery time"))
g, v, pros, cons = reliability(f, "arrived quickly, as described, great quality, recommend", [{"platform": "instagram"}])
check("reliability: good seller → good", g == "good", f"{g} {pros} {cons}")
fb = {"Rating": "4.2/5", "Reviews": "6 reviews", "Price": "€ 9,00"}
g2, v2, p2, c2 = reliability(fb, "damaged dirty not as described no refund broken never arrived", [])
check("reliability: complaints + few reviews → bad", g2 == "bad", f"{g2} {p2} {c2}")

# ---- 2. brief + pace wiring -----------------------------------------------------------------
B = Brief()
b = B.make("hey, real quick find me some good cheap reps for nike slippers")
check("brief: kind seller_check + document", b["kind"] == "seller_check" and b["deliverable"] == "document", f"{b['kind']} {b['deliverable']}")
check("brief: counterfeit → genuine topic", b["counterfeit"] and "genuine" in b["topic"] and "nike" not in b["topic"], b["topic"])
check("brief: quick → 10 min deadline", b["pace"]["pace"] == "quick" and b["pace"]["deadline_min"] == 10, str(b["pace"]))
b2 = B.make("i'm going to work for 5 hours, take it real slow: find me reliable suppliers of bamboo toothbrushes in europe")
check("brief: away 5 h → slow, 300 min budget", b2["pace"]["pace"] == "slow" and b2["pace"]["budget_min"] == 300, str(b2["pace"]))
check("brief: topic without pace words", b2["topic"].startswith("suppliers of bamboo"), b2["topic"])
P = Pace()
P.set({"pace": "quick", "deadline_min": 10, "budget_min": None}, "test")
check("pace: hurry() true when quick", P.hurry())
P.deadline = time.time() - 5                                       # simulate: past the deadline
r = P.tick(); check("pace: late reminder once", "past" in r.lower() and P.tick() == "", r[:60])
V = Viewer(port=8799); V.show_plan(b["goal"], b["steps"], P); V.plan_step(1)
st = V.state()["plan"]
check("viewer: plan panel state", st["step"] == 1 and st["deadline_min"] == 10 and len(st["steps"]) == 6, f"step={st['step']} dl={st['deadline_min']} steps={len(st['steps'])}")

# ---- 3. the whole seller check on the fake marketplace ----------------------------------------
T = Tasks(log=lambda k, **f: None)
notes = []
T.notify = lambda t: notes.append(t)
S = SellerCheck(T, planner=None, log=lambda k, **f: None, viewer=V, pace=None)

def fake_run():
    b = T.browser()
    # stub the search engine: every query returns the local results page's links
    def search_results(query, limit=10):
        b.open(BASE + "search.html")
        links = [{"n": l["n"], "title": l["text"], "url": l["href"]} for l in b.links(50) if l.get("href")]
        if "reviews" in query:                                   # like a real engine: a reviews query surfaces review pages first
            links.sort(key=lambda r: 0 if "review" in r["url"] else 1)
        return links[:limit]
    b.search_results = search_results
    # socials → local page (no internet)
    real_open = b.open
    def open_(url):
        if "instagram.com" in url or "facebook.com" in url:
            return real_open(BASE + "social_corkstep.html")
        return real_open(url)
    b.open = open_
    b.ENGINE_HOSTS = re.compile(r"$^")           # the fake results page is local; keep all its links
    return S.run("cork slippers", n=4)

t0 = time.time()
path, summary, options = T.on_hands(fake_run, timeout=240)
T.on_hands(T.close_browser, timeout=30)
if show: print(summary)
sellers = [o.get("seller") for o in options]
check("run: 3 listings read, wikipedia skipped", len(options) == 3 and not any("wikipedia" in o["url"] for o in options), str(sellers))
a = next((o for o in options if "listing_a" in o["url"]), {}); bb = next((o for o in options if "listing_b" in o["url"]), {})
check("run: CorkStep facts grounded", a.get("facts", {}).get("Price") == "€ 24,90" and "Porto" in a.get("facts", {}).get("Ships from / origin", ""), str(a.get("facts")))
check("run: picture embedded", bool(a.get("image")) and len(a["image"]) > 2000, f"{len(a.get('image') or b'')} bytes")
check("run: reviews read from Trustpilot-like page", any("reviews_corkstep" in u for u in a.get("review_sources", [])), str(a.get("review_sources")))
check("run: social page read (followers)", any("12.4K" in (s.get("note") or "") for s in a.get("socials", [])), str(a.get("socials")))
check("run: CorkStep judged good", a.get("grade") == "good", f"{a.get('grade')} {a.get('pros')} {a.get('cons')}")
check("run: Vinted seller judged bad", bb.get("grade") == "bad", f"{bb.get('grade')} {bb.get('pros')} {bb.get('cons')}")
check("run: ranking good first, bad last", options and options[0]["grade"] == "good" and options[-1]["grade"] == "bad", str([o["grade"] for o in options]))
html = open(path, encoding="utf-8").read() if path else ""
check("doc: saved in library with 3 options + pictures", path and path.exists() and html.count("class=opt") == 3 and html.count("data:image/jpeg") >= 3, str(path))
check("doc: links + verdicts + table", "listing_a.html" in html and "Side by side" in html and "verdict good" in html, "")
rec = library.recent(1)
check("doc: index row", rec and rec[0]["kind"] == "seller_check" and rec[0]["options"] == 3, str(rec[:1]))
check("plan: steps advanced to the end", V.state()["plan"]["step"] >= 5, str(V.state()["plan"]["step"]))
print(f"SELLERS SCORE: {ok}/{total}  ({time.time() - t0:.0f}s browser part)")
