"""Questions about ME and about judgment — answered from what the agent actually knows about itself and the shop:

    "what are you doing right now?"           → the running job / idle state, honestly
    "why did you propose lowering the mug?"    → the proposal's own 'why' from the ledger
    "what would you change about the shop?"    → concrete list from the numbers (stock-outs, late orders, thin margins…)
    "if you were me, what would you do first?" → the first thing, with the reason
    "explain the numbers like I'm 5"           → the shop's P&L in a child's words
    "we made 300 euros this week, is that good?" → judged against the shop's own costs
    "how much would we make if we doubled the traffic?" → conversion × basket, honestly caveated
    "what's the plan for next week?"           → from to-dos, stock, proposals
    "can you handle the shop alone for a week?" → what I do alone, what needs the owner's tap

No model, no browsing. SelfTalk(store, inbox, memory, mind, pace, tasks_stats).reply(text) → str or None.
"""
import datetime as _dt
import json
import re
import time


def _eur(x):
    return f"€ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _num(s):
    return float(str(s).replace(".", "").replace(",", ".")) if re.search(r"\d\.\d{3}\b", str(s)) else float(str(s).replace(",", "."))


class SelfTalk:
    def __init__(self, store=None, inbox=None, memory=None, mind=None, pace=None, version=""):
        self.store = store
        self.inbox = inbox
        self.memory = memory
        self.mind = mind
        self.pace = pace
        self.version = version
        self.busy_text = lambda: None          # core sets this to a function returning Agent.busy
        self.last_reply = lambda: None         # talk sets this: () → (question, answer) of the last thing I said

    RULES = [
        (r"^\W*(?:ok[,.]? |yes[,.]? |sure[,.]? |fine[,.]? |va bene[,.]? |sì[,.]? )?(?:approve|apply|accept|confirm|go ahead with|approva|applica|accetta|conferma)\s*(?:it|that|this|the (?:last|latest) (?:one|proposal)|the proposal|quello|quella|questo|questa|la proposta)?\W*$|^\W*(?:approved|applied|accepted|confirmed|approvato|approvata)\W*$", "approve_last"),
        (r"^\W*(?:no[,.]? |nah[,.]? |non? [,.]?)?(?:reject|decline|refuse|leave it|leave that|don'?t (?:do|apply|change) (?:it|that|this)|skip (?:it|that)|forget (?:it|that)|rifiuta|lascia stare|lascia perdere|non (?:farlo|applicarlo))\s*(?:it|that|this|the (?:last|latest) (?:one|proposal)|the proposal|quello|quella|la proposta)?\W*$|^\W*(?:rejected|declined|rifiutato|rifiutata)\W*$", "reject_last"),
        (r"^\W*(?:undo|revert|roll ?back|take (?:it|that) back|put it back|annulla|ripristina|torna indietro)\s*(?:it|that|this|the last (?:one|change)|the change|that change|l'?ultima modifica|quello|quella)?\W*$", "undo_last"),
        (r"^\W*(?:what(?:'s| is) (?:still )?(?:pending|open|waiting|outstanding|unresolved)|(?:any|anything) (?:pending|open|waiting)|open (?:proposals|items)|pending (?:proposals|items|things)|what (?:needs|is waiting for) (?:my )?(?:tap|approval|decision|ok)|what (?:do i|should i) (?:need to )?(?:approve|decide)|cosa (?:c'è|è) in sospeso|cosa devo approvare|proposte aperte)\W*$", "pending"),
        (r"\b(?:show|see|repeat|resend|send (?:me )?again|what was|read me|remind me of) (?:me )?(?:the |your |that )?(?:last|latest|previous|most recent) (?:proposal|suggestion|proposta|change you proposed)\b|\bthe last proposal\??\W*$|\bl'?ultima proposta\W*$", "last_proposal"),
        (r"\bwhat (?:did|have) i (?:approve|apply|accept|reject|decline|decide|approved|applied|rejected)\b(?: today| this week| yesterday| so far)?|\bwhat (?:changed|changes were made|did you change|was changed|did we change)\b(?: in the shop| today| this week)?\W*$|\b(?:changes|change log|changelog|history) (?:today|this week|so far)\b|\bcosa ho approvato\b|\bcosa è cambiato\b", "decisions_log"),
        (r"\bhow many (?:proposals|suggestions|changes|things) (?:did|have) you (?:make|made|propose|proposed|suggest|suggested)\b|\bhow many (?:proposals|of (?:them|those|your proposals)) (?:did|have) i (?:reject|rejected|approve|approved|accept|accepted|apply|applied|say no to|turn down)\b|\bhow many did i (?:reject|approve|accept|apply|say no to|turn down)\b|\bproposal (?:stats|statistics|count|numbers)\b|\byour (?:hit|approval|acceptance) rate\b|\bquante proposte\b", "proposal_stats"),
        (r"^\W*(?:move|shift|push|postpone|reschedule|change|sposta|rimanda) (?:that|the|this|my|it|quel|il|la) ?(?:reminder|to-?do|task|it|promemoria)?\s*(?:to|for|until|till|a|al)\s+(?P<when>tomorrow|domani|today|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica|next week|la settimana prossima|next month|\d{1,2}[/.]\d{1,2}|\d{1,2} (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*)(?:\s+(?:at|alle)\s+(?P<time>\d{1,2}(?:[:.]\d{2})?))?\W*$", "move_reminder"),
        (r"^\W*(?:cancel|delete|remove|drop|forget|scrap|kill|cancella|elimina|togli|rimuovi) (?:that|the|this|my|it|quel|il|la|questo|quella) ?(?:last )?(?:reminder|promemoria)\W*$|^\W*(?:cancel|delete|remove|drop|forget|scrap|cancella|elimina|togli|rimuovi) (?:the |that |this |my |il |la |quel )?(?:to-?do|task|item|entry|reminder|promemoria|voce)?\s*(?:about|on|for|regarding|called|saying|su|per|del|della|sul|sulla)\s+(?P<what>.{3,60}?)\W*$|^\W*(?:cancel|delete|remove|drop|forget|cancella|elimina|togli|rimuovi) (?:to-?do |task |item |number |#)?(?P<n>\d{1,3})\W*$", "delete_todo"),
        (r"^\W*(?:mark|tick|set) (?:everything|all|them all|all of them|all items|the whole list|tutto|tutti) (?:as )?(?:done|complete|completed|finished|fatto|fatti)\W*$|^\W*(?:everything|all|all of it|all of them|the whole list|tutto|tutti)(?:'s| is| are)? (?:done|finished|complete|completed|fatto|fatti)\W*$|^\W*(?:done with (?:everything|all of it|the list|all)|all done|tutto fatto)\W*$", "all_done"),
        (r"^\W*(?:clear|empty|wipe|reset|delete|erase|svuota|cancella|pulisci|azzera) (?:my |the |our |la |il |tutta la )?(?:to-?do|todo|task)? ?(?:list|lista|list of to-?dos)\W*$|^\W*(?:delete|remove|clear) (?:all|every) (?:my |the )?(?:to-?dos|tasks|items|reminders)\W*$", "clear_list"),
        (r"\bwhat (?:does|do) (?:the |our |my )?(?P<page>shipping|delivery|returns?|refunds?|faq|about|contact|privacy|terms) (?:page|policy|pages|section|text)(?: on the (?:site|shop|store))? (?:say|says|read|state|contain|look like)\b|\b(?:read|show|give|send) (?:me )?(?:the |our |my )?(?P<page2>shipping|delivery|returns?|refunds?|faq|about|contact|privacy|terms) (?:page|policy|text|wording)\b|\bcosa (?:dice|c'è scritto (?:nel|sulla|nella)) (?:la )?pagina (?P<page3>spedizioni|resi|faq|contatti|privacy|termini)\b|\bleggimi (?:la )?(?:pagina |politica )?(?:dei |delle |di )?(?P<page4>spedizioni|resi|rimborsi|faq)\b", "read_page"),
        (r"\b(?:change|set|make|update|move|put|extend|shorten|cambia|metti|porta|allunga|accorcia) (?:the |our |my |il |la |i )?(?:returns?|resi|reso|refund|withdrawal|recesso) (?:window|period|policy|time|days|term|deadline|periodo|termine|finestra)?\s*(?:to|at|a|di|from \d+ to)\s*(?P<n>\d{1,3})\s*(?:days?|giorni|d)\b|\b(?P<n2>\d{1,3})[- ]day returns?\b.{0,20}?\b(?:instead|from now|make it|set|switch)\b|\breturns? (?:within|entro) (?P<n3>\d{1,3}) (?:days|giorni) (?:instead of|invece di|from now on|d'ora in poi)\b", "returns_window"),
        (r"\b(?:which|what|who) (?:customers?|orders?|buyers?|people|clienti|ordini)\b.{0,20}?\b(?:waiting|wait|waited|been waiting|are waiting|is waiting|aspettano|in attesa)\b.{0,20}?\b(?:longest|most|long|the longest|più a lungo|da più tempo)\b|\bwho(?:'s| is| has) (?:been )?waiting (?:the )?longest\b|\boldest (?:unshipped|open|waiting|pending) orders?\b|\blongest[- ]waiting (?:customers?|orders?)\b|\bchi aspetta da più (?:tempo|giorni)\b", "waiting_longest"),
        (r"\bhow much (?:did|has|was) (?:order|the order|ordine|l'?ordine)\s*#?\s*(?P<n>\d{4,6})\s*(?:pay|paid|cost|come to|total|worth|pagato|costava)?\b|\b(?:order|ordine)\s*#?\s*(?P<n2>\d{4,6})\b.{0,25}?\b(?:total|amount|value|how much|worth|paid|price|totale|importo|quanto)\b|\b(?:total|amount|value|totale|importo) (?:of|for|di|dell'?ordine)\s*(?:order )?#?\s*(?P<n3>\d{4,6})\b|\bwhat(?:'s| is| was) (?:in|on) (?:order|ordine)\s*#?\s*(?P<n4>\d{4,6})\b|\b(?:who|whose|chi)\b.{0,15}?\b(?:order|ordine)\s*#?\s*(?P<n5>\d{4,6})\b|\b(?:tell me about|show me|details of|dettagli) (?:order|ordine)\s*#?\s*(?P<n6>\d{4,6})\b", "order_lookup"),
        (r"\bwhat (?:happens|would happen|will happen|if) (?:if )?(?:i|we) (?:do|did) nothing\b|\bif (?:i|we) (?:do|did) nothing (?:for|this|next|all)\b|\bwhat if (?:i|we) (?:ignore|skip|leave) (?:it|the shop|everything) (?:for )?(?:a|this|one|the) (?:week|month|day)\b|\bse non faccio (?:niente|nulla)\b|\bwhat happens if (?:i|we) (?:stop|pause|take a break)\b", "do_nothing"),
        (r"\b(?:i'?m|i am|we'?re|we are|sono|vado|parto) (?:going |away )?(?:on|in) (?:holiday|holidays|vacation|vacanza|ferie)\b|\b(?:holiday|vacation|vacanza|ferie) (?:for|per|next|from|dal|da)\b|\b(?:i'?ll be|i will be|i'?m) (?:away|off|gone|out of town|abroad|unreachable|offline) (?:for|from|until|next|the whole|tutta|per) \b|\bgoing away for (?:a |two |three |\d+ )?(?:days?|weeks?|month)\b|\bsarò via\b|\bnon ci sono per\b", "holiday_plan"),
        (r"\bcan you (?:run|handle|manage|watch|mind|look after) (?:the |my |our )?(?:shop|store|business|things|it) (?:while|when) (?:i|we) (?:sleep|am asleep|'m asleep|are asleep|work|'m at work|am at work|'m away|are out)\b|\bwhile i sleep\b|\b(?:at|during the) night\b.{0,30}?\b(?:you|shop|orders|customers)\b.{0,20}?\?|\bdo you (?:work|run|sleep) (?:at night|24/7|all the time|nonstop|overnight)\b|\bmentre dormo\b|\blavori (?:anche )?di notte\b", "while_sleep"),
        (r"\bhow do you (?:decide|choose|pick|know) (?:what|which|when) to (?:propose|suggest|change|flag|recommend|ask)\b|\bwhy (?:do|did) you propose (?:that|this|it|things)\b|\bwhat makes you propose\b|\bhow do proposals work\b|\bcome decidi (?:cosa|quando) propor\w+\b", "how_propose"),
        (r"\bwhat (?:can'?t|cannot|can not|don'?t|do not|won'?t|will not) you do\b|\bwhat are you (?:not able|unable) to do\b|\byour (?:limits|limitations|weaknesses|blind spots)\b|\bwhat are you bad at\b|\bcosa non (?:sai|puoi|riesci a) fare\b|\bthings you can'?t do\b", "cant_do"),
        (r"\bare you sure (?:the |that the |about the )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?) (?:margin|price|cost|stock|number|figure|numbers) (?:is|are) (?:right|correct|ok|accurate)\b|\bis the (?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?) (?:margin|cost|price) (?:right|correct|accurate)\b|\b(?:check|double-check|verify|recheck) the (?P<what3>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?) (?:margin|cost|price|numbers)\b", "check_product_number"),
        (r"\b(?:a |my )?(?:friend|mate|buddy|neighbou?r|colleague|cousin|sister|brother|mum|mom|dad|aunt|uncle|amic[oa]|collega|vicin[oa]) (?:wants?|would like|asked|asks|is asking|vuole|chiede)(?: to buy| to order| to get| to have)? (?:a |an |the |one |two |\d+ |un |una |il |la )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\b.{0,30}?\b(?:price|how much|what do i charge|charge|discount|prezzo|quanto|sconto)\b|\b(?:friends?|family|family and friends|amici|parenti) (?:price|discount|rate)\b|\bwhat (?:do i|should i|to) charge (?:a |my )?(?:friend|mate|family|cousin|neighbou?r)\b|\bhow much (?:for|do i charge) (?:a |my )?(?:friend|mate|colleague|neighbou?r)\b", "friend_price"),
        (r"\b(?:customer|client|buyer|someone|cliente)\b.{0,20}?\b(?:paid|has paid|says (?:he|she|they) paid|ha pagato|dice di aver pagato)\b.{0,40}?\b(?:never (?:got|received|arrived|saw)|didn'?t (?:get|receive|arrive)|not (?:received|arrived|in|on) (?:the |my )?(?:account|bank|stripe|paypal)|no money|nothing (?:arrived|came)|non (?:è arrivato|ho ricevuto|vedo) (?:niente|nulla|i soldi|il pagamento))\b|\bpayment (?:missing|not received|never arrived|didn'?t arrive|not showing)\b|\b(?:money|payment|pagamento|soldi) (?:never|not|hasn'?t|non è) (?:arrived|came|showed up|arrivat[oi])\b|\bpaid but (?:no|not|nothing|never)\b", "payment_missing"),
        (r"\b(?:when|how long until|how long before|how soon|in how many days|quando|tra quanto) (?:will|do|can|could|might|does)? ?(?:we|i|the shop|it)? ?(?:hit|reach|get to|make|pass|cross|arrive at|be at|raggiung\w+|arriv\w+ a|far\w*) (?:€|eur)?\s*(?P<amt>\d[\d.,]*)\s*(?:k|€|eur|euro|euros|mila)?\s*(?:of |in |di )?(?P<what>profit|revenue|sales|turnover|orders|customers|a month|per month|month|profitto|utile|fatturato|vendite|ordini|clienti)?\b", "when_reach"),
        (r"\bhow (?:do|can|would) (?:i|we|you) (?:know|tell|check|see|find out|verify|spot) (?:if|whether|that) (?:a |the |this |an? online )?(?:supplier|seller|vendor|wholesaler|factory|shop|store|site|website|fornitore|venditore) is (?:legit|legitimate|real|trustworthy|reliable|safe|serious|a scam|fake|genuine|ok|okay)\b|\b(?:legit|trustworthy|reliable) (?:supplier|seller)\b.{0,20}?\b(?:how|signs|tell)\b|\bsigns of a (?:fake|scam|bad) (?:supplier|seller)\b|\bcome (?:capisco|faccio a capire|so) se (?:un |il )?(?:fornitore|venditore) è (?:serio|affidabile|una truffa)\b", "supplier_legit"),
        (r"\bhow (?:do|does|will) (?:refunds?|a refund|rimbors[oi]) work (?:with|on|in|through) (?:stripe|paypal|shopify payments|the card|cards|satispay|klarna)\b|\b(?:stripe|paypal) refunds?\b.{0,20}?\b(?:how|fees?|cost|time|days)\b|\brefund (?:fees?|costs?)\b.{0,20}?\b(?:stripe|paypal)\b|\bcome funzionano i rimborsi (?:con|su) (?:stripe|paypal)\b", "refund_mechanics"),
        (r"\b(?:difference|differenza) between (?:gross )?margin and markup\b|\bmargin (?:vs\.?|versus|or) markup\b|\bmarkup (?:vs\.?|versus|or) margin\b|\bmargine (?:e|o|vs) (?:ricarico|markup)\b", "margin_vs_markup"),
        (r"\bhow many (?:orders|sales|ordini|vendite) (?:a|per|each|al|ogni) (?:day|week|month|giorno|settimana|mese) (?:is|are|counts as|would be|è|sono) (?:'|\")?(?:good|ok|okay|normal|enough|decent|healthy|bene|buono|normale)\b|\bis \d+ (?:orders|sales|ordini) (?:a|per) (?:day|week|month) (?:good|ok|okay|normal|enough|decent|bad)\b|\bwhat(?:'s| is) a (?:good|normal|decent|healthy) (?:number of )?(?:orders|sales) (?:a|per) (?:day|week|month)\b", "orders_benchmark"),
        (r"\bwhat(?:'s| is) a (?:good|normal|acceptable|healthy|typical|decent|bad|high) (?:return|refund|cancellation|resi|reso) rate\b|\bis (?:our|my|the|a|\d+ ?%) (?:return|refund) rate (?:good|ok|okay|normal|high|bad|too high|fine)\b|\breturn rate (?:benchmark|norm|average|normal)\b|\bqual ?[èe] un (?:buon )?tasso di res[oi] (?:normale|accettabile)?\b", "return_benchmark"),
        (r"^\W*(?:what(?:'s| is| does| do) (?:an? |the )?)?(?P<term>sku|skus|aov|cogs|roas|cpc|cpm|ctr|cac|ltv|clv|mov|upsell|cross-?sell|conversion rate|conversion|bounce rate|churn|dropshipping|dropship|3pl|fulfil+ment|landed cost|cogs|gross margin|net margin|margin|markup|break-?even|cash ?flow|inventory turnover|stock turnover|lead time|moq|minimum order quantity|white label|private label|oss|vies|incoterms|ddp|dap|exw|fob|omnibus|chargeback|reverse charge|forfettario|ateco|sdi|pec|a/b test|ab test|kpi|seo|sem|ugc|cro|dm|reel|carousel|hook|cta|call to action|funnel|retargeting|pixel|lookalike|open rate|click rate|unsubscribe rate|net promoter score|nps|omnichannel|marketplace|pos|epos|barcode|ean|gtin|hs code|customs code|tracking number|proof of delivery|pod|sla|b2b|b2c|d2c|dtc|wholesale|retail|rrp|msrp|map|bundle|loss leader|anchor price|charm pricing|psychological pricing|dynamic pricing|price elasticity|sunk cost|opportunity cost|fixed cost|variable cost|unit economics|contribution margin|payback period|working capital|invoice|pro forma|proforma|credit note|withdrawal right|diritto di recesso|legal guarantee|garanzia legale)(?: mean| stand for| stands for)?\??\W*$|^\W*(?:cos'?[èe]|che cos'?[èe]|cosa (?:è|significa|vuol dire)|che (?:significa|vuol dire))\s+(?:lo |la |il |l'|un |una |gli |le |i )?(?P<term3>sku|aov|cogs|roas|cpc|cpm|ctr|cac|ltv|conversion rate|conversion|tasso di conversione|bounce rate|churn|dropshipping|3pl|landed cost|gross margin|net margin|margine|margin|markup|ricarico|break-?even|cash ?flow|lead time|moq|white label|private label|oss|vies|incoterms|ddp|omnibus|chargeback|reverse charge|forfettario|ateco|sdi|pec|kpi|seo|ugc|cro|hook|cta|funnel|retargeting|pixel|open rate|nps|b2b|d2c|wholesale|rrp|bundle|loss leader|unit economics|working capital|nota di credito|diritto di recesso|garanzia legale|fattura|ean|pos)\??\W*$|\b(?:explain|spiega(?:mi)?|define|meaning of|what does) (?:the term |the word |a )?(?P<term2>sku|aov|cogs|roas|cpc|cpm|ctr|cac|ltv|conversion rate|conversion|bounce rate|churn|dropshipping|3pl|landed cost|gross margin|net margin|margin|markup|break-?even|cash ?flow|inventory turnover|lead time|moq|white label|private label|oss|vies|incoterms|ddp|omnibus|chargeback|reverse charge|forfettario|sdi|pec|kpi|seo|ugc|cro|hook|cta|funnel|retargeting|pixel|open rate|nps|b2b|d2c|wholesale|rrp|bundle|loss leader|anchor price|charm pricing|unit economics|contribution margin|payback period|working capital|credit note|withdrawal right)\b(?: like i'?m (?:5|five|10|ten|a kid|new to this))?(?: mean| stands? for)?\W*$", "glossary"),
        (r"^\W*(?:note|nota|remember|ricorda|ricordati|keep in mind|fyi|for the record|write (?:this )?down|segna|appunta)\b\s*(?:that|this|che|:)?\s*(?P<what>.{6,300})$", "take_note"),
        (r"\bwhat(?:'s| is) (?:the |our |my )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?) (?:supplier|fornitore|vendor|factory|maker|producer|courier|accountant|commercialista|photographer|designer|bank|agency)(?:'s name| called| name)?\b\W*$|\bwho (?:makes|supplies|produces|manufactures|delivers|ships) (?:the |our |my )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\W*$|\bwho (?:is|'s) (?:the |our |my )?(?P<what5>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?) (?:supplier|fornitore|vendor|courier|accountant|commercialista)\W*$|\bcome si chiama (?:il |la )?(?:fornitore|corriere) (?:del|della|dei|delle) (?P<what3>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\W*$", "recall_fact"),
        (r"\bhow(?:'s| is|’s) (?:the |our |my )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?) (?:doing|going|selling|performing|moving)\b|\bcome (?:va|vanno|sta andando) (?:la |il |le |i |lo )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\W*$", "product_report"),
        (r"\b(?:is|are) (?:the |our |my )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?) worth (?:keeping|it|selling|stocking|reordering|the (?:shelf|space|trouble))\b|\bis it worth (?:keeping|selling|stocking|reordering|pushing|advertising) (?:the |our |my )?(?P<what4>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\W*$|\bshould (?:i|we) (?:drop|kill|remove|delist|discontinue|stop (?:selling|stocking|advertising|pushing|promoting)|get rid of|keep) (?:the |our |my )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\W*$|\bwhich (?:product|item|one) should (?:i|we) (?:drop|stop (?:advertising|pushing|selling|promoting)|discontinue|cut)\b|\b(?:conviene|vale la pena|devo|dovrei) (?:tenere|continuare a vendere|togliere|eliminare) (?:il |la |le |i |lo |gli )?(?P<what3>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\W*$", "keep_or_drop"),
        (r"\b(?:quali sono|dimmi) i miei punti (?:deboli|forti|di forza|di debolezza)\b|\bin cosa (?:sono|vado) (?:bravo|brava|forte|debole|male|bene)\b|\bcosa (?:faccio|sto facendo) (?:bene|male)\b", "strengths"),
        (r"\bquanto (?:devo|dovrei|mi conviene) (?:mettere|tenere|accantonare) da parte (?:per le|per|di) (?:tasse|imposte|fisco)\b|\bquanto (?:accantono|accantonare) per (?:le )?tasse\b|\b(?:tasse|imposte)\b.{0,20}?\bquanto (?:mettere|tenere) da parte\b", "tax_set_aside"),
        (r"\bwhat (?:should|could|will|would|does) (?:the |our |my )?(?:shop|store|business) (?:look like|be|be like|be doing) in (?P<n>\d+|six|three|twelve|a) (?P<unit>months?|weeks?|year|years)\b|\bwhere (?:should|could|will) (?:we|the shop|the business) be in (?P<n2>\d+|six|three|twelve|a) (?P<unit2>months?|weeks?|year|years)\b|\b(?P<n3>\d+|six|three|twelve)[- ](?P<unit3>month|week|year) (?:plan|goal|target|vision|picture)\b|\btra (?P<n4>\d+|sei|tre|dodici) mesi\b", "horizon"),
        (r"\bwhat(?:'s| is) my hourly (?:rate|wage|pay|income)\b|\bhow much (?:do i|am i) (?:make|earn|making|earning) (?:an|per|by the) hour\b|\bper hour\b.{0,20}?\b(?:make|earn|worth)\b|\bwhat am i (?:earning|making) per hour\b|\bquanto guadagno all'?ora\b", "hourly_rate"),
        (r"\bhow (?:much time|many hours) (?:does|will|should) (?:the |running the |this )?(?:shop|store|business|it) (?:take|need|cost me|eat)\b|\bhow long (?:does|will|should) (?:the |running the |this )?(?:shop|store|business) (?:take|need)\b|\bhow (?:much time|many hours) (?:a|per) (?:day|week)\b.{0,20}?\b(?:shop|store|business|need|take)\b|\btime (?:the )?shop takes\b|\bquanto tempo (?:mi )?(?:porta|porta via|richiede|serve|ci vuole per|prende) (?:via )?(?:il |lo )?(?:negozio|shop)\b", "time_needed"),
        (r"\bcan (?:we|i) afford\b.{0,40}?(?:€|eur)?\s*(?P<amt>\d[\d.,]*)\s*(?:€|eur|euros?|k)?\b|\b(?:€|eur)?\s*(?P<amt2>\d[\d.,]*)\s*(?:€|eur|euros?)\b.{0,30}?\bcan (?:we|i) afford\b|\bpossiamo permetterci\b.{0,30}?(?P<amt3>\d[\d.,]*)|\bis (?:€|eur)?\s*(?P<amt4>\d[\d.,]*)\s*(?:€|eur|euros?)? (?:too much|ok|okay|reasonable|fine) to spend\b", "afford"),
        (r"\bwhat (?:if|happens if|would happen if) (?:the |our |my )?(?:supplier|fornitore|vendor|factory)\b.{0,20}?\b(?:raises?|increases?|ups|puts up|charges?|goes to|alza|aumenta)\b.{0,30}?\b(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\s+(?:cost|price|prezzo|costo)?\s*(?:to|at|by|a|di)\s*(?:€|eur)?\s*(?P<v>\d+(?:[.,]\d+)?)\s*(?:€|eur|euros?|%)?\b|\bwhat if (?:the )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?) (?:cost|price) (?:goes|went|rises|rose|jumps) to (?:€|eur)?\s*(?P<v2>\d+(?:[.,]\d+)?)\b", "cost_what_if"),
        (r"\bworst[- ]case\b|\bwhat(?:'s| is) the worst that (?:can|could) happen\b|\bif everything goes wrong\b|\bnel peggiore dei casi\b|\bhow bad (?:can|could) (?:it|this month|next month) (?:get|be)\b", "worst_case"),
        (r"\bwhat (?:did|have|are) (?:the )?(?:customers|buyers|people|clienti) (?:say|said|saying|write|written|writing|tell us|told us|ask)\b(?: this week| today| lately| recently| this month)?\W*$|\bcustomer feedback\b(?: this week)?\W*$|\bcosa (?:hanno detto|dicono) i clienti\b", "customers_said"),
        (r"\bhow (?:do|does) (?:we|the shop|the store|this shop|our shop|our numbers|it) (?:compare|stack up|measure up|rank|do) (?:to|against|with|vs\.?|versus|compared to) (?:other|similar|most|typical|average|the average) (?:small )?(?:shops?|stores?|sellers?|businesses|dropshippers|e-?commerce|negozi)\b|\bare we (?:normal|average|typical|behind|ahead|doing (?:better|worse) than (?:most|others|average))\b|\bhow (?:does|do) (?:this|our|the) (?:shop|store|numbers) compare\b|\bcome siamo (?:rispetto|messi rispetto) (?:agli altri|alla media)\b", "benchmark"),
        (r"\bwhat am i (?:good|bad|great|terrible|strong|weak) at\b|\bmy (?:strengths|weaknesses|strong points|weak points)\b|\bwhat (?:are|am) (?:i|we) (?:doing )?(?:well|right) and (?:what )?(?:badly|wrong|not)\b|\bwhere am i (?:strong|weak)\b|\bin cosa sono (?:bravo|brava|scarso|scarsa)\b", "strengths"),
        (r"\bwhat(?:'s| is) the (?:cheapest|fastest|quickest|easiest|simplest|best|surest|most reliable) way to (?:get|make|win|reach|add|find|land) (?:(?P<n>\d+|ten|twenty|five|a few|some|more|the next) )?(?:more |extra |new |additional )?(?:sales|orders|customers|buyers|clienti|vendite|ordini)\b|\bhow (?:do|can|could) (?:i|we) get (?P<n2>\d+|ten|twenty|five) (?:more |extra |new )?(?:sales|orders|customers)\b|\b(?P<n3>\d+) (?:more |extra )?(?:sales|orders) (?:this|by|in a|within a) (?:week|month|weekend)\b|\bcome (?:faccio a )?(?:fare|avere|trovare) (?:\d+ )?(?:altre |più )?(?:vendite|ordini)\b", "more_sales"),
        (r"\bshould (?:we|i) (?:do|run|have|join|plan|prepare) (?:a |the )?(?:black friday|cyber monday|christmas|xmas|natale|saldi|summer|january|spring|clearance|flash|weekend)\s*(?:sale|sales|promo|promotion|discount|offer|deal|sconti|offerta)?\b|\b(?:black friday|cyber monday|saldi)\b.{0,20}?\b(?:yes or no|worth it|good idea|should we|conviene|or not)\b|\bworth (?:doing|joining) (?:black friday|a sale|the sales)\b", "sale_or_not"),
        (r"\bwhat do you think (?:of|about) (?:the |our |my )?(?:shop|store|brand|business)?'?s? ?name\b|\bis (?:the |our |my )?(?:shop|store|brand)? ?name (?:good|ok|okay|bad|right|fine)\b|\b(?:rate|judge|opinion on) (?:the |our |my )?(?:shop|store|brand) name\b|\bche ne pensi del nome\b|\bthe name (?:green nest)\b.{0,20}?\b(?:good|ok|think|like)\b", "name_opinion"),
        (r"\b(?:am i|are we|is the shop|is it) ready (?:for|to open|to go|to launch|for launch|for the real|to go live|for real)\b|\bcan (?:we|i) (?:open|launch|go live|go real|start selling) (?:for real|now|yet|already|the real (?:shop|store))\b|\bwhat do (?:i|we) need (?:before|to) (?:open(?:ing)?|launch(?:ing)?|go(?:ing)? live|start(?:ing)?)(?: for real| the real (?:shop|store)| properly)?\b|\bready for the real (?:shop|store|thing)\b|\b(?:what'?s|anything) (?:still )?missing (?:before|for) (?:launch|opening|the real (?:shop|store))\b|\bsiamo pronti (?:per|ad) aprire\b|\bcosa (?:manca|serve) per aprire\b", "ready_real"),
        (r"\bhow long (?:have we been|has the shop been|have you been) (?:running|open|going|live|selling|at this|working)\b|\bsince when (?:is|has) the shop\b|\bhow many days (?:has the shop been|have we been|since we) (?:open|running|started|opened)\b|\bda quanto (?:siamo aperti|è aperto il negozio|andiamo avanti)\b|\bwhat day (?:is it|are we on) (?:for|in) the (?:shop|store|practice)\b", "running_since"),
        (r"\b(?:did|have) you (?:make|made) (?:any |some )?(?:mistakes?|errors?|blunders)\b|\bwhat did you (?:get wrong|do wrong|mess up|screw up|miss)\b(?: this week| today| lately)?|\byour (?:mistakes|errors|worst call)\b(?: this week| today)?|\bhave you been wrong\b|\bhai (?:fatto|commesso) (?:degli )?errori\b|\bwhere were you wrong\b", "my_mistakes"),
        (r"^\W*(?:show me|let me see|walk me through|spiegami|fammi vedere)\s+(?:the |your |i |la )?(?:maths?|math|calculation|calcolo|conti|numbers behind (?:it|that)|working|workings)\W*$|\bhow did you (?:get|calculate|compute|work out) (?:that|this|it|those numbers?|the number)\b|\bwhere does (?:that|this) (?:number|figure) come from\b", "show_maths"),
        (r"^\W*(?:hmm+,? |well,? |ok,? )?(?:not convinced|i'?m not convinced|not sure about that|i doubt (?:it|that)|i disagree|i don'?t (?:buy|think so|agree)|that doesn'?t (?:sound|seem|feel) right|non sono convint[oa]|non ci credo|mah)\W*$", "not_convinced"),
        (r"\b(?:i'?m|i am|im) (?:tired|sick|fed up|done|exhausted|frustrated|losing (?:hope|faith|motivation)|about to give up)\b|\bnothing (?:sells|is selling|works|is working)\b|\bthis (?:isn'?t|is not|doesn'?t) work(?:ing)?\b|\bi (?:want to|should|might|will) (?:give up|quit|stop|close (?:the )?shop)\b|\bwhat'?s the point\b|\bsono stanc[oa]\b|\bnon vende (?:niente|nulla)\b|\bmollo tutto\b", "discouraged"),
        (r"^\W*(?:be honest(?: with me)?|honestly\??|tell me the truth|straight answer|no sugar ?coating|don'?t sugar ?coat it|sii onest[oa]|dimmi la verità|give it to me straight)\W*$|\bbe honest\b.{0,20}?\b(?:shop|store|business|numbers|me)\b", "be_honest"),
        (r"\bwhat would you do differently\b|\bwhat should (?:i|we) (?:do|have done) differently\b|\bcosa faresti di diverso\b|\bdifferently (?:than|from|to) last (?:week|month)\b", "differently"),
        (r"^\W*(?:please |ok |so |right,? )?(?:stop|don'?t|do not|no more|quit|smetti di|basta)\s+(?:proposing|suggesting|asking (?:me )?(?:about|for)|nagging (?:me )?about|sending(?: me)?|with the|proporre|proporr?mi)\s+(?:the |those |these |any |me )?(?P<what>price|prices|pricing|price changes?|repric\w*|stock|restock\w*|reorders?|reordering|stock changes?|ship\w*|shipping reminders?|order reminders?|proposals?|suggestions?|everything|cambi di prezzo|prezzi|riordini|scorte)\b.{0,30}$", "mute_kind"),
        (r"^\W*(?:ok |please |from now on |you can |you may |go ahead and |just )?(?:send|answer|reply to|handle|do|deal with|take care of)\s+(?:the |all the |any )?(?:routine|simple|easy|standard|normal|tracking|basic|obvious|trivial)\s+(?:customer |client )?(?:replies|answers|messages|ones|questions|stuff|e-?mails|emails|customer (?:replies|messages))\b.{0,25}?(?:yourself|on your own|by yourself|alone|without (?:asking|me)|automatically|directly|da sol[oa]|from now on)\b|\byou (?:can|may) (?:send|answer|reply to) (?:the )?(?:routine|simple|easy) (?:ones|replies|messages|questions) (?:yourself|on your own|without me)\b|\brispondi (?:tu )?(?:da sol[oa]|direttamente) (?:a quelle|alle) (?:semplici|di routine)\b|\b(?:turn on|enable|switch on|activate) (?:the )?auto[- ]?(?:replies|reply|answers)\b", "auto_routine"),
        (r"^\W*(?:what|which)\s+(?:do|can|would|will)\s+you\s+(?:answer|reply to|send|handle)\s+(?:on your own|yourself|by yourself|alone|automatically|without me|without asking)\W*$|\bwhat (?:counts as|is|are) (?:a )?routine (?:reply|replies|message|messages|question|questions)\b|\bcosa rispondi da sol[oa]\b", "auto_scope"),
        (r"^\W*(?:which|what|how many|show me the|list the)\s+(?:replies|messages|answers|e-?mails)\s+(?:did you|have you|you)\s+(?:send|sent|answer|answered)\s+(?:yourself|on your own|by yourself|alone|automatically|without me)\b.{0,20}$|\bsent by you today\b|\bwhat did you (?:send|answer) (?:on your own|yourself|alone|automatically)\b|\bcosa hai (?:mandato|risposto) da sol[oa]\b", "auto_log"),
        (r"^\W*(?:stop|don'?t|do not|quit|smetti di|basta|no more)\s+(?:answering|replying to|sending|handling|answer|reply to|send)\s+(?:the |to )?(?:customers?|clients?|messages|replies|e-?mails|routine (?:replies|ones|messages))\s*(?:yourself|on your own|by yourself|alone|automatically|without me|without asking|da sol[oa])?\W*$|\b(?:turn off|disable|switch off) (?:the )?auto[- ]?(?:replies|reply|answers)\b", "auto_off"),
        (r"^\W*(?:ok,? |please |and |then |now )?(?:ask|check with|send|show) me (?:everything|all|every (?:reply|message|proposal|change)|the (?:routine|simple) ones)(?: again| from now on| too)?\W*$|\b(?:stop|don'?t) (?:sending|answering) (?:replies |messages |anything )?(?:yourself|on your own|alone|automatically)\b|\bback to (?:asking|approving) (?:me )?(?:everything|every(?:thing)?|all)\b|\bpropose (?:price|stock|ship\w*|everything|all)(?: changes)? again\b", "unmute"),
        (r"^\W*(?:ok,? |please |so |yes,? |good,? )?(?:fix (?:them|it|those|that|all of (?:it|them)|everything)|sort (?:them|it|that|those) out|handle (?:them|it|all of it|those)|deal with (?:them|it|those)|take care of (?:them|it|those)|do (?:them|those|all of it|it all)|go ahead with (?:them|those|all)|sistemali|sistema tutto|risolvi(?:li)?|occupatene)\W*$", "fix_them"),
        (r"\b(?:write|draft|prepare|scrivi|prepara)\b.{0,20}?\b(?:e-?mail|mail|message|newsletter|messaggio)\b.{0,30}?\b(?:past|previous|old|existing|former|earlier) (?:customers|buyers|clients|clienti)\b|\b(?:e-?mail|mail|message) to (?:our |my |the )?(?:past|previous|old|existing) (?:customers|buyers|clients)\b|\bwin-?back (?:e-?mail|mail)\b|\b(?:back in stock|new colou?r|restock) (?:e-?mail|mail|announcement)\b.{0,20}?\b(?:customers|buyers|write|draft)\b|\bmail ai vecchi clienti\b", "email_past_customers"),
        (r"\b(?:write|draft|prepare|scrivi|prepara)\b.{0,20}?\b(?:review|feedback|rating|recensione) (?:request|ask|asking)? ?(?:e-?mail|mail|message|template|messaggio)\b|\b(?:review|feedback) request\b|\be-?mail (?:asking|to ask) for (?:a )?(?:review|feedback)\b|\bmail per chiedere (?:una )?recensione\b", "email_review_request"),
        (r"\b(?:do you )?remember (?:what|when|that|the thing|anything) (?:i|we) (?:told|said|mentioned|wrote|decided|agreed)(?: to)? ?(?:you)?\b.{0,20}?\b(?:about|on|regarding|for|su|del|della|riguardo)\s+(?:the |our |my |il |la |lo )?(?P<topic>[a-zà-ú][a-zà-ú0-9 \-']{2,40}?)\W*$|\bwhat did i (?:tell|say to) you about (?:the |our |my )?(?P<topic2>[a-zà-ú][a-zà-ú0-9 \-']{2,40}?)\W*$|\bti ricordi (?:cosa|quello che) (?:ti )?(?:ho detto|avevo detto|abbiamo detto) (?:su|del|della|sul|sulla|riguardo a?l?)\s+(?P<topic3>[a-zà-ú][a-zà-ú0-9 \-']{2,40}?)\W*$", "remember_topic"),
        (r"\b(?:what(?:'s| is) )?(?:the )?(?:most important|key|one|single most important|number one|main|first) (?:number|metric|figure|kpi|stat|thing to watch|thing to track|indicator)s?\b.{0,25}?\b(?:to )?(?:watch|track|look at|follow|check|care about|matter|matters)\b|\bwhich (?:number|metric|kpi) (?:matters|counts) (?:the )?most\b|\bwhat should i (?:watch|track|look at) (?:every day|daily|most|first)\b|\bil numero più importante\b|\bquale metrica\b", "key_number"),
        (r"\bhow much (?:did|have) we (?:lose|lost|pay|paid|spend|spent)\b.{0,20}?\b(?:on |in |to |for |because of )?(?:refunds?|returns?|cancellations?|cancelled orders|resi|rimborsi)\b|\b(?:refunds?|returns?|cancellations?) (?:cost|cost us|lost us|total|totale)\b|\bmoney (?:lost|spent) on (?:refunds?|returns?)\b|\bquanto (?:abbiamo perso|ci sono costati) (?:con |per |in )?(?:i )?(?:resi|rimborsi)\b", "refund_losses"),
        (r"\b(?:customer|client|buyer|someone|cliente|he|she|they) (?:paid|was charged|got charged|has been charged|were charged|was billed|ha pagato|è stato addebitato)\s+(?:twice|two times|double|2 times|2x|due volte|doppio)\b|\b(?:double|duplicate) (?:payment|charge|order|pagamento|addebito)\b|\bcharged (?:them|him|her) twice\b|\btwo (?:payments|charges) for (?:one|the same) order\b", "paid_twice"),
        (r"^\W*(?:give me|i need|can i have|i could use|dammi|ho bisogno di)\s+(?:a |some |un |una )?(?:pep ?talk|motivation|encouragement|boost|kick|push|good news|reason to (?:keep going|continue|go on)|motivazione|incoraggiamento|carica)\W*$|\b(?:motivate|encourage|cheer) me( up)?\b|\btell me (?:something good|it'?s going to be (?:ok|fine|alright)|we'?ll make it)\b|\bcheer me up\b|\bincoraggiami\b", "pep_talk"),
        (r"^\W*(?:are you sure(?: about (?:that|this|it))?|sure\??|really\??|(?:is|are) (?:that|those|these) (?:right|correct|true|real)|sei sicur[oa]|davvero)\W*$|\bhow do you know (?:that|this)\b|\bwhere (?:did you get|does) (?:that|this) (?:number|figure)? ?(?:come )?from\b", "are_you_sure"),
        (r"\b(?:best[- ]selling|top|most popular|best) (?:product|item|seller)\b.{0,20}?\b(?:and )?why\b|\bwhy (?:does|is) (?:the |our )?(?:\w+ ){0,3}(?:sell|selling) (?:so )?(?:well|best|most)\b|\bwhy is (?:it|that) (?:the|our) best[- ]?seller\b|\bperch[ée] (?:si )?vende", "best_why"),
        (r"\b(?:how long|when) (?:until|till|before|do) (?:we|i) ?(?:break even|breakeven|reach break[- ]even|get (?:the|our) money back|recover (?:the|our) (?:investment|money|start-?up costs?))\b|\bbreak[- ]?even\b.{0,20}?\b(?:when|how long|point)\b|\bquando (?:andiamo in pari|rientriamo)\b|\bhave we (?:broken even|made (?:the|our) money back)\b", "break_even"),
        (r"\bhow many (?:orders|sales|customers|visits|visitors) (?:do|would|will) (?:we|i) need\b.{0,30}?(?:€|eur|euros?)?\s*(?P<amt>\d[\d.,]*)\s*(?:€|eur|euros?|k)?\b.{0,20}?\b(?:a|per|in a|each|every) (?P<per>month|week|day|year)\b|\b(?:to make|for|to earn|to reach|to hit) (?:€|eur)?\s*(?P<amt2>\d[\d.,]*)\s*(?:€|eur|euros?|k)?\s*(?:a|per|in a|each|every) (?P<per2>month|week|day|year)\b.{0,30}?\bhow many (?:orders|sales|customers)\b|\bquanti ordini (?:servono|ci vogliono)\b.{0,20}?(?P<amt3>\d[\d.,]*)", "orders_needed"),
        (r"^\W*(?:is )?(?:anything|something|nothing)? ?(?:urgent|on fire|burning|critical)(?: today| right now| now)?\W*$|\bis (?:anything|something|there anything) (?:urgent|on fire|critical|pressing)\b|\bany (?:emergencies|fires|urgent (?:things|stuff|matters))\b|\bc'?[èe] qualcosa di urgente\b", "urgent"),
        (r"\b(?:did|has) (?:anyone|anybody|someone|any customer|a customer) complain\w*\b|\bany (?:complaints?|unhappy customers?|angry customers?|bad (?:reviews?|feedback))\b(?: (?:today|this week|lately|recently))?|\b(?:who|anyone) (?:is|was) unhappy\b|\bqualcuno si [èe] lamentato\b|\breclami\b", "complaints"),
        (r"\bwhat would you do with (?:€|eur)?\s*(?P<amt>\d[\d.,]*)\s*(?:€|eur|euros?|k)?\b|\bif (?:i|you) had (?:€|eur)?\s*(?P<amt2>\d[\d.,]*)\s*(?:€|eur|euros?)?\b.{0,30}?\b(?:spend|do|invest|put)\b|\b(?:how|where) (?:should|would) (?:i|we|you) (?:spend|invest|put) (?:€|eur)?\s*(?P<amt3>\d[\d.,]*)\s*(?:€|eur|euros?)?\b|\bcosa faresti con (?:€ ?)?(?P<amt4>\d[\d.,]*)", "spend_budget"),
        (r"\bhow (?:do|can|could|should) (?:i|we) get (?:more |some |our first )?(?:reviews|ratings|testimonials|stars)\b|\bmore reviews\b|\bcome (?:ottengo|avere) (?:più )?recensioni\b|\bask(?:ing)? for reviews\b", "reviews"),
        (r"\b(?:give me|one|an?|any|quick|your best) (?:idea|tip|trick|thing|suggestion)s?\b.{0,25}?\b(?:to )?(?:sell|selling|get) more\b|\bhow (?:do|can|could) (?:i|we) sell more\b(?: this week| today)?|\bidea (?:to|for) (?:more )?(?:sales|selling)\b|\bboost sales\b|\bun'?idea per vendere di più\b|\bone idea\b", "one_idea"),
        (r"\bwhat (?:mistakes?|errors?) (?:did|have) (?:i|we) (?:make|made)\b|\bwhat did (?:i|we) (?:do wrong|get wrong|mess up|screw up)\b|\bmy (?:mistakes|errors) this week\b|\bche errori ho fatto\b|\bcosa ho sbagliato\b", "mistakes"),
        (r"\bwhat do (?:customers|buyers|people|clients|clienti) ask (?:the )?most\b|\bmost (?:common|frequent) (?:customer )?(?:questions?|messages?|requests?)\b|\bwhat (?:are|do) (?:customers|people) (?:asking|writing) (?:about|us|me)?\b|\bcosa chiedono (?:di più|più spesso) i clienti\b", "asked_most"),
        (r"\bwhy (?:did|have|are|is) (?:the )?(?:sales|orders|revenue|visits|traffic|conversion)s? (?:drop|dropped|fall|fallen|down|going down|dropping|falling|lower|slowed|slow)\b|\bwhy (?:did|have) we sell less\b|\bwhat happened to (?:the )?sales\b|\bperch[ée] (?:sono )?(?:calate|scese) le vendite\b|\bsales (?:are )?down\b", "sales_drop"),
        (r"\b(?:are|aren'?t) (?:the |our |my )?prices? too (?:high|low|expensive|cheap)\b|\b(?:am i|are we) (?:too )?(?:expensive|cheap|overpriced|underpriced)\b|\bis (?:the |our )?(?:pricing|price) (?:right|ok|okay|wrong)\b|\b(?:i )?prezzi (?:sono )?troppo (?:alti|bassi)\b", "prices_right"),
        (r"\bwhat(?:'s| is|’s) your (?:goal|aim|objective|target|mission)\b.{0,20}?\b(?:shop|store|business|us|here|me)\b|\bwhat are you (?:trying to (?:do|achieve)|aiming (?:at|for)|optimi[sz]ing for)\b|\bwhat do you want (?:for|from) (?:the|this|our) (?:shop|store|business)\b|\bqual è il tuo obiettivo\b", "my_goal"),
        (r"^\W*(?:what are you (?:doing|up to|working on)(?: right now| now| at the moment)?|what(?:'s| is) (?:going on|happening)(?: right now| now)?|are you busy|cosa stai facendo|che fai(?: adesso)?)\W*$", "doing_now"),
        (r"\bwhy did you (?:propose|suggest|want to|recommend|prepare)\b(?P<what>.{3,80})|\bwhy (?:the|that|this) (?:proposal|suggestion|change)\b|\bperché hai proposto\b(?P<what2>.{3,80})", "why_proposal"),
        (r"\bwhat (?:happens|will happen|if) (?:if )?i (?:ignore|don't (?:answer|tap|approve|look at)|skip|leave) (?:the |your )?(?:proposals?|suggestions?|buttons?|questions?)\b|\bcan i ignore (?:the |your )?proposals\b", "ignore_proposals"),
        (r"\bwhat would you (?:change|improve|fix|do differently)\b.{0,30}?\b(?:shop|store|business|site|negozio|catalogue|catalog)\b|\bcosa cambieresti\b|\bwhat(?:'s| is) (?:wrong|broken|weak|missing) (?:with|in|about) (?:the |our |my )?(?:shop|store|business)\b|\bwhat are we doing wrong\b|\bwhere are we (?:weak|losing)\b", "what_change"),
        (r"\bif you were me\b|\bwhat would you do (?:first|today|now|in my (?:place|shoes))\b|\bwhat should i do first\b|\bal posto mio\b|\bwhat(?:'s| is) the (?:first|one) thing (?:i should|to) (?:do|fix)\b", "do_first"),
        (r"\b(?:biggest|main|real|top) (?:risk|danger|threat|problem|worry)s?\b.{0,20}?\b(?:for us|right now|now|for the shop|we have|today)\b|\bwhat (?:worries|scares) you\b|\bwhat could go wrong\b|\bqual è il rischio\b", "biggest_risk"),
        (r"\bwhat do you need from me\b|\bwhat do you need me (?:to do|for)\b|\bdo you need (?:anything|something) from me\b|\banything you need\b|\bdi cosa hai bisogno\b|\bcosa ti serve\b", "need_from_owner"),
        (r"\bexplain (?:the |our |these )?(?:numbers|figures|profit|report|results|margin|p&l|stats)\b.{0,30}?\b(?:like i'?m (?:5|five|a child|stupid|new)|simply|simple|in plain (?:words|english)|for dummies|slowly)\b|\b(?:numbers|figures) (?:in plain|simply|simple)\b|\bspiegami i numeri\b|\bi don'?t understand (?:the |these )?numbers\b", "eli5"),
        (r"\b(?:is|are) (?P<pct>\d+(?:[.,]\d+)?)\s*%?\s*(?:percent )?conversion (?:rate )?(?:good|bad|ok|okay|normal|fine|high|low|enough)\b|\bconversion (?:rate )?(?:of )?(?P<pct2>\d+(?:[.,]\d+)?)\s*%?\s*(?:—|-|,)?\s*(?:is that )?(?:good|bad|ok|normal|fine)\b", "conv_good"),
        (r"\bhow much (?:should|do) i (?:put|set|keep|save) (?:aside|away|apart)\b.{0,20}?\b(?:tax|taxes|tasse|the taxman|vat|iva|inps)\b|\bset aside for tax", "tax_aside"),
        (r"\bshould (?:i|we) hire\b|\bdo (?:i|we) need (?:an? )?(?:employee|assistant|help|someone|va|virtual assistant)\b|\bhire (?:someone|a person|help|an assistant)\b|\bassumere\b|\bdevo assumere\b", "hire"),
        (r"\bwhat (?:can|could|will|do) you do (?:for (?:the |my |our )?(?:shop|store|business)|today|tomorrow|this week)\b.{0,20}?\b(?:without me|alone|on your own|by yourself|while i'?m (?:away|out|at work))\b|\bwhat (?:can|could) you do (?:alone|on your own|by yourself|without me)\b|\bcosa (?:puoi|riesci a) fare da sol[oa]\b", "alone_today"),
        (r"\bcan you (?:handle|run|manage|look after|take care of|mind) (?:the |my |our )?(?:shop|store|business|everything)\b.{0,20}?\b(?:alone|by yourself|on your own|without me|for a (?:day|week|month)|while i'?m (?:away|on holiday|out))\b|\bcan i leave (?:the |you )?(?:shop|store)? ?(?:to|with) you\b|\bpuoi gestire (?:il |lo )?(?:negozio|shop) da sol[oa]\b", "handle_alone"),
        (r"\bhow do you (?:decide|choose|know|pick) (?:what|how) (?:to (?:answer|reply|say|write)|you (?:answer|reply))\b.{0,20}?\b(?:customers?|clienti|messages?|e-?mails?)\b|\bhow do you (?:answer|reply to|handle) (?:customers?|customer messages?|the inbox)\b|\bcome rispondi ai clienti\b", "how_answer"),
        (r"\bwhat do you do (?:when|if) (?:a )?customer (?:is|gets) (?:angry|rude|upset|furious|mad|aggressive)\b|\b(?:angry|rude|upset|furious) customers?\b.{0,20}?\b(?:what do you do|how do you|your approach)\b|\bcliente arrabbiato\b", "angry_customer"),
        (r"\bwhat do you know about (?:our|my|the) (?:customers|buyers|clients|clienti)\b|\bwho (?:are|is) (?:our|my) (?:customers|buyers|typical customer|audience)\b|\bwho buys from us\b|\bchi sono i nostri clienti\b", "know_customers"),
        (r"\bwhich (?:countries|markets|country|market) (?:should|could) we (?:sell|ship|open|go|expand) (?:to|in)? ?(?:next|now|first)?\b|\bwhere (?:should|could) we (?:expand|sell next|ship next)\b|\bnext (?:country|market) to (?:open|sell)\b|\bin quali paesi\b", "next_countries"),
        (r"\bwhat(?:'s| is) the plan for (?:next|this) (?:week|month)\b|\bplan for (?:next|this) week\b|\bwhat(?:'s| are) (?:we|you) (?:doing|going to do) (?:next|this) week\b|\bpiano per (?:la )?(?:prossima |questa )?settimana\b|\bnext week'?s plan\b", "week_plan"),
        (r"\b(?:summari[sz]e|sum up|recap|riassumi|riepiloga)\b.{0,15}?\b(?:the )?(?:last|past) (?P<n>\d+) days?\b|\b(?:last|past) (?P<n2>\d+) days? (?:in|summary|recap)\b|\bsummari[sz]e (?:the |this |last )?week\b", "summarize_days"),
        (r"\bhow (?:confident|sure|certain) are you\b|\bcan i trust (?:the |these |your )?(?:numbers|figures|data|report)\b|\bare (?:the |these |your )?numbers (?:right|correct|real|reliable|accurate)\b|\bquanto sei sicur[oa]\b", "confidence"),
        (r"\bwhat would a (?:good|great|normal|realistic|bad) (?:month|week|year|day) look like\b|\bwhat(?:'s| is) a (?:good|realistic) (?:month|week|target|goal)\b|\bwhat should we aim for\b|\bcosa sarebbe un buon mese\b", "good_month"),
        (r"\bwe (?:made|earned|took|did|sold|turned over)\s+(?:€|eur|euro)?\s*(?P<amt>\d+(?:[.,]\d+)?)\s*(?:€|eur|euros?|k)?\s+(?:this|last|in a|per|a|in one|of profit this|profit this|of sales this|in sales this)?\s*(?P<per>week|month|day|today|yesterday|settimana|mese)\b.{0,20}?\b(?:good|bad|ok|okay|normal|fine|enough|well|poor|decent|bene|buono)\b|\b(?:is|are)\s+(?:€|eur)?\s*(?P<amt2>\d+(?:[.,]\d+)?)\s*(?:€|eur|euros?)?\s+(?:a|per|in a|of profit a|of sales a)\s+(?P<per2>week|month|day)\s+(?:good|bad|ok|okay|normal|fine|enough|decent)\b", "is_amount_good"),
        (r"\b(?:how much|what) (?:would|could|will|do) we (?:make|earn|get|have|sell)\b.{0,30}?\b(?:if (?:we|i) )?(?:double|doubled|triple|tripled|halve|halved|10x|twice|two times|three times|\d+ ?x|\+\s*\d+ ?%|\d+ ?% more)\b.{0,15}?\b(?:traffic|visitors|visits|conversion|prices?|orders|sales|the shop)\b|\bif (?:we|i) (?:double|doubled|triple|tripled)\b.{0,15}?\b(?:traffic|visitors|visits|conversion|orders)\b.{0,30}?\b(?:how much|what|profit|make|earn)\b|\bdoubl(?:e|ing) (?:the )?(?:traffic|visitors|visits)\b", "what_if_traffic"),
        (r"\bwhat did you learn (?:this week|today|lately|recently|so far|from (?:the|your) (?:last )?jobs?)\b|\bwhat have you learn(?:ed|t)\b|\bcosa hai imparato\b|\banything (?:new )?you learn(?:ed|t)\b", "learned"),
    ]

    JOB_WORDS = re.compile(r"https?://|\b(research|compare|look up|write me a (?:doc|document|report)|document about)\b", re.I)

    FOLLOW_PRODUCT = re.compile(r"^\W*(?:and|what about|how about|same for|e|e per|and for|and the|now the|ok and)\s+(?:the |for the |il |la |lo )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\W*$", re.I)
    FOLLOW_WHY = re.compile(r"^\W*(?:why|why so|why that|why not|how come|perch[ée]|come mai|because\?|explain|explain why|reason\?)\W*$", re.I)
    FOLLOW_ELSE = re.compile(r"^\W*(?:what else|anything else|and then|next|another one|one more|more|other ideas?|altro|e poi|un'?altra|and\?|go on|continue)\W*$", re.I)
    FOLLOW_DO = re.compile(r"^\W*(?:ok|okay|yes|yep|sure|fine|alright|va bene|sì|si|ok then|good|great|perfect)?[\s,]*(?:do it|do that|go ahead|go for it|make it so|let'?s do (?:it|that)|please do|yes please|do the first one|start with that|fallo|procedi|vai)\W*$", re.I)
    FOLLOW_EXPENSIVE = re.compile(r"^\W*(?:that'?s|that is|it'?s|this is|too|sounds|seems)?\s*(?:too |way too |a bit |very )?(?:expensive|much|much money|pricey|dear|costly|a lot|caro|troppo|troppi soldi)\b.{0,30}$|\bi (?:can'?t|cannot|don'?t want to) (?:afford|spend) (?:that|this|so much|that much)\b|\bcheaper (?:version|option|way)\??\W*$", re.I)
    FOLLOW_NOTIME = re.compile(r"^\W*(?:i )?(?:don'?t|do not|haven'?t got|have no|no)\s+(?:have )?(?:the )?time(?: for (?:that|this|it|all that|all of it))?\b.{0,20}$|^\W*(?:too long|too much work|that'?s a lot of work|no time|non ho tempo|shorter\??|tl;?dr|quicker version\??|make it (?:short|shorter|quick))\W*$", re.I)

    @classmethod
    def _rule(cls, name):
        return next(p for p, n in cls.RULES if n == name)

    def followup(self, t):
        """Short reactions that only make sense after my last answer: 'and the mug?', 'why?', 'what else?', 'ok do it', 'too expensive', 'no time'."""
        try:
            last = self.last_reply()
        except Exception:
            last = None
        if not last or not isinstance(last, tuple) or not last[1]:
            return None
        q, a = last
        a = str(a)
        m = self.FOLLOW_PRODUCT.match(t)
        if m and self.store is not None:
            p_new = self.store.find_product(m.group("what"))
            p_old = self.store.find_product(q) if q else None
            if p_new and p_old and p_new["id"] != p_old["id"]:
                words = [w for w in re.findall(r"[a-z0-9]{3,}", p_old["name"].lower()) if w not in ("set", "pcs", "with")]
                newq = q
                for w in sorted(words, key=len, reverse=True):
                    newq = re.sub(r"\b" + re.escape(w) + r"s?\b", p_new["name"].split(" (")[0].lower(), newq, count=1, flags=re.I)
                    if newq != q:
                        break
                if newq != q:
                    return {"redo": newq, "text": f"Same question for the {p_new['name'].split(' (')[0]}:"}
        if self.FOLLOW_WHY.match(t):
            props = [p for p in reversed(self.store.data.get("proposals", []))] if self.store is not None else []
            if a.startswith("🏪") or "Apply it?" in a or "Do it?" in a:
                if props:
                    return self.why_proposal(t, re.match(r"(?P<what>.*)", props[0]["why"][:0]))
            pure_numbers = bool(re.match(r"^(?:Yes|Not yet|No sales yet) — Profit|^Profit |^Sold today|^Orders |^Visitors |^Average order|^Stock:|^Most money|^Return/refund rate|^Last \d+ days|^Practice store —", a))
            if pure_numbers:
                return self.show_maths(t, None)
            sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n", a) if x.strip()]
            reasons = [x for x in sents if re.search(r"\b(because|since|so |so that|that'?s where|that'?s why|means|the reason)\b|—", x) and not x.startswith(("Say ", "say “"))]
            if reasons:
                return "Why: " + " ".join(reasons[:2])[:500] + ("\nIf you want the numbers behind it, say “show me the maths”." if re.search(r"€|%", a) else "")
            return "Short version of my reasoning: " + " ".join(sents[:2])[:400] + "\nAsk about any one part and I'll go deeper."
        if self.FOLLOW_ELSE.match(t):
            if a.startswith("One idea for this week:"):
                self._idea_offset = getattr(self, "_idea_offset", 0) + 1
                return self.one_idea(t, None)
            if "What I'd change, in order:" in a:
                facts = self._facts()
                rest = [f for f in facts if f[0] != "good"][5:]
                if rest:
                    return "Further down the list: " + "; ".join(f[1] for f in rest[:3]) + "."
                return "That was the whole list from the numbers. Beyond the numbers: photos in real rooms, one short video a day, and a card in every parcel — the three things every small shop under-does."
            if re.search(r"^\d+\. ", a, re.M):
                return "That was the full list. If you want, I turn it into to-dos (“add them to my list”) or pick the first one and start (“do the first one”)."
            return "Nothing else on that from me — ask the next thing, or “what's the plan for next week?” for the bigger picture."
        if self.FOLLOW_DO.match(t):
            cmds = re.findall(r"[“\"]([^”\"]{4,80})[”\"]", a)
            cmds = [c for c in cmds if re.match(r"^(?:say |)?(?:[a-z])", c, re.I) and not re.search(r"\bsorry\b|\bthank you\b|^i |^we |^you |^the one|^still using|^\d", c, re.I) and "?" not in c or re.match(r"^(what|which|how|why|should)\b", c, re.I)]
            cmds = [re.sub(r"^say\s+", "", c, flags=re.I) for c in cmds]
            cmds = [c for c in cmds if not re.match(r"^(what|which|how|why|should|is|are|did|do)\b", c, re.I)] or []
            if cmds:
                return {"redo": cmds[0], "text": f"Doing it: “{cmds[0]}” →"}
            return "Which part? Name it in a few words (or repeat the line in quotes) and I start."
        if self.FOLLOW_EXPENSIVE.match(t):
            amts = [_num(x) for x in re.findall(r"€ ?(\d[\d.]*,\d{2}|\d[\d.]*)", a)]
            big = max(amts) if amts else None
            if re.search(r"\byour money\b.*\bready to send\b", a) and self.store is not None:
                mm = re.search(r"“(\d+) × ([^”]+?) at", a)
                if mm:
                    p = self.store.find_product(mm.group(2)); n = max(5, int(mm.group(1)) // 2)
                    if p:
                        return f"Fair — half of it then: {n} × {p['name'].split(' (')[0]} = {_eur(n * p.get('cost', 0))}, enough for a few weeks, and reorder again from the sales. Smaller batches cost a bit more per unit but never leave you with dead stock. Say “order {n} more {p['name'].split(' (')[0].lower()}” and I write the line."
            if re.search(r"\bads?\b", a.lower()):
                return "Then no ads yet — that's the right call at this size. The free version: one 20-second video a day for 14 days, same product, posted at 12:00 and 19:00; it costs time, not money, and teaches you the same thing an ad would (which hook people stop for). If you want to test paid at all: € 3 a day for 7 days (€ 21) is the smallest experiment that still says something."
            if big:
                return (f"Understood — {_eur(big)} is too much right now. The cheaper version: start with about {_eur(big / 2)} " +
                        "and do half the plan (the first items, they carry most of the effect), then decide the rest from the results. What I'd cut first: anything that's 'nice' rather than 'stops a loss' — stock-outs and unanswered customers cost money today; cards and ads can wait a week.")
            return "Fair. Cheapest route: do only the part that stops a loss (late orders, stock-outs, unanswered customers) and skip the rest for now — say “what's urgent?” and I list just those."
        if self.FOLLOW_NOTIME.match(t):
            cmds = re.findall(r"[“\"]([^”\"]{4,80})[”\"]", a)
            cmds = [re.sub(r"^say\s+", "", c, flags=re.I) for c in cmds if not re.match(r"^(what|which|how|why|should|is|are|did|do|i |we |you )", c, re.I)]
            first = cmds[0] if cmds else None
            try:
                self.memory.add("Come back to: " + (q[:80] if q else "the last suggestion")) if self.memory else None
            except Exception:
                pass
            return ("Fair — the 2-minute version: I do the preparing, you tap. " + (f"I'll start with “{first}” and put it in front of you as a proposal; the rest" if first else "I've parked it") +
                    " on your to-do list under “Come back to” for a calmer day. Nothing else is needed from you today.")
        return None

    def reply(self, t):
        low = t.lower().strip()
        if self.JOB_WORDS.search(low) and not re.search(self._rule("benchmark"), low, re.I):     # 'how do we compare to other small shops' is a ledger question, not a job
            return None
        fu = self.followup(t)
        if fu:
            return fu
        for pat, name in self.RULES:
            m = re.search(pat, low, re.I)
            if m:
                try:
                    r = getattr(self, name)(t, m)
                except Exception:
                    r = None
                if r:
                    return r
        return None

    # ---- owner preferences read by core ----
    def muted(self):
        try:
            return tuple(self.memory.pref("mute_proposals", []) or []) if self.memory else ()
        except Exception:
            return ()

    def auto_ok(self, kind, checks):
        """May this customer reply go out without a tap? Only if the owner said 'send routine replies yourself' and the kind is routine and clean."""
        try:
            if not (self.memory and self.memory.pref("auto_routine")):
                return False
        except Exception:
            return False
        return kind in ("where_is_my_order", "product_question", "compliment") and not checks

    # ---- helpers --------------------------------------------------------------------------------
    def _n(self):
        try:
            return self.store.numbers()
        except Exception:
            return None

    def _paid(self, days=None):
        try:
            day = self.store.data.get("day", 0)
            return [o for o in self.store.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and (days is None or o.get("day", 0) > day - days)]
        except Exception:
            return []

    def _facts(self):
        """The shop's state as short facts, each tagged good/bad/neutral — reused by several answers."""
        st = self.store
        out = []
        if st is None:
            return out
        n = self._n() or {}
        day = st.data.get("day", 0)
        paid = self._paid()
        oos = [p for p in st.products() if p["stock"] == 0]
        low = [p for p in st.products() if 0 < p["stock"] <= 3]
        late = [o for o in st.data["orders"] if o["status"] == "paid" and day - o.get("day", day) >= 1]
        open_ = [o for o in st.data["orders"] if o["status"] == "paid"]
        props = [p for p in st.data.get("proposals", []) if p["status"] == "open"]
        new = []
        try:
            new = self.inbox.items("new") if self.inbox is not None else []
        except Exception:
            pass
        units = n.get("units", {})
        if oos:
            out.append(("bad", "sold out: " + ", ".join(p["name"].split(" (")[0] for p in oos) + " — every visitor who wanted one leaves", "restock"))
        if late:
            out.append(("bad", f"{len(late)} paid order(s) waiting longer than the promised next-day shipping", "ship"))
        elif open_:
            out.append(("neutral", f"{len(open_)} order(s) to ship today", "ship"))
        if new:
            out.append(("bad", f"{len(new)} customer message(s) unanswered", "inbox"))
        if low:
            out.append(("neutral", "low stock: " + ", ".join(f"{p['name'].split(' (')[0]} ({p['stock']})" for p in low), "reorder"))
        if props:
            out.append(("neutral", f"{len(props)} proposal(s) waiting for your tap", "proposals"))
        if paid:
            rev = n.get("revenue", 0)
            margin = n.get("profit", 0) / rev * 100 if rev else 0
            out.append(("good" if margin >= 40 else "bad", f"net margin {margin:.0f} % after goods, shipping and fees" + ("" if margin >= 40 else " — thin"), "margin"))
            conv = n.get("conversion", 0)
            out.append(("good" if conv >= 1.5 else "bad", f"conversion {conv:.1f} % ({len(paid)} orders from {n.get('visits', 0)} visits)" + ("" if conv >= 1.5 else " — under the 1.5–3 % a small shop should see"), "conversion"))
            if len(units) >= 2:
                top = max(units.values()); share = top / sum(units.values())
                if share > 0.6:
                    out.append(("bad", f"one product is {share * 100:.0f} % of sales — a supplier hiccup stops the shop", "diversify"))
            emails = {}
            for o in paid:
                k = (o.get("customer") or {}).get("email") or str(o["n"])
                emails[k] = emails.get(k, 0) + 1
            rep = sum(1 for v in emails.values() if v > 1)
            if len(paid) >= 8:
                out.append(("bad" if not rep else "good", (f"no repeat buyers yet (0 of {len(emails)} customers) — nothing brings people back (no card in the parcel, no e-mail after 3 weeks)" if not rep else f"{rep} repeat buyer(s) out of {len(emails)} customers"), "repeat"))
        else:
            out.append(("neutral", "no sales yet — the shop hasn't had a practice day", "run"))
        return out

    # ---- answers --------------------------------------------------------------------------------
    def doing_now(self, t, m):
        busy = None
        try:
            busy = self.busy_text()
        except Exception:
            pass
        if self.mind is not None and self.mind.job:
            return self.mind.status_line()
        if busy:
            return f"Right now: {busy}. Nothing else in the queue — ask me anything, quick things I answer alongside."
        bits = ["Nothing running — I'm waiting for you"]
        try:
            n = len(self.inbox.items("new")) if self.inbox is not None else 0
            if n:
                bits.append(f"{n} customer message(s) have drafts waiting for your tap")
        except Exception:
            pass
        try:
            props = [p for p in self.store.data.get("proposals", []) if p["status"] == "open"]
            if props:
                bits.append(f"{len(props)} store proposal(s) waiting")
        except Exception:
            pass
        try:
            items = self.memory.open_items() if self.memory else []
            if items:
                bits.append(f"{len(items)} thing(s) on your to-do list")
        except Exception:
            pass
        if self.pace is not None and getattr(self.pace, "has_quiet_time", lambda: False)():
            bits.append("you said you're away, so between checks I read and self-train")
        return "; ".join(bits) + ". Say the word and I start something."

    def why_proposal(self, t, m):
        st = self.store
        if st is None:
            return None
        what = ((m.groupdict().get("what") or m.groupdict().get("what2") or "") if m is not None and hasattr(m, "groupdict") else "").strip(" ?.")
        props = list(reversed(st.data.get("proposals", [])))
        if not props:
            return "I haven't proposed anything for the shop yet — when I do, each proposal carries its reason and you see it before you tap."
        p = None
        prod = st.find_product(what) if what else None
        kind = ("price" if re.search(r"\b(price|lower|raise|cheaper|dearer|prezzo)\b", what) else "stock" if re.search(r"\b(stock|restock|reorder)\b", what) else
                "ship" if re.search(r"\b(ship|spedire)\b", what) else "refund" if "refund" in what else "cancel" if "cancel" in what else None)
        for x in props:
            if prod and str(x.get("target")) == prod["id"] and (kind is None or x["kind"] == kind):
                p = x; break
        if p is None:
            for x in props:
                if kind and x["kind"] == kind:
                    p = x; break
        if p is None:
            p = props[0]
        name = (st.product(p["target"]) or {}).get("name") if p["kind"] in ("price", "stock", "cost", "description") else f"order #{p['target']}" if p["kind"] in ("ship", "refund", "cancel") else p["target"]
        status = {"open": "still waiting for your tap", "applied": "you applied it", "rejected": "you said no"}.get(p["status"], p["status"])
        extra = ""
        if p["kind"] == "price" and st.product(p["target"]):
            pr = st.product(p["target"])
            cost = pr.get("cost", 0)
            try:
                new = float(p["change"])
                extra = (f" The maths: at {_eur(new)} the margin is {(new - cost - 0.029 * new - 0.30) / new * 100:.0f} % after fees vs {(pr['price'] - cost - 0.029 * pr['price'] - 0.30) / pr['price'] * 100:.0f} % at {_eur(pr['price'])}"
                         + (" — I only trade margin when the numbers say conversion is the problem." if new < pr["price"] else " — more per sale, and a ,90 ending keeps it looking cheap."))
            except Exception:
                pass
        return (f"That proposal ({p['kind']} · {name} → {p['change'] if p['kind'] not in ('product', 'page') else '…'}), {p['t'][:10]} — my reason at the time: “{p['why']}”. Status: {status}." + extra +
                "\nIf the reason doesn't convince you, say no — I learn from the answer (I keep a note of which kinds you accept).")

    def ignore_proposals(self, t, m):
        st = self.store
        props = [p for p in st.data.get("proposals", []) if p["status"] == "open"] if st is not None else []
        return ("Nothing breaks — a proposal is a suggestion, the shop never changes without your tap. What happens by kind:\n"
                "• price / stock / page changes: stay as they are; the shop keeps selling at the old numbers.\n"
                "• 'mark shipped': the order stays 'paid' — after a day I count it as late and it shows in your check-ins; the customer is the one who feels it.\n"
                "• refunds / cancellations: the customer keeps waiting, which is the one thing that turns into a chargeback or a 1-star review — those I nag you about.\n"
                "• customer reply drafts: nothing is sent; the inbox counts them as unanswered.\n"
                + (f"Right now {len(props)} are open: " + "; ".join(f"{p['kind']} {p['target']}" for p in props[:4]) + ". " if props else "Right now nothing is open. ")
                + "If you'd rather I stopped asking about a kind of thing, tell me (“don't propose price changes”) and I keep to it.")

    def what_change(self, t, m):
        facts = self._facts()
        bad = [f for f in facts if f[0] == "bad"]
        neutral = [f for f in facts if f[0] == "neutral"]
        if not facts or (len(facts) == 1 and facts[0][2] == "run"):
            return ("Too early for a verdict — no sales yet. What I'd change before the first customer: real product photos (not supplier ones), a 'ships from Bergamo in 1 day' line on every product, "
                    "and a free-shipping threshold just above the average basket. Then run practice days and ask me again.")
        fixes = {"restock": "restock (say “what do I need to reorder?”)", "ship": "ship what's waiting today (say “print the shipping labels”)", "inbox": "answer the inbox (/inbox — drafts are ready)",
                 "reorder": "reorder before it hits zero", "proposals": "decide the open proposals (/store)", "margin": "raise the thin prices or the shipping fee",
                 "conversion": "fix the product page (photos, shipping cost visible early) before buying traffic", "diversify": "push a second product in posts this week", "repeat": "a card with a code in every parcel + one e-mail after 3 weeks"}
        out = ["What I'd change, in order:"]
        i = 1
        for f in bad + neutral:
            out.append(f"{i}. {f[1]} → {fixes.get(f[2], 'fix it')}")
            i += 1
            if i > 5:
                break
        good = [f for f in facts if f[0] == "good"]
        if good:
            out.append("What I would NOT touch: " + "; ".join(f[1] for f in good) + ".")
        out.append("Things outside the numbers I'd also do: one short video a day for 30 days, and product photos in real rooms — nothing else moves a small shop as much.")
        return "\n".join(out)

    def do_first(self, t, m):
        facts = self._facts()
        order = {"inbox": 0, "ship": 1, "restock": 2, "proposals": 3, "reorder": 4, "margin": 5, "conversion": 6, "diversify": 7, "repeat": 8, "run": 9}
        why = {"inbox": "a waiting customer is the only thing that gets worse by the hour (reviews, chargebacks); everything else can wait a day",
               "ship": "shipping late breaks the promise on your own page, and late parcels are 80 % of 'where is my order' mails",
               "restock": "a sold-out product still listed loses the buyers you already paid to attract",
               "proposals": "they're decisions I already prepared — 2 minutes of taps",
               "reorder": "supplier lead time is 1–3 weeks; ordering now avoids the stock-out",
               "margin": "every sale at a thin margin makes a refund hurt three times",
               "conversion": "more traffic on a page that doesn't convert is money burned",
               "diversify": "one product carrying the shop is a single point of failure",
               "repeat": "a returning customer costs nothing to acquire",
               "run": "without sales data every other decision is a guess"}
        act = {"inbox": "open /inbox and tap the drafts", "ship": "say “print the shipping labels”, then “all shipped”", "restock": "say “what do I need to reorder?” and order today",
               "proposals": "open /store and decide", "reorder": "say “order 20 more <product>”", "margin": "say “should I raise prices?” and I show which ones", "conversion": "say “why is nobody buying the <product>?”",
               "diversify": "say “which product should I push this week?”", "repeat": "say “write the thank-you card text”", "run": "say “run a practice day”"}
        cand = sorted([f for f in facts if f[0] != "good"], key=lambda f: order.get(f[2], 9))
        if not cand:
            return "If I were you: nothing is on fire, so I'd spend today on one thing that compounds — a 30-second video of the best seller in a real room, posted today. Everything else is running."
        f = cand[0]
        second = f"\nSecond: {cand[1][1]} → {act.get(cand[1][2], '')}." if len(cand) > 1 else ""
        return f"If I were you, first: {f[1]}. Why: {why.get(f[2], '')}. How: {act.get(f[2], '')}.{second}\nThen stop looking at numbers for the day and post something."

    def biggest_risk(self, t, m):
        facts = self._facts()
        st = self.store
        risks = []
        for f in facts:
            if f[2] == "diversify":
                risks.append(("Concentration: " + f[1] + ". If that supplier is late by two weeks, sales stop.", "have a second supplier's sample on the shelf; push a second product now"))
            if f[2] == "restock":
                risks.append(("Stock-outs: " + f[1] + ".", "reorder today and set 'ships in X days' instead of hiding the product"))
            if f[2] == "inbox":
                risks.append(("Unanswered customers: " + f[1] + " — that's where chargebacks and 1-star reviews come from.", "answer today, even with 'I'm on it, answer by tomorrow'"))
            if f[2] == "margin":
                risks.append(("Thin margins: " + f[1] + " — one refund eats three sales.", "raise the thin prices by 5–10 % or charge real shipping"))
        if st is not None:
            try:
                paid = self._paid()
                if paid and len({o.get("country") for o in paid}) == 1:
                    risks.append(("All sales from one country — one platform or courier problem there stops everything.", "open shipping to a second country and post in that language"))
            except Exception:
                pass
        if not risks:
            risks.append(("The usual small-shop killer: everything depends on you (the only person who ships, answers and posts). One sick week = a broken promise on every page.",
                          "a backup shipper (friend/family) with pre-printed labels, and my drafts so customers always get an answer"))
        risks = risks[:2] + [("Cash: stock is paid up front, sales come later; with € 1.000 in stock a slow month is felt at once.", "reorder in small batches, never more than 4–6 weeks of stock")]
        out = ["Biggest risks right now, in order:"]
        for i, (r, fix) in enumerate(risks, 1):
            out.append(f"{i}. {r} → {fix}.")
        out.append("Not a risk today: legal basics (pages are honest), payment fraud (small tickets), competition (they don't know you exist yet).")
        return "\n".join(out)

    def need_from_owner(self, t, m):
        st = self.store
        needs = []
        try:
            new = self.inbox.items("new") if self.inbox is not None else []
            if new:
                needs.append(f"tap the {len(new)} customer reply draft(s) in /inbox")
        except Exception:
            pass
        try:
            props = [p for p in st.data.get("proposals", []) if p["status"] == "open"]
            if props:
                needs.append(f"decide the {len(props)} store proposal(s) (/store)")
            day = st.data.get("day", 0)
            open_ = [o for o in st.data["orders"] if o["status"] == "paid"]
            if open_:
                needs.append(f"ship {len(open_)} order(s) — I print the labels, you hand the parcels to GLS")
            oos = [p for p in st.products() if p["stock"] == 0]
            if oos:
                needs.append("order stock for " + ", ".join(p["name"].split(" (")[0] for p in oos) + " (money leaves your account, so that's yours)")
        except Exception:
            pass
        try:
            items = self.memory.open_items() if self.memory else []
            due = [x for x in items if x.get("due") and x["due"][:10] <= _dt.date.today().isoformat()]
            if due:
                needs.append(f"{len(due)} reminder(s) came due: " + "; ".join(re.sub(r" \(⏰ .*\)$", "", x["text"])[:40] for x in due[:2]))
        except Exception:
            pass
        always = ("Standing needs: a tap on anything that costs money, goes public or reaches a customer — I prepare, you approve. "
                  "Real product photos from you (I can't take them). And when you're away, tell me for how long — I plan around it.")
        if not needs:
            return "Nothing right now — no taps pending, nothing to ship, no stock at zero. " + always
        return "From you, today:\n" + "\n".join(f"• {x}" for x in needs) + "\n" + always

    def eli5(self, t, m):
        n = self._n()
        if not n or not n.get("orders"):
            return ("Like you're five: the shop is a lemonade stand. Nobody has bought lemonade yet, so there are no numbers to explain — "
                    "say “run a practice day” and pretend-customers come, then I explain what happened with real figures.")
        rev, cogs, ship, fees, profit = n["revenue"], n["cogs"], n["shipping_cost"], n["fees"], n["profit"]
        per = profit / n["orders"] if n["orders"] else 0
        return (f"Like you're five, with the real numbers:\n"
                f"• People gave us {_eur(rev)} for {n['orders']} orders — that's the money in the jar. 🫙\n"
                f"• But we had to buy the things first: {_eur(cogs)} went to the people who make them. 📦\n"
                f"• The postman wants money to carry the boxes: {_eur(ship)}. 🚚\n"
                f"• The card machine takes a tiny bite of every payment: {_eur(fees)}. 💳\n"
                f"• What's left in the jar is ours: {_eur(profit)} — about {_eur(per)} for every order" + (f", or {profit / rev * 100:.0f} cents of every euro." if rev else ".") + "\n"
                f"• {n['visits']} people looked in the window and {n['orders']} came in — {n['conversion']:.1f} out of 100. Normal for a small shop is 1 to 3.\n"
                + ("Bigger jar = more people looking in the window (posts, videos) or a bigger basket (bundles, free shipping over a number)." if n["conversion"] >= 1.5 else
                   "Fewer than 1–2 in 100 buy, so the window needs work before inviting more people: photos and the shipping price shown early."))

    def conv_good(self, t, m):
        pct = _num(m.group("pct") or m.group("pct2"))
        n = self._n() or {}
        mine = f" Yours is {n['conversion']:.1f} % so far." if n.get("orders") else ""
        if pct >= 5:
            verdict = f"{pct:g} % is excellent — above what most shops ever see (the average sits at 2–3 %). Check it's real: a small number of visits makes the % jump around; trust it after 500+ visits."
        elif pct >= 2.5:
            verdict = f"{pct:g} % is good — right at or above the 2–3 % average for online shops; for a new small shop it's very good."
        elif pct >= 1.5:
            verdict = f"{pct:g} % is normal — fine for a small shop. Gains come from the checkout (shipping cost visible early) and product photos, not from more traffic."
        elif pct >= 0.8:
            verdict = f"{pct:g} % is low but not broken — typical when traffic comes from cold ads or the shipping fee surprises people at checkout. Fix the page before buying more visitors."
        else:
            verdict = f"{pct:g} % is a problem — under 1 in 100 buys. Usually: wrong traffic (curious, not buyers), a price/shipping shock at checkout, or photos that don't sell. Fix before spending a euro on ads."
        return verdict + mine + " Two things to remember: mobile converts about half of desktop, and returning visitors convert 2–3× first-timers — so a newsletter box beats another ad."

    def tax_aside(self, t, m):
        n = self._n() or {}
        rev = n.get("revenue", 0)
        base = ("In regime forfettario (the normal start in Italy): put aside about 15 % of what comes in — that covers the 5 % flat tax on 40 % of turnover (≈ 2 % of sales) plus the INPS contributions, which are the real bill "
                "(a fixed ~€ 4.600/yr, ~€ 3.000 with the 35 % reduction, whatever you sell). ")
        if rev:
            base += f"On your {_eur(rev)} so far that's about {_eur(rev * 0.15)} set aside" + (f"; the INPS minimum alone is € 250/month, so under ~€ 1.700 of monthly sales the fixed part dominates." if rev < 1700 else ".")
        base += (" Outside forfettario (ordinary regime): set aside 22 % VAT on every sale (it's not your money) plus ~30 % of the profit for IRPEF and INPS. "
                 "Do it weekly into a separate account — never at the deadline. Ask a commercialista once (€ 300–600 for the set-up) — this is the one place where I want you to double-check me.")
        return base

    def hire(self, t, m):
        n = self._n() or {}
        paid = self._paid(7)
        wk = len(paid)
        return ("Hire someone? Not yet, by the numbers: " + (f"{wk} orders this week" if wk else "no steady orders yet") + " is about 20–40 minutes of packing a day — I already draft the customer replies, "
                "the labels and the posts, so your own time goes into packing and photos.\n"
                "When it starts to make sense: (1) 15+ parcels a day every day → a fulfilment service (from ~€ 2–3/order, no salary, no contract) before an employee; "
                "(2) you're turning down things that would grow sales (videos, a second channel) because of packing → a part-timer 2 h/day or a family member paid per parcel (€ 1–2); "
                "(3) customer messages > 30/day → a support person, but I handle drafts up to far more than that.\n"
                "In Italy an employee costs about 1,5–1,7× the net salary (contributions + TFR), so a € 800 net part-timer is ~€ 1.300/month — that needs ~€ 4.000/month extra margin. "
                "Rule of thumb: hire when you can pay 3 months of it from the last 3 months' profit. Ask me “are we profitable?” and you have the base number.")

    def alone_today(self, t, m):
        facts = self._facts()
        st = self.store
        do, ask = [], []
        for f in facts:
            if f[2] == "inbox":
                do.append(f"draft the replies to the {f[1].split(' ')[0]} waiting customer message(s) (sent after your tap)")
            if f[2] == "ship":
                do.append("print today's shipping labels and the packing slips, and mark the orders once you say they've gone")
            if f[2] == "restock":
                ask.append("the reorder — I compute the quantities, the purchase is yours")
            if f[2] == "proposals":
                ask.append("the open proposals — 10 seconds each")
        do += ["watch the store: new orders, messages, stock — and ping you only for the urgent ones",
               "prepare today's post (photo pick + caption) for your tap",
               "look at the week's numbers and put one concrete suggestion in the evening report",
               "study one thing the shop needs (I keep a list: packaging, the German market, ads) and file the useful part in Drive"]
        out = ["Today, without you, I can:"] + [f"• {x}" for x in do]
        if ask:
            out.append("What still needs your tap: " + "; ".join(ask) + ".")
        out.append("If you'd like me to go further while you're out — e.g. send routine replies myself (tracking, product questions) — say so once and I keep to exactly that.")
        return "\n".join(out)

    def handle_alone(self, t, m):
        return ("Mostly yes — with the rules you set. Alone I can: answer every customer within the hour with a draft that follows the policies (but the reply goes out only after your tap — "
                "if you want me to send the routine ones myself while you're away, say “send routine replies yourself” and I'll do just tracking/returns-info/product questions, never refunds or arguments); "
                "watch orders and print labels; keep the stock numbers right; post the day's post (again: after a tap, unless you pre-approve a week of posts before you go); "
                "run the numbers and send you an evening report; study when nothing is happening.\n"
                "What I can't do alone: physically ship (a friend with pre-printed labels solves it), decide money (refunds, reorders, price changes — I prepare, you tap, 10 seconds each from the phone), "
                "and phone calls with couriers.\n"
                "So a week away looks like: 10 minutes of taps a day from your phone, plus someone who drops parcels at GLS. Tell me the dates and I'll put the 'orders ship on <date>' note up if there's no shipper.")

    def how_answer(self, t, m):
        return ("How I decide what to answer a customer:\n"
                "1. I sort the message: where-is-my-order, return/refund, damaged/wrong item, product question, cancel/change, complaint, discount request, compliment, or 'other'.\n"
                "2. I look up what I'm allowed to know: the order (status, tracking, dates — only if the e-mail matches the order), the shop's own pages (shipping, returns, product details) — never anything I'd have to invent.\n"
                "3. I write the draft from a template for that kind, filled with the real facts, in the customer's language, and I run checks: no promises the policy doesn't make, no refund amount unless the policy gives it, "
                "no 'sorry' for things that aren't our fault without a fix attached, nothing about another customer's order.\n"
                "4. If a fact is missing (their order number, a photo of the damage) the draft asks for it instead of guessing.\n"
                "5. You get the draft with Approve / Edit / Reject. Nothing leaves without your tap; when you edit, I keep the edit as a lesson for that kind of message.\n"
                "Refunds, damage and angry messages I flag so you see them first. Say “show me the drafts” or /inbox to see them.")

    def angry_customer(self, t, m):
        return ("An angry customer, my routine:\n"
                "1. Answer fast — within the hour if I can, even if the answer is “I'm looking into it, you'll hear from me by <time today>”. Silence is what makes it worse.\n"
                "2. No defence in the first line. First: what they feel and what I'll do. “I'm sorry — that shouldn't have happened, and I'll sort it out today.”\n"
                "3. Then the facts, short, from the order — never argue about tone, never quote policy at them in the first message.\n"
                "4. Offer the fix that costs us least and them nothing: replacement or refund, their choice, no return of a broken item.\n"
                "5. I flag it to you before sending — you always see angry ones first, and anything with money in it needs your tap anyway.\n"
                "6. Afterwards I note the cause (packaging? late shipping? photo vs reality?) so the same anger doesn't come back next week.\n"
                "Abuse or threats: one calm reply, then stop replying and tell you; nobody has to take insults, and a paper trail beats a fight.")

    def know_customers(self, t, m):
        paid = self._paid()
        if not paid:
            return "Nothing yet — no orders, so no customers to describe. Once there are, I can tell you where they buy from, what they buy together, basket size and repeat rate (never names in posts or documents)."
        st = self.store
        countries = {}
        for o in paid:
            countries[o.get("country", "?")] = countries.get(o.get("country", "?"), 0) + 1
        top_c = sorted(countries.items(), key=lambda x: -x[1])
        rev = sum(o["total"] for o in paid)
        aov = rev / len(paid)
        emails = {}
        for o in paid:
            k = (o.get("customer") or {}).get("email") or str(o["n"])
            emails[k] = emails.get(k, 0) + 1
        rep = sum(1 for v in emails.values() if v > 1)
        pairs = {}
        for o in paid:
            names = sorted({l["name"].split(" (")[0] for l in o["lines"]})
            if len(names) >= 2:
                k = " + ".join(names[:2]); pairs[k] = pairs.get(k, 0) + 1
        multi = len([o for o in paid if sum(l["qty"] for l in o["lines"]) > 1])
        days = {}
        for o in paid:
            days[o.get("day", 0)] = days.get(o.get("day", 0), 0) + 1
        return (f"Our customers so far ({len(emails)} people, {len(paid)} orders):\n"
                f"• Where: " + ", ".join(f"{c} {n} ({n / len(paid) * 100:.0f} %)" for c, n in top_c[:4]) + ".\n"
                f"• Basket: {_eur(aov)} on average; {multi} of {len(paid)} orders had more than one item" + (f"; the pair that shows up most: {max(pairs, key=pairs.get)}" if pairs else "") + ".\n"
                f"• Loyalty: {rep} came back" + (" — early days." if not rep else ".") + "\n"
                f"• Rhythm: {len(paid) / max(1, len(days)):.1f} orders per selling day.\n"
                "What I don't know and would like to: how they found us (no analytics on the practice store) and their age/gender — an eco home range usually sells to women 25–45 buying for the home or as gifts; "
                "I'd verify that with a one-question e-mail after delivery. Names and e-mails stay in the store — never in posts or documents.")

    def next_countries(self, t, m):
        paid = self._paid()
        st = self.store
        have = []
        try:
            have = [r[0] for r in st.ship_rules()]
        except Exception:
            pass
        countries = {}
        for o in paid:
            countries[o.get("country", "?")] = countries.get(o.get("country", "?"), 0) + 1
        best_other = sorted(((c, n) for c, n in countries.items() if c not in ("IT",)), key=lambda x: -x[1])
        out = ["Next countries, in order of sense for a small Italian eco-home shop:"]
        out.append("1. Germany + Austria first (if not already strong): biggest EU market for eco/home goods, they pay for quality, PayPal and invoice payment matter, GLS delivers in 4–6 days; pages in German double conversion there.")
        out.append("2. France: strong on design/home, needs French pages and French customer replies (I write both); Colissimo/GLS 4–6 days.")
        out.append("3. Netherlands/Belgium: small but easy — English is fine, iDEAL/Bancontact as payment methods help.")
        out.append("4. Spain: price-sensitive, later. Switzerland/UK: only after that — customs paperwork and € 20+ shipping kill baskets under € 60.")
        if best_other:
            out.append(f"Your own data agrees or not: outside Italy you already sold in " + ", ".join(f"{c} ×{n}" for c, n in best_other[:3]) + " — start where the orders already come from.")
        if have:
            out.append(f"Currently open at checkout: {', '.join(have)}. Say “open shipping to <country> at <price>” and I prepare the rule; “translate the shipping page into German” and I do the page.")
        out.append("One at a time: open, translate the 4 help pages, post twice a week in that language, look at the numbers after 30 days.")
        return "\n".join(out)

    def week_plan(self, t, m):
        facts = self._facts()
        st = self.store
        out = ["Plan for the week:"]
        i = 1
        for f in [x for x in facts if x[0] != "good"][:3]:
            out.append(f"{i}. {f[1].split(' — ')[0]} → " + {"restock": "reorder Monday", "ship": "ship daily before the GLS pickup", "inbox": "answer today", "reorder": "reorder mid-week", "proposals": "decide them Monday", "margin": "adjust prices Tuesday, watch till Sunday",
                                                                 "conversion": "product page fixes (photos, shipping line) by Wednesday", "diversify": "push the second product in every post", "repeat": "thank-you card in every parcel from Monday", "run": "run a practice week"}.get(f[2], "handle"))
            i += 1
        out.append(f"{i}. Content: 5 posts (Mon–Fri), one short video, all on the best seller and one 'second' product — say “what should I post today?” each morning.")
        out.append(f"{i + 1}. Friday: numbers — say “how's the week going?” — and one decision from them (price, stock or post), not five.")
        try:
            items = self.memory.open_items() if self.memory else []
            if items:
                out.append("Your to-do list feeds in: " + "; ".join(re.sub(r" \(⏰ .*\)$", "", x["text"])[:40] for x in items[:3]) + (f" (+{len(items) - 3})" if len(items) > 3 else "") + ".")
        except Exception:
            pass
        out.append("Me, in the gaps: draft replies within the hour, evening report at 20:00, one study session a day on what the shop needs (packaging, ads, the German market).")
        return "\n".join(out)

    def summarize_days(self, t, m):
        n_days = int(m.group("n") or m.group("n2") or 7)
        st = self.store
        if st is None:
            return None
        day = st.data.get("day", 0)
        paid = self._paid(n_days)
        if not st.data["orders"]:
            return f"Last {n_days} days: no shop activity yet — the practice store hasn't run. Say “run a practice day”."
        rev = sum(o["total"] for o in paid)
        cogs = sum(l["qty"] * l.get("cost", 0) for o in paid for l in o["lines"])
        ship = sum(2.9 + 0.35 * sum(l["qty"] for l in o["lines"]) for o in paid)
        fees = sum(0.029 * o["total"] + 0.30 for o in paid)
        profit = rev - cogs - ship - fees
        units = {}
        for o in paid:
            for l in o["lines"]:
                units[l["name"].split(" (")[0]] = units.get(l["name"].split(" (")[0], 0) + l["qty"]
        best = max(units, key=units.get) if units else "—"
        visits = sum(v for d, v in st.data.get("visits", {}).items() if int(d) > day - n_days)
        bad = [o for o in st.data["orders"] if o.get("day", 0) > day - n_days and o["status"] in ("refunded", "cancelled")]
        oos = [p["name"].split(" (")[0] for p in st.products() if p["stock"] == 0]
        line3 = ("Problems: " + "; ".join(x for x in [f"{len(bad)} refund/cancel" if bad else "", "sold out: " + ", ".join(oos) if oos else "", f"{len([o for o in st.data['orders'] if o['status'] == 'paid'])} to ship" if any(o["status"] == "paid" for o in st.data["orders"]) else ""] if x)) if (bad or oos or any(o["status"] == "paid" for o in st.data["orders"])) else "Problems: none open — nothing late, nothing sold out."
        return (f"Last {n_days} days in 3 lines:\n"
                f"1. {len(paid)} orders, {_eur(rev)} sales, {_eur(profit)} profit ({profit / rev * 100:.0f} %) from {visits} visits ({len(paid) / visits * 100 if visits else 0:.1f} % bought).\n"
                f"2. Best seller: {best} ({units.get(best, 0)} sold); " + (f"{len(units)} products sold in total." if units else "nothing else sold.") + "\n"
                f"3. {line3}")

    def confidence(self, t, m):
        n = self._n() or {}
        return ("Honest answer, in layers:\n"
                f"• Orders, sales, stock, per-country split: exact — they come straight from the shop's own ledger ({n.get('orders', 0)} orders counted, nothing estimated).\n"
                "• Costs of goods: as good as the cost you gave me per product; if a supplier price changed and you didn't tell me, the margin is off by that much.\n"
                "• Shipping cost per parcel and payment fees: practice figures (€ 2,90 + € 0,35/item; 2,9 % + € 0,30) — realistic for a small Italian shop but not your real contract. Give me the real rates and I use them.\n"
                "• Conversion: exact for the practice store; in a real shop it depends on the analytics being set up right.\n"
                "• Forecasts ('if we doubled traffic', 'a good month'): educated guesses from small numbers — right in direction, ±30 % in size until there are a few hundred orders.\n"
                "• Law and tax: rules of thumb I checked against Italian/EU sources this year — right for the common case, still ask a commercialista for your own situation.\n"
                "If a number matters for a money decision, ask me “show me the maths” and I lay it out line by line.")

    def good_month(self, t, m):
        st = self.store
        n = self._n() or {}
        paid = self._paid()
        aov = (n.get("revenue", 0) / n["orders"]) if n.get("orders") else 25.0
        margin = (n.get("profit", 0) / n["revenue"]) if n.get("revenue") else 0.5
        conv = n.get("conversion", 2.0) or 2.0
        fixed = 250 + 30 + 20                                    # INPS minimum/month, domain+tools, boxes
        rows = []
        for label, orders in (("a quiet month", 40), ("a good month", 120), ("a great month", 300)):
            rev = orders * aov
            prof = rev * margin - fixed - orders * 1.0
            visits_needed = f"{int(orders / (conv / 100)):,}".replace(",", ".")
            rows.append(f"• {label}: ~{orders} orders ({orders // 30}–{orders // 30 + 1} a day) → {_eur(rev)} sales, about {_eur(prof)} left after goods, shipping, fees, boxes and the INPS minimum; needs ~{visits_needed} visits at {conv:.1f} % conversion")
        return ("What a month looks like, with your own basket and margin (" + f"{_eur(aov)} per order, {margin * 100:.0f} % net):\n" + "\n".join(rows) +
                "\nA 'good month' for a one-person shop is the middle one: it pays the taxman and leaves a real part-time income; the top one is where hiring/fulfilment questions start. "
                "The lever behind all three is visits — say “how do I get my first 100 followers?” or “ads budget?” for how.")

    def is_amount_good(self, t, m):
        amt = _num(m.group("amt") or m.group("amt2"))
        per = (m.group("per") or m.group("per2") or "week").lower()
        per_days = {"week": 7, "settimana": 7, "month": 30, "mese": 30, "day": 1, "today": 1, "yesterday": 1}.get(per, 7)
        n = self._n() or {}
        margin = (n.get("profit", 0) / n["revenue"]) if n.get("revenue") else 0.5
        sales_word = bool(re.search(r"\b(sales|turnover|sold|revenue|fatturato|venduto)\b", t.lower()))
        profit = amt if (not sales_word and re.search(r"\bprofit\b", t.lower())) else amt * margin
        month_profit = profit / per_days * 30
        fixed = 250 + 50
        if month_profit < fixed:
            verdict = f"For a start it's fine — for a business not yet: about {_eur(month_profit)} of profit a month (at your {margin * 100:.0f} % margin) doesn't yet cover the fixed bills (~{_eur(fixed)}: INPS minimum, domain, boxes)."
        elif month_profit < 1000:
            verdict = f"Good for month one or two: ~{_eur(month_profit)} profit a month (at your {margin * 100:.0f} % margin) covers the fixed bills and leaves pocket money. The next step is 3× that, which is traffic, not a new product."
        elif month_profit < 2500:
            verdict = f"Genuinely good: ~{_eur(month_profit)} profit a month is a real part-time income from a one-person shop."
        else:
            verdict = f"Very good: ~{_eur(month_profit)} profit a month — that's full-time money; start thinking about fulfilment and a second channel."
        kind_w = "profit" if (not sales_word and "profit" in t.lower()) else "sales"
        per_w = {"settimana": "week", "mese": "month", "today": "day", "yesterday": "day"}.get(per, per)
        return (f"{_eur(amt)} of {kind_w} in a {per_w}: {verdict} "
                f"Benchmarks: a new small shop typically does € 200–800 of sales a week in months 1–3; € 2.000+ a week by month 6 is a strong one. "
                "What matters more than the number: is it growing week on week (say “how are we doing compared to last week?”), and is the margin holding.")

    def what_if_traffic(self, t, m):
        n = self._n() or {}
        if not n.get("orders"):
            return "No sales data yet, so I'd be inventing it — run a few practice days and ask again; then I answer from the real conversion and basket."
        low = t.lower()
        factor = 2.0
        if re.search(r"\btripl|3 ?x|three times\b", low):
            factor = 3.0
        elif re.search(r"\bhalv", low):
            factor = 0.5
        elif re.search(r"\b10 ?x\b", low):
            factor = 10.0
        mp = re.search(r"\+?\s*(\d+)\s*%", low)
        if mp:
            factor = 1 + int(mp.group(1)) / 100
        what = "conversion" if "conversion" in low else "prices" if re.search(r"\bprices?\b", low) else "traffic"
        rev, orders, profit, visits = n["revenue"], n["orders"], n["profit"], n["visits"]
        aov = rev / orders
        unit_margin = profit / orders
        if what == "traffic":
            new_orders = orders * factor
            new_profit = new_orders * unit_margin
            cav = ""
            if factor > 1:
                cav = (" Two honest caveats: extra visitors convert worse than the first ones (new traffic is colder), so plan for 70–80 % of that; and ads to double traffic cost money — "
                       f"at ~€ 0,30–0,60 a visit you'd spend {_eur(visits * (factor - 1) * 0.3)}–{_eur(visits * (factor - 1) * 0.6)} to get it, which is {'more than' if visits * (factor - 1) * 0.45 > (new_profit - profit) else 'less than'} the extra profit. Free traffic (videos, posts) is the same maths without the bill.")
            return (f"Doubling the traffic" if factor == 2 else f"Traffic × {factor:g}") + f": {visits} → {int(visits * factor)} visits at the same {n['conversion']:.1f} % conversion = ~{int(new_orders)} orders instead of {orders}, " \
                   f"~{_eur(new_orders * aov)} sales, ~{_eur(new_profit)} profit (was {_eur(profit)}) — every extra order brings about {_eur(unit_margin)}." + cav
        if what == "conversion":
            new_orders = orders * factor
            return (f"Conversion × {factor:g} ({n['conversion']:.1f} % → {n['conversion'] * factor:.1f} %) with the same {visits} visits: ~{int(new_orders)} orders, ~{_eur(new_orders * unit_margin)} profit (was {_eur(profit)}). "
                    "That's the cheapest growth there is — it costs page work, not ad money: shipping price shown before checkout, real photos, a review or two, free shipping over a threshold. Realistic gains are +30–50 %, not ×2, unless something is badly broken today.")
        # prices
        new_rev = rev * factor
        lost = 0.15 if factor <= 1.1 else 0.3 if factor <= 1.25 else 0.5
        return (f"Prices × {factor:g}: if nobody blinked, {_eur(rev)} → {_eur(new_rev)} of sales and all of the extra {_eur(new_rev - rev)} is profit (costs stay). "
                f"But some buyers walk: at +{(factor - 1) * 100:.0f} % expect to lose ~{lost * 100:.0f} % of orders — profit becomes ~{_eur((orders * (1 - lost)) * (unit_margin + aov * (factor - 1)))} vs {_eur(profit)} now. "
                + ("Still a win — small rises on products with no direct comparison usually pay." if (orders * (1 - lost)) * (unit_margin + aov * (factor - 1)) > profit else "Not worth it at that size — try +5–10 % on the best seller only."))

    def _msg_kinds(self, days=7):
        """Customer messages of the last N days, each with its kind (regex classifier, no model)."""
        out = []
        if self.inbox is None:
            return out
        try:
            since = (_dt.datetime.now() - _dt.timedelta(days=days)).isoformat()[:19]
            for r in self.inbox.items():
                if str(r.get("t", ""))[:19] < since:
                    continue
                try:
                    k = self.inbox.classify(r["text"])["kind"]
                except Exception:
                    k = "other"
                out.append((r, k))
        except Exception:
            pass
        return out

    def _days(self):
        """{day: (orders, sales)} and {day: visits} from the ledger."""
        st = self.store
        od, vd = {}, {}
        for o in st.data["orders"]:
            if o["status"] in ("paid", "shipped", "delivered"):
                a, b = od.get(o.get("day", 0), (0, 0.0))
                od[o.get("day", 0)] = (a + 1, b + o["total"])
        for d, v in st.data.get("visits", {}).items():
            vd[int(d)] = v
        return od, vd

    def are_you_sure(self, t, m):
        last = None
        try:
            last = self.last_reply()
        except Exception:
            pass
        if not last or not isinstance(last, tuple) or not last[1]:
            return "Sure about what? Ask the question again and I'll tell you where each part of the answer comes from — ledger, your own settings, what I've read, or my judgement."
        q, a = last
        a_l = str(a).lower()
        n = self._n() or {}
        if re.search(r"\n— .|\bsurvey\b|\baccording to\b|shopify's|\*\s*$", str(a)) and "€" not in str(a):
            return ("Honestly, no — that answer came from what I've read (articles, not our data), so it's a rule of thumb, not a fact about your shop. "
                    "If it matters for a decision, say “research it and write me a document” and I'll come back with sources you can open; or ask the same question about OUR numbers and I answer from the ledger.")
        if re.search(r"€|\d+ order|\d+ visits|conversion|profit|sold|stock", a_l):
            return (f"The numbers in it — yes: they come straight from the shop's ledger ({n.get('orders', 0)} orders, every one counted), not estimated. "
                    "Two things are softer: costs use the per-product cost and the practice shipping/fee rates you gave me (change them and the margins move), and any 'what to do' part is my judgement — right in direction, arguable in detail. "
                    "Say “show me the maths” and I lay the calculation out line by line.")
        if re.search(r"\b(law|legal|vat|tax|inps|forfettario|guarantee|withdraw|gdpr)\b", a_l + " " + q.lower()):
            return "Reasonably — that's the rule as I checked it against Italian/EU sources this year, and it's right for the common case. Your own situation can differ (regime, volumes, what you sell), so treat it as the question to bring to a commercialista, not the final word."
        if re.search(r"\b(i'?d|i would|my (?:take|opinion|advice)|verdict|rule of thumb|usually|typically)\b", a_l):
            return "It's my judgement from the numbers plus what I've learned about small shops — confident in direction, not a guarantee. If you see something in the shop I can't see from the ledger (a supplier problem, a customer's tone), tell me and I'll rethink it."
        return "Yes, as far as it's about our own data and settings; anything about the outside world in it is what I've read, not something I verified today. Point at the part you doubt and I'll say exactly where it comes from."

    def best_why(self, t, m):
        n = self._n() or {}
        units = n.get("units", {})
        if not units:
            return "No sales yet, so no best seller — run a practice day and ask again."
        st = self.store
        best = max(units, key=units.get)
        prod = next((p for p in st.products() if p["name"] == best), None) or {}
        prods = st.products()
        cheapest = min(prods, key=lambda p: p["price"])
        reasons = []
        if prod and prod["id"] == cheapest["id"]:
            reasons.append(f"it's the cheapest thing in the shop ({_eur(prod['price'])}) — the low-risk first purchase people make to try a new shop")
        elif prod and prod["price"] <= 20:
            reasons.append(f"under € 20 ({_eur(prod['price'])}) — impulse territory, no thinking needed")
        if prod and re.search(r"\bset\b|\d+ ?pcs|pack", prod["name"].lower()):
            reasons.append("it's a set — a multi-pack feels like better value and works as a gift")
        if prod and prod.get("stock", 0) > 0:
            reasons.append("it never sold out, so it was always there to buy — two products that sold slower were out of stock part of the time" if any(p["stock"] == 0 for p in prods) else "it stayed in stock the whole time")
        if prod and prod.get("price") and prod.get("cost") is not None:
            mg = (prod["price"] - prod["cost"]) / prod["price"] * 100
            reasons.append(f"and it's a good one to lead with: {mg:.0f} % gross margin, light to ship")
        total = sum(units.values())
        share = units[best] / total * 100
        second = sorted(units.items(), key=lambda x: -x[1])[1] if len(units) > 1 else None
        return (f"Best seller: {best} — {units[best]} of {total} units sold ({share:.0f} %)" + (f"; second is {second[0]} with {second[1]}." if second else ".") +
                "\nWhy, as far as the numbers can tell: " + "; ".join(reasons or ["it's the product on the home page and in the posts — visibility, more than the product itself"]) + "." +
                "\nWhat that means: post it, bundle it with a slower item (“toothbrush set + mug”) and never let it go out of stock; a shop's best seller is its door.")

    def break_even(self, t, m):
        st = self.store
        n = self._n() or {}
        stock_cost = sum(p["stock"] * p.get("cost", 0) for p in st.products())
        setup = 150.0
        outlay = stock_cost + setup
        profit = n.get("profit", 0)
        day = max(1, st.data.get("day", 0))
        per_day = profit / day if day else 0
        remaining = outlay - profit
        if not n.get("orders"):
            return f"No sales yet, so there's nothing to project from. What's at stake: {_eur(stock_cost)} of stock at cost on the shelf plus ~€ 150 of set-up (domain, boxes, samples) = {_eur(outlay)} to earn back."
        if remaining <= 0:
            return f"Already there: {_eur(profit)} of profit so far covers the {_eur(stock_cost)} of stock still on the shelf plus ~€ 150 of set-up. From here every sale is real gain (before your time and taxes)."
        days = remaining / per_day if per_day > 0 else None
        return (f"Break-even, on what I can see: money out = {_eur(stock_cost)} of stock at cost still on the shelf + ~€ 150 of set-up (domain, boxes, samples) = {_eur(outlay)}. "
                f"Profit so far {_eur(profit)} in {day} day(s) = {_eur(per_day)} a day → about {days:.0f} more days ({(days / 7):.1f} weeks) at this pace." if days else f"Profit so far is {_eur(profit)} — at zero or negative daily profit there is no break-even date; fix the margin first.") + \
               (" Two things move it: a stock reorder pushes it out (more money on the shelf), a better week pulls it in. If you spent more on set-up than € 150 (photos, samples, ads), tell me the number and I redo it." if days else "")

    def orders_needed(self, t, m):
        gd = m.groupdict()
        amt = _num(gd.get("amt") or gd.get("amt2") or gd.get("amt3") or "1000")
        if re.search(r"\d\s*k\b", t.lower()):
            amt *= 1000
        per = (gd.get("per") or gd.get("per2") or "month").lower()
        n = self._n() or {}
        aov = (n["revenue"] / n["orders"]) if n.get("orders") else 25.0
        unit_margin = (n["profit"] / n["orders"]) if n.get("orders") else aov * 0.5
        conv = n.get("conversion") or 2.0
        want_profit = bool(re.search(r"\b(profit|net|utile|in my pocket|take home|keep)\b", t.lower()))
        days = {"month": 30, "week": 7, "day": 1, "year": 365}[per]
        need_sales = amt / aov
        need_profit = amt / unit_margin if unit_margin > 0 else float("inf")
        line = (f"To make {_eur(amt)} of {'profit' if want_profit else 'sales'} a {per} with your current basket ({_eur(aov)} per order" + (f", {_eur(unit_margin)} of it profit" if not want_profit else f" → {_eur(unit_margin)} profit each") + "): "
                f"{(need_profit if want_profit else need_sales):.0f} orders a {per} — {((need_profit if want_profit else need_sales) / days):.1f} a day — "
                f"which at {conv:.1f} % conversion means about {int((need_profit if want_profit else need_sales) / (conv / 100)):,} visits a {per}.".replace(",", "."))
        if not want_profit:
            line += f" If you meant profit in your pocket, it's {need_profit:.0f} orders ({need_profit / days:.1f} a day)."
        base = (n.get("orders", 0) / max(1, self.store.data.get("day", 1))) * days
        line += f" You're at ~{base:.0f} orders a {per} at the current pace." if n.get("orders") else ""
        line += " The two levers: basket size (bundles, a free-shipping threshold) and visits (posts/videos first, ads only once the page converts)."
        return line

    def urgent(self, t, m):
        facts = self._facts()
        st = self.store
        urgent = []
        day = st.data.get("day", 0)
        late = [o for o in st.data["orders"] if o["status"] == "paid" and day - o.get("day", day) >= 1]
        if late:
            urgent.append(f"🔴 {len(late)} order(s) past the promised next-day shipping (oldest #{min(late, key=lambda o: o.get('day', 0))['n']}) — ship today: say “print the shipping labels”")
        for r, k in self._msg_kinds(7):
            if r.get("status") == "new" and k in ("damaged_or_wrong", "return_or_refund", "cancel_or_change"):
                urgent.append(f"🔴 unanswered {k.replace('_', ' ')} message from {r.get('from', 'a customer')} — draft is ready in /inbox")
        for f in facts:
            if f[2] == "restock":
                urgent.append(f"🟠 {f[1].split(' — ')[0]} — still listed, so buyers bounce; reorder or mark 'back in X days'")
        try:
            items = self.memory.open_items() if self.memory else []
            due = [x for x in items if x.get("due") and x["due"][:16] <= _dt.datetime.now().isoformat()[:16]]
            for x in due[:2]:
                urgent.append(f"🟠 reminder due: {re.sub(r' \(⏰ .*\)$', '', x['text'])[:50]}")
        except Exception:
            pass
        if not urgent:
            return "Nothing urgent: no late orders, no complaint unanswered, nothing sold out, no reminder due. The rest can wait for your evening report."
        return "Urgent, most first:\n" + "\n".join(f"• {u}" for u in urgent[:5]) + ("\nEverything else is routine." if len(urgent) <= 2 else "")

    def complaints(self, t, m):
        rows = self._msg_kinds(7)
        bad = [(r, k) for r, k in rows if k in ("damaged_or_wrong", "return_or_refund", "where_is_my_order", "cancel_or_change") or re.search(r"\b(angry|unacceptable|terrible|disappointed|worst|never again|scam|furious|ridiculous)\b", r["text"].lower())]
        if not rows:
            return "No customer messages at all in the last 7 days — nothing to complain about, or nobody's talking (both worth knowing: a zero-message week with orders is normal for a small shop)."
        if not bad:
            return f"No complaints: {len(rows)} message(s) in the last 7 days, all questions or compliments — " + ", ".join(sorted({k.replace('_', ' ') for _, k in rows})) + "."
        names = {"damaged_or_wrong": "damaged/wrong item", "return_or_refund": "return or refund", "where_is_my_order": "where is my order", "cancel_or_change": "cancel/change"}
        lines = [f"{len(bad)} of {len(rows)} message(s) in the last 7 days were complaints or problems:"]
        for r, k in bad[:5]:
            lines.append(f"• {r.get('from', '?')} — {names.get(k, k)}: “{r['text'][:70]}…” → {'answered' if r.get('status') != 'new' else 'draft waiting for your tap'}")
        kinds = {}
        for _, k in bad:
            kinds[k] = kinds.get(k, 0) + 1
        top = max(kinds, key=kinds.get)
        cause = {"where_is_my_order": "usually late shipping or no tracking mail — ship daily and send the tracking number the same day",
                 "damaged_or_wrong": "packaging: mugs and lamps need double-wall boxes and 5 cm of padding; one broken parcel costs more than 20 better boxes",
                 "return_or_refund": "expectations vs photos — check the product page says exactly what arrives (size, colour, material)",
                 "cancel_or_change": "people change their mind fast — ship fast and they can't; and a clear 'edit your order within 2 h' line saves mails"}
        lines.append(f"Pattern: most are '{names.get(top, top)}' — {cause.get(top, '')}.")
        return "\n".join(lines)

    def spend_budget(self, t, m):
        gd = m.groupdict()
        amt = _num(gd.get("amt") or gd.get("amt2") or gd.get("amt3") or gd.get("amt4") or "200")
        if re.search(r"\d\s*k\b", t.lower()):
            amt *= 1000
        st = self.store
        n = self._n() or {}
        units = n.get("units", {})
        left = amt
        plan = []
        oos = sorted([p for p in st.products() if p["stock"] == 0], key=lambda p: -units.get(p["name"], 0))
        low = sorted([p for p in st.products() if 0 < p["stock"] <= 3], key=lambda p: -units.get(p["name"], 0))
        for p in oos + low:
            qty = 10 if p.get("cost", 0) < 8 else 5
            c = qty * p.get("cost", 0)
            if c <= left and c > 0:
                plan.append((c, f"{qty} × {p['name'].split(' (')[0]} at {_eur(p['cost'])} = {_eur(c)} — {'sold out' if p['stock'] == 0 else 'nearly out'}" + (f", {units.get(p['name'], 0)} sold so far" if units.get(p['name']) else "")))
                left -= c
        if left >= 25:
            c = min(30.0, left)
            plan.append((c, f"{_eur(c)} on 100 thank-you cards with a 10 % return code + better tape/paper — the cheapest repeat-customer machine there is"))
            left -= c
        if left >= 40:
            best = max(units, key=units.get) if units else None
            days = int(left // 5)
            plan.append((left, f"{_eur(left)} on a first ad test: € 5 a day for {days} days on one short video of {best.split(' (')[0] if best else 'the best seller'}, Italy only, to learn the cost per visit — not to make money yet"))
            left = 0
        if left > 0:
            plan.append((left, f"{_eur(left)} kept as a cushion for a refund or a broken parcel"))
        out = [f"With {_eur(amt)}, in this order:"]
        for i, (c, line) in enumerate(plan, 1):
            out.append(f"{i}. {line}")
        out.append("Why this order: stock you can't sell is lost sales today; cards bring the second order; ads only teach you something once the page converts (it does, at " + (f"{n['conversion']:.1f} %)." if n.get('orders') else "— unknown until there are sales)."))
        out.append("Nothing here spends itself — say “order 10 more <product>” or “prepare the ad test” and I prepare it for your tap.")
        return "\n".join(out)

    def reviews(self, t, m):
        n = self._n() or {}
        return ("More reviews — what works for a small shop, in order of effect:\n"
                "1. Ask at the right moment: 5–7 days after delivery (the item is in use, the parcel joy is still there), one short personal e-mail with a direct link to the review form. That alone is 5–10 % of buyers; nothing else comes close.\n"
                "2. The card in the parcel: 'Happy with it? A photo review helps us more than you'd think' + a QR code to the review page. Don't offer money for a review (illegal in the EU when undisclosed); a small code for the NEXT order in exchange for honest feedback is fine if the review isn't required.\n"
                "3. Make it easy: 3 clicks max, phone-friendly, photo optional.\n"
                "4. Reply to every review, good or bad, in one human sentence — future buyers read the replies more than the stars.\n"
                "5. Answer problems fast: a solved complaint becomes a 5-star review surprisingly often; an ignored one becomes a 1-star.\n"
                + (f"With your {n['orders']} orders so far, expect the first 1–3 reviews from a review request e-mail; " if n.get("orders") else "") +
                "say “write the review request e-mail” and I draft it, or “put a review line on the thank-you card” and I add it to the card text.")

    def one_idea(self, t, m):
        st = self.store
        n = self._n() or {}
        units = n.get("units", {})
        day = st.data.get("day", 0)
        ideas = []
        best = max(units, key=units.get) if units else None
        instock = [p for p in st.products() if p["stock"] > 0]
        slow = sorted([p for p in instock if units.get(p["name"], 0) <= 1], key=lambda p: -p["stock"])
        aov = (n["revenue"] / n["orders"]) if n.get("orders") else 0
        if best and slow:
            b = next((p for p in st.products() if p["name"] == best), None)
            if b and b["stock"] > 0:
                s0 = slow[0]
                bundle = round((b["price"] + s0["price"]) * 0.9, 2)
                ideas.append(f"Bundle the best seller with the slowest item: “{best.split(' (')[0]} + {s0['name'].split(' (')[0]}” for {_eur(bundle)} instead of {_eur(b['price'] + s0['price'])} (10 % off, still {((bundle - b['cost'] - s0['cost']) / bundle * 100):.0f} % margin). It lifts the basket and moves the {s0['stock']} pcs of {s0['name'].split(' (')[0]} sitting there. Say “add the bundle” and I prepare it.")
        if aov:
            thr = int(aov) + 6
            thr = thr - (thr % 5) + 4.99
            ideas.append(f"Free shipping over {_eur(thr)}: your average basket is {_eur(aov)}, so shoppers add a small item to reach it — basket up 10–20 % in most small shops. Say “free shipping over {int(thr)}” and I prepare the rule.")
        if best:
            ideas.append(f"One 20-second video a day of {best.split(' (')[0]} in a real room, 7 days straight, same hook (“the one thing in my kitchen everyone asks about”) — short video is the only free traffic that still works; I'll write the 7 hooks: say “write 7 video hooks”.")
        ideas.append("A 'back in stock / new colour' e-mail to everyone who bought — a mail to past buyers converts 5–10× a post; I draft it in your tone: say “write the e-mail to past customers”.")
        ideas.append("Put the shipping price and the '1-day dispatch from Bergamo' line on the product page above the buy button — the checkout surprise is where small shops lose a third of carts.")
        if not ideas:
            return "Run a practice day first — with no sales I'd only be guessing which lever to pull."
        pick = ideas[(day + getattr(self, "_idea_offset", 0)) % len(ideas)]
        return f"One idea for this week: {pick}\n(Say “another one” for the next — I rotate through {len(ideas)}.)"

    def mistakes(self, t, m):
        st = self.store
        day = st.data.get("day", 0)
        n = self._n() or {}
        out = []
        late = [o for o in st.data["orders"] if o["status"] == "paid" and day - o.get("day", day) >= 1]
        if late:
            out.append(f"{len(late)} order(s) not shipped the next day as the page promises — the one mistake customers notice")
        oos = [p for p in st.products() if p["stock"] == 0]
        for p in oos:
            out.append(f"{p['name'].split(' (')[0]} ran out and stayed listed as buyable — reorder point should be 2 weeks of sales, not zero")
        rows = self._msg_kinds(7)
        new = [r for r, _ in rows if r.get("status") == "new"]
        if new:
            out.append(f"{len(new)} customer message(s) still unanswered — drafts were ready; a reply within the hour is the cheapest marketing")
        rej = [p for p in st.data.get("proposals", []) if p["status"] == "rejected"]
        openp = [p for p in st.data.get("proposals", []) if p["status"] == "open"]
        if openp and day >= 2:
            out.append(f"{len(openp)} proposal(s) left undecided for days — a 'no' is fine, a 'nothing' costs the week")
        if n.get("orders") and n.get("visits"):
            units = n.get("units", {})
            if len(units) < len(st.products()) - len(oos):
                unsold = [p["name"].split(" (")[0] for p in st.products() if p["stock"] > 0 and not units.get(p["name"])]
                if unsold:
                    out.append(f"{', '.join(unsold)} never appeared in a post, so never sold — every product needs its week in the light")
        if not out:
            return "None I can see in the ledger: orders shipped on time, nothing sold out, customers answered. The mistakes I can't see are the ones outside the shop — posts not made, photos not taken — tell me what you did and I'll be honest."
        return ("Mistakes this week, from the numbers (the ones I can see — no judgement on the rest):\n" + "\n".join(f"• {x}" for x in out[:5]) +
                "\nMine too: " + ("I should have nagged harder about the late orders." if late else "I could have proposed the fixes earlier instead of waiting to be asked.") + " Say “fix them” and I prepare labels, reorders and drafts in one go.")

    def asked_most(self, t, m):
        rows = self._msg_kinds(30)
        if not rows:
            return "No customer messages yet, so no pattern. In small home-goods shops the usual top three are: where is my order (40 %), does it fit/what size (25 %), returns (15 %) — the first one disappears when the tracking mail goes out the same day."
        kinds = {}
        for _, k in rows:
            kinds[k] = kinds.get(k, 0) + 1
        top = sorted(kinds.items(), key=lambda x: -x[1])
        names = {"where_is_my_order": "where is my order", "product_question": "product questions (size, material, does it fit)", "return_or_refund": "returns/refunds", "damaged_or_wrong": "damaged or wrong item",
                 "cancel_or_change": "cancel/change the order", "discount_request": "discount requests", "compliment": "compliments", "partnership_or_press": "collab/press", "spam_or_scam": "spam", "other": "other"}
        fix = {"where_is_my_order": "send the tracking number the same day and put 'delivery in 2–3 days after dispatch' on the product page — this kind halves",
               "product_question": "add the answers to the product page (a short FAQ under the description) — I can write it from the messages: say “write the FAQ”",
               "return_or_refund": "check the photos match reality (colour, size in cm next to a hand)",
               "damaged_or_wrong": "packaging — double box and padding for anything breakable",
               "discount_request": "a visible 'first order −10 % for newsletter' beats one-off haggling",
               "cancel_or_change": "a line 'changes possible within 2 hours of ordering' saves most of them"}
        lines = [f"What customers ask most ({len(rows)} messages in the last 30 days):"]
        for k, c in top[:4]:
            lines.append(f"• {names.get(k, k)}: {c} ({c / len(rows) * 100:.0f} %)")
        lines.append(f"What to do about the top one: {fix.get(top[0][0], 'answer it once on the page, then the mails stop')}.")
        return "\n".join(lines)

    def sales_drop(self, t, m):
        st = self.store
        od, vd = self._days()
        day = st.data.get("day", 0)
        if day < 2:
            return "Too early to talk about drops — the shop has had " + ("one practice day" if day == 1 else "no practice day") + "; a trend needs at least a few days."
        w = 3 if day >= 6 else 1
        a_days = range(day - w + 1, day + 1)
        b_days = range(day - 2 * w + 1, day - w + 1)
        a_o = sum(od.get(d, (0, 0))[0] for d in a_days); b_o = sum(od.get(d, (0, 0))[0] for d in b_days)
        a_s = sum(od.get(d, (0, 0))[1] for d in a_days); b_s = sum(od.get(d, (0, 0))[1] for d in b_days)
        a_v = sum(vd.get(d, 0) for d in a_days); b_v = sum(vd.get(d, 0) for d in b_days)
        span = f"days {a_days[0]}–{a_days[-1]} vs {b_days[0]}–{b_days[-1]}" if w > 1 else f"day {day} vs day {day - 1}"
        if a_s >= b_s * 0.9:
            return (f"They didn't, by the ledger: {a_o} orders / {_eur(a_s)} ({span}) against {b_o} / {_eur(b_s)} before — " + ("flat" if a_s < b_s * 1.1 else "actually up") +
                    f". Visits {a_v} vs {b_v}. Day-to-day swings of ±50 % are normal at this size; I only call it a drop after a full week under the previous one. If you saw a drop somewhere else (a marketplace, a social account), tell me where.")
        causes = []
        if a_v < b_v * 0.85:
            causes.append(f"fewer visitors ({a_v} vs {b_v}, {(1 - a_v / b_v) * 100:.0f} % down) — that's traffic: fewer posts, a post that flopped, or the algorithm; not the shop itself")
        conv_a = a_o / a_v * 100 if a_v else 0; conv_b = b_o / b_v * 100 if b_v else 0
        if a_v and conv_a < conv_b * 0.8:
            causes.append(f"visitors buy less ({conv_a:.1f} % vs {conv_b:.1f} %) — something on the page or at checkout changed, or the traffic is colder")
        oos = [p for p in st.products() if p["stock"] == 0]
        if oos:
            causes.append("sold out: " + ", ".join(p["name"].split(" (")[0] for p in oos) + " — visitors who came for those left")
        pc = [c for c in st.data.get("changes", []) if "price" in str(c.get("what", "")).lower()]
        if pc:
            causes.append(f"a price change on {pc[-1]['t'][:10]} ({pc[-1]['what'][:60]}) — if the drop started then, that's it")
        if not causes:
            causes.append("nothing in the ledger explains it (visits and conversion are steady, stock is fine) — small numbers wobble; watch two more days before changing anything")
        return f"Sales down: {a_o} orders / {_eur(a_s)} ({span}) vs {b_o} / {_eur(b_s)}. What the numbers point to:\n" + "\n".join(f"• {c}" for c in causes) + "\nFirst move: " + ("restock, then post." if oos else "post today (traffic is the fastest lever) and don't touch prices on one bad stretch.")

    def prices_right(self, t, m):
        st = self.store
        n = self._n() or {}
        units = n.get("units", {})
        high = bool(re.search(r"\b(high|expensive|overpriced|alti)\b", t.lower()))
        if not n.get("orders"):
            return "No sales yet, so the market hasn't voted. On paper: " + "; ".join(f"{p['name'].split(' (')[0]} {_eur(p['price'])} ({(p['price'] - p['cost']) / p['price'] * 100:.0f} % gross)" for p in st.products()) + ". Margins are healthy; whether the price is 'too high' only conversion can tell — run practice days."
        conv = n.get("conversion", 0)
        lines = []
        verdict = ("Not too high, by the numbers: " if conv >= 1.5 else "Possibly — ") + f"{conv:.1f} % of visitors buy" + (" (above the 1–3 % normal), and people who find prices too high simply don't buy." if conv >= 1.5 else ", under the normal 1.5–3 %: price, shipping surprise or photos — one of the three.")
        if not high:
            verdict = f"Too low? No: net margin is {n['profit'] / n['revenue'] * 100:.0f} % after goods, shipping and fees — healthy. " + ("A shop that converts at " + f"{conv:.1f} % could try +5–10 % on the best seller and watch a week." if conv >= 3 else "Keep them; test upward only when conversion is comfortably above 3 %.")
        lines.append(verdict)
        for p in st.products():
            sold = units.get(p["name"], 0)
            mg = (p["price"] - p["cost"]) / p["price"] * 100
            note = ("sells well → room to go up 5–10 %" if sold >= 3 else "sells → fine" if sold >= 1 else ("sold out, can't judge" if p["stock"] == 0 else "no sales → either unseen or too dear — post it once before cutting the price"))
            lines.append(f"• {p['name'].split(' (')[0]} {_eur(p['price'])} ({mg:.0f} % gross, {sold} sold): {note}")
        lines.append("Rule I use: cut a price only after the product has had its week in posts and still doesn't sell; raise one only on the best seller and only by a step (,90 endings).")
        return "\n".join(lines)

    def my_goal(self, t, m):
        n = self._n() or {}
        st = self.store
        aov = (n["revenue"] / n["orders"]) if n.get("orders") else 25.0
        margin = (n["profit"] / n["revenue"]) if n.get("revenue") else 0.5
        target_orders = 120
        return ("My goal for the shop, in order:\n"
                "1. Keep every promise on our own pages: every order shipped next day, every customer answered within the hour, every product listed is in stock. That's the reputation — the only thing a small shop has.\n"
                f"2. Turn it into a real income for you: from {n.get('orders', 0)} orders so far to ~{target_orders} a month, which at your basket ({_eur(aov)}) and margin ({margin * 100:.0f} %) is about {_eur(target_orders * aov * margin - 300)} a month after goods, shipping, fees and the INPS minimum. Then double it.\n"
                "3. Never spend your money or speak in public without your tap — and get so good at preparing things that your tap takes 10 seconds.\n"
                "4. Get smarter every week: learn from what you accept and reject, from the customers' messages, and from what I read in the quiet hours.\n"
                "What I'm NOT optimising for: sales at any margin, ads before the page converts, or a hundred products — three that sell beat thirty that don't.")

    def show_maths(self, t, m):
        n = self._n()
        st = self.store
        last = None
        try:
            last = self.last_reply()
        except Exception:
            pass
        if not n or not n.get("orders"):
            return "No sales yet, so the only maths I have is the price list: " + "; ".join(f"{p['name'].split(' (')[0]} {_eur(p['price'])} − cost {_eur(p['cost'])} = {_eur(p['price'] - p['cost'])} gross ({(p['price'] - p['cost']) / p['price'] * 100:.0f} %)" for p in st.products()) + "."
        rev, cogs, ship, fees, profit = n["revenue"], n["cogs"], n["shipping_cost"], n["fees"], n["profit"]
        losses = n.get("losses", 0)
        paid = self._paid()
        units = sum(l["qty"] for o in paid for l in o["lines"])
        conv = n["conversion"]
        head = "The maths behind it, line by line" + (f" (for “{last[0][:50]}”)" if last and last[0] and "€" in str(last[1]) else "") + ":\n"
        lines = [f"• sales: {len(paid)} paid orders, totals added up = {_eur(rev)} (goods + shipping the customers paid)",
                 f"• goods: for every order line, quantity × the cost you set per product → {units} units = {_eur(cogs)}",
                 f"• shipping we pay: € 2,90 per parcel + € 0,35 per unit → {len(paid)} × 2,90 + {units} × 0,35 = {_eur(ship)} (practice rates; give me your real contract and I swap them)",
                 f"• payment fees: 2,9 % of each total + € 0,30 → {_eur(fees)}"]
        if losses:
            lines.append(f"• refunds/cancellations: fees the gateway kept + goods and postage on parcels that had already left = {_eur(losses)}")
        lines.append(f"• profit = {_eur(rev)} − {_eur(cogs)} − {_eur(ship)} − {_eur(fees)}" + (f" − {_eur(losses)}" if losses else "") + f" = {_eur(profit)} → {profit / rev * 100:.0f} % of sales")
        lines.append(f"• conversion: {len(paid)} orders ÷ {n['visits']} visits × 100 = {conv:.1f} %")
        lines.append(f"• average basket: {_eur(rev)} ÷ {len(paid)} = {_eur(rev / len(paid))}; profit per order {_eur(profit / len(paid))}")
        lines.append("Not in there: your time, boxes (~€ 1 a parcel), the domain, ads, taxes — say “explain the numbers like I'm 5” for the plain version, or ask about one product and I do its line alone.")
        return head + "\n".join(lines)

    def not_convinced(self, t, m):
        last = None
        try:
            last = self.last_reply()
        except Exception:
            pass
        if not last or not last[1]:
            return "Fair — tell me which part and I'll show you what it rests on. I'd rather be corrected than trusted blindly."
        q, a = last
        a_l = a.lower()
        if re.search(r"€|\d+ orders?|\d+ visits|conversion", a_l):
            return ("Fair enough. What's solid in what I said: the counts and euros (from the ledger, nothing estimated). What's arguable: the conclusions I drew from them — small numbers, a few days, one shop. "
                    "So here's the test instead of my opinion: pick the smallest version of it, run it for a week, and look at the numbers with me on Friday. If it didn't move anything, we drop it and I'll say so. "
                    "And if you know something the ledger doesn't (a supplier, a customer's tone, the neighbourhood), tell me — that changes the answer more than my maths does.")
        if re.search(r"\b(law|legal|vat|tax|inps|forfettario|guarantee|withdraw)\b", a_l + q.lower()):
            return "Then don't take my word for it — this is a legal/tax point, and the right move is a 20-minute call with a commercialista with my summary in hand. I'll write it as three questions to ask: say “write the questions for the accountant”."
        return ("That's allowed. It's my judgement, not a fact — I can be wrong, especially about people and taste. Tell me what you'd do instead and I'll argue it honestly: "
                "if your version is better I'll say so and remember it for next time; if I still disagree I'll give you the one number that would settle it.")

    def discouraged(self, t, m):
        n = self._n() or {}
        st = self.store
        day = st.data.get("day", 0)
        facts = self._facts()
        bad = [f for f in facts if f[0] == "bad"]
        if not n.get("orders"):
            return ("I hear you. Two honest things: first, no shop sells before people see it — with zero visits the product isn't the problem, the door is. Second, the fix is boring and it works: one short video a day for 14 days, "
                    "same product, real room, and the shipping price visible on the page. Let's not decide anything about quitting on a day with no data. "
                    "Say “run a practice week” and “what should I post today?” and we look at real numbers together next week — if they're bad, I'll be the first to say what to change.")
        conv = n.get("conversion", 0)
        aov = n["revenue"] / n["orders"]
        good_bits = []
        if conv >= 1.5:
            good_bits.append(f"{conv:.1f} % of visitors buy — that's a shop that works; what's missing is visitors, not a better shop")
        if n["revenue"] and n["profit"] / n["revenue"] >= 0.4:
            good_bits.append(f"every order leaves {_eur(n['profit'] / n['orders'])} — the maths is healthy")
        per_day = n["orders"] / max(1, day)
        lines = [f"I get it — {n['orders']} orders in {day} day(s) feels like nothing when you're the one packing. Let me be straight rather than cheerful:"]
        if good_bits:
            lines.append("• what's actually good: " + "; ".join(good_bits) + ".")
        if bad:
            lines.append("• what's actually wrong: " + "; ".join(f[1].split(' — ')[0] for f in bad[:2]) + " — fixable this week, not a reason to quit.")
        lines.append(f"• the size of it: at {per_day:.1f} orders a day you're on the normal curve for month one; shops that make it don't sell more in week 1, they post more and don't stop.")
        lines.append("What I'd do today: one thing that changes the door, not the shop — say “what should I post today?” and I hand you the shot and caption; then leave the numbers alone for three days. "
                     "If in a month the visits are up and nothing sells, that's a real signal and we'll talk about changing products — with data, not on a bad evening.")
        return "\n".join(lines)

    def be_honest(self, t, m):
        facts = self._facts()
        n = self._n() or {}
        if not facts or (len(facts) == 1 and facts[0][2] == "run"):
            return "Honest: there's nothing to judge yet — no sales data. The honest risk is spending weeks polishing a shop nobody visits; the honest fix is posting daily from day one. Run practice days and ask me again; I'll be blunt."
        bad = [f for f in facts if f[0] == "bad"]
        good = [f for f in facts if f[0] == "good"]
        out = ["Honest, no cushion:"]
        if bad:
            out.append("• Bad: " + "; ".join(f[1] for f in bad[:3]) + ".")
        if good:
            out.append("• Good: " + "; ".join(f[1] for f in good[:2]) + ".")
        rev = n.get("revenue", 0)
        day = self.store.data.get("day", 0) or 1
        monthly = rev / day * 30
        out.append(f"• The size: {_eur(monthly)} of sales a month at this pace — " + ("pocket money, not an income yet. That's normal at the start and it's a traffic problem, not a product problem." if monthly < 1500 else "a real side income; the next step is repeat customers, not new products." if monthly < 5000 else "a real business — start acting like one (accountant, contracts, backup shipper)."))
        out.append("• About me: I see the ledger, not the world — I don't know how your photos look next to the competition or how you sound to customers. Where I'm guessing I'll say so; where I'm sure I'll say that too.")
        out.append("• What I'd stop doing: asking me for opinions more than once a day — the numbers change slowly; posting changes them faster.")
        return "\n".join(out)

    def differently(self, t, m):
        st = self.store
        day = st.data.get("day", 0)
        if day < 7:
            fx = self._facts()
            bad = [f for f in fx if f[0] == "bad"]
            return ("There isn't a full 'last week' yet (day " + str(day) + "), so from what I can see: " + ("; ".join(f[1].split(' — ')[0] for f in bad[:3]) + " — I'd fix those first and I'd propose them earlier instead of waiting to be asked." if bad else "nothing went wrong yet — I'd start posting daily from day one, that's the one thing every shop wishes it had done sooner.")
                    + " Ask again after a week and I compare the two weeks properly.")
        a = self._week(day - 7, day); b = self._week(day - 14, day - 7)
        out = ["Differently than last week:"]
        if b["orders"] and a["orders"] < b["orders"]:
            out.append(f"• Sales fell ({a['orders']} vs {b['orders']} orders): last week I'd have posted more mid-week — visits {a['visits']} vs {b['visits']} say the door was quieter.")
        elif b["orders"]:
            out.append(f"• Sales held or grew ({a['orders']} vs {b['orders']} orders) — I'd change less, not more; one lever at a time.")
        if a["late"]:
            out.append(f"• {a['late']} order(s) shipped late — I'd print the labels every morning before anything else; it's 10 minutes and it's the promise on the page.")
        if a["oos_days"]:
            out.append("• Something was sold out for part of the week — I'd reorder at 2 weeks of stock, not at zero.")
        if a["unanswered"]:
            out.append(f"• {a['unanswered']} customer message(s) waited — I'd approve drafts once a day at a fixed time.")
        if len(out) == 1:
            out.append("• Nothing I'd undo — the week ran clean. I'd add one thing: a post about the second product, so the shop isn't one item deep.")
        out.append("Me: I'd nag less about small things and earlier about the big ones (late orders, stock-outs).")
        return "\n".join(out)

    def _week(self, lo, hi):
        st = self.store
        orders = [o for o in st.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and lo < o.get("day", 0) <= hi]
        visits = sum(v for d, v in st.data.get("visits", {}).items() if lo < int(d) <= hi)
        late = sum(1 for o in orders if o["status"] == "paid" and st.data.get("day", 0) - o.get("day", 0) >= 1)
        oos_days = any(p["stock"] == 0 for p in st.products())
        unanswered = 0
        try:
            unanswered = len([r for r in self.inbox.items("new")]) if self.inbox is not None else 0
        except Exception:
            pass
        return {"orders": len(orders), "visits": visits, "late": late, "oos_days": oos_days, "unanswered": unanswered}

    def mute_kind(self, t, m):
        what = (m.group("what") or "").lower()
        kind = ("price" if re.search(r"pric|repric|prezz", what) else "stock" if re.search(r"stock|reorder|riordin|scort", what) else
                "ship" if re.search(r"ship|order remind", what) else "all")
        if self.memory is None:
            return None
        muted = set(self.memory.pref("mute_proposals", []) or [])
        if kind == "all":
            muted = {"price", "stock", "ship"}
        else:
            muted.add(kind)
        self.memory.set_pref("mute_proposals", sorted(muted))
        names = {"price": "price changes", "stock": "reorders / stock", "ship": "shipping reminders"}
        what_now = ", ".join(names[k] for k in sorted(muted))
        return (f"Understood — no more proposals about {names.get(kind, 'anything')} from me" + (f" (now muted: {what_now})" if kind != "all" else " (all three kinds muted)") +
                ". I'll still answer if you ask, and I'll still mention it once in the evening report when it costs money (a thin margin, a sold-out best seller). "
                "Say “propose price changes again” to switch it back on.")

    def unmute(self, t, m):
        if self.memory is None:
            return None
        low = t.lower()
        changed = []
        if re.search(r"\b(everything|all|every)\b", low) or not re.search(r"\b(price|stock|ship|replies|messages|yourself|alone|automatically)\b", low):
            if self.memory.pref("mute_proposals"):
                self.memory.set_pref("mute_proposals", []); changed.append("proposals of every kind are back on")
            if self.memory.pref("auto_routine"):
                self.memory.set_pref("auto_routine", False); changed.append("every customer reply comes to you again before it goes out")
        else:
            muted = set(self.memory.pref("mute_proposals", []) or [])
            for k in ("price", "stock", "ship"):
                if k in low and k in muted:
                    muted.discard(k); changed.append(f"{k} proposals back on")
            if re.search(r"\b(replies|messages|yourself|alone|automatically|answering)\b", low) and self.memory.pref("auto_routine"):
                self.memory.set_pref("auto_routine", False); changed.append("every customer reply comes to you again before it goes out")
            self.memory.set_pref("mute_proposals", sorted(muted))
        if not changed:
            return "Nothing was switched off — you already see everything: every proposal and every reply before it goes out."
        return "Done: " + "; ".join(changed) + "."

    def auto_routine(self, t, m):
        if self.memory is None:
            return None
        self.memory.set_pref("auto_routine", True)
        return ("OK — from now on I send the routine replies myself: where-is-my-order (with the tracking from the ledger), product questions answered from the product page, shipping/returns information. "
                "Each one still shows up in your chat afterwards, marked 'sent by me', so you can read it and tell me if you'd have said it differently — I learn from that.\n"
                "Still yours to approve, always: refunds and returns with money in them, damaged/wrong items, cancellations, complaints, anything angry, discounts, press/collab, and anything my checks flag. "
                "Say “ask me everything again” to switch it back.")

    def auto_scope(self, t, m):
        on = bool(self.memory and self.memory.pref("auto_routine"))
        return ((f"Right now: {'ON — I send the routine ones myself' if on else 'OFF — every reply waits for your tap'}.\n" if self.memory else "") +
                "What counts as routine (sent by me only when switched on, and only when my checks find nothing wrong):\n"
                "• where is my order — with the tracking number and dates from the ledger\n• product questions answered from the product page (material, size, care)\n• shipping and returns information straight from the shop pages\n• thank-you notes / compliments\n"
                "Never on my own: refunds, returns with money, damaged or wrong items, cancellations, complaints, angry tone, discount requests, press/collab, anything the checks flag, anything I'm not sure about.\n"
                + ("Say “ask me everything again” to switch it off." if on else "Say “answer the routine replies yourself” to switch it on — each one still shows up in your chat afterwards."))

    def auto_log(self, t, m):
        if self.inbox is None:
            return None
        try:
            today = time.strftime("%Y-%m-%d")
            decs = self.inbox.decisions() if hasattr(self.inbox, "decisions") else []
        except Exception:
            decs = []
        mine = [d for d in decs if str(d.get("note", "")).startswith("auto") and str(d.get("t", "")).startswith(today)]
        if not mine:
            on = bool(self.memory and self.memory.pref("auto_routine"))
            return "Nothing sent on my own today" + (" — every reply went through your tap." if not on else " — nothing routine came in (or my checks flagged the ones that did, so they waited for you).")
        lines = []
        for d in mine[-8:]:
            body = re.sub(r"^\s*(?:Hi|Hello|Dear|Buongiorno|Salve|Ciao)[^\n]*\n+", "", (d.get("text") or "").strip())   # skip the greeting line, show the substance
            lines.append(f"• {d.get('kind', '').replace('_', ' ')} → {d.get('id', '')}: “{body[:120].strip()}…”")
        return f"Sent by me today ({len(mine)}):\n" + "\n".join(lines) + "\nTell me if you'd have said any of them differently and I adjust."

    def auto_off(self, t, m):
        if self.memory is None:
            return None
        was = self.memory.pref("auto_routine")
        self.memory.set_pref("auto_routine", False)
        return ("OK — every customer reply comes to you again before it goes out." if was else "It was already off — nothing goes out without your tap.")

    def fix_them(self, t, m):
        facts = self._facts()
        st = self.store
        acts = []
        for f in facts:
            if f[2] == "ship":
                acts.append("labels + packing slips for the waiting orders (say “all shipped” when they're with GLS)")
            elif f[2] == "restock":
                acts.append("a reorder proposal for what's sold out — quantities from the sales pace, you tap Apply")
            elif f[2] == "reorder":
                acts.append("a reorder proposal for what's nearly out")
            elif f[2] == "inbox":
                acts.append("the customer drafts, one by one with Approve / Edit / Reject")
            elif f[2] == "proposals":
                acts.append("the open proposals again, so you can tap them")
        if not acts:
            return "There's nothing broken to fix right now — orders shipped, stock fine, inbox empty. If you meant something specific, name it."
        return {"fix_all": True, "text": "On it — in order: " + "; ".join(acts) + "."}

    def email_past_customers(self, t, m):
        st = self.store
        n = self._n() or {}
        units = n.get("units", {})
        shop = st.data.get("name", "Green Nest")
        low = t.lower()
        back = [p for p in st.products() if p["stock"] > 0 and re.search(r"\bback in stock\b", low)]
        best = max(units, key=units.get).split(" (")[0] if units else "the bamboo toothbrush set"
        new_item = next((p for p in st.products() if p["stock"] > 0 and not units.get(p["name"])), None)
        hook = (f"{back[0]['name'].split(' (')[0]} is back" if back else f"Something new next to your {best}")
        body = (f"Subject: {hook} — and a small thank-you\n\n"
                f"Hi {{first name}},\n\n"
                f"A few weeks ago you ordered from {shop} — thank you, really: a small shop notices every single order.\n\n"
                + (f"Quick news: the {back[0]['name'].split(' (')[0]} is back in stock (we had run out — sorry to anyone who looked for it).\n\n" if back else
                   (f"Quick news: we've added the {new_item['name'].split(' (')[0]} ({_eur(new_item['price'])}) — it sits well next to the {best} you have.\n\n" if new_item else f"Quick news: the {best} now ships the same day, and free over the threshold you'll see in the cart.\n\n"))
                + "As a thank-you, the code BACK10 takes 10 % off your next order until Sunday. No pressure — if you'd rather not hear from us, the unsubscribe link is below and it works.\n\n"
                "One favour: if something wasn't perfect with your last parcel, reply to this e-mail and tell me — I read every reply.\n\n"
                f"Warmly,\n{{your name}}, {shop}\n\n(unsubscribe link)")
        return ("E-mail to past customers — short, one piece of news, one code, one question:\n\n" + body +
                "\n\nSend it once, Tuesday–Thursday morning, only to people who bought (that's legitimate interest under GDPR; the unsubscribe link is mandatory). "
                "Expect 30–40 % opens and 3–8 % of them ordering. Say “make it Italian” or “change the code” and I redo it; say “send it” and I prepare the list for your tap.")

    def email_review_request(self, t, m):
        st = self.store
        shop = st.data.get("name", "Green Nest")
        it = bool(re.search(r"\b(italian|in italiano|italiano)\b", t.lower()))
        if it:
            body = (f"Oggetto: Com'è andata con il tuo ordine {shop}?\n\n"
                    "Ciao {nome},\n\n"
                    "Il tuo {prodotto} dovrebbe essere arrivato da qualche giorno — spero ti stia piacendo.\n\n"
                    "Ti chiedo un favore piccolo ma per noi enorme: una recensione onesta, anche di due righe (una foto vale doppio). Bastano 30 secondi: {link recensione}\n\n"
                    "Se invece qualcosa non è andato bene, rispondi a questa mail prima di lasciare la recensione: lo sistemiamo, sempre.\n\n"
                    f"Grazie davvero,\n{{il tuo nome}}, {shop}")
        else:
            body = (f"Subject: How's your {shop} order working out?\n\n"
                    "Hi {first name},\n\n"
                    "Your {product} should have arrived a few days ago — I hope it's already in use.\n\n"
                    "A small favour that's huge for a small shop: an honest review, even two lines (a photo counts double). It takes 30 seconds: {review link}\n\n"
                    "And if anything wasn't right, reply to this e-mail before you review — we fix it, always.\n\n"
                    f"Thank you,\n{{your name}}, {shop}")
        return ("Review request e-mail — send it 5–7 days after delivery, one per order, never twice:\n\n" + body +
                "\n\nRules I kept: no reward for the review itself (an EU no-no when undisclosed), a way to complain privately first, one link, no images. Expect 5–10 % of buyers to leave one. "
                + ("Say “in English” for the English version." if it else "Say “in Italian” for the Italian version.") + " When the real shop has a review link, I fill it in and queue them automatically after delivery — with your tap on the first few.")

    def remember_topic(self, t, m):
        topic = (m.group("topic") or m.group("topic2") or m.group("topic3") or "").strip(" ?.!")
        out = []
        try:
            for r in (self.memory.notes(topic, limit=3) if self.memory else []):
                if r.get("kind") in ("owner", "decision", "owner_said") or topic.lower() in (r.get("topic", "") + " " + r.get("text", "")).lower():
                    out.append(f"• {r['t'][:10]}: {r['text'][:200]}")
        except Exception:
            pass
        try:
            for x in (self.memory.todo.get("items", []) if self.memory else []):
                if topic.lower() in x["text"].lower():
                    out.append(f"• to-do #{x['id']} ({x['status']}): {x['text'][:120]}")
        except Exception:
            pass
        try:
            for c in reversed(self.store.data.get("changes", [])[-30:]):
                if topic.lower() in (str(c.get("what", "")) + " " + str(c.get("why", ""))).lower():
                    out.append(f"• store change {c['t'][:10]}: {c['what'][:100]}")
        except Exception:
            pass
        if not out:
            return (f"Honestly, no — I have nothing written down from you about “{topic}”. I keep what you tell me only when it's a to-do, a decision, a reminder or a store change; plain chat I don't store. "
                    f"Tell me again in one line (“note: the supplier …”) and I'll keep it under “{topic}”.")
        return f"What I have from you about “{topic}”:\n" + "\n".join(dict.fromkeys(out[:6]))

    def key_number(self, t, m):
        n = self._n() or {}
        st = self.store
        conv = n.get("conversion", 0)
        if not n.get("orders"):
            return ("One number: visits a day. Before the first sales nothing else can move — no visits, no data. Watch it every evening; when it's above ~50 a day, switch to conversion (buyers ÷ visitors). "
                    "Say “how many visitors did we get today?” each evening and I'll tell you.")
        margin = n["profit"] / n["revenue"] if n["revenue"] else 0
        day = st.data.get("day", 0) or 1
        per_day = n["orders"] / day
        if conv < 1.2:
            pick = ("conversion", f"{conv:.1f} % — under 1,2 % it means visitors arrive and leave; every euro on traffic is wasted until it's ~2 %. Watch it weekly (daily is noise), fix the page, not the ads.")
        elif margin < 0.35:
            pick = ("net margin per order", f"{_eur(n['profit'] / n['orders'])} ({margin * 100:.0f} %) — thin; one refund eats three sales. Watch it every time you change a price or a shipping rule.")
        elif per_day < 3:
            pick = ("visits a day", f"~{n['visits'] / day:.0f} — the shop converts ({conv:.1f} %) and earns ({margin * 100:.0f} %), so the only thing between you and more orders is people at the door. Watch it daily; each post should show up in it.")
        else:
            pick = ("repeat rate", "how many buyers come back within 60 days — at this volume growth comes from the second order, which costs nothing; watch it monthly, aim for 15–20 %.")
        return (f"One number to watch right now: {pick[0]} — {pick[1]}\n"
                "The other two on the dashboard, not to obsess over: orders a day (the pulse) and net margin (the health). Everything else — followers, likes, page views — is weather.\n"
                "It changes as the shop grows: visits first, then conversion, then margin, then repeat rate — ask me again in a month.")

    def refund_losses(self, t, m):
        st = self.store
        orders = st.data["orders"]
        if not orders:
            return "No orders yet, so no refunds and nothing lost."
        ref = [o for o in orders if o["status"] == "refunded"]
        canc = [o for o in orders if o["status"] == "cancelled"]
        if not ref and not canc:
            return f"Nothing lost on refunds so far: 0 refunds and 0 cancellations out of {len(orders)} orders. Keep it that way with double boxes for anything breakable and same-day tracking mails — the two causes of most refunds."
        fees = sum(0.029 * o["total"] + 0.30 for o in ref + canc)
        shipped = [o for o in ref if o.get("tracking")]
        post = sum(2.9 + 0.35 * sum(l["qty"] for l in o["lines"]) for o in shipped)
        goods = sum(l["qty"] * l.get("cost", 0) for o in shipped for l in o["lines"])
        total = fees + post + goods
        refunded_money = sum(o["total"] for o in ref)
        return (f"Refunds and cancellations so far: {len(ref)} refund(s) ({_eur(refunded_money)} given back) and {len(canc)} cancellation(s) out of {len(orders)} orders.\n"
                f"What it actually cost us (the refund itself is the customer's money going back, not a loss):\n"
                f"• payment fees the gateway kept: {_eur(fees)}\n"
                + (f"• postage on {len(shipped)} parcel(s) that had already left: {_eur(post)}\n• goods on those parcels (not back on the shelf in the practice store): {_eur(goods)}\n" if shipped else "• no postage or goods lost — everything was cancelled before shipping\n")
                + f"Total lost: {_eur(total)} — {total / max(1, len(ref) + len(canc)):.2f} € per case. "
                + ("Under 3 % of orders is normal for home goods." if (len(ref) + len(canc)) / len(orders) < 0.03 else "That's above the 2–5 % normal — ask me “did anyone complain?” to see the reasons."))

    def paid_twice(self, t, m):
        return ("Double payment — do this, in order:\n"
                "1. Check before believing it: in the payment provider (Stripe/PayPal) look for two charges with the same amount minutes apart. Often it's one charge plus a pending authorisation that disappears in 3–5 days — no refund needed, just tell the customer.\n"
                "2. If there really are two orders: cancel the duplicate order and refund the second charge in full from the provider (not a bank transfer — provider refunds are traceable and free of dispute risk). Do it today; a customer who paid twice is one click from a chargeback.\n"
                "3. Keep the first order moving — ship it, don't hold it hostage to the refund.\n"
                "4. Write to them: “You're right — the second payment is refunded, it shows on your card in 5–10 business days; your order ships as planned. Sorry for the scare.” I'll draft it: say “customer paid twice, write the reply”.\n"
                "5. Refund costs you the fee on the duplicate (~2,9 % + € 0,30) — annoying, not worth arguing over.\n"
                "Give me the order number and I prepare the cancel + refund proposal for your tap.")

    def pep_talk(self, t, m):
        n = self._n() or {}
        st = self.store
        day = st.data.get("day", 0)
        if not n.get("orders"):
            return ("Here's the honest pep talk: you've done the part most people never do — the shop exists, the prices are set, the pages are written. Everyone else is still 'thinking about it'. "
                    "What's left isn't clever, it's daily: one post, one parcel, one reply. Nobody's first month is impressive; the ones who make it are simply still there in month three. "
                    "Run a practice day, post once today, and let me carry the boring parts.")
        good = []
        if n.get("conversion", 0) >= 1.5:
            good.append(f"{n['conversion']:.1f} % of visitors buy — that's a shop people trust on first sight")
        if n["revenue"] and n["profit"] / n["revenue"] >= 0.4:
            good.append(f"{n['profit'] / n['revenue'] * 100:.0f} % stays as profit — the maths works, which is rarer than it sounds")
        units = n.get("units", {})
        if units:
            best = max(units, key=units.get).split(" (")[0]
            good.append(f"{units[max(units, key=units.get)]} people chose the {best} — strangers, with their own money")
        return (f"Pep talk, with facts (I don't do the empty kind): {n['orders']} orders in {day} day(s). " + ("; ".join(good) + ". " if good else "") +
                "Everything that's not working is a traffic problem, and traffic is the one problem that gives in to plain stubbornness — a post a day, for weeks. "
                "You don't need a better idea; you need the same idea for 60 more days. I'll take the numbers, the drafts and the labels; you take the camera. Say “what should I post today?” — that's today's whole job.")

    # ---- round 16: proposals, reminders and lists in plain words --------------------------------------------------
    def _last_open(self):
        props = [p for p in self.store.data.get("proposals", []) if p["status"] == "open"] if self.store is not None else []
        return props[-1] if props else None

    def _prop_line(self, p):
        st = self.store
        k, t, ch = p["kind"], p["target"], p["change"]
        try:
            if k in ("price", "stock", "cost"):
                pr = st.product(t)
                name = pr["name"].split(" (")[0] if pr else t
                if p.get("before") is not None:
                    cur = _eur(float(p["before"])) if k != "stock" else str(int(p["before"]))
                else:
                    cur = {"price": _eur(pr["price"]), "stock": str(pr["stock"]), "cost": _eur(pr.get("cost", 0))}[k] if pr else "?"
                new = _eur(float(ch)) if k != "stock" else str(int(ch))
                return f"{k} of {name}: {cur} → {new}"
            if k in ("ship", "cancel", "refund"):
                return f"{k} order #{t}"
            if k == "shipping":
                d = json.loads(ch) if isinstance(ch, str) else dict(ch)
                return f"shipping {t}: " + ", ".join(f"{a} {b}" for a, b in d.items())
            if k == "product":
                d = json.loads(ch) if isinstance(ch, str) else dict(ch)
                return f"new product “{d.get('name', '?')}” at {_eur(float(d.get('price', 0)))}"
            if k == "page":
                return f"page '{t}' rewrite ({len(str(ch))} chars)"
            if k == "description":
                pr = st.product(t)
                return f"new description for {pr['name'].split(' (')[0] if pr else t}"
            if k == "code":
                d = json.loads(ch) if isinstance(ch, str) else dict(ch)
                if d.get("off"):
                    return f"switch off code {t}"
                return f"code {t}: " + (f"{float(d.get('pct', 0)):g} % off" if d.get("pct") else f"{_eur(float(d.get('fixed', 0)))} off") + (f" over {_eur(float(d['min']))}" if d.get("min") else "")
            if k == "gift_wrap":
                d = json.loads(ch) if isinstance(ch, str) else dict(ch)
                return f"gift wrap {'on at ' + _eur(float(d.get('price', 0))) if d.get('active') else 'off'}"
            if k == "notice":
                d = json.loads(ch) if isinstance(ch, str) else dict(ch)
                return f"shop notice “{d.get('text', '')[:50]}”" if d.get("text") else "remove the shop notice"
            if k == "logo":
                return "logo on the shop header" if ch else "logo off the shop header"
        except Exception:
            pass
        return f"{k} {t} → {str(ch)[:60]}"

    def approve_last(self, t, m):
        if self.store is None:
            return None
        p = self._last_open()
        if not p:
            return "Nothing is waiting for a tap — no open proposal. Say “what's pending?” any time, or “review the shop” and I look for things to propose."
        out = self.store.apply(p["id"])
        self._log_decision("applied", p, out)
        left = len([x for x in self.store.data["proposals"] if x["status"] == "open"])
        return f"✅ Applied: {out}." + (f" {left} more still open — say “what's pending?”." if left else " Nothing else open.") + " (Say “undo that” within the hour if it was a slip.)"

    def reject_last(self, t, m):
        if self.store is None:
            return None
        p = self._last_open()
        if not p:
            return "Nothing open to reject — the list is clean."
        self.store.reject(p["id"])
        self._log_decision("rejected", p, self._prop_line(p))
        why = ""
        if p["kind"] == "price":
            why = " I'll hold back on price proposals for that product."
        return f"❌ Left as it is: {self._prop_line(p)}.{why} " + ("Nothing else open." if not self._last_open() else "One more is open — say “what's pending?”.")

    def _log_decision(self, action, p, line):
        try:
            self.store.data.setdefault("decisions", []).append({"t": _dt.datetime.now().isoformat(timespec="minutes"), "action": action, "kind": p["kind"], "target": p["target"], "line": str(line)[:160], "id": p["id"]})
            self.store.save()
        except Exception:
            pass

    def undo_last(self, t, m):
        if self.store is None:
            return None
        st = self.store
        applied = [p for p in st.data.get("proposals", []) if p["status"] == "applied" and p["kind"] in ("price", "stock", "cost", "shipping", "description", "page", "code", "gift_wrap", "notice", "logo")]
        if not applied:
            return "Nothing to undo — no change of price, stock, cost, shipping, text, code, gift wrap or notice has been applied yet (orders shipped/refunded can't be un-done from here)."
        p = applied[-1]
        k, tg, ch = p["kind"], p["target"], p["change"]
        try:
            if p.get("before") is None and k not in ("code", "logo"):
                return f"I can't undo that one safely ({self._prop_line(p)}) — it was applied before I kept 'before' values. Tell me the value to set and I propose it."
            before = p["before"]
            if k in ("price", "cost", "stock"):
                newp = st.propose(k, tg, before if k != "stock" else int(before), f"undo of {p['id']}: back to the previous value")
            elif k == "shipping":
                newp = st.propose("shipping", tg, json.dumps({"cost": before[1], "free_over": before[2]}), f"undo of {p['id']}: back to the previous shipping row")
            elif k == "code":
                if before is None or not before.get("active"):          # the code did not exist / was off before → switch it off again
                    newp = st.propose("code", tg, json.dumps({"off": True}), f"undo of {p['id']}: code off again")
                else:
                    newp = st.propose("code", tg, json.dumps({"pct": before.get("pct", 0), "fixed": before.get("fixed", 0), "min": before.get("min", 0), "max_uses": before.get("max_uses"), "note": before.get("note", "")}), f"undo of {p['id']}: code back on")
            elif k in ("gift_wrap", "notice"):
                newp = st.propose(k, tg, json.dumps(before), f"undo of {p['id']}: back to the previous setting")
            elif k == "logo":
                newp = st.propose("logo", tg, before or "", f"undo of {p['id']}: previous header")
            else:
                newp = st.propose(k, tg, before, f"undo of {p['id']}: back to the previous text")
            out = st.apply(newp["id"])
            p["status"] = "undone"
            st.save()
            self._log_decision("undone", p, out)
            return f"↩️ Undone: {out}. (The change and the undo both stay in the log.)"
        except Exception as e:
            return f"Undo failed on my side ({str(e)[:60]}) — tell me the value to set and I propose it."

    def pending(self, t, m):
        out = []
        try:
            props = [p for p in self.store.data.get("proposals", []) if p["status"] == "open"] if self.store is not None else []
            if props:
                out.append(f"Open proposals ({len(props)}) — newest last; “approve that” takes the last one:")
                out += [f"• {self._prop_line(p)}" for p in props[-8:]]
        except Exception:
            pass
        try:
            drafts = self.inbox.items("new") if self.inbox is not None else []
            if drafts:
                out.append(f"Customer drafts waiting: {len(drafts)} — say “show me the drafts”.")
        except Exception:
            pass
        try:
            due = [x for x in (self.memory.open_items() if self.memory else []) if x.get("due")]
            if due:
                out.append("Reminders: " + "; ".join(f"{x['text'][:50]}" for x in due[:3]))
        except Exception:
            pass
        return "\n".join(out) if out else "Nothing pending — no open proposal, no draft waiting, no reminder due. Enjoy it."

    def last_proposal(self, t, m):
        if self.store is None:
            return None
        props = self.store.data.get("proposals", [])
        if not props:
            return "I haven't proposed anything yet."
        p = props[-1]
        state = {"open": "still open — “approve that” or “reject it”", "applied": "already applied", "rejected": "you left it as it was", "undone": "undone", "failed": "failed to apply"}.get(p["status"], p["status"])
        return f"Last proposal: {self._prop_line(p)} — {state}. Why I proposed it: {p.get('why', '')[:200]}"

    def decisions_log(self, t, m):
        if self.store is None:
            return None
        low = t.lower()
        days = 1 if re.search(r"\btoday|oggi\b", low) else 7 if re.search(r"\bweek|settimana\b", low) else 30
        cutoff = (_dt.datetime.now() - _dt.timedelta(days=days)).isoformat(timespec="minutes")
        want = "rejected" if re.search(r"\breject|declin|say no|rifiut", low) else "applied" if re.search(r"\bapprov|appl|accept|confirm|change", low) else None
        rows = []
        for p in self.store.data.get("proposals", []):
            if p["status"] in ("applied", "rejected", "undone") and (p.get("applied_at") or p.get("t", ""))[:16] >= cutoff[:16]:
                if want is None or p["status"] == want or (want == "applied" and p["status"] == "undone"):
                    rows.append(p)
        label = {1: "today", 7: "this week", 30: "in the last 30 days"}[days]
        if not rows:
            return f"No {want or 'approved or rejected'} proposals {label}." + (" The shop is unchanged." if want != "rejected" else "")
        return (f"{'Approved' if want == 'applied' else 'Rejected' if want == 'rejected' else 'Decided'} {label} ({len(rows)}):\n" +
                "\n".join(f"• {'↩️' if str(p.get('why', '')).startswith('undo of') else '✅' if p['status'] == 'applied' else '✅→↩️ (then undone)' if p['status'] == 'undone' else '❌'} {self._prop_line(p)}" for p in rows[-10:]))

    def proposal_stats(self, t, m):
        if self.store is None:
            return None
        low = t.lower()
        days = 7 if re.search(r"\bweek|settimana\b", low) else 1 if re.search(r"\btoday|oggi\b", low) else None
        props = self.store.data.get("proposals", [])
        if days:
            cutoff = (_dt.datetime.now() - _dt.timedelta(days=days)).isoformat(timespec="minutes")
            props = [p for p in props if p.get("t", "")[:16] >= cutoff[:16]]
        if not props:
            return "No proposals " + ("this week" if days == 7 else "today" if days == 1 else "yet") + "."
        n = len(props); a = sum(p["status"] == "applied" for p in props); r = sum(p["status"] == "rejected" for p in props); o = sum(p["status"] == "open" for p in props)
        kinds = {}
        for p in props:
            kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
        by_kind = ", ".join(f"{k} ×{v}" for k, v in sorted(kinds.items(), key=lambda x: -x[1]))
        rate = f"{a / (a + r) * 100:.0f} % of the decided ones approved" if a + r else "none decided yet"
        if re.search(r"\breject|say no|turn down|rifiut", low):
            rk = {}
            for p in props:
                if p["status"] == "rejected":
                    rk[p["kind"]] = rk.get(p["kind"], 0) + 1
            return f"You rejected {r} of {n} proposal(s)" + (f" ({', '.join(f'{k} ×{v}' for k, v in rk.items())})" if rk else "") + f"; {a} approved, {o} still open. " + ("I propose rejected kinds less often — say “stop proposing price changes” to switch one off entirely." if r else "")
        return f"{n} proposal(s)" + (" this week" if days == 7 else " today" if days == 1 else " so far") + f": {a} approved, {r} rejected, {o} open — {rate}. By kind: {by_kind}."

    def _last_reminder(self):
        items = [x for x in (self.memory.open_items() if self.memory else []) if x.get("due")]
        return items[-1] if items else None

    def move_reminder(self, t, m):
        if self.memory is None:
            return None
        x = self._last_reminder()
        if not x:
            return "There's no reminder to move — say “remind me friday to call the accountant” first."
        when = (m.group("when") or "").lower()
        tm = m.group("time")
        now = _dt.datetime.now()
        days_en = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        days_it = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
        old = _dt.datetime.fromisoformat(x["due"]) if x.get("due") else now.replace(hour=9, minute=0)
        if when in ("tomorrow", "domani"):
            day = (now + _dt.timedelta(days=1)).date()
        elif when in ("today", "tonight"):
            day = now.date()
        elif when in days_en or when in days_it:
            wd = days_en.index(when) if when in days_en else days_it.index(when)
            delta = (wd - now.weekday()) % 7 or 7
            day = (now + _dt.timedelta(days=delta)).date()
        elif when in ("next week", "la settimana prossima"):
            day = (now + _dt.timedelta(days=(7 - now.weekday()))).date()
        elif when == "next month":
            day = (now.replace(day=1) + _dt.timedelta(days=32)).replace(day=1).date()
        else:
            mm = re.match(r"(\d{1,2})[/.](\d{1,2})", when)
            if mm:
                day = _dt.date(now.year, int(mm.group(2)), int(mm.group(1)))
                if day < now.date():
                    day = day.replace(year=now.year + 1)
            else:
                mm = re.match(r"(\d{1,2}) ([a-z]{3})", when)
                months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
                day = _dt.date(now.year, months.index(mm.group(2)) + 1, int(mm.group(1))) if mm else old.date()
        hour, minute = old.hour, old.minute
        if tm:
            hh = re.split(r"[:.]", tm)
            hour, minute = int(hh[0]), int(hh[1]) if len(hh) > 1 else 0
        due = _dt.datetime.combine(day, _dt.time(hour, minute))
        x["due"] = due.isoformat(timespec="minutes")
        x["text"] = re.sub(r"\s*\(⏰ [^)]*\)", "", x["text"]) + f" (⏰ {due:%a %d %b %H:%M})"
        self.memory._save()
        return f"Moved: “{re.sub(r'\s*\(⏰ [^)]*\)', '', x['text'])}” now rings {due:%A %d %B at %H:%M}."

    def delete_todo(self, t, m):
        if self.memory is None:
            return None
        gd = m.groupdict()
        items = self.memory.open_items()
        x = None
        if gd.get("n"):
            x = next((i for i in items if i["id"] == int(gd["n"])), None)
        elif gd.get("what"):
            words = [w for w in re.findall(r"[a-zà-ú]{4,}", gd["what"].lower()) if w not in ("with", "that", "this", "about", "the")]
            x = next((i for i in items if words and sum(w in i["text"].lower() for w in words) >= max(1, len(words) - 1)), None)
        else:
            x = self._last_reminder() or (items[-1] if items else None)
        if not x:
            return "I couldn't find that on the list — say “what's on my list?” and then “delete 3”."
        x["status"], x["deleted_t"] = "deleted", _dt.datetime.now().isoformat(timespec="minutes")
        self.memory._save()
        left = len(self.memory.open_items())
        return f"Removed: {re.sub(r'\s*\(⏰ [^)]*\)', '', x['text'])}." + (f" {left} left." if left else " The list is empty.")

    def all_done(self, t, m):
        if self.memory is None:
            return None
        items = self.memory.open_items()
        if not items:
            return "The list was already empty."
        for x in items:
            self.memory.done(x["id"])
        return f"Ticked off all {len(items)}: " + "; ".join(re.sub(r'\s*\(⏰ [^)]*\)', '', x["text"])[:40] for x in items[:6]) + (" …" if len(items) > 6 else "") + ". Clean slate."

    def clear_list(self, t, m):
        if self.memory is None:
            return None
        items = self.memory.open_items()
        if not items:
            return "The list is already empty."
        for x in items:
            x["status"], x["deleted_t"] = "deleted", _dt.datetime.now().isoformat(timespec="minutes")
        self.memory._save()
        return f"Cleared {len(items)} item(s) (not ticked as done — just removed). Say “what's on my list?” to check."

    def read_page(self, t, m):
        if self.store is None:
            return None
        gd = m.groupdict()
        key = (gd.get("page") or gd.get("page2") or gd.get("page3") or gd.get("page4") or "").lower()
        key = {"delivery": "shipping", "spedizioni": "shipping", "return": "returns", "resi": "returns", "refund": "returns", "refunds": "returns", "rimborsi": "returns", "contatti": "contact", "termini": "terms"}.get(key, key)
        pages = self.store.data.get("pages", {})
        txt = pages.get(key)
        if not txt:
            return f"There's no '{key}' page in the practice shop — the pages are: {', '.join(pages.keys())}. Say “write the {key} page” and I draft one from the rules."
        return f"The {key} page says:\n{txt[:1200]}" + ("\n…" if len(txt) > 1200 else "") + "\nSay “change the returns window to 14 days” or “rewrite the shipping page” and I prepare the change."

    def returns_window(self, t, m):
        if self.store is None:
            return None
        gd = m.groupdict()
        n = int(gd.get("n") or gd.get("n2") or gd.get("n3") or 0)
        if n < 14:
            return f"{n} days isn't allowed for consumers in the EU — the legal minimum is 14 days from delivery (right of withdrawal). I can set 14; 30 is what most small shops promise because it reads as confidence."
        pages = self.store.data.get("pages", {})
        cur = pages.get("returns", "")
        mm = re.search(r"within (\d+) days", cur)
        old = int(mm.group(1)) if mm else None
        if old == n:
            return f"The returns window is already {n} days."
        new = re.sub(r"within \d+ days", f"within {n} days", cur) if mm else cur + f"\nYou can return any unused item within {n} days of delivery for a full refund."
        prop = self.store.propose("page", "returns", new, f"you asked: returns window {old or '?'} → {n} days")
        return {"proposal": prop["id"], "text": f"🏪 Returns window {old or '?'} → {n} days. The returns page and customer replies follow.\nApply it?"}

    def waiting_longest(self, t, m):
        if self.store is None:
            return None
        st = self.store
        day = st.data.get("day", 0)
        rows = [o for o in st.data["orders"] if o["status"] == "paid"]
        if not rows:
            return "Nobody is waiting — every paid order is shipped."
        rows.sort(key=lambda o: o.get("day", 0))
        out = [f"Waiting longest ({len(rows)} unshipped):"]
        for o in rows[:6]:
            wait = day - o.get("day", day)
            c = o.get("customer") or {}
            out.append(f"• #{o['n']} {c.get('name', '?')} ({o.get('country') or c.get('country', '?')}) — {wait} practice day(s), {_eur(o.get('total', 0))}" + (" ⚠️ past the promise" if wait >= 1 else ""))
        out.append("Say “print the shipping labels” and I prepare all of them.")
        return "\n".join(out)

    def order_lookup(self, t, m):
        """'how much did order 51003 pay?', 'who placed order 51003?' — the phrasings talk.order_info doesn't catch; it stays the owner of 'status/total/details of order N'."""
        if self.store is None:
            return None
        try:
            from .talk import Talk
            if Talk.ORDER_Q.search(t):
                return None                                                   # talk.py answers those (with our-side costs and events)
        except Exception:
            pass
        gd = m.groupdict()
        n = next((gd[k] for k in ("n", "n2", "n3", "n4", "n5", "n6") if gd.get(k)), None)
        if not n:
            return None
        o = self.store.order(int(n))
        if not o:
            return f"There's no order #{n} in the practice shop (orders start at #51001)."
        c = o.get("customer") or {}
        lines = "; ".join(f"{l['qty']} × {l.get('name', l['id'])} at {_eur(l['price'])}" for l in o["lines"])
        low = t.lower()
        country = o.get("country") or c.get("country", "?")
        if re.search(r"\bwho|whose|chi\b", low):
            return f"Order #{n}: {c.get('name', '?')} ({country}, {c.get('email', '?')}) — {lines}; {_eur(o.get('total', 0))}, {o['status']}."
        return (f"Order #{n}: {_eur(o.get('total', 0))} total ({lines}" + (f"; shipping {_eur(o.get('shipping', 0))}" if o.get("shipping") is not None else "") +
                f"), placed day {o.get('day', '?')}, status {o['status']}" + (f", tracking {o['tracking']}" if o.get("tracking") else "") + f". Customer: {c.get('name', '?')} ({country}).")

    # ---- round 15: consequences, absence, night work, how I propose, limits, friend price, missing payment, milestones, glossary ----
    def do_nothing(self, t, m):
        st = self.store
        n = self._n() or {}
        day = st.data.get("day", 0) or 1
        per_day = n.get("orders", 0) / day if n.get("orders") else 0
        waiting = [o for o in st.data["orders"] if o["status"] == "paid"]
        low = [p for p in st.products() if p["stock"] <= 3]
        try:
            msgs = len(self.inbox.items("new"))
        except Exception:
            msgs = 0
        wk_orders = per_day * 7
        return ("If nothing happens for a week, day by day:\n"
                f"• Day 1–2: {len(waiting) + round(per_day * 2)} order(s) sit unshipped; the 'ships in 1 business day' promise on the page is already broken. " + (f"{msgs} message(s) wait." if msgs else "") + "\n"
                f"• Day 3–4: the first 'where is my order?' mails (about 1 in 3 waiting customers writes); a few cancel — with card payments that's their right and it costs the fees (~€ 0,70 each).\n"
                f"• Day 5–7: ~{max(1, round(wk_orders * 0.1))} chargeback/complaint risk, the first public 1-star ('never shipped'), and the algorithm forgets you: 7 days without a post costs about 2 weeks of reach afterwards.\n"
                f"• Money: roughly {_eur(n.get('profit', 0) / day * 7)} of profit not made, plus refunds of what got cancelled" + (f"; {', '.join(p['name'].split(' (')[0] for p in low[:2])} run out and stay out." if low else ".") + "\n"
                "What I'd do on my own meanwhile: keep drafting replies (they wait for your tap unless you said “send routine replies yourself”), hold the numbers, and nag you once a day — gently.\n"
                "If you need a week off, say “I'm going on holiday for 2 weeks” and I set it up properly (holiday notice on the page, dates in replies, labels pre-printed).")

    def holiday_plan(self, t, m):
        low = t.lower()
        mm = re.search(r"(\d+|two|three|a|one|due|tre|una)\s*(day|days|week|weeks|month|giorni|settiman[ae]|mese)", low)
        n = {"two": 2, "three": 3, "a": 1, "one": 1, "due": 2, "tre": 3, "una": 1}.get(mm.group(1), mm.group(1)) if mm else 1
        n = int(n)
        unit = mm.group(2) if mm else "week"
        days = n * (7 if unit.startswith(("week", "settiman")) else 30 if unit.startswith(("month", "mese")) else 1)
        st = self.store
        nn = self._n() or {}
        day = st.data.get("day", 0) or 1
        per_day = nn.get("orders", 0) / day if nn.get("orders") else 1
        try:
            if self.memory:
                self.memory.add(f"Holiday: {days} day(s) away — set the shop's holiday notice before leaving; remove it when back")
        except Exception:
            pass
        return (f"Enjoy it. {days} day(s) away, about {per_day * days:.0f} orders in that time — three ways, pick one:\n"
                f"1. Keep selling, ship on return: a banner + a line in the order confirmation “orders placed now ship on <return date>” — legal and honest; expect ~20 % fewer orders, almost no complaints because people knew. I put the date in every reply.\n"
                "2. Keep selling, someone ships: labels pre-printed (say “print the shipping labels” each morning from your phone), a friend drops parcels at GLS; you do 5 minutes of taps a day.\n"
                "3. Pause the shop: ‘back on <date>’ page, no orders, no risk — you lose the sales and about a week of algorithm momentum after.\n"
                "Either way, before you go: reorder anything under 2 weeks of stock, approve a week of posts (say “write 7 captions”) so the pages aren't silent, "
                "say “send routine replies yourself” if you want me to answer tracking/product questions on my own, and tell me the dates so replies and the page say the same thing. "
                "I've put “holiday notice” on your to-do list. Which option?")

    def while_sleep(self, t, m):
        return ("Yes — I don't sleep, and the shop doesn't either. Overnight I: sort every message that comes in and draft the reply in the customer's language (sent at once if you've turned on “send routine replies yourself”, otherwise waiting for your morning tap); "
                "watch orders and stock and prepare the labels; run the numbers; study when nothing happens (PDFs, videos → my library); and I stay quiet — no notifications between 22:00 and 08:00 unless it's money or a real problem (a chargeback, a site down). "
                "In the morning you get one “☀️ Today” message with what happened and the 2–3 taps that need you. What I never do at night: spend money, change prices, publish, or promise a customer something outside the policy. "
                "So: sleep. The worst thing that happens overnight is a draft waiting for you.")

    def how_propose(self, t, m):
        return ("How I decide what to propose — rules, not moods:\n"
                "• Stock: a product under ~3 weeks of sales at its recent pace → reorder proposal; at 0 → 'sold out' page note or a 'ships in N days' proposal.\n"
                "• Price: margin after fees under 50 % → suggest a rise; conversion low with a fat margin → suggest a bundle or free-shipping threshold before any cut; never a change within 30 days of a sale (Omnibus).\n"
                "• Shipping: a paid order older than the promise → label proposal, and a 'ship daily' nudge if it repeats.\n"
                "• Customers: every message → a draft; refunds/damage/anger flagged first; the 'routine' kinds go out alone only if you allowed it.\n"
                "• Content: a product without a post in 7 days moves up the 'post today' list; the best seller gets the ad test.\n"
                "Every proposal shows the numbers it came from and has Apply/Reject; a rejection teaches me — rejected kinds come back less often, and “stop proposing price changes” switches a kind off. "
                "Ask “why?” after any proposal and I show the line of reasoning; “show me the maths” gives the calculation.")

    def cant_do(self, t, m):
        return ("What I can't do — honestly:\n"
                "• Touch money: no buying stock, paying suppliers, refunding, or running ads on my own — I prepare, you tap.\n"
                "• Publish or send without you unless you've explicitly allowed a kind (routine replies, pre-approved posts).\n"
                "• Pack and ship, take product photos, talk on the phone to couriers or the bank.\n"
                "• See what you don't show me: your photos, your tone, the real store's back office until it exists. My 'eyes' read screens and listings, but only when pointed at them.\n"
                "• Solve every CAPTCHA or log into sites that block robots — I try, then hand you a one-tap fallback.\n"
                "• Give legal or tax advice you can rely on in a dispute — I know the rules of the common case; a commercialista signs off.\n"
                "• Predict: my forecasts come from a few weeks of numbers; treat them as direction, not promises.\n"
                "• Remember what you never told me: supplier names, your costs, your plans — say “remember that …” and I keep it.\n"
                "Everything else in the shop routine — replies, numbers, proposals, labels, research, documents, posts' text, study — I do.")

    def check_product_number(self, t, m):
        gd = m.groupdict()
        what = (gd.get("what") or gd.get("what2") or gd.get("what3") or "").strip()
        p = self.store.find_product(what) if self.store is not None else None
        if not p:
            return None
        price, cost = p["price"], p.get("cost", 0)
        fee = 0.029 * price + 0.30
        gm = price - cost
        net = gm - fee
        return (f"Checked again, from the product record: {p['name'].split(' (')[0]} sells at {_eur(price)}, cost you set {_eur(cost)} → gross margin {_eur(gm)} ({gm / price * 100:.0f} %); "
                f"payment fee 2,9 % + € 0,30 = {_eur(fee)} → {_eur(net)} ({net / price * 100:.0f} %) after fees; if that order ships free, minus the carrier (€ 2,90 + € 0,35/unit) → {_eur(net - 3.25)} ({(net - 3.25) / price * 100:.0f} %).\n"
                f"The only number I can't verify is the cost {_eur(cost)} — it's what was entered, not an invoice. If the real cost is different, say “the {p['name'].split(' (')[0].lower()} cost is actually X” and I correct it and redo every margin.")

    def friend_price(self, t, m):
        gd = m.groupdict() if m is not None else {}
        what = (gd.get("what") or "").strip()
        p = self.store.find_product(what) if (self.store is not None and what) else None
        if p:
            price, cost = p["price"], p.get("cost", 0)
            fair = round(cost * 1.3 + 0.5, 0) - 0.10 if cost else round(price * 0.7, 0) - 0.10
            fair = max(fair, cost + 1)
            return (f"For a friend: {_eur(fair)} — that's cost {_eur(cost)} + a little (about 30 %) so it isn't a gift and you're not 'selling' either; "
                    f"the public price is {_eur(price)} and a 'friends' price around 70 % of it ({_eur(round(price * 0.7, 0) - 0.10)}) is the other common choice.\n"
                    "Two rules: never below cost (friends multiply), and the price is the same for all friends so nobody feels second-class. "
                    "It's an offline sale — say “I sold 1 " + p['name'].split(' (')[0].lower() + " to a friend” and I take it off the stock; the money stays outside the shop's ledger (note it for the tax books).")
        return ("Friends' price rule: cost + about 30 %, rounded to a ,90 — never below cost, and the same for every friend. Cheaper than the shop, not a gift. "
                "Tell me which product and I give you the number; then say “I sold 1 <product> to a friend” and I fix the stock.")

    def payment_missing(self, t, m):
        return ("‘I paid but you got nothing’ — check before you ship, kindly but firmly:\n"
                "1. Look in the payment dashboard (Stripe/PayPal/bank) for the order number, the amount and the date — not in the e-mail inbox. A card payment shows within seconds; a bank transfer takes 1–2 business days (SEPA), 3–5 from abroad.\n"
                "2. Ask the customer for the receipt/transaction id (a screenshot is not proof — they're easy to fake); compare the amount and the date.\n"
                "3. Common real causes: transfer still in transit, a typo in the IBAN or reference (money bounces back in ~5 days), a card 'pending' that the bank released, PayPal 'eCheck' (takes days).\n"
                "4. Common fake: the 'payment confirmation' e-mail from a look-alike address urging you to ship now. Rule: nothing ships until the money is on the account. Say so plainly: “as soon as the payment shows on our side (1–2 business days for transfers) your order ships the same day”.\n"
                "5. If it's a marketplace/checkout error on your side, tell them the truth and send a fresh payment link.\n"
                "Say “write the reply about the missing payment” and I draft it in that tone.")

    def when_reach(self, t, m):
        gd = m.groupdict()
        amt = _num(gd.get("amt") or "1000")
        if re.search(r"\d\s*(?:k|mila)\b", t.lower()):
            amt *= 1000
        what = (gd.get("what") or "profit").lower()
        n = self._n() or {}
        st = self.store
        day = st.data.get("day", 0) or 1
        if not n.get("orders"):
            return f"No sales yet, so no honest date for {_eur(amt)} — after two weeks of practice days I can give one."
        if what.startswith(("order", "ordini")):
            have, per_day, label = n["orders"], n["orders"] / day, "orders"
        elif what.startswith(("customer", "clienti")):
            have = len({(o.get("customer") or {}).get("email") for o in self._paid()}); per_day = have / day; label = "customers"
        elif what.startswith(("revenue", "sales", "turnover", "fatturato", "vendite")):
            have, per_day, label = n["revenue"], n["revenue"] / day, "revenue"
        elif "month" in what:
            per_month = n["profit"] / day * 30
            if per_month >= amt:
                return f"Already there: at today's pace the shop makes {_eur(per_month)} of profit a month (≥ {_eur(amt)})."
            months = 0; pm = per_month
            while pm < amt and months < 36:
                pm *= 1.25; months += 1
            return f"{_eur(amt)} a month: today's pace is {_eur(per_month)}/month; growing 25 % a month (daily posts, no breaks) that's about {months} month(s) away. Faster only with more traffic — say “cheapest way to get 10 more sales” for the levers."
        else:
            have, per_day, label = n["profit"], n["profit"] / day, "profit"
        if have >= amt:
            return f"Already past it: {label} so far is {_eur(have) if label in ('profit', 'revenue') else int(have)} (day {day})."
        left = amt - have
        days_flat = left / per_day if per_day else None
        # with 25 %/month growth
        d, cum, rate = 0, 0.0, per_day
        while cum < left and d < 730:
            d += 1; cum += rate
            if d % 30 == 0:
                rate *= 1.25
        fmt = (lambda v: _eur(v)) if label in ("profit", "revenue") else (lambda v: f"{int(round(v))}")
        return (f"{fmt(amt)} of {label}: you're at {fmt(have)} after {day} day(s), so {fmt(left)} to go. At today's pace ({fmt(per_day)} a day) that's about {days_flat:.0f} days ({days_flat / 30:.1f} months); "
                f"if sales grow 25 % a month with daily posts, about {d} days. " +
                ("A bundle and the past-customers e-mail are the two things that pull that date closer without spending — say “add the bundle”." if label == "profit" else "More visits are the only real lever — say “cheapest way to get 10 more sales”."))

    def tax_set_aside(self, t, m):
        return self.tax_aside(t, m)

    def supplier_legit(self, t, m):
        return ("How I check a supplier before your money goes anywhere (say “is this seller ok? <link>” and I do it and hand you a document):\n"
                "1. Age and footprint: domain older than 2 years (whois), a real company name, address and VAT/registration number you can find in a registry; the same name on Google Maps, LinkedIn, Alibaba/Faire, not only on its own site.\n"
                "2. Reviews off their site: Trustpilot/Google/Reddit — read the 1–2 stars for the pattern (late, no refunds, different product); 0 reviews anywhere is a flag, so are 200 five-stars in one month.\n"
                "3. Contact test: write a real question (materials, MOQ, lead time, certificates) — a serious supplier answers specifically within 1–2 days, a scammer answers instantly and vaguely.\n"
                "4. Payment: card, PayPal or trade assurance — never Western Union, crypto or 'a friend's account'; a first order small enough to lose (€ 50–150).\n"
                "5. Samples: order one first; check materials, weight, packaging, how long it really took, what customs charged.\n"
                "6. Photos: reverse-image-search the product pictures — stolen photos = no real product.\n"
                "7. Price: 60 % below everyone else is not a deal, it's the hook.\n"
                "Green flags: a printed catalogue with a price list, MOQ and lead time written down, certificates they send without fuss, a phone number someone answers.")

    def refund_mechanics(self, t, m):
        low = t.lower()
        paypal = "paypal" in low
        return ((("PayPal refunds: from the transaction → 'Refund', full or partial, within 180 days; the money returns to the buyer's original method in 3–5 business days. "
                  "PayPal keeps the fixed part of its fee (€ 0,35) and, since 2019, the percentage fee too — a € 30 refund costs you about € 1,40 in lost fees. Refunds are automatic for disputes you lose.")
                 if paypal else
                 ("Stripe refunds: in the dashboard, open the payment → 'Refund', full or partial, any time (a partial refund is fine for 'keep it, here's 30 % back'). "
                  "The money goes back to the customer's card in 5–10 business days (that's the banks, not you) and Stripe does NOT return its 1,5 %/2,9 % + € 0,25 fee — a € 30 refund costs you about € 1,10 in fees. "
                  "Stripe takes the refunded amount from your next payout; if the balance is short it debits your bank."))
                + "\nGood practice: refund within 48 h of deciding — slow refunds become chargebacks (which cost € 15–25 on top). Write the refund in the order notes; if an invoice was issued, book a credit note. "
                "Tell the customer the two dates: 'refunded today, on your card within 5–10 business days'. Say “refund order <number>” and I prepare the proposal and the message.")

    def margin_vs_markup(self, t, m):
        p = None
        try:
            p = max(self.store.products(), key=lambda x: x["price"] - x.get("cost", 0)) if self.store is not None else None
        except Exception:
            pass
        ex = ""
        if p:
            price, cost = p["price"], p.get("cost", 0)
            ex = f"\nOur {p['name'].split(' (')[0]}: price {_eur(price)}, cost {_eur(cost)} → margin {(price - cost) / price * 100:.0f} %, markup {(price - cost) / cost * 100:.0f} %."
        return ("Same profit, two yardsticks:\n"
                "• Margin = profit ÷ selling price. It answers 'what share of what the customer pays do I keep?' — the number for judging the shop (fees and refunds also come as % of price).\n"
                "• Markup = profit ÷ cost. It answers 'how much did I add on top of what I paid?' — the number for setting a price from a cost (×2,5–4 for small shops).\n"
                "Example: buy at € 10, sell at € 25 → profit € 15 → margin 60 %, markup 150 %. A 50 % markup is only a 33 % margin — the classic trap." + ex +
                "\nRule: talk margin when deciding, use markup when pricing.")

    def orders_benchmark(self, t, m):
        n = self._n() or {}
        day = self.store.data.get("day", 0) or 1
        mine = n.get("orders", 0) / day if n.get("orders") else 0
        return (f"For a one-person shop: 1–3 orders a day is a healthy start (month 1–3), 5 a day is a real side business (~€ 4–6k of sales a month), 10+ a day is a job — and where packing takes 1–2 hours. "
                f"You're at {mine:.1f} a day — " + ("a good start." if 1 <= mine < 3 else "already a real business." if mine >= 3 else "the first weeks; 1 a day is the first goal.") +
                "\nWhat matters more than the number: does it come from your own page (repeatable) or from one viral post (luck), and does the average basket grow (bundles, free-shipping threshold).")

    def return_benchmark(self, t, m):
        rr = None
        try:
            rr = self.advice_return_rate() if hasattr(self, "advice_return_rate") else None
        except Exception:
            rr = None
        n = self._n() or {}
        ref = n.get("refunded", 0)
        tot = n.get("orders", 0) + ref
        mine = f"Yours: {ref} refund(s) on {tot} orders = {ref / tot * 100:.1f} %." if tot else "Yours: no returns yet."
        return ("Return rates by kind of shop: home goods and gifts 2–5 % (good under 3 %), electronics 5–10 %, fashion 20–30 % (size), marketplaces higher than own shops. "
                f"{mine} Above 5 % on home goods usually means one thing: the photos or the description promise something the product isn't (size, colour, 'ceramic' that's stoneware) — fix the page, not the policy. "
                "Under 1 % with many orders can also be bad: people don't bother returning cheap disappointing things, they just never come back.")

    GLOSSARY = {
        "sku": "SKU (stock keeping unit): the code you give each product variant — e.g. MUG-350-BLUE. One SKU per thing you count on the shelf; it's what labels, stock and orders refer to.",
        "aov": "AOV (average order value): sales ÷ orders — what a customer spends per order. Bundles and a free-shipping threshold raise it; it's the cheapest way to earn more from the same visitors.",
        "cogs": "COGS (cost of goods sold): what the products you sold cost you — purchase price plus what it took to get them to your shelf. Sales − COGS = gross margin.",
        "roas": "ROAS (return on ad spend): sales from ads ÷ money spent on ads. 3× means € 3 of sales per € 1 of ads; with a 50 % margin you need about 2× just to break even.",
        "cpc": "CPC (cost per click): what one click on your ad costs, typically € 0,20–0,80 for small shops. Clicks × conversion = orders, so CPC ÷ conversion ≈ cost per order.",
        "cpm": "CPM: cost per 1,000 ad views. Useful to compare platforms; what you pay for attention before anyone clicks.",
        "ctr": "CTR (click-through rate): clicks ÷ views. 1–2 % is normal for ads; higher means the picture/hook works.",
        "cac": "CAC (customer acquisition cost): total marketing spend ÷ new customers. Must be well under what a customer earns you over time (LTV).",
        "ltv": "LTV/CLV (customer lifetime value): the profit one customer brings over all their orders. Repeat buyers are why a € 10 CAC can be fine for a € 15 product.",
        "clv": "LTV/CLV (customer lifetime value): the profit one customer brings over all their orders. Repeat buyers are why a € 10 CAC can be fine for a € 15 product.",
        "conversion rate": "Conversion rate: orders ÷ visitors × 100. Out of 100 people who open the shop, how many buy — 1–3 % is normal online, so 100 visits ≈ 1–3 orders.",
        "conversion": "Conversion rate: orders ÷ visitors × 100. Out of 100 people who open the shop, how many buy — 1–3 % is normal online, so 100 visits ≈ 1–3 orders.",
        "bounce rate": "Bounce rate: the share of visitors who leave after one page. High on a product page = the photo, price or shipping cost didn't convince in 5 seconds.",
        "churn": "Churn: customers or subscribers you lose over a period. For a shop: newsletter unsubscribes and buyers who never return.",
        "dropshipping": "Dropshipping: you sell, the supplier ships straight to the customer; you never hold stock. Low risk, low margin (10–25 %), slow delivery, and the customer experience is in someone else's hands.",
        "dropship": "Dropshipping: you sell, the supplier ships straight to the customer; you never hold stock. Low risk, low margin (10–25 %), slow delivery, and the customer experience is in someone else's hands.",
        "3pl": "3PL (third-party logistics): a warehouse that stores, packs and ships for you for a fee per order (€ 2–4 + storage). Worth it from ~10 orders a day.",
        "fulfilment": "Fulfilment: everything between 'order paid' and 'parcel delivered' — picking, packing, labelling, hand-over to the courier, tracking.",
        "fulfillment": "Fulfilment: everything between 'order paid' and 'parcel delivered' — picking, packing, labelling, hand-over to the courier, tracking.",
        "landed cost": "Landed cost: the real cost of a product on your shelf — price + shipping to you + customs/VAT on import + payment fees. Margins must be computed on this, not the supplier's price.",
        "gross margin": "Gross margin: price − cost of the product, usually as % of price. € 14,90 mug with € 5,60 cost → € 9,30 = 62 %. Fees and shipping come out of it later.",
        "net margin": "Net margin: what's left of the price after the product, shipping, fees and your fixed bills — the real profit share. 10–40 % is the usual range for small shops.",
        "margin": "Margin: profit as a share of the selling price. € 14,90 mug, € 5,60 cost → margin € 9,30 = 62 %. (Markup is the same profit as a share of the cost: 166 %.)",
        "markup": "Markup: profit as a share of the cost. Buy at € 5,60, sell at € 14,90 → markup 166 % (margin 62 %). Rule of thumb for small shops: 2,5–4× the landed cost.",
        "break-even": "Break-even: the point where sales cover all costs — zero profit, zero loss. Fixed costs ÷ margin per order = orders needed; e.g. € 300/month ÷ € 15 = 20 orders a month.",
        "breakeven": "Break-even: the point where sales cover all costs — zero profit, zero loss. Fixed costs ÷ margin per order = orders needed; e.g. € 300/month ÷ € 15 = 20 orders a month.",
        "cash flow": "Cash flow: money in vs money out over time — not the same as profit. You can be profitable and still run out of cash because stock is paid months before it sells.",
        "cashflow": "Cash flow: money in vs money out over time — not the same as profit. You can be profitable and still run out of cash because stock is paid months before it sells.",
        "inventory turnover": "Inventory turnover: how many times a year you sell through your stock. 6–12 is healthy for small shops; 2 means money asleep on the shelf.",
        "stock turnover": "Inventory turnover: how many times a year you sell through your stock. 6–12 is healthy for small shops; 2 means money asleep on the shelf.",
        "lead time": "Lead time: the days between placing a reorder and having it on the shelf. Reorder when stock covers less than lead time + a safety margin.",
        "moq": "MOQ (minimum order quantity): the smallest batch a supplier sells. Negotiate it down for a first order, or accept a higher unit price for a smaller test batch.",
        "minimum order quantity": "MOQ (minimum order quantity): the smallest batch a supplier sells. Negotiate it down for a first order, or accept a higher unit price for a smaller test batch.",
        "white label": "White label: a generic product from a manufacturer that you sell under your brand. Private label is the same with your own tweaks (colour, packaging).",
        "private label": "Private label: a manufacturer's product made to your spec and sold under your brand — a step up from white label (generic).",
        "oss": "OSS (One-Stop Shop): the EU VAT scheme — above € 10,000/year of sales to consumers in other EU countries you charge their VAT rate and declare it all in one quarterly return at home.",
        "vies": "VIES: the EU's VAT-number checker (ec.europa.eu/taxation_customs/vies). A valid number lets you invoice an EU business without VAT (reverse charge).",
        "incoterms": "Incoterms: who pays and who is responsible at each step of an international shipment. For a shop: DDP = all duties paid, customer gets no surprise; DAP/EXW = customer pays import costs.",
        "ddp": "DDP (delivered duty paid): the seller pays shipping, customs and import VAT; the customer gets the parcel with no extra bill. The only good option for non-EU customers.",
        "dap": "DAP (delivered at place): seller ships; the customer pays import duties/VAT on arrival — the classic 'surprise bill' complaint.",
        "exw": "EXW (ex works): the buyer picks it up at the factory and handles everything. What suppliers quote when the price looks too good.",
        "fob": "FOB (free on board): the supplier gets goods onto the ship; you pay from there (freight, insurance, customs).",
        "omnibus": "Omnibus rule (EU, 2022): when you show a discount, the 'before' price must be the lowest price of the previous 30 days. No fake crossings-out; raise prices well before a sale or don't.",
        "chargeback": "Chargeback: the customer's bank reverses a card payment after a dispute. You get ~7–10 days to send evidence (tracking, delivery proof, messages); lose it and you pay the amount plus a € 15–25 fee.",
        "reverse charge": "Reverse charge: invoicing an EU business (valid VAT number) without VAT — they account for it in their country. Write 'reverse charge, art. 196 Dir. 2006/112/EC' on the invoice.",
        "forfettario": "Regime forfettario: Italy's flat-tax scheme for small businesses — up to € 85,000/year, tax 5 % (first 5 years) then 15 % on a fixed 40 % of turnover for online retail, no VAT charged, simple books.",
        "ateco": "ATECO code: Italy's activity code on your Partita IVA; online retail is 47.91.10. It sets the forfettario coefficient (40 %) and the INPS fund.",
        "sdi": "SDI (Sistema di Interscambio): the Italian tax agency's e-invoice hub — every business invoice goes through it electronically (XML) and gets a receipt.",
        "pec": "PEC: certified e-mail, legally like registered post in Italy. Every Partita IVA must have one; official notices arrive there.",
        "a/b test": "A/B test: show two versions (photo, price, headline) to similar visitors and keep the one that sells more. Needs a few hundred visitors per version to mean anything.",
        "ab test": "A/B test: show two versions (photo, price, headline) to similar visitors and keep the one that sells more. Needs a few hundred visitors per version to mean anything.",
        "kpi": "KPI (key performance indicator): the 3–5 numbers you watch every week. For us: orders, conversion, average basket, margin, late shipments.",
        "seo": "SEO: making your pages show up in Google without paying — clear product names, real descriptions, fast pages, a few articles answering the questions buyers search for. Slow (months) but free.",
        "sem": "SEM: paid search ads (Google Shopping/Search). You pay per click; works when people already search for what you sell.",
        "ugc": "UGC (user-generated content): photos/videos your customers make with the product. Converts better than studio shots; ask for it on the parcel card.",
        "cro": "CRO (conversion rate optimisation): changing the page so more of the same visitors buy — photos, shipping shown early, reviews, fewer steps at checkout.",
        "hook": "Hook: the first 1–2 seconds of a short video — the line or image that makes people stop scrolling. Most of a video's reach is decided there.",
        "cta": "CTA (call to action): the one thing you ask at the end — 'link in bio', 'reply with your favourite colour'. One per post, plainly.",
        "call to action": "CTA (call to action): the one thing you ask at the end — 'link in bio', 'reply with your favourite colour'. One per post, plainly.",
        "funnel": "Funnel: the path from stranger → visitor → cart → buyer → repeat buyer. Each step loses people; fix the step that leaks most (usually cart → paid: shipping cost surprise).",
        "retargeting": "Retargeting: ads shown only to people who already visited your shop or left a cart. Cheapest paid ads there are, because they already know you.",
        "pixel": "Pixel: a small piece of code from Meta/TikTok on your site that tells the platform who visited and bought — needed for retargeting and ad measurement; requires cookie consent in the EU.",
        "lookalike": "Lookalike audience: the ad platform finds people similar to your buyers. Works from ~100 buyers; before that it's guessing.",
        "open rate": "Open rate: the share of e-mails opened. 35–50 % is normal for a small shop's own list; the subject line decides it.",
        "click rate": "Click rate: the share of delivered e-mails where someone clicked a link — 2–5 % normal, 6–10 % great.",
        "unsubscribe rate": "Unsubscribe rate: who leaves your list per send — keep it under 0,5 %.",
        "nps": "NPS (net promoter score): 'would you recommend us, 0–10?' — % of 9–10 minus % of 0–6. Above 50 is excellent for a shop; the free version is reading your reviews.",
        "net promoter score": "NPS (net promoter score): 'would you recommend us, 0–10?' — % of 9–10 minus % of 0–6. Above 50 is excellent for a shop; the free version is reading your reviews.",
        "omnichannel": "Omnichannel: selling in several places (own site, marketplace, Instagram, a stall) with one stock and one customer view. For a small shop: own site + one marketplace, no more.",
        "marketplace": "Marketplace: someone else's shop where you list (Amazon, Etsy, eBay). Traffic for a fee (8–15 % + listing costs) and their rules; you don't own the customer.",
        "pos": "POS (point of sale): the till — the card reader/app you use at a market stall (SumUp, Stripe Terminal). Fees ~1,5–2 %.",
        "ean": "EAN/GTIN: the 13-digit barcode number a product has worldwide. Needed for Amazon and shops' tills; you buy them from GS1 or use the supplier's.",
        "gtin": "EAN/GTIN: the 13-digit barcode number a product has worldwide. Needed for Amazon and shops' tills; you buy them from GS1 or use the supplier's.",
        "barcode": "Barcode/EAN: the 13-digit number a product has worldwide. Needed for Amazon and shops' tills; you buy them from GS1 or use the supplier's.",
        "hs code": "HS/customs code: the 6–10 digit code that classifies goods at customs and sets the duty rate. On every non-EU shipment's customs form.",
        "customs code": "HS/customs code: the 6–10 digit code that classifies goods at customs and sets the duty rate. On every non-EU shipment's customs form.",
        "proof of delivery": "Proof of delivery (POD): the courier's record that the parcel was handed over — signature, photo, GPS. What wins a 'never received' chargeback.",
        "pod": "Proof of delivery (POD): the courier's record that the parcel was handed over — signature, photo, GPS. What wins a 'never received' chargeback.",
        "sla": "SLA (service level agreement): a promised standard — e.g. 'replies within 24 h', 'ships in 1 business day'. Promise only what you keep.",
        "b2b": "B2B: selling to businesses (invoices, VAT numbers, no withdrawal right, bigger orders). B2C: to consumers (14-day withdrawal, 2-year guarantee).",
        "b2c": "B2C: selling to consumers — 14-day withdrawal right, 2-year legal guarantee, prices shown with VAT. B2B is selling to businesses.",
        "d2c": "D2C/DTC (direct to consumer): a brand selling from its own site instead of through shops or marketplaces — full margin, but you bring your own traffic.",
        "dtc": "D2C/DTC (direct to consumer): a brand selling from its own site instead of through shops or marketplaces — full margin, but you bring your own traffic.",
        "wholesale": "Wholesale: selling in bulk to shops that resell — usually 50 % of the retail price, minimum quantities, invoices, payment terms.",
        "retail": "Retail: selling single items to the final customer at the full price — what the shop does.",
        "rrp": "RRP/MSRP: the price the maker recommends. You may sell below it; in the EU a maker can't force you to.",
        "msrp": "RRP/MSRP: the price the maker recommends. You may sell below it; in the EU a maker can't force you to.",
        "bundle": "Bundle: two or more products sold together for less than the sum — raises the basket and moves slow stock while keeping most of the margin.",
        "loss leader": "Loss leader: a product sold at or below cost to bring people in, hoping they buy more. Dangerous for a small shop — only with a bundle or upsell attached.",
        "anchor price": "Anchor price: a higher price shown first (the 'before' price, a premium version) that makes the real price look reasonable. Legal only if it's true (Omnibus rule).",
        "charm pricing": "Charm/psychological pricing: € 14,90 instead of € 15 — the left digit rules perception. Use ,90 endings; ,99 looks cheap for gifts.",
        "psychological pricing": "Charm/psychological pricing: € 14,90 instead of € 15 — the left digit rules perception. Use ,90 endings; ,99 looks cheap for gifts.",
        "dynamic pricing": "Dynamic pricing: prices that change with demand or time (airlines). Not for a small shop — customers notice and trust drops.",
        "price elasticity": "Price elasticity: how much sales fall when the price rises. Gifts and unique items are inelastic (a 10 % rise barely dents sales); commodities are elastic.",
        "sunk cost": "Sunk cost: money already spent that you can't get back — it must not drive decisions. Stock that doesn't sell: clear it, don't keep 'waiting to recover the cost'.",
        "opportunity cost": "Opportunity cost: what you give up by choosing one thing — € 500 in slow stock is € 500 not in the product that sells.",
        "fixed cost": "Fixed costs: what you pay whether you sell or not (domain, apps, accountant, INPS). Variable costs move with each order (product, shipping, fees).",
        "variable cost": "Variable costs: what each order costs (product, box, shipping, fees). Fixed costs stay whether you sell or not (domain, accountant, INPS).",
        "unit economics": "Unit economics: the profit on ONE order after everything variable — price − product − shipping − fees − box. If one order isn't profitable, volume won't fix it.",
        "contribution margin": "Contribution margin: price minus all variable costs of an order — what each sale contributes to paying the fixed bills and then profit.",
        "payback period": "Payback period: how long until a purchase (camera, stock, ads) has earned its cost back. Under a month: do it; over three: think.",
        "working capital": "Working capital: the money tied up between paying suppliers and getting paid by customers — stock on the shelf plus unpaid invoices. Why growth eats cash.",
        "invoice": "Invoice (fattura): the legal sales document with your Partita IVA, the buyer's details, items, VAT. In Italy it goes electronically through SDI; consumers get a receipt unless they ask for one.",
        "pro forma": "Pro forma invoice: a preview of an invoice, not a tax document — used for quotes, prepayment or customs.",
        "proforma": "Pro forma invoice: a preview of an invoice, not a tax document — used for quotes, prepayment or customs.",
        "credit note": "Credit note (nota di credito): the document that cancels part or all of an invoice — how a refund is booked when an invoice was issued.",
        "withdrawal right": "Right of withdrawal (diritto di recesso): EU consumers may return an online purchase within 14 days of delivery without a reason; you refund within 14 days of getting it back. You may charge the return postage if your terms say so.",
        "diritto di recesso": "Diritto di recesso: EU consumers may return an online purchase within 14 days of delivery without a reason; you refund within 14 days of getting it back. You may charge the return postage if your terms say so.",
        "legal guarantee": "Legal guarantee (garanzia legale): in the EU consumer goods are covered 2 years against defects; the seller repairs, replaces or refunds. Separate from any maker's warranty.",
        "garanzia legale": "Garanzia legale: 2 years against defects for consumers in the EU; the seller repairs, replaces or refunds. Separate from the maker's warranty.",
        "upsell": "Upsell: offering a better/bigger version at checkout; cross-sell: a matching product ('add the wraps for € 12'). Both raise the basket without new visitors.",
        "cross-sell": "Cross-sell: offering a matching product at checkout ('add the wraps for € 12'). Upsell is the bigger/better version. Both raise the basket without new visitors.",
        "cross sell": "Cross-sell: offering a matching product at checkout ('add the wraps for € 12'). Upsell is the bigger/better version. Both raise the basket without new visitors.",
        "mov": "MOV (minimum order value): the smallest order you accept, or the threshold for free shipping — set it just above your average basket to lift it.",
        "dm": "DM: a direct/private message on Instagram/TikTok. Where half of small-shop customer service happens; answer within the hour.",
        "reel": "Reel: Instagram's short vertical video (15–90 s). The format that reaches strangers; a photo post reaches followers only.",
        "carousel": "Carousel: a post with several swipeable images. Good for 'how it's made' or 5 uses of one product; more time on the post helps reach.",
        "epos": "EPOS/POS: the till — a card reader/app for a market stall (SumUp, Stripe Terminal). Fees ~1,5–2 %.",
        "tracking number": "Tracking number: the courier's code for one parcel; put it in the shipping e-mail — 80 % of 'where is my order' mails disappear.",
        "map": "MAP (minimum advertised price): a maker's rule on the lowest price you may advertise — common in the US, not enforceable in the EU for resellers.",
        "skus": "SKUs (stock keeping units): the codes you give each product variant — e.g. MUG-350-BLUE. One per thing you count on the shelf.",
    }

    def glossary(self, t, m):
        gd = m.groupdict()
        term = (gd.get("term") or gd.get("term2") or gd.get("term3") or "").lower().strip()
        term = {"fulfilment": "fulfilment", "fulfillment": "fulfilment", "break even": "break-even", "cash flow": "cash flow", "tasso di conversione": "conversion rate", "margine": "margin", "ricarico": "markup",
                "nota di credito": "credit note", "fattura": "invoice"}.get(term, term)
        text = self.GLOSSARY.get(term) or self.GLOSSARY.get(term.replace("-", " ")) or self.GLOSSARY.get(term.replace(" ", "-"))
        if not text:
            return None
        kid = bool(re.search(r"like i'?m (?:5|five|10|ten|a kid|new)", t.lower()))
        if kid and term in ("conversion", "conversion rate"):
            n = self._n() or {}
            return ("Imagine 100 people walk past your lemonade stand and look. If 3 of them buy a lemonade, your conversion rate is 3 %. "
                    "The shop is the same: out of every 100 people who open it, how many buy. " + (f"Ours: {n['conversion']:.1f} out of 100." if n.get("conversion") else "") +
                    " Two ways to sell more lemonade: more people walking past (visits) or a nicer sign so more of them stop (conversion).")
        n = self._n() or {}
        mine = ""
        try:
            if term in ("aov",) and n.get("orders"):
                mine = f" Ours: {_eur(n['revenue'] / n['orders'])}."
            elif term in ("conversion", "conversion rate") and n.get("orders"):
                mine = f" Ours: {n['conversion']:.1f} %."
            elif term in ("net margin",) and n.get("revenue"):
                mine = f" Ours so far: {n['profit'] / n['revenue'] * 100:.0f} % before fixed bills."
            elif term in ("break-even", "breakeven") and n.get("orders"):
                per = n["profit"] / n["orders"]
                mine = f" Ours: about {300 / per:.0f} orders a month at {_eur(per)} profit each cover € 300 of fixed bills."
        except Exception:
            pass
        return text + mine

    # ---- round 13: notes, product verdicts, horizons, affordability ---------------------------------------------
    def take_note(self, t, m):
        try:
            what = t[m.start("what"):m.end("what")].strip(" .")               # original casing ("Terra Ceramics"), not the lowercased match
        except Exception:
            what = (m.group("what") or "").strip(" .")
        if self.memory is None or len(what) < 4:
            return None
        if re.match(r"^(?:me |to )?(?:tomorrow|on |at |in \d)", what.lower()) or re.search(r"\?$", what):
            return None                                                          # 'remind me tomorrow…' / a question → other paths
        topic = None
        mm = re.search(r"\b(?:the |our |my |il |la )?([a-zà-ú][a-zà-ú0-9\-]{2,}(?: [a-zà-ú][a-zà-ú0-9\-]{2,})?) (?:supplier|fornitore|vendor|courier|corriere|accountant|commercialista|photographer|bank|agency|factory|maker)\b", what, re.I)
        if mm:
            topic = mm.group(0)
        else:
            words = [w for w in re.findall(r"[a-zà-ú]{4,}", what.lower()) if w not in ("that", "this", "with", "from", "about", "called", "closes", "close", "will", "have", "there", "their", "they", "when", "what", "which", "our", "every", "always", "never", "also")]
            topic = " ".join(words[:3]) or "note"
        topic = re.sub(r"^(?:the|our|my|il|la) ", "", topic.strip())
        self.memory.note("owner", topic[:60], what[:1000])
        key = topic.split()[0] if topic else "it"
        return f"Noted under “{topic[:40]}”: “{what[:120]}”. Ask me “what did I tell you about the {key}?” any time — and I'll use it when it matters (reorders, replies, plans)."

    def recall_fact(self, t, m):
        gd = m.groupdict()
        what = (gd.get("what") or gd.get("what2") or gd.get("what3") or gd.get("what5") or "").strip()
        try:                                                                  # 'tazze' → 'mug' so an English note is found from an Italian question (and vice versa)
            it = getattr(self.store, "IT_WORDS", {}) if self.store is not None else {}
            en = " ".join(it.get(w, w) for w in what.lower().split())
            back = {v: k for k, v in it.items()}
            it_q = " ".join(back.get(w, w) for w in what.lower().split())
            query = " ".join(dict.fromkeys((what + " " + en + " " + it_q).split()))
        except Exception:
            query = what
        rows = []
        try:
            rows = [r for r in (self.memory.notes(query, limit=8) if self.memory else []) if r.get("kind") == "owner"]
            if not rows:
                rows = [r for r in (self.memory.notes(query, limit=8) if self.memory else []) if any(w in (r.get("topic", "") + " " + r.get("text", "")).lower() for w in query.split() if len(w) > 2)]
        except Exception:
            pass
        low = t.lower()
        role = re.search(r"\b(supplier|fornitore|vendor|factory|maker|producer|courier|accountant|commercialista|photographer|designer|bank|agency)\b", low)
        role = role.group(1) if role else None
        if role:
            rows = [r for r in rows if role in (r.get("topic", "") + " " + r.get("text", "")).lower()] or rows
        if rows:
            r = rows[0]
            mm = re.search(r"\b(?:is called|is named|si chiama|called|named|is|are|=|:)\s+([A-Za-z][\w&'\-]*(?: [A-Za-z][\w&'\-]*){0,3})", r["text"])
            name = mm.group(1).strip() if mm else None
            if name and re.match(r"^(?:the|a|an|closed|open|not|in|on|at|going|very|also)\b", name.lower()):
                name = None
            return (f"{name} — " if name else "") + f"from your note of {r['t'][:10]}: “{r['text'][:160]}”."
        prod = self.store.find_product(what) if self.store is not None else None
        if prod and (prod.get("supplier") or (prod.get("details") and any("supplier" in d.lower() for d in prod["details"]))):
            sup = prod.get("supplier") or next(d for d in prod["details"] if "supplier" in d.lower())
            return f"{prod['name'].split(' (')[0]}: {sup} (from the product record)."
        return (f"I don't have that written down — nobody told me who the {what} {role or 'supplier'} is. Say “remember that the {what} {role or 'supplier'} is called X” and I keep it"
                + (" (and I'll put it on the reorder lines)." if role in (None, "supplier", "fornitore", "vendor", "factory") else "."))

    def _product_stats(self, p):
        st = self.store
        day = st.data.get("day", 0)
        paid = self._paid()
        sold = sum(l["qty"] for o in paid for l in o["lines"] if l["id"] == p["id"])
        sold7 = sum(l["qty"] for o in paid if o.get("day", 0) > day - 7 for l in o["lines"] if l["id"] == p["id"])
        rev = sum(l["qty"] * l["price"] for o in paid for l in o["lines"] if l["id"] == p["id"])
        gm = rev - sold * p.get("cost", 0)
        total_units = sum(l["qty"] for o in paid for l in o["lines"]) or 1
        ref = sum(1 for o in st.data["orders"] if o["status"] == "refunded" and any(l["id"] == p["id"] for l in o["lines"]))
        per_day = sold7 / 7 if sold7 else (sold / max(1, day) if day else 0)
        return {"sold": sold, "sold7": sold7, "rev": rev, "gm": gm, "share": sold / total_units * 100, "refunds": ref, "per_day": per_day,
                "days_left": (p["stock"] / per_day) if per_day else None, "margin_pct": (p["price"] - p.get("cost", 0)) / p["price"] * 100 if p["price"] else 0,
                "stock_cost": p["stock"] * p.get("cost", 0)}

    def product_report(self, t, m):
        what = (m.group("what") or m.group("what2") or "").strip()
        if re.search(r"\b(shop|store|business|week|day|month|it|things|everything|we|you|sales|negozio)\b", what.lower()):
            return None
        p = self.store.find_product(what) if self.store is not None else None
        if not p:
            return None
        s = self._product_stats(p)
        day = self.store.data.get("day", 0)
        name = p["name"].split(" (")[0]
        if not s["sold"]:
            verdict = ("never sold yet" + (" — and it's out of stock, so it can't" if p["stock"] == 0 else f" in {day} day(s); {p['stock']} on the shelf ({_eur(s['stock_cost'])} at cost). Give it one week in the posts before judging it."))
            return f"{name}: {verdict}"
        pace = f"{s['sold7']} in the last 7 days" if s["sold7"] else "none in the last 7 days"
        stock_line = ("sold out — that's lost sales every day" if p["stock"] == 0 else f"{p['stock']} left ≈ {s['days_left']:.0f} days" if s["days_left"] else f"{p['stock']} left")
        mood = ("Doing well" if s["share"] >= 30 else "Steady" if s["sold7"] else "Slow")
        return (f"{name}: {mood}. {s['sold']} sold ({s['share']:.0f} % of all units), {pace}; {_eur(s['rev'])} of sales, {_eur(s['gm'])} gross margin ({s['margin_pct']:.0f} %); {stock_line}"
                + (f"; {s['refunds']} refund(s)" if s["refunds"] else "; no refunds") + ". "
                + ("Reorder now." if p["stock"] == 0 or (s["days_left"] and s["days_left"] < 21) else "Stock is fine.")
                + (" Push it in the next posts — it converts." if s["share"] >= 30 and p["stock"] > 0 else ""))

    def keep_or_drop(self, t, m):
        st = self.store
        gd = m.groupdict() if m is not None else {}
        what = (gd.get("what") or gd.get("what2") or gd.get("what3") or gd.get("what4") or "").strip()
        low = t.lower()
        if not what or re.search(r"\bwhich (?:product|item|one)\b", low):
            cands = []
            for p in st.products():
                s = self._product_stats(p)
                cands.append((s["share"], s["gm"], p, s))
            cands.sort(key=lambda x: (x[0], x[1]))
            if not cands or not any(c[3]["sold"] for c in cands):
                return "No sales yet, so nothing has earned a verdict — every product gets its week in the posts first."
            share, gm, p, s = cands[0]
            others = [c for c in cands if c[3]["sold"] == 0 and c[2]["stock"] > 0]
            return (f"If one has to go quiet: {p['name'].split(' (')[0]} — {s['sold']} sold ({s['share']:.0f} % of units), {_eur(s['gm'])} gross margin so far"
                    + (f", {p['stock']} pcs = {_eur(s['stock_cost'])} sitting at cost" if p["stock"] else ", and it's out of stock anyway") + ". "
                    + "Don't delist it — stop spending posts/ads on it, sell the stock through a bundle with the best seller, and don't reorder. "
                    + ("Keep advertising " + ", ".join(c[2]["name"].split(" (")[0] for c in sorted(cands, key=lambda x: -x[0])[:2]) + " — that's where the money is." if len(cands) > 1 else ""))
        p = st.find_product(what)
        if not p:
            return None
        s = self._product_stats(p)
        name = p["name"].split(" (")[0]
        day = st.data.get("day", 0)
        if not s["sold"]:
            if day < 14:
                return (f"Too early to drop the {name}: {day} practice day(s) and it's had no post of its own. The rule I use: a product gets 2 weeks with at least 3 posts; if it still sells nothing, stop reordering it, sell the {p['stock']} pcs ({_eur(s['stock_cost'])} at cost) in a bundle, then delist. "
                        "Nothing sells by itself — say “what should I post today?” and I'll pick it.")
            return f"Yes, quietly: {name} sold nothing in {day} days. Don't reorder; bundle the {p['stock']} pcs with the best seller at a small discount; delist when they're gone. Money on the shelf: {_eur(s['stock_cost'])}."
        good = s["share"] >= 20 or s["margin_pct"] >= 60 and s["sold7"] >= 1
        return (f"{'Keep' if good else 'Keep, but stop pushing'} the {name}: {s['sold']} sold ({s['share']:.0f} % of units), {_eur(s['gm'])} gross margin ({s['margin_pct']:.0f} %), "
                + (f"{s['sold7']} in the last 7 days. " if s["sold7"] else "nothing in the last 7 days. ")
                + ("It earns its place — it's " + ("a top seller." if s["share"] >= 30 else "a healthy second line.") if good else
                   "It isn't losing money, it's just quiet — no reorder beyond one small batch, sell it in bundles, and revisit in a month.")
                + (f" Watch the refunds ({s['refunds']})." if s["refunds"] else ""))

    def horizon(self, t, m):
        gd = m.groupdict()
        n = gd.get("n") or gd.get("n2") or gd.get("n3") or gd.get("n4") or "6"
        unit = (gd.get("unit") or gd.get("unit2") or gd.get("unit3") or "months").lower()
        n = {"six": 6, "three": 3, "twelve": 12, "a": 1, "sei": 6, "tre": 3, "dodici": 12}.get(n, n)
        n = int(n)
        months = n if unit.startswith("month") or unit.startswith("mes") else n * 12 if unit.startswith("year") else max(1, round(n / 4))
        st = self.store
        nn = self._n() or {}
        aov = (nn["revenue"] / nn["orders"]) if nn.get("orders") else 25.0
        margin = (nn["profit"] / nn["revenue"]) if nn.get("revenue") else 0.5
        day = st.data.get("day", 0) or 1
        per_day = nn.get("orders", 0) / day if nn.get("orders") else 0.5
        growth = 1.25                                                             # a realistic small-shop month-on-month with steady posting
        target = per_day * 30 * (growth ** months)
        target = max(target, 60 if months >= 6 else 30)
        rev = target * aov
        prof = rev * margin - 300
        prods = len(st.products())
        return (f"In {months} month{'s' if months != 1 else ''}, a realistic picture if you post daily and nothing breaks:\n"
                f"• ~{target:.0f} orders a month ({target / 30:.1f} a day) → {_eur(rev)} sales, about {_eur(prof)} a month after goods, shipping, fees and fixed bills — from {nn.get('orders', 0) / day * 30:.0f} a month at today's pace, growing ~25 % a month.\n"
                f"• Range: {prods}–{prods + 2} products, no more — one or two 'hero' items carrying 60 %+ of sales, the rest as add-ons; a bundle; a gift option before Christmas.\n"
                "• Repeat buyers 15–20 % of orders (card in every parcel + one e-mail a month) — that's what makes month 6 stable.\n"
                "• Two countries live (Italy + Germany or France), pages in both languages, shipping rules per country.\n"
                "• Reviews: 20+ real ones with photos; a review request goes out after every delivery.\n"
                "• You: 30–45 minutes a day (packing + taps), one afternoon a week for content; me: replies, numbers, proposals, drafts, study.\n"
                + ("• Legal: Partita IVA and forfettario sorted, a commercialista, e-invoicing running.\n" if months >= 3 else "")
                + "What it does NOT look like: 30 products, three marketplaces, paid ads before the page converts. Say “what's the plan for next week?” for the first step of that.")

    def hourly_rate(self, t, m):
        n = self._n() or {}
        st = self.store
        day = st.data.get("day", 0) or 1
        if not n.get("orders"):
            return "No profit yet, so the hourly rate is € 0 — normal for the first days; the hours now are an investment, not a wage. Ask again after a couple of weeks."
        orders_day = n["orders"] / day
        mins = 15 + 6 * orders_day + 10 + 20                                      # fixed check-in + 6 min/parcel + taps + content
        hours = mins / 60
        profit_day = n["profit"] / day
        rate = profit_day / hours
        return (f"Rough hourly rate: {_eur(rate)} an hour. Maths: profit {_eur(n['profit'])} in {day} day(s) = {_eur(profit_day)} a day; your time about {mins:.0f} min a day "
                f"(15 min check-in + ~6 min per parcel × {orders_day:.1f} + 10 min of taps + 20 min of content) = {hours:.1f} h. "
                + ("Below minimum wage for now — normal for month one; it rises fast because the fixed 45 minutes don't grow with orders." if rate < 9 else
                   "That's already a real rate — the fixed minutes stay the same as orders grow, so it climbs from here." if rate < 25 else "That's a good rate; the shop is paying for your time.")
                + " Tell me your real minutes per parcel and I redo it. Before taxes.")

    def time_needed(self, t, m):
        n = self._n() or {}
        st = self.store
        day = st.data.get("day", 0) or 1
        orders_day = n.get("orders", 0) / day if n.get("orders") else 1
        return (f"Per day, at {orders_day:.1f} orders a day: about {15 + 6 * orders_day + 10:.0f} minutes of must-do — 15 min morning check-in (my plate + taps), ~6 min per parcel to pack and label, 10 min of proposal/reply taps through the day. "
                "Plus the part that grows the shop: 20–30 min for one post or short video. So 45–60 minutes on a normal day; a delivery day at 10 parcels is ~1,5 h.\n"
                "Per week: one hour on Friday for numbers and decisions, one afternoon a month for photos/content in bulk.\n"
                "What I take off your hands: customer drafts, numbers, reorder maths, labels, posts' text, research, study. What stays yours: packing, money decisions, the camera. "
                "Say “can you handle the shop alone for a week?” for the away version.")

    def afford(self, t, m):
        gd = m.groupdict()
        amt = _num(gd.get("amt") or gd.get("amt2") or gd.get("amt3") or gd.get("amt4") or "50")
        if re.search(r"\d\s*k\b", t.lower()):
            amt *= 1000
        n = self._n() or {}
        st = self.store
        profit = n.get("profit", 0)
        day = st.data.get("day", 0) or 1
        month_profit = profit / day * 30
        what = re.sub(r"\b(can|we|i|afford|a|an|the|euro|euros|eur|€|\d[\d.,]*|is|too much|ok|okay|reasonable|fine|to spend|for|on)\b", " ", t.lower()).strip(" ?.,")
        what = re.sub(r"\s+", " ", what) or "it"
        useful = bool(re.search(r"\b(photo|photos|shoot|photographer|camera|light|lighting|box|boxes|packaging|sample|samples|stock|reorder|domain|card|cards|label printer|printer|tripod|video)\b", t.lower()))
        if not n.get("orders"):
            yes = amt <= 100
            return (f"{'Yes, if it' if yes else 'Not from the shop yet — it'} would come out of your pocket, not the shop's: no profit so far. " +
                    (f"{_eur(amt)} for {what} is a start-up cost, and " + ("photos are the one thing that pays back first — I'd do it." if "photo" in what else "worth it only if it makes the product page better or the parcels cheaper.") if yes else
                     f"{_eur(amt)} before the first sales is the kind of spend that hurts if the shop is slow — wait for two weeks of data."))
        payback = amt / (profit / day) if profit > 0 else None
        verdict = ("Yes" if profit >= amt else "Soon — not from today's profit, but covered within two weeks at this pace" if payback and payback <= 14 else "Not yet")
        return (f"{verdict}: {_eur(amt)} for {what} against {_eur(profit)} of profit so far ({_eur(month_profit)} a month at this pace)"
                + (f" — the shop earns it back in {payback:.0f} day(s)." if payback else " — there's no profit to pay it from yet.")
                + (" Photos/packaging pay for themselves fastest (better page = more of every visitor), so I'd say go, but pay it from profit already made, never from the money reserved for stock." if useful else
                   " Rule I use: a non-stock purchase is fine when it's under two weeks of profit and either sells more or saves time every week; otherwise it waits.")
                + (f" Keep at least {_eur(max(50, month_profit * 0.5))} untouched for a refund or a broken parcel." if profit > 0 else ""))

    def cost_what_if(self, t, m):
        gd = m.groupdict()
        what = (gd.get("what") or gd.get("what2") or "").strip()
        v = _num(gd.get("v") or gd.get("v2") or "0")
        p = self.store.find_product(what) if self.store is not None else None
        if not p or not v:
            return None
        pct = "%" in t
        new_cost = p.get("cost", 0) * (1 + v / 100) if pct else v
        price = p["price"]
        old_m = (price - p.get("cost", 0) - 0.029 * price - 0.30) / price * 100
        new_m = (price - new_cost - 0.029 * price - 0.30) / price * 100
        s = self._product_stats(p)
        per_month = s["per_day"] * 30 if s["per_day"] else 0
        hit = (new_cost - p.get("cost", 0)) * per_month
        keep_price = round(new_cost / (1 - old_m / 100 - 0.029) + 0.30, 1) - 0.1
        keep_price = max(keep_price, price)
        return (f"If the {p['name'].split(' (')[0]} cost goes from {_eur(p.get('cost', 0))} to {_eur(new_cost)}: at {_eur(price)} the margin after fees drops from {old_m:.0f} % to {new_m:.0f} %"
                + (f" — about {_eur(hit)} a month less at the current {per_month:.0f} units/month." if per_month else ".") + "\n"
                + ("Still fine — absorb it, don't touch the price." if new_m >= 45 else
                   f"Thin. To keep today's margin the price would need to be {_eur(keep_price)}; a smaller step ({_eur(round(price * 1.05 + 0.1, 0) - 0.1)}) plus asking the supplier for the old price on a bigger batch is what I'd do first." if new_m >= 30 else
                   f"Not worth selling at that cost and price: {new_m:.0f} % after fees means one refund eats three sales. Either {_eur(keep_price)} (test it — this product " + ("sells, so it may hold" if s["share"] >= 20 else "is slow, so it probably won't") + "), a second supplier, or drop it.")
                + "\nSay “the supplier raised the cost of the " + p['name'].split(' (')[0].lower() + f" to {new_cost:.2f}” when it's real and I put it in the books with the price proposal.")

    def worst_case(self, t, m):
        n = self._n() or {}
        st = self.store
        stock_cost = sum(p["stock"] * p.get("cost", 0) for p in st.products())
        day = st.data.get("day", 0) or 1
        month_profit = (n.get("profit", 0) / day * 30) if n.get("orders") else 0
        fixed = 300
        return ("Worst case for a month, honestly sized:\n"
                f"• Sales stop (a platform block, a bad review wave, a courier strike): you lose the {_eur(month_profit)} of profit you'd have made and still pay ~{_eur(fixed)} of fixed bills — that's the hole: about {_eur(month_profit + fixed)}.\n"
                f"• Stock goes stale: {_eur(stock_cost)} at cost sits on the shelf — not lost, but frozen; sold at cost in a clearance you get most of it back.\n"
                "• A bad batch (say 10 % of a product defective): refunds + return postage ≈ 1,5× the product's cost per unit; on a 20-unit batch that's ~€ 150–300 and a week of unhappy mails.\n"
                "• A chargeback dispute lost: order value + € 15–25 fee each.\n"
                "• Your time: the real worst case is a month of work for nothing — which is why we keep stock small and never buy ads before the page converts.\n"
                "What can't happen: debt (nothing is bought on credit), a fine (pages are legal, taxes set aside), or a customer harmed (no risky products). "
                "The insurance is boring: 4–6 weeks of stock max, € 200 untouched for refunds, a second supplier's sample on the shelf.")

    def customers_said(self, t, m):
        rows = self._msg_kinds(7)
        if not rows:
            return "Nothing this week — no customer messages in the last 7 days. With " + (f"{len(self._paid(7))} orders" if self._paid(7) else "no orders") + " that's normal: most buyers only write when something's wrong."
        names = {"where_is_my_order": "where is my order", "product_question": "product question", "return_or_refund": "return/refund", "damaged_or_wrong": "damaged/wrong item", "cancel_or_change": "cancel/change",
                 "discount_request": "discount request", "compliment": "compliment", "partnership_or_press": "collab/press", "spam_or_scam": "spam", "other": "other"}
        lines = [f"Customers this week ({len(rows)} message(s)):"]
        for r, k in rows[-6:]:
            lines.append(f"• {r.get('from', '?').split('@')[0]} — {names.get(k, k)}: “{r['text'][:90]}”" + ("" if r.get("status") != "new" else " (draft waiting)"))
        kinds = {}
        for _, k in rows:
            kinds[k] = kinds.get(k, 0) + 1
        top = max(kinds, key=kinds.get)
        lines.append(f"Theme: mostly '{names.get(top, top)}'. " + {"where_is_my_order": "Ship + tracking mail the same day and this theme disappears.", "product_question": "Put those answers on the product page — say “write the FAQ”.",
                                                                     "damaged_or_wrong": "Packaging, now.", "compliment": "Ask those people for a review — say “write the review request e-mail”."}.get(top, ""))
        return "\n".join(lines)

    def benchmark(self, t, m):
        n = self._n() or {}
        if not n.get("orders"):
            return "No numbers yet to compare. The yardsticks I'll use once there are: conversion 1–3 % (small shops), net margin 30–50 % for eco/home goods, basket € 25–45, return rate 2–5 %, repeat buyers 15–25 % by month 6."
        conv = n["conversion"]; margin = n["profit"] / n["revenue"] * 100 if n["revenue"] else 0
        aov = n["revenue"] / n["orders"]
        ref = n.get("refunded", 0) / max(1, n["orders"] + n.get("refunded", 0)) * 100
        def band(v, lo, hi, higher_better=True):
            return "above" if v > hi else "below" if v < lo else "in line with"
        return ("Against typical small online shops (home/eco goods, first year):\n"
                f"• Conversion {conv:.1f} % — {band(conv, 1.0, 3.0)} the 1–3 % norm.\n"
                f"• Net margin {margin:.0f} % — {band(margin, 30, 50)} the 30–50 % band (most dropshippers sit at 10–25 %).\n"
                f"• Basket {_eur(aov)} — {band(aov, 25, 45)} the € 25–45 typical for home goods.\n"
                f"• Returns {ref:.1f} % — {band(ref, 2, 5)} the 2–5 % norm (fashion runs 20–30 %).\n"
                f"• Traffic {n['visits'] / max(1, self.store.data.get('day', 1)):.0f} visits a day — small shops start at 20–100; 300+ is where ads and SEO start to matter.\n"
                "Where small shops usually lose and we should check: repeat rate (norm 15–25 % by month 6), review count (20+ before people trust a new brand), and the owner's time per parcel. "
                "These are rules of thumb from what I've read, not a live industry feed — say “research small shop benchmarks 2026, write me a document” for sourced figures.")

    def strengths(self, t, m):
        facts = self._facts()
        good = [f[1] for f in facts if f[0] == "good"]
        bad = [f[1] for f in facts if f[0] == "bad"]
        if not facts or (len(facts) == 1 and facts[0][2] == "run"):
            return "I can only judge what the ledger shows, and it shows nothing yet. Run practice days; then I'll tell you plainly where you're strong (usually: product choice, margins) and weak (usually: shipping on time, posting daily)."
        out = ["From the ledger — your work, not the products:"]
        out.append("• Good at: " + ("; ".join(good) if good else "keeping margins healthy and prices sane") + ".")
        if bad:
            out.append("• Weak at: " + "; ".join(x.split(" — ")[0] for x in bad[:3]) + ".")
        out.append("• Can't see from here: your photos, your captions, how you sound to customers — send me a post or a reply and I'll tell you.")
        out.append("• The pattern I see in most owners: strong on choosing and pricing, weak on the boring daily loop (ship, answer, post). The loop is where the money is; I can carry two of the three.")
        return "\n".join(out)

    def more_sales(self, t, m):
        gd = m.groupdict()
        n_want = gd.get("n") or gd.get("n2") or gd.get("n3") or "10"
        n_want = {"ten": 10, "twenty": 20, "five": 5, "a few": 5, "some": 5, "more": 10, "the next": 10}.get(str(n_want).lower(), n_want)
        n_want = int(n_want)
        n = self._n() or {}
        conv = n.get("conversion") or 2.0
        visits = int(n_want / (conv / 100))
        paid = self._paid()
        cust = len({(o.get("customer") or {}).get("email") for o in paid})
        units = n.get("units", {})
        best = max(units, key=units.get).split(" (")[0] if units else "the best seller"
        out = [f"{n_want} more sales, cheapest first:"]
        if cust >= 5:
            out.append(f"1. One e-mail to the {cust} people who already bought (code, one piece of news): 5–8 % order again → ~{max(1, round(cust * 0.06))} sales for € 0. Say “write the e-mail to past customers”.")
        out.append(f"{2 if cust >= 5 else 1}. {visits} more visits at your {conv:.1f} % conversion = {n_want} sales. Free: {max(3, round(visits / 40))} short videos of {best} (a decent one brings 30–80 visits), posted at 12:00 and 19:00, plus 2 Reddit/Facebook-group answers a day where people ask about the problem it solves.")
        out.append(f"{3 if cust >= 5 else 2}. A bundle or a free-shipping threshold: same visitors, bigger baskets — worth about 10–20 % more revenue without one extra visitor. Say “add the bundle”.")
        out.append(f"{4 if cust >= 5 else 3}. Only then paid: € 5 a day for 7 days on the best video ≈ 100–150 visits ≈ {max(1, round(125 * conv / 100))}–{max(2, round(150 * conv / 100))} sales — teaches you the cost per sale.")
        out.append("Not cheap ways: discounts to strangers, more products, a marketplace listing (fees eat the margin).")
        return "\n".join(out)

    def sale_or_not(self, t, m):
        n = self._n() or {}
        st = self.store
        margin = (n["profit"] / n["revenue"]) if n.get("revenue") else 0.5
        low = t.lower()
        event = "Black Friday" if "black" in low else "Cyber Monday" if "cyber" in low else "Christmas" if re.search(r"christmas|xmas|natale", low) else "the sale"
        slow = [p for p in st.products() if p["stock"] > 5 and n.get("units", {}).get(p["name"], 0) <= 1]
        return (f"{event}: yes, small and honest — no, not a 30 % storewide cut. At your {margin * 100:.0f} % net margin a 30 % discount would hand over most of the profit to people who were buying anyway.\n"
                "What works for a small shop:\n"
                "• 10–15 % with a code, 3–4 days, announced to your own list and followers first (they're the ones who'll buy) — not a homepage banner for strangers.\n"
                + (f"• Bundles instead of discounts: the pair costs less than the two, the margin stays. " + (f"Clear the slow stock in them ({', '.join(p['name'].split(' (')[0] for p in slow[:2])})." if slow else "") + "\n")
                + "• A gift angle: gift wrap + card option, 'arrives before the 24th' date on the page — that sells more than a discount in November/December.\n"
                "• Rules: the EU Omnibus rule means the 'before' price must be the lowest of the previous 30 days — no fake crossings-out; stock for 2× a normal week; ship within 24 h or don't run it.\n"
                "Say “black friday prices” and I compute per product what discount keeps the margin; “write the black friday e-mail” and I draft it.")

    def name_opinion(self, t, m):
        st = self.store
        name = st.data.get("name", "Green Nest — Eco Home Store").split(" — ")[0]
        return (f"“{name}”: good bones. Short, two plain words, easy to say and spell in Italian and English, and it tells you the category (green → eco, nest → home) without being literal. "
                "It's memorable enough for a small brand and neutral enough to grow (kitchen, bathroom, gifts).\n"
                "Weak spots: it's generic — dozens of 'Green X' eco shops exist, so search results and social handles will be crowded (check the exact handle and the .it/.com before printing anything: say “is greennest.it free?”); "
                "and it says nothing about Italy or craft, which are your two real differentiators — the tagline should carry that: “Green Nest — eco home goods, shipped from Bergamo”.\n"
                "I wouldn't rename it. I'd spend the energy on a consistent look (one green, one typeface, real photos) — a name becomes a brand by repetition, not by cleverness.")

    def ready_real(self, t, m):
        facts = self._facts()
        n = self._n() or {}
        st = self.store
        day = st.data.get("day", 0)
        done, todo = [], []
        def chk(ok, label_ok, label_todo):
            (done if ok else todo).append(label_ok if ok else label_todo)
        chk(day >= 7 or n.get("orders", 0) >= 10, f"{day} practice day(s), {n.get('orders', 0)} orders handled end to end", "run at least a full practice week (say “run 7 practice days”)")
        chk(not any(o["status"] == "paid" and day - o.get("day", day) >= 1 for o in st.data["orders"]), "orders ship on time", "late orders in the practice store — the shipping routine isn't a habit yet")
        chk(not any(p["stock"] == 0 for p in st.products()), "nothing sold out", "sold-out products still listed — reorder points aren't set")
        try:
            chk(not self.inbox.items("new"), "inbox answered", "customer messages waiting — decide the drafts")
        except Exception:
            pass
        chk(bool(st.data.get("pages", {}).get("returns")) and bool(st.data.get("pages", {}).get("shipping")), "shipping and returns pages written from the rules", "shipping/returns pages missing")
        todo += ["Partita IVA + forfettario with a commercialista (say “do I need a partita iva?” for the why)", "real product photos (your own, in real rooms)", "a payment provider and a courier contract (Stripe/PayPal + GLS/Poste Delivery Business)",
                 "your own domain and e-mail (say “is greennest.it free?”)", "20 posts scheduled before day 1 so the shop isn't silent"]
        return ("Ready for the real store? " + ("Nearly — the shop routine works; what's left is paperwork and photos." if len(done) >= 4 else "Not yet — the routine needs to be boring before the money is real.") +
                "\n✅ " + "\n✅ ".join(done) + "\n⬜ " + "\n⬜ ".join(todo) +
                "\nMy test: two practice weeks in a row with no late order, no stock-out and every message answered the same day. Then we pick the platform and I set it up with you.")

    def running_since(self, t, m):
        st = self.store
        day = st.data.get("day", 0)
        created = st.data.get("created", "")[:10]
        n = self._n() or {}
        return (f"The practice store is on day {day}" + (f" (opened {created})" if created else "") + f": {n.get('orders', 0)} orders, {_eur(n.get('revenue', 0))} of sales so far. "
                + ("A practice day passes only when you say “run a practice day” — it's not tied to the calendar." if day < 30 else "That's a month of practice — enough data to trust the averages.")
                + " The real store hasn't opened yet — say “am I ready for the real store?” for the checklist.")

    def my_mistakes(self, t, m):
        out = []
        try:
            from . import mind as _m
            recs = [j for j in _m._load(_m.LESSONS)[-40:] if j.get("snags") or (j.get("outcome") and re.search(r"fail|slow|snag|wrong|could not|couldn't|missed", str(j.get("outcome")).lower()))]
            for j in recs[-3:]:
                out.append(f"• {str(j.get('t', ''))[:10]} “{str(j.get('goal', ''))[:50]}”: " + ("; ".join(str(x) for x in (j.get("snags") or [])[:2]) or str(j.get("outcome", ""))[:120]))
        except Exception:
            pass
        try:
            rej = [p for p in self.store.data.get("proposals", []) if p["status"] == "rejected"]
            if rej:
                kinds = {}
                for p in rej:
                    kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
                out.append("• proposals you said no to: " + ", ".join(f"{k} ×{v}" for k, v in kinds.items()) + " — I take that as 'too early' or 'not your style' and propose those less.")
        except Exception:
            pass
        try:
            stt = self.inbox.stats() if self.inbox is not None else {}
            if stt.get("decisions"):
                out.append(f"• customer drafts: {stt['edited']} edited and {stt['rejected']} rejected out of {stt['decisions']} — each edit is a lesson I keep for that kind of message.")
        except Exception:
            pass
        if not out:
            return ("None recorded yet — no job went wrong, no proposal was refused, no draft was rejected. That's partly because I've done little; the honest list of where I'm weakest: "
                    "I don't see photos or tone unless you show me, my forecasts are rough with small numbers, and I sometimes ask for a tap on things you'd rather I just did. Tell me and I adjust.")
        return "Where I got it wrong, from my own records:\n" + "\n".join(out[:5]) + "\nWhat I do with it: each job ends with a lesson note; your no's and edits change what I propose next."

    def learned(self, t, m):
        bits = []
        try:
            if self.mind is not None:
                txt = self.mind.lessons_text(limit=4)
                if txt and not txt.startswith("No lessons"):
                    bits.append(txt)
        except Exception:
            pass
        try:
            notes = self.memory.notes(limit=6, days=7) if self.memory else []
            if notes:
                bits.append("📚 Notes this week: " + "; ".join(dict.fromkeys(f"{r['kind']}: {r['topic'][:40]}" for r in notes)))
        except Exception:
            pass
        try:
            n = self._n() or {}
            if n.get("orders"):
                units = n.get("units", {})
                best = max(units, key=units.get) if units else None
                bits.append(f"🏪 From the shop: {best.split(' (')[0]} sells most; conversion runs at {n['conversion']:.1f} %; " + ("net margin is healthy." if n["revenue"] and n["profit"] / n["revenue"] >= 0.4 else "margin needs watching.") if best else "")
        except Exception:
            pass
        bits = [b for b in bits if b]
        if not bits:
            return "Nothing new this week — no jobs finished, no study sessions. Give me a task or an away-window and I'll have something to report."
        return "\n".join(bits)
