"""Situations a shop owner runs into, answered like an experienced shopkeeper would — from rules of thumb plus the
practice store's own numbers. No model, no browsing: the owner gets the plan in one message and can act at once.

    Advice(store, inbox, memory).reply("the courier lost a parcel, what do I do?")  → text or None
"""
import datetime as _dt
import re


def _eur(x):
    return f"€ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _num(s):
    return float(str(s).replace(",", "."))


class Advice:
    def __init__(self, store=None, inbox=None, memory=None):
        self.store = store
        self.inbox = inbox
        self.memory = memory

    # each entry: (regex, method name). First match wins; a method may return None to fall through.
    RULES = [
        (r"\b(courier|carrier|gls|brt|poste|dhl|ups|corriere)\b.{0,30}?\b(lost|lose|smarrito|perso|missing|damaged (?:the|a|my)|broke)\b|\b(lost|smarrito) (?:a |the |il |un )?(?:parcel|package|pacco)\b", "lost_parcel"),
        (r"\btracking (?:says|shows|dice) (?:delivered|consegnato)\b|\bnever (?:got|received) (?:the |their |his |her )?(?:parcel|package|order)\b.{0,40}?\bdelivered\b|\bdelivered but (?:not|never) (?:received|arrived|got)\b|\bsays delivered\b", "says_delivered"),
        (r"\b(?:wants?|asks? for|needs?|chiede|vuole) (?:an? |la |una )?(?:invoice|receipt|fattura|ricevuta)\b|\binvoice\b.{0,20}?\b(?:how|do i|must|devo)\b", "invoice"),
        (r"\bhow (?:do|should) i (?:handle|process|do|manage) (?:a |the |i )?(?:returns?|resi|reso)\b|\breturn process\b|\bcome gestisco (?:un |i )?res[oi]\b", "handle_return"),
        (r"\b(?:wants?|would like|asks? (?:for|about)|ordered|is asking for|vuole|chiede)\b.{0,20}?\b(?P<n>\d{2,5})\s+(?:pcs|pieces|units|pezzi|x\s+)?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\b.{0,40}?\b(?:company|business|office|shop|store|resell|wholesale|bulk|azienda|ufficio|rivendere|ingrosso)\b|\b(?:wholesale|b2b|bulk order|ordine all'ingrosso)\b.{0,30}?\b(?:request|asked|inquiry|enquiry|richiesta|how|what)\b", "wholesale"),
        (r"\b(?:influencer|creator|blogger|youtuber|tiktoker|instagrammer)\b.{0,60}?\b(?:free|gift|gifted|omaggio|gratis|in exchange|in cambio|collab|collaboration|sponsor)\b|\b(?:free|gifted) (?:product|lamp|mug|item)\b.{0,30}?\b(?:for|in exchange for) (?:a )?(?:post|review|story|video)\b", "influencer"),
        (r"\bchargebacks?\b|\bdispute[sd]? (?:the |a )?(?:payment|charge|transaction)\b|\bcontestazione (?:della )?(?:carta|pagamento)\b|\bstorno\b", "chargeback"),
        (r"\b(?:should i|do i (?:want|need)|worth|conviene|dovrei) (?:open|start|try|use|sell on|aprire|vendere su)\b.{0,15}?\btiktok shop\b|\btiktok shop\b.{0,20}?\b(?:worth it|good idea|yes or no|conviene|\?)", "tiktok_shop"),
        (r"\b(?:do i need|should i (?:get|have|buy)|is .{0,20}? (?:needed|required|mandatory)|serve|devo (?:fare|avere))\b.{0,20}?\b(?:insurance|assicurazione)\b|\binsurance\b.{0,20}?\b(?:need|needed|necessary|required|worth)\b", "insurance"),
        (r"\bhow (?:do|should|can) i (?:pack|package|wrap|ship|protect|imballo|impacchetto)\s+(?:the |our |my |a |an |i |le |il |la )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\s+(?:so|that|to|without|senza|in modo|properly|safely|for shipping)\b|\bpackaging (?:for|of) (?:the |our |my )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\b|\bcome imballo\b", "packaging"),
        (r"\b(?:name|nome|title|call)\b.{0,20}?\b(?:for|per|of|di)\b.{0,15}?\bnewsletter\b|\bnewsletter (?:name|title|nome)\b", "newsletter_name"),
        (r"\b(?:write|draft|make|prepare|send|scrivi|prepara|manda)\b.{0,20}?\b(?:the |a |our |my |la |una )?(?:newsletter|e-?mail (?:campaign|blast)|email to (?:our |the )?customers)\b", "newsletter_write"),
        (r"\b(?:what|which|best|good|ideal|migliore|quale|a che) (?:time|hour|ora|orario)s?\b.{0,20}?\b(?:post|publish|pubblicare|postare)\b|\bwhen (?:should|do) i post\b|\bquando (?:posto|pubblico)\b", "post_time"),
        (r"\bhow (?:often|many times|frequently|much) (?:should|do|must) (?:i|we) post\b|\bposting (?:frequency|schedule|cadence)\b|\bquante volte (?:devo )?(?:postare|pubblicare)\b|\bogni quanto (?:posto|pubblico)\b", "post_often"),
        (r"\b(?:our|my|the|what(?:'s| is) (?:our|my|the)) (?:return|refund|cancellation) rate\b|\bhow many returns\b|\btasso di res[oi]\b|\bquanti resi\b", "return_rate"),
        (r"\b(?:which|what) countr(?:y|ies) (?:buys?|orders?|is|are) (?:the )?(?:most|best|top)\b|\bwhere (?:do|are) (?:our |the |my )?(?:customers|buyers|orders) (?:from|coming from|come from)\b|\b(?:sales|orders) by country\b|\bda che paes[ei] (?:comprano|arrivano)\b|\bquale paese compra di più\b", "by_country"),
        (r"\b(?:which|what) (?:day|weekday|day of the week|giorno)\b.{0,20}?\b(?:sells?|sold|best|most|più)\b|\bbest (?:day|weekday) for sales\b|\bsales by (?:day|weekday)\b", "by_day"),
        (r"\b(?:out[- ]of[- ]office|auto[- ]?repl(?:y|ier)|automatic repl(?:y|ies)|autoresponder|vacation responder|risposta automatica|away message)\b", "auto_reply"),
        (r"\b(?:first|primi) (?:\d+ |hundred |thousand |mille |cento )?(?:followers|follower|seguaci)\b|\b(?:get|grow|gain|more|find|win|avere|ottenere) (?:more )?(?:followers|follower|seguaci)\b|\bgrow (?:my |our |the )?(?:instagram|tiktok|account|page)\b", "first_followers"),
        (r"\b(?:should (?:i|we)|worth|conviene|do (?:i|we) (?:also )?(?:need|want) to|what about|thinking (?:of|about)|is it worth)\b.{0,20}?\b(?:sell(?:ing)?|list(?:ing)?|open(?:ing)?|be|go|vendere|aprire)\b.{0,8}?\b(?:on|su|a)\s+(?P<mp>etsy|amazon|ebay|vinted|subito|zalando|manomano|temu|facebook marketplace|instagram shop|wallapop)\b|\b(?P<mp2>etsy|amazon|ebay|vinted|subito|zalando|manomano)\b.{0,15}?\b(?:too|as well|anche|worth it|good idea|yes or no)\b", "marketplace"),
        (r"\b(?:should (?:i|we)|worth|conviene|do (?:i|we))\b.{0,20}?\b(?:offer|add|do|give|propose|offrire|fare)\b.{0,10}?\bgift[- ]?wrap(?:ping)?\b|\bgift[- ]?wrapping\b.{0,20}?\b(?:yes or no|worth|good idea|\?)|\bconfezione regalo\b", "gift_wrap"),
        (r"\b(?:refund or replace|replace or refund|replacement or (?:a )?refund|refund or (?:a )?replacement|rimborso o sostituzione|sostituzione o rimborso|resend or refund|refund or resend)\b|\bshould (?:i|we) (?:refund|replace|resend)\b.{0,30}?\b(?:chipped|broken|damaged|cracked|faulty|defective|stopped working|doesn't work|arrived broken|rotto|difettoso)\b|\b(?:chipped|broken|damaged|cracked|faulty|defective|stopped working|doesn't work|rotto|difettoso)\b.{0,40}?\bshould (?:i|we) (?:refund|replace|resend)\b", "refund_or_replace"),
        (r"(?<!does )(?<!do )(?<!is )\b(?:amazon|temu|aliexpress|shein|ebay|a competitor|competitors?|another shop|someone else|ikea|la concorrenza|un concorrente)\b.{0,30}?\b(?:sells?|has|offers?|lists?|vende|ha)\b.{0,40}?\b(?:cheaper|less|lower|for half|a metà|meno|più economico|(?:for|at|a) (?:€|eur|euro)?\s*\d+(?:[.,]\d+)?\s*(?:€|eur|euros?)?)\b|\b(?:cheaper|lower price|less)\b.{0,20}?\bon (?:amazon|temu|aliexpress|ebay)\b|\bundercut(?:ting)?\b", "cheaper_elsewhere"),
        (r"\b(?:asks?|asking|wants?|would like|chiede|vuole)\b.{0,15}?\b(?:a |un )?(?:discount|promo|coupon|voucher|first[- ]order)\s*(?:code|codice)?\b|\bcodice sconto\b|\bdo we have (?:any )?(?:discount|promo|coupon) codes?\b|\bshould (?:i|we) (?:make|create|offer|set up|have) (?:a |any )?(?:discount|promo|coupon|welcome) codes?\b", "discount_code"),
        (r"\b(?:what (?:do|should) i (?:write|put|include|print) (?:on|in|inside|with) the (?:package|parcel|box|packing slip|shipment|pacco))|packing slip\b|\bwhat goes in(?:to|side)? the (?:box|parcel|package)\b|\bcosa (?:metto|scrivo) (?:nel|sul) pacco\b|\b(?:thank[- ]you|thank you) (?:card|note)\b.{0,20}?\b(?:in|with) the (?:parcel|package|box|order)\b", "packing_slip"),
        (r"\b(?:ordered|wants?|bought|asks? for|ha ordinato|vuole)\s+(?P<n>\d{1,3})\s+(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\b.{0,40}?\b(?:only have|we have|have only|left|in stock|ne (?:abbiamo|restano))\b.{0,20}?\b(?:keep|hold|hold back|save|reserve|tenere|tengo|trattenere)\b|\b(?:keep|hold) (?:one|1|some|a few) back\b|\blast (?:one|piece|unit)\b.{0,40}?\b(?:sell|ship|keep|hold)\b", "stock_hold"),
        (r"\b(?:what do you think|your (?:opinion|take|view|honest opinion)|how (?:do you|would you) (?:rate|judge)|che ne pensi|come (?:ti sembra|lo vedi|va secondo te))\b.{0,20}?\b(?:the |our |my |il |del |lo )?(?:shop|store|business|negozio|numbers|results|so far|finora)\b|\bhonest (?:review|opinion) of the (?:shop|store)\b", "shop_opinion"),
        (r"\b(?:thinking (?:of|about)|considering|planning to|should i|would it be (?:smart|good|a good idea) to|what about|conviene|pensavo di|vorrei)\b.{0,15}?\b(?:add|adding|sell|selling|stock|stocking|introduce|introducing|aggiungere|vendere)\b.{0,10}?\b(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\b.{0,30}?\b(?:good idea|worth it|smart|yes or no|\?|buona idea)", "add_product_idea"),
        (r"\bshould (?:i|we) (?:raise|increase|lower|drop|cut|reduce) (?:the |our |my )?prices?\b|\b(?:raise|increase|lower|cut) (?:the |our |my )?prices\??\W*$|\b(?:alzo|abbasso|aumento) i prezzi\b|\bare (?:our|my) prices (?:too )?(?:high|low|right|ok)\b", "raise_prices"),
        (r"\b(?:tell me a joke|make me laugh|raccontami una barzelletta|a joke)\b", "joke"),
        (r"^\W*(?:i'?m bored|i am bored|mi annoio|bored)\W*$", "bored"),
        (r"\b(?:what(?:'s| is) the weather|weather (?:like |forecast |in |for |at |tomorrow|today|next week)|will it rain|is it (?:going to )?rain|che tempo fa|previsioni (?:meteo|del tempo)|meteo)\b", "weather"),
        (r"\bhow (?:do|should|can) i (?:answer|reply to|respond to|handle) (?:a |the )?(?:review|recensione)\b.{0,30}?\b(?:positive|good|5[- ]star|nice|bella|positiva)\b|\b(?:positive|good|5[- ]star) review\b.{0,30}?\b(?:answer|reply|respond|thank|rispondo)\b", "good_review"),
        (r"\b(?:customer|client|buyer|someone|cliente)\b.{0,30}?\b(?:asks?|asking|wants? to know|chiede)\b.{0,20}?\b(?:where (?:it|the product|they|these|the [a-z]+) (?:is|are) made|made in|origin|provenienza|dove (?:è|sono) fatt[oi])\b|\bwhere (?:is|are) (?:it|they|the [a-z]+) made\b.{0,30}?\b(?:say|answer|tell|rispondo)\b", "made_where"),
        (r"\b(?:gdpr|privacy)\b.{0,40}?\b(?:need|must|do i|what|how|serve|devo)\b|\bcookie (?:banner|consent|policy)\b.{0,20}?\b(?:need|required|do i|serve)\b|\bdo i need (?:a )?(?:privacy policy|cookie banner|terms)\b", "gdpr"),
        (r"\b(?:someone|a company|a shop|another (?:shop|store|seller)|un altro negozio)\b.{0,30}?\b(?:copied|copying|stole|stealing|is using|uses|ha copiato|usa)\b.{0,20}?\b(?:my|our|the) (?:photos?|pictures?|images?|description|text|name|logo|foto|descrizione|nome)\b|\b(?:copied|stole) (?:my|our) (?:photos?|listing|description|brand)\b", "copied"),
        (r"\b(?:price|prezzo)\b.{0,20}?\b(?:mistake|error|wrong|typo|errore|sbagliato)\b.{0,40}?\b(?:order|ordered|bought|sold|ordine|comprato)\b|\b(?:ordered|bought|sold)\b.{0,30}?\b(?:wrong|mistaken) price\b|\blisted (?:it |the [a-z ]{2,20}? )?at the wrong price\b|\bwrong price\b.{0,30}?\b(?:ordered|bought|order)\b", "price_mistake"),
        (r"\b(?:out of|no) (?:boxes|packaging|tape|cartons|scatole)\b|\bwhere (?:do|can) i (?:buy|get|find) (?:cheap )?(?:boxes|packaging|shipping boxes|mailers|bubble wrap|scatole|imballaggi)\b", "buy_boxes"),
        (r"\b(?:how (?:do|should) i|what(?:'s| is) the best way to) (?:take|shoot|make|do) (?:product )?(?:photos?|pictures?|foto)\b|\bproduct photo(?:s|graphy)? (?:tips|setup|at home|with (?:a|my) phone)\b|\bcome faccio le foto\b", "photos"),
        (r"\b(?:vacation|holiday|holidays|ferie|vacanza|away for (?:a|two|\d+) weeks?|closing (?:the shop )?for)\b.{0,40}?\b(?:shop|store|orders|what do i do|how|negozio|ordini|come faccio)\b|\bwhat (?:do i do with|happens to) (?:the shop|orders) (?:when|while) i'?m (?:away|on holiday)\b", "vacation"),
    ]

    SITUATIONS = ("made_where", "lost_parcel", "says_delivered", "invoice", "wholesale", "influencer", "chargeback", "price_mistake", "copied",
                  "discount_code", "stock_hold", "cheaper_elsewhere", "refund_or_replace")

    JOB_WORDS = re.compile(r"https?://|\b(research|find|search|compare|look up|look into|write me a (?:doc|document|report)|document|report|cerca|trova|ricerca|confronta)\b", re.I)

    def reply(self, t, only=None):
        low = t.lower().strip()
        if self.JOB_WORDS.search(low):                                     # "research the best packaging…" is a job for the browser, not a rule of thumb
            return None
        for pat, name in self.RULES:
            if only is not None and name not in only:
                continue
            m = re.search(pat, low, re.I)
            if m:
                try:
                    r = getattr(self, name)(t, m)
                except Exception:
                    r = None
                if r:
                    return r
        return None

    # ---- helpers ------------------------------------------------------------------------------
    def _product(self, what):
        try:
            return self.store.find_product(what) if (self.store is not None and what) else None
        except Exception:
            return None

    def _paid(self):
        try:
            return [o for o in self.store.data["orders"] if o["status"] in ("paid", "shipped", "delivered")]
        except Exception:
            return []

    @staticmethod
    def _it(t):
        return bool(re.search(r"\b(come|cosa|devo|conviene|quale|quanti|dove|che|il|la|un|una|per|non|mi)\b", t.lower())) and not re.search(r"\b(the|what|how|should|do|is|are)\b", t.lower())

    # ---- incidents ----------------------------------------------------------------------------
    def lost_parcel(self, t, m):
        return ("Courier lost a parcel — the customer is your problem, the courier is your claim; keep the two apart:\n"
                "1. Today: tell the customer you're on it and give a date: “If it doesn't show a scan by <date, 3 working days>, I resend or refund — your choice.” Don't make them wait for the courier's investigation.\n"
                "2. Open the trace/claim with the courier now (GLS: from the tracking page or your account; Poste: online claim). Keep the proof of shipment and the label.\n"
                "3. Day 3–5 with no movement: resend (if in stock) or refund in full. The law is on the customer's side — the risk is yours until delivery.\n"
                "4. Claim the value from the courier: standard cover is small (GLS ~€ 8/kg, Poste up to € 50 unless insured), so for items over ~€ 50 add insurance (~€ 1–2) at shipping time.\n"
                "5. Write it down: tracking, dates, what you offered — a chargeback later is won with that paper trail.\n"
                "Forward me the customer's message and I draft the reply; say “refund order <n>” or “resend order <n>” when you decide.")

    def says_delivered(self, t, m):
        return ("“Tracking says delivered, customer says nothing arrived” — the classic; handle it warmly and by the book:\n"
                "1. Reply today, no suspicion in the tone: “Sorry about this — let's find it. Could you check with neighbours, the building's mailroom/portineria, and around the door? Couriers sometimes leave parcels in odd spots.” Ask them to wait 24 h — 30–40 % turn up.\n"
                "2. Meanwhile ask the courier for the proof of delivery (GPS point, photo, signature). GLS/Poste give it within a day or two.\n"
                "3. Still missing after 24–48 h: for an order under ~€ 50 just resend or refund — arguing costs more than the item. Over that, wait for the POD; if it shows a different address or no signature, the courier pays (claim); if it's clean and the customer insists, refund once and note the address.\n"
                "4. Repeat cases at the same address → require signature on delivery or ship to a pickup point next time.\n"
                "Legally (EU) the risk is yours until the goods are in the customer's hands, so plan on refunding in doubt — and insure parcels over € 50. Forward me the message and I draft the first reply.")

    def invoice(self, t, m):
        it = self._it(t)
        if it:
            return ("Fattura — sì, se il cliente la chiede devi emetterla (entro le 24:00 del giorno stesso se lo chiede al momento dell'ordine, altrimenti al più tardi entro 12 giorni). "
                    "Ti servono: nome/ragione sociale, indirizzo, codice fiscale o Partita IVA, e per le aziende il codice destinatario/PEC per la fattura elettronica (SdI).\n"
                    "In forfettario: fattura senza IVA con la dicitura “operazione in franchigia da IVA, regime forfettario art. 1 c. 54-89 L. 190/2014”, bollo da € 2 sopra € 77,47. "
                    "Ai privati basta la ricevuta/scontrino (corrispettivo) se non chiedono la fattura. Metti nella pagina di checkout la casella “voglio la fattura” con i campi: risparmia dieci e-mail.")
        return ("A customer wants an invoice — you must issue one when asked (in Italy: same day if asked at the time of the order, otherwise within 12 days). Ask for: full name / company name, address, "
                "codice fiscale or VAT number, and for companies the SDI recipient code or PEC (the invoice goes through the e-invoicing system).\n"
                "Forfettario: invoice without VAT and with the standard exemption wording; € 2 stamp duty above € 77,47. Consumers who don't ask only need the receipt.\n"
                "Fix for the future: an “I need an invoice” checkbox at checkout with those fields — it ends the back-and-forth. Reply to the customer: “Of course — send me <fields> and you'll have it within 24 h.”")

    def handle_return(self, t, m):
        rule = ""
        try:
            rule = self.store.data.get("pages", {}).get("returns", "")
        except Exception:
            pass
        return ("Handling a return, step by step (our page says: " + (rule.splitlines()[0][:120] if rule else "30 days, customer pays return postage unless faulty") + "):\n"
                "1. Reply within a day: confirm they can return it, give the address, say who pays the postage and when the refund comes. No forms, no interrogation — ask the reason in one friendly line (it's your product feedback).\n"
                "2. Ask them to send it tracked and to keep the receipt; for faulty items ask for a photo and skip the return if the item is cheap (postage costs more than the goods).\n"
                "3. When it arrives: check it the same day, refund within 5 days (law: 14) to the same payment method, and message them that it's done. Put the item back in stock only if it's really unused.\n"
                "4. Write down the reason. Three returns for the same reason = fix the product page (size, colour, expectation), not the customer.\n"
                "5. EU rules you can't go below: 14 days to withdraw for any reason, refund incl. the original standard shipping, within 14 days of getting the goods back. Faulty items: 2-year legal guarantee, you pay everything.\n"
                "Forward me the customer's message and I draft the reply from our returns page.")

    def wholesale(self, t, m):
        n = int(m.group("n")) if m.groupdict().get("n") else 100
        p = self._product(m.groupdict().get("what") or "")
        if p:
            cost, price = p.get("cost", 0), p["price"]
            disc = 0.30 if n >= 100 else 0.20 if n >= 50 else 0.10
            unit = round(price * (1 - disc), 2)
            profit = (unit - cost) * n
            stock_line = f"You have {p['stock']} in stock — the supplier must deliver the rest; quote a date only after they confirm." if p["stock"] < n else f"You have {p['stock']} in stock, so you can ship at once."
            return (f"{n} × {p['name']} for a company — yes, take it, it's a month of retail in one parcel. My numbers:\n"
                    f"• Wholesale price: {_eur(unit)} each (−{disc * 100:.0f} % from {_eur(price)}) — still {_eur(unit - cost)} over cost, {_eur(profit)} on the order. Never below 2× cost ({_eur(cost * 2)}).\n"
                    f"• Terms: 50 % deposit, balance before shipping (or full payment by bank transfer for a first order); invoice with their VAT number; delivery date from the supplier's date + 3 days. {stock_line}\n"
                    f"• One pallet/box, one address, no gift wrap; shipping at cost (ask the courier for a quote, ~€ 15–40 for a 20–30 kg box in Italy).\n"
                    f"• Ask what it's for (gifts? resale?) — resellers want 40–50 % off and exclusivity; say no to exclusivity for now.\n"
                    f"Reply: “Happy to — for {n} pieces the price is {_eur(unit)} each + shipping at cost, delivery by <date>, 50 % deposit. Shall I send the pro-forma invoice?” Say “write the quote” and I prepare it.")
        return (f"A {n}-piece order for a company — yes, but on your terms: −10 % from 25 pieces, −20 % from 50, −30 % from 100, never below 2× your cost; 50 % deposit and the balance before shipping "
                "(or full bank transfer for a first order); invoice with their VAT number; delivery date = supplier's date + 3 days, quoted only after the supplier confirms; shipping at cost. "
                "Ask what it's for: gifts are easy, resellers want 40–50 % and exclusivity (say no for now). Tell me the product and I do the exact quote.")

    def influencer(self, t, m):
        p = None
        for w in ("lamp", "mug", "case", "toothbrush", "wraps"):
            if w in t.lower():
                p = self._product(w)
                break
        cost_line = f" It costs you {_eur(p.get('cost', 0))} + € 5 postage, so it's a cheap test" if p else " Your cost is the product + postage, so it's a cheap test"
        return ("An influencer asking for a free product — check three things in 5 minutes before you say yes:\n"
                "1. Real audience: open their profile; comments vs likes (a 50k account with 3 comments per post is bought), do the comments look like real people, is the audience in your country? Say “check <profile link>” and I look.\n"
                "2. Fit: would their followers buy a € 15–40 home product? Home/food/lifestyle micro-accounts (3–30k) convert better than big generic ones.\n"
                "3. The deal, in writing (a DM is fine): 1 post + 1–3 stories with the link/tag, within 2 weeks of delivery, they keep the product, you may reuse the content (say “usage rights for our page”). No money on top for a gifted collab.\n"
                + cost_line + " — do 3–5 of these a month, keep the ones that bring orders (give each a discount code: LENA10 → you see the sales).\n"
                "Red flags: asks for money or several products, 'media kit' with round numbers, follower count much bigger than their views. Reply I'd send: “Happy to send you the <product> — one reel + a story with our tag within two weeks after it arrives, and we can reshare your content. Address?”")

    def chargeback(self, t, m):
        return ("A chargeback (the customer's bank pulled the money back) — you have ~7–10 days to answer, and evidence wins, not arguments:\n"
                "1. Read the reason code in your payment dashboard: 'item not received', 'not as described', 'fraud/unrecognised' — each needs different proof.\n"
                "2. Not received → tracking with delivery scan, address matching the order, proof of delivery from the courier. Not as described → product page text, photos, your messages with the customer, the returns offer you made. Fraud → IP/country, e-mail confirmations, any contact with the customer.\n"
                "3. Upload it all in one go before the deadline; write two plain paragraphs, no emotion. Banks side with clear paper trails ~40–60 % of the time.\n"
                "4. Message the customer too: many chargebacks are people who didn't recognise the charge — if they withdraw it, you win for sure.\n"
                "5. If you lose: you lose the money + a € 15–20 fee; don't fight it further under € 50. Then fix the cause: clear shop name on the card statement, tracking e-mails, answer messages within a day (most chargebacks start with an unanswered e-mail).\n"
                "Keep a folder per order (tracking, messages) — say “cancel/refund order <n>” early when a customer is unhappy: a refund costs you less than a chargeback.")

    def tiktok_shop(self, t, m):
        return ("TikTok Shop — my take for a small shop in Italy: not yet as the main channel, yes as a test once you have content that works.\n"
                "For: huge reach for € 0, buyers impulse-buy inside the app, the algorithm doesn't care how many followers you have. Against: fees ~5–9 % + payment, strict shipping windows (ship in 1–3 days or you get penalised), returns are generous to buyers, "
                "you don't own the customer (no e-mail), and it rewards daily video + lives — that's a job.\n"
                "Do it in this order: (1) post 20–30 organic videos on your normal TikTok first; (2) if some pass 10k views and people ask 'where do I buy', open the Shop with your 2 best-margin products; (3) keep your own store as home base and put the link everywhere.\n"
                "Price the same as your store (they check). Need: Partita IVA, a bank account, EU address, product photos, stock for 30+ orders. Say “tiktok ideas for <product>” and we start with the content — that's the real gate.")

    def insurance(self, t, m):
        return ("Insurance for a small online shop — what actually matters, in order:\n"
                "1. Parcel insurance: only for items over ~€ 50–70 (standard courier cover is € 8/kg–€ 50); costs € 1–2 per parcel, buy it per shipment at label time. Cheap items: self-insure (budget 1 % of sales for losses).\n"
                "2. Product liability (RC prodotti): when you sell things that can hurt (electrical like the lamp, cosmetics, food contact, kids' items) — € 150–400/year for a micro shop; often bundled with the general RC. Ask your insurer for “RC prodotti e-commerce”.\n"
                "3. General liability (RC generale) if you have a physical space, markets, or staff.\n"
                "4. Stock: worth insuring when the stock in your home/garage is over ~€ 3–5k (fire, theft, water) — check whether the home policy excludes business goods (most do).\n"
                "Not needed now: cyber policies, credit insurance, 'shop closure' cover. Also not insurance but as important: a CE/compliance check for electrical products and the supplier's liability clause in writing.\n"
                "Cheapest way: one call to an insurer with the list above and your sales (say “€ 10k/year, home stock € 2k, lamps and kitchen goods”).")

    def packaging(self, t, m):
        what = (m.groupdict().get("what") or m.groupdict().get("what2") or "").strip()
        p = self._product(what)
        name = p["name"] if p else (what or "fragile items")
        fragile = bool(p and re.search(r"\b(mug|lamp|glass|ceramic|stoneware|candle|jar)\b", p["name"].lower())) or bool(re.search(r"\b(mug|glass|ceramic|candle|jar|plate|vase)\b", what))
        w = (p or {}).get("weight_g", 300)
        lines = [f"Packing {name} so it arrives whole — the rule is: nothing moves, nothing touches the box wall, the box survives a 1 m drop:"]
        if fragile:
            lines += ["1. Wrap the item in 2 layers of bubble wrap (bubbles inward), handle/spout wrapped separately; tape it closed.",
                      "2. Inner box or a snug sleeve, then the outer box with ≥ 5 cm of cushioning on every side (paper fill, air pillows, or shredded card — not loose foam chips).",
                      "3. Double-wall cardboard box, right size (item + 10 cm each way); fill until nothing rattles when you shake it; H-tape the seams.",
                      "4. 'Fragile' stickers help a little; the packing does the work. Drop-test one parcel from table height before you ship the first batch."]
        else:
            lines += ["1. Item in a bag or tissue (dust, rain on the doorstep), then a padded mailer or a box with 2–3 cm of paper fill so it doesn't slide.",
                      "2. Right size: shipping price is by volume too (L×W×H/5000), so the smallest box that fits with padding.",
                      "3. Tape all seams; label flat on the largest face; a return address inside the box too."]
        lines.append(f"Weight: ~{w} g item + ~{120 if not fragile else 250} g packing → shipping band {'≤ 1 kg' if w + 250 <= 1000 else '1–2 kg'}. Costs: ~€ 0,60–1,20 per parcel for box + wrap when you buy 25–50 at a time (see “where do I buy boxes”).")
        lines.append("One breakage per 100 parcels is normal; more than that = change the packing, not the courier. Put a thank-you card inside — say “write a thank-you note”.")
        return "\n".join(lines)

    def newsletter_name(self, t, m):
        name = "Green Nest"
        try:
            name = self.store.data.get("name", name).split(" —")[0]
        except Exception:
            pass
        return (f"Newsletter names for {name} — short, says what people get, no 'newsletter' in it:\n"
                f"1. “The Nest Notes” — monthly, 3 things: one product story, one tip, one offer.\n2. “Small Changes” — fits eco home goods: one swap a month.\n3. “From Bergamo, with care” — the personal one, signed by you.\n"
                f"4. “The Slow Sunday” — if you send on Sundays; people remember the day.\n5. “Behind the Parcel” — what happened in the shop this month.\n"
                "Rule: pick the one you'd be happy to say out loud to a customer. Send at most twice a month, always with one useful thing and one clear link. Say “write the newsletter” and I draft the first one from the shop's facts.")

    def newsletter_write(self, t, m):
        st = self.store
        name = "the shop"
        prods = []
        try:
            name = st.data.get("name", name).split(" —")[0]
            prods = [p for p in st.products() if p["stock"] > 0][:2]
        except Exception:
            pass
        p1 = prods[0] if prods else None
        p2 = prods[1] if len(prods) > 1 else None
        month = _dt.date.today().strftime("%B")
        body = (f"Subject: {month} at {name}: one thing worth knowing\n\n"
                f"Hi <first name>,\n\n"
                f"Short one this month. {('We finally have ' + p1['name'].split(' (')[0] + ' back — ' + (p1.get('short') or '').rstrip('.') + '.') if p1 else 'Here is what changed in the shop.'}\n\n"
                f"One tip: <one honest, useful tip about using the product — 2 lines, no selling>.\n\n"
                f"{('Also new: ' + p2['name'].split(' (')[0] + ' — ' + (p2.get('short') or '').rstrip('.') + '.') if p2 else ''}\n\n"
                f"Free shipping in Italy over € 39, as always. Reply to this e-mail with anything — a real person reads it (me).\n\n<your name>\n{name}\n\n<unsubscribe link> · <company address>")
        return ("Newsletter draft (from the shop's facts; fill the <…> and it's ready — I never send it myself, you do):\n\n" + body +
                "\n\nRules baked in: one topic, one link, sent from a person, unsubscribe + address at the bottom (GDPR/anti-spam), no 'SALE!!!' subject. Send Tuesday–Thursday 10:00 or Sunday 18:00; look at the click rate after 48 h.")

    def post_time(self, t, m):
        return ("When to post (Italy, small home/gift brand — start here, then let your own numbers overrule me after 3 weeks):\n"
                "• Instagram: 12:30–13:30 (lunch scroll) and 19:00–21:30; best days Tue–Thu, Sunday evening for reels.\n• TikTok: 12:00–13:00, 18:00–22:00; weekends good for reels/lives.\n"
                "• Facebook: 12:00–14:00 and 20:00–22:00; older audience, weekdays.\n• Pinterest: evenings and weekends; timing matters little, consistency matters (pins live for months).\n"
                "• Newsletter: Tue–Thu 10:00 or Sunday 18:00.\n"
                "The real answer is in your insights: post at two different times for 2 weeks, compare reach at 24 h, keep the winner. I can hold the schedule: say “remind me tomorrow at 19 to post”.")

    def post_often(self, t, m):
        return ("How often to post — sustainable beats heroic:\n"
                "• TikTok / Reels: 1 short video a day for the first 30 days (that's the learning phase — the algorithm and you), then 3–5 a week. Under 3 a week the account goes cold.\n"
                "• Instagram feed: 3 posts a week + stories most days (stories are where the 'behind the shop' lives; 2–5 a day is plenty).\n"
                "• Facebook page: 2–3 a week, reuse the Instagram posts.\n• Pinterest: 5–10 pins a week, mostly repins of your own product photos — batch them once a week.\n"
                "• Newsletter: 1–2 a month, never more.\n"
                "Batch it: one afternoon a week, shoot 7–10 clips, edit in the app, schedule. Say “tiktok ideas for <product>” for the week's list; when a post is ready I hand it to you for approval and you tap.")

    def return_rate(self, t, m):
        paid = self._paid()
        try:
            orders = self.store.data["orders"]
        except Exception:
            return None
        if not orders:
            return "No orders yet in the practice store, so no return rate. Say “run a practice day”."
        ref = [o for o in orders if o["status"] == "refunded"]
        canc = [o for o in orders if o["status"] == "cancelled"]
        n = len(paid) + len(ref)
        rate = len(ref) / n * 100 if n else 0
        return (f"Return/refund rate so far: {len(ref)} refunded of {n} paid orders = {rate:.1f} % (plus {len(canc)} cancelled before shipping). "
                + ("That's low — home goods run 2–5 %, fashion 20–30 %." if rate <= 5 else "That's high for home goods (normal 2–5 %) — check the top reason: breakage → packing; 'not as expected' → photos and description.")
                + f" Money lost on them: {_eur(sum(0.029 * o['total'] + 0.30 for o in ref + canc))} in kept payment fees" + (" plus postage on the ones that had shipped." if any(o.get('tracking') for o in ref) else "."))

    def by_country(self, t, m):
        paid = self._paid()
        if not paid:
            return "No orders yet, so no country split. Say “run a practice day”."
        by = {}
        for o in paid:
            c = by.setdefault(o["country"], [0, 0.0])
            c[0] += 1
            c[1] += o["total"]
        rows = sorted(by.items(), key=lambda x: -x[1][1])
        tot = sum(v[1] for _, v in rows)
        top = rows[0][0]
        tip = {"IT": "Italy leads — keep the free-shipping threshold there and consider Italian-only posts.", "DE": "Germany leads — Germans want invoices, exact delivery dates and easy returns; a German help page is worth it."}.get(top, f"{top} leads — check that the shipping fee and delivery time shown for it are right.")
        return ("Sales by country: " + ", ".join(f"{c} {n} order(s) {_eur(v)} ({v / tot * 100:.0f} %)" for c, (n, v) in rows) + f".\n{tip}")

    def by_day(self, t, m):
        paid = self._paid()
        if len(paid) < 14:
            return f"Only {len(paid)} orders so far — too few to see a weekday pattern (you need 3–4 weeks). In general for home goods: Sunday evening and Monday are the strongest, Friday–Saturday the weakest; payday (27th–2nd) lifts everything."
        by = {}
        for o in paid:
            d = o.get("day", 0) % 7
            by[d] = by.get(d, 0) + 1
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        rows = sorted(by.items(), key=lambda x: -x[1])
        return "Orders by weekday (practice days mapped to Mon–Sun): " + ", ".join(f"{names[d]} {n}" for d, n in rows) + f". Best: {names[rows[0][0]]} — post the evening before and send the newsletter that morning."

    def shop_opinion(self, t, m):
        st = self.store
        if st is None:
            return None
        paid = self._paid()
        n = st.numbers()
        day = st.data.get("day", 0)
        good, bad = [], []
        if n["revenue"] and n["profit"] / n["revenue"] >= 0.4:
            good.append(f"margins are healthy ({n['profit'] / n['revenue'] * 100:.0f} % net after goods, shipping and fees)")
        elif n["revenue"]:
            bad.append(f"net margin is thin ({n['profit'] / n['revenue'] * 100:.0f} %) — price or shipping fee needs a look")
        if n["conversion"] >= 1.5:
            good.append(f"conversion {n['conversion']:.1f} % is above the small-shop norm")
        elif paid:
            bad.append(f"conversion {n['conversion']:.1f} % is low — the product page or the shipping cost scares people at checkout")
        oos = [p for p in st.products() if p["stock"] == 0]
        if oos:
            bad.append("sold-out products still listed: " + ", ".join(p["name"].split(" (")[0] for p in oos) + " — every visitor who wanted one is lost")
        late = [o for o in st.data["orders"] if o["status"] == "paid" and day - o.get("day", day) >= 1]
        if late:
            bad.append(f"{len(late)} order(s) waiting longer than the promised next-day shipping")
        units = n["units"]
        if len(units) >= 2:
            top = max(units.values())
            share = top / sum(units.values())
            if share > 0.6:
                bad.append(f"one product makes {share * 100:.0f} % of sales — fine now, risky if the supplier fails; add a second strong one")
            else:
                good.append("sales are spread over several products")
        if not paid:
            return "Too early to judge — no orders yet. The catalogue is sane (5 products, 54–68 % gross margins, honest pages). Run a few practice days and ask me again."
        verdict = ("Honestly: good bones, fix the operational stuff first." if bad and good else "Honestly: it's working — now it needs traffic, not fixes." if not bad else "Honestly: the basics need work before spending a euro on ads.")
        return (f"{verdict}\n" + ("".join(f"✅ {g}\n" for g in good)) + ("".join(f"⚠️ {b}\n" for b in bad)) +
                f"Numbers: {n['orders']} orders, {_eur(n['revenue'])} sales, {_eur(n['profit'])} profit over {day} practice day(s). Next: " +
                ("restock and ship what's waiting, then one post a day for two weeks." if bad else "one video a day for 30 days, then ads on the winner."))

    def add_product_idea(self, t, m):
        what = (m.groupdict().get("what") or "").strip()
        if not what or what in ("it", "them", "this", "that"):
            return None
        fit = {"candle": ("fits the eco-home line", "glass breaks — packing; scent is personal — offer 3 max; soy/beeswax only to stay honest with the brand; margin 3× is normal (cost € 3–5 → € 12–16)"),
               "soap": ("fits", "cosmetics rules: CPNP notification and INCI label needed in the EU — buy from a maker who has them"),
               "tea": ("fits", "food: HACCP/labeling; short shelf life; low ticket — bundle with the mug"),
               "plant": ("fits the brand", "living goods: shipping stress, seasonality, returns impossible — only local"),
               "towel": ("fits", "bulky = shipping cost; GOTS cotton; low margin unless bundled"),
               "jewel": ("weak fit with eco-home", "high margin, tiny parcels, but crowded market and very photo-dependent"),
               "electronic": ("weak fit", "CE, warranty, returns 10 %+, price wars"),
               "clothes": ("weak fit", "sizes → 20–30 % returns; avoid at this stage")}
        key = next((k for k in fit if k in what.lower().rstrip("s")), None)
        f, note = fit.get(key, ("depends on the fit with the current line", "check margin (3× cost), parcel size, breakage, legal labels, and whether it makes the average basket bigger"))
        cats = ""
        try:
            cats = ", ".join(p["name"].split(" (")[0] for p in self.store.products()[:3])
        except Exception:
            pass
        return (f"Adding {what} — {f}. My checklist before you buy stock:\n"
                f"1. Fit: does a buyer of {cats or 'your current products'} also want {what}? If yes it raises the average basket (bundles) — that's the best reason to add anything.\n"
                f"2. Numbers: sell at ≥ 3× landed cost, parcel under 1 kg, breakage risk, returns rate of the category.\n"
                f"3. Specific to {what}: {note}.\n"
                f"4. Test small: 10–20 units from a supplier I've checked (say “find suppliers for {what}” and I do the seller check), one product page, one post a day for two weeks; keep it if it sells 5+ in 30 days.\n"
                f"Verdict: worth a small test, not a big order. Say “compare prices for {what}” and I check what others charge first.")

    def raise_prices(self, t, m):
        st = self.store
        if st is None:
            return None
        n = st.numbers()
        rows = []
        for p in st.products():
            cost = p.get("cost", 0)
            margin = (p["price"] - cost - 0.029 * p["price"] - 0.30) / p["price"] if p["price"] else 0
            rows.append((p, margin))
        thin = [p["name"].split(" (")[0] + f" ({m * 100:.0f} %)" for p, m in rows if m < 0.5]
        fat = [p["name"].split(" (")[0] + f" ({m * 100:.0f} %)" for p, m in rows if m >= 0.6]
        conv = n["conversion"]
        up = bool(re.search(r"\b(raise|increase|alzo|aumento)\b", t.lower()))
        if up:
            return (("Raise prices? " + ("Yes, on the thin ones: " + ", ".join(thin) + " — under 50 % after fees one refund eats three sales. " if thin else "Not across the board — margins are fine. ") +
                     (f"Conversion is {conv:.1f} %, " + ("so demand is there: a 5–10 % rise on the best seller won't hurt. " if conv >= 2 else "already low: raising now would hurt; fix the page first. " if n["orders"] else "no data yet. ")) +
                     "How: change one product at a time, X,90 endings, watch conversion for 2 weeks; never raise in the 30 days before a sale (Omnibus rule). Say “raise the price of <product> to <price>” and I prepare it for your tap."))
        return (("Lower prices? " + ("No — " + ", ".join(fat) + " have room, but lower prices rarely fix sales; visibility does. " if fat else "Careful: margins don't leave room. ") +
                 (f"Conversion is {conv:.1f} %: " + ("fine, so price isn't the problem — traffic is." if conv >= 1.5 else "low — before cutting price, check the shipping cost shown at checkout (the #1 reason people leave) and the photos.") if n["orders"] else "no sales data yet.") +
                 " If you want a lever: a bundle (mug + wraps −10 %) or free shipping over a threshold beats a price cut. Say “should I offer free shipping?”."))

    def joke(self, t, m):
        jokes = ["Why did the parcel break up with the courier? It felt like it was being handled.",
                 "A customer asked if our bamboo toothbrushes were vegan. I said yes — pandas are strictly not on the menu.",
                 "Dropshipping is easy: you just ship drops. Nobody told me the drops needed tracking numbers.",
                 "Our best-selling product this week was 'free shipping'. Margin: excellent."]
        return jokes[_dt.date.today().toordinal() % len(jokes)] + "\n(Back to work? Say “what should I post today” or “what's on my plate”.)"

    def bored(self, t, m):
        opts = ["“what should I post today” — I pick the product and the angle", "“which product should I push” — from the numbers", "“tiktok ideas for <product>”", "“5 captions for the mug”",
                "“build a website for <a place>” — I make one while you watch", "“run a practice day” — customers come, then “what's on my plate”", "“study something” — I read a business article and tell you the one useful thing"]
        return "Bored is good — it means nothing's on fire. Pick one:\n" + "\n".join(f"• {o}" for o in opts)

    def weather(self, t, m):
        place = re.search(r"\b(?:in|at|for|a)\s+([A-Za-zÀ-ú][A-Za-zÀ-ú .'-]{2,40}?)(?:\s+(?:tomorrow|today|next week|this week|domani|oggi))?\W*$", t, re.I)
        when = "week" if re.search(r"\b(next week|this week|settimana|launch|weekend)\b", t.lower()) else "tomorrow" if re.search(r"\b(tomorrow|domani)\b", t.lower()) else "now"
        return {"weather": (place.group(1).strip().title() if place else "Bergamo"), "when": when}

    def good_review(self, t, m):
        return ("Answering a good review — short, personal, useful for the next reader:\n"
                "“Thank you, <name>! Glad the <product> is doing its job — <one specific detail they mentioned>. If it ever needs anything, write to us. — <your name>, <shop>”\n"
                "Rules: reply within 48 h to every 5-star (it shows future buyers a person is there), mention the product name once (search finds it), never a discount code in public replies (looks like buying reviews), "
                "and copy the best lines onto the product page (“as one customer put it: …”) with their first name only.")

    def made_where(self, t, m):
        facts = []
        try:
            for p in self.store.products():
                for d in p.get("details", []):
                    if re.search(r"\bmade in\b|\bfrom\b", d.lower()):
                        facts.append(f"{p['name'].split(' (')[0]}: {d}")
        except Exception:
            pass
        return ("“Where is it made?” — answer with the truth, one line, no drama: buyers who ask usually just want honesty, not a country.\n"
                "“It's made in <country> by <the workshop/factory type>; we chose them for <one real reason: material, quality control, price>. Design/selection and shipping are ours, from Bergamo.”\n"
                + (("What the store already says: " + "; ".join(facts[:4]) + ".\n") if facts else "Put the origin on every product page (it's also required for some goods) — the question stops coming.\n")
                + "Never say 'made in Italy' or 'handmade' if it isn't — that's a legal problem, not a marketing one. If you don't know, ask the supplier today and add it to the page.")

    def gdpr(self, t, m):
        return ("GDPR for a small shop — the must-haves, nothing more:\n"
                "1. Privacy policy page (who you are, what data, why, how long, their rights, your e-mail) — say “write the privacy page” for the skeleton.\n"
                "2. Cookie banner only if you use non-essential cookies (analytics, Meta pixel, TikTok pixel): consent before they load, 'reject' as easy as 'accept'. Essential cookies (cart, login) need no banner.\n"
                "3. Newsletter: opt-in checkbox not pre-ticked, unsubscribe link in every mail, keep the proof of consent (the tool does it).\n"
                "4. Data you keep: order data 10 years (tax law), everything else as short as possible; customer can ask to see/delete → answer within 30 days.\n"
                "5. Processors: your platform, payment provider, courier, mail tool — they're covered by their own terms; list them in the policy.\n"
                "Free tools do the wording (platform built-ins, iubenda free tier). Fines for a micro shop are rare and start with a warning — the real risk is a complaint from an annoyed customer, so just be honest and answer requests.")

    def copied(self, t, m):
        return ("Someone copied your photos/text — it's yours (copyright is automatic), and the fix is a process, not a fight:\n"
                "1. Screenshot everything with the date and URL; save your originals with their creation dates (phone metadata).\n"
                "2. Write to them once, politely: “These photos/texts are ours (links). Please remove them within 48 h.” Most do.\n"
                "3. If not: report to the platform (Etsy/Amazon/eBay/Instagram/Shopify all have a copyright/DMCA form — takes 2–7 days) and to their hosting provider (whois → abuse e-mail) for own websites; Google 'remove content' form for search results.\n"
                "4. A lawyer's letter (€ 100–200) only if they're selling with your photos and it hurts sales.\n"
                "Prevention: small watermark on marketplace photos, your own product shots (not the supplier's — those everyone has), and text that mentions your shop name once. Send me the link and I check what exactly they copied.")

    def price_mistake(self, t, m):
        return ("Wrong price and someone ordered — what you can and should do:\n"
                "• Obvious mistake (€ 3,90 instead of € 39,00): you may cancel — a contract at an evidently wrong price isn't binding; write within 24 h: “Sorry, that was a pricing error on our side (the real price is € X). I've refunded you in full; if you still want it at € X, here's a 10 % code as an apology.” Refund immediately.\n"
                "• Small mistake (€ 34 instead of € 39): honour it. It costs you € 5 and buys a customer; cancelling costs more in trust.\n"
                "• Many orders in minutes (a deal site found it): stop the listing first, then refund all with the same message — don't ship some and cancel others.\n"
                "Then fix the cause: a second look at every price change (I show them for your tap for exactly this reason), and a rule that no product sells below cost — I already warn on that.")

    def buy_boxes(self, t, m):
        return ("Boxes and packing supplies in Italy — cheapest per parcel when you buy 25–50 at a time:\n"
                "• Boxes: RAJA (rajapack.it), Kartoni, Imballaggi 2000, Amazon Business — small double-wall boxes € 0,40–0,90 each in 25s; mailers (busta imbottita) € 0,15–0,30.\n"
                "• Poste: free boxes come only with some Poste Delivery Business contracts; otherwise buy your own.\n"
                "• Bubble wrap € 8–12 per 50 m roll; paper fill (kraft) € 10–15 per 250 m — paper matches an eco brand better than plastic.\n"
                "• Tape: a good dispenser + 6 rolls € 10; a thermal label printer (€ 50–80, no ink) pays back in 2 months if you ship 3+ parcels a day.\n"
                "Pick 2 box sizes max (a small one for cases/wraps/toothbrushes, a medium for mugs/lamps) — fewer sizes = cheaper and faster. Budget: ~€ 1 per parcel all-in.")

    def photos(self, t, m):
        return ("Product photos with a phone — the setup that sells:\n"
                "1. Light: next to a window, no direct sun, a white sheet/card opposite the window to bounce light back. Never the ceiling lamp, never flash.\n"
                "2. Background: white or a light neutral surface for the main photo (marketplaces want it); one 'in use' photo on a real table for the second shot.\n"
                "3. Camera: main lens (not wide), tap to focus on the product, lower exposure a touch, wipe the lens. Phone on a stack of books or a € 15 tripod.\n"
                "4. Shots per product: front, 45°, detail (texture, logo, stitching), scale (in a hand), in use, packaging. 6 photos, same order for every product.\n"
                "5. Edit lightly (brightness, straighten, crop square 1:1 for shop, 4:5 for Instagram); no filters that change the colour — colour mismatches cause returns.\n"
                "Do all products in one session, same spot, same time of day — consistency makes the shop look bigger than it is. Send me a photo and I tell you what to fix (say “look at this photo”).")

    MARKETPLACES = {
        "etsy": ("Etsy", "handmade, vintage, craft supplies and 'design-led' small brands — eco home goods fit well", "€ 0,18 per listing (4 months) + 6,5 % transaction + payment 4 % + € 0,30 + 15 % 'offsite ads' fee if a buyer comes through Etsy's ads (mandatory above $ 10k/yr)", "about 12–15 % all-in", "Yes for a small eco line — the buyers are already there and set-up is an afternoon. Start with your 3 best photos per product, ship in 1 day, and treat Etsy as a second shop window; keep your own site as the home."),
        "amazon": ("Amazon", "everything, price- and Prime-driven", "Individual plan € 0,99 per item or Pro € 39/month, + 8–15 % referral (15 % home & kitchen), + FBA storage/pick-pack if you use their warehouse", "about 15–20 % (more with FBA)", "Not yet. Amazon is a price war with big sellers, needs invoices/GTIN barcodes, and one bad metric suspends the account. Come back when a product sells 5+ a day and you want volume."),
        "ebay": ("eBay", "electronics, collectibles, second-hand and bargain buyers", "up to ~250 free listings/month, then € 0,35; ~12,8 % final value fee + € 0,35 per order", "about 13 %", "Maybe for the lamp and cases (people search eBay for gadgets); weak for mugs and wraps. Low effort: list, see what happens in 30 days."),
        "vinted": ("Vinted", "second-hand clothes and home items; buyers expect used prices", "sellers pay € 0 — buyers pay a 'protection fee' (~5 % + € 0,70); Vinted Pro exists for businesses (selling new goods as a private seller breaks the rules and Italian tax law)", "0 % for you", "No for a shop selling new goods, unless you open a Vinted Pro business account; fine for clearing samples and returns."),
        "subito": ("Subito.it", "local Italian buyers, cash on pickup", "free basic ads; paid boosts € 2–10", "0–5 %", "Only for clearing stock locally (returns, last pieces). Not a sales channel for a brand."),
        "zalando": ("Zalando", "fashion and lifestyle, big brands", "partner program by invitation; ~5–25 % commission; strict logistics", "invite only", "Not reachable for a small shop today; revisit at € 20k+/month."),
        "manomano": ("ManoMano", "home, garden and DIY", "€ 0 fixed for small sellers on the marketplace plan, ~15 % commission; application review", "about 15 %", "Possible for the lamp; the rest doesn't fit. Low priority."),
        "temu": ("Temu", "ultra-cheap direct-from-factory goods", "local seller program in Europe with 0 % commission for now, but Temu sets prices and demands the lowest price on the market", "0 % but price control", "No — your margins and brand die there; it's where your competitors' € 3 mugs live."),
        "facebook marketplace": ("Facebook Marketplace", "local buyers, pickup, second-hand", "free for local listings; a Facebook/Instagram shop is different (uses your catalogue)", "0 %", "Free and quick for local sales; the real move is the Instagram/Facebook Shop tied to your catalogue."),
        "instagram shop": ("Instagram Shop", "your own followers", "free tags on posts; checkout on your site", "0 % (your own gateway)", "Yes — it's your catalogue shown on posts, no fee; needs a Facebook Business account and the product feed (I can prepare it)."),
        "wallapop": ("Wallapop", "second-hand, local (Spain/Italy)", "free; paid 'destacar' boosts", "0 %", "Not for new goods; okay to clear samples."),
    }

    def marketplace(self, t, m):
        key = (m.group("mp") or m.group("mp2") or "").lower()
        if key not in self.MARKETPLACES:
            return None
        name, who, fees, allin, verdict = self.MARKETPLACES[key]
        st = self.store
        top = ""
        if st is not None:
            try:
                prods = sorted(st.products(), key=lambda p: -(p["price"] - p.get("cost", 0)))
                p = prods[0]
                after = p["price"] * (1 - 0.15) - p.get("cost", 0) - 0.30
                top = (f"\nWith your numbers: {p['name']} at {_eur(p['price'])} leaves about {_eur(after)} after ~15 % marketplace fees and cost (vs {_eur(p['price'] - p.get('cost', 0) - 0.029 * p['price'] - 0.30)} on your own site) — "
                       "still fine; below € 10 items it stops being worth the packing time.")
            except Exception:
                top = ""
        return (f"Sell on {name} too? {verdict}\n"
                f"• Who buys there: {who}.\n"
                f"• Fees: {fees} → {allin}.\n"
                "• Rule for any marketplace: same price as your site (never cheaper there), your own photos, ship in 1 business day, answer within 24 h — marketplaces rank sellers on exactly that."
                + top + "\nIf you want it, say so and I put 'open the account + list 3 products' on the plan; the account is yours, I prepare the listings for your tap.")

    def gift_wrap(self, t, m):
        st = self.store
        aov = None
        paid = self._paid()
        if paid:
            aov = sum(o["total"] for o in paid) / len(paid)
        return ("Gift wrapping — yes, as a paid option, because your products are gifts (mugs, wraps, lamps) and it's the cheapest 'premium' you can add:\n"
                "• Price it € 2,90–3,90; it costs you ~€ 0,60 (kraft paper, jute string, a card) + 2 minutes. Typically 10–20 % of orders take it, more in Nov–Dec.\n"
                "• Offer a free handwritten card message with it — that's what people actually want; 'gift receipt without prices' in the box.\n"
                "• Keep ONE style (kraft + your stamp/sticker) — matches an eco brand and never runs out of a colour.\n"
                "• On the site: a checkbox at checkout 'Gift wrap + card (€ 2,90)' with a message field; on the product page one photo of the wrapped item.\n"
                + (f"With an average order of {_eur(aov)}, a € 2,90 add-on on 15 % of orders is about +{aov and 2.9 * 0.15 / aov * 100:.0f} % revenue at ~80 % margin — small, but it also cuts returns (gifts get kept). " if aov else "")
                + "Say “add gift wrapping to the store” and I prepare the checkout option and the page text for your tap.")

    def cheaper_elsewhere(self, t, m):
        p = self._product(t)
        who = re.search(r"\b(amazon|temu|aliexpress|shein|ebay|ikea)\b", t, re.I)
        who = who.group(1).title() if who else "A competitor"
        pline = ""
        if p:
            cost = p.get("cost", 0)
            floor = round((cost + 0.30 + 3.25) / (1 - 0.029 - 0.30), 2)   # price that still leaves ~30 % after fees + shipping share
            pline = (f"\nYour {p['name']}: sells at {_eur(p['price'])}, costs {_eur(cost)} — the lowest price that still leaves ~30 % after fees and your share of shipping is about {_eur(floor)}. "
                     f"Never go under that to chase {who.lower() if who.startswith('A ') else who}; if their price is below your cost, they're selling a different product (quality, warranty, origin) or losing money.")
        return (f"{who} sells it cheaper — this happens to every small shop, and the answer is not to match the price:\n"
                "1. Check it's really the same item: material, size, brand, seller reviews, delivery time, return rights. Usually it isn't — then say so on your page (“hand-glazed in Portugal, 2-year warranty, ships from Italy in 1 day”).\n"
                "2. Compete on what they can't do: your photos, a gift option, a bundle (mug + wraps), the handwritten note, replies within an hour, easy returns. People pay 20–30 % more for certainty on a € 15–40 purchase.\n"
                "3. If it IS the same generic product from the same factory, drop it from the line over time — a product you can't defend is a product you'll never make money on.\n"
                "4. Don't start a price war; a price cut is the only move competitors copy the same day." + pline +
                "\nSay “compare the <product> on amazon” and I fetch their listing, price, delivery and reviews into a document so you see the real difference.")

    def discount_code(self, t, m):
        st = self.store
        name = "the shop"
        if st is not None:
            try:
                name = st.data.get("name", "the shop").split(" — ")[0]
            except Exception:
                pass
        ask = bool(re.search(r"\b(asks?|asking|wants?|would like|chiede|vuole)\b", t, re.I))
        head = ("A customer asks for a discount code — " if ask else "Discount codes — ")
        return (head + "the practice store has none yet, and my rule is: one code, one purpose, never 'because they asked'.\n"
                "• A blanket 10 % for anyone who asks trains people to ask; a code tied to something (newsletter sign-up, second order, a review with a photo) earns its cost.\n"
                "• Sensible set: WELCOME10 only via the newsletter box (10 %, first order, 30 days), COMEBACK10 in the parcel card (second order), free shipping over € 39 for everyone (already in place) — nothing else.\n"
                "• Cost check: 10 % on a € 14,90 mug is € 1,49 of a ~€ 5,50 margin — fine once, not on every order.\n"
                + ("Reply to the customer (for your tap): “Thanks for asking! We don't do codes on request, but if you sign up to our newsletter you get 10 % off your first order — and shipping is free over € 39.” "
                   "It says no without saying no.\n" if ask else "")
                + f"Say “create a welcome code” and I prepare it (10 %, first order, newsletter) for your tap; {name}'s checkout takes it from there.")

    def packing_slip(self, t, m):
        return ("What goes in the parcel (in this order, top to bottom):\n"
                "1. Packing slip — order number, date, the items and quantities (no prices needed for B2C; put prices only if the customer asked for a receipt), your shop name, e-mail and return address. Half a page. I print it with the label (say “print the shipping labels”).\n"
                "2. A small card — handwritten first name + 2 lines of thanks + how to return/contact. Optionally a code for the next order (COMEBACK10). Costs € 0,10, gets you reviews and second orders.\n"
                "3. Care/use note if the product needs one (mug: dishwasher ok; wraps: cold water, no meat; lamp: charge 2,5 h first).\n"
                "4. Invoice: only if requested (or B2B) — Italian B2C sales need no invoice unless the customer asks at checkout; keep the 'corrispettivi' record instead.\n"
                "5. Nothing loose: card and slip in a paper sleeve, not floating.\n"
                "Outside the box: only the label and a 'fragile' mark where needed — no company stickers that invite theft. Say “write the thank-you card text” and I draft it.")

    def stock_hold(self, t, m):
        n = int(m.group("n")) if m.groupdict().get("n") else None
        p = self._product(m.groupdict().get("what") or t)
        if not p:
            return ("Ship what was ordered — an order is a promise, and holding a paid unit back to 'keep one in stock' is how you end up with two unhappy customers instead of one happy one. "
                    "Then reorder today. If the last unit is a display/photo sample, sell it too and shoot photos before it goes.")
        st = self.store
        day = st.data.get("day", 0)
        week = sum(l["qty"] for o in self._paid() if o.get("day", 0) > day - 7 for l in o["lines"] if l["id"] == p["id"])
        left = p["stock"]
        after = left - (n or 0) if n and left >= (n or 0) else left
        return (f"Ship the order in full — the {p['name']} has {left} in stock" + (f", {after} after this order" if n else "") +
                f" (selling {week} a week lately). Holding one back gains you nothing: the next buyer pays the same, and a partial shipment costs you a second postage and an annoyed customer.\n"
                f"Do instead: (1) mark it shipped when GLS takes it; (2) reorder now — say “how much should I order of the {p['name'].split(' (')[0].lower()}” and I compute it; "
                f"(3) if the supplier needs 2+ weeks, put 'ships in X days' on the page when it hits 0 instead of hiding it — pre-orders keep the sales.")

    def auto_reply(self, t, m):
        st = self.store
        name, mail = "Green Nest", "help@greennest.example"
        if st is not None:
            try:
                name = st.data.get("name", name).split(" — ")[0]
                mail = st.data.get("pages", {}).get("contact_email", mail) if isinstance(st.data.get("pages"), dict) else mail
            except Exception:
                pass
        it = bool(re.search(r"\b(risposta automatica|ferie|in italiano|italian)\b", t, re.I))
        en = (f"Subject: We got your message — {name}\n\n"
              "Hi, thanks for writing to us! This is an automatic note to say your message arrived.\n"
              "We answer every e-mail personally within 1 business day (Mon–Fri). Orders keep shipping as usual, within 1 business day.\n"
              "Quick answers meanwhile: tracking → in your shipping e-mail; returns → 30 days, instructions at <returns page>; order changes → reply with your order number.\n"
              f"Talk soon,\n{name} · {mail}")
        hol = ("Holiday version — add one line at the top: “We're closed from <date> to <date>; orders placed now ship on <date> and e-mails get answered from that day. Thank you for your patience!”")
        itx = (f"Oggetto: Abbiamo ricevuto il tuo messaggio — {name}\n\n"
               "Ciao, grazie per averci scritto! Questa è una risposta automatica per dirti che il messaggio è arrivato.\n"
               "Rispondiamo personalmente a ogni e-mail entro 1 giorno lavorativo (lun–ven). Gli ordini partono regolarmente entro 1 giorno lavorativo.\n"
               "Nel frattempo: tracking → nell'e-mail di spedizione; resi → 30 giorni, istruzioni su <pagina resi>; modifiche all'ordine → rispondi con il numero d'ordine.\n"
               f"A presto,\n{name} · {mail}")
        rules = ("Rules: short, a real reply time, the three things people actually ask, no 'your message is important to us'. Set it in Gmail → Settings → Vacation responder (dates + this text) — "
                 "or say “set the auto-reply” when Gmail is connected and I prepare it for your tap.")
        return ("Auto-reply for the shop e-mail — English first, Italian under it; fill the <…>:\n\n" + (itx + "\n\n" + en if it else en + "\n\n" + itx) + "\n\n" + hol + "\n" + rules)

    def first_followers(self, t, m):
        st = self.store
        prods = []
        if st is not None:
            try:
                prods = [p["name"].split(" (")[0] for p in st.products()][:3]
            except Exception:
                prods = []
        ex = prods[0] if prods else "your best product"
        return ("First 100 followers — they come from work, not tricks; here's the 30-day version that works for a small shop:\n"
                "1. Profile first (day 1): clear name, one-line bio saying what you sell + where you ship, link to the shop, 9 posts before you invite anyone (an empty page converts nobody).\n"
                f"2. Post 1 a day for 30 days, 3 formats in rotation: the product in real use ({ex} on a real desk/kitchen), a 15-second making/packing video, one 'why we do this' text post. Reels/TikTok get reach without followers; photos don't.\n"
                "3. 20 minutes a day of real comments on 10 accounts your buyers follow (eco home, slow living, Italian design) — not 'nice pic', a real sentence. That's where the first 100 come from.\n"
                "4. Tell the people you already have: every parcel gets a card with the handle; your e-mail signature; your personal account shares the shop once a week.\n"
                "5. One small collaboration: 3 micro-creators (2–10k followers) get a product for an honest story — ask me, I write the message.\n"
                "Don't: buy followers (kills reach for good), giveaways for follows (you get freebie hunters), 5 platforms at once (one, done well). "
                "Measure reach and saves, not followers — 100 real ones who buy beat 5,000 who don't. Say “what should I post today?” and I give you the day's post.")

    def refund_or_replace(self, t, m):
        p = self._product(t)
        st = self.store
        line = ""
        if p:
            cost, price, stock = p.get("cost", 0), p["price"], p["stock"]
            repl = cost + 3.25 + 1.0
            line = (f"\nYour numbers for the {p['name']}: a replacement costs you about {_eur(repl)} (goods {_eur(cost)} + postage + box) and keeps the {_eur(price)} sale; a refund costs the full {_eur(price)} plus the first postage. "
                    + (f"{stock} in stock, so replace is possible." if stock > 0 else "Stock is 0, so it has to be a refund (or 'we resend as soon as it's back, plus a small extra' if they can wait)."))
        return ("Refund or replace? Let the customer choose — but lead with the replacement, and never ask them to send the broken one back (a photo is enough under € 30; the return postage would cost more than the item):\n"
                "• Reply today: “I'm so sorry — that shouldn't happen. I can send you a new one tomorrow, or refund you in full today; which do you prefer? No need to return the damaged one.”\n"
                "• Replace when it's in stock and the damage is transport/one-off — most people want the product, and a fast replacement turns a complaint into a 5-star review.\n"
                "• Refund when it's out of stock, it's the second problem with the same customer, or the fault is the product itself (then pull the batch).\n"
                "• Either way: log it (order, photo, cause) — 3 breakages of the same item = a packaging problem, not bad luck; and claim from the courier if the box was crushed." + line +
                "\nForward me the customer's message and I draft the reply for your tap; say “refund order <n>” or “resend order <n>” once they answer.")

    def vacation(self, t, m):
        return ("Going on holiday with an online shop — four ways, pick by how long:\n"
                "• Up to 4 days: nothing changes — set the shipping page to 'orders ship on <date>', I keep answering customers with drafts for your tap, and you ship when back.\n"
                "• 1–2 weeks: (a) put a banner + checkout note 'orders placed now ship on <date>' (people still order for gifts), or (b) ask a friend/family member to ship: pre-print labels, a photo of how to pack, € 1–2 per parcel — I prepare the label file; or (c) pause the store (Shopify 'password page', Etsy 'vacation mode') — cleanest, costs you the sales.\n"
                "• Longer: a fulfilment service (from ~€ 2–3 per order + storage) — worth it only above ~50 orders a month.\n"
                "Before you leave: reply to the inbox, ship everything (say “all shipped”), set the auto-reply with the return date, tell me the dates — I'll hold customer drafts and ping you only for the urgent ones (chargebacks, damaged parcels).")
