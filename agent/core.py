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
from .learn import Learner
from .inbox import Inbox
from .social import Social
from .telegram import Bot, TelegramError

VERSION = "0.7 (milestone 5: customer replies + social posts, self-repairing thinking model)"

HELP = """Just talk to me. I work out whether you're asking a question, want something looked up on the web, want a page summarized, or want suppliers compared.
Examples: "what is a good margin for dropshipping" · "find out how ePacket works" · "look for suppliers of bamboo toothbrushes" · paste a link.

Commands (optional):
/research <topic> · /compare <product> · /summarize <url> · /visit <site> | <question> · /watch <video url or topic> · /exam [n]
/todo — my to-do list · /todo add <text> · /todo done <n>
/goal <topic> — give me a standing learning goal; I study it on my own when idle (max 6 sessions a day) and keep notes
/goals · /goal drop <n> · /notes [topic] — my notes · /learned — facts I've folded into my own knowledge pack · /report — today's summary
Forward me any customer message (or write /customer <their text>) → I draft the answer, you tap Approve / Edit / Reject, and I hand you the final text to paste back. Nothing is ever sent by itself.
/inbox — customer messages waiting; /inbox practice loads 12 sample messages so you can see how I'd answer them
/post <platform> <what about> — I draft a social post (instagram, facebook, tiktok, x, linkedin, pinterest), you approve/edit, then copy it — I never publish by myself
/policy — the store rules every reply obeys (/policy set <field> <text>) · /stats — how often you approve my drafts
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
        self.learner = Learner(planner=self.planner, memory=self.memory, log=self.log)
        self.inbox = Inbox(planner=self.planner, brain=self.brain, memory=self.memory, log=self.log)
        self.social = Social(planner=self.planner, inbox=self.inbox, memory=self.memory, log=self.log)
        self.posts = {}             # post id -> draft dict awaiting the owner's tap
        self.editing_post = None    # post id whose text the owner is typing
        self.drafts = {}            # message id -> draft dict awaiting the owner's tap
        self.editing = None         # message id whose reply the owner is typing
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
        fwd = msg.get("forward_origin") or msg.get("forward_from") or msg.get("forward_sender_name") or msg.get("forward_date")
        if not text:
            text = (msg.get("caption") or "").strip()
        self.log("in", text=text)
        if (fwd or re.match(r"^/customer\b", text, re.I)) and not self.editing:
            body = re.sub(r"^/customer\b[:\s]*", "", text, flags=re.I).strip()
            if not body:
                self.bot.send(chat_id, "Paste the customer's message after /customer, or forward it to me.")
                return
            self.bot.send(chat_id, f"Got it — drafting a reply for {self._forward_name(msg)}. You'll get it with Approve / Edit / Reject buttons.")
            self.inbox.add("owner", self._forward_name(msg), body)
            threading.Thread(target=self.process_inbox, daemon=True).start()
            return
        if self.editing_post and not text.startswith("/"):
            pid, self.editing_post = self.editing_post, None
            d = self.posts.pop(pid, None) or {}
            self.social.decide(pid, "edited", d, text)
            self.bot.send(chat_id, f"Saved your version of the {d.get('platform', '')} post.\n\n📋 Long-press to copy and publish it yourself:\n\n{text}")
            self.log("post_edited", id=pid)
            return
        if self.editing and not text.startswith("/"):
            mid, self.editing = self.editing, None
            d = self.drafts.pop(mid, None) or {}
            dec = self.inbox.decide(mid, "edited", text, kind=d.get("kind"), draft=d.get("text"))
            learned = f" I noticed you sign as “{dec['signoff_learned']}” — I'll end every reply that way from now on (change it with /policy set sign_off …)." if dec.get("signoff_learned") else ""
            self.bot.send(chat_id, "Saved your version. I learn your style from edits (greeting, length, how you sign) — never the details, those stay with this customer." + learned)
            self.log("inbox_edited", id=mid)
            self.deliver(mid, text)
            return
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

    @staticmethod
    def _forward_name(msg):
        o = msg.get("forward_origin") or {}
        u = o.get("sender_user") or msg.get("forward_from") or {}
        name = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x) or o.get("sender_user_name") or \
               msg.get("forward_sender_name") or (o.get("chat") or {}).get("title") or "a customer"
        return name

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
        elif data.startswith("p:"):
            _, action, pid = data.split(":", 2)
            d = self.posts.get(pid)
            m = cq.get("message") or {}
            if not d:
                self.bot.answer_callback(cq["id"], "Already handled.")
                return
            if action == "ok":
                self.posts.pop(pid, None)
                self.social.decide(pid, "approved", d, d["text"])
                self.bot.answer_callback(cq["id"], "Approved")
                if m:
                    self.bot.clear_buttons(m["chat"]["id"], m["message_id"], new_text=(m.get("text") or "")[:3800] + "\n\n✅ approved")
                self.bot.send(self.owner_id, f"📋 {d['platform']} post — long-press to copy and publish it yourself (I can't post for you yet):\n\n{d['text']}")
            elif action == "edit":
                self.editing_post = pid
                self.bot.answer_callback(cq["id"], "Type your version")
                self.bot.send(self.owner_id, "Type the post text you want (your next message is taken as the post). /cancel to keep the draft waiting.")
            elif action == "redo":
                self.posts.pop(pid, None)
                self.social.decide(pid, "rejected", d, "")
                self.bot.answer_callback(cq["id"], "Trying again")
                if m:
                    self.bot.clear_buttons(m["chat"]["id"], m["message_id"])
                threading.Thread(target=self.draft_post, args=(d["platform"], d["topic"]), daemon=True).start()
            elif action == "no":
                self.posts.pop(pid, None)
                self.social.decide(pid, "rejected", d, "")
                self.bot.answer_callback(cq["id"], "Dropped")
                if m:
                    self.bot.clear_buttons(m["chat"]["id"], m["message_id"], new_text=(m.get("text") or "")[:3800] + "\n\n❌ dropped — nothing published")
            self.log("post_decision", id=pid, action=action)
        elif data.startswith("r:"):
            _, action, mid = data.split(":", 2)
            d = self.drafts.get(mid)
            m = cq.get("message") or {}
            if not d:
                self.bot.answer_callback(cq["id"], "Already handled.")
                return
            if action == "ok":
                self.drafts.pop(mid, None)
                self.inbox.decide(mid, "approved", d["text"], kind=d["kind"], draft=d["text"])
                self.bot.answer_callback(cq["id"], "Approved")
                if m:
                    self.bot.clear_buttons(m["chat"]["id"], m["message_id"], new_text=(m.get("text") or "")[:3800] + "\n\n✅ approved")
                self.deliver(mid, d["text"])
            elif action == "edit":
                self.editing = mid
                self.bot.answer_callback(cq["id"], "Type your version")
                self.bot.send(self.owner_id, f"Type the reply you want to send for message {mid} (your next message is taken as the reply).")
            elif action == "no":
                self.drafts.pop(mid, None)
                self.inbox.decide(mid, "rejected", "", kind=d["kind"], draft=d["text"])
                self.bot.answer_callback(cq["id"], "Rejected")
                if m:
                    self.bot.clear_buttons(m["chat"]["id"], m["message_id"], new_text=(m.get("text") or "")[:3800] + "\n\n❌ rejected — nothing sent")
            self.log("inbox_decision", id=mid, action=action)
        else:
            self.bot.answer_callback(cq["id"])

    # ---- social posts -----------------------------------------------------
    def draft_post(self, platform, topic):
        if self.busy:
            self.notify(f"I'm busy ({self.busy}) — I'll draft the {platform} post right after.")
            while self.busy:
                time.sleep(3)
        self.busy = f"drafting a {platform} post"
        try:
            d = self.social.draft(platform, topic)
            pid = str(int(time.time() * 1000) % 10 ** 8)
            self.posts[pid] = d
            flags = ("\n⚠️ " + "; ".join(d["checks"])) if d["checks"] else ""
            note = f"\nℹ️ {d['note']}" if d.get("note") else ""
            body = f"📣 {platform} post · {d['chars']} characters\nabout: {topic[:120]}\n\n— my draft —\n{d['text']}{flags}{note}"
            ok_label = "⚠️ Approve anyway" if d["checks"] else "✅ Approve"
            self.bot.send(self.owner_id, body, buttons=[[(ok_label, f"p:ok:{pid}"), ("✏️ Edit", f"p:edit:{pid}")],
                                                        [("🔁 Try again", f"p:redo:{pid}"), ("❌ Drop", f"p:no:{pid}")]])
            self.log("post_draft", id=pid, platform=platform, flags=d["checks"])
        except Exception as e:
            self.log("post_error", error=str(e)[:200])
            self.notify(f"I couldn't draft that post: {str(e)[:120]}")
        finally:
            self.busy = None

    # ---- customer messages ---------------------------------------------
    def deliver(self, mid, final_text):
        """Hand an approved reply to its channel. practice: log only; owner (pasted/forwarded): give back copyable text."""
        rec = self.inbox.get(mid) or {}
        ch = rec.get("channel", "practice")
        if ch == "owner":
            self.bot.send(self.owner_id, f"📋 Reply for {rec.get('from', 'the customer')} — long-press to copy, then paste it where they wrote you:\n\n{final_text}")
        self.log("inbox_delivered", id=mid, channel=ch)

    def process_inbox(self):
        """Draft a reply for every new message and put each in front of the owner with buttons."""
        if self.busy:
            return
        self.busy = "drafting customer replies"
        try:
            for rec in self.inbox.items("new"):
                if rec["id"] in self.drafts:
                    continue
                d = self.inbox.draft(rec)
                if d["kind"] == "spam_or_scam":
                    self.inbox.decide(rec["id"], "rejected", "", note="spam", kind=d["kind"])
                    self.notify(f"🗑 Spam from {rec['from']} — no reply: “{rec['text'][:120]}”")
                    continue
                self.drafts[rec["id"]] = d
                head = f"📨 {rec['from']} ({rec['channel']}) · {d['kind'].replace('_', ' ')} · {d['urgency']}" + (" · ⚠️ ESCALATION" if d.get("escalate") else "")
                flags = ("\n⚠️ " + "; ".join(d["checks"])) if d["checks"] else ""
                note = f"\nℹ️ {d['note']}" if d.get("note") else ""
                body = f"{head}\n\n“{rec['text'][:600]}”\n\n— my draft —\n{d['text']}{flags}{note}"
                ok_label = "⚠️ Approve anyway" if d["checks"] else "✅ Approve"
                self.bot.send(self.owner_id, body, buttons=[[(ok_label, f"r:ok:{rec['id']}"), ("✏️ Edit", f"r:edit:{rec['id']}"), ("❌ Reject", f"r:no:{rec['id']}")]])
                self.log("inbox_draft", id=rec["id"], mtype=d["kind"], flags=d["checks"])
        except Exception as e:
            self.log("inbox_error", error=str(e)[:200])
        finally:
            self.busy = None

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
        if low.startswith("/post"):
            arg = text[5:].strip()
            if not arg:
                return "Tell me what the post is about: /post instagram our new bamboo toothbrush set (platforms: instagram, facebook, tiktok, x, linkedin, pinterest)."
            plat, topic = self.social.parse(arg)
            if not topic:
                return f"What should the {plat} post be about?"
            threading.Thread(target=self.draft_post, args=(plat, topic), daemon=True).start()
            return f"Drafting a {plat} post about “{topic}” — you'll get it with Approve / Edit / Reject buttons. Nothing gets published by itself."
        if low.startswith("/inbox"):
            arg = low[6:].strip()
            if arg.startswith("practice"):
                n = self.inbox.load_practice()
                threading.Thread(target=self.process_inbox, daemon=True).start()
                return f"Loaded {n} practice messages. I'll draft a reply for each and send it to you with Approve / Edit / Reject buttons — nothing is sent anywhere, this is a dry run."
            new = self.inbox.items("new")
            if not new:
                return "Inbox: nothing waiting. (/inbox practice loads sample messages.)"
            threading.Thread(target=self.process_inbox, daemon=True).start()
            return f"{len(new)} message(s) waiting — drafting replies now."
        if low.startswith("/policy"):
            arg = text[7:].strip()
            m = re.match(r"set\s+(\w+)\s+(.+)", arg, re.S | re.I)
            if m:
                return self.inbox.set_policy(m.group(1).lower(), m.group(2).strip())
            fields = "\n".join(f"• {k}: {v or '(empty)'}" for k, v in self.inbox.policy.items() if k != "sign_off")
            fields += f"\n• sign_off: {self.inbox.policy['sign_off'].replace(chr(10), ' / ')}"
            st = self.inbox.style_text()
            tips = "\n".join(f"  {k}: {v}" for k, v in self.inbox.POLICY_HELP.items())
            return f"Store policy (every customer reply obeys this):\n{fields}" + (f"\n• style {st}" if st else "") + f"\n\nChange one: /policy set <field> <text>\n{tips}"
        if low.startswith("/stats"):
            return self.inbox.stats_text()
        if low.startswith("/cancel"):
            had = self.editing or self.editing_post
            self.editing = self.editing_post = None
            return "Okay, edit cancelled — the draft is still waiting with its buttons." if had else "Nothing to cancel."
        if low.startswith("/learned"):
            if "rebuild" in low:
                threading.Thread(target=lambda: self.notify(self.learner.build(force=True)), daemon=True).start()
                return "Rebuilding my learned pack — I'll tell you when it's done."
            rec = self.learner.recent(8)
            return self.learner.status() + ("\n\nLatest facts:\n" + "\n".join(f"• {f['text']}" for f in rec) if rec else "")
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
            if rep:
                rep += "\n" + self.inbox.status()
            self.report_sent = today
            if rep:
                self.notify(rep)
        if self.learner.pending() and self.planner.installed():
            threading.Thread(target=self.run_digest, daemon=True).start()
            return
        goal = self.memory.next_goal()
        if goal and 8 <= hour < 23 and self.owner_id:
            threading.Thread(target=self.run_study, args=(goal,), daemon=True).start()

    def run_digest(self):
        """Trim: boil new notes down to facts; when enough new facts, fold them into learned.kdw."""
        self.busy = "digesting my notes into facts"
        try:
            from .learn import MIN_NEW_FOR_BUILD
            self.learner.digest(max_notes=3)
            if self.learner.new_since_build >= MIN_NEW_FOR_BUILD:
                self.busy = "rebuilding my learned knowledge pack"
                msg = self.learner.build()
                if msg.startswith("learned.kdw"):
                    self.notify("🧠 " + msg)
        except Exception as e:
            self.log("digest_error", error=str(e)[:200])
        finally:
            self.busy = None

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
                f"{self.learner.status()}\n"
                f"{self.inbox.status()}\n{self.social.status()}\n"
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
