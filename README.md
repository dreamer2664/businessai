# businessai

An AI that (eventually) runs an online store end to end: product and supplier
research, listings, customer messages, social media — reporting to its owner
and asking questions through Telegram.

**Status: milestone 3 — thinking model, plain language, memory** (marketing exam 90 %, browse tasks 18/19, knowledge pack 52/55). Packs: [docs/PACKS.md](docs/PACKS.md). See [docs/PLAN.md](docs/PLAN.md)
for the roadmap and the rules (score-driven, frugal, owner-in-the-loop, no
CAPTCHA-breaking, official platform connections only).

## Layout
```
agent/      the agent: Telegram line, owner check, ask()/notify(), logs   (Python, no dependencies)
engine/     knowledge brain inherited from kdr-brain: C engine, pack builders, scorers
packs/      knowledge pack sources (milestone 1+)
tests/      score sets — every capability has one
scripts/    install.sh, run.sh, service.sh, push_to_github.sh, upload_release.sh, restore.sh
release/    built artefacts (git-ignored; published as GitHub Release assets)
state/      runtime memory + logs (git-ignored)
.secrets/   keys (git-ignored) — template in .secrets.example
```

## Run it (Linux / WSL, free, nothing to install beyond python3) — Windows step-by-step: [docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md)
```sh
git clone https://github.com/dreamer2664/businessai && cd businessai
sh scripts/install.sh          # creates .secrets/env — put the bot token + your Telegram username in it
sh scripts/run.sh              # foreground; or: sh scripts/service.sh  (starts at boot, auto-restarts)
```
Then message the bot on Telegram: `/start`, `/status`, `/selftest` (asks you a question with buttons).

Knowledge brain (optional, ~65 MB): `sh scripts/get_brain.sh` downloads the engine + models + packs from the release; after that any
question you send (or `/ask …`) is answered from the business pack with its source.

## Thinking model (planner)
`agent/planner.py` runs a small open model locally through llama.cpp (`sh scripts/get_model.sh` picks Qwen2.5-3B-Instruct on machines with ≥ 6 GB RAM, else Qwen2.5-1.5B; CPU only; the
server is our own fully static 16 MB build from the GitHub Release, so it runs on any x86-64 Linux/WSL). It is started on first use and stopped after 10 idle minutes, so RAM is only used while thinking.
It never answers from thin air: it gets evidence (knowledge-pack passages, page notes, the agent's own notes) and must say
when the evidence isn't enough. Any OpenAI-compatible endpoint can replace it (`BAI_LLM_URL`, `BAI_LLM_KEY`, `BAI_LLM_MODEL`).

## Low-memory machines
Browser and thinking model together need ~2.5 GB. With less, the agent enters low-memory mode automatically: it closes the browser before thinking and reopens it for the next task (slower, but no stalls). `/status` and `state/logs/llm.log` show why the model isn't running, and `sh scripts/get_model.sh --test` / `--build` fix a prebuilt server that doesn't match the machine.

## Memory
**Learning loop (bulk-feed → trim → pack).** Everything it reads (research, page summaries, videos, self-study) becomes a note;
when idle it boils new notes down to one-sentence facts (numbers/names kept, hype dropped, duplicates removed) and folds
them into its own knowledge pack `release/packs/learned.kdw`, searched together with the business pack. `/learned` shows the
latest facts and pack size; `/learned rebuild` forces a rebuild. Budget: ~40 KB per 100 facts, capped at 5000 facts.

`state/notes.jsonl` (everything researched/summarized, with sources), `state/todo.json` (to-do + learning goals).
`/visit <site> | <question>` (or just "open Amazon and tell me the bestsellers") goes to a site and reports what is really on it — answers are checked word-for-word against the page, and empty/login-only pages (YouTube, TikTok) are reported as such instead of guessed.
`/watch <video url or topic>` (or "watch a video about facebook ads and tell me what you learned") reads the video's captions — no download, no login — and reports the concrete claims plus whether the speaker is selling something.
`/goal <topic>` gives the agent a standing learning goal: when idle it studies one new angle per session, at most 6 sessions
a day, and sends a daily report at 20:00. That is the only thing it does on its own.

## Browser (eyes & hands)
`agent/browser.py` drives a headless Chromium: every page is turned into numbered text (`[7] button: Add to cart`), actions
refer to the numbers, and every step is logged in plain words. Built-in rules: never passes CAPTCHAs or logins (it stops and
reports), refuses buy/pay/post/submit clicks unless a task is explicitly allowed to act, blocklist for adult/gambling/banking.
Telegram: `/research <topic>`, `/compare <product>`, `/summarize <url>`, `/exam [n]`. Install: `sh scripts/install_browser.sh`.

## Watching it work (live screen)
Three ways, all free and local:
1. **Live page** — the agent serves its own screen at `http://localhost:8765` on the machine it runs on: latest screenshot
   (refreshes every second), a plain-words log of every step, and a toggle to see the numbered text it actually reads.
   No files are written; screenshots are only taken while somebody is watching. Change the port with `BAI_VIEW_PORT`.
2. **Phone** — `/screen` sends one screenshot; `/watch on` sends a photo after every browser step (`/watch off` to stop).
3. **A real window** — set `BAI_HEADED=1` (or just run where a display exists, e.g. WSLg on Windows 11) and the agent's
   Chrome opens visibly, slowed to 250 ms per action so you can follow the cursor. Without a display it falls back to
   invisible mode automatically. The window stays open between tasks and closes itself after 10 idle minutes.
Try it without Telegram: `python3 -m agent.viewer --demo` (runs a few read-only tasks in a loop).

## Customer messages (milestone 5, practice channel)
- `agent/inbox.py` reads `state/inbox.jsonl`, classifies each message (order status, damaged, return, cancel, discount,
  product question, complaint, compliment, spam, press/partnership, other), drafts a reply with the thinking model
  under the store policy (`state/policy.json`; see and change it with `/policy`), then runs hard checks: no numbers
  the customer never gave, no "it has shipped"/tracking claims, no refunds or discounts outside the policy, no time
  promises, no cancellations "done", no product or shipping facts the policy does not contain. A failing draft is
  repaired once, otherwise a safe template is used. Legal, chargeback, injury, personal-data and press messages get a
  holding reply and are handed to the owner; spam gets no reply.
- Every draft goes to the owner's phone with **Approve / Edit / Reject** buttons. Approved or edited text is written to
  `state/outbox.jsonl` — the agent never sends anything by itself. `/stats` shows the approval rate per message type
  and how far each is from the automatic-sending bar (30 decisions, ≥ 90 % approved as written; still off by design).
- Channel "owner": forward any customer message to the bot (or `/customer <text>`) → draft → tap → the final reply comes
  back as copyable text to paste into the shop chat / e-mail / Instagram. Real channels through official APIs come later.
- Edits teach style, not facts: from an edited reply the agent learns the greeting (`Ciao {name}!`), preferred length and
  sign-off (`state/style.json`, visible in `/policy`); the customer-specific words are never reused for another customer.
- `/inbox practice` loads 12 sample messages; `python3 engine/scripts/score_inbox.py` scores 23 messages
  (kind + must/must-not phrases + zero safety flags), currently 22/23.

## Phone line (what the agent can do today)
- Only the owner (Telegram username in `.secrets/env`, pinned to the numeric id at first contact) is served.
- `notify(text)` — one-way message to the phone.
- `ask(question, options)` — sends buttons (or waits for a typed reply) and blocks until answered; used by every
  later module for approvals ("post this?", "order this sample?").
- Every in/out message and decision is logged to `state/logs/<date>.jsonl` with secrets redacted.
