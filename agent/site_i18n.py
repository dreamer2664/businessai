"""Languages for the website builder. English is the base; Italian is complete (chrome, template copy, every kind's
services). A site can be built in one language or in several — extra languages live in a subfolder (it/index.html)
with a language switch in the menu. Adding a language = adding one dict here."""

UI = {
    "en": {
        "nav": [("index.html", "Home"), ("about.html", "About"), ("services.html", "Services"), ("gallery.html", "Gallery"), ("contact.html", "Contact")],
        "what_we_do": "What we do", "why": "Why {name}", "find_us": "Find us", "address": "Address", "phone": "Phone", "hours": "Opening hours", "city": "City",
        "map": "Map", "open_map": "Open in OpenStreetMap", "about": "About {name}", "people_say": "What people say",
        "sample_reviews": "Sample testimonials — replace with real reviews.", "services": "Services", "gallery": "Gallery",
        "gallery_lead": "A first look. Real photos go here — drop them into the gallery folder and replace these placeholders.",
        "gallery_items": ["The place", "Our team", "Details", "At work", "Happy customers", "Around us"],
        "contact": "Contact", "send_msg": "Send us a message", "your_name": "Your name", "your_email": "Your e-mail", "how_help": "How can we help?",
        "send": "Send", "thanks": "Thanks — we will reply soon", "form_demo": "This form is a demo (no server). Connect it to Formspree, Netlify Forms or your e-mail when the site goes live.",
        "privacy": "Privacy", "privacy_text": "{name} only uses the information you send through the contact form to answer you. No tracking cookies are set by this website. To have your data removed, write to us at the address on the contact page.",
        "reach": "The quickest way to reach {name} is by phone{phone} or simply by coming in{hours}. For anything that can wait, use the form below and we reply within one working day.",
        "reach_phone": " at {phone}", "reach_hours": " during opening hours ({hours})",
        "tagline_city": "{Kind} in {city} — done with care, every day", "tagline": "{name} — {kind}",
        "about_text": "{name} is a {kind} in {city}{country}. We keep things simple: good work, honest prices and a friendly welcome. Whether you are a regular or just passing by, you will find the same attention every time.",
        "story_since": "{name} has been part of {city} {since} — a {kind} built on the same care today as on day one.",
        "story_others": "What sets us apart: {others}.", "and": " and ", "neighbourhood": "the neighbourhood",
        "why_local": "Local and independent — {name} is run by people who live here", "why_prices": "Clear prices, no surprises", "why_reach": "Easy to reach: {where}", "centre": "in the centre",
        "review1": "Exactly what a {kind} should be — friendly and reliable.", "review1_who": "A regular customer", "review2": "Quick, kind and well priced. Recommended.", "review2_who": "Visitor from out of town",
        "meta": "{name} — {kind} in {city}. {s1}, {s2} and more.", "meta_facts": "{name} — {kind} in {city}: {facts}.", "cuisine": " The kitchen focuses on {cuisine}.",
        "lang_name": "English", "since_word": "since",
    },
    "it": {
        "nav": [("index.html", "Home"), ("about.html", "Chi siamo"), ("services.html", "Servizi"), ("gallery.html", "Galleria"), ("contact.html", "Contatti")],
        "what_we_do": "Cosa facciamo", "why": "Perché {name}", "find_us": "Dove siamo", "address": "Indirizzo", "phone": "Telefono", "hours": "Orari di apertura", "city": "Città",
        "map": "Mappa", "open_map": "Apri in OpenStreetMap", "about": "Chi è {name}", "people_say": "Cosa dicono di noi",
        "sample_reviews": "Recensioni di esempio — sostituiscile con quelle vere.", "services": "Servizi", "gallery": "Galleria",
        "gallery_lead": "Un primo sguardo. Qui vanno le foto vere — mettile nella cartella gallery al posto di questi segnaposto.",
        "gallery_items": ["Il locale", "Il nostro team", "Dettagli", "Al lavoro", "Clienti felici", "Qui intorno"],
        "contact": "Contatti", "send_msg": "Scrivici", "your_name": "Il tuo nome", "your_email": "La tua e-mail", "how_help": "Come possiamo aiutarti?",
        "send": "Invia", "thanks": "Grazie — ti rispondiamo presto", "form_demo": "Questo modulo è dimostrativo (nessun server). Collegalo a Formspree, Netlify Forms o alla tua e-mail quando il sito va online.",
        "privacy": "Privacy", "privacy_text": "{name} usa le informazioni inviate tramite il modulo di contatto solo per risponderti. Questo sito non imposta cookie di tracciamento. Per far cancellare i tuoi dati scrivici all'indirizzo nella pagina contatti.",
        "reach": "Il modo più rapido per raggiungere {name} è il telefono{phone} o semplicemente passare a trovarci{hours}. Per tutto ciò che può aspettare, usa il modulo qui sotto: rispondiamo entro un giorno lavorativo.",
        "reach_phone": " al {phone}", "reach_hours": " negli orari di apertura ({hours})",
        "tagline_city": "{Kind} a {city} — con cura, ogni giorno", "tagline": "{name} — {kind}",
        "about_text": "{name} è un {kind} a {city}{country}. Facciamo le cose semplici: buon lavoro, prezzi onesti e un'accoglienza cordiale. Che tu sia un cliente abituale o di passaggio, troverai sempre la stessa attenzione.",
        "story_since": "{name} fa parte di {city} {since}: un {kind} costruito con la stessa cura di oggi fin dal primo giorno.",
        "story_others": "Cosa ci distingue: {others}.", "and": " e ", "neighbourhood": "del quartiere",
        "why_local": "Locale e indipendente: {name} è gestito da persone che vivono qui", "why_prices": "Prezzi chiari, nessuna sorpresa", "why_reach": "Facile da raggiungere: {where}", "centre": "in centro",
        "review1": "Esattamente ciò che un {kind} dovrebbe essere: cordiale e affidabile.", "review1_who": "Un cliente abituale", "review2": "Veloci, gentili e con prezzi giusti. Consigliato.", "review2_who": "Visitatore di passaggio",
        "meta": "{name} — {kind} a {city}. {s1}, {s2} e altro.", "meta_facts": "{name} — {kind} a {city}: {facts}.", "cuisine": " La cucina punta su {cuisine}.",
        "lang_name": "Italiano", "since_word": "dal",
    },
}

# business kinds: name, call to action, services (title, one sentence) — Italian
KIND_IT = {
    "restaurant": ("ristorante", "Prenota un tavolo", [("Pranzo e cena", "Aperti a pranzo e a cena con un menù corto che cambia con la stagione."), ("Da asporto", "Tutto il menù può essere preparato da portare a casa: chiama prima e lo trovi pronto."),
                                                       ("Eventi privati", "Compleanni, cene di lavoro e feste di famiglia: la sala si può riservare per i gruppi."), ("Menù di stagione", "Cuciniamo con ciò che è buono adesso, così il menù segue le stagioni.")]),
    "cafe": ("caffetteria", "Vieni a trovarci", [("Caffè di qualità", "Chicchi di piccole torrefazioni, macinati al momento: espresso, filtro e tutto il resto."), ("Colazione e brunch", "Dal primo caffè con la brioche a un lento brunch del fine settimana."),
                                                  ("Torte fatte in casa", "Torte e biscotti sfornati qui ogni mattina: chiedi cosa è appena uscito dal forno."), ("Posti per lavorare", "Buon Wi-Fi, prese ovunque e nessuno che ti mette fretta.")]),
    "bakery": ("panificio", "Ordina per il ritiro", [("Pane fresco ogni giorno", "Pagnotte, panini e focaccia sfornati prima dell'alba, con lievitazione lenta e senza additivi."), ("Dolci e torte", "Cornetti, crostate e torte per il caffè del mattino o la tavola della domenica."),
                                                      ("Torte su ordinazione", "Torte di compleanno e di nozze su misura: dicci l'occasione e il numero di ospiti."), ("Forniture per bar", "Consegne quotidiane di pane e dolci a bar e ristoranti della zona.")]),
    "hair salon": ("parrucchiere", "Prenota un appuntamento", [("Taglio e piega", "Un taglio adatto al tuo viso e alle tue mattine, con una piega che puoi rifare a casa."), ("Colore e schiariture", "Colore naturale, balayage e schiariture con prodotti delicati."),
                                                                ("Trattamenti", "Trattamenti riparatori e idratanti per capelli provati da sole, calore o decolorazione."), ("Sposa ed eventi", "Prima una prova, poi un'acconciatura serena il giorno stesso.")]),
    "gym": ("palestra", "Inizia la prova gratuita", [("Sala pesi", "Pesi liberi, macchine e cardio, con orari lunghi per allenarti quando vuoi."), ("Corsi di gruppo", "Classi piccole con un coach che sa come ti chiami: forza, mobilità e HIIT."),
                                                     ("Personal training", "Sedute individuali costruite sul tuo obiettivo, con un piano da seguire tra una visita e l'altra."), ("Consigli alimentari", "Consigli semplici e realistici per mangiare in linea con l'allenamento.")]),
    "dentist": ("studio dentistico", "Prenota una visita", [("Controlli e igiene", "Visite regolari che tengono piccoli i piccoli problemi: delicati, accurati e puntuali."), ("Sbiancamento", "Sbiancamento sicuro in studio con risultati visibili lo stesso giorno."),
                                                            ("Ortodonzia", "Apparecchi e allineatori trasparenti per bambini e adulti, con piano e prezzo chiari fin dall'inizio."), ("Urgenze", "Dolore improvviso o dente rotto? Chiama e, quando possiamo, ti troviamo posto in giornata.")]),
    "pharmacy": ("farmacia", "Chiamaci", [("Ricette", "Ricette evase in fretta, con consigli chiari su come assumere ciò che ti viene dato."), ("Consigli di salute", "Un farmacista con cui parlare dei piccoli disturbi prima di decidere se andare dal medico."),
                                          ("Cosmetica e infanzia", "Cura della pelle, protezione solare e tutto per i neonati, da marchi di cui ci fidiamo."), ("Consegna a domicilio", "Farmaci consegnati a casa in zona: chiedi al banco o chiama.")]),
    "hotel": ("hotel", "Verifica la disponibilità", [("Camere e suite", "Camere tranquille e confortevoli, con buoni letti e tende oscuranti."), ("Colazione inclusa", "Una vera colazione con pane locale, frutta e caffè fresco, inclusa in ogni soggiorno."),
                                                     ("Wi-Fi gratuito", "Wi-Fi veloce in ogni camera e nelle aree comuni, senza costi aggiuntivi."), ("Check-out posticipato", "Vuoi dormire di più? Chiedilo il giorno prima e, quando possiamo, lo organizziamo.")]),
    "florist": ("fioraio", "Ordina i fiori", [("Bouquet e composizioni", "Fiori di stagione composti per l'occasione, dal mazzolino al pezzo importante."), ("Matrimoni ed eventi", "Fiori per la cerimonia, i tavoli e la sposa, pianificati insieme a te."),
                                              ("Piante e vasi", "Piante da interno, erbe aromatiche e vasi, con consigli onesti su cosa sopravviverà sul tuo davanzale."), ("Consegna in giornata", "Ordina entro mezzogiorno per la consegna in città lo stesso giorno.")]),
    "bookshop": ("libreria", "Vieni in libreria", [("Libri nuovi e usati", "Novità accanto a buoni libri di seconda mano, a prezzi giusti."), ("Angolo bambini", "Un angolo accogliente con albi illustrati e un tappeto: i bambini possono sedersi e leggere."),
                                                   ("Incontri con gli autori", "Letture e firmacopie con autori locali e di passaggio, quasi sempre gratuiti."), ("Ordini in 48 ore", "Qualsiasi libro in catalogo ordinato per te e pronto da ritirare entro due giorni.")]),
    "bike shop": ("negozio di biciclette", "Prenota una riparazione", [("Bici ed e-bike", "Bici da città, e-bike e bici per bambini, regolate su di te prima di partire."), ("Riparazioni e tagliandi", "Forature, freni, cambi e tagliandi completi: molte riparazioni mentre aspetti o entro il giorno dopo."),
                                                                        ("Accessori", "Lucchetti, luci, caschi, borse e tutto ciò che serve per pedalare ogni giorno."), ("Noleggio", "Bici a ore o a giornata per esplorare la città e i percorsi intorno.")]),
    "shop": ("negozio", "Vieni a trovarci", [("Prodotti selezionati", "Una selezione piccola e curata: sappiamo da dove viene ogni cosa."), ("Confezione regalo", "Confezione regalo gratuita su richiesta, per ogni occasione."),
                                             ("Ritiro in negozio", "Ordina per telefono o messaggio e ritira in negozio quando ti è comodo."), ("Carta fedeltà", "I clienti abituali accumulano punti a ogni acquisto e ottengono uno sconto a carta completa.")]),
    "plumber": ("idraulico", "Chiama ora", [("Interventi urgenti", "Tubo rotto o niente acqua calda? Rispondiamo al telefono e arriviamo in fretta."), ("Manutenzione caldaie", "Manutenzione annuale e riparazioni che tengono la caldaia sicura ed efficiente."),
                                            ("Bagni", "Da un rubinetto nuovo a un bagno completo, con ordine e nei tempi."), ("Ricerca perdite", "Troviamo la perdita prima che trovi il tuo soffitto, con il minimo disturbo.")]),
    "lawyer": ("studio legale", "Richiedi una consulenza", [("Diritto di famiglia", "Separazioni, affidamenti e successioni gestiti con cura e spiegazioni semplici."), ("Contratti", "Contratti redatti e revisionati perché tu sappia esattamente cosa firmi."),
                                                            ("Immobiliare", "Acquisti, locazioni e controversie: consigli pratici a ogni passo."), ("Primo colloquio", "Un primo incontro per capire la tua situazione e spiegarti opzioni e costi.")]),
    "veterinary": ("ambulatorio veterinario", "Prenota una visita", [("Controlli e vaccini", "Visite di routine e vaccinazioni che mantengono il tuo animale in salute anno dopo anno."), ("Chirurgia", "Operazioni di routine e urgenti nella nostra sala operatoria, con cure attente dopo l'intervento."),
                                                                      ("Cure dentali", "Pulizia e cura di denti e gengive per cani, gatti e piccoli animali."), ("Linea d'emergenza", "Un numero per le emergenze fuori orario: chiama e ti diciamo cosa fare.")]),
}

LANG_WORDS = {"italian": "it", "italiano": "it", "in italiano": "it", "english": "en", "inglese": "en", "in inglese": "en"}


def kind_name(kind, lang):
    if lang == "it" and kind in KIND_IT:
        return KIND_IT[kind][0]
    return kind


def services_for(kind, lang):
    """[(title, text)] in the language, for the template kinds; None when we have no translation."""
    if lang == "it" and kind in KIND_IT:
        return KIND_IT[kind][2]
    return None


def cta_for(kind, lang, default):
    if lang == "it" and kind in KIND_IT:
        return KIND_IT[kind][1]
    return default


def generic_service_text(title, name, kind, lang):
    """One honest sentence in the language for a service we have no template for."""
    if lang != "it":
        return None
    t = title.strip().rstrip(".")
    low = t.lower()
    T = t[0].upper() + t[1:]
    if "grat" in low or "prova" in low:
        return f"{T}: vieni a provare {name} senza impegno, dicci solo quando vorresti venire."
    if any(w in low for w in ("corso", "lezione", "classe", "sessione", "laboratorio")):
        return f"{T} da {name}: gruppi piccoli, tutti i livelli — chiedici gli orari attuali."
    if any(w in low for w in ("prezz", "pacchett", "tariff", "listino")):
        return f"{T} chiari e senza sorprese: chiedi e ti mandiamo il listino completo."
    if any(w in low for w in ("buono", "regalo", "voucher")):
        return f"{T} per amici e famiglia: qualsiasi importo, validi un anno."
    if any(w in low for w in ("orari", "apertura")):
        return "I nostri orari sono in fondo a ogni pagina; scrivici se ti serve un orario diverso."
    if any(w in low for w in ("contatt", "prenot", "appuntament")):
        return f"Scrivi o chiama {name}: rispondiamo entro un giorno lavorativo."
    return f"{T}: una delle cose che {name} fa come {kind_name(kind, 'it')} — chiedici come funziona e quanto costa."
