# Business AI — project plan (v0, 2026-09-06)

Goal: an AI that runs an online (dropshipping) store end to end — researches
products and suppliers, sets up and maintains listings, handles customer
messages and social media, reports to the owner and asks questions via phone.

## Principles (carried over from kdr-brain)
- Score-driven: every capability has a test set; nothing ships that lowers a score.
- Frugal: every knowledge pack and model has a size budget — bulk in, filler out.
- Restorable: GitHub is the source of truth; one script rebuilds everything.
- Owner in the loop: money, public posts and customer-facing messages need
  approval until scores earn autonomy.
- Never defeats CAPTCHAs/logins (those go to the owner's phone); uses official
  platform connections (APIs) where they exist — puppet browsers get store and
  social accounts banned.

## Architecture — three parts
1. Library — knowledge packs (KDRW format + wiki_pack pipeline from kdr-brain):
   e-commerce & dropshipping, marketing & copywriting, platform manuals
   (Shopify / WooCommerce / Etsy / Meta / TikTok), customer service, EU/Italian
   consumer rules. Each pack ≤ ~100 MB, scored with 50 questions.
2. Planner — the "thinking" model. Default: hybrid (local model for knowledge
   and routine + paid online model for hard planning steps), swappable like
   composer.gguf. Fully-local option needs a machine with 8–16 GB RAM.
3. Hands — tools: controlled browser (open tabs, read page as text, click/type
   by element name, screenshot on demand), files/notes, task list & memory,
   Telegram bot (two-way phone line), store platform connection; later:
   vision + desktop/cursor control.

## Milestones (one per session; each has a score set and a size budget)
0. ✅ Home & skeleton — new repo, install script, Telegram line. (runs on the owner's Windows PC via WSL)
1. ✅ Knowledge pack #1 — business.kdw 5.7 MB, 52/55 on tests/business.txt; hard test banks collected in tests/banks/ (to be sat alone once it has a browser).
2. ✅ Eyes & hands v1 — own headless browser (agent/browser.py: tabs, numbered page text, click/type,
   screenshots, CAPTCHA/login walls detected and never passed, buy/pay/post clicks refused); read-only tasks
   /research /compare /summarize (tests/browse.txt 18/19); offline exam solver (agent/mcq.py) 57–60 % on the
   440-question marketing bank, 87 % on the half it is confident about.
   + Live screen (agent/viewer.py): local web page with screenshot + plain-words step log, /screen & /watch on Telegram,
   visible Chrome window where a display exists (BAI_HEADED).
3. ✅ Memory & a thinking model — local llama.cpp + Qwen2.5-1.5B (agent/planner.py, starts/stops itself, ~1.3 GB RAM
   only while thinking); plain-language understanding (ask / research / summarize / compare / chat); answers written in
   its own words from evidence with sources; agent/memory.py: notes (state/notes.jsonl), to-do, learning goals with
   self-study when idle (≤6 runs/day), daily report at 20:00. Exam: 27/30 = 90 % (retrieval alone 18/30). Warm-up ladder (visit/find/refuse/watch/ask) 14/14.
   Video 'watching' = captions → summary (agent/video.py). Static llama-server on the Release; 3B model on ≥ 6 GB RAM.
   Bulk-feed → trim → pack (agent/learn.py): notes are digested into one-sentence facts (quality gate, de-dup), folded
   into release/packs/learned.kdw (~40 KB / 100 facts, cap 5000) which the brain searches alongside business.kdw.
4. ✅ Social posts (practice) — agent/social.py: /post <platform> <topic> drafts a post within the platform's caps,
   owner taps Approve / Edit / Redo / Reject; nothing is ever published by itself (no channel connected yet).
5. ✅ (practice channel) Customer messages — agent/inbox.py: every message is classified (11 kinds), answered with a
   draft that obeys the store policy (state/policy.json, edit with /policy), checked by hard rules (no invented
   numbers, no status/tracking claims, no discounts, no promises, defer product/shipping facts the policy does not
   contain, escalate legal/chargeback/injury/data/press), and sent to the owner's phone with Approve / Edit / Reject.
   Approved or edited text goes to state/outbox.jsonl — nothing is ever sent by itself. Score: tests/inbox.txt 22/23.
   Channel "owner": forwarded/pasted customer messages → draft → tap → copyable final text. Edits teach greeting, length
   and sign-off (style.json), never the facts of another customer; /stats tracks approval per type.
   Still to do later: real channels through official APIs (shop e-mail, Instagram/Facebook messaging) and automatic
   sending of a message type only after the owner's approval rate for that type stays ≥ 90 % over 30 replies.
6. ✅ Eyes — agent/eyes.py: a small vision model (LFM2-VL-450M, 310 MB, downloaded once with /eyes install; same
   llama-server, ~550 MB RAM only while looking) answers plain questions about any screenshot; OCR (tesseract, three
   views: normal, white-on-colour buttons, borderless) gives every word its pixel position, menu items split into
   separate targets. /look, photos sent to the bot, thin pages seen through the eyes. Score: tests/eyes.txt 16/16.
7. ✅ Desktop hands — agent/desktop.py: its own virtual screen (Xvfb) or the real one, screenshot → OCR → click on words
   (xdotool), type, keys, scroll; the same danger guard as the browser (money/publish/sign-in clicks need the owner's
   tap), before/after comparison after every click, passwords never typed. Installed by scripts/install_desktop.sh.
8. ✅ Operator — agent/operator.py, command /do <goal>: the see → think → act → check loop that works a screen by itself.
   Browser mode (page elements, exact and fast) and desktop mode (pixels + OCR, any window). Question goals are read
   first (answers only from the screen, figures checked against it), action goals are verified by what newly appeared
   (a "buy" needs an order confirmation, not just "added to cart"); rule-based first moves for search/open goals;
   never repeats a failed click; at most 2 questions to the owner, 12 steps, 15 minutes per goal; refuses login,
   payment and password goals up front; stops at captcha/login walls. Score: tests/operator.txt 10/10 (browser);
   desktop live test 4/4 (price, add to cart with approval, cart count, second product's price).
9. ✅ Bigger tasks on the operator — multi-page goals (`/do <url1> <url2> … | question`: the same fact question per page,
   figures copied exactly incl. price tiers, cheapest/lowest/fastest/… ranked in code, other comparisons summarised and
   checked against the findings), form filling for approval (`fill in the form: name = …, email = …` — typed, never sent),
   cookie banners closed before every look (page + consent iframes; reject preferred), wrong-click recovery (back when a page
   is off-goal; follows the most goal-related link when the thinker names something that is not on the page), rule-based
   first moves (add to cart / buy now / search) so simple goals take 4–17 s. Score: tests/operator.txt 15/15 in 321 s;
   live banners: theguardian.com ("Do not sell or share…"), wired.com ("Close"). A live-site score set is still to do
   (sites change; kept for milestone 10 when the real channels arrive).
10. Real channels through official APIs (shop e-mail, Instagram/Facebook messaging) behind the same approval gate.
11. Practice store (free test shop) — listings, descriptions, pricing rules; every change approved by the owner.
   (moved to the very end at the owner's request, 2026-09-06)
12. Real store — owner handles accounts, payments, legal; AI operates with approval gates on money and public posts.

## Defaults chosen (override anytime)
- Engine: hybrid (local + paid model for hard steps), swappable.
- Autonomy: automatic for research and drafts; ask for money, public posts,
  customer messages.
- Store platform: decided at milestone 4 (a Shopify development store is free
  for practice; WooCommerce is free software on own hosting).

## Needed from the owner before session 0
- New GitHub repo name + token (same setup as kdr-brain).
- A Telegram account (for the bot).
- Where it lives 24/7: spare PC (ideally ≥ 8 GB RAM) or a small rented server
  (~€5–15/month). The sandbox used for development is wiped between sessions.
- Monthly budget for the paid thinking model (€0 = fully local: slower, bigger
  machine needed).

## What moves over from kdr-brain
- C engine (brain.c, wiki.c, chat.c, main.c), web chat UI, scoring scripts
  (score.py / eval_*.py), pack builders (pack.py, wiki_pack.py), CI/release
  scripts (push_to_github.sh, upload_release.sh, restore.sh).
- Not the Kingdom facts (data/passages.json, tests/kingdom.txt).
