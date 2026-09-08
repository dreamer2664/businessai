"""Business AI — agent core (milestone 0).

Runs forever: polls Telegram, only talks to the owner, answers messages,
and offers ask()/notify() so later modules (browser, store, memory) can
reach the owner's phone. Everything it does is appended to state/logs/.

Usage:  python3 -m agent.core            # run
        python3 -m agent.core --once     # process pending updates, then exit
"""
import datetime as _dt
import html
import json
import os
import re
import sys
import threading
import time
import traceback
from pathlib import Path

from . import brain, config
from .tasks import Tasks
from .viewer import Viewer
from .planner import Planner
from .memory import Memory
from .learn import Learner
from .inbox import Inbox
from .shopfacts import ShopFacts
from . import store as practice_store
from .channels import Channels, REAL as REAL_CHANNELS
from .social import Social
from .eyes import Eyes
from .desktop import Desktop
from .operator import Operator
from .telegram import Bot, TelegramError
from .store import money
from .google import Google, GoogleError
from . import library
from .brief import Brief
from .pace import Pace
from .sellers import SellerCheck
from .accounts import Accounts
from .study import Study
from .sitebuilder import SiteBuilder, KINDS as SITE_KINDS
from .rehearsal import Rehearsal
from .mind import Mind


def money_list(orders):
    return ", ".join(f"#{o['n']} {money(o['total'])}" for o in orders[:5]) + ("…" if len(orders) > 5 else "")

VERSION = "1.5 (milestone 11: practice store — /store open; I run a whole shop here with fake payments and simulated customers, and every change waits for your tap)"

HELP = """Just talk to me. I work out whether you're asking a question, want something looked up on the web, want a page summarized, or want suppliers compared.
Examples: "what is a good margin for dropshipping" · "find out how ePacket works" · "look for suppliers of bamboo toothbrushes" · paste a link.

Commands (optional):
/research <topic> · /compare <product> · /summarize <url> · /visit <site> | <question> · /watch <video url or topic> · /exam [n]
/todo — my to-do list · /todo add <text> · /todo done <n>
/goal <topic> — give me a standing learning goal; I study it on my own when idle (max 6 sessions a day) and keep notes
/goals · /goal drop <n> · /notes [topic] — my notes · /learned — facts I've folded into my own knowledge pack · /report — today's summary
Forward me any customer message (or write /customer <their text>) → I draft the answer, you tap Approve / Edit / Reject, and I hand you the final text to paste back. Nothing is ever sent by itself.
/inbox — customer messages waiting; /inbox practice loads 12 sample messages so you can see how I'd answer them
/channels — your real channels (shop e-mail, Facebook/Instagram messages): what is connected, /channels check tests the connection, /channels now looks for new messages right away. New messages get a drafted reply; nothing is sent until you tap Approve & send
/post <platform> <what about> — I draft a social post (instagram, facebook, tiktok, x, linkedin, pinterest), you approve/edit, then copy it — I never publish by myself
/policy — the store rules every reply obeys (/policy set <field> <text>) · /stats — how often you approve my drafts
/store — my practice shop on this machine (fake payments, simulated customers): /store open · /store day — a practice day passes · /store review — I propose ship / reorder / reprice, you tap Apply · /store numbers · /store admin
/shop <address> — I read your own shop's help, shipping, returns and contact pages and answer customers with their exact words (re-read by itself every week) · /shop — what I know from them · /shop forget
/eyes — my vision status (/eyes install once, 310 MB) · /look [question] — I look at my own screen and tell you what I see · send me any screenshot or photo and I'll read it
/do <goal> — I work a web page by myself, step by step (look → decide → click/type → check), e.g. /do https://en.wikipedia.org/wiki/Etsy | in which year was Etsy founded? · /do <page1> <page2> | which is cheaper? (compare several pages) · /do <page> | fill in the form: name = …, email = …, message = … (I type, you send) · /do desktop <goal> — same on my own screen. Any click that costs money, publishes, signs in or deletes waits for your tap.
/google — my own Google account (Drive library + reading my own mailbox for sign-up codes): /google connect · /google test · /google ls
"rehearse posting about <topic>" — a dry run on my own practice network: log in, publish with photo, learn the limits, answer comments (nothing public) · /rehearse map — what I learned about each interface
"build a website for <a place>" — I write the copy, build the pages, check them in my browser and send you the files · "start auto training on website building" — I practise on random real places from the map (watch it live) · "stop training"
while I work: "status" / "what are you doing" · "why" · "hurry up" · "stop" · a change ("only Italy") · a new request (queued) — no need to wait
/lessons — what I learned from my last jobs (I reflect after every one)
/ideas — business ideas I jotted from short videos (/ideas <topic> = go watch some now) · /study [topic] — find and keep a good PDF in my library
/accounts — the site accounts I created with my own e-mail (I sign up when a task needs it and tell you in one line; never money sites)
/library — the documents I've written (seller checks, research, comparisons); they also land in my Drive folder
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
        self.eyes = Eyes(log=self.log, planner=self.planner)
        self.pace = Pace(log=self.log)
        self.tasks = Tasks(log=self.log, notify=self.notify, brain=self.brain, viewer=self.viewer, eyes=self.eyes,
                           planner=self.planner, memory=self.memory, pace=self.pace)
        self.learner = Learner(planner=self.planner, memory=self.memory, log=self.log)
        self.shopfacts = ShopFacts(tasks=self.tasks, log=self.log)
        self.store = practice_store.Store(log=self.log)          # the practice shop (milestone 11); served only when /store open
        self.inbox = Inbox(planner=self.planner, brain=self.brain, memory=self.memory, log=self.log, shopfacts=self.shopfacts, store=self.store)
        self.social = Social(planner=self.planner, inbox=self.inbox, memory=self.memory, log=self.log)
        self.channels = Channels(inbox=self.inbox, log=self.log)
        self.google = Google(log=self.log)
        self.google_reconnect_told = 0
        self.briefer = Brief(planner=self.planner, log=self.log)
        self.accounts = Accounts(google=self.google, log=self.log, notify=self.notify, ask=self.ask)
        self.accounts.eyes = self.eyes
        self.sellers = SellerCheck(self.tasks, planner=self.planner, log=self.log, viewer=self.viewer, pace=self.pace, eyes=self.eyes)
        self.sellers.accounts = self.accounts
        self.tasks.accounts = self.accounts                  # CAPTCHA solvers + one-tap owner fallback for essential pages
        self.study = Study(self.tasks, planner=self.planner, google=self.google, memory=self.memory, log=self.log, notify=self.notify, viewer=self.viewer)
        self.quiet_sessions = 0
        self.last_quiet = 0
        self.sites = SiteBuilder(planner=self.planner, tasks=self.tasks, google=self.google, log=self.log, viewer=self.viewer, eyes=self.eyes)
        self.site_training = False          # "start auto training on website building" → loop until "stop"
        self.sites_built = 0
        self.mind = Mind(planner=self.planner, log=self.log, pace=self.pace, viewer=self.viewer)
        self.viewer.listener = self.mind.on_event
        self.stop_flag = False
        self.rehearsal = Rehearsal(self.tasks, accounts=self.accounts, social=self.social, inbox=self.inbox, log=self.log, viewer=self.viewer, eyes=self.eyes)
        self.stage = None                   # the rehearsal network (tests/social/server.py) once started
        self.rehearsals_done = 0
        self.active_brief = None            # the plan being worked on (shown in /status)
        self.last_brief = None              # last plan proposed, for "go" / "change step 2 …"
        self.desktop = Desktop(log=self.log, eyes=self.eyes)
        self.operator = Operator(self.planner, eyes=self.eyes, tasks=self.tasks, desktop=self.desktop, log=self.log,
                                 notify=self.notify, ask_owner=lambda q, opts: self.ask(q, opts, timeout=900), viewer=self.viewer)
        self.operator.accounts = self.accounts
        self.posts = {}             # post id -> draft dict awaiting the owner's tap
        self.editing_post = None    # post id whose text the owner is typing
        self.drafts = {}            # message id -> draft dict awaiting the owner's tap
        self.editing = None         # message id whose reply the owner is typing
        self.busy = None
        self.last_idle_check = time.time()
        self.report_sent = ""
        self.log("start", version=VERSION, bot=self.me.get("username"))
        if self.brain.ready and self.brain.missing_packs():
            threading.Thread(target=self._fetch_packs, daemon=True).start()

    def _fetch_packs(self):
        got = self.brain.fetch_missing(log=self.log)
        if got and self.owner_id:
            self.notify("📚 New knowledge pack" + ("s" if len(got) > 1 else "") + f" installed: {', '.join(got)} — {self.brain.describe()}")

    # ---- persistence / logging ----------------------------------------
    def _load_state(self):
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return {"offset": 0}

    def _save_state(self):
        self.state_file.write_text(json.dumps(self.state))

    def log(self, *args, **fields):
        """log("event", field=…). A field literally named 'kind' is kept as 'kind_' so no caller can crash the logger."""
        kind = args[0] if args else fields.pop("event", "event")
        if "kind" in fields:
            fields["kind_"] = fields.pop("kind")
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
        photo = msg.get("photo") or ([msg["document"]] if (msg.get("document") or {}).get("mime_type", "").startswith("image/") else [])
        if photo and not fwd:
            self.log("in", text=f"[photo] {text}")
            threading.Thread(target=self.look_at_photo, args=(chat_id, photo[-1]["file_id"], text), daemon=True).start()
            return
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
            self.deliver(mid, text)                 # for a real channel this sends the owner's own text
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
        elif data.startswith("b:"):
            act = data[2:]
            m0 = cq.get("message") or {}
            chat_id, mid = (m0.get("chat") or {}).get("id", self.owner_id), m0.get("message_id")
            self.bot.answer_callback(cq["id"], "Ok")
            b, self.last_brief = self.last_brief, None
            if not b:
                self.bot.clear_buttons(chat_id, mid, new_text="(that plan is gone — just ask again)")
            elif act == "go":
                self.bot.clear_buttons(chat_id, mid, new_text="▶ Going.")
                r = self.execute(b)
                if r:
                    self.bot.send(chat_id, r)
            elif act == "edit":
                self.last_brief = b
                self.bot.clear_buttons(chat_id, mid, new_text="✏️ Tell me what to change (e.g. 'only Italian sellers', 'max 30 €', 'skip social media', 'take your time') — or 'go'.")
            else:
                self.bot.clear_buttons(chat_id, mid, new_text="✖ Cancelled.")
            return
        elif data.startswith("s:"):
            _, action, pid = data.split(":", 2)
            m = cq.get("message") or {}
            prop = self.store.proposal(pid)
            if not prop or prop["status"] != "open":
                self.bot.answer_callback(cq["id"], "Already handled.")
                return
            if action == "ok":
                out = self.store.apply(pid)
                self.bot.answer_callback(cq["id"], "Applied")
                if m:
                    self.bot.clear_buttons(m["chat"]["id"], m["message_id"], new_text=(m.get("text") or "")[:3800] + f"\n\n✅ applied: {out}")
            else:
                self.store.reject(pid)
                self.bot.answer_callback(cq["id"], "Left as it is")
                if m:
                    self.bot.clear_buttons(m["chat"]["id"], m["message_id"], new_text=(m.get("text") or "")[:3800] + "\n\n❌ not applied")
            self.log("store_decision", id=pid, action=action)
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

    # ---- eyes -------------------------------------------------------------
    def install_eyes(self):
        msg = self.eyes.install(progress=lambda p: self.log("eyes_download", progress=p))
        self.notify(msg + ("" if self.eyes.ocr else "\nFor exact clicking I also need OCR: sudo apt install -y tesseract-ocr (see scripts/install_desktop.sh)."))

    def look_at_photo(self, chat_id, file_id, question):
        data = self.bot.get_file(file_id)
        if not data:
            self.bot.send(chat_id, "I couldn't download that picture.")
            return
        if not self.eyes.installed():
            txt = self.eyes.text(data) if self.eyes.ocr else ""
            self.bot.send(chat_id, ("I can read the words but my vision model isn't installed yet (/eyes install).\n\n" + txt[:1500]) if txt
                          else "My vision model isn't installed yet — send /eyes install (310 MB, once).")
            return
        self.busy = "looking at a picture"
        try:
            d = self.eyes.describe(data)
            ans = self.eyes.look(data, question) if question else ""
            words = self.eyes.text(data, limit=600) if self.eyes.ocr else ""
            out = f"👁 {d['title'] or 'Picture'} — {d['summary']}"
            if d["warnings"]:
                out += "\n⚠️ " + ", ".join(d["warnings"])
            if ans:
                out += f"\n\nYour question: {ans}"
            if words:
                out += f"\n\nText I can read: {words[:500]}{'…' if len(words) > 500 else ''}"
            self.bot.send(chat_id, out)
        finally:
            self.busy = None

    def look_at_screen(self, question=None):
        """Screenshot of the agent's own screen (desktop if there is one, else the browser) → eyes → owner."""
        shot = b""
        src = ""
        if self.desktop.available() and (os.environ.get("DISPLAY") or self.desktop.own_x):
            shot = self.desktop.screenshot("look")
            src = "my desktop"
            if shot and self.eyes.ocr and not self.eyes.read(shot):          # blank screen: nothing open on it
                shot, src = b"", ""
        if not shot:
            try:
                res = self.tasks.screenshot()
                if res:
                    shot, src = res[0], "my browser"
            except Exception:
                pass
        if not shot:
            self.notify("Nothing to look at right now: my desktop is empty and my browser is closed (it opens when a task starts).")
            return
        self.busy = "looking at my screen"
        try:
            self.bot.send_photo(self.owner_id, shot, caption=src)
            if self.eyes.installed():
                d = self.eyes.describe(shot)
                ans = self.eyes.look(shot, question) if question else ""
                out = f"👁 I see: {d['title']} — {d['summary']}" + (f"\n⚠️ {', '.join(d['warnings'])}" if d["warnings"] else "") + (f"\n\n{ans}" if ans else "")
            else:
                out = "Text on it: " + (self.eyes.text(shot, limit=500) or "(none)") + "\n(vision model not installed — /eyes install)"
            self.notify(out)
        finally:
            self.busy = None

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
        """Hand an approved reply to its channel. practice: log only; owner (pasted/forwarded): give back copyable text;
        email / facebook / instagram: really send it (this is the only place a customer message ever leaves)."""
        rec = self.inbox.get(mid) or {}
        ch = rec.get("channel", "practice")
        if ch == "owner":
            self.bot.send(self.owner_id, f"📋 Reply for {rec.get('from', 'the customer')} — long-press to copy, then paste it where they wrote you:\n\n{final_text}")
        elif ch == "store":                                              # practice shop: the reply is filed on the order (visible in /store admin)
            d = self.drafts.get(mid) or {}
            try:
                self.store.note_reply(d.get("order_no"), rec.get("from", ""), final_text)
            except Exception as e:
                self.log("store_note_error", error=str(e)[:120])
        elif ch == "social" and rec.get("post_url") and self.rehearsal.is_stage(rec["post_url"]):
            ok = self.rehearsal.reply(rec["post_url"], final_text)
            self.bot.send(self.owner_id, ("🎭 Reply posted under the rehearsal post (practice network only)." if ok else "🎭 I could not place the reply under the rehearsal post — noted for the next rehearsal."))
        elif ch in REAL_CHANNELS:
            ok, info = self.channels.send(rec, final_text)
            if ok:
                self.bot.send(self.owner_id, f"📤 Sent to {rec.get('from', 'the customer')} by {ch}.")
            else:
                self.bot.send(self.owner_id, f"⚠️ Could not send the reply to {rec.get('from', 'the customer')} by {ch}: {info}\n"
                                             f"Here it is to send by hand:\n\n{final_text}")
        self.log("inbox_delivered", id=mid, channel=ch)

    def poll_channels(self, announce=False):
        """Fetch new customer messages from the real channels and draft replies for them (nothing is sent)."""
        try:
            new = self.channels.poll()
        except Exception as e:
            self.log("channel_error", error=str(e)[:200])
            new = []
        if new:
            self.notify(f"📥 {len(new)} new customer message{'s' if len(new) > 1 else ''} — drafting replies, you'll get them with Approve & send / Edit / Reject.")
            self.process_inbox()
        elif announce:
            self.notify("📥 Checked: no new customer messages.")
        return len(new)

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
                real = rec.get("channel") in REAL_CHANNELS
                ok_label = ("⚠️ Send anyway" if real else "⚠️ Approve anyway") if d["checks"] else ("✅ Approve & send" if real else "✅ Approve")
                self.bot.send(self.owner_id, body, buttons=[[(ok_label, f"r:ok:{rec['id']}"), ("✏️ Edit", f"r:edit:{rec['id']}"), ("❌ Reject", f"r:no:{rec['id']}")]])
                self.log("inbox_draft", id=rec["id"], mtype=d["kind"], flags=d["checks"])
                if rec.get("channel") == "store" and d.get("order_no") and d["kind"] in ("cancel_or_change", "damaged_or_wrong", "where_is_my_order"):
                    prop = self.store.proposal_for_message(d["kind"], d["order_no"], rec.get("text", ""))
                    if prop is None and d["kind"] == "where_is_my_order":       # the draft step may have opened it already
                        prop = next((p for p in reversed(self.store.data["proposals"]) if p["status"] == "open" and p["kind"] == "ship" and p["target"] == str(d["order_no"]) and "asking where" in p["why"]), None)
                    if prop:
                        self.bot.send(self.owner_id, f"🏪 Proposal — {prop['kind']} order {prop['target']}\n{prop['why']}",
                                      buttons=[[("✅ Apply", f"s:ok:{prop['id']}"), ("❌ Leave it", f"s:no:{prop['id']}")]])
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
        if low.startswith("/eyes"):
            arg = low[5:].strip()
            if arg.startswith("install"):
                threading.Thread(target=self.install_eyes, daemon=True).start()
                return "Downloading my vision model (about 310 MB, once). I'll tell you when it's ready."
            return f"{self.eyes.describe_status()}\n{self.desktop.describe_status()}\n\nSend me any screenshot or photo (with a question as the caption if you like) and I'll tell you what I see. /look = look at my own screen now."
        if low.startswith("/look"):
            q = text[5:].strip() or None
            threading.Thread(target=self.look_at_screen, args=(q,), daemon=True).start()
            return "Looking at my screen…"
        if low.startswith("/do"):
            return self.start_do(text[3:].strip())
        if low.startswith("/post"):
            arg = text[5:].strip()
            if not arg:
                return "Tell me what the post is about: /post instagram our new bamboo toothbrush set (platforms: instagram, facebook, tiktok, x, linkedin, pinterest)."
            plat, topic = self.social.parse(arg)
            if not topic:
                return f"What should the {plat} post be about?"
            threading.Thread(target=self.draft_post, args=(plat, topic), daemon=True).start()
            return f"Drafting a {plat} post about “{topic}” — you'll get it with Approve / Edit / Reject buttons. Nothing gets published by itself."
        if low.startswith("/channels"):
            arg = low[9:].strip()
            if arg == "check":
                return "🔌 " + self.channels.check()
            if arg == "now":
                if not self.channels.configured():
                    return self.channels.status()
                threading.Thread(target=self.poll_channels, kwargs={"announce": True}, daemon=True).start()
                return "Checking the channels now…"
            return "🔌 " + self.channels.status()
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
        if low.startswith("/store"):
            return self.store_command(text[6:].strip())
        if low.startswith("/shop"):
            arg = text[5:].strip()
            if arg.lower() in ("forget", "clear", "reset"):
                self.shopfacts.forget()
                return "Forgotten — I no longer use any facts from a shop website."
            if not arg:
                return self.shopfacts.sheet_text()
            if self.busy:
                self.mind.queue.append((f"/shop {arg}", time.time()))
                return f"I'm still on: {self.busy}. Queued the shop read as #{len(self.mind.queue)} — it starts right after."
            self.start_shop_read(arg)
            return f"Reading {arg} now — its help, shipping, returns and contact pages. About a minute; I'll show you what I found."
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
        if re.search(r"\b(start|begin|avvia)\b.*\b(auto[- ]?train|training|practi[cs]e|allenamento)\b.*\b(website|web site|sites?|siti)\b", low) or low.startswith("/train"):
            arg = low.replace("/train", "").strip()
            if arg.startswith("stop") or arg in ("off", "no"):
                self.site_training = False
                return f"Stopping website training after the current one ({self.sites_built} built this session)."
            if self.site_training:
                return f"Already training on websites ({self.sites_built} built so far). Say 'stop training' to stop. Watch it on {self.viewer.address()}"
            self.site_training = True
            threading.Thread(target=self.train_sites, daemon=True).start()
            return (f"🏋️ Website training on: I pick a random real place in a random country, build its full site, check it in my browser, save it "
                    f"to my library/Drive and send you one line per site. Watch on {self.viewer.address()} — say 'stop training' to stop.")
        if re.search(r"^(stop|basta|enough)\b.*\b(train|training|allenamento|websites?)?", low) and self.site_training:
            self.site_training = False
            return f"Okay — stopping website training after the current one ({self.sites_built} built)."
        if low.startswith("/rehearse") or re.search(r"\b(rehears\w*|dry[- ]?run|practi[cs]e)\b.*\b(post\w*|social|instagram|facebook|tiktok|publishing)\b", low) \
                or re.search(r"\b(post\w*|social)\b.*\b(rehears\w*|dry[- ]?run|practi[cs]e)\b", low):
            arg = re.sub(r"^/rehearse\s*", "", text.strip(), flags=re.I)
            if arg.lower() in ("map", "status", "what did you learn", "learned"):
                return "🎭 What I know about posting interfaces:\n" + self.rehearsal.map_text()
            topic = re.sub(r"\b(rehearse|rehearsal|dry run|practice|practise|posting|a post|post|on|social media|social)\b", " ", arg, flags=re.I).strip(" ,.:") or "our newest product"
            threading.Thread(target=self.run_rehearsal, args=(topic, True), daemon=True).start()
            return "🎭 Rehearsing: I draft a post, log into my practice network with my own account, publish it there with a photo, read the platform's reaction, then answer the comments. One report line when done."
        if low.startswith("/lessons") or re.fullmatch(r"\W*(what did you learn( from your (last )?jobs)?|lessons?( learned)?|cosa hai imparato)\W*", low):
            return self.mind.lessons_text()
        if low.startswith("/ideas"):
            arg = text[6:].strip()
            if arg:
                threading.Thread(target=lambda: self.notify(self.study.video_session(query=arg)), daemon=True).start()
                return f"Watching short videos about “{arg}” and jotting the concrete ideas — a few minutes."
            return self.study.ideas_text()
        if low.startswith("/study"):
            arg = text[6:].strip()
            threading.Thread(target=lambda: self.notify(self.study.pdf_session(topic=arg or None)), daemon=True).start()
            return "Looking for a good PDF to learn from" + (f" about {arg}" if arg else "") + " — I'll tell you if I keep one."
        if low.startswith("/library"):
            return library.list_text(10) + ("\n\nDrive folder: " + self.google.folder_link() if self.google.connected() else "")
        if low.startswith("/accounts") or low.startswith("/account"):
            return self.accounts.list_text()
        if low.startswith("/google") or re.fullmatch(r"(please )?(connect|link|reconnect|set ?up) (to )?(my |your )?google( drive| account)?( please)?", low.strip(" .!")):
            return self.google_command(text[7:].strip() if low.startswith("/google") else "connect")
        if low.startswith("http://localhost") and "code=" in low:
            return self.google.finish_with_url(text)
        if low.startswith("/learned"):
            if "rebuild" in low:
                threading.Thread(target=lambda: self.notify(self.learner.build(force=True)), daemon=True).start()
                return "Rebuilding my learned pack — I'll tell you when it's done."
            rec = self.learner.recent(8)
            return self.learner.status() + ("\n\nLatest facts:\n" + "\n".join(f"• {f['text']}" for f in rec) if rec else "")
        # ---- plain language: understand → plan → do --------------------------------
        if self.planner.last_error and not getattr(self, "warned_llm", False):
            self.warned_llm = True
            self.notify(f"⚠️ My thinking model isn't running: {self.planner.last_error}\nI'll keep working in simple mode (worse understanding and answers) until it is fixed. /status shows the state.")
        return self.understand(text)

    # ---- milestone 13: understand → plan → do -------------------------------------------
    GO_WORDS = re.compile(r"^(go|ok go|yes go|do it|go ahead|start|proceed|vai|procedi|sì vai|yes|yep|ok|okay|sure)\W*$", re.I)

    def understand(self, text):
        """Every plain message: build a brief (goal, pace, deliverable, steps). Short jobs start at once with the plan
        shown; long ones (documents, sites) show the plan first with Go / Change / Cancel buttons."""
        low = text.strip().lower()
        if self.busy and self.mind.job and not self.last_brief:                       # a message while I'm working
            what, reply = self.mind.interrupt(text)
            if what in ("status", "why", "hurry"):
                return reply
            if what == "stop":
                self.stop_flag = True
                self.site_training = False
                self.pace.stop_now()
                self.mind.snag("owner said stop")
                return f"Stopping “{self.mind.job['goal'][:60]}” — I'll hand you what I have so far in a moment."
            if what == "chat":
                return None if re.fullmatch(r"\W*(ok(ay)?|👍|❤️|🙏)\W*", low) else "🙂 (still working on it — ask me 'status' any time)"
            if what == "change":
                self.mind.job["snags"].append(f"owner changed course: {text[:80]}")
                self.mind.job["change"] = text
                return f"Noted for this job: “{text.strip()[:100]}”. I apply it to what's left, and I'll say so in the result."
            self.mind.queue.append((text, time.time()))
            return f"Got it — I'm in the middle of “{self.mind.job['goal'][:60]}”, so this is queued as #{len(self.mind.queue)}. I start it as soon as I'm done (or say 'stop' to switch now)."
        if self.last_brief and self.GO_WORDS.match(low):
            b, self.last_brief = self.last_brief, None
            return self.execute(b)
        if self.last_brief and re.match(r"^(no|cancel|stop|forget it|nah|annulla|lascia)\W*$", low):
            self.last_brief = None
            return "Okay, dropped."
        if self.last_brief and len(low.split()) <= 12 and not low.startswith("/"):
            b = self.last_brief
            b = self.briefer.amend(b, text)
            self.last_brief = b
            self.bot.send(self.owner_id, Brief.text(b) + "\n\nShall I go?", buttons=[[("▶ Go", "b:go"), ("✏️ Change", "b:edit"), ("✖ Cancel", "b:no")]])
            return None
        it = self.planner.intent(text) if self.planner.installed() else None       # cheap regexes inside, model for the middle
        b = self.briefer.make(text)
        if it and it["kind"] in ("watch", "summarize", "visit") and b["kind"] in ("ask", "research", "visit", "watch", "summarize"):
            b["kind"], b["topic"] = it["kind"], it["topic"]                                        # URL rules are reliable
        self.log("intent", intent=b["kind"], topic=b["topic"][:80])
        if b["kind"] == "chat":
            try:
                return self.planner.reply(text) if self.planner.installed() else "Hi! Tell me what you need — a search, a seller check, a document, a website…"
            except Exception:
                return "Hi! Tell me what you need."
        if b["kind"] == "ask":
            self.pace.set(b["pace"], b["goal"])
            ans = self.tasks.ask(text)
            if ans and not re.search(r"\b(does not|doesn't|do not|don't) (contain|answer|mention|provide|include)\b|no evidence|not enough (evidence|information)", ans, re.I):
                self.pace.finish()
                return ans
            if not self.brain.ready and not self.planner.installed():
                return "My knowledge brain and thinking model aren't installed here yet — run: sh scripts/get_brain.sh && sh scripts/get_model.sh"
            b["kind"] = "research"
            return self.execute(b, prefix="I don't know that well enough from my own knowledge, so I'll look it up. ")
        big = b["deliverable"] in ("document", "website") or b["kind"] in ("seller_check", "build_site") or b.get("questions")
        if big and not (b["pace"]["pace"] == "quick" and not b.get("questions")):
            self.last_brief = b
            adv = self.mind.advice(b["kind"])
            self.bot.send(self.owner_id, Brief.text(b) + ("\n\n🧠 From last time: " + " · ".join(adv[:2]) if adv else "") + "\n\nShall I go? (you can also write changes, e.g. 'only Italian sellers, max 30 €')",
                          buttons=[[("▶ Go", "b:go"), ("✏️ Change", "b:edit"), ("✖ Cancel", "b:no")]])
            return None
        return self.execute(b)

    def execute(self, b, prefix=""):
        if self.busy:                                  # e.g. ▶ Go tapped while another job runs → queue it, never a dead end
            self.mind.queue.append((b, time.time()))
            return (f"I'm still on: {self.busy}. I queued “{(b.get('goal') or '')[:60]}” as #{len(self.mind.queue)} and start it right after "
                    f"(say 'stop' to switch now).")
        self.pace.set(b["pace"], b["goal"])
        self.active_brief = b
        self.stop_flag = False
        self.viewer.show_plan(b["goal"], b["steps"], self.pace)
        kind, topic = b["kind"], b["topic"]
        self.mind.begin(b["goal"], kind, b["steps"], why=f"You asked: “{b['goal'][:100]}” — I hand you {b['deliverable']} at {b['pace']['pace']} pace.")
        adv = self.mind.advice(kind)
        head = Brief.text(b) if not prefix else prefix + Brief.text(b)
        if adv:
            head += "\n\n🧠 From last time: " + " · ".join(adv[:2])
        if kind == "seller_check":
            threading.Thread(target=self.run_seller_check, args=(b,), daemon=True).start()
            return head + "\n\nStarting — you'll get the document here (and in my Drive if it's connected)."
        if kind == "watch" and not re.search(r"https?://", topic) and re.search(r"\b(ideas?|videos|shorts|tiktoks?|reels)\b", b["goal"], re.I):
            threading.Thread(target=self._run_ideas, args=(topic, b), daemon=True).start()
            return head
        if kind == "watch" and re.search(r"https?://", b["goal"]) and len(re.findall(r"https?://\S+", b["goal"])) > 1:
            urls = re.findall(r"https?://\S+", b["goal"])
            threading.Thread(target=self._run_ideas, args=(None, b, urls), daemon=True).start()
            return head
        if kind in ("research", "compare", "summarize", "visit", "watch"):
            threading.Thread(target=self.run_task, args=(f"{kind} {topic}", b), daemon=True).start()
            return head + ("\n\nYou'll get the document here (and in my Drive if it's connected)." if b["deliverable"] == "document" else "")
        if kind == "build_site":
            threading.Thread(target=self.run_build_site, args=(b,), daemon=True).start()
            return head + "\n\nBuilding it now — you'll get a screenshot and the files (and a Drive link if connected)."
        if kind == "post":
            plat, t2 = self.social.parse(topic)
            threading.Thread(target=self.draft_post, args=(plat, t2 or topic), daemon=True).start()
            return head
        return self.start_task("research", topic)

    def _site_brief_from(self, b):
        """'build a website for a small bakery in bergamo called Forno Bianchi' → builder brief."""
        g = b["goal"]
        low = g.lower()
        kind = next((k for k in sorted(SITE_KINDS, key=len, reverse=True) if k in low), None)
        if not kind:
            kind = {"pizzeria": "restaurant", "trattoria": "restaurant", "bar": "cafe", "coffee": "cafe", "barber": "hair salon", "hairdresser": "hair salon", "fitness": "gym",
                    "dental": "dentist", "b&b": "hotel", "bed and breakfast": "hotel", "flowers": "florist", "books": "bookshop", "bikes": "bike shop", "vet": "veterinary",
                    "lawyer": "lawyer", "studio legale": "lawyer", "store": "shop", "boutique": "shop"}.get(next((w for w in ("pizzeria", "trattoria", "coffee", "barber", "hairdresser", "fitness", "dental", "b&b", "bed and breakfast", "flowers", "books", "bikes", "vet", "studio legale", "lawyer", "boutique", "store", "bar") if w in low), ""), "shop")
        m = re.search(r"\b(?:called|named|chiamat[oa]|di nome)\s+[\"“']?([A-Z][\w&'’ -]{1,40}?)[\"”']?(?:\s+(?:in|at|a|di|offering|that|which|with)\b|\s*[,.;:]|$)", g)
        name = m.group(1).strip() if m else None
        if not name:                                                       # "for Studio Legale Rossi, a lawyer in Milan"
            m = re.search(r"\b(?:for|per)\s+((?:[A-Z][\w&'’-]*\s?){1,4})\s*,\s*(?:an?|the|un|una)\b", g)
            name = m.group(1).strip() if m else None
        m2 = re.search(r"\b(?:in|at|a)\s+([A-Z][\w'’-]+(?: [A-Z][\w'’-]+)?)(?:\s*,\s*([A-Z][\w]+(?: [A-Z][\w]+)?))?(?=\s*[.,;:]|\s+(?:called|named|that|which|with|for|offering|and)\b|$)", g)
        city = m2.group(1).strip() if m2 else ""
        country = (m2.group(2) or "").strip() if m2 else ""
        if not name:
            name = f"{city} {kind.title()}".strip() if city else f"My {kind.title()}"
        services = None
        m3 = re.search(r"\b(?:services|offering|that (?:sells|does|offers))\s*:?\s*(.+)$", g, re.I)
        if m3:
            services = [x.strip(" .") for x in re.split(r",|;| and ", m3.group(1)) if 2 < len(x.strip()) < 40][:6] or None
        return {"name": name, "kind": kind, "city": city, "country": country, "services": services, "about": None, "tagline": None}

    def run_build_site(self, b):
        self.busy = "building a website"
        try:
            brief = self._site_brief_from(b)
            self.viewer.plan_step(1, f"writing copy for {brief['name']}")
            report, built, shot = self.sites.build_for(brief)
            self.viewer.plan_step(3, "checked in my browser")
            self.bot.send(self.owner_id, report)
            if shot:
                self.bot.send_photo(self.owner_id, shot, caption=f"Home page of {brief['name']}")
            if built:
                self.bot.send_document(self.owner_id, str(built["zip"]), caption="The whole site (unzip, open index.html).")
            self.memory.note("website", brief["name"], report, [])
        except Exception as e:
            self.log("build_site_failed", error=traceback.format_exc()[-400:])
            self.bot.send(self.owner_id, f"Building the site failed: {type(e).__name__}: {str(e)[:160]}")
            self.mind.snag(f"{type(e).__name__}: {str(e)[:80]}")
            delivered = False
        finally:
            self.busy = None
            self._finish_job(locals().get("report", "") if isinstance(locals().get("report"), str) else "", delivered=locals().get("delivered", True))

    def train_sites(self):
        """Auto-training loop: random real place → full site → check → save; one short line per site."""
        import random as _r
        rng = _r.Random()
        while self.site_training:
            if self.busy and not str(self.busy).startswith("website training"):
                time.sleep(20)
                continue
            self.busy = "website training"
            try:
                self.viewer.show_plan("Website training: random real place → full website", ["pick a random place on the map", "write the copy", "build the pages", "check every page in my browser", "save to my library / Drive"], None)
                self.viewer.plan_step(0)
                report, built, shot = self.sites.auto_train(rng)
                self.viewer.plan_done()
                if built:
                    self.sites_built += 1
                    self.bot.send(self.owner_id, report.splitlines()[0].replace("🌐 Built a website for", f"🌐 #{self.sites_built} built this website for") + ("\n" + report.splitlines()[1] if len(report.splitlines()) > 1 else ""))
                    if shot and self.watch:
                        self.bot.send_photo(self.owner_id, shot, caption=built["slug"])
                    self.memory.note("website", built["slug"], report, [])
                else:
                    self.log("site_train_skip", why=report[:100])
            except Exception as e:
                self.log("site_train_failed", error=traceback.format_exc()[-300:])
            finally:
                self.busy = None
            for _ in range(45):                                   # 45 s between sites, stop promptly when told
                if not self.site_training:
                    break
                time.sleep(1)
        self.bot.send(self.owner_id, f"🏁 Website training stopped — {self.sites_built} site(s) built this session; all in my library" + (" and Drive → Websites." if self.google.connected() else "."))

    # ---- social rehearsal (milestone 18) --------------------------------------------------------
    def stage_url(self):
        """Start the rehearsal network on this machine (once) and return its address."""
        if self.stage is None:
            import importlib.util
            path = Path(__file__).resolve().parent.parent / "tests" / "social" / "server.py"
            spec = importlib.util.spec_from_file_location("postly", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            port = int(os.environ.get("BAI_STAGE_PORT", "8096"))
            srv = mod.serve(port)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.stage = (srv, f"http://127.0.0.1:{port}/")
            self.log("stage_started", port=port)
        return self.stage[1]

    def _placeholder_photo(self, topic):
        """A simple product-card image for rehearsals: PIL when present, else a screenshot of an HTML card in my browser."""
        path = config.STATE_DIR / "rehearsal_photo.jpg"
        try:
            from PIL import Image, ImageDraw
            im = Image.new("RGB", (800, 600), (236, 228, 214))
            ImageDraw.Draw(im).text((40, 280), topic[:40], fill=(60, 60, 60))
            im.save(path, quality=80)
            return str(path)
        except Exception:
            pass
        try:
            card = config.STATE_DIR / "rehearsal_card.html"
            card.write_text(f"<html><body style='margin:0;width:800px;height:600px;background:#ece4d6;display:flex;align-items:center;justify-content:center;"
                            f"font:32px system-ui;color:#333'>{html.escape(topic[:60])}</body></html>")
            def shot():
                with self.tasks._session() as b:
                    b.page.set_viewport_size({"width": 800, "height": 600})
                    b.open("file://" + str(card))
                    b.page.screenshot(path=str(path), type="jpeg", quality=80)
                    b.page.set_viewport_size({"width": 1280, "height": 800})
            self.tasks.on_hands(shot, timeout=60)
            return str(path)
        except Exception as e:
            self.log("placeholder_photo_failed", error=str(e)[:80])
            return None

    def run_rehearsal(self, topic, tell=True):
        """Draft (Social checks) → publish on the stage with a product photo → read comments → reply drafts. Quiet-time safe."""
        if self.busy:
            if tell:
                self.notify(f"I'm busy ({self.busy}) — the rehearsal comes right after.")
            while self.busy:
                time.sleep(3)
        self.busy = "rehearsing a social post"
        try:
            url = self.stage_url()
            d = self.social.draft("instagram", topic)
            photo = None
            try:
                prod = self.store.find_product(topic)
                img = (prod or {}).get("image")
                if img and Path(img).exists():
                    photo = img
            except Exception:
                photo = None
            if not photo:
                photo = self._placeholder_photo(topic)
            rep = self.rehearsal.post(url, d["text"], image=photo, file_for_owner=tell)
            self.rehearsals_done += 1
            line = self.rehearsal.report_text(rep)
            self.memory.note("rehearsal", f"posting on {rep.get('site', 'stage')}", line, [])
            self.log("rehearsal", ok=rep.get("ok"), attempts=rep.get("attempts"), site=rep.get("site"))
            if tell:
                self.bot.send(self.owner_id, line + ("\n(the post lives only on my practice network — nothing public)" if rep.get("ok") else ""))
            followup = bool(tell and rep.get("ok") and rep.get("replies"))
        except Exception as e:
            self.log("rehearsal_failed", error=traceback.format_exc()[-300:])
            if tell:
                self.bot.send(self.owner_id, f"The rehearsal broke: {type(e).__name__}: {str(e)[:120]}")
            return f"rehearsal failed: {str(e)[:80]}"
        finally:
            self.busy = None
        if followup:
            self.process_inbox()                                              # the comment replies go through the normal Approve / Edit / Reject gate
        return line

    def _run_ideas(self, query, b, urls=None):
        self.busy = "ideas from videos"
        try:
            self.bot.send(self.owner_id, self.study.video_session(query=query, urls=urls))
        except Exception as e:
            self.bot.send(self.owner_id, f"Couldn't read those videos: {str(e)[:120]}")
            self.mind.snag(str(e)[:80])
            delivered = False
        finally:
            self.busy = None
            self._finish_job("ideas session", delivered=locals().get("delivered", True))

    def run_seller_check(self, b):
        self.busy = f"seller check: {b['topic'][:40]}"
        try:
            note = "Note: branded replicas are counterfeit, so these are genuine or unbranded options. " if b.get("counterfeit") else ""
            path, summary, options = self.tasks.on_hands(self.sellers.run, b["topic"], 4, True, note, timeout=1500)
            if not path:
                self.bot.send(self.owner_id, summary)
                return
            link = ""
            if self.google.connected():
                try:
                    up = self.google.upload(path, folder="Research", convert_to_doc=True)
                    link = f"\n📄 Google Doc: {up['link']}"
                except Exception as e:
                    self.log("drive_upload_failed", error=str(e)[:120])
                    link = f"\n(Drive upload failed: {str(e)[:80]} — the file is attached instead)"
            self.bot.send(self.owner_id, f"✅ Done. {summary}{link}")
            self.bot.send_document(self.owner_id, str(path), caption="The full document — open it in any browser (pictures, links, verdicts).")
            self.memory.note("sellers", b["topic"], summary, [o["url"] for o in options])
            # ---- offer to add the good ones to the shop --------------------------------
            good = [o for o in options if o.get("grade") == "good" and o["facts"].get("_price")]
            if good and self.store.server:
                o = good[0]
                price = round(o["facts"]["_price"] * 2.5, 2)
                prop = self.store.propose("product", o["seller"], json.dumps({"name": f"{b['topic'].title()} ({o['seller']})", "cost": o["facts"]["_price"], "price": price,
                                                                             "short": o.get("verdict", ""), "supplier": o["url"], "ship": o["facts"].get("Delivery time", "")}),
                                          f"best option from the seller check of {b['topic']}")
                self.bot.send(self.owner_id, f"🛒 The shop is open — want me to add {o['seller']}'s {b['topic']} to it? Cost {o['facts'].get('Price')} → I'd list it at € {price:.2f} "
                                             f"(2.5×), shipping {o['facts'].get('Delivery time', 'as the supplier states')}, description from the listing.",
                              buttons=[[("✅ Add to shop", f"s:ok:{prop['id']}"), ("❌ No", f"s:no:{prop['id']}")]])
        except Exception as e:
            self.log("seller_check_failed", error=traceback.format_exc()[-400:])
            self.bot.send(self.owner_id, f"The seller check failed: {type(e).__name__}: {str(e)[:160]}")
            self.mind.snag(f"{type(e).__name__}: {str(e)[:80]}")
            delivered = False
        finally:
            self.busy = None
            self._finish_job(locals().get("summary", "") if isinstance(locals().get("summary"), str) else "", delivered=locals().get("delivered", True))

    def start_do(self, arg):
        """/do [desktop] [<url> |] <goal> — the operator works the screen step by step."""
        if not arg:
            return ("Tell me the goal, e.g.\n/do https://en.wikipedia.org/wiki/Etsy | in which year was Etsy founded?\n"
                    "/do desktop what is written on my screen right now?\nI look, decide one step, click or type, check, repeat — "
                    "and ask you before any click that costs money, publishes, signs in or deletes.")
        if self.busy:
            self.mind.queue.append((f"/do {arg}", time.time()))
            return f"I'm still on: {self.busy}. Queued this /do as #{len(self.mind.queue)} — it starts right after (say 'stop' to switch now)."
        if not self.planner.installed():
            return "My thinking model isn't installed here yet — run: sh scripts/get_model.sh"
        where = "browser"
        if re.match(r"^(desktop|screen)\b", arg, re.I):
            where = "desktop"
            arg = re.sub(r"^(desktop|screen)\b[:\s]*", "", arg, flags=re.I).strip()
            if not self.desktop.available():
                return "I have no desktop hands here yet — run: sh scripts/install_desktop.sh (then /eyes to check)."
        if len(arg) < 4:
            return "And the goal? e.g. /do desktop what is written on my screen right now?" if where == "desktop" else "And the goal? e.g. /do en.wikipedia.org/wiki/Etsy | in which year was Etsy founded?"
        start_url, goal = None, arg
        if where == "browser":
            mm = re.match(r"^((?:(?:https?|file)://\S+|[a-z0-9.-]+\.[a-z]{2,}\S*)(?:[\s,]+(?:(?:https?|file)://\S+|[a-z0-9.-]+\.[a-z]{2,}\S*))+)\s*[|—-]\s*(.+)$", arg, re.I | re.S)
            m = re.match(r"^((?:https?|file)://\S+|[a-z0-9.-]+\.[a-z]{2,}\S*)\s*[|—-]?\s*(.*)$", arg, re.I | re.S)
            if mm:                                                        # "/do <page1> <page2> <page3> | which is cheapest?"
                start_url, goal = re.split(r"[\s,]+", mm.group(1).strip()), mm.group(2).strip()
            elif m and m.group(2).strip():
                start_url, goal = m.group(1), m.group(2).strip()          # "/do <address> | <goal>"
            else:
                mu = re.search(r"((?:https?|file)://\S+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:/\S*)?)", arg, re.I)
                if mu:                                                    # "… on shop.example.com" anywhere in the goal
                    start_url = mu.group(1).rstrip(".,;:)")
                    goal = re.sub(r"\s*\(?\b(?:on|at|from|in)\s+" + re.escape(mu.group(1)) + r"[.,;:)]*", "", arg).strip(" (") or arg
        if where == "browser" and not start_url and not (self.tasks._browser and self.tasks._browser.alive()):
            return ("Which page should I start on? Write it first: /do <address> | <goal>\n"
                    "e.g. /do en.wikipedia.org/wiki/Etsy | in which year was Etsy founded?")
        if where == "desktop" and not self.eyes.ocr:
            return "For working my own screen I need OCR: sudo apt install -y tesseract-ocr (sh scripts/install_desktop.sh does it)."
        threading.Thread(target=self.run_do, args=(goal, where, start_url), daemon=True).start()
        where_txt = "my own screen" if where == "desktop" else (f"{len(start_url)} pages" if isinstance(start_url, list) else (start_url or "the page I have open"))
        return (f"On it — working {where_txt} towards: “{goal}”. "
                f"I'll report when I'm done or stuck (usually 1–5 minutes; each step takes a moment on this machine).")

    def run_do(self, goal, where, start_url):
        self.busy = f"working the {'desktop' if where == 'desktop' else 'browser'}: {goal[:40]}"
        try:
            out = self.operator.run(goal, where=where, start_url=start_url)
        except Exception as e:
            self.log("do_error", error=str(e)[:200])
            out = f"Something broke while I was working on it: {str(e)[:120]}"
        finally:
            self.busy = None
        self.log("out", text=out[:300])
        self.bot.send(self.owner_id, out)

    # ---- practice store (milestone 11) ------------------------------------
    def store_url(self):
        return f"http://{self.store.host}:{practice_store.PORT}/"

    def store_command(self, arg):
        a = arg.lower()
        st = self.store
        if a in ("", "status", "numbers"):
            if not st.server:
                return ("The practice store is closed. /store open starts it on this machine (nothing real: fake payments, simulated customers).\n"
                        "Then: /store day — one practice day passes (visits, orders, customer messages) · /store review — I propose what to do "
                        "(ship, reorder, reprice; you tap) · /store numbers · /store orders · /store admin — the admin login · /store reset")
            return st.numbers_text() + f"\n\nshop: {self.store_url()} · admin: {self.store_url()}admin (login: /store admin) · open proposals: {len([p for p in st.data['proposals'] if p['status'] == 'open'])}"
        if a == "open":
            if st.server:
                return f"Already open: {self.store_url()}"
            try:
                practice_store.start(st, inbox=self.inbox, port=practice_store.PORT)
            except OSError as e:
                return f"I couldn't open the store on port {practice_store.PORT}: {e}"
            if not self.shopfacts.url or "127.0.0.1" in self.shopfacts.url:
                self.start_shop_read(self.store_url())                       # read my own shop like any other: facts + product pages
                learn = " I'm reading its pages now so customer replies use them."
            else:
                learn = ""
            return (f"Practice store open: {self.store_url()} (on the machine I run on; admin: {self.store_url()}admin, login with /store admin).{learn}\n"
                    f"/store day lets a practice day pass; /store review makes me propose actions.")
        if a == "close":
            practice_store.stop(st)
            return "Practice store closed (the ledger is kept)."
        if a == "admin":
            return f"Admin panel: {self.store_url()}admin — user admin, password {st.data['token']}"
        if a == "reset":
            st.reset()
            return "Practice store reset to the starting catalogue — no orders, day 0."
        if a.startswith("day"):
            n = int(re.search(r"\d+", a).group(0)) if re.search(r"\d+", a) else 1
            n = max(1, min(n, 7))
            rep = []
            for _ in range(n):
                r = st.simulate_day(inbox=self.inbox)
                rep.append(f"day {r['day']}: {r['visits']} visits, {len(r['orders'])} order(s)" + (f" ({money_list(r['orders'])})" if r["orders"] else "") + f", {len(r['messages'])} customer message(s)")
            if any(True for x in self.inbox.items("new")):
                threading.Thread(target=self.process_inbox, daemon=True).start()
                rep.append("Drafting the replies to the customer messages now — they come with Approve / Edit / Reject as usual.")
            return "\n".join(rep) + "\n\n" + st.numbers_text(st.data["day"])
        if a.startswith("review"):
            props = st.review()
            if not props:
                return "Nothing to propose: all orders shipped, stock fine, prices sane."
            for p in props:
                self.bot.send(self.owner_id, f"🏪 Proposal — {p['kind']} {p['target']} → {p['change']}\n{p['why']}",
                              buttons=[[("✅ Apply", f"s:ok:{p['id']}"), ("❌ Leave it", f"s:no:{p['id']}")]])
            return f"{len(props)} proposal(s) sent — tap Apply on the ones you agree with. Nothing changes until you tap."
        if a.startswith("orders"):
            os_ = st.data["orders"][-15:]
            if not os_:
                return "No orders yet. /store day makes customers come."
            return "\n".join(f"#{o['n']} day {o.get('day')} · {o['customer'].get('name', '')} ({o['country']}) · " + ", ".join(f"{l['name']} ×{l['qty']}" for l in o["lines"]) + f" · {money(o['total'])} · {o['status']}" for o in reversed(os_))
        if a.startswith("products") or a.startswith("stock"):
            return "\n".join(f"{p['name']} · {money(p['price'])} (cost {money(p.get('cost', 0))}) · stock {p['stock']}" for p in st.products())
        return "Store commands: /store [open|close|day [n]|review|numbers|orders|products|admin|reset]"

    def start_shop_read(self, url):
        def go():
            self.busy = "reading the shop's pages"
            try:
                out = self.shopfacts.learn(url)
            except Exception as e:
                out = f"Something broke while reading the shop: {str(e)[:120]}"
            finally:
                self.busy = None
            self.log("out", text=out[:300])
            self.bot.send(self.owner_id, out)
        threading.Thread(target=go, daemon=True).start()

    def start_task(self, kind, arg, prefix=""):
        if self.busy:
            self.mind.queue.append((f"/{kind} {arg}".strip(), time.time()))
            return f"I'm still on: {self.busy}. Queued “{kind} {arg[:50]}” as #{len(self.mind.queue)} — it starts right after (say 'stop' to switch now)."
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

    def _finish_job(self, outcome, delivered=True):
        """Every job ends here: reflect (one lesson), clear the clocks, then start whatever the owner queued meanwhile."""
        try:
            if self.mind.job:
                if self.mind.job.get("change"):
                    outcome = (outcome or "") + f" | owner's mid-job change: {self.mind.job['change'][:80]}"
                self.mind.reflect(outcome or "", delivered=delivered)
        except Exception as e:
            self.log("reflect_failed", error=str(e)[:100])
        self.pace.finish()
        self.viewer.plan_done()
        self.active_brief = None
        self.stop_flag = False
        if self.mind.queue:
            item, _ = self.mind.queue.pop(0)
            label = item.get("goal", "") if isinstance(item, dict) else item
            self.bot.send(self.owner_id, f"▶ Now the request you queued: “{str(label)[:80]}”")
            threading.Thread(target=self._start_queued, args=(item,), daemon=True).start()

    def _start_queued(self, item):
        """A queued item is either the owner's text (goes through understanding again) or an already-approved brief (runs as is)."""
        time.sleep(1)
        try:
            r = self.execute(item) if isinstance(item, dict) else self.respond(item)
            if r:
                self.bot.send(self.owner_id, r)
        except Exception as e:
            self.log("queued_failed", error=str(e)[:120])

    def run_task(self, command, brief=None):
        self.busy = command[:60]
        out = ""
        want_doc = bool(brief and brief.get("deliverable") == "document")
        self.tasks.want_doc = want_doc            # attribute, not argument: test doubles replace run(command)
        self.tasks.last_doc = None
        try:
            out = self.tasks.run(command)
        finally:
            self.busy = None
            if brief is not None:
                self._finish_job(out[:200], delivered=not out.startswith("Task failed"))
        self.log("out", text=out[:300])
        path = self.tasks.last_doc
        if path and not want_doc:                  # a doc came out anyway (e.g. seller list in a compare) → still hand it over
            want_doc = True
        if want_doc and path:
            link = ""
            if self.google.connected():
                try:
                    up = self.google.upload(path, folder="Research", convert_to_doc=True)
                    link = f"\n📄 Google Doc: {up['link']}"
                except Exception as e:
                    self.log("drive_upload_failed", error=str(e)[:120])
            self.bot.send(self.owner_id, f"✅ {out[:2500]}{link}")
            self.bot.send_document(self.owner_id, str(path), caption="The document — open it in any browser (links, pictures, key points).")
            return
        self.bot.send(self.owner_id, out)

    def idle_work(self):
        """Between messages: one self-study session when a learning goal is waiting, and the daily report at 20:00."""
        now = time.time()
        if self.busy or now - self.last_idle_check < 60:
            return
        self.last_idle_check = now
        self.google_check()
        if self.channels.due():
            threading.Thread(target=self.poll_channels, daemon=True).start()
            return
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
        if self.shopfacts.stale() and 8 <= hour < 23 and not self.busy:      # weekly: re-read the shop's own pages
            self.start_shop_read(self.shopfacts.url)
            return
        goal = self.memory.next_goal()
        if goal and 8 <= hour < 23 and self.owner_id:
            threading.Thread(target=self.run_study, args=(goal,), daemon=True).start()
            return
        # owner away ("take it slow") and nothing else to do → self-training sessions every ~10 min
        if self.pace.has_quiet_time() and not self.busy and now - self.last_quiet > 600:
            self.last_quiet = now
            threading.Thread(target=self.run_quiet, daemon=True).start()
            return
        # normal idle: at most 3 quiet sessions a day, daytime only, spaced ≥ 90 min
        if 9 <= hour < 22 and not self.busy and self.owner_id and now - self.last_quiet > 5400 and self.study.sessions_today() < 3:
            self.last_quiet = now
            threading.Thread(target=self.run_quiet, daemon=True).start()

    def run_quiet(self):
        self.busy = "self-training (quiet time)"
        try:
            if self.quiet_sessions % 4 == 3 and self.rehearsals_done < 2:
                out = "🎭 " + self.run_rehearsal("one of our products", tell=False)
            else:
                out = self.study.quiet_session(self.quiet_sessions)
            self.quiet_sessions += 1
            self.log("quiet_session", n=self.quiet_sessions, out=out[:120])
            if out.startswith(("📚", "💡", "🧠")) and self.owner_id:
                self.bot.send(self.owner_id, out)                      # one short line per kept thing, never chatter
        except Exception as e:
            self.log("quiet_session_failed", error=str(e)[:160])
        finally:
            self.busy = None
            if self.viewer:
                self.viewer.task = None

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

    def google_command(self, arg):
        arg = (arg or "").lower().strip()
        g = self.google
        if arg in ("connect", "reconnect", "link"):
            if not g.has_client():
                return ("I can't connect yet: my Google key file is missing. On my machine put the OAuth client JSON from Google Cloud at "
                        ".secrets/google_client.json (Google Auth Platform → Clients → Desktop app → Download JSON), then say 'connect google' again.")
            try:
                url = g.connect_link(prefer_port=8097)
            except Exception as e:
                return f"Couldn't start the Google connection: {e}"
            return ("Open this link in a browser where you're logged in as my account (busynessai001@gmail.com), click Advanced → Go to businessai → "
                    "tick everything → Continue:\n" + url +
                    "\n\nIf the last page fails to load (it points at localhost on my machine), just paste that page's address here and I'll finish it myself.")
        if arg in ("ls", "list", "library", "files"):
            if not g.connected():
                return g.status()
            try:
                files = g.list_library()
            except Exception as e:
                return f"Drive didn't answer: {e}"
            if not files:
                return f"My Drive library is empty so far — {g.folder_link()}"
            return "My Drive library (latest first):\n" + "\n".join(f"• {f['name'][:60]} — {f.get('webViewLink', '')}" for f in files[:15]) + f"\n\nFolder: {g.folder_link()}"
        if arg in ("mail", "inbox"):
            if not g.connected():
                return g.status()
            try:
                ms = g.recent_mail("newer_than:7d", 5)
            except Exception as e:
                return f"Gmail didn't answer: {e}"
            return "My mailbox, latest 5:\n" + ("\n".join(f"• {m['date'][:16]} · {m['from'][:35]} · {m['subject'][:50]}" for m in ms) or "(empty)")
        if arg.startswith("test"):
            if not g.connected():
                return g.status()
            try:
                doc = library.Doc("Google connection test", "written by Business AI to check its Drive library", kind="test")
                doc.summary("If you can read this in Google Drive, my library works: documents I write land here as editable Google Docs.")
                path = doc.save("google-test")
                up = g.upload(path, convert_to_doc=True)
                ms = g.recent_mail("newer_than:30d", 1)
                return f"✅ Drive works — test document: {up['link']}\n✅ Gmail works — I can read my mailbox ({len(ms)} recent message{'s' if len(ms) != 1 else ''}).\nFolder: {g.folder_link()}"
            except Exception as e:
                return f"❌ Google test failed: {e}"
        lib = library.list_text(5)
        return f"{g.status()}\n\n{lib}\n\n/google connect · /google test · /google ls (Drive files) · /google mail (my mailbox)"

    def google_check(self):
        """Called from the idle loop: if Google dropped the 7-day token, ask the owner once a day for a re-tap."""
        g = self.google
        if g.needs_reconnect and time.time() - self.google_reconnect_told > 86400:
            self.google_reconnect_told = time.time()
            self.notify("🔑 Google cut my Drive/Gmail connection (it does that every 7 days for private apps). " + self.google_command("connect"))

    def status_text(self):
        up = int(time.time() - self.started)
        return (f"Business AI {VERSION}\n"
                f"up {up // 3600}h {up % 3600 // 60}m · brain: {self.brain.describe()}\n"
                f"{self.planner.describe()} · notes: {len(self.memory.notes(limit=100000))} · {self.memory.list_text().splitlines()[-1]}\n"
                f"{self.learner.status()}\n"
                f"{self.inbox.status()} · {self.shopfacts.describe()}\n{self.social.status()}\n"
                f"practice store: {'open at ' + self.store_url() + ' · day ' + str(self.store.data['day']) + ' · ' + str(len(self.store.data['orders'])) + ' orders' if self.store.server else 'closed (/store open)'}\n"
                f"channels: {', '.join(c.describe().split(' (')[0] for c in self.channels.active()) or 'none connected (/channels)'}\n"
                f"{self.eyes.describe_status()} · {self.desktop.describe_status()}\n"
                f"{self.google.status()} · {self.accounts.id.describe()} · {len(self.accounts.data['accounts'])} site account(s)\n"
                f"{self.pace.text()}" + (f" · plan: {self.active_brief['goal'][:60]} (step {self.viewer.plan['step'] + 1 if self.viewer.plan else '?'}/{len(self.active_brief['steps'])})" if self.active_brief else "") + "\n"
                f"thinking: {self.mind.stats_text()}" + (f" · security checks: {self.tasks.captcha_stats['passed']} passed by myself, {self.tasks.captcha_stats['skipped']} skipped, {self.tasks.captcha_stats['owner']} handed to you" if self.tasks.captcha_stats["tried"] else "") + "\n"
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
            self.eyes.tick()
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
