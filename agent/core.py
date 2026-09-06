"""Business AI — agent core (milestone 0).

Runs forever: polls Telegram, only talks to the owner, answers messages,
and offers ask()/notify() so later modules (browser, store, memory) can
reach the owner's phone. Everything it does is appended to state/logs/.

Usage:  python3 -m agent.core            # run
        python3 -m agent.core --once     # process pending updates, then exit
"""
import datetime as _dt
import json
import re
import sys
import threading
import time
import traceback

from . import brain, config
from .tasks import Tasks
from .viewer import Viewer
from .planner import Planner
from .memory import Memory
from .telegram import Bot, TelegramError

VERSION = "0.5 (milestone 3: thinking model, plain-language, memory)"

HELP = """Just talk to me. I work out whether you're asking a question, want something looked up on the web, want a page summarized, or want suppliers compared.
Examples: "what is a good margin for dropshipping" · "find out how ePacket works" · "look for suppliers of bamboo toothbrushes" · paste a link.

Commands (optional):
/research <topic> · /compare <product> · /summarize <url> · /visit <site> | <question> · /watch <video url or topic> · /exam [n]
/todo — my to-do list · /todo add <text> · /todo done <n>
/goal <topic> — give me a standing learning goal; I study it on my own when idle (max 6 sessions a day) and keep notes
/goals · /goal drop <n> · /notes [topic] — what I've learned · /report — today's summary
/screen · /watch on|off — see my browser · /status · /selftest
Browsing is read-only: I never log in, pass CAPTCHAs, buy or post. Money, public posts and customer messages will always need your OK."""


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
        self.viewer = Viewer(on_step=self._on_step).start()
        self.watch = False
        self.planner = Planner(log=self.log)
        self.memory = Memory()
        self.tasks = Tasks(log=self.log, notify=self.notify, brain=self.brain, viewer=self.viewer,
                           planner=self.planner, memory=self.memory)
        self.busy = None
        self.last_idle_check = time.time()
        self.report_sent = ""
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
        if hasattr(self, "viewer"):
            self.viewer.note(kind, fields)
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

    # ---- live screen ---------------------------------------------------
    def _on_step(self, action, shot):
        """Browser step → photo to the owner's phone when /watch is on."""
        if self.watch and shot and self.owner_id:
            try:
                self.bot.send_photo(self.owner_id, shot, caption=action[:200])
            except Exception as e:
                self.log("watch_error", error=str(e)[:120])

    def screen(self):
        try:
            res = self.tasks.screenshot()
        except Exception as e:
            return f"Couldn't take a screenshot: {str(e)[:120]}"
        if not res:
            return "My browser is closed right now (it opens when a task starts and closes 10 minutes after the last one)."
        shot, title, url = res
        self.bot.send_photo(self.owner_id, shot, caption=f"{title}\n{url}"[:200])
        return None

    # ---- the (tiny, for now) conversational policy ---------------------
    def respond(self, text):
        low = text.lower()
        if low in ("/start", "/help", "help"):
            return f"Hi! Business AI {VERSION}\n\n{HELP}"
        if low.startswith("/status") or low == "status":
            return self.status_text()
        if low.startswith("/ask "):
            return self.brain.ask(text[5:].strip())
        if low.startswith("/screen"):
            return self.screen()
        if low.startswith("/watch"):
            arg = low[6:].strip()
            self.watch = (arg != "off") if arg else not self.watch
            self.viewer.force = self.watch
            return ("Watching on: I'll send a photo after every browser step until you say /watch off."
                    if self.watch else "Watching off. /screen still gives you a single screenshot any time.")
        if low.startswith("/selftest"):
            threading.Thread(target=self.selftest, daemon=True).start()
            return "Running a self-test: I'll ask you something with buttons."
        for cmd in ("/research", "/compare", "/summarize", "/summarise", "/visit", "/watch", "/exam"):
            if low.startswith(cmd):
                return self.start_task(cmd[1:].replace("summarise", "summarize"), text[len(cmd):].strip())
        if low.startswith("/todo"):
            arg = text[5:].strip()
            if arg.lower().startswith("add "):
                return f"Added #{self.memory.add(arg[4:].strip())}.\n" + self.memory.list_text()
            if arg.lower().startswith("done "):
                x = self.memory.done(arg[5:].strip())
                return (f"Done: {x['text']}" if x else "No open item with that number.") + "\n" + self.memory.list_text()
            return self.memory.list_text()
        if low.startswith("/goals"):
            return self.memory.list_text()
        if low.startswith("/goal"):
            arg = text[5:].strip()
            if arg.lower().startswith("drop "):
                return "Dropped." if self.memory.drop_goal(arg[5:].strip().lstrip("g")) else "No goal with that number."
            if not arg:
                return self.memory.list_text()
            i = self.memory.add_goal(arg)
            return f"Learning goal g{i} set: {arg}\nI'll study it when idle (up to 6 sessions a day, 3 pages each) and keep notes — /notes {arg.split()[0]} to see them, /goal drop {i} to stop."
        if low.startswith("/notes"):
            q = text[6:].strip()
            ns = self.memory.notes(q or None, limit=5)
            if not ns:
                return "No notes yet" + (f" about '{q}'." if q else ". They appear when I research, summarize or study something.")
            return "\n\n".join(f"{n['t'][:16]} · {n['kind']} · {n['topic']}\n{n['text'][:500]}" for n in ns)
        if low.startswith("/report"):
            return self.memory.daily_report() or "Nothing to report yet today."
        # ---- plain language: work out what the owner wants --------------------
        it = self.planner.intent(text) if self.planner.installed() else {"kind": "ask", "topic": text}
        self.log("intent", intent=it["kind"], topic=it["topic"])
        if self.planner.last_error and not getattr(self, "warned_llm", False):
            self.warned_llm = True
            self.notify(f"⚠️ My thinking model isn't running: {self.planner.last_error}\nI'll keep working in simple mode (worse understanding and answers) until it is fixed. /status shows the state.")
        if it["kind"] == "chat":
            try:
                return self.planner.reply(text) if self.planner.installed() else "Hi! Ask me anything about the store."
            except Exception:
                return "Hi! Ask me anything about the store."
        if it["kind"] in ("research", "compare", "summarize", "visit", "watch"):
            return self.start_task(it["kind"], it["topic"])
        # a question: answer from what I know; if I know nothing useful, go and look
        ans = self.tasks.ask(text)
        if ans and not re.search(r"\b(does not|doesn't|do not|don't) (contain|answer|mention|provide|include)\b|no evidence|not enough (evidence|information)", ans, re.I):
            return ans
        if not self.brain.ready and not self.planner.installed():
            return "My knowledge brain and thinking model aren't installed here yet — run: sh scripts/get_brain.sh && sh scripts/get_model.sh"
        return self.start_task("research", it["topic"], prefix="I don't know that well enough from my own knowledge — ")

    def start_task(self, kind, arg, prefix=""):
        if self.busy:
            return f"I'm still busy with: {self.busy}. Ask me again in a minute."
        if not arg:
            return f"What should I {kind}?"
        threading.Thread(target=self.run_task, args=(f"{kind} {arg}",), daemon=True).start()
        msg = {"exam": "sitting the exam now — this takes a few minutes; I'll send the score.",
               "visit": f"going to {arg.split('|')[0].strip()} now — a moment.",
               "watch": "watching it now (I read the captions) — a minute or two.",
               "compare": f"looking for suppliers of {arg} in my browser — about a minute.",
               "summarize": "reading it now — a moment.",
               "research": f"looking into '{arg}' — report in about a minute."}[kind]
        return (prefix + msg) if prefix else msg[0].upper() + msg[1:]

    def run_task(self, command):
        self.busy = command[:60]
        try:
            out = self.tasks.run(command)
        finally:
            self.busy = None
        self.log("out", text=out[:300])
        self.bot.send(self.owner_id, out)

    def idle_work(self):
        """Between messages: one self-study session when a learning goal is waiting, and the daily report at 20:00."""
        now = time.time()
        if self.busy or now - self.last_idle_check < 60:
            return
        self.last_idle_check = now
        hour = _dt.datetime.now().hour
        today = _dt.date.today().isoformat()
        if hour >= 20 and self.report_sent != today and self.owner_id:
            rep = self.memory.daily_report()
            self.report_sent = today
            if rep:
                self.notify(rep)
        goal = self.memory.next_goal()
        if goal and 8 <= hour < 23 and self.owner_id:
            threading.Thread(target=self.run_study, args=(goal,), daemon=True).start()

    def run_study(self, goal):
        self.busy = f"studying g{goal['id']}: {goal['topic'][:40]}"
        try:
            angle, out = self.tasks.study(goal)
            self.log("study", goal=goal["id"], angle=angle, chars=len(out))
            self.notify(f"📚 Self-study on '{goal['topic']}' — angle: {angle}\n\n{out[:1500]}")
        except Exception as e:
            self.log("study_error", error=str(e)[:200])
        finally:
            self.busy = None

    def status_text(self):
        up = int(time.time() - self.started)
        return (f"Business AI {VERSION}\n"
                f"up {up // 3600}h {up % 3600 // 60}m · brain: {self.brain.describe()}\n"
                f"{self.planner.describe()} · notes: {len(self.memory.notes(limit=100000))} · {self.memory.list_text().splitlines()[-1]}\n"
                f"owner: {'pinned' if self.owner_id else 'not yet seen'} · "
                f"pending questions: {len(self.pending)} · busy: {self.busy or 'no'}\n"
                f"live screen: {self.viewer.address()} (on the machine I run on) · watch: {'on' if self.watch else 'off'}")

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
            self.tasks.tick()
            self.planner.tick()
            self.idle_work()
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
