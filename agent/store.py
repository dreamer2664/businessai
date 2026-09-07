"""Practice store — a small shop that really works, served by the agent on this machine (milestone 11).

Why: before touching a real store, the AI must run a whole one end to end with the SAME skills it will use later —
read its own listings (/shop), answer customers from them, watch orders and stock, propose price/description changes,
and report the numbers. Nothing here moves real money: payment is a fake button, customers are simulated.

What it is:
  * a web shop (front): /            product list         /p/<id>       product page (options, add to cart)
                        /cart        cart + checkout      /checkout     name/e-mail/address, "Pay now" (fake)
                        /order/<n>   order page           /faq /shipping /returns /contact  help pages (owner-editable text)
  * an admin panel      /admin       orders, stock, prices (HTTP basic auth: admin / <store.token>)
                        /admin/order/<n>?do=ship|refund|cancel   /admin/product/<id> (price/stock/description form)
  * a ledger            state/store/store.json — products, orders, changes, day counters. Plain JSON, restorable.
  * simulated customers state/store/… — `simulate(day)` creates visits, orders, a message or two per practice day.

Rules (same as the rest of the agent):
  * every change the AI proposes (price, description, stock, refund, shipment) is a PROPOSAL that the owner taps to apply;
  * the AI never clicks "Pay now" — the fake payment is a customer's step, not the AI's;
  * the store listens on 127.0.0.1 only (the owner can open it in a browser on the same machine or through the WSL port).
"""
import datetime as _dt
import hashlib
import html
import json
import os
import random
import re
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config

STORE_DIR = config.STATE_DIR / "store"
LEDGER = STORE_DIR / "store.json"
PORT = int(os.environ.get("BAI_STORE_PORT", "8095"))

# ---- seed catalogue (a small eco home-goods dropshipping shop; the AI can change everything later, with approval) ----
SEED_PRODUCTS = [
    {"id": "bamboo-toothbrush-set", "name": "Bamboo Toothbrush Set (4 pcs)", "price": 12.90, "cost": 4.10, "stock": 38,
     "options": {"Bristles": ["Soft", "Medium"]},
     "short": "Four biodegradable bamboo toothbrushes with charcoal-infused bristles.",
     "details": ["4 toothbrushes, individually numbered so the family can tell them apart", "Handle: moso bamboo, water-resistant finish",
                 "Bristles: BPA-free nylon, soft or medium", "Packaging: recycled cardboard, no plastic", "Replace every 3 months, like any toothbrush"],
     "weight_g": 80},
    {"id": "stoneware-mug", "name": "Stoneware Coffee Mug 350 ml", "price": 14.90, "cost": 5.60, "stock": 21,
     "options": {"Colour": ["Sage green", "Sand", "Charcoal"]},
     "short": "Hand-glazed stoneware mug, dishwasher and microwave safe.",
     "details": ["Hand-glazed stoneware, lead-free and cadmium-free glaze", "Capacity 350 ml; height 9,5 cm, diameter 8,5 cm; weight 320 g",
                 "Dishwasher safe and microwave safe", "Made in Portugal", "Small variations in glaze colour are normal for hand-glazed pieces"],
     "weight_g": 320},
    {"id": "led-desk-lamp", "name": "LED Desk Lamp Nordic", "price": 39.00, "cost": 17.80, "stock": 3,
     "options": {},
     "short": "Rechargeable desk lamp with a beech base and an adjustable recycled-aluminium arm.",
     "details": ["Battery: 2000 mAh, up to 8 hours on the lowest setting, 3 hours on the highest",
                 "Charging: USB-C, cable included, full charge in 2,5 hours; no power adapter included",
                 "Light: 3 brightness levels, 3 colour temperatures (2700 K warm, 4000 K, 6000 K cool)",
                 "Arm: adjustable arm and head, folds flat for travel", "Material: beech wood base, recycled aluminium arm",
                 "Size: height 40 cm extended, base 12 x 12 cm, weight 650 g", "Warranty: 2 years", "Not waterproof — indoor use only"],
     "weight_g": 650},
    {"id": "cork-phone-case", "name": "Phone Case Cork", "price": 19.90, "cost": 6.20, "stock": 54,
     "options": {"Model": ["iPhone 15", "iPhone 15 Pro", "iPhone 14", "Samsung Galaxy S24"]},
     "short": "Natural cork on a recycled TPU shell; raised edge protects screen and camera.",
     "details": ["Natural cork on a recycled TPU shell; raised edge protects the screen and camera",
                 "Available for iPhone 15, iPhone 15 Pro, iPhone 14 and Samsung Galaxy S24 (no iPhone 15 Pro Max version)",
                 "Compatible with wireless charging", "Weight 28 g"],
     "weight_g": 28},
    {"id": "beeswax-wraps", "name": "Beeswax Food Wraps (3 sizes)", "price": 16.50, "cost": 5.90, "stock": 0,
     "options": {},
     "short": "Reusable food wraps: organic cotton, beeswax, jojoba oil and tree resin.",
     "details": ["Set of 3: small 18 x 18 cm, medium 25 x 25 cm, large 33 x 33 cm", "Organic cotton, beeswax, jojoba oil, tree resin",
                 "Wash in cool water with mild soap; lasts about a year", "Not for raw meat or hot food"],
     "weight_g": 60},
]
SEED_PAGES = {
    "shipping": "Destination · Cost · Time\nItaly · € 3,90 (free over € 39) · 2–3 business days\nGermany, France, Spain · € 6,90 · 4–6 business days\n"
                "Other EU countries · € 8,90 · 5–7 business days\nWe do not ship outside the EU yet; UK and Switzerland are planned for 2027.\n"
                "Orders ship within 1 business day. Carrier: GLS. Tracking number by e-mail as soon as the parcel leaves our warehouse in Bergamo.",
    "returns": "You can return any unused item within 30 days of delivery for a full refund. Return shipping costs € 4,90 unless the item was faulty or wrong.\n"
               "Refunds are issued within 5 business days after the returned item arrives. Faulty or wrong items are refunded or replaced at once.",
    "faq": "How long does delivery take? Orders ship within 1 business day. Delivery inside Italy takes 2–3 business days; the rest of the EU 4–7 business days.\n"
           "Do you ship outside the EU? Not yet. We plan to add the UK and Switzerland in 2027.\n"
           "Which payment methods do you accept? Credit and debit cards, PayPal and Apple Pay.\n"
           "How can I contact you? Write to help@greennest.example or use the contact form — we answer within 24 hours on working days.",
    "contact": "Green Nest — Eco Home Store\nhelp@greennest.example\nWe answer within 24 hours on working days.\nWarehouse: Bergamo, Italy.",
}
SHIP = [("IT", 3.90, 39.0), ("DE", 6.90, None), ("FR", 6.90, None), ("ES", 6.90, None), ("EU", 8.90, None)]

# simulated customers
FIRST = ["Anna", "Luca", "Marta", "Giulia", "Paolo", "Sara", "Jonas", "Lena", "Claire", "Marco", "Elena", "Tom", "Nina", "Davide", "Sofia"]
LAST = ["Rossi", "Bianchi", "Müller", "Schmidt", "Martin", "Bernard", "García", "Ferrari", "Conti", "Weber", "Moreau", "Russo"]
COUNTRIES = ["IT", "IT", "IT", "IT", "DE", "DE", "FR", "ES", "AT", "NL"]
CUSTOMER_MESSAGES = [
    ("Hi, I ordered {product} (order {order}) {when} and there is no tracking yet. When does it ship?", "where_is_my_order"),
    ("Is the {product} available in other colours?", "product_question"),
    ("Do you ship to Switzerland? I'd like the {product}.", "product_question"),
    ("The {product} arrived with a crack. Order {order}. What now?", "damaged_or_wrong"),
    ("Can I still return the {product} after 3 weeks? Who pays the return shipping?", "return_or_refund"),
    ("Hello! Do you have a discount code for a first order?", "discount_request"),
    ("I want to cancel order {order}, I ordered the wrong model.", "cancel_or_change"),
    ("Love the {product}, best purchase this year. Thank you!", "compliment"),
    ("How long does delivery to Germany take and what does it cost?", "product_question"),
    ("Is the {product} in stock? The page says only a few left.", "product_question"),
    ("Hello, where is my order? I paid {when} and heard nothing since.", "where_is_my_order"),
    ("My {product} arrived and one piece is missing. Order {order}.", "damaged_or_wrong"),
    ("Can I change the colour on order {order} before it ships?", "cancel_or_change"),
]


def _now():
    return _dt.datetime.now().isoformat(timespec="seconds")


def money(x):
    return f"€ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class Store:
    """The ledger + the rules. The HTTP front reads and writes through this object (one lock)."""

    def __init__(self, log=None):
        self.log = log or (lambda kind, **f: None)
        self.lock = threading.RLock()
        self.data = self._load()
        self.server = None
        self.thread = None
        self.host = "127.0.0.1"

    # ---- ledger ------------------------------------------------------------------
    def _load(self):
        try:
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        except Exception:
            pass
        d = {"name": "Green Nest — Eco Home Store", "token": secrets.token_urlsafe(9), "created": _now(), "day": 0,
             "products": [dict(p) for p in SEED_PRODUCTS], "pages": dict(SEED_PAGES), "orders": [], "next_order": 51001,
             "proposals": [], "changes": [], "visits": {}, "carts": {}}
        return d

    def save(self):
        with self.lock:
            STORE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = LEDGER.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(LEDGER)

    def reset(self):
        with self.lock:
            tok = self.data.get("token") or secrets.token_urlsafe(9)
            self.data = self._load() if not LEDGER.exists() else None
            try:
                LEDGER.unlink()
            except FileNotFoundError:
                pass
            self.data = self._load()
            self.data["token"] = tok
            self.save()

    # ---- catalogue -----------------------------------------------------------------
    def product(self, pid):
        return next((p for p in self.data["products"] if p["id"] == pid), None)

    def products(self):
        return self.data["products"]

    def find_product(self, text):
        """Best product for free text ('the lamp', 'cork case') — name words."""
        low = re.sub(r"\W+", " ", text.lower())
        best, score = None, 0
        for p in self.products():
            words = [w for w in re.findall(r"[a-z0-9]{3,}", p["name"].lower()) if w not in ("set", "pcs", "with")]
            sc = sum(1 for w in words if w in low or w.rstrip("s") in low)
            if sc > score:
                best, score = p, sc
        return best

    # ---- orders --------------------------------------------------------------------
    def shipping_for(self, country, subtotal):
        c = country.upper()
        for code, cost, free_over in SHIP:
            if code == c:
                return 0.0 if (free_over and subtotal >= free_over) else cost
        if c in ("AT", "NL", "BE", "PT", "IE", "PL", "SE", "DK", "FI", "GR", "CZ", "HU", "RO", "HR", "SI", "SK", "LT", "LV", "EE", "LU", "MT", "CY", "BG"):
            return SHIP[-1][1]
        return None                                                     # outside the EU: not offered

    def place_order(self, items, customer, country, simulated=False, day=None):
        """items: [(product_id, option_text, qty)] → order dict; stock is reserved at once (like a real shop)."""
        with self.lock:
            lines, subtotal = [], 0.0
            for pid, opt, qty in items:
                p = self.product(pid)
                if not p or qty < 1:
                    continue
                qty = min(qty, max(0, p["stock"]))
                if qty == 0:
                    continue
                p["stock"] -= qty
                lines.append({"id": pid, "name": p["name"], "option": opt, "qty": qty, "price": p["price"], "cost": p.get("cost", 0)})
                subtotal += qty * p["price"]
            if not lines:
                return None
            ship = self.shipping_for(country, subtotal)
            if ship is None:
                for l in lines:                                          # give the stock back
                    self.product(l["id"])["stock"] += l["qty"]
                return None
            n = self.data["next_order"]
            self.data["next_order"] += 1
            o = {"n": n, "t": _now(), "day": day if day is not None else self.data["day"], "customer": customer, "country": country.upper(),
                 "lines": lines, "subtotal": round(subtotal, 2), "shipping": ship, "total": round(subtotal + ship, 2),
                 "status": "paid", "events": [{"t": _now(), "what": "paid (practice payment)"}], "simulated": simulated}
            self.data["orders"].append(o)
            self.save()
            self.log("store_order", n=n, total=o["total"], simulated=simulated)
            return o

    def order(self, n):
        return next((o for o in self.data["orders"] if o["n"] == int(n)), None)

    def set_status(self, n, status, note=""):
        with self.lock:
            o = self.order(n)
            if not o:
                return False
            if status == "refunded" and o["status"] not in ("paid", "shipped", "delivered", "return_requested"):
                return False
            if status == "cancelled" and o["status"] != "paid":
                return False
            if status in ("refunded", "cancelled") and o["status"] in ("paid",):
                for l in o["lines"]:
                    p = self.product(l["id"])
                    if p:
                        p["stock"] += l["qty"]
            o["status"] = status
            o["events"].append({"t": _now(), "what": status + (f" — {note}" if note else "")})
            if status == "shipped":
                o["tracking"] = "GLS" + hashlib.sha1(str(n).encode()).hexdigest()[:10].upper()
            self.save()
            return True

    def note_reply(self, order_no, email, text):
        """File an approved customer reply: on the order's event list when the order is known, else in the message log."""
        with self.lock:
            o = self.order(order_no) if order_no and str(order_no).isdigit() else None
            entry = {"t": _now(), "what": f"replied to {email}: {text[:160]}"}
            if o:
                o["events"].append(entry)
            else:
                self.data.setdefault("replies", []).append({**entry, "to": email})
            self.save()
            return bool(o)

    def orders_for(self, email):
        """All orders placed with this e-mail address, newest first."""
        e = (email or "").strip().lower()
        return [o for o in reversed(self.data["orders"]) if e and o["customer"].get("email", "").lower() == e]

    # ---- what a customer-care reply may know about an order ----------------------------
    def order_facts(self, n, email=None):
        """Plain sentences about one order for the reply writer — only what the ledger really says. None when the order
        does not exist or belongs to another e-mail address (a customer must not learn about someone else's order)."""
        o = self.order(n) if str(n).isdigit() else None
        if not o:
            return None
        if email and o["customer"].get("email") and o["customer"]["email"].lower() != email.lower():
            return {"n": o["n"], "mismatch": True, "lines": [f"Order {o['n']} exists but was placed with a different e-mail address — ask the customer to write from the address used for the order (or to send the order confirmation)."]}
        items = ", ".join(f"{l['name']}" + (f" ({l['option']})" if l.get("option") else "") + f" ×{l['qty']}" for l in o["lines"])
        days_ago = max(0, self.data["day"] - o.get("day", self.data["day"]))
        lines = [f"Order {o['n']}: {items}, total {money(o['total'])}, to {o['country']}, placed {days_ago} day(s) ago (practice day {o.get('day')})."]
        st = o["status"]
        if st == "paid":
            lines.append(f"Status: PAID, NOT YET SHIPPED — it is still in the warehouse; it can still be cancelled and refunded in full; no tracking number exists yet.")
            if days_ago >= 2:
                lines.append(f"It was placed {days_ago} days ago — LATER than the promised 1 business day: apologise, say the owner has been asked to ship it today, and offer a full cancellation and refund instead if the customer prefers.")
        elif st == "shipped":
            lines.append(f"Status: SHIPPED with GLS, tracking number {o.get('tracking', '')}. It can no longer be cancelled; the customer can return it within 30 days of delivery.")
        elif st == "delivered":
            lines.append(f"Status: DELIVERED (tracking {o.get('tracking', '')}). Returns possible within 30 days of delivery.")
        elif st == "cancelled":
            lines.append("Status: CANCELLED and refunded.")
        elif st == "refunded":
            lines.append("Status: REFUNDED.")
        return {"n": o["n"], "status": st, "lines": lines, "tracking": o.get("tracking", ""), "days_ago": days_ago, "late": st == "paid" and days_ago >= 2, "order": o}

    # ---- proposals (the AI suggests, the owner applies) ----------------------------
    def propose(self, kind, target, change, why):
        with self.lock:
            pid = str(int(time.time() * 1000) % 10 ** 8)
            taken = {p["id"] for p in self.data["proposals"]}
            while pid in taken:                                   # never two proposals with one id (same-millisecond bug)
                pid = str(int(pid) + 1)
            prop = {"id": pid, "t": _now(), "kind": kind, "target": target, "change": change, "why": why, "status": "open"}
            self.data["proposals"].append(prop)
            self.save()
            return prop

    def proposal(self, pid):
        return next((p for p in self.data["proposals"] if p["id"] == pid), None)

    def apply(self, pid, by="owner"):
        """Apply an open proposal. Returns a plain-language line."""
        with self.lock:
            prop = self.proposal(pid)
            if not prop or prop["status"] != "open":
                return "That proposal is no longer open."
            k, t, ch = prop["kind"], prop["target"], prop["change"]
            out = ""
            if k == "price":
                p = self.product(t)
                if not p:
                    return "Product not found."
                old = p["price"]
                p["price"] = round(float(ch), 2)
                out = f"{p['name']}: price {money(old)} → {money(p['price'])}"
            elif k == "stock":
                p = self.product(t)
                if not p:
                    return "Product not found."
                old = p["stock"]
                p["stock"] = int(ch)
                out = f"{p['name']}: stock {old} → {p['stock']}"
            elif k == "description":
                p = self.product(t)
                if not p:
                    return "Product not found."
                p["short"] = str(ch)[:300]
                out = f"{p['name']}: description updated"
            elif k == "page":
                self.data["pages"][t] = str(ch)[:4000]
                out = f"page '{t}' updated"
            elif k in ("ship", "refund", "cancel"):
                ok = self.set_status(int(t), {"ship": "shipped", "refund": "refunded", "cancel": "cancelled"}[k], note=f"applied by {by}")
                if not ok:
                    prop["status"] = "failed"
                    self.save()
                    return f"Order {t} could not be {k}ped." if k == "ship" else f"Order {t} could not be {k}led/refunded (status {self.order(int(t))['status'] if self.order(int(t)) else '?'})."
                out = f"order {t} {'shipped' if k == 'ship' else 'refunded' if k == 'refund' else 'cancelled'}"
            prop["status"] = "applied"
            prop["applied_at"] = _now()
            self.data["changes"].append({"t": _now(), "by": by, "what": out, "why": prop["why"]})
            self.save()
            self.log("store_change", what=out)
            return out

    def reject(self, pid):
        with self.lock:
            prop = self.proposal(pid)
            if prop and prop["status"] == "open":
                prop["status"] = "rejected"
                self.save()
                return True
            return False

    def proposal_for_message(self, kind, order_no, text=""):
        """A customer asks to cancel / reports damage / wants to return → the matching proposal (or None)."""
        o = self.order(order_no) if str(order_no).isdigit() else None
        if not o:
            return None
        open_ = {(p["kind"], p["target"]) for p in self.data["proposals"] if p["status"] == "open"}
        if kind == "where_is_my_order" and o["status"] == "paid" and ("ship", str(o["n"])) not in open_:
            return self.propose("ship", str(o["n"]), "shipped", f"the customer is asking where order #{o['n']} is ({', '.join(l['name'] for l in o['lines'])}, {money(o['total'])}) and it has NOT shipped yet — hand it to GLS today and mark it shipped")
        if kind == "cancel_or_change" and o["status"] == "paid" and ("cancel", str(o["n"])) not in open_ and (not text or re.search(r"\bcancel", text.lower())):
            return self.propose("cancel", str(o["n"]), "cancelled", f"the customer asked to cancel order #{o['n']} ({', '.join(l['name'] for l in o['lines'])}, {money(o['total'])}) and it has not shipped — cancel and refund in full")
        if kind == "damaged_or_wrong" and o["status"] in ("shipped", "delivered") and ("refund", str(o["n"])) not in open_:
            return self.propose("refund", str(o["n"]), "refunded", f"the customer reports order #{o['n']} arrived damaged/wrong ({', '.join(l['name'] for l in o['lines'])}, {money(o['total'])}) — policy: refund or replace at once, no return needed for items under € 10")
        return None

    # ---- numbers -----------------------------------------------------------------
    def numbers(self, day=None):
        """Revenue, orders, margin, stock warnings — for one practice day (default: all)."""
        os_ = [o for o in self.data["orders"] if day is None or o.get("day") == day]
        paid = [o for o in os_ if o["status"] in ("paid", "shipped", "delivered")]
        refunded = [o for o in os_ if o["status"] == "refunded"]
        rev = sum(o["total"] for o in paid)
        cogs = sum(l["qty"] * l.get("cost", 0) for o in paid for l in o["lines"])
        ship_cost = sum(2.9 + 0.35 * sum(l["qty"] for l in o["lines"]) for o in paid)            # what the carrier charges us (practice figure)
        fees = sum(0.029 * o["total"] + 0.30 for o in paid)                                     # payment gateway
        units = {}
        for o in paid:
            for l in o["lines"]:
                units[l["name"]] = units.get(l["name"], 0) + l["qty"]
        # refunds and cancellations are not free: the gateway keeps its fee; a parcel that already left also cost the goods and the postage
        cancelled = [o for o in os_ if o["status"] == "cancelled"]
        losses = sum(0.029 * o["total"] + 0.30 for o in refunded + cancelled)
        losses += sum(2.9 + 0.35 * sum(l["qty"] for l in o["lines"]) + sum(l["qty"] * l.get("cost", 0) for l in o["lines"]) for o in refunded if o.get("tracking"))
        visits = sum(v for d, v in self.data["visits"].items() if day is None or int(d) == day)
        low = [p for p in self.products() if p["stock"] <= 3]
        return {"orders": len(paid), "refunded": len(refunded), "cancelled": len(cancelled), "losses": round(losses, 2), "revenue": round(rev, 2), "cogs": round(cogs, 2), "shipping_cost": round(ship_cost, 2),
                "fees": round(fees, 2), "profit": round(rev - cogs - ship_cost - fees - losses, 2), "units": units, "visits": visits,
                "conversion": (len(paid) / visits * 100) if visits else 0.0, "low_stock": [(p["name"], p["stock"]) for p in low],
                "open": [o for o in self.data["orders"] if o["status"] == "paid"]}

    def numbers_text(self, day=None):
        n = self.numbers(day)
        head = f"Practice store — {'day ' + str(day) if day is not None else 'all days'}"
        best = sorted(n["units"].items(), key=lambda x: -x[1])[:3]
        lines = [head,
                 f"visits {n['visits']} · orders {n['orders']} ({n['conversion']:.1f} % conversion) · refunded {n['refunded']} · cancelled {n['cancelled']}",
                 f"revenue {money(n['revenue'])} − goods {money(n['cogs'])} − shipping {money(n['shipping_cost'])} − fees {money(n['fees'])}"
                 + (f" − refunds/cancellations {money(n['losses'])}" if n["losses"] else "") + f" = profit {money(n['profit'])}"
                 + (f" ({n['profit'] / n['revenue'] * 100:.0f} % margin)" if n['revenue'] else "")]
        if best:
            lines.append("best sellers: " + ", ".join(f"{k} ×{v}" for k, v in best))
        if n["open"]:
            lines.append(f"to ship: {len(n['open'])} order(s) — " + ", ".join(f"#{o['n']}" for o in n["open"][:6]))
        if n["low_stock"]:
            lines.append("low stock: " + ", ".join(f"{k} ({v} left)" for k, v in n["low_stock"]))
        return "\n".join(lines)

    # ---- simulated customers -------------------------------------------------------
    def simulate_day(self, inbox=None):
        """One practice day: visits, a few orders, one or two customer messages (put into the inbox as channel 'store')."""
        with self.lock:
            self.data["day"] += 1
            day = self.data["day"]
            rnd = random.Random(day * 7919 + len(self.data["orders"]))
            visits = rnd.randint(35, 120)
            self.data["visits"][str(day)] = visits
            n_orders = max(0, int(visits * rnd.uniform(0.015, 0.045)))
            made = []
            for _ in range(n_orders):
                avail = [p for p in self.products() if p["stock"] > 0]
                if not avail:
                    break
                weights = [max(0.2, 1.5 - p["price"] / 40) for p in avail]                         # cheaper sells more
                p = rnd.choices(avail, weights=weights)[0]
                opt = ""
                if p["options"]:
                    k, vals = next(iter(p["options"].items()))
                    opt = f"{k}: {rnd.choice(vals)}"
                qty = 1 if rnd.random() < 0.8 else 2
                name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
                email = re.sub(r"[^a-z]", "", name.lower().split()[0]) + str(rnd.randint(1, 99)) + "@example.com"
                o = self.place_order([(p["id"], opt, qty)], {"name": name, "email": email}, rnd.choice(COUNTRIES), simulated=True, day=day)
                if o:
                    made.append(o)
            # earlier paid orders that were shipped get delivered; a shipped one may come back
            for o in self.data["orders"]:
                if o["status"] == "shipped" and o.get("day", 0) <= day - 3 and rnd.random() < 0.8:
                    o["status"] = "delivered"
                    o["events"].append({"t": _now(), "what": "delivered"})
            msgs = []
            if inbox is not None:
                n_msgs = 1 if rnd.random() < 0.7 else 2
                for _ in range(n_msgs):
                    tpl, kind = rnd.choice(CUSTOMER_MESSAGES)
                    pool = self.data["orders"]
                    if kind == "where_is_my_order":                       # people chase orders that are not delivered yet, usually older ones
                        pool = [o for o in pool if o["status"] in ("paid", "shipped")] or pool
                        older = [o for o in pool if o.get("day", day) <= day - 2]
                        pool = older or pool
                    elif kind == "damaged_or_wrong":                      # only something that arrived can be broken
                        pool = [o for o in pool if o["status"] in ("shipped", "delivered")] or pool
                    elif kind == "cancel_or_change":
                        pool = [o for o in pool if o["status"] == "paid"] or pool
                    ref = rnd.choice(pool) if pool else None
                    prod = (ref["lines"][0]["name"] if ref else rnd.choice(self.products())["name"])
                    ago = (day - ref.get("day", day)) if ref else 0
                    when = "today" if ago == 0 else "yesterday" if ago == 1 else f"{ago} days ago"
                    text = tpl.format(product=prod, order=ref["n"] if ref else 51000, when=when)
                    sender = (ref["customer"]["email"] if ref else f"{rnd.choice(FIRST).lower()}@example.com")
                    rec = inbox.add("store", sender, text, subject=f"Question about {prod}"[:60])
                    msgs.append(rec)
            self.save()
            self.log("store_day", day=day, visits=visits, orders=len(made), messages=len(msgs))
            return {"day": day, "visits": visits, "orders": made, "messages": msgs}

    # ---- the AI's own review: what would a careful shopkeeper propose today? ---------
    def review(self):
        """Rule-based proposals (no model): unshipped orders, out-of-stock listings, low stock, price sanity."""
        props = []
        with self.lock:
            open_ids = {p["target"] for p in self.data["proposals"] if p["status"] == "open"}
            for o in self.data["orders"]:
                if o["status"] == "paid" and str(o["n"]) not in open_ids:
                    props.append(self.propose("ship", str(o["n"]), "shipped", f"order #{o['n']} is paid and waiting ({', '.join(l['name'] + ' ×' + str(l['qty']) for l in o['lines'])}) — mark it shipped once the parcel is handed to GLS"))
            sold = {}                                                          # units sold per product in the last 7 practice days → reorder by demand
            for o in self.data["orders"]:
                if o["status"] in ("paid", "shipped", "delivered") and o.get("day", 0) > self.data["day"] - 7:
                    for l in o["lines"]:
                        sold[l["id"]] = sold.get(l["id"], 0) + l["qty"]
            rejected = {(p["kind"], p["target"]) for p in self.data["proposals"] if p["status"] == "rejected"}
            for p in self.products():
                if p["id"] in open_ids:
                    continue
                weekly = sold.get(p["id"], 0)
                if p["stock"] == 0:
                    qty = max(25, 3 * weekly)
                    props.append(self.propose("stock", p["id"], qty, f"{p['name']} is sold out and still listed — reorder from the supplier (suggested {qty} units" + (f" = 3 weeks at {weekly}/week" if weekly else "") + ") or hide it; until then customers see 'out of stock'"))
                elif p["stock"] <= max(3, weekly):
                    qty = p["stock"] + max(20, 3 * weekly)
                    props.append(self.propose("stock", p["id"], qty, f"{p['name']} has only {p['stock']} left" + (f" and sold {weekly} last week" if weekly else "") + f" — reorder now (suggested +{qty - p['stock']}) so it is not out of stock this week"))
                margin = (p["price"] - p.get("cost", 0)) / p["price"] if p["price"] else 0
                if margin < 0.55 and p.get("cost") and ("price", p["id"]) not in rejected:   # the owner said 'leave it' once → do not nag
                    new = round(p["cost"] / 0.4 + 0.0, 1) - 0.1
                    props.append(self.propose("price", p["id"], new, f"{p['name']} sells at {money(p['price'])} with a landed cost of {money(p['cost'])} — {margin*100:.0f} % gross margin is thin once shipping (~€ 3,25) and fees (2,9 % + € 0,30) are paid; {money(new)} keeps ~60 %"))
        return props


# ---- HTTP front ---------------------------------------------------------------------------------------------------
CSS = ("body{font-family:system-ui,sans-serif;margin:0;background:#f7f7f4;color:#222}header{background:#2f5d3a;color:#fff;padding:14px 24px}"
       "header a{color:#fff;text-decoration:none;margin-right:16px}main{max-width:900px;margin:0 auto;padding:20px}"
       ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px}.card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px}"
       ".price{color:#2f5d3a;font-size:20px;font-weight:600}button,.btn{background:#2f5d3a;color:#fff;border:0;padding:9px 14px;border-radius:6px;cursor:pointer;font-size:15px}"
       "table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #e5e5e5;padding:6px 8px;text-align:left}footer{color:#777;font-size:12px;padding:20px 24px}"
       "input,select,textarea{padding:7px;border:1px solid #bbb;border-radius:6px;font-size:15px}label{display:block;margin:8px 0}.muted{color:#777}.warn{color:#a33}")


def page(title, body, store, admin=False):
    nav = ('<a href="/">Shop</a><a href="/cart">Cart</a><a href="/faq">Help</a><a href="/shipping">Shipping</a><a href="/returns">Returns</a><a href="/contact">Contact</a>'
           if not admin else '<a href="/admin">Orders</a><a href="/admin/products">Products &amp; stock</a><a href="/admin/changes">Changes</a><a href="/">Shop front</a>')
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)} — {html.escape(store.data['name'])}</title><style>{CSS}</style></head>"
            f"<body><header><b>{html.escape(store.data['name'])}</b> &nbsp; {nav}</header><main><h1>{html.escape(title)}</h1>{body}</main>"
            f"<footer>Practice store run by Business AI — nothing here is real: payments are simulated, customers are simulated. "
            f"Free returns within 30 days · help@greennest.example</footer></body></html>")


class Handler(BaseHTTPRequestHandler):
    store = None       # set by Store.start()
    inbox = None
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    # -- helpers
    def _send(self, body, code=200, ctype="text/html; charset=utf-8", extra=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, where, extra=None):
        self.send_response(303)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _form(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8") if n else ""
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}

    def _cart_id(self):
        m = re.search(r"cart=([A-Za-z0-9_-]{6,40})", self.headers.get("Cookie") or "")
        return m.group(1) if m else None

    def _cart(self):
        cid = self._cart_id()
        if not cid:
            cid = secrets.token_urlsafe(8)
            self._new_cookie = f"cart={cid}; Path=/; HttpOnly"
        return cid, self.store.data["carts"].setdefault(cid, [])

    def _admin_ok(self):
        auth = self.headers.get("Authorization") or ""
        if auth.startswith("Basic "):
            try:
                import base64
                user, pw = base64.b64decode(auth[6:]).decode().split(":", 1)
                return user == "admin" and secrets.compare_digest(pw, self.store.data["token"])
            except Exception:
                return False
        return False

    def _need_auth(self):
        self._send("Admin login needed.", 401, extra={"WWW-Authenticate": 'Basic realm="practice store admin"'})

    # -- routes
    def do_GET(self):
        s = self.store
        self._new_cookie = None
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        p = u.path.rstrip("/") or "/"
        try:
            if p == "/":
                return self._front()
            if p.startswith("/p/"):
                return self._product(p[3:])
            if p == "/cart":
                return self._cart_page()
            if p == "/checkout":
                return self._checkout()
            if p.startswith("/order/"):
                return self._order_page(p[7:])
            if p in ("/faq", "/shipping", "/returns", "/contact"):
                return self._help(p[1:])
            if p == "/robots.txt":
                return self._send("User-agent: *\nDisallow: /admin\n", ctype="text/plain")
            if p.startswith("/admin"):
                if not self._admin_ok():
                    return self._need_auth()
                if p == "/admin":
                    return self._admin_orders()
                if p == "/admin/products":
                    return self._admin_products()
                if p == "/admin/changes":
                    return self._admin_changes()
                if p.startswith("/admin/order/"):
                    return self._admin_order(p[13:], q.get("do"))
                if p.startswith("/admin/product/"):
                    return self._admin_product(p[15:])
            if p == "/api/numbers":
                return self._send(json.dumps(s.numbers(), default=str), ctype="application/json")
            self._send(page("Not found", "<p>That page does not exist.</p>", s), 404)
        except Exception as e:
            self._send(page("Error", f"<p class=warn>{html.escape(str(e)[:200])}</p>", s), 500)

    def do_POST(self):
        s = self.store
        self._new_cookie = None
        u = urllib.parse.urlparse(self.path)
        p = u.path.rstrip("/")
        f = self._form()
        try:
            if p == "/cart/add":
                cid, cart = self._cart()
                prod = s.product(f.get("id", ""))
                if prod and prod["stock"] > 0:
                    opt = f.get("option", "")
                    qty = max(1, min(5, int(f.get("qty") or 1)))
                    for line in cart:
                        if line["id"] == prod["id"] and line["option"] == opt:
                            line["qty"] += qty
                            break
                    else:
                        cart.append({"id": prod["id"], "option": opt, "qty": qty})
                    s.save()
                return self._redirect("/cart", {"Set-Cookie": self._new_cookie} if self._new_cookie else None)
            if p == "/cart/remove":
                cid, cart = self._cart()
                cart[:] = [l for l in cart if not (l["id"] == f.get("id") and l["option"] == f.get("option", ""))]
                s.save()
                return self._redirect("/cart")
            if p == "/checkout/pay":
                cid, cart = self._cart()
                if not cart:
                    return self._redirect("/cart")
                name, email, country = f.get("name", "").strip(), f.get("email", "").strip(), f.get("country", "IT").strip().upper()
                if not name or "@" not in email:
                    return self._send(page("Checkout", "<p class=warn>Name and a valid e-mail are needed.</p><p><a href='/checkout'>Back</a></p>", s))
                o = s.place_order([(l["id"], l["option"], l["qty"]) for l in cart], {"name": name, "email": email, "address": f.get("address", "")[:200]}, country)
                if not o:
                    return self._send(page("Checkout", "<p class=warn>We cannot ship to that destination yet, or the items are out of stock.</p><p><a href='/cart'>Back to cart</a></p>", s))
                s.data["carts"].pop(cid, None)
                s.save()
                return self._redirect(f"/order/{o['n']}")
            if p == "/contact/send":
                if self.inbox is not None and f.get("message", "").strip():
                    self.inbox.add("store", f.get("email", "visitor@example.com").strip() or "visitor@example.com", f["message"].strip()[:1500], subject="Contact form")
                return self._send(page("Contact", "<p>Thank you — we answer within 24 hours on working days.</p>", s))
            if p.startswith("/admin/"):
                if not self._admin_ok():
                    return self._need_auth()
                if p.startswith("/admin/product/"):
                    prod = s.product(p[15:])
                    if prod:
                        with s.lock:
                            before = (prod["price"], prod["stock"], prod["short"])
                            prod["price"] = round(float(f.get("price") or prod["price"]), 2)
                            prod["stock"] = int(f.get("stock") or 0)
                            prod["short"] = f.get("short", prod["short"])[:300]
                            s.data["changes"].append({"t": _now(), "by": "owner (admin panel)", "what": f"{prod['name']}: price {money(before[0])}→{money(prod['price'])}, stock {before[1]}→{prod['stock']}", "why": "edited in the admin panel"})
                            s.save()
                    return self._redirect("/admin/products")
                if p.startswith("/admin/page/"):
                    key = p[12:]
                    if key in s.data["pages"]:
                        with s.lock:
                            s.data["pages"][key] = f.get("text", "")[:4000]
                            s.data["changes"].append({"t": _now(), "by": "owner (admin panel)", "what": f"page '{key}' edited", "why": ""})
                            s.save()
                    return self._redirect("/admin/products")
            self._send(page("Not found", "<p>That page does not exist.</p>", s), 404)
        except Exception as e:
            self._send(page("Error", f"<p class=warn>{html.escape(str(e)[:200])}</p>", s), 500)

    # -- front pages
    def _front(self):
        s = self.store
        cards = []
        for p in s.products():
            avail = "In stock" if p["stock"] > 5 else (f"Only {p['stock']} left" if p["stock"] > 0 else "Out of stock")
            cards.append(f"<div class=card><a href='/p/{p['id']}'><b>{html.escape(p['name'])}</b></a><div class=price>{money(p['price'])}</div>"
                         f"<div class=muted>{html.escape(p['short'])}</div><div>{avail}</div></div>")
        body = f"<div class=grid>{''.join(cards)}</div>"
        self._send(page("All products", body, s))

    def _product(self, pid):
        s = self.store
        p = s.product(pid)
        if not p:
            return self._send(page("Not found", "<p>No such product.</p>", s), 404)
        avail = "In stock — ships in 1 business day" if p["stock"] > 5 else (f"Only {p['stock']} left — ships in 1 business day" if p["stock"] > 0 else "Out of stock")
        opts = ""
        for k, vals in p["options"].items():
            opts = f"<label>{html.escape(k)}: <select name=option>" + "".join(f"<option>{html.escape(k)}: {html.escape(v)}</option>" for v in vals) + "</select></label>"
        form = (f"<form method=post action='/cart/add'><input type=hidden name=id value='{p['id']}'>{opts}"
                f"<label>Quantity: <input name=qty value=1 size=3></label>"
                + (f"<button type=submit>Add to cart</button>" if p["stock"] > 0 else "<button disabled>Out of stock</button>") + "</form>")
        details = "".join(f"<li>{html.escape(d)}</li>" for d in p["details"])
        body = (f"<div class=price>{money(p['price'])} incl. VAT</div><p>{html.escape(p['short'])}</p><p>{avail}</p>{form}"
                f"<h3>Details</h3><ul>{details}</ul>")
        self._send(page(p["name"], body, s))

    def _cart_page(self):
        s = self.store
        cid, cart = self._cart()
        if not cart:
            return self._send(page("Your cart", "<p>Your cart is empty — 0 items.</p><p><a class=btn href='/'>Continue shopping</a></p>", s),
                              extra={"Set-Cookie": self._new_cookie} if self._new_cookie else None)
        rows, total, n = [], 0.0, 0
        for l in cart:
            p = s.product(l["id"])
            if not p:
                continue
            rows.append(f"<tr><td>{html.escape(p['name'])}<br><span class=muted>{html.escape(l['option'])}</span></td><td>{l['qty']}</td><td>{money(p['price'] * l['qty'])}</td>"
                        f"<td><form method=post action='/cart/remove'><input type=hidden name=id value='{p['id']}'><input type=hidden name=option value='{html.escape(l['option'])}'><button>Remove</button></form></td></tr>")
            total += p["price"] * l["qty"]
            n += l["qty"]
        body = (f"<p>{n} item{'s' if n != 1 else ''} in your cart.</p><table><tr><th>Item</th><th>Qty</th><th>Price</th><th></th></tr>{''.join(rows)}</table>"
                f"<p>Subtotal: <b>{money(total)}</b> · shipping is calculated at checkout (Italy € 3,90, free over € 39)</p><p><a class=btn href='/checkout'>Checkout</a></p>")
        self._send(page("Your cart", body, s), extra={"Set-Cookie": self._new_cookie} if self._new_cookie else None)

    def _checkout(self):
        s = self.store
        cid, cart = self._cart()
        if not cart:
            return self._redirect("/cart")
        sub = sum(s.product(l["id"])["price"] * l["qty"] for l in cart if s.product(l["id"]))
        body = (f"<p>Subtotal {money(sub)}. Shipping: Italy {money(s.shipping_for('IT', sub))}, Germany/France/Spain € 6,90, other EU € 8,90.</p>"
                "<form method=post action='/checkout/pay'><label>Name <input name=name required></label><label>E-mail <input name=email type=email required></label>"
                "<label>Address <input name=address size=40></label><label>Country <select name=country><option value=IT>Italy</option><option value=DE>Germany</option>"
                "<option value=FR>France</option><option value=ES>Spain</option><option value=AT>Austria</option><option value=NL>Netherlands</option><option value=CH>Switzerland</option><option value=GB>United Kingdom</option></select></label>"
                "<p><button type=submit>Pay now (practice payment — no real money)</button></p></form>")
        self._send(page("Checkout", body, s), extra={"Set-Cookie": self._new_cookie} if self._new_cookie else None)

    def _order_page(self, n):
        s = self.store
        o = s.order(n) if n.isdigit() else None
        if not o:
            return self._send(page("Order", "<p>No such order.</p>", s), 404)
        rows = "".join(f"<tr><td>{html.escape(l['name'])} <span class=muted>{html.escape(l['option'])}</span></td><td>{l['qty']}</td><td>{money(l['price'] * l['qty'])}</td></tr>" for l in o["lines"])
        ev = "".join(f"<li>{html.escape(e['t'][:16])} — {html.escape(e['what'])}</li>" for e in o["events"] if not e["what"].startswith("replied to"))
        body = (f"<p>Thank you, {html.escape(o['customer'].get('name', ''))}! Order <b>#{o['n']}</b> — status: <b>{o['status']}</b>" + (f" · tracking {o['tracking']}" if o.get("tracking") else "") + "</p>"
                f"<table>{rows}<tr><td>Shipping ({o['country']})</td><td></td><td>{money(o['shipping'])}</td></tr><tr><td><b>Total</b></td><td></td><td><b>{money(o['total'])}</b></td></tr></table><ul>{ev}</ul>")
        self._send(page(f"Order #{o['n']}", body, s))

    def _help(self, key):
        s = self.store
        text = s.data["pages"].get(key, "")
        if key == "shipping" and "·" in text:
            rows = [l.split("·") for l in text.splitlines() if "·" in l]
            rest = [l for l in text.splitlines() if "·" not in l]
            table = "<table>" + "".join("<tr>" + "".join(f"<td>{html.escape(c.strip())}</td>" for c in r) + "</tr>" for r in rows) + "</table>"
            body = table + "".join(f"<p>{html.escape(l)}</p>" for l in rest)
        elif key == "faq":
            body = "".join(f"<h3>{html.escape(l.split('? ')[0])}?</h3><p>{html.escape(l.split('? ', 1)[1] if '? ' in l else l)}</p>" for l in text.splitlines() if l.strip())
        elif key == "contact":
            body = "".join(f"<p>{html.escape(l)}</p>" for l in text.splitlines()) + ("<form method=post action='/contact/send'><label>Your e-mail <input name=email type=email></label>"
                                                                                       "<label>Message<br><textarea name=message rows=4 cols=50></textarea></label><button>Send</button></form>")
        else:
            body = "".join(f"<p>{html.escape(l)}</p>" for l in text.splitlines())
        self._send(page({"faq": "Help — frequently asked questions", "shipping": "Shipping", "returns": "Returns & refunds", "contact": "Contact us"}[key], body, s))

    # -- admin
    def _admin_orders(self):
        s = self.store
        rows = []
        for o in reversed(s.data["orders"][-60:]):
            acts = " ".join(f"<a href='/admin/order/{o['n']}?do={a}'>{a}</a>" for a in (["ship", "cancel"] if o["status"] == "paid" else ["refund"] if o["status"] in ("shipped", "delivered") else []))
            rows.append(f"<tr><td><a href='/admin/order/{o['n']}'>#{o['n']}</a></td><td>day {o.get('day')}</td><td>{html.escape(o['customer'].get('name', ''))} ({o['country']})</td>"
                        f"<td>{html.escape(', '.join(l['name'] + ' ×' + str(l['qty']) for l in o['lines']))}</td><td>{money(o['total'])}</td><td>{o['status']}</td><td>{acts}</td></tr>")
        body = f"<pre>{html.escape(s.numbers_text())}</pre><table><tr><th>Order</th><th>Day</th><th>Customer</th><th>Items</th><th>Total</th><th>Status</th><th>Actions</th></tr>{''.join(rows)}</table>"
        self._send(page("Orders", body, s, admin=True))

    def _admin_order(self, n, do):
        s = self.store
        o = s.order(n) if n.isdigit() else None
        if not o:
            return self._send(page("Order", "<p>No such order.</p>", s, admin=True), 404)
        if do in ("ship", "cancel", "refund"):
            s.set_status(o["n"], {"ship": "shipped", "cancel": "cancelled", "refund": "refunded"}[do], note="admin panel")
            s.data["changes"].append({"t": _now(), "by": "owner (admin panel)", "what": f"order #{o['n']} {do}", "why": ""})
            s.save()
            return self._redirect("/admin")
        ev = "".join(f"<li>{html.escape(e['t'][:16])} — {html.escape(e['what'])}</li>" for e in o["events"])
        body = (f"<p>{html.escape(o['customer'].get('name', ''))} · {html.escape(o['customer'].get('email', ''))} · {o['country']} · {o['status']}</p>"
                f"<p>{html.escape(', '.join(l['name'] + ' (' + l['option'] + ') ×' + str(l['qty']) for l in o['lines']))} — total {money(o['total'])}</p><ul>{ev}</ul>"
                + " ".join(f"<a class=btn href='/admin/order/{o['n']}?do={a}'>{a}</a>" for a in (["ship", "cancel"] if o["status"] == "paid" else ["refund"] if o["status"] in ("shipped", "delivered") else [])))
        self._send(page(f"Order #{o['n']}", body, s, admin=True))

    def _admin_products(self):
        s = self.store
        rows = "".join(f"<tr><td><a href='/admin/product/{p['id']}'>{html.escape(p['name'])}</a></td><td>{money(p['price'])}</td><td>{money(p.get('cost', 0))}</td>"
                       f"<td>{(p['price'] - p.get('cost', 0)) / p['price'] * 100:.0f} %</td><td class='{'warn' if p['stock'] <= 3 else ''}'>{p['stock']}</td></tr>" for p in s.products())
        pages_ = "".join(f"<h3>{k}</h3><form method=post action='/admin/page/{k}'><textarea name=text rows=5 cols=90>{html.escape(v)}</textarea><br><button>Save</button></form>" for k, v in s.data["pages"].items())
        body = f"<table><tr><th>Product</th><th>Price</th><th>Cost</th><th>Margin</th><th>Stock</th></tr>{rows}</table><h2>Help pages</h2>{pages_}"
        self._send(page("Products & stock", body, s, admin=True))

    def _admin_product(self, pid):
        s = self.store
        p = s.product(pid)
        if not p:
            return self._send(page("Product", "<p>No such product.</p>", s, admin=True), 404)
        body = (f"<form method=post action='/admin/product/{p['id']}'><label>Price € <input name=price value='{p['price']:.2f}'></label>"
                f"<label>Stock <input name=stock value='{p['stock']}'></label><label>Short description<br><textarea name=short rows=3 cols=80>{html.escape(p['short'])}</textarea></label>"
                f"<p class=muted>Landed cost {money(p.get('cost', 0))} · weight {p.get('weight_g', 0)} g</p><button>Save</button></form>")
        self._send(page(p["name"], body, s, admin=True))

    def _admin_changes(self):
        s = self.store
        rows = "".join(f"<tr><td>{html.escape(c['t'][:16])}</td><td>{html.escape(c['by'])}</td><td>{html.escape(c['what'])}</td><td class=muted>{html.escape(c.get('why', ''))}</td></tr>" for c in reversed(s.data["changes"][-100:]))
        props = "".join(f"<tr><td>{html.escape(p['t'][:16])}</td><td>{p['kind']} {html.escape(str(p['target']))} → {html.escape(str(p['change']))}</td><td>{p['status']}</td><td class=muted>{html.escape(p['why'][:160])}</td></tr>" for p in reversed(s.data["proposals"][-100:]))
        body = f"<h2>Applied changes</h2><table>{rows}</table><h2>AI proposals</h2><table>{props}</table>"
        self._send(page("Changes", body, s, admin=True))


def start(store, inbox=None, port=PORT, host="127.0.0.1"):
    """Serve the store in a background thread. Returns (server, url)."""
    Handler.store = store
    Handler.inbox = inbox
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True, name="store-http")
    t.start()
    store.server, store.thread, store.host = srv, t, host
    store.log("store_started", url=f"http://{host}:{port}/")
    return srv, f"http://{host}:{port}/"


def stop(store):
    if store.server:
        try:
            store.server.shutdown()
            store.server.server_close()
        except Exception:
            pass
        store.server = None
