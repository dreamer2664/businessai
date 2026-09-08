"""Website builder (milestone 19): a brief about a place/business → a complete, mobile-friendly, self-contained website
(index / about / services / gallery / contact) with real copy, then a visual check in the agent's own browser.

Two ways in:
  build(brief)            — brief = {name, kind, city, country, address, phone, website, hours, tagline, about, services[], extras}
  auto-train()            — picks a random real place in a random country (OpenStreetMap / Overpass, free, no key),
                            builds the whole site for it, screenshots it, saves to state/sites/<slug>/ (+ Drive "Websites"),
                            and returns a one-line notification "built this website for X place".

The copy comes from the thinking model when it is running (with strict grounding: only facts from the brief);
otherwise from templates per business kind — always complete, never lorem ipsum. Images: inline SVG art (no downloads,
no licensing questions); the owner can drop real photos in the gallery folder later.
"""
import html
import json
import os
import random
import re
import shutil
import time
import urllib.parse
import urllib.request
import zipfile

from . import config

SITES_DIR = config.STATE_DIR / "sites"

KINDS = {
    "restaurant": {"services": ["Lunch & dinner", "Takeaway", "Private events", "Seasonal menu"], "verb": "cooks", "cta": "Book a table", "palette": ("#7a2e1d", "#f7efe6", "#2b2b2b")},
    "cafe": {"services": ["Specialty coffee", "Breakfast & brunch", "Homemade cakes", "Laptop-friendly seating"], "verb": "brews", "cta": "Find us", "palette": ("#5b3a29", "#faf6f0", "#2b2b2b")},
    "bakery": {"services": ["Fresh bread daily", "Pastries & cakes", "Custom celebration cakes", "Wholesale for cafés"], "verb": "bakes", "cta": "Order for pickup", "palette": ("#b8742a", "#fff8ee", "#2b2b2b")},
    "hair salon": {"services": ["Cut & style", "Colour & highlights", "Treatments", "Bridal & events"], "verb": "styles", "cta": "Book an appointment", "palette": ("#3b2f5c", "#f6f3fa", "#222")},
    "gym": {"services": ["Open gym", "Group classes", "Personal training", "Nutrition guidance"], "verb": "trains", "cta": "Start your free trial", "palette": ("#0f3d3e", "#eef7f6", "#111")},
    "dentist": {"services": ["Check-ups & cleaning", "Whitening", "Orthodontics", "Emergency care"], "verb": "cares for", "cta": "Book a visit", "palette": ("#1f5f8b", "#eef5fb", "#1b1b1b")},
    "pharmacy": {"services": ["Prescriptions", "Health advice", "Cosmetics & baby care", "Home delivery"], "verb": "serves", "cta": "Call us", "palette": ("#1b7f4c", "#eef8f2", "#1b1b1b")},
    "hotel": {"services": ["Rooms & suites", "Breakfast included", "Free Wi-Fi", "Late check-out on request"], "verb": "welcomes", "cta": "Check availability", "palette": ("#274060", "#f2f5f9", "#1b1b1b")},
    "florist": {"services": ["Bouquets & arrangements", "Weddings & events", "Plants & pots", "Same-day delivery"], "verb": "arranges", "cta": "Order flowers", "palette": ("#8b3a62", "#fdf3f8", "#222")},
    "bookshop": {"services": ["New & used books", "Children's corner", "Author events", "Orders in 48 h"], "verb": "recommends", "cta": "Visit the shop", "palette": ("#3c4a2a", "#f5f7f0", "#222")},
    "bike shop": {"services": ["Bikes & e-bikes", "Repairs & servicing", "Accessories", "Rentals"], "verb": "repairs", "cta": "Book a repair", "palette": ("#1d4e89", "#eef3f9", "#1b1b1b")},
    "shop": {"services": ["Curated products", "Gift wrapping", "Local pickup", "Loyalty card"], "verb": "sells", "cta": "Visit us", "palette": ("#444", "#f6f6f6", "#1b1b1b")},
    "plumber": {"services": ["Emergency call-outs", "Boiler service", "Bathroom installations", "Leak detection"], "verb": "fixes", "cta": "Call now", "palette": ("#0b4f6c", "#eef6f9", "#1b1b1b")},
    "lawyer": {"services": ["Family law", "Contracts", "Property", "First consultation"], "verb": "advises", "cta": "Request a consultation", "palette": ("#2f2f4f", "#f4f4f8", "#1b1b1b")},
    "veterinary": {"services": ["Check-ups & vaccines", "Surgery", "Dental care", "Emergency line"], "verb": "cares for", "cta": "Book a visit", "palette": ("#2a6f4e", "#eef7f2", "#1b1b1b")},
}
SERVICE_TEXT = {
    "Lunch & dinner": "Open for lunch and dinner with a short menu that changes with the season.", "Takeaway": "Everything on the menu can be packed to take home — call ahead and it is ready when you arrive.",
    "Private events": "Birthdays, team dinners and family celebrations: the room can be reserved for groups.", "Seasonal menu": "We cook with what is good right now, so the menu moves with the seasons.",
    "Specialty coffee": "Beans from small roasters, ground to order; espresso, filter and everything in between.", "Breakfast & brunch": "From early coffee and a croissant to a slow weekend brunch.",
    "Homemade cakes": "Cakes and biscuits baked here every morning — ask what came out of the oven today.", "Laptop-friendly seating": "Good Wi-Fi, plenty of sockets and no one hurrying you along.",
    "Fresh bread daily": "Loaves, rolls and focaccia baked before dawn every day, with slow-risen dough and no additives.", "Pastries & cakes": "Croissants, tarts and cakes for the morning coffee or the Sunday table.",
    "Custom celebration cakes": "Birthday and wedding cakes made to order — tell us the occasion and the number of guests.", "Wholesale for cafés": "Daily deliveries of bread and pastries to cafés and restaurants nearby.",
    "Cut & style": "A cut that suits your face and your mornings, finished with a style you can repeat at home.", "Colour & highlights": "Natural-looking colour, balayage and highlights with gentle products.",
    "Treatments": "Repair and hydration treatments for hair that has seen sun, heat or bleach.", "Bridal & events": "Trial session first, then relaxed styling on the day itself.",
    "Open gym": "Free weights, machines and cardio, open long hours so you can train around your day.", "Group classes": "Small classes with a coach who knows your name — strength, mobility and HIIT.",
    "Personal training": "One-to-one sessions built around your goal, with a plan you can follow between visits.", "Nutrition guidance": "Simple, realistic advice on eating to match your training.",
    "Check-ups & cleaning": "Regular visits that keep small problems small — gentle, thorough and on time.", "Whitening": "Safe in-clinic whitening with results you can see the same day.",
    "Orthodontics": "Braces and clear aligners for children and adults, with a clear plan and price from the start.", "Emergency care": "Sudden pain or a broken tooth? Call and we find you a slot the same day when we can.",
    "Prescriptions": "Prescriptions filled quickly, with clear advice on how to take what you are given.", "Health advice": "A pharmacist you can talk to about minor ailments before you decide to see a doctor.",
    "Cosmetics & baby care": "Skincare, sun protection and everything for newborns from brands we trust.", "Home delivery": "Medicines delivered to your door in the area — ask at the counter or call.",
    "Rooms & suites": "Quiet, comfortable rooms with good beds and blackout curtains.", "Breakfast included": "A proper breakfast with local bread, fruit and fresh coffee, included in every stay.",
    "Free Wi-Fi": "Fast Wi-Fi in every room and in the common areas, at no extra cost.", "Late check-out on request": "Sleeping in? Ask the day before and we arrange a later check-out when we can.",
    "Bouquets & arrangements": "Seasonal flowers arranged for the occasion, from a small posy to a statement piece.", "Weddings & events": "Flowers for the ceremony, the tables and the bride, planned together with you.",
    "Plants & pots": "Houseplants, herbs and pots, with honest advice on what will survive your windowsill.", "Same-day delivery": "Order before noon for delivery in town the same day.",
    "New & used books": "New releases next to well-kept second-hand finds, at fair prices.", "Children's corner": "A cosy corner with picture books and a rug — children welcome to sit and read.",
    "Author events": "Readings and signings with local and visiting authors, most of them free.", "Orders in 48 h": "Any book in print ordered for you and ready to collect within two days.",
    "Bikes & e-bikes": "City bikes, e-bikes and children's bikes, set up to fit you before you ride away.", "Repairs & servicing": "Punctures, brakes, gears and full services — most repairs done while you wait or by the next day.",
    "Accessories": "Locks, lights, helmets, bags and everything else you need to ride every day.", "Rentals": "Bikes by the hour or the day for exploring the town and the paths around it.",
    "Curated products": "A small, carefully chosen selection — we know where everything comes from.", "Gift wrapping": "Free gift wrapping on request, for any occasion.",
    "Local pickup": "Order by phone or message and collect it in the shop when it suits you.", "Loyalty card": "Regulars collect points on every purchase and get a discount when the card is full.",
    "Emergency call-outs": "Burst pipe or no hot water? We answer the phone and come out fast.", "Boiler service": "Annual servicing and repairs that keep your boiler safe and efficient.",
    "Bathroom installations": "From a new tap to a full bathroom, done tidily and on schedule.", "Leak detection": "We find the leak before it finds your ceiling — with the least possible disruption.",
    "Family law": "Separation, custody and inheritance handled with care and plain explanations.", "Contracts": "Contracts drafted and reviewed so you know exactly what you are signing.",
    "Property": "Purchases, rentals and disputes — practical advice at every step.", "First consultation": "A first meeting to understand your situation and explain your options and costs.",
    "Check-ups & vaccines": "Routine visits and vaccinations that keep your animal healthy year after year.", "Surgery": "Routine and urgent operations in our own surgery, with careful aftercare.",
    "Dental care": "Cleaning and treatment of teeth and gums for dogs, cats and small animals.", "Emergency line": "An emergency number for out-of-hours problems — call and we tell you what to do.",
}
OSM_KIND = {"restaurant": "restaurant", "cafe": "cafe", "bakery": "bakery", "hairdresser": "hair salon", "fitness_centre": "gym", "dentist": "dentist",
            "pharmacy": "pharmacy", "hotel": "hotel", "florist": "florist", "books": "bookshop", "bicycle": "bike shop", "veterinary": "veterinary", "pub": "restaurant",
            "bar": "cafe", "fast_food": "restaurant", "ice_cream": "cafe", "clothes": "shop", "gift": "shop", "shoes": "shop", "furniture": "shop", "hardware": "shop",
            "optician": "shop", "jewelry": "shop", "toys": "shop", "pet": "shop", "supermarket": "shop", "convenience": "shop", "beauty": "hair salon", "massage": "hair salon", "lawyer": "lawyer"}
CITIES = [("Milan", "Italy"), ("Lisbon", "Portugal"), ("Kyoto", "Japan"), ("Montreal", "Canada"), ("Valencia", "Spain"), ("Kraków", "Poland"), ("Auckland", "New Zealand"),
          ("Cape Town", "South Africa"), ("Buenos Aires", "Argentina"), ("Copenhagen", "Denmark"), ("Ljubljana", "Slovenia"), ("Porto", "Portugal"), ("Bologna", "Italy"),
          ("Melbourne", "Australia"), ("Edinburgh", "United Kingdom"), ("Tallinn", "Estonia"), ("Mexico City", "Mexico"), ("Seoul", "South Korea"), ("Lyon", "France"), ("Vienna", "Austria"),
          ("Bergamo", "Italy"), ("Dublin", "Ireland"), ("Utrecht", "Netherlands"), ("Bruges", "Belgium"), ("Santiago", "Chile"), ("Nairobi", "Kenya"), ("Bangkok", "Thailand")]


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48] or "site"


# ---- random real places (OpenStreetMap, free) --------------------------------------------------------
def random_place(rng=random, timeout=40):
    """A random real business in a random city: {name, kind, city, country, address, phone, website, hours, lat, lon}."""
    city, country = rng.choice(CITIES)
    q = urllib.parse.urlencode({"q": f"{city}, {country}", "format": "json", "limit": 1})
    req = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{q}", headers={"User-Agent": "businessai-sitebuilder/1.0 (training; contact: owner via telegram)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    if not d:
        raise RuntimeError(f"city not found: {city}")
    lat, lon = float(d[0]["lat"]), float(d[0]["lon"])
    kinds = list(OSM_KIND.keys())
    rng.shuffle(kinds)
    tags = "".join(f'nwr["amenity"="{k}"](around:2500,{lat},{lon});nwr["shop"="{k}"](around:2500,{lat},{lon});' for k in kinds[:6])
    query = f'[out:json][timeout:25];({tags});out tags center 60;'
    req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=urllib.parse.urlencode({"data": query}).encode(),
                                 headers={"User-Agent": "businessai-sitebuilder/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        els = json.loads(r.read().decode()).get("elements", [])
    named = [e for e in els if e.get("tags", {}).get("name") and not e["tags"].get("website")]      # prefer places WITHOUT a website
    named = named or [e for e in els if e.get("tags", {}).get("name")]
    if not named:
        raise RuntimeError(f"no named places near {city}")
    e = rng.choice(named)
    t = e["tags"]
    osm_kind = t.get("amenity") or t.get("shop") or ""
    addr = ", ".join(x for x in (f"{t.get('addr:street', '')} {t.get('addr:housenumber', '')}".strip(), t.get("addr:postcode", ""), t.get("addr:city", city)) if x)
    c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
    return {"name": t["name"], "kind": OSM_KIND.get(osm_kind, "shop"), "osm_kind": osm_kind, "city": t.get("addr:city", city), "country": country, "address": addr,
            "phone": t.get("phone") or t.get("contact:phone", ""), "website": t.get("website", ""), "hours": t.get("opening_hours", ""),
            "cuisine": t.get("cuisine", ""), "lat": c.get("lat"), "lon": c.get("lon"), "osm_id": f"{e['type']}/{e['id']}"}


# ---- the pages -------------------------------------------------------------------------------------------
def _svg_hero(name, primary, seed=0):
    rng = random.Random(seed)
    shapes = "".join(f'<circle cx="{rng.randint(0, 1200)}" cy="{rng.randint(0, 500)}" r="{rng.randint(60, 220)}" fill="white" opacity="{rng.uniform(0.05, 0.14):.2f}"/>' for _ in range(7))
    initials = html.escape("".join(w[0] for w in name.split()[:2]).upper())
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 500" preserveAspectRatio="xMidYMid slice" class="hero-art">'
            f'<rect width="1200" height="500" fill="{primary}"/>{shapes}<text x="1010" y="330" text-anchor="middle" font-family="Georgia,serif" font-size="260" fill="white" opacity="0.13">{initials}</text></svg>')


def _svg_card(i, primary):
    rng = random.Random(i * 7)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 260" class="card-art"><rect width="400" height="260" fill="{primary}" opacity="{0.75 + 0.05 * (i % 4):.2f}"/>'
            + "".join(f'<rect x="{rng.randint(0, 340)}" y="{rng.randint(0, 200)}" width="{rng.randint(40, 160)}" height="{rng.randint(20, 90)}" rx="12" fill="white" opacity="{rng.uniform(0.08, 0.2):.2f}"/>' for _ in range(5)) + "</svg>")


CSS = """:root{--p:%(p)s;--bg:%(bg)s;--fg:%(fg)s}*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--fg);background:#fff;line-height:1.55}
a{color:var(--p)}header{position:sticky;top:0;background:#fff;border-bottom:1px solid #eee;z-index:9}.nav{max-width:1080px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;padding:12px 20px}
.brand{font-weight:700;font-size:1.15em;text-decoration:none;color:var(--fg)}.nav nav a{margin-left:18px;text-decoration:none;color:var(--fg);font-weight:500}.nav nav a.on{color:var(--p);border-bottom:2px solid var(--p)}
.burger{display:none;background:none;border:0;font-size:1.6em}.hero{position:relative;color:#fff;min-height:420px;display:flex;align-items:center}.hero-art{position:absolute;inset:0;width:100%%;height:100%%}
.hero .in{position:relative;max-width:1080px;margin:0 auto;padding:60px 20px}.hero h1{font-size:2.6em;margin:0 0 10px;font-family:Georgia,serif;text-shadow:0 2px 12px rgba(0,0,0,.25)}.hero p{font-size:1.2em;max-width:600px;margin:0 0 22px;text-shadow:0 1px 8px rgba(0,0,0,.25)}
.btn{display:inline-block;background:var(--p);color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600}.btn.alt{background:#fff;color:var(--p)}
section{max-width:1080px;margin:0 auto;padding:48px 20px}h2{font-family:Georgia,serif;font-size:1.8em;margin:0 0 18px}.lead{font-size:1.1em;max-width:720px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:20px}.card{background:var(--bg);border-radius:12px;overflow:hidden}.card-art{width:100%%;height:150px;display:block}.card .t{padding:14px 16px}.card h3{margin:0 0 6px;font-size:1.05em}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;background:var(--bg);border-radius:12px;padding:20px}.facts b{display:block;color:var(--p);font-size:.85em;text-transform:uppercase;letter-spacing:.04em}
form{display:grid;gap:12px;max-width:520px}input,textarea{width:100%%;padding:11px;border:1px solid #ccc;border-radius:8px;font:inherit}button{padding:12px;border:0;border-radius:8px;background:var(--p);color:#fff;font:inherit;font-weight:600}
footer{background:var(--fg);color:#ddd;padding:28px 20px;margin-top:40px}footer .in{max-width:1080px;margin:0 auto;display:flex;flex-wrap:wrap;gap:20px;justify-content:space-between;font-size:.95em}footer a{color:#fff}
.map{border:0;width:100%%;height:320px;border-radius:12px}.review{background:var(--bg);border-radius:12px;padding:16px}.review small{color:#666}
@media(max-width:720px){.nav nav{display:none;position:absolute;left:0;right:0;top:56px;background:#fff;padding:10px 20px;border-bottom:1px solid #eee}.nav nav.open{display:block}.nav nav a{display:block;margin:10px 0}.burger{display:block}.hero h1{font-size:2em}}"""


class SiteBuilder:
    def __init__(self, planner=None, tasks=None, google=None, log=None, viewer=None, eyes=None):
        self.planner = planner
        self.T = tasks
        self.google = google
        self.log = log or (lambda kind, **f: None)
        self.viewer = viewer
        self.eyes = eyes

    # ---- copy ------------------------------------------------------------------------------------------
    def copy(self, b):
        """Text for every page. Model when available (grounded in the brief), templates otherwise."""
        k = KINDS.get(b["kind"], KINDS["shop"])
        name, city = b["name"], b.get("city") or ""
        base = {
            "tagline": b.get("tagline") or f"{k['verb'].capitalize()} with care in {city}" if city else f"{name} — {b['kind']}",
            "about": b.get("about") or (f"{name} is a {b['kind']} in {city}{', ' + b['country'] if b.get('country') else ''}. "
                                        f"We keep things simple: good work, honest prices and a friendly welcome. "
                                        f"Whether you are a regular or just passing by, you will find the same attention every time."),
            "services": [{"title": s, "text": SERVICE_TEXT.get(s, f"Ask us about {s.lower()} — we are happy to explain what we offer and what it costs.")} for s in (b.get("services") or k["services"])],
            "why": [f"Local and independent — {name} is run by people who live here", "Clear prices, no surprises", "Easy to reach: " + (b.get("address") or city or "in the centre")],
            "cta": k["cta"],
            "reviews": [{"text": f"Exactly what a {b['kind']} should be — friendly and reliable.", "who": "A regular customer"},
                        {"text": "Quick, kind and well priced. Recommended.", "who": "Visitor from out of town"}],
            "meta": f"{name} — {b['kind']} in {city}. {(b.get('services') or k['services'])[0]}, {(b.get('services') or k['services'])[1].lower()} and more.",
        }
        if b.get("cuisine"):
            base["about"] += f" The kitchen focuses on {b['cuisine'].replace(';', ', ').replace('_', ' ')}."
        if not (self.planner and self.planner.installed()):
            return base
        try:
            facts = json.dumps({x: b.get(x) for x in ("name", "kind", "city", "country", "address", "phone", "hours", "cuisine", "services") if b.get(x)}, ensure_ascii=False)
            raw = self.planner.chat(
                "You write website copy for small local businesses. Warm, concrete, short sentences. Use ONLY the facts given; never invent awards, years, prices or names. Output JSON only.",
                f"Facts: {facts}\nWrite JSON: {{\"tagline\": max 9 words, \"about\": 2 short paragraphs (60-110 words total) separated by \\n\\n, "
                f"\"services\": [{{\"title\", \"text\": one sentence}} for each of these services: {json.dumps(b.get('services') or k['services'])}], "
                f"\"why\": [3 short reasons to choose us], \"meta\": one sentence for search engines (max 150 chars)}}",
                max_tokens=520, timeout=240)
            m = re.search(r"\{.*\}", raw, re.S)
            j = json.loads(m.group(0)) if m else {}
            for key in ("tagline", "about", "meta"):
                if isinstance(j.get(key), str) and 8 < len(j[key]) < 900 and not re.search(r"lorem|\[|\]|{|}", j[key]):
                    base[key] = j[key].strip()
            if isinstance(j.get("services"), list) and len(j["services"]) >= 3 and all(isinstance(x, dict) and x.get("title") and x.get("text") for x in j["services"]):
                base["services"] = [{"title": str(x["title"])[:60], "text": str(x["text"])[:220]} for x in j["services"][:6]]
            if isinstance(j.get("why"), list) and len(j["why"]) >= 3:
                base["why"] = [str(x)[:120] for x in j["why"][:3]]
            self.log("site_copy_model", name=name)
        except Exception as e:
            self.log("site_copy_fallback", error=str(e)[:100])
        return base

    # ---- html ----------------------------------------------------------------------------------------------
    def _shell(self, b, c, page, body, pages):
        k = KINDS.get(b["kind"], KINDS["shop"])
        p, bg, fg = k["palette"]
        nav = "".join(f'<a href="{f}"{" class=on" if f == page else ""}>{t}</a>' for f, t in pages)
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(b['name'])} — {html.escape(dict(pages).get(page, ''))}</title><meta name="description" content="{html.escape(c['meta'])}">
<style>{CSS % {'p': p, 'bg': bg, 'fg': fg}}</style></head><body>
<header><div class="nav"><a class="brand" href="index.html">{html.escape(b['name'])}</a><button class="burger" onclick="document.querySelector('.nav nav').classList.toggle('open')" aria-label="menu">☰</button><nav>{nav}</nav></div></header>
{body}
<footer><div class="in"><div><b>{html.escape(b['name'])}</b><br>{html.escape(b.get('address') or b.get('city') or '')}</div>
<div>{('☎ <a href="tel:' + html.escape(re.sub(r'[^+0-9]', '', b['phone'])) + '">' + html.escape(b['phone']) + '</a><br>') if b.get('phone') else ''}{html.escape(b.get('hours') or '')}</div>
<div>© {time.strftime('%Y')} {html.escape(b['name'])} · <a href="contact.html">Contact</a> · <a href="privacy.html">Privacy</a></div></div></footer></body></html>"""

    def build(self, b, out_dir=None):
        """Write the site. Returns {dir, index, pages, copy}."""
        b = dict(b)
        b["kind"] = b.get("kind") if b.get("kind") in KINDS else "shop"
        k = KINDS[b["kind"]]
        c = self.copy(b)
        slug = slugify(f"{b['name']}-{b.get('city', '')}")
        d = out_dir or (SITES_DIR / slug)
        d = __import__("pathlib").Path(d)
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        pages = [("index.html", "Home"), ("about.html", "About"), ("services.html", "Services"), ("gallery.html", "Gallery"), ("contact.html", "Contact")]
        p = k["palette"][0]
        maps = f"https://www.openstreetmap.org/?mlat={b['lat']}&mlon={b['lon']}#map=17/{b['lat']}/{b['lon']}" if b.get("lat") else f"https://www.openstreetmap.org/search?query={urllib.parse.quote(b.get('address') or b['name'] + ' ' + b.get('city', ''))}"
        facts = "".join(f"<div><b>{t}</b>{html.escape(v)}</div>" for t, v in (("Address", b.get("address") or b.get("city") or ""), ("Phone", b.get("phone", "")), ("Opening hours", b.get("hours", "")), ("City", f"{b.get('city', '')}, {b.get('country', '')}".strip(", "))) if v)
        home = f"""<div class="hero">{_svg_hero(b['name'], p, len(b['name']))}<div class="in"><h1>{html.escape(b['name'])}</h1><p>{html.escape(c['tagline'])}</p><a class="btn alt" href="contact.html">{html.escape(c['cta'])}</a></div></div>
<section><h2>What we do</h2><div class="grid">{"".join(f'<div class="card">{_svg_card(i, p)}<div class="t"><h3>{html.escape(s["title"])}</h3><p>{html.escape(s["text"])}</p></div></div>' for i, s in enumerate(c['services'][:4]))}</div></section>
<section><h2>Why {html.escape(b['name'])}</h2><ul class="lead">{"".join(f'<li>{html.escape(w)}</li>' for w in c['why'])}</ul></section>
<section><h2>Find us</h2><div class="facts">{facts}<div><b>Map</b><a href="{maps}">Open in OpenStreetMap</a></div></div></section>"""
        about = f"""<section><h2>About {html.escape(b['name'])}</h2>{"".join(f'<p class="lead">{html.escape(par)}</p>' for par in c['about'].split(chr(10) + chr(10)))}</section>
<section><h2>What people say</h2><div class="grid">{"".join(f'<div class="review">“{html.escape(r["text"])}”<br><small>— {html.escape(r["who"])}</small></div>' for r in c['reviews'])}</div><p><small>Sample testimonials — replace with real reviews.</small></p></section>"""
        services = f"""<section><h2>Services</h2><div class="grid">{"".join(f'<div class="card">{_svg_card(i + 10, p)}<div class="t"><h3>{html.escape(s["title"])}</h3><p>{html.escape(s["text"])}</p></div></div>' for i, s in enumerate(c['services']))}</div>
<p style="margin-top:24px"><a class="btn" href="contact.html">{html.escape(c['cta'])}</a></p></section>"""
        gallery = f"""<section><h2>Gallery</h2><p class="lead">A first look. Real photos go here — drop them into the <code>gallery</code> folder and replace these placeholders.</p><div class="grid">{"".join(f'<div class="card">{_svg_card(i + 20, p)}<div class="t"><h3>{html.escape(t)}</h3></div></div>' for i, t in enumerate(["The place", "Our team", "Details", "At work", "Happy customers", "Around us"]))}</div></section>"""
        contact = f"""<section><h2>Contact</h2><div class="facts">{facts}</div></section>
<section><h2>Send us a message</h2><form onsubmit="event.preventDefault();this.querySelector('button').textContent='Thanks — we will reply soon';"><input placeholder="Your name" required><input type="email" placeholder="Your e-mail" required><textarea rows="5" placeholder="How can we help?" required></textarea><button type="submit">Send</button></form>
<p><small>This form is a demo (no server). Connect it to Formspree, Netlify Forms or your e-mail when the site goes live.</small></p></section>
<section><h2>Map</h2><iframe class="map" loading="lazy" title="map" src="https://www.openstreetmap.org/export/embed.html?bbox={(b.get('lon') or 0) - 0.006}%2C{(b.get('lat') or 0) - 0.004}%2C{(b.get('lon') or 0) + 0.006}%2C{(b.get('lat') or 0) + 0.004}&layer=mapnik&marker={b.get('lat') or 0}%2C{b.get('lon') or 0}"></iframe></section>""" if b.get("lat") else f"""<section><h2>Contact</h2><div class="facts">{facts}</div></section>
<section><h2>Send us a message</h2><form onsubmit="event.preventDefault();this.querySelector('button').textContent='Thanks — we will reply soon';"><input placeholder="Your name" required><input type="email" placeholder="Your e-mail" required><textarea rows="5" placeholder="How can we help?" required></textarea><button type="submit">Send</button></form></section>"""
        privacy = f"""<section><h2>Privacy</h2><p class="lead">{html.escape(b['name'])} only uses the information you send through the contact form to answer you. No tracking cookies are set by this website. To have your data removed, write to us at the address on the contact page.</p></section>"""
        for fn, body in (("index.html", home), ("about.html", about), ("services.html", services), ("gallery.html", gallery), ("contact.html", contact), ("privacy.html", privacy)):
            (d / fn).write_text(self._shell(b, c, fn, body, pages), encoding="utf-8")
        (d / "brief.json").write_text(json.dumps(b, ensure_ascii=False, indent=1))
        (d / "gallery").mkdir(exist_ok=True)
        with zipfile.ZipFile(d / f"{slug}.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for fn in d.glob("*.html"):
                z.write(fn, fn.name)
        self.log("site_built", name=b["name"], pages=len(pages), dir=str(d))
        return {"dir": d, "index": d / "index.html", "pages": [fn for fn, _ in pages] + ["privacy.html"], "copy": c, "slug": slug, "zip": d / f"{slug}.zip"}

    # ---- checking my own work ----------------------------------------------------------------------------------
    def check(self, built, screenshots=True):
        """Open every page in my browser: no broken links, no empty sections, mobile width works; screenshot the home page.
        Returns (problems list, shot path)."""
        problems, shot = [], None
        if not self.T:
            return problems, shot
        with self.T._session() as b:
            for fn in built["pages"]:
                url = "file://" + str(built["dir"] / fn)
                try:
                    b.open(url)
                    txt = b.extract_text()
                    if len(txt) < 120 or (fn == "index.html" and len(txt) < 500):
                        problems.append(f"{fn}: almost empty")
                    if re.search(r"lorem|\{|\}|None\b|undefined", txt):
                        problems.append(f"{fn}: template leftovers")
                    for l in b.links(80):
                        h = l.get("href") or ""
                        if h.startswith("file://") and not os.path.exists(urllib.parse.unquote(h[7:]).split("#")[0]):
                            problems.append(f"{fn}: broken link {os.path.basename(h)}")
                except Exception as e:
                    problems.append(f"{fn}: {str(e)[:60]}")
            try:
                b.open("file://" + str(built["index"]))
                b.page.set_viewport_size({"width": 390, "height": 800})
                w = b.page.evaluate("document.documentElement.scrollWidth")
                if w > 400:
                    problems.append(f"index: horizontal overflow on mobile ({w}px)")
                b.page.set_viewport_size({"width": 1280, "height": 800})
                if screenshots:
                    shot = str(built["dir"] / "screenshot.jpg")
                    b.page.screenshot(path=shot, type="jpeg", quality=70, full_page=False)
            except Exception as e:
                problems.append(f"viewport check failed: {str(e)[:60]}")
        self.T._release_page()
        return problems, shot

    # ---- the whole job -----------------------------------------------------------------------------------------
    def build_for(self, brief, notify_line=True):
        """Build + check + save (+ Drive). Returns (report line, built dict)."""
        t0 = time.time()
        if self.viewer:
            self.viewer.task = f"building a website for {brief['name']}"
        built = self.build(brief)
        problems, shot = (self.T.on_hands(self.check, built, timeout=300) if self.T else ([], None))
        if problems and self.T:
            self.log("site_problems", n=len(problems), first=problems[0][:80])
        link = ""
        if self.google and self.google.connected():
            try:
                folder = f"Websites"
                up = self.google.upload(built["zip"], folder=folder)
                self.google.upload(built["index"], name=f"{built['slug']}-preview.html", folder=folder)
                if shot:
                    self.google.upload(shot, name=f"{built['slug']}.jpg", folder=folder, mime="image/jpeg")
                link = up["link"]
            except Exception as e:
                self.log("site_upload_failed", error=str(e)[:100])
        where = ", ".join(x for x in (brief.get("city"), brief.get("country")) if x)
        report = (f"🌐 Built a website for {brief['name']} ({brief['kind']}{', ' + where if where else ''}) — {len(built['pages'])} pages"
                  + (f", {len(problems)} issue(s): {problems[0]}" if problems else ", checks passed") + f" ({time.time() - t0:.0f}s)"
                  + (f"\n☁️ Drive: {link}" if link else f"\n📁 {built['dir']}"))
        return report, built, shot

    def auto_train(self, rng=None):
        """One training round: random real place → website → check → save. Returns (report, built, shot)."""
        rng = rng or random.Random()
        last = None
        for _ in range(3):
            try:
                place = random_place(rng)
                break
            except Exception as e:
                last = e
                time.sleep(2)
        else:
            return f"auto-training skipped: could not fetch a place ({str(last)[:80]})", None, None
        self.log("site_train_place", name=place["name"], kind=place["kind"], city=place["city"], country=place["country"])
        return self.build_for(place)
