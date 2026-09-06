"""Business AI — agent core (milestone 0).

Runs forever: polls Telegram, only talks to the owner, answers messages,
and offers ask()/notify() so later modules (browser, store, memory) can
reach the owner's phone. Everything it does is appended to state/logs/.

Usage:  python3 -m agent.core            # run
        python3 -m agent.core --once     # process pending updates, then exit
"""
import datetime as _dt
import json
import sys
import threading
import time
import traceback

from . import brain, config
from .tasks import Tasks
from .telegram import Bot, TelegramError

VERSION = "0.3 (milestone 2: own browser, read-only research tasks)"

HELP = """I'm your Business AI. I can:
/ask <question> — answer from my business knowledge pack (e-commerce, dropshipping, marketing, business basics)
/research <topic> — search the web in my own browser, read the best pages, report with sources (~30 s)
/compare <product> — look for suppliers of a product and tabulate prices / shipping / MOQ notes (~1 min)
/summarize <url> — open a page or PDF and give me the key points
/exam [n] — sit n questions of the marketing exam bank offline and report my score
/status — what I'm running and how much I know
Any plain question is looked up in the pack too. Browsing is read-only: I never log in, pass CAPTCHAs, buy or post."""


class Agent:
    def __init__(self):
        config.ensure_dirs()
        self.bot = Bot()
        self.me = self.bot.get_me()
        self.owner_id = config.TELEGRAM_OWNER_ID
        self.owner_name = config.TELEGRAM_OWNER_USERNAME
        self.state_file = config.STATE_DIR / "agent.json"
        self.state = self._load_state()
        if not self.owner_id and self.state.get("owner_id"):
            self.owner_id = int(self.state["owner_id"])
        self.pending = {}          # question_id -> {"event": Event, "answer": str|None}
        self.started = time.time()
        self.brain = brain.Brain()
        self.tasks = Tasks(log=self.log, notify=self.notify, brain=self.brain)
        self.busy = None
        self.log("start", version=VERSION, bot=self.me.get("username"))

    # ---- persistence / logging ----------------------------------------
    def _load_state(self):
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return {"offset": 0}

    def _save_state(self):
        self.state_file.write_text(json.dumps(self.state))

    def log(self, kind, **fields):
        rec = {"t": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), "kind": kind}
        rec.update(fields)
        line = config.redact(json.dumps(rec, ensure_ascii=False))
        day = _dt.date.today().isoformat()
        with open(config.LOG_DIR / f"{day}.jsonl", "a") as f:
            f.write(line + "\n")
        print(line, flush=True)

    # ---- owner check ---------------------------------------------------
    def is_owner(self, user):
        if not user:
            return False
        if self.owner_id:
            return user.get("id") == self.owner_id
        uname = (user.get("username") or "").lower()
        if self.owner_name and uname == self.owner_name:
            # first contact: pin the numeric id so a username change can't hijack the bot
            self.owner_id = user["id"]
            self.state["owner_id"] = self.owner_id
            self._save_state()
            self.log("owner_pinned", id=self.owner_id, username=uname)
            return True
        return False

    # ---- outgoing ------------------------------------------------------
    def notify(self, text):
        """Send the owner a message (no answer expected)."""
        if not self.owner_id:
            self.log("notify_skipped", reason="owner unknown (owner must message the bot first)")
            return None
        self.log("notify", text=text)
        return self.bot.send(self.owner_id, text)

    def ask(self, question, options=None, timeout=3600):
        """Ask the owner; block until they tap a button / reply, or timeout.

        options: list of short labels -> shown as tap-buttons. Returns the
        chosen label, the free-text reply, or None on timeout.
        """
        if not self.owner_id:
            self.log("ask_skipped", question=question)
            return None
        qid = str(int(time.time() * 1000))[-9:]
        ev = threading.Event()
        self.pending[qid] = {"event": ev, "answer": None, "question": question}
        rows = None
        if options:
            rows = [[(lab, f"q:{qid}:{i}")] for i, lab in enumerate(options)]
            self.pending[qid]["options"] = list(options)
        msg = self.bot.send(self.owner_id, f"❓ {question}", buttons=rows)
        self.pending[qid]["message_id"] = msg.get("message_id") if msg else None
        self.state.setdefault("open", {})[qid] = {"question": question, "options": options,
                                                 "message_id": self.pending[qid]["message_id"]}
        self._save_state()
        self.log("ask", qid=qid, question=question, options=options)
        ev.wait(timeout)
        ans = self.pending.pop(qid)["answer"]
        if ans is not None:
            self.state.get("open", {}).pop(qid, None)
            self._save_state()
        self.log("ask_result", qid=qid, answer=ans)
        return ans

    def record_answer(self, qid, question, answer, late=False):
        """Append every owner answer to state/answers.jsonl (modules read late answers from here)."""
        rec = {"t": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
               "qid": qid, "question": question, "answer": answer, "late": late}
        with open(config.STATE_DIR / "answers.jsonl", "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---- incoming ------------------------------------------------------
    def handle_update(self, upd):
        if "callback_query" in upd:
            return self.handle_callback(upd["callback_query"])
        msg = upd.get("message")
        if not msg:
            return
        user = msg.get("from") or {}
        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        if not self.is_owner(user):
            self.log("stranger", username=user.get("username"), id=user.get("id"), text=text[:80])
            self.bot.send(chat_id, "Sorry, I only work for my owner.")
            return
        self.log("in", text=text)
        # a pending free-text question takes the next message as its answer
        for qid, p in list(self.pending.items()):
            if "options" not in p and p["answer"] is None:
                p["answer"] = text
                p["event"].set()
                self.bot.send(chat_id, "Got it, thanks.")
                return
        reply = self.respond(text)
        if reply:
            self.log("out", text=reply)
            self.bot.send(chat_id, reply)

    def handle_callback(self, cq):
        data = cq.get("data") or ""
        user = cq.get("from") or {}
        if not self.is_owner(user):
            self.bot.answer_callback(cq["id"], "Not for you.")
            return
        if data.startswith("q:"):
            _, qid, idx = data.split(":", 2)
            p = self.pending.get(qid)
            m = cq.get("message") or {}
            if p and p["answer"] is None:
                try:
                    p["answer"] = p["options"][int(idx)]
                except (ValueError, IndexError, KeyError):
                    p["answer"] = data
                p["event"].set()
                self.record_answer(qid, p["question"], p["answer"])
                self.bot.answer_callback(cq["id"], "Noted")
                if m:
                    self.bot.clear_buttons(m["chat"]["id"], m["message_id"],
                                           new_text=f"❓ {p['question']}\n✅ {p['answer']}")
            elif qid in self.state.get("open", {}):
                # asked by a previous run (before a restart): still accept and record the answer
                o = self.state["open"].pop(qid)
                self._save_state()
                try:
                    ans = (o.get("options") or [])[int(idx)]
                except (ValueError, IndexError):
                    ans = data
                self.record_answer(qid, o["question"], ans, late=True)
                self.log("ask_result_late", qid=qid, answer=ans)
                self.bot.answer_callback(cq["id"], "Noted")
                if m:
                    self.bot.clear_buttons(m["chat"]["id"], m["message_id"],
                                           new_text=f"❓ {o['question']}\n✅ {ans}")
                self.bot.send(self.owner_id, f"Noted: {ans!r} (answer to an earlier question — I had restarted in between).")
            else:
                self.bot.answer_callback(cq["id"], "That question is already closed.")
        else:
            self.bot.answer_callback(cq["id"])

    # ---- the (tiny, for now) conversational policy ---------------------
    def respond(self, text):
        low = text.lower()
        if low in ("/start", "/help", "help"):
            return f"Hi! Business AI {VERSION}\n\n{HELP}"
        if low.startswith("/status") or low == "status":
            return self.status_text()
        if low.startswith("/ask "):
            return self.brain.ask(text[5:].strip())
        if low.startswith("/selftest"):
            threading.Thread(target=self.selftest, daemon=True).start()
            return "Running a self-test: I'll ask you something with buttons."
        for cmd in ("/research", "/compare", "/summarize", "/summarise", "/exam"):
            if low.startswith(cmd):
                if self.busy:
                    return f"I'm still busy with: {self.busy}. Ask me again in a minute."
                arg = text[len(cmd):].strip()
                threading.Thread(target=self.run_task, args=(cmd[1:] + " " + arg,), daemon=True).start()
                return {"/exam": "Sitting the exam now — this takes a few minutes; I'll send the score.",
                        "/compare": "Looking for suppliers in my browser — about a minute."}.get(cmd, "On it — browsing now, report in ~30 seconds.")
        # default: try the knowledge brain, otherwise be honest
        ans = self.brain.ask(text)
        if ans:
            return ans
        if not self.brain.ready:
            return "My knowledge brain isn't installed on this machine yet — run: sh scripts/get_brain.sh"
        return "I couldn't find a confident answer in my business pack for that."

    def run_task(self, command):
        self.busy = command[:60]
        try:
            out = self.tasks.run(command)
        finally:
            self.busy = None
        self.log("out", text=out[:300])
        self.bot.send(self.owner_id, out)

    def status_text(self):
        up = int(time.time() - self.started)
        return (f"Business AI {VERSION}\n"
                f"up {up // 3600}h {up % 3600 // 60}m · brain: {self.brain.describe()}\n"
                f"owner: {'pinned' if self.owner_id else 'not yet seen'} · "
                f"pending questions: {len(self.pending)} · busy: {self.busy or 'no'}")

    def selftest(self):
        a = self.ask("Self-test (the buttons mean nothing, just checking that your tap reaches me): tap one",
                     ["Tap me", "Or me"], timeout=300)
        self.notify(f"Self-test passed: I received your tap ({a}). The phone line works both ways." if a
                    else "Self-test: no tap within 5 minutes.")

    # ---- main loop -----------------------------------------------------
    def run(self, once=False):
        backoff = 2
        while True:
            try:
                updates = self.bot.get_updates(offset=self.state.get("offset", 0) or None, timeout=15)
                backoff = 2
            except TelegramError as e:
                self.log("poll_error", error=str(e))
                if "timed out" not in str(e):
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                continue
            for u in updates:
                self.state["offset"] = u["update_id"] + 1
                self._save_state()
                try:
                    self.handle_update(u)
                except Exception:
                    self.log("handler_error", trace=traceback.format_exc()[-800:])
            if once and not updates:
                return


def main(argv):
    agent = Agent()
    if "--say" in argv:
        agent.notify(" ".join(argv[argv.index("--say") + 1:]) or "hello")
        return
    if "--selftest" in argv:
        threading.Thread(target=agent.selftest, daemon=True).start()
    try:
        agent.run(once="--once" in argv)
    except KeyboardInterrupt:
        agent.log("stop", reason="Ctrl-C")
        print("stopped.")


if __name__ == "__main__":
    main(sys.argv[1:])
