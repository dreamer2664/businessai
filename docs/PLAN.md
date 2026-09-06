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
   self-study when idle (≤6 runs/day), daily report at 20:00. Exam: 27/30 = 90 % (retrieval alone 18/30).
4. Practice store (free test shop) — listings, descriptions, pricing rules;
   every change approved by the owner.
5. Customer messages & social — drafts → approval → automatic for routine
   replies once its score earns it.
6. Real store — owner handles accounts, payments, legal; AI operates with
   approval gates on money and public posts.
7+. Vision (screenshots) and desktop/cursor control for what the browser
   cannot reach.

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
