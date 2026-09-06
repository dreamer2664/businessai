"""python3 -m agent.selfcheck — verify keys and the phone line without starting the loop."""
import sys
from . import config
from .telegram import Bot, TelegramError

ok = True
if not config.TELEGRAM_BOT_TOKEN:
    print("x TELEGRAM_BOT_TOKEN missing in .secrets/env"); ok = False
else:
    try:
        me = Bot().get_me()
        print(f"v telegram bot @{me.get('username')} reachable")
    except TelegramError as e:
        print("x telegram:", e); ok = False
if not config.TELEGRAM_OWNER_USERNAME and not config.TELEGRAM_OWNER_ID:
    print("x TELEGRAM_OWNER_USERNAME missing (who is allowed to talk to the bot)"); ok = False
else:
    print(f"v owner = @{config.TELEGRAM_OWNER_USERNAME or config.TELEGRAM_OWNER_ID}")
from .brain import Brain
print(("v" if Brain().ready else "-") + " brain:", Brain().describe())
sys.exit(0 if ok else 1)
