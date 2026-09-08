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
import re


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
        (r"^\W*(?:show me|let me see|walk me through|spiegami|fammi vedere)\s+(?:the |your |i |la )?(?:maths?|math|calculation|calcolo|conti|numbers behind (?:it|that)|working|workings)\W*$|\bhow did you (?:get|calculate|compute|work out) (?:that|this|it|those numbers?|the number)\b|\bwhere does (?:that|this) (?:number|figure) come from\b", "show_maths"),
        (r"^\W*(?:hmm+,? |well,? |ok,? )?(?:not convinced|i'?m not convinced|not sure about that|i doubt (?:it|that)|i disagree|i don'?t (?:buy|think so|agree)|that doesn'?t (?:sound|seem|feel) right|non sono convint[oa]|non ci credo|mah)\W*$", "not_convinced"),
        (r"\b(?:i'?m|i am|im) (?:tired|sick|fed up|done|exhausted|frustrated|losing (?:hope|faith|motivation)|about to give up)\b|\bnothing (?:sells|is selling|works|is working)\b|\bthis (?:isn'?t|is not|doesn'?t) work(?:ing)?\b|\bi (?:want to|should|might|will) (?:give up|quit|stop|close (?:the )?shop)\b|\bwhat'?s the point\b|\bsono stanc[oa]\b|\bnon vende (?:niente|nulla)\b|\bmollo tutto\b", "discouraged"),
        (r"^\W*(?:be honest(?: with me)?|honestly\??|tell me the truth|straight answer|no sugar ?coating|don'?t sugar ?coat it|sii onest[oa]|dimmi la verità|give it to me straight)\W*$|\bbe honest\b.{0,20}?\b(?:shop|store|business|numbers|me)\b", "be_honest"),
        (r"\bwhat would you do differently\b|\bwhat should (?:i|we) (?:do|have done) differently\b|\bcosa faresti di diverso\b|\bdifferently (?:than|from|to) last (?:week|month)\b", "differently"),
        (r"^\W*(?:please |ok |so |right,? )?(?:stop|don'?t|do not|no more|quit|smetti di|basta)\s+(?:proposing|suggesting|asking (?:me )?(?:about|for)|nagging (?:me )?about|sending(?: me)?|with the|proporre|proporr?mi)\s+(?:the |those |these |any |me )?(?P<what>price|prices|pricing|price changes?|repric\w*|stock|restock\w*|reorders?|reordering|stock changes?|ship\w*|shipping reminders?|order reminders?|proposals?|suggestions?|everything|cambi di prezzo|prezzi|riordini|scorte)\b.{0,30}$", "mute_kind"),
        (r"^\W*(?:ok |please |from now on |you can |you may |go ahead and )?(?:send|answer|reply to|handle|do)\s+(?:the )?(?:routine|simple|easy|standard|normal|tracking|basic)\s+(?:replies|answers|messages|ones|questions|e-?mails|customer (?:replies|messages))\s+(?:yourself|on your own|by yourself|alone|without (?:asking|me)|automatically|directly|da sol[oa])\b|\byou (?:can|may) (?:send|answer) (?:the )?(?:routine|simple|easy) (?:ones|replies|messages) (?:yourself|on your own|without me)\b|\brispondi (?:tu )?(?:da sol[oa]|direttamente) (?:a quelle|alle) (?:semplici|di routine)\b", "auto_routine"),
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

    def reply(self, t):
        low = t.lower().strip()
        if self.JOB_WORDS.search(low):
            return None
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
                out.append(("bad" if not rep else "good", f"{rep} repeat buyer(s) out of {len(emails)} customers" + (" — nothing brings people back yet (no card in the parcel, no e-mail after 3 weeks)" if not rep else ""), "repeat"))
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
        what = (m.groupdict().get("what") or m.groupdict().get("what2") or "").strip(" ?.")
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
        pick = ideas[day % len(ideas)]
        return f"One idea for this week: {pick}\n(Ask again tomorrow and I give you a different one — I rotate through {len(ideas)}.)"

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
