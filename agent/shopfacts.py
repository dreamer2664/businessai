"""Shop facts — what the owner's OWN shop pages say about delivery, costs, returns, contact and payment.

/shop <address>  → the browser opens the shop, follows its help / shipping / returns / contact / FAQ links (same site only,
at most a handful of pages), and keeps every sentence that states a fact about those topics, word for word, with the page it
came from. No model is involved: a fact is always a sentence that really stands on the shop's page.

Customer-reply drafts then get these sentences as "facts from the shop's own website" and the safety checks accept the
figures they contain (a reply may say "2–3 business days" when the shipping page says so). The sheet lives in
state/shopfacts.json and is refreshed by itself about once a week when the agent is idle.
"""
import json, re, time, urllib.parse
from . import config

SHEET = config.STATE_DIR / "shopfacts.json"
MAX_PAGES = 7                 # start page + up to 6 help pages
MAX_FACTS = 40
REFRESH_DAYS = 7

# links worth following (label or address), in priority order
PAGE_WORDS = [
    ("shipping", r"(shipping|delivery|deliver|spedizion|consegn|livraison|versand|lieferung|verzend|bezorg)"),
    ("returns", r"(return|resi\b|reso\b|rimbors|retour|rückgabe|ruckgabe|widerruf|recesso|refund|garanzia|guarantee|warranty|exchange)"),
    ("help", r"(faq|help|aiuto|hilfe|aide|support|assistenza|customer service|servizio clienti|kundenservice|service client|domande)"),
    ("contact", r"(contact|contatt|kontakt)"),
    ("payment", r"(payment|pagament|zahlung|paiement|pay\b)"),
    ("about", r"(about|chi siamo|über uns|uber uns|à propos|a propos|our story|la nostra storia)"),
    ("terms", r"(terms|condizioni|termini|agb\b|cgv\b|policy|policies)"),
]
# links to product listings (collections / catalogue / shop-all) and words that mark a product page
LISTING_WORDS = re.compile(r"(shop all|all products|tutti i prodotti|catalog|catalogue|collection|collezion|products?$|prodotti|"
                           r"/shop/?$|/store/?$|/collections?/|/categor|/negozio|/boutique|/produkte|/produits|/producten|new arrivals|"
                           r"bestsellers?|best sellers|\bshop\b|negozio)", re.I)
PRODUCT_URL = re.compile(r"(/products?/|/prodott[oi]/|/produkt|/produit|/product_|/p/|/item/|/dp/|product_[a-z0-9_-]+\.html?$)", re.I)
PRICE_RE = re.compile(r"(?:€|eur|\$|£|chf|usd|gbp)\s?\d{1,5}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d{1,5}(?:[.,]\d{3})*(?:[.,]\d{1,2})?\s?(?:€|eur\b|\$|£|chf\b|usd\b|gbp\b)", re.I)
MAX_PRODUCTS = 40
MAX_PRODUCT_PAGES = 12
SKIP_LINK = re.compile(r"(login|log-in|signin|sign-in|account|cart|carrello|checkout|privacy|cookie|wishlist|register|"
                       r"\.pdf$|\.jpg$|\.png$|mailto:|tel:|javascript:|whatsapp|facebook\.com|instagram\.com|twitter\.com|"
                       r"tiktok\.com|youtube\.com|linkedin\.com|pinterest\.com)", re.I)

# a sentence is a fact when it names a topic AND carries the kind of detail customers ask about
TOPICS = [
    ("delivery time",
     r"(deliver|shipping|ship\b|ships\b|shipped|dispatch|arriv|consegn|spedizion|spedit|livraison|livr|versand|lieferung|liefer|verzend|bezorg|order)",
     r"\b\d+\s*(?:[-–—]|to|a|à|bis)?\s*\d*\s*(business |working |lavorativ\w* |ouvr\w* |werk\w* )?(day|days|giorn\w*|jour\w*|tag\w*|hour\w*|ore\b|heure\w*|stund\w*|week\w*|settiman\w*|semaine\w*|woche\w*)"),
    ("shipping cost",
     r"(deliver|shipping|ship\b|ships\b|consegn|spedizion|livraison|frais de port|versand|verzend|bezorg)",
     r"(€|eur\b|euro|\$|£|chf|free\b|gratis|gratuit|kostenlos|cost|costo|prezzo|tarif|charge)"),
    ("where we ship",
     r"(ship\b|ships\b|shipping|deliver|spedi|consegn|liefer|livr|verzend|bezorg)",
     r"\b(to|outside|countr\w*|eu\b|europe|european|worldwide|international\w*|only|not yet|not\b|non\b|estero|paesi|ausland|abroad|uk\b|switzerland|svizzera|usa\b|world|italia|italy|germany|germania|france|francia|spain|spagna)\b"),
    ("returns & refunds",
     r"(return|refund|reso\b|resi\b|rimbors|restitu|retour|rembours|rückgabe|ruckgabe|rücksend|erstatt|widerruf|recesso|garanzia|guarantee|warranty|exchange|cambio|sostituz)",
     r"(\d|free\b|gratis|gratuit|kostenlos|cost|unused|original|condition|label|etichetta|receipt|scontrino|faulty|difett|damaged|dannegg)"),
    ("contact",
     r"([\w.+-]+@[\w-]+\.[\w.-]+|\+?\d[\d ().-]{7,}\d|contact|contatt|kontakt|support|assistenza|help\b|aiuto|chat\b|whatsapp|telefon|phone|hotline|write to|scriv|e-?mail)",
     r"(@|\d|chat|whatsapp|hour|ore\b|orari|day|giorn|business|working|lavorativ|answer|reply|respond|rispond|risposta|antwort|répond|repond)"),
    ("payment",
     r"(payment|pay\b|paypal|credit card|debit card|carta di credito|carta|pagament|klarna|apple pay|google pay|bank transfer|bonifico|contrassegno|cash on delivery|zahlung|paiement|ideal\b|sofort|scalapay|satispay|amex|visa|mastercard)",
     r"."),
    ("about the shop",
     r"(founded|fondat|gegründet|warehouse|magazzino|based in|con sede|sede a|our team|il nostro team|family business|since \d{4}|dal \d{4}|depuis \d{4}|seit \d{4})",
     r"."),
]
TOPIC_RES = [(name, re.compile(a, re.I), re.compile(b, re.I)) for name, a, b in TOPICS]
JUNK = re.compile(r"^(©|cookie|we use cookies|utilizziamo i cookie|accept all|reject all|subscribe|iscriviti|sign up|newsletter\b|"
                  r"follow us|seguici|share\b|condividi|skip to|vai al contenuto)", re.I)
# questions customers ask → the topics whose facts help answer them
ASK_TOPICS = [
    (r"\b(?:deliver|shipping|ship\b|ships\b|shipped|arriv|dispatch|how long|when will|tracking|track\b|consegn|spedi|quando arriva|livraison|lieferung|versand|verzend|bezorg|levering)",
     ("delivery time", "shipping cost", "where we ship")),
    (r"\b(?:cost|price of shipping|shipping fee|fee\b|free shipping|how much|quanto costa|spese di spedizione|frais de port|versandkosten|verzendkosten)", ("shipping cost",)),
    (r"\b(?:to (?:the )?(?:uk|us|usa|switzerland|germany|france|spain|austria|netherlands|belgium|ireland|australia|canada|europe|eu)\b|outside|abroad|international|my country|countries|spedite in|all'estero|in (?:svizzera|germania|francia|spagna|inghilterra)|nach (?:deutschland|österreich|der schweiz)|ausland|étranger|etranger|buitenland)",
     ("where we ship",)),
    (r"\b(?:return|refund|send (?:it )?back|exchange|money back|withdraw|cancel|warranty|guarantee|faulty|broken|damaged|wrong (?:item|size|colour|color)|res[oi]\b|restitu|rimbors|garanzia|recesso|cambio|retour|rembours|rückgabe|ruckgabe|erstattung|widerruf|umtausch|terugstur|retourn)",
     ("returns & refunds",)),
    (r"\b(?:phone|call\b|e-?mail|address|contact|speak to|talk to|reach you|opening hours|whatsapp|chat\b|telefon|contatt|numero|chiamar|kontakt|joindre|appeler|bereiken|bellen)", ("contact",)),
    (r"\b(?:pay\b|paying|payment|paypal|card\b|klarna|instal?ments|bank transfer|cash on delivery|invoice|receipt|pagar|pagament|bonifico|contrassegno|fattura|zahl|bezahl|rechnung|paiement|payer|facture|betal|factuur)", ("payment",)),
    (r"\b(?:who are you|where are you|based\b|located|warehouse|company|about you|chi siete|dove siete|wer seid|wo seid|qui êtes|où êtes|wie zijn)", ("about the shop",)),
]

_JS_FACT_TEXT = r"""
() => {
  const root = document.querySelector('main, article, [role=main]') || document.body;
  const skip = new Set(['SCRIPT','STYLE','NOSCRIPT','NAV','HEADER','FOOTER','ASIDE','SVG','TEMPLATE','IFRAME','BUTTON','SELECT','OPTION']);
  const out = []; let heading = '';
  function txt(el) { return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim(); }
  function walk(n) {
    if (n.nodeType === 3) { const t = n.textContent.replace(/\s+/g, ' ').trim(); if (t) out.push(t + ' '); return; }
    if (n.nodeType !== 1 || skip.has(n.tagName)) return;
    const tag = n.tagName;
    if (/^H[1-6]$/.test(tag)) { heading = txt(n); out.push('\n' + heading + '\n'); return; }
    if (tag === 'TABLE') {
      const trs = [...n.querySelectorAll('tr')];
      const rows = trs.map(tr => [...tr.children].map(c => txt(c)));
      let hdr = null;
      const first = trs[0];
      if (rows.length > 1 && first && [...first.children].length > 1 && [...first.children].every(c => c.tagName === 'TH')) hdr = rows.shift();
      const cap = (n.caption && txt(n.caption)) || heading;
      for (let i = 0; i < rows.length; i++) {
        const r = rows[i];
        if (!r.filter(Boolean).length) continue;
        const tr = trs[hdr ? i + 1 : i];
        const rowHead = tr && tr.children[0] && tr.children[0].tagName === 'TH' && r.length === 2;
        let cells;
        if (rowHead) cells = [r[0] + ': ' + r[1]];                       // spec table: "Battery: 2000 mAh …"
        else cells = hdr ? r.map((c, k) => (hdr[k] && c ? hdr[k] + ': ' : '') + c) : r;
        out.push('\n' + (cap && !rowHead ? cap + ' — ' : '') + cells.filter(Boolean).join(' · ') + '\n');
      }
      return;
    }
    const block = /^(P|DIV|LI|BR|SECTION|ARTICLE|BLOCKQUOTE|PRE|DT|DD|OL|UL|LABEL|DETAILS|SUMMARY|TR|FIGCAPTION)$/.test(tag);
    if (block) out.push('\n');
    for (const c of n.childNodes) walk(c);
    if (block) out.push('\n');
  }
  walk(root);
  return out.join('').replace(/[ \t]+\n/g, '\n').replace(/\n{2,}/g, '\n').trim();
}
"""

STOP = {"the", "and", "for", "with", "this", "that", "your", "you", "are", "does", "can", "how", "what", "have", "has", "set", "from",
        "about", "one", "two", "per", "con", "per", "della", "del", "che", "una", "uno", "les", "des", "und", "der", "die", "das", "mit",
        "green", "nest", "store", "shop", "eco", "home", "product", "item", "buy", "order", "please", "hello", "hi", "thanks", "there"}
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Þ0-9€])|\s+[·|]\s+")
# the usual addresses of help pages, tried when the start page links to none of them
GUESS_PATHS = ["faq", "help", "shipping", "returns", "contact", "delivery", "shipping-policy", "refund-policy", "return-policy",
               "pages/faq", "pages/shipping", "pages/returns", "pages/contact", "pages/shipping-policy", "pages/refund-policy",
               "policies/shipping-policy", "policies/refund-policy", "spedizioni", "resi", "contatti", "aiuto", "domande-frequenti"]


def _same_site(a, b):
    pa, pb = urllib.parse.urlparse(a), urllib.parse.urlparse(b)
    if pa.scheme == "file" or pb.scheme == "file":
        return pa.scheme == pb.scheme and pa.path.rsplit("/", 1)[0] == pb.path.rsplit("/", 1)[0]
    host = lambda p: p.netloc.lower().split(":")[0].removeprefix("www.")
    return host(pa) == host(pb)


def candidate_lines(text):
    """Lines of a page, with FAQ questions glued to their answers and long paragraphs split into sentences."""
    lines = [l.strip(" •·-–#") for l in text.splitlines()]
    lines = [l for l in lines if l]
    out, i = [], 0
    while i < len(lines):
        l = lines[i]
        if l.endswith("?") and len(l) <= 140 and i + 1 < len(lines) and not lines[i + 1].endswith("?"):
            ans = lines[i + 1]
            for s in SENT_SPLIT.split(ans):
                s = s.strip()
                if s:
                    out.append(f"{l} {s}")
            i += 2
            continue
        parts = SENT_SPLIT.split(l) if len(l) > 260 else [l]
        out.extend(p.strip() for p in parts if p.strip())
        i += 1
    return out


def extract_facts(text, url):
    """Sentences of one page that state a customer-relevant fact → [{topics, text, url}]."""
    facts = []
    for line in candidate_lines(text):
        if not (15 <= len(line) <= 300) or JUNK.search(line):
            continue
        words = len(line.split())
        if words < 4 and not re.search(r"@|\d", line):
            continue
        topics = [name for name, a, b in TOPIC_RES if a.search(line) and b.search(line)]
        if not topics:
            continue
        facts.append({"topics": topics, "text": line, "url": url})
    return facts


DETAIL_JUNK = re.compile(r"^(add to (cart|bag|basket)|buy now|aggiungi|acquista|in den warenkorb|ajouter|quantity|quantità|share|condividi|"
                         r"related|you may also like|potrebbero piacerti|customer reviews|recensioni|free returns|reso gratuito|"
                         r"home|shop|cart|help|account|login|sign in|wishlist|write a review|description$|details$|dettagli$|specifications?$|"
                         r"specifiche|care$|cura$|©)", re.I)
AVAIL_RE = re.compile(r"(in stock|out of stock|sold out|only \d+ left|\d+ left|available|not available|disponibile|esaurito|non disponibile|"
                      r"solo \d+ rimast|pre-?order|back in stock|ships in|spedito in|auf lager|ausverkauft|en stock|épuisé|rupture|op voorraad|uitverkocht)", re.I)


def parse_product(text, url, title="", variants=None, shop_name=""):
    """One product page → {name, price, availability, variants, details[], url} or None when it is not a product page."""
    lines = [l.strip(" •·-–#") for l in text.splitlines()]
    lines = [l for l in lines if l and l != shop_name]
    if not lines:
        return None
    name = ""
    for l in lines[:12]:                                                # the first short heading-like line that is not the shop name
        if 4 <= len(l) <= 90 and not PRICE_RE.search(l) and not DETAIL_JUNK.search(l) and not AVAIL_RE.search(l) and not l.endswith(("?", ":")):
            if title and l.lower() in title.lower():
                name = l
                break
            if not name:
                name = l
    if title and (not name or name.lower() not in title.lower()):
        t = re.split(r"\s+[|–—-]\s+", title)[0].strip()
        if 4 <= len(t) <= 90 and not (shop_name and (t.lower() in shop_name.lower() or shop_name.lower() in t.lower())) \
                and not re.search(r"(shop|store|negozio|boutique|home$|welcome|benvenut)", t, re.I):
            name = t
    price = ""
    for l in lines[:40]:
        m = PRICE_RE.search(l)
        if m and not re.search(r"(free (over|above|from)|gratis (oltre|sopra|da)|shipping|spedizion|return|reso|discount|save|risparmi|was |instead of|invece di)", l, re.I):
            price = m.group(0).strip()
            break
    if not price:
        return None                                                     # a product page always shows a price
    avail = ""
    for l in lines[:60]:
        if AVAIL_RE.search(l) and len(l) <= 120:
            avail = l
            break
    details, seen = [], set()
    for l in lines:
        short_spec = 5 <= len(l) < 12 and re.search(r"\d", l) and re.search(r"[a-z]", l, re.I)      # "Weight 28 g", "2 years"
        if not (12 <= len(l) <= 260 or short_spec) or DETAIL_JUNK.search(l) or l == name or l == avail:
            continue
        if PRICE_RE.search(l) and len(l) < 40:
            continue
        if JUNK.search(l) or re.search(r"(free returns within|customer reviews)", l, re.I):
            continue
        key = re.sub(r"\W+", " ", l.lower()).strip()[:100]
        if key in seen:
            continue
        seen.add(key)
        details.append(l)
        if len(details) >= 18:
            break
    if not name:
        return None
    return {"name": name, "price": price, "availability": avail, "variants": [v for v in (variants or []) if v][:4], "details": details, "url": url,
            "text": " ".join(lines)[:3000]}


class ShopFacts:
    def __init__(self, tasks=None, log=None):
        self.tasks = tasks
        self.log = log or (lambda kind, **f: None)
        self.sheet = self._load()

    # ---- storage ----------------------------------------------------------
    def _load(self):
        try:
            return json.loads(SHEET.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self):
        SHEET.parent.mkdir(parents=True, exist_ok=True)
        SHEET.write_text(json.dumps(self.sheet, ensure_ascii=False, indent=1), encoding="utf-8")

    def forget(self):
        self.sheet = {}
        try:
            SHEET.unlink()
        except FileNotFoundError:
            pass

    @property
    def facts(self):
        return self.sheet.get("facts", [])

    @property
    def products(self):
        return self.sheet.get("products", [])

    @property
    def url(self):
        return self.sheet.get("url", "")

    # ---- products -----------------------------------------------------------
    @staticmethod
    def _words(text):
        return set(w for w in re.findall(r"[a-zà-ÿ0-9]{3,}", text.lower()) if w not in STOP)

    @staticmethod
    def _stems(words):
        return set(w[:-2] if w.endswith("es") and len(w) > 5 else (w[:-1] if w.endswith("s") and len(w) > 4 else w) for w in words)

    def match_products(self, message, limit=2):
        """Products the customer is talking about, best first: name words (and their singular forms) found in the message;
        a single shared word is enough when it points at only one product ('the lamp', 'the mug')."""
        if not self.products:
            return []
        mw = self._stems(self._words(message))
        scored = []
        for p in self.products:
            nw = self._stems(self._words(p["name"] + " " + " ".join(p["details"][:1])))
            hit = len(mw & nw)
            if hit:
                scored.append((hit, p))
        if not scored:
            return []
        scored.sort(key=lambda x: -x[0])
        best = scored[0][0]
        top = [p for h, p in scored if h == best]
        if best == 1 and len(top) > 1:                                   # one common word shared by several products → unsure
            return []
        if best == 1:                                                    # a single shared word must be the product itself, not a stray
            hit = next(iter(mw & self._stems(self._words(top[0]["name"] + " " + " ".join(top[0]["details"][:1])))), "")
            low = message.lower()
            if re.search(r"\b" + re.escape(hit) + r"\w*\s+(number|call|line|support|shop|store|order|delivery|shipping|page|website|site)\b", low) \
                    or re.search(r"\b(your|by|via|on the|over the)\s+" + re.escape(hit) + r"\w*\b", low):
                return []                                                # "phone number", "your phone", "by phone" — not the phone case
            if not re.search(r"\b(the|this|that|my|a|an|your|il|la|lo|le|questo|questa|der|die|das|le|la|un|une)\s+(\w+\s+){0,2}" + re.escape(hit) + r"\w*\b", low):
                return []                                                # a product is talked about as "the mug", "this lamp", "my case"
        return top[:limit] if best > 1 else top[:1]

    def product_block(self, message):
        """The product page(s) the message is about, as text for the reply writer ('' when none)."""
        hits = self.match_products(message)
        if not hits:
            return ""
        out = []
        for p in hits:
            lines = [f"PRODUCT: {p['name']} — price {p['price']}" + (f" — {p['availability']}" if p.get("availability") else "")]
            if p.get("variants"):
                lines += [f"options: {', '.join(v)}" for v in p["variants"]]
            lines += [f"- {d}" for d in p["details"][:14]]
            out.append("\n".join(lines))
        return ("\nTHE PRODUCT PAGE(S) ON THE SHOP'S WEBSITE (copy specifications, materials, sizes, options and figures exactly; "
                "if the page does not mention what the customer asks, say you will check with the owner — never guess):\n" + "\n".join(out))

    GENERIC = {"come", "comes", "coming", "work", "works", "working", "does", "with", "what", "which", "have", "much", "many", "long",
               "safe", "also", "really", "there", "please", "thanks", "thank", "hello", "would", "could", "should", "want", "need", "know",
               "tell", "about", "this", "that", "your", "from", "into", "still", "order", "ordered", "bought", "item", "product", "price",
               "cost", "costs", "when", "where", "will", "them", "they", "just", "like", "make", "made", "same", "good", "well", "size",
               "sizes", "colour", "colours", "color", "colors", "option", "options", "available", "possible", "exactly", "kind", "type",
               "last", "lasts", "hold", "holds", "take", "takes", "fits", "keep", "keeps", "look", "looks", "feel", "feels", "give",
               "gives", "using", "used", "sure", "might", "maybe", "anyone", "someone", "question", "asking", "wondering", "interested",
               "before", "after", "buying", "purchase", "purchasing", "actually", "real", "heavy", "light", "small", "large", "tall",
               "wide", "high", "short", "included", "include", "includes", "supplied", "delivered", "arrive", "arrives", "quality",
               "recommend", "suitable", "enough", "properly", "easily", "quickly", "normal", "regular", "standard", "different"}

    def unmentioned(self, message, product):
        """Content words of the question that the product page never mentions (a 'yes' about them would be invented)."""
        page = (product.get("text", "") + " " + product["name"] + " " + " ".join(product["details"]) +
                " " + " ".join(x for v in product.get("variants", []) for x in v)).lower()
        facts = " ".join(f["text"] for f in self.facts).lower()
        name_words = self._stems(self._words(product["name"]))
        out = []
        for w in re.findall(r"[a-zà-ÿ]{4,}", message.lower()):
            if w in STOP or w in self.GENERIC or w in name_words or w[:-1] in name_words:
                continue
            stem = w[:5]
            if stem in page or stem in facts:
                continue
            out.append(w)
        return list(dict.fromkeys(out))

    def contradiction(self, message, product):
        """A product-page line that negates something the question asks about ('no iPhone 15 Pro Max version',
        'no power adapter included') → that line, else ''."""
        qwords = [w for w in re.findall(r"[a-z0-9à-ÿ]{3,}", message.lower()) if w not in STOP and w not in self.GENERIC]
        for line in product["details"] + [product.get("text", "")]:
            for m in re.finditer(r"\b(no|not|without|non|senza|kein|keine|pas de|sans|niet|geen)\b([^.;()]{0,60})", line, re.I):
                span = m.group(2).lower()
                hits = [w for w in qwords if len(w) >= 3 and w in span]
                if len(hits) >= 2 or (hits and len(hits[0]) >= 6):
                    start = max(0, line.rfind(".", 0, m.start()) + 1)
                    seg = line[start:m.end()].strip(" ;,")
                    if seg.count("(") > seg.count(")"):
                        seg += ")"
                    return seg
        return ""

    def best_detail(self, message, product, limit=2):
        """The product-page line(s) that share most words with the question (for the safe template): up to `limit` lines,
        one per part of the question, joined for quoting. Word matching is by 5-letter prefix (weigh ~ weight)."""
        name_w = {w[:5] for w in self._words(product["name"])}
        qw = {w[:5] for w in self._words(message) if w not in self.GENERIC} - name_w        # the product's own name words say nothing
        if re.search(r"\b(price|cost|costs|how much (is|does it cost)|quanto costa|prezzo|preis|prix)\b", message.lower()):
            qw.add("price")
        cands = list(product["details"]) + ([f"{product['name']} price: {product['price']}"] if product.get("price") else [])
        for v in product.get("variants", []):
            cands.append("Options: " + ", ".join(v))
        if re.search(r"\b(colou?rs?|colori|farben|couleurs?|kleuren|options?|models?|sizes?|versions?|variants?|which .* (come|available))\b", message.lower()):
            qw.add("optio")
        if re.search(r"\b(weigh|weight|heavy|light|grams?|peso|pesa|gewicht|poids)\b", message.lower()):
            qw.add("weigh")
        scored = []
        for line in cands:
            lw = {w[:5] for w in self._words(line)}
            sc = len(qw & lw)
            if sc:
                scored.append((sc, line))
        scored.sort(key=lambda x: -x[0])
        picked, covered = [], set()
        for sc, line in scored:
            lw = {w[:5] for w in self._words(line)} & qw
            if lw - covered:                                              # adds a part of the question not yet answered
                picked.append(line)
                covered |= lw
            if len(picked) >= limit:
                break
        return '" and "'.join(picked)

    def product_numbers(self):
        out = set()
        for p in self.products:
            for t in [p["name"], p["price"], p.get("availability", "")] + p["details"] + [x for v in p.get("variants", []) for x in v]:
                out.update(re.findall(r"\d+(?:[.,]\d+)?", t))
        return out

    def stale(self):
        return bool(self.url) and time.time() - self.sheet.get("learned_at", 0) > REFRESH_DAYS * 86400

    # ---- learning --------------------------------------------------------
    def learn(self, url):
        """Read the shop's help pages and rebuild the fact sheet. Returns a plain-language report for the owner."""
        if not self.tasks:
            return "I have no browser hands here."
        if not re.match(r"^(https?|file)://", url):
            url = "https://" + url.strip().strip("/")
        t0 = time.time()
        try:
            pages, walls = self.tasks.on_hands(lambda: self._crawl(self.tasks.browser(), url), timeout=420)
            products = []
            try:
                products = self.tasks.on_hands(lambda: self._crawl_products(self.tasks.browser(), url), timeout=600)
            except Exception as e:
                self.log("shopfacts_products_failed", url=url, error=str(e)[:160])
        except Exception as e:
            self.log("shopfacts_failed", url=url, error=str(e)[:160])
            return f"I couldn't read {url}: {str(e)[:120]}"
        finally:
            try:
                self.tasks._release_page()
            except Exception:
                pass
        if not pages and not products:
            return (f"I opened {url} but could not read anything useful" + (f" ({walls[0]} wall)." if walls else " (empty page).") +
                    " If your shop has a help or FAQ page, give me its address directly: /shop <address>")
        facts, seen = [], set()
        for p in pages:
            for f in extract_facts(p["text"], p["url"]):
                key = re.sub(r"\W+", " ", f["text"].lower()).strip()[:120]
                if key in seen:
                    continue
                seen.add(key)
                facts.append(f)
        facts = facts[:MAX_FACTS]
        old = {f["text"] for f in self.facts}
        old_products = {p["name"] for p in self.products}
        self.sheet = {"url": url, "learned_at": time.time(), "facts": facts, "products": products[:MAX_PRODUCTS],
                      "pages": [{"url": p["url"], "title": p["title"], "chars": len(p["text"])} for p in pages]}
        self._save()
        self.log("shopfacts_learned", url=url, pages=len(pages), facts=len(facts), products=len(products), seconds=int(time.time() - t0))
        changed = len([f for f in facts if f["text"] not in old])
        by_topic = {}
        for f in facts:
            by_topic.setdefault(f["topics"][0], 0)
            by_topic[f["topics"][0]] += 1
        rep = [f"I read {len(pages)} page(s) of {urllib.parse.urlparse(url).netloc or url}: " + "; ".join((p["title"] or p["url"])[:40] for p in pages) + "."]
        if products:
            newp = len([p for p in products if p["name"] not in old_products])
            rep.append(f"{len(products)} product page(s) read: " + "; ".join(f"{p['name'][:40]} ({p['price']})" for p in products[:6]) +
                       ("…" if len(products) > 6 else "") + (f" — {newp} new." if old_products else ".") +
                       " Product questions (material, size, battery, compatibility, stock) will be answered from these pages.")
        if facts:
            rep.append(f"{len(facts)} facts kept (" + ", ".join(f"{k}: {v}" for k, v in by_topic.items()) + ")" +
                       (f" — {changed} new or changed since last time." if old else ".") + " Customer replies will use these exact words. A few examples:")
            rep += [f"• {f['text'][:160]}" for f in facts[:5]]
            rep.append("See them all: /shop")
        else:
            rep.append("No sentences about delivery, returns, contact or payment on those pages. If the shop keeps them elsewhere, give me that page: /shop <address>")
        if walls:
            rep.append(f"({len(walls)} page(s) showed a bot-check or login wall — I never try to pass those.)")
        return "\n".join(rep)

    def _crawl(self, b, url):
        """On the hands thread: open the start page, follow the help-like links, return [(url, title, text)], walls.
        Product links seen on the way (listing pages, product-looking addresses) are remembered for _crawl_products."""
        pages, walls, todo, done = [], [], [(0, url)], set()
        self._product_links, self._listing_links, self._shop_name = [], [], ""
        guessed = False
        while (todo or not guessed) and len(pages) < MAX_PAGES:
            if not todo:                                                  # no help links found → try the usual addresses
                guessed = True
                base = url if url.endswith("/") else url.rsplit("/", 1)[0] + "/"
                ext = ".html" if re.search(r"\.html?$", url) else ""
                cands = [base + g.rsplit("/", 1)[-1] + ext for g in GUESS_PATHS] if ext else [base + g for g in GUESS_PATHS]
                todo = [(9, c) for c in cands[:12] if c not in done]
                if not todo:
                    break
            todo.sort(key=lambda x: x[0])
            _, u = todo.pop(0)
            if u in done:
                continue
            done.add(u)
            try:
                b.open(u)
            except Exception as e:
                self.log("shopfacts_open_failed", url=u, error=str(e)[:100])
                continue
            if guessed:                                                   # a guessed address: skip "not found" pages quietly
                try:
                    t = (b.page.title() or "").lower()
                    if re.search(r"not found|404|non trovat|nicht gefunden|introuvable|page doesn't exist", t):
                        continue
                except Exception:
                    continue
            try:
                b.dismiss_banner()
            except Exception:
                pass
            st = b.status()
            if st != "ok":
                walls.append(st)
                continue
            try:
                text = b.page.evaluate(_JS_FACT_TEXT) or ""
            except Exception:
                text = ""
            title = ""
            try:
                title = b.page.title()[:80]
            except Exception:
                pass
            final = b.page.url
            if final in done and final != u and any(p["url"] == final for p in pages):
                continue
            done.add(final)
            if len(text) > 40:
                pages.append({"url": final, "title": title, "text": text[:15000]})
                if len(pages) == 1:                                        # the start page's first line is usually the shop's name
                    first = next((l.strip(" •·-–#") for l in text.splitlines() if l.strip(" •·-–#")), "")
                    if 2 <= len(first) <= 60:
                        self._shop_name = first
            if len(pages) >= MAX_PAGES:
                break
            # follow help-like links from the first two pages (start page + first help page) and from any guessed page
            if len(pages) <= 2 or guessed:
                try:
                    links = b.links(limit=400)
                except Exception:
                    links = []
                for l in links:
                    href = (l.get("href") or "").split("#")[0].strip()
                    if not href or href in done or SKIP_LINK.search(href) or not _same_site(href, url):
                        continue
                    label = (l.get("text") or "")[:80]
                    if PRODUCT_URL.search(href) and href not in self._product_links:
                        self._product_links.append(href)
                    elif (LISTING_WORDS.search(label) or LISTING_WORDS.search(href)) and href not in self._listing_links and href != url:
                        self._listing_links.append(href)
                    for rank, (_, rx) in enumerate(PAGE_WORDS):
                        if re.search(rx, label, re.I) or re.search(rx, urllib.parse.unquote(href.rsplit("/", 1)[-1] or href), re.I):
                            todo.append((rank, href))
                            break
        return pages, walls

    def _crawl_products(self, b, url):
        """On the hands thread, after _crawl: open the listing pages, then each product page; return product dicts."""
        products, seen_urls = [], set()
        listing = list(dict.fromkeys(self._listing_links))[:3]
        cand = list(dict.fromkeys(self._product_links))
        for lu in listing:
            try:
                b.open(lu)
                b.dismiss_banner()
                if b.status() != "ok":
                    continue
                for l in b.links(limit=600):
                    href = (l.get("href") or "").split("#")[0].strip()
                    label = (l.get("text") or "").strip()
                    if not href or href in cand or SKIP_LINK.search(href) or not _same_site(href, url) or href == lu:
                        continue
                    if PRODUCT_URL.search(href) or (PRICE_RE.search(label) and len(label) > 8):
                        cand.append(href)
                    elif len(label) >= 8 and not l.get("nav") and re.search(r"[a-z]", label, re.I) and not LISTING_WORDS.search(label) \
                            and not re.search(r"(home|help|faq|contact|cart|account|login|about|blog|shipping|returns|continue shopping)", label, re.I):
                        cand.append(href)
            except Exception as e:
                self.log("shopfacts_listing_failed", url=lu, error=str(e)[:100])
        if not cand and not listing:                                      # single-page shop: the start page may itself be a product
            cand = [url]
        for pu in cand[:MAX_PRODUCT_PAGES]:
            if pu in seen_urls:
                continue
            seen_urls.add(pu)
            try:
                b.open(pu)
                b.dismiss_banner()
                if b.status() != "ok":
                    continue
                text = b.page.evaluate(_JS_FACT_TEXT) or ""
                variants = b.page.evaluate("""() => [...document.querySelectorAll('select')].map(s => [...s.options].map(o => o.textContent.trim()).filter(Boolean)).filter(a => a.length > 1 && a.length < 40)""")
                title = b.page.title()[:100]
                prod = parse_product(text, b.page.url, title, variants, shop_name=self._shop_name)
                if prod:
                    products.append(prod)
            except Exception as e:
                self.log("shopfacts_product_failed", url=pu, error=str(e)[:100])
            if len(products) >= MAX_PRODUCTS:
                break
        return products

    # ---- use ----------------------------------------------------------------
    def relevant(self, message, limit=8):
        """The facts that help answer one customer message (by topic, then by shared words)."""
        if not self.facts:
            return []
        low = message.lower()
        want = set()
        for rx, topics in ASK_TOPICS:
            if re.search(rx, low):
                want.update(topics)
        words = set(w for w in re.findall(r"[a-zà-ÿ]{4,}", low))
        scored = []
        for f in self.facts:
            s = 3 if want & set(f["topics"]) else 0
            s += len(words & set(re.findall(r"[a-zà-ÿ]{4,}", f["text"].lower())))
            if s:
                scored.append((s, f))
        scored.sort(key=lambda x: -x[0])
        return [f for _, f in scored[:limit]]

    def prompt_block(self, message):
        rel = self.relevant(message)
        if not rel:
            return ""
        when = time.strftime("%Y-%m-%d", time.localtime(self.sheet.get("learned_at", 0)))
        return (f"\nFACTS FROM THE SHOP'S OWN WEBSITE (read on {when}; copy figures and conditions exactly, never add anything they do not say; "
                f"if they say something is not offered, say so plainly and do not invent an alternative):\n" +
                "\n".join(f"- {f['text']}" for f in rel))

    def numbers(self):
        """Every figure that stands on the shop's pages — allowed in replies."""
        out = set()
        for f in self.facts:
            out.update(re.findall(r"\d+(?:[.,]\d+)?", f["text"]))
        return out | self.product_numbers()

    def covers(self, topic):
        return any(topic in f["topics"] for f in self.facts)

    def best_sentence(self, message):
        rel = self.relevant(message, limit=1)
        if not rel:
            return ""
        return re.sub(r"^[^?]{0,140}\?\s*", "", rel[0]["text"])          # drop a glued FAQ question ("What is your return policy? ")

    def describe(self):
        if not self.url:
            return "shop pages: not read yet (/shop <address>)"
        age = int((time.time() - self.sheet.get("learned_at", 0)) / 86400)
        return (f"shop pages: {len(self.facts)} facts, {len(self.products)} products from {urllib.parse.urlparse(self.url).netloc or self.url} "
                f"({'today' if age == 0 else f'{age} d ago'})")

    def sheet_text(self):
        if not self.url:
            return ("I haven't read your shop's pages yet. Tell me its address — /shop www.yourshop.com — and I'll read the help, "
                    "shipping, returns and contact pages and use their exact words when I answer customers.")
        by = {}
        for f in self.facts:
            by.setdefault(f["topics"][0], []).append(f["text"])
        out = [self.describe() + f" · pages: " + ", ".join((p['title'] or p['url'])[:30] for p in self.sheet.get("pages", []))]
        for k, v in by.items():
            out.append(f"\n{k.upper()}")
            out += [f"• {t[:200]}" for t in v]
        if self.products:
            out.append("\nPRODUCTS")
            out += [f"• {p['name'][:60]} — {p['price']}" + (f" — {p['availability'][:40]}" if p.get("availability") else "") + f" ({len(p['details'])} details)" for p in self.products]
        out.append("\nRefresh: /shop <address> · forget: /shop forget")
        return "\n".join(out)
