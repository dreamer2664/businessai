"""Website builder score: brief parsing, full build, page checks, mobile layout, zip, facts grounding, kind coverage.
Run:  timeout 280 python3 engine/scripts/score_sites.py --show 2>&1 | grep -v '^{"t"' | tail -30
Offline except one optional geocode (skipped when the network is down)."""
import json
import os
import re
import sys
import time
import zipfile

os.environ.setdefault("BAI_STATE", "/tmp/bai_sites_state")
os.environ.pop("DISPLAY", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.sitebuilder import SiteBuilder, KINDS, slugify   # noqa: E402
from agent.tasks import Tasks                                 # noqa: E402
from agent import core                                        # noqa: E402

SHOW = "--show" in sys.argv
checks = []


def check(name, ok, note=""):
    checks.append((name, bool(ok)))
    if SHOW or not ok:
        print(("✅" if ok else "❌"), name, ("— " + str(note)[:100]) if note else "")


class FakeBot:
    def __init__(self, *a, **k):
        self.sent = []

    def get_me(self):
        return {"username": "bot", "id": 1}

    def send(self, chat, text, buttons=None, **k):
        self.sent.append(text)
        return {"message_id": len(self.sent)}

    def send_photo(self, chat, path, caption=None, **k):
        self.sent.append(f"[photo {os.path.basename(str(path))}]")

    def send_document(self, chat, path, caption=None, **k):
        self.sent.append(f"[doc {os.path.basename(str(path))}]")

    def __getattr__(self, n):
        return lambda *a, **k: None


t_start = time.time()
core.Bot = lambda *a, **k: FakeBot()
A = core.Agent()
A.owner_id = 1
A.planner.available = lambda: False
A.planner.installed = lambda: False

# 1) brief parsing from plain sentences
cases = [
    ("build a website for a small bakery in Bergamo called Forno Bianchi", ("Forno Bianchi", "bakery", "Bergamo")),
    ("make a website for Studio Legale Rossi, a lawyer in Milan, Italy", ("Studio Legale Rossi", "lawyer", "Milan")),
    ("create a site for a coffee bar in Lisbon", ("Lisbon Cafe", "cafe", "Lisbon")),
    ("build a website for a gym called IronWorks in Turin offering: crossfit, yoga, personal training", ("IronWorks", "gym", "Turin")),
    ("I need a website for my dentist practice in Vienna, Austria called Smile Studio", ("Smile Studio", "dentist", "Vienna")),
]
for goal, (name, kind, city) in cases:
    b = A._site_brief_from({"goal": goal})
    check(f"brief: {goal[:45]}…", (b["name"], b["kind"], b["city"]) == (name, kind, city), f"{b['name']} | {b['kind']} | {b['city']}")
b = A._site_brief_from({"goal": cases[3][0]})
check("brief: services list parsed", b["services"] == ["crossfit", "yoga", "personal training"], b["services"])

# 2) full build without network (coordinates given)
S = SiteBuilder(planner=None, tasks=A.tasks, log=lambda k, **f: None)
brief = {"name": "Forno Bianchi", "kind": "bakery", "city": "Bergamo", "country": "Italy", "address": "Via Pignolo 12, 24121 Bergamo", "phone": "+39 035 123456", "hours": "Mo-Sa 07:00-19:30", "lat": 45.703, "lon": 9.672}
t0 = time.time()
report, built, shot = S.build_for(brief)
check("build: 6 pages written", built and all((built["dir"] / p).exists() for p in built["pages"]) and len(built["pages"]) == 6, built and built["pages"])
check("build: checks passed in own browser", "checks passed" in report, report.splitlines()[0])
check("build: screenshot taken", shot and os.path.getsize(shot) > 10000, shot and os.path.getsize(shot))
check("build: zip contains the pages", built and zipfile.ZipFile(built["zip"]).namelist() and len(zipfile.ZipFile(built["zip"]).namelist()) == 6)
check("build: under 30 s", time.time() - t0 < 30, f"{time.time() - t0:.0f}s")
idx = (built["dir"] / "index.html").read_text()
check("facts: name, address, phone, hours on the home page", all(x in idx for x in ("Forno Bianchi", "Via Pignolo 12", "+39 035 123456", "Mo-Sa 07:00-19:30")))
check("facts: no invented claims (years, awards, prices)", not re.search(r"\b(since 19|since 20|award|winner|€\s?\d|\$\s?\d)", idx, re.I))
check("html: viewport + description + tel link", all(x in idx for x in ('name="viewport"', 'name="description"', 'href="tel:+39035123456"')))
check("html: no external resources (self-contained)", not re.search(r'(src|href)="https?://[^"]+\.(css|js|png|jpg|woff)', idx))
contact = (built["dir"] / "contact.html").read_text()
check("contact: map embed + form", "openstreetmap.org/export/embed.html" in contact and "<form" in contact)
check("copy: per-service texts, not one template line", len({s["text"] for s in built["copy"]["services"]}) == len(built["copy"]["services"]))
about = (built["dir"] / "about.html").read_text()
check("about: mentions city and kind", "Bergamo" in about and "bakery" in about)

# 3) every business kind builds and passes its own checks (no browser: structural check only)
bad = []
for kind in KINDS:
    b2 = {"name": f"Test {kind.title()}", "kind": kind, "city": "Lyon", "country": "France", "lat": 45.76, "lon": 4.83}
    try:
        out = S.build(b2)
        txt = (out["dir"] / "index.html").read_text()
        if len(txt) < 5000 or "None" in re.sub(r"<[^>]+>", " ", txt):
            bad.append(kind)
    except Exception as e:
        bad.append(f"{kind}: {e}")
check(f"all {len(KINDS)} business kinds build cleanly", not bad, bad)

# 4) checker catches real problems (a broken link + template leftovers + horizontal overflow)
d = built["dir"]
(d / "about.html").write_text((d / "about.html").read_text().replace('href="services.html"', 'href="missing.html"').replace("What people say", "What people say {{lorem}}"))
(d / "index.html").write_text((d / "index.html").read_text().replace("</body>", '<div style="width:1400px;height:10px"></div></body>'))
problems, _ = A.tasks.on_hands(S.check, built, False, timeout=120)
check("checker: broken link found", any("broken link missing.html" in p for p in problems), problems)
check("checker: template leftovers found", any("template leftovers" in p for p in problems), problems)
check("checker: mobile overflow found", any("overflow" in p for p in problems), problems)

# 5) through the agent: plain sentence → plan → go → report + photo + zip
A.bot.sent.clear()
r = A.respond("build a website for a small bakery in Bergamo called Forno Bianchi")
check("agent: big job asks for ▶ Go", A.last_brief is not None and A.last_brief.get("kind") == "build_site", A.last_brief and A.last_brief.get("kind"))
A.handle_callback({"id": "1", "from": {"id": 1, "username": "dreamer2664"}, "message": {"chat": {"id": 1}, "message_id": 5}, "data": "b:go"})
for _ in range(60):
    if any(s.startswith("[doc") for s in A.bot.sent):
        break
    time.sleep(1)
check("agent: report line + screenshot + zip sent", any(s.startswith("🌐 Built a website") for s in A.bot.sent) and any(s.startswith("[photo") for s in A.bot.sent) and any(s.startswith("[doc") for s in A.bot.sent), A.bot.sent[-3:])
check("agent: memory note kept", any("Forno Bianchi" in n.get("topic", "") for n in A.memory.notes("Forno Bianchi", limit=20)))

# 6) training switch
r = A.respond("start auto training on website building")
check("agent: training starts from a sentence", A.site_training and "training on" in r.lower(), r[:60])
r = A.respond("stop training")
check("agent: 'stop training' stops it", not A.site_training and "stop" in r.lower(), r[:60])
r = A.respond("/train stop")
check("agent: /train stop when idle is harmless", "stopping" in r.lower() or "0 built" in r or "built" in r, r[:60])

A.tasks.on_hands(A.tasks.close_browser, timeout=30)
ok = sum(1 for _, o in checks if o)
print(f"\nSCORE sites {ok}/{len(checks)}  ({time.time() - t_start:.0f}s)")
sys.exit(0 if ok == len(checks) else 1)
