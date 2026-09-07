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
      const rows = [...n.querySelectorAll('tr')].map(tr => [...tr.children].map(c => txt(c)));
      let hdr = null;
      if (rows.length > 1 && n.querySelector('th')) hdr = rows.shift();
      const cap = (n.caption && txt(n.caption)) || heading;
      for (const r of rows) {
        if (!r.filter(Boolean).length) continue;
        const cells = hdr ? r.map((c, i) => (hdr[i] && c ? hdr[i] + ': ' : '') + c) : r;
        out.push('\n' + (cap ? cap + ' — ' : '') + cells.filter(Boolean).join(' · ') + '\n');
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
    def url(self):
        return self.sheet.get("url", "")

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
        except Exception as e:
            self.log("shopfacts_failed", url=url, error=str(e)[:160])
            return f"I couldn't read {url}: {str(e)[:120]}"
        finally:
            try:
                self.tasks._release_page()
            except Exception:
                pass
        if not pages:
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
        self.sheet = {"url": url, "learned_at": time.time(), "facts": facts,
                      "pages": [{"url": p["url"], "title": p["title"], "chars": len(p["text"])} for p in pages]}
        self._save()
        self.log("shopfacts_learned", url=url, pages=len(pages), facts=len(facts), seconds=int(time.time() - t0))
        changed = len([f for f in facts if f["text"] not in old])
        by_topic = {}
        for f in facts:
            by_topic.setdefault(f["topics"][0], 0)
            by_topic[f["topics"][0]] += 1
        rep = [f"I read {len(pages)} page(s) of {urllib.parse.urlparse(url).netloc or url}: " + "; ".join((p["title"] or p["url"])[:40] for p in pages) + "."]
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
        """On the hands thread: open the start page, follow the help-like links, return [(url, title, text)], walls."""
        pages, walls, todo, done = [], [], [(0, url)], set()
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
                    for rank, (_, rx) in enumerate(PAGE_WORDS):
                        if re.search(rx, label, re.I) or re.search(rx, urllib.parse.unquote(href.rsplit("/", 1)[-1] or href), re.I):
                            todo.append((rank, href))
                            break
        return pages, walls

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
        return out

    def covers(self, topic):
        return any(topic in f["topics"] for f in self.facts)

    def best_sentence(self, message):
        rel = self.relevant(message, limit=1)
        return rel[0]["text"] if rel else ""

    def describe(self):
        if not self.url:
            return "shop pages: not read yet (/shop <address>)"
        age = int((time.time() - self.sheet.get("learned_at", 0)) / 86400)
        return f"shop pages: {len(self.facts)} facts from {urllib.parse.urlparse(self.url).netloc or self.url} ({'today' if age == 0 else f'{age} d ago'})"

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
        out.append("\nRefresh: /shop <address> · forget: /shop forget")
        return "\n".join(out)
