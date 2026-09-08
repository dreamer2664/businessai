#!/bin/sh
# One-shot: update, check everything, open the browser chat with the builder.
# From PowerShell:  wsl bash -lc "cd ~/businessai && sh scripts/talk.sh"
# From Ubuntu:      cd ~/businessai && sh scripts/talk.sh
cd "$(dirname "$0")/.." || exit 1
echo "1/4 updating from GitHub…"
git pull -q 2>&1 | head -3
if [ ! -f .secrets/env ]; then
  echo "❌ .secrets/env is missing — this is the PC folder without the secrets. Ask the builder."; exit 1
fi
if ! grep -q "GITHUB_TOKEN=" .secrets/env; then
  echo "❌ GITHUB_TOKEN is not in .secrets/env — the chat cannot reach GitHub. Ask the builder."; exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 is missing: sudo apt install -y python3"; exit 1
fi
echo "2/4 checking GitHub…"
if ! python3 scripts/say.py >/dev/null 2>&1; then
  echo "❌ Cannot reach GitHub from here (network or token). Output:"; python3 scripts/say.py 2>&1 | tail -3; exit 1
fi
echo "3/4 leaving a first note so the builder knows this side works…"
python3 scripts/say.py "hello from the PC — the browser chat is open" >/dev/null 2>&1 && echo "   ✅ note delivered"
echo "4/4 opening the chat page…"
PORT="${BAI_TALK_PORT:-8787}"
( sleep 2; (command -v wslview >/dev/null 2>&1 && wslview "http://localhost:$PORT") \
  || (command -v powershell.exe >/dev/null 2>&1 && powershell.exe -NoProfile -Command "Start-Process 'http://localhost:$PORT'") \
  || (command -v xdg-open >/dev/null 2>&1 && xdg-open "http://localhost:$PORT") ) >/dev/null 2>&1 &
echo ""
echo "   ➜ If no browser opened, open this yourself:  http://localhost:$PORT"
echo "   Type at the bottom of the page. Leave this window open (Ctrl-C closes the chat)."
echo ""
exec python3 scripts/talk.py
