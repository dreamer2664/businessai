"""Talk — the everyday questions an owner asks in plain words, answered directly (milestone 20 polish).

Before a message is turned into a job, this layer catches the things that need no browsing at all:

  • "what can you do?"                       → a short menu in plain words
  • "thanks, that's all" / "bye"             → a short goodbye, no menu, no job
  • "what did you do today?"                 → recap from the journal, lessons, notes and library
  • "how much should I charge for X that costs me Y?"  → the pricing maths (2.5× / 3× / 4×, fee, margin)
  • "is € 3.90 shipping too much for Italy?" → a grounded rule of thumb
  • "customer says … what do I answer?"      → treated as a customer message: a draft with Approve/Edit/Reject
  • "where do I start selling X online?"     → the standard first steps, offered as a to-do list
  • "add 'call the accountant' to my list" / "my to-do list" / "done 2" / "I ordered the boxes, tick it off"
  • "what time is it in Shenzhen?"           → local time there, gap to the owner's clock, office-hours hint
  • "shopify vs woocommerce?"                → a grounded opinion from a small table of the usual choices
  • "translate to english: …" / "how do you say X in italian" → {"translate", "to"} for the agent's thinking model
  • "do I need a partita iva?" / "how much tax on € 1,000 in Italy?" / "the customer wants a refund but used it"
                                             → Italian shop basics and EU return rules as rules of thumb (always: confirm with a commercialista)
  These "quick" ones (Talk.quick) are answered even while a job is running; the job is not touched.

Everything here is rules + arithmetic; nothing is invented. Returns None when the message is not one of these,
so the normal understanding (brief → plan → job) takes over.
"""
import datetime as _dt
import json
import re

_MONEY = r"(?:€|eur|euro|euros|\$|usd|£)?\s*(\d+(?:[.,]\d+)?)\s*(?:€|eur|euro|euros|\$|usd|£|k)?"


def _num(s):
    return float(s.replace(",", "."))


def _eur(x):
    return f"€ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class Talk:
    CAN_DO = re.compile(r"^\W*(what (can|could) you do|what do you do|what are you (able|good) (to|at)|how can you help|cosa (sai|puoi) fare|che cosa fai|what else can you do)\b", re.I)
    BYE = re.compile(r"^\W*((ok(ay)?|alright|great|perfect|cool|thanks?|thank you|grazie|ty|thx)[\s,!.]*)*(that'?s all( for now)?|bye|goodbye|see you|talk later|ciao|a dopo|good night|buonanotte|nothing else|no more for now|later)\b", re.I)
    THANKS = re.compile(r"^\W*(thanks?( you)?( a lot| so much)?|grazie( mille)?|ty|thx|perfect|great job|well done|nice work|good job)\W*$", re.I)
    TODAY = re.compile(r"\b(what (did|have) you (do|done|work(ed)? on|been up to)( today| so far| this morning)?|remind me what you did|recap( of)? (today|the day)|what happened today|cosa hai fatto( oggi)?|daily recap|summary of (today|your day))\b", re.I)
    PRICE = re.compile(r"\b(how much (should|can|do) i (charge|sell|price|ask)|what (price|should i charge)|(sell|retail) price for|quanto (dovrei|posso) (chiedere|far pagare)|a che prezzo)\b", re.I)
    COST = re.compile(r"\b(?:costs?(?: me)?|cost price|i pay|buy (?:it )?(?:for|at)|mi costa|pago)\s*" + _MONEY, re.I)
    SHIP_OK = re.compile(r"\b(?:is|are)\s*" + _MONEY + r"\s*(?:for )?(?:shipping|delivery|spedizione)(?: (?:cost|fee))?(?: (?:to|for|in) [a-z ]{2,20}?)?\s*(?:too (?:much|expensive|high)|ok|okay|fine|reasonable|fair|normal|a lot|acceptable|right)"
                         r"|\b(?:è|e'|sono) (?:troppo|troppi|giusto|giusti|ok|normale|normali|tanto|tanti|caro|cara)?\s*" + _MONEY + r"\s*(?:di |per la |per )?spedizione", re.I)
    LAST_DOC_IT = re.compile(r"\b(?:mandami|rimandami|inviami|rimanda|manda|carica)\b.{0,20}\b(?:l'?ultimo|quel|il) (?:documento|report|file|pdf)\b", re.I)
    CUSTOMER = re.compile(r"\b(?:a |the |my )?(?:customer|client|buyer|cliente)s?\s+(?:says?|wrote|writes|asks?|is asking|complain(?:s|ed)?|messaged|emailed|sent|dice|scrive|chiede)\b(?P<inner>.{0,400}?)(?:what (?:do|should|can) i (?:answer|reply|say|tell|write)|how (?:do|should) i (?:answer|reply|respond)|cosa (?:rispondo|gli dico|le dico)|what now)\b", re.I | re.S)
    START = re.compile(r"\b(where (do|should) i (start|begin)|how (do|should|can) i (start|begin|get started)|i want to (start|sell|open)|voglio (vendere|aprire|iniziare)|da dove (comincio|inizio|parto))\b", re.I)
    OPINION_IT = re.compile(r"\b(che ne pensi|cosa ne pensi|secondo te)\b", re.I)
    # ---- the practice store in plain words ----
    STORE_NUM = re.compile(r"\b(?:how many (?:orders|sales|visitors|visits|customers)|(?:what(?:'s| is| are) )?(?:our|my|the) (?:best[- ]?sellers?|top (?:product|seller)s?|conversion(?: rate)?|revenue|turnover|profit|margin|numbers|visitors|visits)|how much (?:profit|money|revenue) (?:did|have) (?:we|i) (?:make|made|earn|earned)|(?:profit|revenue|sales) (?:so far|this week|today|this month)|summary of (?:the|this|my) (?:week|day|month)|(?:weekly|daily) summary|how(?:'s| is| are) (?:business|sales|things) going|quanti ordini|quante visite|quanto abbiamo (?:guadagnato|venduto|incassato)|qual è il (?:più venduto|best seller)|riepilogo (?:della )?settimana)\b", re.I)
    SHIP_COST_Q = re.compile(r"\b(?:how much (?:is|does|do we charge for|costs?) (?:the )?(?:shipping|delivery|postage)|(?:shipping|delivery) (?:cost|price|fee)s?(?: to| for)?|what do we charge (?:for )?(?:shipping|delivery)|quanto (?:costa|chiediamo per) (?:la )?spedizione|quanto costa spedire)\b", re.I)
    SELLOUT_Q = re.compile(r"\b(?:how long (?:until|before|till) (?:the |our )?(?P<what>[a-z][a-z \-]{2,40}?) (?:sells? out|runs? out|is gone|is sold out)|when (?:will|does) (?:the |our )?(?P<what2>[a-z][a-z \-]{2,40}?) (?:sell out|run out)|(?:stock|units) (?:left )?(?:of |for )?(?:the )?(?P<what3>[a-z][a-z \-]{2,40}?) (?:last|lasts|will last)|quanto dura(?:no)? (?:le |la |il |lo |gli |i )?(?P<what4>[a-zà-ú][a-zà-ú \-]{2,40}?)\?)", re.I)
    MATHS = re.compile(r"^\W*(?:what(?:'s| is)|quanto (?:fa|è)|calcola|calculate|compute)?\s*(?P<a>\d+(?:[.,]\d+)?)\s*%\s*(?:of|di|del|della)\s*(?P<b>\d+(?:[.,]\d+)?)\W*$"
                       r"|^\W*(?:what(?:'s| is)|quanto fa)?\s*(?P<c>\d+(?:[.,]\d+)?)\s*(?:€|eur|euro)?\s*(?:plus|più|\+)\s*(?P<d>\d+(?:[.,]\d+)?)\s*%\W*$"
                       r"|^\W*(?:what(?:'s| is)|quanto fa)?\s*(?P<e>\d+(?:[.,]\d+)?)\s*(?:€|eur|euro)?\s*(?:minus|meno|less|-)\s*(?P<f>\d+(?:[.,]\d+)?)\s*%\W*$"
                       r"|^\W*(?:what(?:'s| is)|quanto fa|calcola|calculate|compute)?\s*(?P<expr>[\d.,]+(?:\s*[-+*/x×÷:]\s*[\d.,]+)+)\W*$", re.I)
    WHATIF = re.compile(r"\b(?:if|when|se)\s+(?:i|we)\s+(?:sell|sold|vendo|vendiamo)\s+(?P<n>\d+)\s+(?P<what>[a-zà-ú][a-zà-ú \-]{2,40}?)\s+(?:a|per|al|every|each|ogni)\s+(?P<per>month|week|day|mese|settimana|giorno)\b.{0,40}?\b(?:at|a|for|per)\s*" + _MONEY.replace("(\\d", "(?P<price>\\d") + r".{0,30}?\b(?:cost|costs|costing|costo|that cost me|mi costa)\s*" + _MONEY.replace("(\\d", "(?P<cost>\\d") + r"|\b(?:if|when|se)\s+(?:i|we)\s+(?:sell|sold|vendo|vendiamo)\s+(?P<n2>\d+)\s+(?P<what2>[a-zà-ú][a-zà-ú \-]{2,40}?)\s+(?:a|per|al|every|each|ogni)\s+(?P<per2>month|week|day|mese|settimana|giorno)\b", re.I)
    THANK_NOTE = re.compile(r"\b(?:write|draft|make|scrivi|scrivimi|prepara)\b.{0,20}?\b(?:thank[- ]you (?:note|card|message|slip)|thanks card|note (?:to put |for )?(?:in|into) the (?:parcels?|packages?|boxes?|orders?)|biglietto (?:di ringraziamento|per i pacchi)|messaggio di ringraziamento)\b", re.I)
    CANCEL_HOW = re.compile(r"\bhow (?:do|should|can) i (?:answer|reply to|respond to|handle|deal with)\b.{0,30}?\b(?:customer|client|buyer|someone)\b.{0,30}?\b(?:cancel|cancellation|refund|return|complain|angry|wants? (?:their|his|her) money back)\b|\bcome rispondo a un cliente che (?:vuole annullare|vuole il rimborso|si lamenta)\b", re.I)
    REMIND_AT = re.compile(r"^\W*(?:remind me|ricordami)\s+(?P<when>(?:tomorrow|domani|today|oggi|tonight|stasera|on \w+day|monday|tuesday|wednesday|thursday|friday|saturday|sunday|lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica|in \d+ (?:hours?|minutes?|days?|ore|minuti|giorni))(?:\s+(?:at|alle|alle ore)\s+\d{1,2}(?:[:.]\d{2})?(?:\s*(?:am|pm))?)?|(?:at|alle)\s+\d{1,2}(?:[:.]\d{2})?(?:\s*(?:am|pm))?(?:\s+(?:tomorrow|domani|today|oggi))?)\s+(?:to|di|a)?\s*(?P<what>.+?)\W*$", re.I)
    DOMAIN_Q = re.compile(r"\b(?:is|check(?: if| whether)?|see if|verify|controlla se|vedi se)\b.{0,30}?\b(?:the )?domain\b.{0,30}?\b(?P<dom>[a-z0-9-]+\.(?:com|it|eu|net|org|shop|store|co|io|de|fr|es))\b.{0,20}?\b(?:free|available|taken|libero|disponibile|occupato)\b|\b(?P<dom2>[a-z0-9-]+\.(?:com|it|eu|net|org|shop|store|co|io|de|fr|es))\b.{0,20}?\b(?:free|available|taken|libero|disponibile)\?", re.I)
    STORE_OPEN = re.compile(r"^\W*(?:can you |could you |please |puoi )?(?P<verb>open|start|launch|turn on|close|stop|shut|apri|avvia|chiudi)\s+(?:up |down )?(?:the |my |our |il |lo |la )?(?:practice |test |fake |training |online )?(?:store|shop|negozio|bottega)\b", re.I)
    STORE_STOCK = re.compile(r"\b(?:what(?:'s| is| do we have| do i have) (?:in |the |our |my )?stock|stock (?:levels?|list|situation|status)|how many .{2,30}? (?:do (?:we|i) have|are left|in stock|left)|list (?:the |our |my )?products|(?:our|my) (?:products|catalogue|catalog)|cosa (?:abbiamo|c'è) in magazzino|quant[ei] .{2,30}? (?:abbiamo|restano|rimangono))\b", re.I)
    STORE_DAY = re.compile(r"\b(?:(?:run|simulate|start|do|play|fai)\s+(?:a |one |another |the next |un |un altro )?(?:practice |test |training )?(?:day|giorno)|(?:a |one |another )?(?:practice |test )?day (?:passes|goes by)|let (?:a|the) day pass|practice day|giorno di prova|passa un giorno)\b", re.I)
    STORE_REVIEW = re.compile(r"\b(?:review the (?:store|shop)|store review|what (?:do you|would you) (?:propose|suggest) (?:for|in) the (?:store|shop)|any proposals|what (?:should|needs to|do) (?:i|we) (?:do|fix) in the (?:store|shop)|cosa proponi per il negozio|controlla il negozio)\b", re.I)
    STORE_ORDERS = re.compile(r"\b(?:(?:open|pending|new|today'?s|latest|recent|last|unshipped|paid) orders|orders to ship|what (?:do i|should i|needs to be|do we) ship|which orders|show (?:me )?(?:the )?orders|ordini (?:da spedire|aperti|recenti|nuovi)|quali ordini)\b", re.I)
    STORE_LABELS = re.compile(r"\b(?:print|prepare|make|generate|create|give me|stampa|prepara|fammi)\b.{0,20}?\b(?:shipping labels?|labels?|packing slips?|etichette|bolle|lettere di vettura)\b|\b(?:shipping labels?|packing slips?|etichette)\b.{0,25}?\b(?:for|of|per)\b.{0,25}?\b(?:orders?|ordini|today|oggi)\b", re.I)
    STORE_SHIPPED = re.compile(r"^\W*(?:all |everything |tutto )?(?:shipped|sent|handed (?:to|over to) (?:the )?(?:courier|gls|carrier)|spedito|spediti|consegnato al corriere)\b.{0,30}$|^\W*(?:i (?:have |'ve )?)?(?:shipped|sent|posted) (?:all |every |the |today's )?(?:orders|parcels|packages|ordini|pacchi)\b.{0,30}$", re.I)
    STORE_NAME_Q = re.compile(r"\b(?:what(?:'s| is) (?:the |my |our )?(?:store|shop) (?:called|name)|what(?:'s| is) the name of (?:the|my|our) (?:store|shop)|come si chiama il (?:negozio|shop))\b", re.I)
    ADD_PRODUCT = re.compile(r"^\W*(?:can you |could you |please |puoi )?(?:add|list|create|put up|aggiungi|metti|inserisci)\s+(?:a |the |this |new |a new |another |un |una |nuovo |nuova |un nuovo |una nuova )*(?:product|item|listing|article|prodotto|articolo)\s*[:\-–—]?\s*(?P<name>.+?)(?=\s*[,;:—]|\s+(?:that|which|it|costs?|costing|cost|at|sells?|selling|for|priced?|prezzo|costa|che)\b|\W*$)(?P<rest>.*)$", re.I | re.S)
    PRICE_CHANGE = re.compile(r"\b(?:lower|raise|increase|decrease|drop|cut|bump|change|set|update|put|move|abbassa|alza|metti|cambia|porta)\s+(?:the |il |la )?(?:price|prezzo)\s+(?:of|for|di|del|della|dello|dei)\s+(?:the |a |an |our |my |il |la |lo |i )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:to|at|a|down to|up to|→)\s*" + _MONEY.replace("(\\d", "(?P<v1>\\d")
                              + r"|\b(?:make|price|sell)\s+(?:the |il |la )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:at |for |a )?" + _MONEY.replace("(\\d", "(?P<v2>\\d") + r"\s*(?:from now on|instead|d'ora in poi)\b", re.I)
    STOCK_CHANGE = re.compile(r"\b(?:set|update|put|correct|metti|aggiorna)\s+(?:the )?stock\s+(?:of|for|di|del|della)\s+(?:the |il |la )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:to|at|a)\s+(?P<n>\d+)\b|\b(?:we |i )?(?:received|got|have got|restocked|arrived with|sono arrivat[ei])\s+(?P<n2>\d+)\s+(?:more |new |extra |altri |altre |nuov[ei] )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)(?:\s+(?:today|from the supplier|dal fornitore|oggi))?\W*$", re.I)
    # ---- shop sense: reviews, free shipping, couriers, hashtags, video ideas ----
    BAD_REVIEW = re.compile(r"\b(?:(?:1|one|2|two)[- ]star|bad|negative|angry|nasty|terrible|awful|unfair|brutta|negativa|cattiva)\s+(?:review|recensione|rating|feedback|stelle)\b|\b(?:review|recensione)\b.{0,40}?\b(?:broke|broken|damaged|late|never arrived|rude|scam|fake|rotto|rotta|danneggiato|mai arrivato)\b|\b(?:left|gave|wrote|posted|ha lasciato|ha scritto)\s+(?:us |me |a |una )?(?:\d[- ]star|bad|negative|brutta) (?:review|recensione)\b", re.I)
    FREE_SHIP = re.compile(r"\b(?:should (?:i|we) (?:offer|do|give|have) free (?:shipping|delivery)|free (?:shipping|delivery) (?:threshold|or not|worth it|yes or no|good idea)|is free (?:shipping|delivery) (?:a good idea|worth it|smart)|(?:offer|give) free (?:shipping|delivery)\?|spedizione gratuita (?:sì o no|conviene|o no)|conviene (?:la |offrire la )?spedizione gratuita|soglia (?:per la |della )?spedizione gratuita)", re.I)
    COURIER = re.compile(r"\b(?:which|what|cheapest|best|good|migliore|quale|che)\b.{0,30}?\b(?:courier|carrier|shipping (?:company|service|provider)|corriere|spedizioniere)\b|\b(?:corriere|courier|carrier)\b.{0,20}?\b(?:cheap|cheapest|economico|conviene|use|choose|pick|recommend)\b|\bhow (?:do|should|can) (?:i|we) ship (?:the |my |our )?(?:orders|parcels|packages|products)\b|\bcome spedisco\b", re.I)
    HASHTAGS = re.compile(r"\b(?:what|which|quali|che)\s+hashtags?\b|\bhashtags?\s+(?:for|per|to use|should (?:i|we) use|da usare)\b|\b(?:suggest|give me|dammi|suggerisci)\b.{0,12}?\bhashtags?\b", re.I)
    VIDEO_IDEAS = re.compile(r"\b(?:(?P<n>\d+|three|four|five|six|a few|some|un paio di|qualche|tre|cinque)\s+)?(?:tiktok|reels?|instagram|short|short-form|video|content|post)\s+(?:video |content |post )?(?:ideas?|idee|concepts?|hooks?|scripts?)\b|\b(?:ideas?|idee)\s+(?:for|per|di)\s+(?:a |some |\d+ |un |dei )?(?:tiktoks?|reels?|videos?|short videos?|video|contenuti)\b", re.I)
    TODO_ADD = re.compile(r"^\W*(?:please\s+|can you\s+|could you\s+)?(?:add|put|write|note|jot(?: down)?|aggiungi|segna|metti)\s+(?P<item>.+?)\s+(?:to|on|in|onto|into|alla|nella|sulla)\s+(?:my |the |our |our |la |mia )?(?:to-?do(?: list)?|list|lista|todo|tasks?|reminders?|note)s?\W*$"
                          r"|^\W*(?:remind me to|ricordami di|todo:|to-do:|to do:)\s*(?P<item2>.+?)\W*$", re.I)
    TODO_SHOW = re.compile(r"^\W*(?:what(?:'s| is) (?:on )?(?:my |the |our )?(?:to-?do|list|todo)(?: list)?|show (?:me )?(?:my |the |our )?(?:to-?do|todo|list)(?: list)?|(?:my |the )?(?:to-?do|todo)(?: list)?\??|my list|read (?:me )?(?:my |the )?(?:to-?do|list)|cosa (?:c'è|ho) (?:da fare|in lista)|(?:la )?(?:mia )?lista)\W*$", re.I)
    TODO_DONE = re.compile(r"^\W*(?:(?:mark |tick |check )?(?:off )?(?:number |item |#)?(?P<n>\d+)\s+(?:as )?(?:done|is done|finished|complete[d]?|fatto|fatta)|(?:done|finished|fatto)\s+(?:with )?(?:number |item |#)?(?P<n2>\d+)|(?:i(?:'ve| have)? )?(?:did|called|sent|finished|handled|ordered|paid|booked|emailed|wrote|bought|fixed|posted|shipped|answered|already did|took care of)\s+(?P<what>.{3,60}?)(?:,? (?:you can )?(?:tick|cross|mark|check|strike) (?:it|that)(?: off)?|,? (?:it's )?done)?)\W*$", re.I)
    TIME_IN = re.compile(r"\b(?:what(?:'s| is) the time|what time is it|che ora (?:è|sono)|che ore sono|current time|local time)(?: (?:now|right now|adesso|ora))?(?: (?:in|at|a) (?P<place>[a-zà-ú][a-zà-ú .'-]{1,40}?))?\W*$", re.I)
    TRANSLATE = re.compile(r"^\W*(?:can you |could you |please |per favore )?(?:translate|traduci(?:mi)?|traduce)(?:\s*[:\-–—]\s*|\s+)(?:this |that |it |the following |me |questo |questa )?"
                           r"(?:(?:into|in|to|a) (?P<lang>english|italian|german|french|spanish|portuguese|chinese|dutch|inglese|italiano|tedesco|francese|spagnolo|portoghese|cinese|olandese))?\s*[:\-–—]?\s*(?P<text>.+)?$", re.I | re.S)
    SAY_IN = re.compile(r"^\W*(?:how (?:do|would) (?:you|i) say|come si dice)\s+[\"“']?(?P<text>.+?)[\"”']?\s+in (?P<lang>english|italian|german|french|spanish|portuguese|chinese|dutch|inglese|italiano|tedesco|francese|spagnolo|portoghese|cinese|olandese)\W*$", re.I | re.S)
    LANGS = {"inglese": "English", "italiano": "Italian", "tedesco": "German", "francese": "French", "spagnolo": "Spanish", "portoghese": "Portuguese", "cinese": "Chinese", "olandese": "Dutch"}
    AWAY = re.compile(r"^\W*(?:i'?m |i am |sono |vado |going |off )?(?:off to|going to|heading to|away for|out for|back in|be back in|at|in|a|fuori per|torno tra|torno fra)\s+(?:lunch|dinner|the gym|gym|a meeting|meetings|work|bed|sleep|pranzo|cena|palestra|riunione|letto|(?:about |circa |~)?\d+ ?(?:min|minutes|minuti|h|hours?|ore|ora))\b.{0,40}?(?:back in|torno (?:tra|fra)|for)?\s*(?:about |circa |~)?(?P<n>\d+|an?|un[ao]?|half an|mezz')?\s*(?P<u>min(?:ute)?s?|minuti|h|hours?|ore|ora)?\W*$"
                      r"|^\W*(?:brb|bbl|afk|gotta go|i have to go|talk later|ci sentiamo dopo|a dopo|torno dopo)\W*$", re.I)
    HERE_Q = re.compile(r"^\W*(?:are you (?:there|here|awake|alive|online|around|still there|with me)|you there|ci sei|sei (?:lì|li|online|sveglio)|hello\?+|anyone (?:there|home))\W*$", re.I)
    LAST_DOC = re.compile(r"\b(?:send|resend|show|give|forward|mandami|rimandami|inviami)\b.{0,20}\b(?:last|latest|previous|that|the) (?:doc(?:ument)?|report|file|pdf|comparison|seller check|research)\b|\b(?:last|latest) (?:doc(?:ument)?|report|file) (?:again|please)\b|\bupload\b.{0,20}\b(?:doc(?:ument)?|report|file)\b.{0,20}\b(?:drive|google)\b", re.I)
    STORE_Q = re.compile(r"\b(?:how(?:'s| is| are) (?:the |my |our )?(?:practice |test |fake )?(?:store|shop|sales|orders|numbers)(?: doing| going)?|(?:store|shop) (?:numbers|stats|status|report)|come va (?:il negozio|lo shop)|quanti ordini)\b", re.I)
    DECIDED = re.compile(r"\b(?:what did we (?:decide|say|agree)|what was (?:decided|agreed)|remind me what we (?:decided|said|agreed)|cosa avevamo (?:deciso|detto)|what were (?:the|our) (?:conclusions|findings))\b.{0,12}?(?:about|on|for|regarding|su|per)\s+(?P<topic>.+?)\W*$", re.I)
    WHY_SLOW = re.compile(r"\bwhy (?:did|was|has) (?:the |that |my |your )?(?P<what>.{2,40}?) (?:take so long|so slow|take (?:that|so) much time|fail|not work|go wrong|break)\b|\bwhat (?:went wrong|happened) (?:with|on|during) (?:the |that )?(?P<what2>.{2,40}?)\W*$|\bperch[eé] (?:ci hai messo tanto|è andata male)\b", re.I)
    IT_BIZ = re.compile(r"\b(partita iva|p\.? ?iva|vat number|forfettario|forfetario|flat[- ]tax|regime forfettario|inps|ateco|codice ateco|scia|camera di commercio|registro (?:delle )?imprese|commercialista|oss\b|one[- ]stop[- ]shop|fattura elettronica|electronic invoic)\w*", re.I)
    TAX_ON = re.compile(r"\b(?:how much )?(?:tax(?:es)?|imposte|tasse)\b.{0,30}?(?:on|su|for|per)\s*" + _MONEY + r"\s*(?:of |di |in )?(?:sales|revenue|turnover|income|fatturato|vendite|incassi)?", re.I)
    RETURNS_Q = re.compile(r"\b(?:customer|client|buyer|cliente)\b.{0,40}?\b(?:refund|return|rimborso|reso|money back)\b.{0,60}?\b(?:used|worn|opened|damaged by|after \d+ days|late|too late|no receipt|without (?:the )?box|usato|aperto|in ritardo)\b|\b(?:do i have to|must i|am i obliged to|devo)\b.{0,20}?\b(?:refund|accept the return|rimborsare|accettare il reso)\b", re.I)
    OPINION = re.compile(r"\b(?:what do you think(?: about| of)?|what(?:'s| is) (?:your (?:take|opinion|view)|better)|which (?:is|one is|would you) (?:better|pick|choose|recommend)|should i (?:use|go with|pick|choose)|would you (?:recommend|suggest)|is it worth|che ne pensi|cosa ne pensi|secondo te|meglio)\b", re.I)
    VS = re.compile(r"\b(?P<a>[a-z0-9][a-z0-9 .'+-]{1,30}?)\s+(?:vs\.?|versus|or|o|oppure)\s+(?P<b>[a-z0-9][a-z0-9 .'+-]{1,30}?)(?=[\s?.!,]|$)", re.I)

    WRITE_DESC = re.compile(r"\b(?:write|draft|make|create|give|scrivi|scrivimi|fammi)\b.{0,20}?\b(?:product )?(?:description|descrizione|listing text|product text|blurb|copy)\b.{0,20}?\b(?:for|of|about|per|di)\s+(?:a |an |the |our |my |un |una |il |la )?(?P<what>.+?)(?:,\s*(?P<lines>\d+)\s*(?:lines?|righe|sentences?|frasi))?\W*$", re.I)
    NAME_SHOP = re.compile(r"\b(?:what (?:should|could|do) i (?:name|call)|name ideas? for|names? for|suggest (?:a )?names?|come (?:chiamo|lo chiamo)|nome per)\b.{0,20}?\b(?:shop|store|brand|business|negozio|marchio)\b", re.I)
    LAUNCH_LIST = re.compile(r"\b(?:make|write|give|prepare|build|fammi|scrivi)\b.{0,12}?\b(?:to-?do|todo|check-?list|task list|plan)\b.{0,30}?\b(?:launch|launching|opening|open|go live|lancio|apertura|aprire)\b", re.I)
    MAIL_CODE = re.compile(r"\b(?:check|look (?:in|at)|read|open|controlla|guarda)\b.{0,12}?\b(?:my |the |your |la |il )?(?:e-?mail|gmail|inbox|posta|mail)\b.{0,30}?\b(?:code|codice|verification|verifica|otp|link|conferma|confirmation)\b|\b(?:verification|confirmation) (?:code|link|mail|email)\b.{0,20}?\b(?:e-?mail|gmail|inbox|posta|arrived|check)\b", re.I)

    def __init__(self, memory=None, mind=None, library=None, inbox=None, store=None, log=None, planner=None):
        self.planner = planner
        self.memory = memory
        self.mind = mind
        self.library = library
        self.inbox = inbox
        self.store = store
        self.log = log or (lambda kind, **f: None)

    # ---- entry --------------------------------------------------------------------------------
    GREET = re.compile(r"^\W*(hi|hello|hey|yo|ciao|buongiorno|buonasera|good (morning|afternoon|evening)|morning|evening)\b[\s,!.]*(there|bot|mate|man)?[\s,!.]*(how'?s it going|how are you|how are things|what'?s up|come va|tutto bene|all good)?\W*$", re.I)

    def reply(self, text):
        """The direct answer, or a dict {"customer": <their message>} / {"todo": [...], "text": ...} for the agent to act on, or None."""
        t = (text or "").strip()
        if not t or t.startswith("/"):
            return None
        low = t.lower()
        if self.GREET.match(t):
            return self.greet()
        if self.CAN_DO.search(t):
            return self.can_do()
        if self.BYE.match(t) and len(low.split()) <= 8:
            return self.bye()
        if self.THANKS.match(t):
            return "You're welcome. I'm here when you need the next thing."
        if self.TODAY.search(t):
            return self.today()
        q = self.quick(t)                                              # to-do, clock, opinions — also answered while I'm busy
        if q is not None:
            return q
        m = self.CUSTOMER.search(t)
        if m:
            return {"customer": self._customer_text(t, m)}
        m = self.MATHS.match(t)
        if m:
            r = self.maths(m)
            if r:
                return r
        if self.THANK_NOTE.search(t):
            return self.thank_note(t)
        if self.CANCEL_HOW.search(t):
            return self.cancel_how(t)
        m = self.DOMAIN_Q.search(t)
        if m:
            return {"domain": (m.group("dom") or m.group("dom2")).lower()}
        st = self.store_talk(t)                                        # the practice shop in plain words (open, stock, prices, labels…)
        if st is not None:
            return st
        sense = self.shop_sense(t)                                     # bad review, free shipping, couriers, hashtags, video ideas
        if sense is not None:
            return sense
        if self.PRICE.search(t) or (self.COST.search(t) and re.search(r"\b(price|charge|sell|margin|markup|prezzo)\b", low)):
            p = self.pricing(t)
            if p:
                return p
        m = self.SHIP_OK.search(t)
        if m:
            return self.shipping_ok(_num(m.group(1) or m.group(2)), t)
        if self.START.search(t) and re.search(r"\b(sell|selling|shop|store|online|business|vendere|negozio|dropship)", low):
            return self.start_plan(t)
        return None

    # ---- quick things (answered even in the middle of a job) --------------------------------------
    def quick(self, t):
        """To-do adds/list/done, 'what time is it in X', and A-vs-B opinions. None when it's not one of these."""
        low = t.lower()
        m = self.REMIND_AT.match(t)
        if m and self.memory is not None:
            return self.remind_at(m.group("when"), m.group("what"))
        m = self.TODO_ADD.match(t)
        if m and self.memory is not None:
            item = (m.group("item") or m.group("item2") or "").strip(" '\"“”.")
            if 2 <= len(item) <= 200 and not re.search(r"https?://", item):
                n = self.memory.add(item[0].upper() + item[1:])
                return {"todo_added": n, "text": f"Added to your to-do list as #{n}: {item[0].upper() + item[1:]}\n({len(self.memory.open_items())} open — say “my to-do list” to see it, “done {n}” when it's handled.)"}
        if self.TODO_SHOW.match(t) and self.memory is not None:
            items = self.memory.open_items()
            if not items:
                return "Your to-do list is empty. Say “add … to my list” and I keep it."
            return "Your to-do list:\n" + "\n".join(f"  {x['id']}. {x['text']}" for x in items) + "\nSay “done <number>” when one is handled."
        m = self.TODO_DONE.match(t)
        if m and self.memory is not None:
            n = m.group("n") or m.group("n2")
            x = None
            if n:
                x = self.memory.done(n)
            else:
                what = (m.group("what") or "").lower()
                words = [w for w in re.findall(r"[a-zà-ú]{4,}", what) if w not in ("with", "that", "this", "just", "already")]
                for it in self.memory.open_items():
                    if words and sum(w in it["text"].lower() for w in words) >= max(1, len(words) - 1):
                        x = self.memory.done(it["id"])
                        break
                if x is None and not words:
                    return None
            if x:
                left = len(self.memory.open_items())
                return f"Ticked off: {x['text']}" + (f" — {left} left." if left else " — list empty, nice.")
            return "I couldn't find that on the list. Say “my to-do list” and then “done <number>”." if n else None
        if self.HERE_Q.match(t):
            return self.here()
        if self.MAIL_CODE.search(t):
            return {"mail_code": True, "hint": self._sender_hint(t)}
        m = self.WRITE_DESC.search(t)
        if m and len(t.split()) <= 30:
            return self.description(m.group("what"), int(m.group("lines") or 0), t)
        if self.NAME_SHOP.search(t):
            return self.shop_names(t)
        if self.LAUNCH_LIST.search(t):
            return self.launch_list(t)
        if self.AWAY.match(t) and not re.search(r"\b(research|find|check|compare|build|write|look|cerca|trova)\b", low):
            return {"away": self._away_minutes(t), "text": self.away_line(t)}
        if self.LAST_DOC.search(t) or self.LAST_DOC_IT.search(t):
            return {"last_doc": True, "to_drive": bool(re.search(r"\b(drive|google|upload|carica)\b", low))}
        if self.STORE_Q.search(t) and self.store is not None:
            try:
                return self.store.numbers_text() + "\n(/store for the pages and the orders to ship)"
            except Exception:
                return None
        m = self.DECIDED.search(t)
        if m:
            return self.decided(m.group("topic"))
        m = self.WHY_SLOW.search(t)
        if m:
            return self.why_slow((m.group("what") or m.group("what2") or "").strip())
        m = self.TAX_ON.search(t)
        if m and re.search(r"\b(ital(?:y|ia)|forfettario|partita iva)\b", low):
            return self.tax_on(_num(m.group(1)))
        if self.IT_BIZ.search(t) and re.search(r"\?|\b(do i need|need|serve|devo|how|what|quanto|come|cosa)\b", low):
            return self.it_biz(t)
        if self.RETURNS_Q.search(t) and not self.CUSTOMER.search(t):       # "…what do I answer?" → a draft instead (inbox)
            return self.returns_rule(t)
        m = self.TIME_IN.search(t)
        if m:
            return self.clock(m.group("place"))
        m = self.SAY_IN.match(t) or self.TRANSLATE.match(t)
        if m:
            lang = (m.group("lang") or "").lower()
            body = (m.group("text") or "").strip(" :\"“”'")
            if body:
                lang = self.LANGS.get(lang, lang.title() if lang else "")
                if not lang:                                                  # guess: Italian text → English, else → Italian
                    lang = "English" if re.search(r"\b(il|la|di|che|per|non|una|uno|sono|con|del|della|grazie|ciao|dove|quando)\b", body.lower()) else "Italian"
                return {"translate": body, "to": lang}
        if self.OPINION.search(t) or self.VS.search(t) and re.search(r"\?$", t.strip()):
            op = self.opinion(t)
            if op:
                return op
        return None

    @staticmethod
    def _sender_hint(t):
        m = re.search(r"\b(?:from|da|di)\s+([a-z0-9][a-z0-9.-]{2,30})\b", t.lower())
        if m and m.group(1) not in ("the", "my", "your", "gmail", "email", "mail", "inbox"):
            return m.group(1)
        m = re.search(r"\b(shopify|etsy|ebay|amazon|vinted|tiktok|instagram|facebook|meta|paypal|stripe|aliexpress|alibaba|cj|wix|canva|pinterest|x|twitter|linkedin|google|apple)\b", t.lower())
        return m.group(1) if m else ""

    def _fact_lines(self, what):
        """Facts the owner or the shop already gave about a product — the only material a description may use."""
        facts = []
        try:
            p = self.store.find_product(what) if self.store is not None else None
            pw = [w for w in re.findall(r"[a-z]{4,}", p["name"].lower()) if w not in ("with", "pack")] if p else []
            ww = [w.rstrip("s") for w in re.findall(r"[a-z]{4,}", what.lower())]
            # the request's own head noun (last word: "cork SANDAL") must be in the product name — "cork" alone is not the same product
            if p and ww and any(ww[-1] == w.rstrip("s") for w in pw) and sum(w.rstrip("s") in ww for w in pw) >= max(1, len(pw) // 2):
                facts.append(p.get("short") or p["name"])
                facts += [d for d in p.get("details", [])[:4] if d.lower()[:25] not in (p.get("short") or "").lower()]
        except Exception:
            pass
        try:
            for r in (self.memory.notes(what, limit=2) if self.memory else []):
                if r.get("kind") in ("research", "summary", "study", "learned"):
                    facts.append(r["text"][:200])
        except Exception:
            pass
        return facts

    def description(self, what, lines, full_text):
        """'write me a product description for a cork sandal, 2 lines' — from the facts I have; never invented specs."""
        what = what.strip(" .,'\"")
        given = re.search(r"^(.*?)[,;:\-–—]\s*(?:it'?s|they'?re|it is|made (?:of|from|in)|features?|with|has|comes? with)\b\s*(.{6,160})$", what, re.I)
        if given:                                                         # "linen apron, it's made of washed linen with two pockets"
            what, extra = given.group(1).strip(" ,"), given.group(2).strip(" .")
        else:
            extra = ""
        lines = lines or 3
        facts = self._fact_lines(what)
        if extra:
            facts.append(extra)
        text = ""
        if self.planner is not None and self.planner.installed():
            try:
                text = self.planner.chat("You write short, honest product descriptions for a small online shop. Use ONLY the facts given; no prices, no delivery promises, no health or 'best' claims, no invented materials.",
                                         f"Product: {what}\nFacts:\n" + ("\n".join(f"- {f}" for f in facts) if facts else "- (none beyond the name)") + f"\nWrite {lines} short sentence(s), plain words, no hashtags, no emoji.",
                                         max_tokens=60 * lines + 40, temperature=0.3, timeout=120).strip().strip('"“”')
            except Exception:
                text = ""
        if text and re.search(r"[$€£]\s?\d|\d\s?(?:€|eur)|\b(free shipping|guaranteed|best|cures?|100 ?%)\b|ships? (in|within)", text, re.I):
            text = ""                                                     # the model slipped in a price/claim → fall back to the template
        note = ""
        if not text:
            core = what[0].upper() + what[1:]
            fl = [f for f in facts if len(f) < 140][:max(1, lines - 1)]
            if fl:
                first = fl[0].rstrip(".")
                text = f"{core} — {first}." + (" " + " ".join(f.rstrip('.') + "." for f in fl[1:]) if fl[1:] else "")
            else:
                text = f"{core} — made for everyday use, in a simple design that goes with anything."
            text += " Tell us which one you'd like and we prepare it with care."
            note = "\n(Plain version — my thinking model is off, or I have no facts on it yet. Give me 2–3 facts — material, size, what makes it different — and I rewrite it.)" if not facts else "\n(Built only from the facts I have on it. Add a detail and I rewrite it.)"
        return f"Description for {what}:\n{text}{note}"

    def shop_names(self, t):
        """'what should I name my shop? it sells cork sandals' → 6 name ideas built from what it sells + how to check them."""
        m = re.search(r"\b(?:sells?|selling|for|vende|di)\s+(?:my |our |the )?([a-z][a-z \-]{2,40}?)(?:\s+online|\s*[,.?!]|$)", t, re.I)
        what = (m.group(1).strip() if m else "").lower()
        words = [w for w in re.findall(r"[a-z]{3,}", what) if w not in ("shop", "store", "online", "products", "things", "stuff", "and", "the")]
        core = (words[0] if words else "shop").rstrip("s")
        core2 = (words[1] if len(words) > 1 else "").rstrip("s")
        cap = core.capitalize(); cap2 = core2.capitalize()
        ideas = [f"{cap}&Co", f"Casa {cap}", f"{cap} Studio", f"The {cap} Room", f"Ciao {cap}", f"{cap}{cap2 or 'Lab'}", f"Piccolo {cap}", f"{cap} Milano"]
        ideas = list(dict.fromkeys(i for i in ideas if len(i) <= 18))[:6]
        return (f"Name ideas for a shop that sells {what or 'this'}:\n" + "\n".join(f"  • {i}" for i in ideas) +
                "\nHow to pick: say it out loud (easy to spell over the phone?), then check in this order — .com/.it domain free, Instagram and TikTok handle free, "
                "no identical trademark (EUIPO search), no famous brand inside the name. Tell me your favourite two and I check the handles and domains for you.")

    def launch_list(self, t):
        """'make a to-do list for launching the store next monday' → the launch checklist, on the to-do list, in order."""
        when = re.search(r"\b(next (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month)|tomorrow|this (?:week|weekend|friday)|on \w+day|in \d+ days?|lunedì|domani)\b", t, re.I)
        when = when.group(0) if when else "launch day"
        todo = ["Final check of every product page: photos, honest description, price, stock, options",
                "Shipping set: prices per country, free-shipping threshold, delivery days written on the shipping page",
                "Legal pages live: terms, privacy, returns (14-day EU withdrawal), contact with a real address and email",
                "Test order end to end with a real card (then refund it): checkout, confirmation mail, order in admin",
                "Payment methods on: card + PayPal; confirm the payout account",
                "Launch posts drafted for Instagram/TikTok (3 posts + 1 story) — I draft, you approve",
                "Customer replies ready: shipping times, returns, 'where is my order' — I answer from the policy, you approve",
                f"{when.capitalize()}: open the shop, publish post 1, watch the first orders and messages together"]
        return {"todo": todo, "text": f"Launch list for {when} — in the order I'd do it, and it's on your to-do list now:\n" +
                "\n".join(f"{i + 1}. {s}" for i, s in enumerate(todo)) + "\nTell me which ones you want me to do (2, 3, 6 and 7 are mine to prepare)."}

    # ---- Italian business basics (rules of thumb, always "confirm with a commercialista") -----------
    IT_NOTE = "\n(Rules of thumb from the official rules as I know them — confirm the numbers with a commercialista before you file anything.)"

    def it_biz(self, t):
        low = t.lower()
        if re.search(r"partita iva|p\.? ?iva|vat number", low) and re.search(r"\b(need|serve|devo|do i|necessary|required|without|senza|start|open|aprire)\b", low):
            return ("Yes — for a shop that is open all the time (your own site or a marketplace storefront) Italy treats selling as a continuous business, so you need a "
                    "Partita IVA from the first sale. The famous “€ 5,000 a year without Partita IVA” does not exist for selling goods: that threshold is for occasional freelance services (INPS gestione separata). "
                    "Only truly occasional sales (a few used items of your own, no stock, no ads) are exempt.\n"
                    "What opening it means: Partita IVA with ATECO 47.91.10 (retail via internet), Registro Imprese, SCIA to the Comune (SUAP), INPS Gestione Commercianti — a commercialista does it all in about a week, "
                    "typically € 300–600 for the set-up and € 800–1,500 a year to keep the books. Regime forfettario (see below) is the usual choice for a small shop." + self.IT_NOTE)
        if re.search(r"forfettario|forfetario|flat[- ]tax", low):
            return ("Regime forfettario for an online shop: allowed up to € 85,000 revenue a year; no VAT charged to customers and none reclaimed; taxable income = revenue × 40 % (the coefficient for retail); "
                    "on that you pay a flat 5 % for the first 5 years of a new business, then 15 %. On top come INPS Gestione Commercianti contributions: a fixed minimum of roughly € 4,600 a year "
                    "(you can ask for a 35 % reduction under forfettario) plus about 24 % on income above ~€ 18,500. Example: € 20,000 sales → € 8,000 taxable → € 400 tax (5 %) + INPS ≈ € 3,000 with the reduction." + self.IT_NOTE)
        if re.search(r"\binps\b", low):
            return ("INPS for an online shop = Gestione Commercianti: a fixed minimum contribution of about € 4,600 a year even with tiny sales (reduced by 35 % on request if you're in forfettario), "
                    "plus roughly 24 % of business income above the minimum base (~€ 18,500). It's the biggest fixed cost of a small shop in Italy — plan for it from month one." + self.IT_NOTE)
        if re.search(r"\boss\b|one[- ]stop[- ]shop", low):
            return ("OSS (One Stop Shop) matters once your sales to consumers in OTHER EU countries pass € 10,000 a year in total: above that you charge the customer's country VAT and declare it through one quarterly OSS return "
                    "in Italy instead of registering in every country. Under € 10,000 you keep Italian VAT (or none, in forfettario). Note: forfettario sellers who cross € 10,000 of EU distance sales still have to apply destination VAT via OSS." + self.IT_NOTE)
        if re.search(r"ateco", low):
            return "ATECO for an online shop: 47.91.10 — “commercio al dettaglio di qualsiasi tipo di prodotto effettuato via internet”. Dropshipping uses the same code. Handmade goods you make yourself add the artisan code for the craft." + self.IT_NOTE
        if re.search(r"fattura elettronica|electronic invoic", low):
            return "Electronic invoicing (fattura elettronica via SdI) is mandatory for all Partita IVA holders in Italy, forfettario included. For consumer sales on your own shop you issue a daily 'corrispettivo' instead of an invoice unless the customer asks for one." + self.IT_NOTE
        if re.search(r"commercialista", low):
            return "A commercialista for a small online shop costs about € 800–1,500 a year (forfettario, few invoices) — online ones (Fiscozen, Flextax, Taxfix-style) sit at the low end. Worth it from day one: the INPS and forfettario rules have traps." + self.IT_NOTE
        return None

    def tax_on(self, amount):
        taxable = amount * 0.40
        return (f"On {_eur(amount)} of sales in regime forfettario: taxable income = 40 % = {_eur(taxable)}; flat tax 5 % = {_eur(taxable * 0.05)} in the first 5 years (15 % = {_eur(taxable * 0.15)} after). "
                f"Separately, INPS Gestione Commercianti asks a fixed minimum of about € 4,600 a year (≈ € 3,000 with the 35 % forfettario reduction) whatever you sell — so at small volumes INPS, not tax, is the real cost. "
                f"Outside forfettario you'd pay VAT 22 % on sales plus IRPEF (23 % upward) on the real profit." + self.IT_NOTE)

    def returns_rule(self, t):
        low = t.lower()
        if re.search(r"\b(used|worn|opened|usato|aperto|without (?:the )?box)\b", low):
            return ("EU rule (Italy included): within 14 days of delivery the customer can withdraw for any reason and you must refund within 14 days of getting the goods back — even if the item was used. "
                    "BUT you may deduct the loss in value caused by handling beyond what a shop would allow (worn outside, washed, scratched). Two exceptions where you can refuse: sealed hygiene goods that were unsealed "
                    "(cosmetics, earbuds, underwear) and made-to-order items. If they say it's faulty, that's the 2-year legal guarantee instead: repair/replace first, refund if that fails.\n"
                    "What I'd do: ask for photos, refund the price minus a fair deduction (say 20–30 % for clear use), explain it in one calm sentence. Want me to draft that reply?")
        if re.search(r"\b(after \d+ days|late|too late|in ritardo)\b", low):
            return ("After the 14-day withdrawal window you're not obliged to take a change-of-mind return — unless your own returns page promises more (a 30-day policy binds you). "
                    "A faulty item is different: the 2-year legal guarantee applies whenever the defect shows up. Many small shops still accept a late return as store credit — cheap goodwill. Want me to draft the reply?")
        if re.search(r"\bdamaged by\b", low):
            return ("Damage the customer caused is not covered by withdrawal or guarantee — you can refuse the refund. Damage in transit is your risk until delivery: refund or replace, then claim from the courier. "
                    "Ask for photos of the item and the box before deciding. Want me to draft the reply?")
        return ("Refunds in the EU, in one breath: 14 days to withdraw for any reason (refund within 14 days of return, you may deduct for use beyond trying it), 2-year legal guarantee for defects (repair/replace, then refund), "
                "transit damage is on you until delivery, sealed hygiene goods and custom items are excluded from withdrawal. Tell me the exact case and I draft the reply.")

    def here(self):
        """'are you there?' → yes, plus what I'm doing — the honest one-liner an assistant gives."""
        try:
            if self.mind and self.mind.job:
                return "Yes, here — " + self.mind.status_line()
        except Exception:
            pass
        bits = []
        try:
            n = len(self.inbox.items("new")) if self.inbox else 0
            if n:
                bits.append(f"{n} customer message(s) wait for your tap")
        except Exception:
            pass
        try:
            k = len(self.memory.open_items()) if self.memory else 0
            if k:
                bits.append(f"{k} open to-do(s)")
        except Exception:
            pass
        return "Yes, here and free." + (" " + " · ".join(bits) + "." if bits else "") + " What do you need?"

    @staticmethod
    def _away_minutes(t):
        low = t.lower()
        m = re.search(r"(\d+|an?|un[ao]?|half an|mezz')\s*(min(?:ute)?s?|minuti|h|hours?|ore|ora)\b", low)
        if m:
            n = m.group(1)
            n = 30 if n.startswith(("half", "mezz")) else 1 if n in ("a", "an", "un", "una", "uno") else int(n)
            return n * 60 if m.group(2).startswith(("h", "or")) else n
        return {"lunch": 60, "pranzo": 60, "dinner": 90, "cena": 90, "gym": 90, "palestra": 90, "meeting": 60, "riunione": 60, "work": 300, "bed": 480, "sleep": 480, "letto": 480}.get(
            next((w for w in ("lunch", "pranzo", "dinner", "cena", "gym", "palestra", "meeting", "riunione", "work", "bed", "sleep", "letto") if w in low), ""), 45)

    def away_line(self, t):
        mins = self._away_minutes(t)
        span = f"{mins // 60} h" if mins >= 120 else f"{mins} min" if mins < 60 else "1 h"
        busy = ""
        try:
            if self.mind and self.mind.job:
                busy = f" I keep going on “{self.mind.job['goal'][:50]}” and the result waits here."
        except Exception:
            pass
        return f"Enjoy — I'll count on about {span}.{busy} If nothing is running I use the time to study (PDFs, business videos) and I only ping you for something urgent. Say hi when you're back."

    def decided(self, topic):
        """'what did we decide about shipping prices?' → my notes and lessons on it, dated — not a fresh guess."""
        topic = topic.strip(" ?.!")
        out = []
        try:
            for r in (self.memory.notes(topic, limit=3) if self.memory else []):
                out.append(f"• {r['t'][:10]} ({r.get('kind', 'note')} on {r.get('topic', '')[:40]}): {r['text'][:220]}")
        except Exception:
            pass
        try:
            from . import mind as _m
            words = set(re.findall(r"[a-z0-9]{3,}", topic.lower()))
            for j in _m._load(_m.LESSONS)[-40:]:
                hay = (j.get("goal", "") + " " + j.get("outcome", "")).lower()
                if words and sum(w in hay for w in words) >= max(1, len(words) - 1):
                    out.append(f"• {j.get('t', '')[:10]} job “{j.get('goal', '')[:50]}”: {j.get('outcome', '')[:200]}")
        except Exception:
            pass
        try:
            docs = [d for d in (self.library.recent(30) if self.library else []) if all(w in d.get("title", "").lower() for w in topic.lower().split()[:2])]
            for d in docs[:2]:
                out.append(f"• {str(d.get('t', ''))[:10]} document: {d.get('title', '')} (/library)")
        except Exception:
            pass
        if not out:
            return f"I have nothing written down about “{topic}” — we never settled it with me, or it was before my notes. Want me to look into it now?"
        return f"What I have on “{topic}”:\n" + "\n".join(dict.fromkeys(out[:6])) + "\nIf that's not what you meant, tell me the angle."

    def why_slow(self, what):
        """'why did the seller check take so long yesterday?' → the reflected job: time, snags, lesson."""
        try:
            from . import mind as _m
            recs = _m._load(_m.LESSONS)
        except Exception:
            recs = []
        words = set(re.findall(r"[a-z0-9]{3,}", what.lower())) - {"the", "that", "this", "job", "task", "yesterday", "today", "last"}
        kinds = {"seller": "seller_check", "sellers": "seller_check", "check": "seller_check", "research": "research", "comparison": "compare", "compare": "compare", "website": "build_site", "site": "build_site", "video": "watch", "summary": "summarize"}
        want_kind = next((kinds[w] for w in words if w in kinds), None)
        cands = [r for r in recs if (want_kind and r.get("kind") == want_kind) or (words and any(w in r.get("goal", "").lower() for w in words))]
        if not cands:
            return f"I can't find a job like “{what}” in my journal — say 'what did you do today' or /lessons and I'll show what I have."
        r = cands[-1]
        mins = r.get("seconds", 0) / 60
        snags = [s for s in r.get("snags", []) if s]
        why = ("; ".join(snags[:3]) if snags else "no snags noted — it was simply the amount of pages to read (each listing means the page, its reviews and a social page)")
        return (f"The {r.get('kind', 'job')} “{r.get('goal', '')[:60]}” on {r.get('t', '')[:10]} took {mins:.0f} min" + (" and ran late" if r.get("late") else "") +
                f". What slowed it: {why}. Lesson I kept: {r.get('lesson') or 'none'}. Next time say a time limit and I trim the checks to fit.")

    CITY_TZ = {"milan": "Europe/Rome", "milano": "Europe/Rome", "rome": "Europe/Rome", "roma": "Europe/Rome", "italy": "Europe/Rome", "italia": "Europe/Rome",
               "london": "Europe/London", "londra": "Europe/London", "uk": "Europe/London", "england": "Europe/London", "paris": "Europe/Paris", "parigi": "Europe/Paris", "berlin": "Europe/Berlin", "berlino": "Europe/Berlin", "germany": "Europe/Berlin",
               "madrid": "Europe/Madrid", "spain": "Europe/Madrid", "lisbon": "Europe/Lisbon", "lisbona": "Europe/Lisbon", "portugal": "Europe/Lisbon", "amsterdam": "Europe/Amsterdam", "athens": "Europe/Athens", "istanbul": "Europe/Istanbul", "moscow": "Europe/Moscow",
               "new york": "America/New_York", "nyc": "America/New_York", "ny": "America/New_York", "boston": "America/New_York", "miami": "America/New_York", "toronto": "America/Toronto", "chicago": "America/Chicago", "texas": "America/Chicago", "dallas": "America/Chicago",
               "denver": "America/Denver", "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles", "san francisco": "America/Los_Angeles", "california": "America/Los_Angeles", "seattle": "America/Los_Angeles", "vancouver": "America/Vancouver",
               "mexico city": "America/Mexico_City", "mexico": "America/Mexico_City", "sao paulo": "America/Sao_Paulo", "brazil": "America/Sao_Paulo", "buenos aires": "America/Argentina/Buenos_Aires",
               "dubai": "Asia/Dubai", "delhi": "Asia/Kolkata", "mumbai": "Asia/Kolkata", "india": "Asia/Kolkata", "bangkok": "Asia/Bangkok", "singapore": "Asia/Singapore", "hong kong": "Asia/Hong_Kong", "hongkong": "Asia/Hong_Kong",
               "shanghai": "Asia/Shanghai", "beijing": "Asia/Shanghai", "shenzhen": "Asia/Shanghai", "guangzhou": "Asia/Shanghai", "yiwu": "Asia/Shanghai", "china": "Asia/Shanghai", "cina": "Asia/Shanghai", "taipei": "Asia/Taipei", "seoul": "Asia/Seoul", "tokyo": "Asia/Tokyo", "japan": "Asia/Tokyo",
               "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne", "australia": "Australia/Sydney", "auckland": "Pacific/Auckland", "cairo": "Africa/Cairo", "lagos": "Africa/Lagos", "johannesburg": "Africa/Johannesburg", "nairobi": "Africa/Nairobi",
               "utc": "UTC", "gmt": "UTC"}

    def clock(self, place):
        """'what time is it in shenzhen?' → the local time there and the gap to the owner's clock (supplier chat hours matter)."""
        import zoneinfo
        here = _dt.datetime.now().astimezone()
        if not place:
            return f"It's {here:%H:%M} here ({here:%A %d %B})."
        key = place.strip().lower().rstrip("?.! ")
        tz = self.CITY_TZ.get(key)
        if not tz:
            cand = [z for z in zoneinfo.available_timezones() if key.replace(" ", "_") in z.lower()]
            tz = sorted(cand, key=len)[0] if cand else None
        if not tz:
            return f"I don't know the time zone of “{place.strip()}” offhand — tell me the country or a big city near it."
        there = here.astimezone(zoneinfo.ZoneInfo(tz))
        diff = (there.utcoffset() - here.utcoffset()).total_seconds() / 3600
        gap = "same time as here" if abs(diff) < 0.01 else f"{abs(diff):g} h {'ahead of' if diff > 0 else 'behind'} you"
        day = "" if there.date() == here.date() else (" (already tomorrow there)" if there.date() > here.date() else " (still yesterday there)")
        tip = ""
        if 0 <= there.hour < 8 or there.hour >= 22:
            tip = " — it's night there, so don't expect a reply from a supplier before their morning."
        elif 9 <= there.hour < 18 and there.weekday() < 5:
            tip = " — office hours there, a good moment to message a supplier."
        return f"In {place.strip().title()} it's {there:%H:%M}{day} — {gap}{tip}"

    OPINIONS = {
        ("shopify", "woocommerce"): ("Shopify if you want to be selling this week and not touch servers: hosted, ~€ 27–36/month plus 2 % transaction fee unless you use Shopify Payments, apps for everything, support 24/7. "
                                     "WooCommerce if you already have WordPress or want zero monthly licence: free plugin, but you pay hosting (~€ 5–15/month), you update and back it up yourself, and every extra (subscriptions, advanced shipping) is a paid plugin. "
                                     "For a first dropshipping store with no tech person: Shopify. For a content site that also sells a few things: WooCommerce."),
        ("shopify", "etsy"): ("Etsy first if your products are handmade/vintage/craft supplies: buyers are already there, listing costs $0.20 and ~6.5 % + payment fees per sale, no marketing needed at the start. "
                              "Shopify when you want your own brand, repeat customers and no marketplace rules — but then you bring the traffic yourself. Many small sellers do both: Etsy for discovery, Shopify for the brand."),
        ("aliexpress", "cj dropshipping"): ("AliExpress is the widest catalogue with the slowest and least predictable shipping (10–30 days to Italy unless the seller uses AliExpress Standard/Choice). "
                                            "CJ Dropshipping has fewer products but its own warehouses (some in Europe), quality checks and 5–12 day lines — better for a store that has already found its 3–5 products. "
                                            "Start on AliExpress to test, move winners to CJ or a European wholesaler."),
        ("dropshipping", "own stock"): ("Dropshipping = no money tied up in stock, but thin margins (10–25 %) and you don't control shipping or quality. Own stock = better margins (40–60 %), fast shipping, your own packaging — but cash upfront and the risk of unsold boxes. "
                                        "Sensible path: dropship to find what sells, then buy 50–100 units of the winners from the same or a European supplier."),
        ("instagram", "tiktok"): ("TikTok gives reach for free right now — a new account can get 10k views from zero if the first 2 seconds are good; Instagram is better for trust and repeat buyers (profile as a shop window, DMs, saved posts). "
                                  "For a new small store: make short vertical videos for TikTok and repost them as Reels — one production, two channels."),
        ("paypal", "stripe"): ("Offer both. Stripe is what Shopify Payments uses underneath: cards, Apple/Google Pay, ~1.5 % + € 0,25 for EU cards. PayPal costs more (~3.4 % + € 0,35) but many Italian buyers only trust PayPal on an unknown shop — not offering it loses sales."),
        ("amazon", "own store"): ("Amazon = traffic and trust from day one, but 15 % referral fee, FBA storage costs, price wars and no customer relationship. Own store = your margin and your customers, but you buy every visitor with ads or content. "
                                  "For a brand you plan to keep: own store, with Amazon as a second channel later."),
        ("facebook ads", "google ads"): ("Google Ads catches people already searching for the product (high intent, good for known items like “cork sandals”); Facebook/Instagram ads create the want (good for new/impulse products under € 40, needs video). "
                                         "Under € 300/month budget: pick one, test 2 weeks, read the numbers — don't split it."),
    }
    ALIASES = {"woo": "woocommerce", "woo commerce": "woocommerce", "wordpress": "woocommerce", "ali": "aliexpress", "ali express": "aliexpress", "cj": "cj dropshipping", "cjdropshipping": "cj dropshipping",
               "ig": "instagram", "insta": "instagram", "tik tok": "tiktok", "own shop": "own store", "my own store": "own store", "own website": "own store", "own site": "own store", "my own site": "own store",
               "stock": "own stock", "holding stock": "own stock", "inventory": "own stock", "buying stock": "own stock", "meta ads": "facebook ads", "fb ads": "facebook ads", "instagram ads": "facebook ads", "adwords": "google ads"}

    def opinion(self, text):
        low = text.lower()
        names = set()
        for key in list(self.ALIASES) + [n for pair in self.OPINIONS for n in pair]:
            if re.search(r"\b" + re.escape(key) + r"\b", low):
                names.add(self.ALIASES.get(key, key))
        for pair, ans in self.OPINIONS.items():
            if set(pair) <= names:
                return f"My take on {pair[0].title()} vs {pair[1].title()}: {ans}\nIf you tell me the product and budget I can make it more precise."
        if len(names) == 1:
            n = next(iter(names))
            for pair, ans in self.OPINIONS.items():
                if n in pair:
                    other = pair[1] if pair[0] == n else pair[0]
                    return f"On {n.title()} (compared with {other.title()}, the usual alternative): {ans}"
        return None

    # ---- answers -------------------------------------------------------------------------------
    def can_do(self):
        shop = " · the practice shop (/store)" if self.store is not None else ""
        return ("Here's what I do, in plain words:\n"
                "• Look things up on the web and hand you a proper document (links, pictures, key points) — “research X, write me a document”\n"
                "• Check sellers deeply before you buy — page, reviews, social pages, complaints, shipping — “is this seller ok? <link>” or “find me reliable suppliers of X”\n"
                "• Compare suppliers side by side — “compare suppliers of X”\n"
                "• Read a page or a video for you — paste a link\n"
                "• Answer customers — forward me their message, I draft the reply, you approve\n"
                "• Draft social posts and rehearse posting on a practice network — “rehearse posting about X”\n"
                "• Build a full website for a business — “build a website for <place>” (and train on random real places)\n"
                "• Price things — “how much should I charge for X that costs me Y?”\n"
                "• Keep your to-do list — “add … to my list”, “my to-do list”, “done 2” — and tell you the time in a supplier's city\n"
                "• Give you my take — “shopify vs woocommerce?”, “is 9 € shipping to Germany normal?”, “should I offer free shipping?”, “a customer left a 1-star review, what do I do?”, “which courier is cheapest?”\n"
                "• Run the practice shop with you in plain words — “open the practice store”, “what's in stock?”, “lower the price of the lamp to 35”, “add a new product: …”, “print the shipping labels”, “all shipped”\n"
                "• Social bits — “what hashtags for eco products?”, “3 tiktok video ideas for the cork case”\n"
                "• Study on my own when you're away (PDFs, business videos → my Drive library)" + shop + "\n"
                "Pace words work: “make it quick, 10 minutes” or “I'm at work 5 hours, take it slow”. Say “stop” or “what are you doing?” any time.")

    def greet(self):
        """Hello with a one-line status: what's waiting, what I did last — so the owner knows where we stand."""
        hour = _dt.datetime.now().hour
        hello = "Good morning!" if 5 <= hour < 12 else "Good afternoon!" if 12 <= hour < 18 else "Good evening!"
        bits = []
        try:
            new = len(self.inbox.items("new")) if self.inbox else 0
            if new:
                bits.append(f"{new} customer message(s) wait for your tap (/inbox)")
        except Exception:
            pass
        try:
            from . import mind as _m
            last = (_m._load(_m.LESSONS) or [None])[-1]
            if last:
                bits.append(f"last job: {last.get('kind', '?')} “{last.get('goal', '')[:40]}” ({'done' if last.get('delivered') else 'not delivered'})")
        except Exception:
            pass
        try:
            n = len(self.memory.open_items()) if self.memory else 0
            if n:
                bits.append(f"{n} open to-do(s)")
        except Exception:
            pass
        return hello + " All good here." + (" " + " · ".join(bits) + "." if bits else "") + " What do you need — a search, a seller check, a document, a website, or just a question?"

    def bye(self):
        n = 0
        try:
            n = len(self.memory.open_items()) if self.memory else 0
        except Exception:
            pass
        tail = f" You have {n} open to-do(s); I'll keep studying quietly." if n else " I'll keep studying quietly and ping you only if something needs you."
        return "Alright — talk later." + tail

    def today(self):
        day = _dt.date.today().isoformat()
        parts = []
        try:
            from . import mind as _m
            jobs = [r for r in _m._load(_m.LESSONS) if r.get("t", "")[:10] == day]
            if jobs:
                parts.append(f"• {len(jobs)} job(s) finished: " + "; ".join(f"{j.get('kind', '?')} “{j.get('goal', '')[:50]}”" + ("" if j.get("delivered") else " (not delivered)") for j in jobs[-6:]))
            jl = [r for r in _m._load(_m.JOURNAL) if r.get("t", "")[:10] == day]
            if jl and not jobs:
                parts.append(f"• {len(jl)} step(s) worked today, last: {jl[-1].get('what', '')[:80]}")
        except Exception:
            pass
        try:
            docs = [d for d in (self.library.recent(20) if self.library else []) if str(d.get("t", ""))[:10] == day]
            if docs:
                parts.append("• documents written: " + "; ".join(d.get("title", "?")[:50] for d in docs[:5]))
        except Exception:
            pass
        try:
            notes = self.memory.notes(limit=30, days=1) if self.memory else []
            kinds = {}
            for r in notes:
                kinds.setdefault(r.get("kind", "note"), []).append(r.get("topic", ""))
            for k, topics in list(kinds.items())[:5]:
                parts.append(f"• {k}: " + "; ".join(dict.fromkeys(t[:40] for t in topics))[:160])
        except Exception:
            pass
        try:
            if self.inbox:
                new = len(self.inbox.items("new"))
                if new:
                    parts.append(f"• {new} customer message(s) waiting for your tap (/inbox)")
        except Exception:
            pass
        if not parts:
            return "Nothing finished yet today — no jobs, no documents. Give me something to do, or I'll study in the quiet time."
        return f"Today ({day}):\n" + "\n".join(parts)

    # ---- the practice store in plain words ----------------------------------------------------
    def store_talk(self, t):
        """'open the practice store', 'what's in stock?', 'lower the price of the lamp to 35', 'add a new product: …',
        'print the shipping labels', 'all shipped' → a store command or an owner change for core to run. None otherwise."""
        if self.store is None or re.search(r"https?://", t):
            return None
        low = t.lower()
        m = self.WHATIF.search(t)
        if m:
            return self.what_if(m)
        m = self.SELLOUT_Q.search(t)
        if m:
            return self.sell_out(m.group("what") or m.group("what2") or m.group("what3") or m.group("what4") or "")
        if self.SHIP_COST_Q.search(t) and not re.search(r"\b(cheapest|courier|corriere|packlink|poste|which|quale)\b", low):
            return self.ship_cost(t)
        if self.STORE_NUM.search(t) and not re.search(r"\b(what is a|what's a|define|meaning|mean|cos'è|explain)\b", low):
            return self.store_numbers(t)
        m = self.STORE_OPEN.match(t)
        if m:
            return {"store_cmd": "close" if re.match(r"(close|stop|shut|chiudi)", m.group("verb"), re.I) else "open"}
        if self.STORE_LABELS.search(t):
            return {"store_cmd": "labels"}
        if self.STORE_SHIPPED.match(t):
            return {"store_cmd": "shipped_all"}
        if self.STORE_ORDERS.search(t):
            return {"store_cmd": "orders"}
        if self.STORE_STOCK.search(t) and not re.search(r"\b(dead stock|stock photo|stock image|in stock\?? on|amazon|aliexpress|supplier)\b", low):
            return {"store_cmd": "stock"}
        if self.STORE_DAY.search(t):
            n = re.search(r"\b(\d)\s+(?:practice |test )?days\b", low)
            return {"store_cmd": f"day {n.group(1)}" if n else "day"}
        if self.STORE_REVIEW.search(t):
            return {"store_cmd": "review"}
        if self.STORE_NAME_Q.search(t):
            if re.search(r"\b(sells?|selling|vende|for|per)\b", low) and self.NAME_SHOP.search(t) is None:
                return self.shop_names(t)                                    # "come si chiama il negozio? vende sandali" → name ideas
            return f"The practice shop is called “{self.store.data.get('name', 'Green Nest')}”. Say “name ideas for a shop that sells …” if you want a name for a real one."
        m = self.PRICE_CHANGE.search(t)
        if m:
            what = (m.group("what") or m.group("what2") or "").strip()
            value = _num(m.group("v1") or m.group("v2") or "0")
            p = self.store.find_product(what)
            if not p:
                return f"I don't have a product like “{what}” in the shop. Products: " + ", ".join(x["name"] for x in self.store.products()) + "."
            if value <= 0:
                return None
            return {"store_change": {"kind": "price", "product": p["id"], "value": round(value, 2), "name": p["name"], "old": p["price"], "cost": p.get("cost", 0)}}
        m = self.STOCK_CHANGE.search(t)
        if m:
            what = (m.group("what") or m.group("what2") or "").strip()
            n = int(m.group("n") or m.group("n2"))
            p = self.store.find_product(what)
            if not p:
                return None
            add = bool(m.group("n2"))                                        # "we received 20 more lamps" adds; "set stock of … to 20" sets
            return {"store_change": {"kind": "stock", "product": p["id"], "value": p["stock"] + n if add else n, "name": p["name"], "old": p["stock"]}}
        m = self.ADD_PRODUCT.match(t)
        if m:
            name = re.sub(r"\s+", " ", m.group("name")).strip(" .,:;-–—\"'“”")
            rest = m.group("rest") or ""
            if len(name) < 3 or self.store.find_product(name) and self.store.find_product(name)["name"].lower() == name.lower():
                return None
            mc = self.COST.search(rest) or re.search(r"\b(?:cost|costs|costo|costa)\b\D{0,12}" + _MONEY, rest, re.I)
            mp = re.search(r"\b(?:sell(?:ing)?(?: it)?(?: at| for)?|price(?:d)?(?: at| of)?|list(?:ed)?(?: at)?|retail(?: at)?|vend(?:o|erlo)(?: a)?|prezzo(?: di)?|at|a)\s*" + _MONEY, rest, re.I)
            cost = _num(mc.group(1)) if mc else 0.0
            price = _num(mp.group(1)) if mp else 0.0
            if price and cost and abs(price - cost) < 0.01:                 # "at 24" matched the cost itself
                price = 0.0
            if not price and cost:
                price = round(cost * 3 + 0.49, 0) - 0.10                    # 3× landed, X,90 style — the owner can change it
                guessed = True
            else:
                guessed = False
            if not price:
                return f"To add “{name}” I need at least the selling price (and the cost, so I can watch the margin): e.g. “add product: {name}, costs me 8, sell at 24”."
            return {"store_change": {"kind": "product", "name": name[:80], "price": round(price, 2), "cost": round(cost, 2), "guessed": guessed}}
        return None

    # ---- the store's own numbers, in answers -------------------------------------------------------------
    def _period(self, t):
        low = t.lower()
        day = self.store.data.get("day", 0)
        if re.search(r"\b(today|oggi)\b", low):
            return "today", lambda o: o.get("day") == day
        if re.search(r"\b(this week|settimana|weekly|the week)\b", low):
            return "this week", lambda o: o.get("day", 0) > day - 7
        if re.search(r"\b(this month|mese|monthly)\b", low):
            return "this month", lambda o: o.get("day", 0) > day - 30
        return "so far", lambda o: True

    def store_numbers(self, t):
        st = self.store
        label, keep = self._period(t)
        orders = [o for o in st.data["orders"] if keep(o)]
        paid = [o for o in orders if o["status"] in ("paid", "shipped", "delivered")]
        low = t.lower()
        n = st.numbers()
        day = st.data.get("day", 0)
        if not st.data["orders"]:
            return "No orders yet in the practice store — it hasn't had a practice day. Say “run a practice day” and customers come (simulated), then ask me again."
        units = {}
        for o in paid:
            for l in o["lines"]:
                units[l["name"]] = units.get(l["name"], 0) + l["qty"]
        best = sorted(units.items(), key=lambda x: -x[1])
        rev = sum(o["total"] for o in paid)
        cogs = sum(l["qty"] * l.get("cost", 0) for o in paid for l in o["lines"])
        ship = sum(2.9 + 0.35 * sum(l["qty"] for l in o["lines"]) for o in paid)
        fees = sum(0.029 * o["total"] + 0.30 for o in paid)
        profit = rev - cogs - ship - fees
        visits = sum(v for d, v in st.data["visits"].items() if keep({"day": int(d)}))
        conv = (len(paid) / visits * 100) if visits else 0
        if re.search(r"\b(best[- ]?seller|top (?:product|seller)|più venduto)\b", low):
            if not best:
                return f"Nothing sold {label} yet."
            k, v = best[0]
            p = st.find_product(k)
            return (f"Best seller {label}: {k} — {v} sold" + (f" ({_eur(p['price'])}, {(p['price'] - p.get('cost', 0)) / p['price'] * 100:.0f} % margin, {p['stock']} left)" if p else "") +
                    (("; then " + ", ".join(f"{a} ×{b}" for a, b in best[1:3])) if len(best) > 1 else "") + ".")
        if re.search(r"\b(visitors|visits|visite)\b", low) and not re.search(r"orders|ordini", low):
            return f"Visitors {label}: {visits} — {len(paid)} of them bought ({conv:.1f} % conversion; 1–3 % is normal for a small shop)."
        if re.search(r"\bconversion\b", low):
            return (f"Conversion {label}: {conv:.1f} % ({len(paid)} orders from {visits} visits). Normal for a small shop is 1–3 %; " +
                    ("that's healthy." if conv >= 1.5 else "below 1 % usually means the product page or the shipping cost scares people off — check the price shown before checkout."))
        if re.search(r"\b(profit|money|earn|guadagnato|margin)\b", low) and not re.search(r"\bsummary|riepilogo\b", low):
            return (f"Profit {label}: {_eur(profit)} on {_eur(rev)} of sales from {len(paid)} orders " +
                    f"(goods {_eur(cogs)}, shipping {_eur(ship)}, payment fees {_eur(fees)})" + (f" — {profit / rev * 100:.0f} % net margin." if rev else "."))
        if re.search(r"\b(how many|quanti)\b.*\b(orders|sales|ordini|customers)\b", low):
            return (f"Orders {label}: {len(paid)}" + (f" ({_eur(rev)} in sales, average basket {_eur(rev / len(paid))})" if paid else "") +
                    (f"; {len([o for o in orders if o['status'] == 'refunded'])} refunded" if any(o["status"] == "refunded" for o in orders) else "") + ".")
        # summary
        open_ = [o for o in st.data["orders"] if o["status"] == "paid"]
        lowst = [p for p in st.products() if p["stock"] <= 3]
        lines = [f"Practice store — {label} (day {day}):",
                 f"• {len(paid)} orders, {_eur(rev)} sales, profit {_eur(profit)}" + (f" ({profit / rev * 100:.0f} %)" if rev else ""),
                 f"• {visits} visits → {conv:.1f} % conversion"]
        if best:
            lines.append("• best sellers: " + ", ".join(f"{a} ×{b}" for a, b in best[:3]))
        if open_:
            lines.append(f"• to ship: {len(open_)} order(s) — say “print the shipping labels”")
        if lowst:
            lines.append("• low stock: " + ", ".join(f"{p['name']} ({p['stock']})" for p in lowst) + " — say “what do you propose for the store?”")
        return "\n".join(lines)

    def ship_cost(self, t):
        """'how much is shipping to germany?' — from the store's own shipping rules (the practice store), not a web search."""
        from . import store as _s
        low = t.lower()
        code = next((c for w, c in (("germany", "DE"), ("germania", "DE"), ("france", "FR"), ("francia", "FR"), ("spain", "ES"), ("spagna", "ES"), ("italy", "IT"), ("italia", "IT"),
                                     ("austria", "AT"), ("netherlands", "NL"), ("olanda", "NL"), ("belgium", "BE"), ("portugal", "PT"), ("poland", "PL"), ("uk", "GB"), ("united kingdom", "GB"), ("switzerland", "CH"), ("svizzera", "CH"), ("usa", "US"), ("america", "US"), ("stati uniti", "US")) if re.search(r"\b" + w + r"\b", low)), None)
        rules = "Italy € 3,90 (free over € 39) · Germany/France/Spain € 6,90 · other EU € 8,90 · outside the EU: not offered yet"
        if not code:
            return f"Our shipping prices (practice store): {rules}. Orders ship within 1 business day with GLS from Bergamo."
        cost = self.store.shipping_for(code, 0)
        if cost is None:
            return f"We don't ship to {code} yet — the shop covers the EU only (outside: not offered, UK/Switzerland planned). Full list: {rules}."
        days = {"IT": "2–3 business days", "DE": "4–6 business days", "FR": "4–6 business days", "ES": "4–6 business days"}.get(code, "5–7 business days")
        free = " (free over € 39)" if code == "IT" else ""
        return f"Shipping to {code}: {_eur(cost)}{free}, {days}, GLS with tracking. That's what the customer pays; it costs us about € 6–9 for a small EU parcel, so on a € 12,90 item the margin gets thin — a free-shipping threshold for the EU (~€ 60) helps."

    def sell_out(self, what):
        p = self.store.find_product(what)
        if not p:
            return None
        day = self.store.data.get("day", 0)
        sold = sum(l["qty"] for o in self.store.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and o.get("day", 0) > day - 7 for l in o["lines"] if l["id"] == p["id"])
        if p["stock"] == 0:
            return f"{p['name']} is already sold out (0 left). Say “we received N more {p['name'].split(' (')[0].lower()}” when the goods arrive."
        if not sold:
            return f"{p['name']}: {p['stock']} left and nothing sold in the last 7 practice days, so no sell-out in sight — at 1 a day it would last {p['stock']} days."
        per_day = sold / 7
        days = p["stock"] / per_day
        return (f"{p['name']}: {p['stock']} left, selling {sold} a week ({per_day:.1f} a day) → about {days:.0f} days of stock. " +
                ("Reorder now — supplier lead times are usually 1–3 weeks." if days < 21 else "Fine for now; reorder when it drops below ~3 weeks of sales."))

    def what_if(self, m):
        n = int(m.group("n") or m.group("n2"))
        what = (m.group("what") or m.group("what2") or "").strip()
        per = (m.group("per") or m.group("per2") or "month").lower()
        per_en = {"mese": "month", "settimana": "week", "giorno": "day"}.get(per, per)
        p = self.store.find_product(what) if self.store is not None else None
        price = _num(m.group("price")) if m.group("price") else (p["price"] if p else None)
        cost = _num(m.group("cost")) if m.group("cost") else (p.get("cost", 0) if p else None)
        if price is None:
            return f"Tell me the selling price and the cost (“if I sell {n} {what} a {per_en} at 14.90 with cost 5.60”) and I do the maths."
        ship_cost = 3.25                                                             # what the carrier charges us, average
        fee = price * 0.029 + 0.30
        unit = price - (cost or 0) - fee
        unit_ship = unit - ship_cost
        gross = n * unit
        net = n * unit_ship
        mult = {"month": 12, "week": 52, "day": 365}[per_en]
        return (f"{n} × {p['name'] if p else what} a {per_en} at {_eur(price)} (cost {_eur(cost or 0)}):\n"
                f"• per sale: {_eur(price)} − cost {_eur(cost or 0)} − payment fee {_eur(fee)} = {_eur(unit)}; if you pay the shipping (free-shipping orders) another −{_eur(ship_cost)} → {_eur(unit_ship)}\n"
                f"• per {per_en}: {_eur(gross)} (customer pays shipping) to {_eur(net)} (you pay it) · sales {_eur(n * price)}\n"
                f"• per year at this pace: {_eur(gross * mult)} to {_eur(net * mult)} — before ads, returns, tax and your time.\n"
                f"Rule of thumb: keep 1–2 refunds per 100 orders and ~10–20 % of sales for ads in the plan; ask “tax on {round(gross * mult):.0f} €” for the Italian forfettario maths.")

    # ---- small maths, reminders, notes, guidance -------------------------------------------------------
    def maths(self, m):
        try:
            if m.group("a"):
                a, b = _num(m.group("a")), _num(m.group("b"))
                return f"{a:g} % of {b:g} = {a * b / 100:.2f}".replace(".00", "")
            if m.group("c"):
                c, d = _num(m.group("c")), _num(m.group("d"))
                return f"{c:g} + {d:g} % = {c * (1 + d / 100):.2f} (the {d:g} % is {c * d / 100:.2f})"
            if m.group("e"):
                e, f = _num(m.group("e")), _num(m.group("f"))
                return f"{e:g} − {f:g} % = {e * (1 - f / 100):.2f} (the {f:g} % is {e * f / 100:.2f})"
            expr = m.group("expr").replace(",", ".").replace("x", "*").replace("×", "*").replace("÷", "/").replace(":", "/")
            if not re.fullmatch(r"[\d.\s+\-*/()]+", expr):
                return None
            val = eval(expr, {"__builtins__": {}}, {})                            # digits and operators only (checked above)
            return f"{m.group('expr').strip()} = {val:.2f}".rstrip("0").rstrip(".") if isinstance(val, float) and val != int(val) else f"{m.group('expr').strip()} = {int(val)}"
        except Exception:
            return None

    def remind_at(self, when, what):
        """'remind me tomorrow at 9 to call the supplier' → a dated to-do; the daily check pings it when due."""
        import datetime as dt
        now = dt.datetime.now()
        low = when.lower()
        day = now.date()
        if re.search(r"\b(tomorrow|domani)\b", low):
            day = day + dt.timedelta(days=1)
        wd = {"monday": 0, "lunedì": 0, "tuesday": 1, "martedì": 1, "wednesday": 2, "mercoledì": 2, "thursday": 3, "giovedì": 3, "friday": 4, "venerdì": 4, "saturday": 5, "sabato": 5, "sunday": 6, "domenica": 6}
        for k, v in wd.items():
            if re.search(r"\b" + k + r"\b", low):
                ahead = (v - now.weekday()) % 7 or 7
                day = now.date() + dt.timedelta(days=ahead)
        mi = re.search(r"in (\d+) (hours?|minutes?|days?|ore|minuti|giorni)", low)
        hour, minute = 9, 0
        mt = re.search(r"(?:at|alle|alle ore)\s+(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?", low)
        if mt:
            hour = int(mt.group(1)); minute = int(mt.group(2) or 0)
            if mt.group(3) == "pm" and hour < 12:
                hour += 12
        elif re.search(r"\b(tonight|stasera)\b", low):
            hour = 20
        due = dt.datetime.combine(day, dt.time(hour, minute))
        if mi:
            n, unit = int(mi.group(1)), mi.group(2)
            due = now + (dt.timedelta(hours=n) if unit.startswith(("hour", "ore")) else dt.timedelta(minutes=n) if unit.startswith("min") else dt.timedelta(days=n))
        if due <= now and not mi and not mt and not re.search(r"tomorrow|domani", low):
            due = due + dt.timedelta(days=1)
        what = what.strip(" .")
        n = self.memory.add(f"{what[0].upper() + what[1:]} (⏰ {due:%a %d %b %H:%M})")
        try:
            items = self.memory.todo["items"]
            items[-1]["due"] = due.isoformat(timespec="minutes")
            self.memory._save()
        except Exception:
            pass
        return f"Reminder set for {due:%A %d %B at %H:%M}: {what}. It's #{n} on your to-do list; I'll ping you here when it's time."

    def thank_note(self, t):
        it = bool(re.search(r"\b(italian|italiano|in italiano|scrivi|biglietto)\b", t, re.I)) and not re.search(r"\bin english\b", t, re.I)
        shop = (self.store.data.get("name", "the shop").split(" — ")[0] if self.store is not None else "the shop")
        if it:
            return (f"Biglietto per i pacchi (stampalo su un cartoncino 10×7 cm, firmalo a mano):\n\n"
                    f"Grazie per aver scelto {shop}!\nDietro questo pacco c'è una piccola attività: ogni ordine conta davvero.\n"
                    f"Se qualcosa non va, scrivici prima di tutto — sistemiamo tutto entro 24 ore.\nSe invece sei contento, una recensione o una foto con @{shop.lower().replace(' ', '')} ci aiuta più di qualsiasi pubblicità.\n"
                    f"— <il tuo nome>\n\n(Facoltativo: “-10 % sul prossimo ordine con il codice GRAZIE10” — fa tornare 1 cliente su 10.)")
        return (f"Thank-you card for the parcels (print on a 10×7 cm card, sign it by hand):\n\n"
                f"Thank you for choosing {shop}!\nThere's a small business behind this parcel — every order truly matters.\n"
                f"If anything isn't right, write to us first: we fix it within 24 hours.\nIf you're happy, a review or a photo tagging @{shop.lower().replace(' ', '')} helps us more than any ad.\n"
                f"— <your name>\n\n(Optional: “10 % off your next order with code THANKS10” — brings about 1 in 10 customers back. Say “in Italian” for the Italian version.)")

    def cancel_how(self, t):
        low = t.lower()
        if re.search(r"\b(refund|money back|rimborso)\b", low):
            return ("A customer who wants a refund — the rule first, then the tone:\n"
                    "• Not shipped yet → refund at once, no questions (EU right of withdrawal, and it saves the postage).\n"
                    "• Shipped, within 14 days of delivery → they can return it; refund within 14 days of getting it back (you may charge the return postage only if your returns page says so).\n"
                    "• Faulty/wrong item → refund or replace immediately, photo is enough, no return needed for cheap items.\n"
                    "Tone: one line of sorry, one line of what happens now, one line of when — no arguing. Forward me the message and I draft the reply for your approval.")
        if re.search(r"\b(complain|angry|si lamenta)\b", low):
            return ("An angry customer: answer within the hour if you can, even just “I've seen it, I'm on it — answer by 17:00”. Then: facts (order, tracking, photo), the fix (resend/refund/replace), the date. "
                    "Never argue about who's right in writing; give the fix and move on. Forward me the message and I draft it.")
        return ("A customer who wants to cancel:\n"
                "• Order not shipped → cancel and refund right away; say so in one line with the refund timing (3–5 business days on card).\n"
                "• Already shipped → they can refuse the parcel or return it within 14 days of delivery (EU withdrawal); refund when it's back.\n"
                "• Custom/personalised items → no withdrawal right, but say it kindly and offer a discount code instead.\n"
                "Forward me the customer's message and I draft the exact reply (with the order status from the store) for your approval.")

    # ---- shop sense: things every shop owner asks -------------------------------------------------
    def shop_sense(self, t):
        low = t.lower()
        if self.BAD_REVIEW.search(t) and not self.CUSTOMER.search(t):
            return self.bad_review(t)
        if self.FREE_SHIP.search(t):
            return self.free_shipping()
        if self.COURIER.search(t) and not re.search(r"https?://|\b(compare|research|find|cerca|trova)\b", low):
            return self.couriers(t)
        if self.HASHTAGS.search(t):
            return self.hashtags(t)
        m = self.VIDEO_IDEAS.search(t)
        if m and not re.search(r"https?://|youtu|\b(watch|guarda)\b", low):
            return self.video_ideas(t, m.group("n"))
        return None

    def bad_review(self, t):
        """'a customer left a 1-star review saying the mug broke, what do I do?' → the three moves + a public reply draft."""
        product = None
        if self.store is not None:
            product = self.store.find_product(t)
        prod = product["name"] if product else "the item"
        broke = re.search(r"\b(broke|broken|damaged|cracked|arrived (?:in pieces|broken)|rotto|rotta|danneggiato)\b", t, re.I)
        late = re.search(r"\b(late|never arrived|still waiting|in ritardo|mai arrivato)\b", t, re.I)
        rude = re.search(r"\b(rude|ignored|no (?:answer|reply)|maleducat)", t, re.I)
        cause = "a broken item" if broke else "a late or missing delivery" if late else "bad service" if rude else "the problem"
        fix = ("we replace or refund faulty items at once — no return needed for a broken piece, a photo is enough" if broke else
               "we track the parcel with the courier today and refund or resend if it's lost" if late else
               "we look into what happened and make it right")
        draft = (f"Hi <name>, I'm sorry — {cause} is not what we want for you. We {fix.split(' — ')[0]}. "
                 f"I've written to you privately to sort it out today; please answer with your order number so I can send the replacement/refund right away. — <your name>, {self.store.data.get('name', 'the shop').split(' — ')[0] if self.store is not None else 'the shop'}")
        lesson = ("check the packaging for that product (double-wall box, bubble wrap around the item, nothing rattling) and the courier's damage rate" if broke else
                  "check the delivery promise on the product page against the real times, and send tracking numbers automatically" if late else
                  "answer every message within 24 hours; set a template for the common ones")
        return (f"A bad review about {prod} — three moves, in this order:\n"
                f"1. Fix it privately first (today): write to the customer, {fix}. Ask for a photo and the order number; don't argue about fault.\n"
                f"2. Answer publicly, short and calm, so the next 100 readers see how you handle problems. Draft:\n“{draft}”\n"
                f"3. Learn from it: {lesson}.\n"
                "Never offer money for deleting the review — most platforms ban it and it reads badly. If you forward me the customer's message I draft the private reply for your approval.")

    def free_shipping(self):
        avg, n, cat = None, 0, []
        if self.store is not None:
            try:
                paid = [o for o in self.store.data["orders"] if o["status"] in ("paid", "shipped", "delivered")]
                n = len(paid)
                avg = sum(o["subtotal"] for o in paid) / n if n else None
                cat = [p["price"] for p in self.store.products()]
            except Exception:
                pass
        base = avg if avg and n >= 3 else (sorted(cat)[len(cat) // 2] if cat else 25.0)
        thr = round(base * 1.3 + 0.5) - 0.01                                    # a bit above the average basket, X,99
        thr = max(19.99, min(thr, 99.99))
        why = f"your average order so far is {_eur(avg)} over {n} orders" if avg and n >= 3 else (f"your typical product costs {_eur(base)}" if cat else "a typical small-shop basket is ~€ 25")
        return (f"Free shipping — yes, but as a threshold, not on everything. {why.capitalize()}, so I'd set “free shipping over {_eur(thr)}”: "
                f"shoppers add a second item to reach it (basket size usually rises 15–30 %), and you never pay € 4–7 of postage on a single € 12 item.\n"
                "Rules of thumb: (1) show the shipping cost before checkout and the “€ X to free shipping” bar in the cart; (2) below the threshold charge your real cost, rounded (€ 3,90 / 4,90 in Italy); "
                "(3) 'free' isn't free — either the margin covers it (2.5× cost or more) or the price already includes ~€ 3; (4) EU orders keep a fee (€ 6,90–9,90) or a higher threshold.\n"
                f"Say “set free shipping over {thr:.0f}” and I write it into the shipping page of the practice store.")

    def couriers(self, t):
        """'which courier is cheapest in italy for small parcels?' — public list prices (2026), the way a small shop starts, and when to get a contract."""
        eu = re.search(r"\b(europe|eu|germany|france|spain|abroad|estero|europa|germania|francia|international|internazionale)\b", t, re.I)
        lines = ["Cheapest way to ship small parcels from Italy (public prices, 2026 — check the live quote before you promise a fee):",
                 "• Poste Delivery Web (online, pickup at home included): € 5,65 up to 1 kg, € 5,90 up to 2 kg, € 6,70 up to 3 kg, € 7,30 up to 5 kg; 24–48 h with Express (+€ 1). From the post office counter it starts at € 10,30 — never pay counter prices.",
                 "• Comparators (Packlink, Spedire.com, SpedireSubito…): from € 5,48 up to 2 kg with GLS/BRT/SDA/TNT, pickup or drop-off; good for choosing per parcel, prices change weekly.",
                 "• Lockers/pickup points (InPost, GLS ParcelShop, Poste Punto Poste): usually the cheapest 1–2 kg option and customers like them; ask the price for your size in the app.",
                 "• Direct contract with GLS / BRT / SDA: list price ~€ 15 for 3 kg, but from ~10 parcels a month they give 30–60 % off and a pickup every day — that's when you switch (a national parcel lands at € 4–6).",
                 "• Envelopes ≤ 2 cm (phone case, wraps): Posta Raccomandata/Posta 4 Pro is cheaper than any parcel — ask the exact price at Poste Business."]
        if eu:
            lines.append("• Abroad: Germany from € 14,93 and France from € 17,56 via comparators; Poste Crono Internazionale from ~€ 20 up to 2 kg, 3 working days in the EU. That's why EU orders need a € 6,90–9,90 fee or a higher free-shipping threshold, and why heavy items should stay national at first.")
        lines.append("What decides the price: weight AND size (volumetric weight = L×W×H cm / 5000 or /4000), so use the smallest box; print labels at home; always send the tracking number.")
        lines.append("My advice for the start: Poste Delivery Web or a comparator for the first months (no contract, pay per parcel), weigh every product now so the shipping page is honest, then negotiate a contract once you ship 10+ parcels a month.")
        return "\n".join(lines)

    TAG_FAMILIES = {
        "eco": ["ecofriendly", "sustainableliving", "zerowaste", "plasticfree", "ecosostenibile", "greenliving", "consciousconsumer"],
        "home": ["homedecor", "casa", "interiorinspo", "cozyhome", "homestyle", "arredamento"],
        "kitchen": ["kitchenessentials", "cucina", "foodie", "mealprep", "homecooking"],
        "coffee": ["coffeelover", "coffeetime", "caffè", "espresso", "morningritual"],
        "phone": ["phonecase", "phoneaccessories", "iphonecase", "techaccessories", "cover"],
        "bamboo": ["bamboo", "bambootoothbrush", "plasticfreebathroom", "zerowastebathroom"],
        "candle": ["candles", "candlelover", "homefragrance", "candele", "cozyvibes"],
        "pet": ["dogsofinstagram", "petlovers", "doglife", "catsofinstagram", "petaccessories"],
        "baby": ["babyessentials", "newmom", "momlife", "babyshower", "neonato"],
        "fitness": ["fitnessmotivation", "homeworkout", "gymlife", "healthylifestyle", "allenamento"],
        "beauty": ["skincare", "cleanbeauty", "selfcare", "beautyroutine", "skincareroutine"],
        "fashion": ["ootd", "slowfashion", "outfitinspo", "madeinitaly", "styleinspo"],
        "jewel": ["jewelry", "handmadejewelry", "gioielli", "minimaljewelry", "earrings"],
        "garden": ["gardening", "plantsofinstagram", "urbangarden", "giardino", "plantlover"],
        "gift": ["giftideas", "giftsforher", "giftsforhim", "regali", "regaloperfetto"],
        "desk": ["desksetup", "workfromhome", "homeoffice", "studygram", "deskinspo"],
        "lamp": ["lighting", "lampdesign", "homelighting", "interiordesign"],
        "cork": ["cork", "sughero", "naturalmaterials", "veganleather"],
        "food": ["foodwraps", "mealprep", "lunchbox", "zerowastekitchen"],
    }

    def hashtags(self, t):
        """'what hashtags should I use for eco products?' → 12 tags in three sizes + the rules; built from the words, no browsing."""
        low = t.lower()
        topic = re.search(r"\b(?:for|per|about|su|on)\s+(?:my |our |the |a |an |i |le |gli |il |la )?(?P<x>[a-zà-ú][a-zà-ú0-9 \-']{2,50}?)(?:\s+(?:posts?|videos?|reels?|content|shop|store|brand)\b|\s*[?.!,]|$)", t, re.I)
        topic = (topic.group("x") if topic else "").strip()
        words = [w for w in re.findall(r"[a-zà-ú]{3,}", topic.lower()) if w not in ("the", "and", "our", "for", "with", "products", "product", "shop", "store", "items", "stuff", "things", "posts", "post")]
        fam = []
        for w in words + re.findall(r"[a-zà-ú]{4,}", low):
            for k, v in self.TAG_FAMILIES.items():
                if (k in w or w in k) and v not in fam:
                    fam.append(v)
        italian = bool(re.search(r"\b(ital(?:y|ia|ian)|milano|roma|negozio|per il|prodotti)\b", low))
        def clean(seq):
            out = []
            for x in seq:
                x = re.sub(r"[^a-z0-9à-ú]", "", x.lower())
                if x and x not in out:
                    out.append(x)
            return out
        big = clean(["smallbusiness", "shopsmall", "handmade" if re.search(r"hand|artigian", low) else "onlineshop"])
        medium = []
        for v in fam[:3]:                                                  # family tags: the first family gives 3, the others fill up to 5
            medium += v[:3] if not medium else v[:2]
        medium = [x for x in clean(medium) if x not in big][:5]
        if len(medium) < 3 and words:
            medium += clean([w.rstrip("s") + "life" for w in words[:2]])[:3 - len(medium)]
        niche = []
        for w in words[:2]:
            base = w.rstrip("s")
            niche += [base + "lover", base + "gift", base + "shop"]
        if italian:
            niche += ["madeinitaly", "negozionline", "piccoleimprese"]
        small = [x for x in clean(niche) if x not in big + medium][:4]
        brand = "#<yourshopname>"
        return (f"Hashtags for {topic or 'your posts'} — mix three sizes, 8–10 on Instagram, 3–5 on TikTok, always your own brand tag:\n"
                f"• broad (millions of posts, reach): " + " ".join("#" + x for x in big) + "\n"
                f"• medium (10k–500k, where you can actually rank): " + " ".join("#" + x for x in medium) + "\n"
                f"• niche/buyer intent (your people): " + " ".join("#" + x for x in small) + f" {brand}\n"
                "Rules: put them in the caption (not the first comment), never the same block on every post, no banned/junk tags (#followforfollow #like4like), "
                "check each tag once — if the top posts are nothing like yours, drop it. Every 2 weeks look at which posts reached non-followers (Insights → Reach) and keep the tags from those.")

    def video_ideas(self, t, n=None):
        """'write 3 tiktok video ideas for the cork phone case' → hooks + shots + text on screen + caption, from the product facts."""
        n = {"three": 3, "tre": 3, "four": 4, "five": 5, "cinque": 5, "six": 6, "a few": 3, "some": 3, "un paio di": 2, "qualche": 3}.get((n or "").lower(), None) or (int(n) if n and n.isdigit() else 3)
        n = max(1, min(n, 6))
        product = self.store.find_product(t) if self.store is not None else None
        m = re.search(r"\b(?:for|about|per|su|di)\s+(?:my |our |the |a |an |il |la |le |i )?(?P<x>[a-zà-ú][a-zà-ú0-9 \-']{2,50}?)(?:\s*[?.!,]|$)", t, re.I)
        what = product["name"] if product else ((m.group("x").strip() if m else "the product"))
        facts = (product.get("details") or [])[:4] if product else []
        material = next((f for f in facts if re.search(r"\b(material|made|cork|bamboo|stoneware|cotton|wood|beech|aluminium|glaze|organic)\b", f, re.I)), None)
        detail = next((f for f in facts if f != material), None) or "one concrete detail people don't expect"
        platform = "TikTok" if re.search(r"tiktok", t, re.I) else "Reels" if re.search(r"reel|instagram", t, re.I) else "short video"
        short = what.split(" (")[0]
        ideas = [
            ("The 3-second swap", f"Hook (text on screen, 0–2 s): “Still using the usual one?” — cut to {short} in hand.",
             f"Shots: the ordinary version → yours, extreme close-up of the surface{' (' + material.split(':')[-1].split(';')[0].strip().lower()[:50] + ')' if material else ''}, one real use (15–20 s total).",
             f"Caption: “Small change, every day. {detail[:70]}” + 4 tags."),
            ("What arrives at your door", f"Hook: hands opening the parcel, no talking, natural sound (paper, no plastic).",
             f"Shots: label → box → {short} lifted out → one detail shot; end frame: price and the shipping line from your shipping page.",
             "Caption: “Unboxing, honestly filmed. Ships in 1 business day.” — the calm ASMR kind performs well without ads."),
            ("3 things you didn't know", f"Hook: “3 things about {short} nobody tells you” — count on screen 1-2-3.",
             f"Shots: one 4-second clip per fact — use your real product facts (e.g. {facts[0][:60] if facts else 'where it is made'}; {facts[1][:60] if len(facts) > 1 else 'how long it lasts'}).",
             "Caption: the same 3 facts as bullets; ask “which one surprised you?” to get comments."),
            ("Packing your order", f"Hook: “Packing order #{'51042' if product else '12'} — going to <city>”.",
             "Shots: pick, wrap, seal, label, drop at the courier; 12–18 s, upbeat but not salesy. People trust shops they see working.",
             "Caption: “Every order is packed by hand in <city>. Yours next?”"),
            ("The honest answer", f"Hook: read a real customer question out loud (“Does it survive the dishwasher?” / “Is it really plastic-free?”).",
             f"Shots: you answering in one take + the proof shot ({detail[:60]}).",
             "Caption: the question + the short answer; pin the video as an FAQ."),
            ("Before / after", f"Hook: split screen — the messy/ugly/wasteful before, {short} after.",
             "Shots: 2 s before, 2 s after, 8 s of the result in daily life; add the trending sound quietly under it.",
             "Caption: one line on why you chose this product for the shop."),
        ]
        out = [f"{n} {platform} ideas for {what} — each is 15–25 s, hook in the first 2 seconds, film vertical in daylight:"]
        for i, (title, hook, shots, cap) in enumerate(ideas[:n], 1):
            out.append(f"{i}. {title}\n   {hook}\n   {shots}\n   {cap}")
        out.append("Post 3–4 a week for a month before judging; keep the ones with the best watch time (Analytics → average watch time), not the most likes. Say “write the caption for idea 2” and I'll draft it within the platform's limits for your approval.")
        return "\n".join(out)

    def pricing(self, text):
        m = self.COST.search(text)
        if not m:
            return None
        cost = _num(m.group(1))
        if cost <= 0:
            return None
        ship = 0.0
        ms = re.search(r"(?:shipping|delivery|postage|spedizione)\D{0,20}" + _MONEY, text, re.I)
        if ms:
            ship = _num(ms.group(1))
        landed = cost + ship
        rows = []
        for mult, label in ((2.5, "safe minimum for handmade / dropshipping"), (3.0, "typical"), (4.0, "premium / strong brand")):
            price = round(landed * mult + 0.49, 0) - 0.10          # X,90 style
            fee = price * 0.029 + 0.30
            profit = price - landed - fee
            rows.append(f"• {label}: sell at {_eur(price)} → after the ~2.9 % + € 0,30 payment fee you keep {_eur(profit)} per sale ({profit / price * 100:.0f} % margin)")
        item = re.search(r"\bfor (?:a |an |the )?([a-z][a-z \-]{2,40}?)(?: that| which| costing| cost| at| for|\?|$)", text, re.I)
        name = item.group(1).strip() if item else "it"
        return (f"Pricing {name} at a cost of {_eur(cost)}" + (f" + {_eur(ship)} shipping" if ship else "") + f" ({_eur(landed)} landed):\n" + "\n".join(rows) +
                "\n\nRule of thumb: 2.5–4× the landed cost; below 2× you can't absorb ads, returns and a discount. If competitors sell far below "
                f"{_eur(landed * 2.5)}, the product is the problem, not the price. Want me to check what others charge? Say “compare prices for {name}”.")

    def shipping_ok(self, amount, text):
        low = text.lower()
        it = re.search(r"\b(italy|italia|it)\b", low)
        eu = re.search(r"\b(eu|europe|germany|france|spain|europa|germania|francia|spagna)\b", low)
        if it or not eu:
            verdict = ("that's in the normal range — Italian shops typically charge € 3,90–6,90 for a parcel and go free above € 39–49." if 3 <= amount <= 7
                       else "that's cheap — most Italian shops charge € 3,90–6,90 (you may be subsidising it)." if amount < 3
                       else "that's on the high side — Italian shoppers expect € 3,90–6,90, or free above a threshold (€ 39–49 is common).")
        else:
            verdict = ("that's normal for EU delivery — € 6,90–9,90 is typical for a small parcel to Germany/France/Spain." if 5 <= amount <= 10
                       else "that's cheap for EU delivery — small parcels usually cost the shop € 6–9." if amount < 5
                       else "that's high for the EU — shoppers expect € 6,90–9,90 or free above ~€ 60.")
        return (f"{_eur(amount)} shipping: {verdict}\nWhat matters more than the number: show it before checkout, and offer a free-shipping threshold "
                "a bit above your average order — it lifts the basket size.")

    def start_plan(self, text):
        m = re.search(r"\b(?:sell|selling|vendere)\s+(?:my |our )?([a-z][a-z \-]{2,50}?)(?:\s+online|\s+on\b|\s*[,.?!]|$)", text, re.I)
        what = (m.group(1).strip() if m else "products")
        if what in ("products", "things", "stuff", "online"):
            what = "products"
        todo = [f"Pick 3–5 {what} to start with (not 30) and write one honest sentence per product" if what != "products" else "Pick one niche and 3–5 products to start with (not 30) — say “research product ideas for <niche>”",
                f"Find out what similar {what} sell for — say “compare prices for {what}”",
                f"Work out your prices: cost + shipping × 2.5–4 — say “how much should I charge for {what} that costs me …”",
                "Take clear photos on a plain background (phone is fine, daylight, 3 angles)",
                "Choose where to sell: your own shop (Shopify/WooCommerce/Etsy for handmade) — I can build the website",
                "Write the shipping + returns rules once (EU: 14-day withdrawal, 2-year guarantee) — I draft them",
                "Open the social pages and rehearse a first post with me before going live"]
        head = f"Starting to sell {what} online" if what != "products" else "Starting an online shop"
        return {"todo": todo, "text": f"{head} — here's the order I'd do it in, and I've put it on our to-do list:\n" +
                "\n".join(f"{i + 1}. {s}" for i, s in enumerate(todo)) + "\n\nTell me which step you want me to do first."}

    # ---- helpers -------------------------------------------------------------------------------
    def _customer_text(self, text, m):
        """Pull the customer's words out of 'a customer says the parcel arrived broken, what do I answer?'."""
        inner = m.group("inner").strip(" :,-–—\"“”'")
        quoted = re.search(r"[\"“«](.{8,400}?)[\"”»]", text)
        if quoted:
            return quoted.group(1).strip()
        inner = re.sub(r"^(that|me|us)\s+", "", inner, flags=re.I)
        return inner or text
