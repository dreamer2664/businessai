# businessai

An AI that (eventually) runs an online store end to end: product and supplier
research, listings, customer messages, social media — reporting to its owner
and asking questions through Telegram.

**Status: milestone 2 — own browser + read-only research tasks** (browse tasks 18/19, knowledge pack 52/55, marketing exam 60 % offline). Packs: [docs/PACKS.md](docs/PACKS.md). See [docs/PLAN.md](docs/PLAN.md)
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

## Browser (eyes & hands)
`agent/browser.py` drives a headless Chromium: every page is turned into numbered text (`[7] button: Add to cart`), actions
refer to the numbers, and every step is logged in plain words. Built-in rules: never passes CAPTCHAs or logins (it stops and
reports), refuses buy/pay/post/submit clicks unless a task is explicitly allowed to act, blocklist for adult/gambling/banking.
Telegram: `/research <topic>`, `/compare <product>`, `/summarize <url>`, `/exam [n]`. Install: `sh scripts/install_browser.sh`.

## Phone line (what the agent can do today)
- Only the owner (Telegram username in `.secrets/env`, pinned to the numeric id at first contact) is served.
- `notify(text)` — one-way message to the phone.
- `ask(question, options)` — sends buttons (or waits for a typed reply) and blocks until answered; used by every
  later module for approvals ("post this?", "order this sample?").
- Every in/out message and decision is logged to `state/logs/<date>.jsonl` with secrets redacted.
