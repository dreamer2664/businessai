# Builder → owner (newest at the bottom)

- 2026-09-08 19:40 (builder): New channel is live. From PowerShell:
  `wsl bash -lc "cd ~/businessai && git pull && python3 scripts/say.py 'your message'"` → leaves me a note.
  `wsl bash -lc "cd ~/businessai && python3 scripts/say.py"` → prints my replies (add `--watch` to keep listening).
  A one-word "go" in the chat wakes me; I read owner/inbox.md first, answer here.
- 2026-09-08 19:40 (builder): About the Telegram log you sent — 5 bugs found, fixes in progress:
  1) your request no longer queues behind self-training (self-training is filler and gets cut at once);
  2) "stop"/"wait"/"basta" act immediately, never go to the brain (no more circuit-breaker lectures);
  3) "stop" also stops self-training and reports what was running;
  4) the plan repeats your sites (Vinted, subito.it) and conditions ("shipping on, not hand-offs") back to you;
  5) a one-word message asks for more words instead of guessing; long requests get "👀 On it" within a second.
- 2026-09-08 19:55 (builder): Fixes from your Telegram log are pushed (e04e4aa). Update the PC: `cd ~/businessai && git pull && sh scripts/service.sh`.
  Then re-try the same thing: send the Kawhi Leonard request → the plan should name Vinted + subito.it and your "shipping on, not hand-offs" condition, and start at once even if it was studying. "stop" answers in words, immediately.
  New test suite: score_stop 11/11; brief 34/34; talk 460/460.
