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
`agent/planner.py` runs a small open model locally through llama.cpp (default Qwen2.5-1.5B-Instruct, 940 MB, CPU only,
`sh scripts/get_model.sh`). It is started on first use and stopped after 10 idle minutes, so RAM is only used while thinking.
It never answers from thin air: it gets evidence (knowledge-pack passages, page notes, the agent's own notes) and must say
when the evidence isn't enough. Any OpenAI-compatible endpoint can replace it (`BAI_LLM_URL`, `BAI_LLM_KEY`, `BAI_LLM_MODEL`).

## Low-memory machines
Browser and thinking model together need ~2.5 GB. With less, the agent enters low-memory mode automatically: it closes the browser before thinking and reopens it for the next task (slower, but no stalls). `/status` and `state/logs/llm.log` show why the model isn't running, and `sh scripts/get_model.sh --test` / `--build` fix a prebuilt server that doesn't match the machine.

## Memory
`state/notes.jsonl` (everything researched/summarized, with sources), `state/todo.json` (to-do + learning goals).
`/visit <site> | <question>` (or just "open Amazon and tell me the bestsellers") goes to a site and reports what is really on it — answers are checked word-for-word against the page, and empty/login-only pages (YouTube, TikTok) are reported as such instead of guessed.
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

## Phone line (what the agent can do today)
- Only the owner (Telegram username in `.secrets/env`, pinned to the numeric id at first contact) is served.
- `notify(text)` — one-way message to the phone.
- `ask(question, options)` — sends buttons (or waits for a typed reply) and blocks until answered; used by every
  later module for approvals ("post this?", "order this sample?").
- Every in/out message and decision is logged to `state/logs/<date>.jsonl` with secrets redacted.
