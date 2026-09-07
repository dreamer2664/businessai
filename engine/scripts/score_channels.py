"""Score the real-channel plumbing (milestone 10) without any internet, model or account:
   python3 engine/scripts/score_channels.py

Starts the fake mail server (tests/fake_mail.py) and a fake Graph API in-process, then checks:
  mail parsing (plain, HTML, quoted history, signatures, encoded headers, attachments), machine filtering (no-reply, auto-reply,
  newsletter, bounce), dedupe across polls, reply threading (Re:, In-Reply-To, quoted original), Facebook/Instagram fetch + send,
  the approve gate inside the Agent (draft → tap → sent; reject → nothing sent; edit → owner's text sent), secrets never in logs.
"""
import email
import email.message
import email.utils
import http.server
import json
import os
import shutil
import socket
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, ".")
os.environ["BAI_STATE"] = os.path.abspath("state/test_channels")
shutil.rmtree("state/test_channels", ignore_errors=True)
os.environ.update(MAIL_USER="shop@test.local", MAIL_PASSWORD="s3cretpassw0rd", MAIL_IMAP_HOST="127.0.0.1", MAIL_IMAP_PORT="1143", MAIL_IMAP_SSL="0",
                  MAIL_SMTP_HOST="127.0.0.1", MAIL_SMTP_PORT="1025", MAIL_SMTP_TLS="0", MAIL_FROM_NAME="Green Nest",
                  META_PAGE_ID="PAGE1", META_PAGE_TOKEN="TOKEN1234567890", META_API="http://127.0.0.1:8099/v21.0", META_IG_ID="IG1")
sys.path.insert(0, "tests")
import warnings
warnings.filterwarnings("ignore")
try:
    import aiosmtpd  # noqa: F401
except ImportError:
    sys.exit("this test needs the tiny package aiosmtpd:  python3 -m pip install aiosmtpd   (only for the test, the agent itself needs nothing)")
import fake_mail                                   # noqa: E402
fake_mail.PASSWORD = "s3cretpassw0rd"
fake_mail.serve(1143, 1025)

# ---- fake Graph API --------------------------------------------------------------------------
META_SENT = []
CONVS = {"data": [
    {"id": "t_1", "participants": {"data": [{"id": "PAGE1", "name": "Green Nest"}, {"id": "U77", "name": "Giulia Bianchi"}]},
     "messages": {"data": [{"id": "m_3", "message": "Is the soap vegan?", "from": {"id": "U77", "name": "Giulia Bianchi"}, "created_time": "2026-09-07T10:00:00+0000"},
                           {"id": "m_2", "message": "Hello!", "from": {"id": "PAGE1", "name": "Green Nest"}, "created_time": "2026-09-07T09:00:00+0000"}]}},
    {"id": "t_2", "participants": {"data": [{"id": "PAGE1"}, {"id": "U88", "name": "Paolo"}]},
     "messages": {"data": [{"id": "m_9", "message": "Thanks, all good", "from": {"id": "PAGE1", "name": "Green Nest"}, "created_time": "2026-09-07T08:00:00+0000"},
                           {"id": "m_8", "message": "where is my parcel", "from": {"id": "U88", "name": "Paolo"}, "created_time": "2026-09-07T07:00:00+0000"}]}},
    {"id": "t_3", "participants": {"data": [{"id": "PAGE1"}, {"id": "U99", "name": "Sticker Sam"}]},
     "messages": {"data": [{"id": "m_11", "message": "", "from": {"id": "U99", "name": "Sticker Sam"}, "created_time": "2026-09-07T06:00:00+0000"}]}}]}
IG = {"data": [{"id": "t_ig1", "participants": {"data": [{"id": "IG1"}, {"id": "IGU5", "username": "marta.k"}]},
                "messages": {"data": [{"id": "ig_m1", "message": "do you ship to Austria?", "from": {"id": "IGU5", "username": "marta.k"}, "created_time": "2026-09-07T11:00:00+0000"}]}}]}


class Graph(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, d, code=200):
        b = json.dumps(d).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if q.get("access_token", [""])[0] != "TOKEN1234567890":
            return self._send({"error": {"message": "Error validating access token: Session has expired"}}, 400)
        if u.path.endswith("/conversations"):
            return self._send(IG if q.get("platform", [""])[0] == "instagram" else CONVS)
        return self._send({"name": "Green Nest", "id": "PAGE1"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n))
        META_SENT.append(body)
        self._send({"recipient_id": body["recipient"]["id"], "message_id": "mid.%d" % len(META_SENT)})


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8099), Graph)
threading.Thread(target=srv.serve_forever, daemon=True).start()


def ctl(cmd):
    s = socket.create_connection(("127.0.0.1", 1026))
    s.sendall((cmd + "\n").encode())
    d = s.makefile().readline()
    s.close()
    return d.strip()


def deliver_raw(raw: bytes):
    return fake_mail.BOX.deliver(raw)


def deliver(frm, subject, body, headers=None):
    return ctl("DELIVER " + json.dumps({"from": frm, "subject": subject, "body": body, "headers": headers or {}}))


score, total, notes = 0, 0, []


def check(name, cond, detail=""):
    global score, total
    total += 1
    score += bool(cond)
    print(f"{'OK  ' if cond else 'BAD '} {name}" + (f"  — {detail}" if detail and not cond else ""), flush=True)


from agent.channels import EmailChannel, MetaChannel, Channels, clean_body, message_text   # noqa: E402
from agent.inbox import Inbox                                                                 # noqa: E402
from agent import config                                                                      # noqa: E402

# ---- 1. mail parsing ---------------------------------------------------------------------------
m1 = email.message_from_bytes(fake_mail.make_mail("Anna Rossi <anna@example.com>", "shop@test.local", "Where is my order 51410?",
                                                  "Hi,\nI ordered two weeks ago (order 51410) and still nothing arrived.\nThanks, Anna\n\nOn Mon, 1 Sep 2026, Green Nest <shop@test.local> wrote:\n> your order has shipped\n> tracking soon"))
check("quoted history removed", message_text(m1) == "Hi,\nI ordered two weeks ago (order 51410) and still nothing arrived.\nThanks, Anna", repr(message_text(m1)))
check("italian quote header removed", clean_body("Ciao,\nè arrivato rotto.\nGrazie\n\nIl giorno lun 3 set 2026 alle 10:00 Green Nest <shop@x.it> ha scritto:\n> Ciao") == "Ciao,\nè arrivato rotto.\nGrazie")
check("signature cut at '-- '", clean_body("Can I change the address?\n-- \nMarco Verdi\nVia Roma 1") == "Can I change the address?")
html = email.message.EmailMessage()
html["From"], html["To"], html["Subject"] = "luca@example.com", "shop@test.local", "=?utf-8?q?Domanda_sui_prodotti_=E2=82=AC?="
html.set_content("plain fallback")
html.add_alternative("<html><body><p>Ciao, do the <b>bamboo toothbrushes</b> come in a 2-pack?</p><br>Luca</body></html>", subtype="html")
check("text/plain preferred over html", message_text(html) == "plain fallback", repr(message_text(html)))
only_html = email.message.EmailMessage()
only_html["From"], only_html["Subject"] = "luca@example.com", "x"
only_html.set_content("<html><body><p>Ciao, do the <b>bamboo toothbrushes</b> come in a 2-pack?</p><br>Luca</body></html>", subtype="html")
check("html-only mail turned into text", "bamboo toothbrushes come in a 2-pack?" in message_text(only_html) and "<" not in message_text(only_html), repr(message_text(only_html)))
att = email.message.EmailMessage()
att["From"], att["Subject"] = "sara@example.com", "broken item"
att.set_content("The jar arrived cracked, photo attached.")
att.add_attachment(b"\x89PNG....", maintype="image", subtype="png", filename="photo.png")
check("attachment ignored, text kept", message_text(att) == "The jar arrived cracked, photo attached.", repr(message_text(att)))

# ---- 2. fetch: machines filtered, humans kept, encoded headers decoded ----------------------------
ctl("RESET")
deliver("Anna Rossi <anna@example.com>", "Where is my order 51410?", "Hi,\nI ordered two weeks ago (order 51410) and still nothing arrived. Can you check?\nThanks, Anna\n\nOn Mon, Green Nest wrote:\n> shipped")
deliver("Newsletter <noreply@bigshop.com>", "50% OFF TODAY", "buy buy buy", {"List-Unsubscribe": "<mailto:x@y>"})
deliver("Marco <marco@example.com>", "Automatic reply: out of office", "I am away", {"Auto-Submitted": "auto-replied"})
deliver("Mail Delivery System <MAILER-DAEMON@mx.example.com>", "Undelivered Mail Returned to Sender", "bounce")
deliver("=?utf-8?q?J=C3=B6rg_M=C3=BCller?= <joerg@example.de>", "=?utf-8?q?R=C3=BCckgabe?=", "Hallo, ich möchte die Seife zurückgeben.")
deliver("shop@test.local", "Re: your question", "our own sent copy", {"Precedence": "bulk"})
ch = EmailChannel()
check("check() reports mailbox and sending ok", "mailbox ok" in ch.check() and "sending ok" in ch.check(), ch.check())
recs, skipped = ch.fetch_new(set())
names = [r["from"] for r in recs]
check("humans kept (Anna, Jörg)", names == ["Anna Rossi", "Jörg Müller"], str(names))
check("subject decoded", any(r["subject"] == "Rückgabe" for r in recs), str([r["subject"] for r in recs]))
why = sorted(w for _, w in skipped)
check("machines skipped (newsletter, auto-reply, bounce, bulk)", len(skipped) == 4, str(why))
check("skipped mails marked seen (not re-read)", ctl("COUNT").split()[1] == "0", ctl("COUNT"))
recs2, sk2 = ch.fetch_new({r["ref"] for r in recs})
check("second poll finds nothing new", recs2 == [] and sk2 == [])

# ---- 3. reply: threaded, quoted, Re: -------------------------------------------------------------
ok, info = ch.send(recs[0], "Hello Anna,\nI am checking with the carrier and will write back today.\nBest regards,\nCustomer care")
sent = json.loads(ctl("SENT"))
check("reply sent to the customer's address", ok and sent and sent[-1]["to"] == ["anna@example.com"], info)
check("subject gets 'Re:' once", sent[-1]["subject"] == "Re: Where is my order 51410?", sent[-1]["subject"])
check("threaded (In-Reply-To set)", bool(sent[-1]["in_reply_to"]))
check("original quoted under the reply", "> I ordered two weeks ago" in sent[-1]["body"], sent[-1]["body"][-200:])
check("Re: not doubled", ch.send(dict(recs[0], subject="Re: Where is my order 51410?"), "x")[0] and json.loads(ctl("SENT"))[-1]["subject"] == "Re: Where is my order 51410?")

# ---- 4. Facebook / Instagram ----------------------------------------------------------------------
mc = MetaChannel()
check("page check ok", mc.check().startswith("page ok"), mc.check())
mrecs, msk = mc.fetch_new(set())
check("only unanswered customer messages fetched (fb + ig)", sorted(r["ref"] for r in mrecs) == ["facebook:m_3", "instagram:ig_m1"], str([r["ref"] for r in mrecs]))
check("conversation we already answered is skipped", not any(r["addr"] == "U88" for r in mrecs))
check("sticker-only message skipped with a reason", any("no text" in w for _, w in msk), str(msk))
ok, info = mc.send(mrecs[0], "Hi Giulia, yes — the soap is vegan.")
check("messenger reply sent as RESPONSE to the right user", ok and META_SENT[-1]["recipient"]["id"] == "U77" and META_SENT[-1]["messaging_type"] == "RESPONSE", info)
os.environ["META_PAGE_TOKEN"] = "expired"
check("expired token explained in plain words", "expired" in MetaChannel().check().lower(), MetaChannel().check())
os.environ["META_PAGE_TOKEN"] = "TOKEN1234567890"

# ---- 5. secrets never leak -----------------------------------------------------------------------
check("password redacted from any text", "s3cretpassw0rd" not in config.redact("login failed for s3cretpassw0rd") and "TOKEN1234567890" not in config.redact("token TOKEN1234567890 bad"))

# ---- 6. the approve gate inside the Agent (no model: the template draft is enough) ------------------
ctl("RESET")
deliver("Anna Rossi <anna@example.com>", "Where is my order 51410?", "Hi, order 51410 still not here. Anna")
deliver("Luca <luca@example.com>", "2-pack?", "Do the toothbrushes come in a 2-pack?")
deliver("Sara <sara@example.com>", "address", "Can I change my delivery address?")
META_SENT.clear()
from agent import core   # noqa: E402


class FakeBot:
    def __init__(self, *a, **k):
        self.sent = []

    def get_me(self):
        return {"username": "bot", "id": 1}

    def send(self, chat_id, text, buttons=None, **k):
        self.sent.append((text, buttons))
        return {"message_id": len(self.sent)}

    def __getattr__(self, n):
        return lambda *a, **k: None


core.Bot = lambda *a, **k: FakeBot()
A = core.Agent()
A.owner_id = 1
A.planner.available = lambda: False          # force the template drafts: fast and deterministic
n = A.poll_channels()
drafts = [(t, b) for t, b in A.bot.sent if b]
check("3 mails + fb + ig → 5 drafts with buttons, nothing sent yet", n == 5 and len(drafts) == 5 and json.loads(ctl("SENT")) == [] and META_SENT == [],
      f"n={n} drafts={len(drafts)} sent={len(json.loads(ctl('SENT')))} meta={len(META_SENT)}")
check("button says 'Approve & send' for a real channel", any("Approve & send" in b[0][0][0] for _, b in drafts), str([b[0][0][0] for _, b in drafts]))
by_from = {t.split(" (")[0].replace("📨 ", ""): b[0][0][1].split(":")[-1] for t, b in drafts}
ids = [by_from["Anna Rossi"], by_from["Luca"], by_from["Sara"]]
ig_id = by_from.get("marta.k")


def tap(data):
    A.handle_callback({"id": "cq", "from": {"id": 1, "username": "owner"}, "data": data, "message": {"chat": {"id": 1}, "message_id": 9, "text": "draft"}})


tap(f"r:no:{ids[0]}")
check("Reject → nothing sent", json.loads(ctl("SENT")) == [])
tap(f"r:ok:{ids[1]}")
s = json.loads(ctl("SENT"))
check("Approve & send → mail really sent, threaded", len(s) == 1 and s[0]["to"] == ["luca@example.com"] and s[0]["in_reply_to"], str(s)[:200])
check("owner told it was sent", any(t.startswith("📤 Sent to Luca") for t, _ in A.bot.sent), str([t[:40] for t, _ in A.bot.sent[-3:]]))
tap(f"r:edit:{ids[2]}")
A.handle_update({"update_id": 1, "message": {"message_id": 3, "chat": {"id": 1}, "from": {"id": 1, "username": "owner"}, "text": "Hi Sara, yes — send me the new address and I will change it before it ships. Best, Carlo"}})
s = json.loads(ctl("SENT"))
check("Edit → the owner's own text is sent", len(s) == 2 and "send me the new address" in s[-1]["body"] and s[-1]["to"] == ["sara@example.com"], str(s[-1])[:200] if s else "nothing sent")
tap(f"r:ok:{ig_id}")
check("Approve & send on an Instagram DM → sent through the Graph API to the right user", len(META_SENT) == 1 and META_SENT[0]["recipient"]["id"] == "IGU5", str(META_SENT))
check("ledger: 5 received, 3 sent, 1 skipped", A.channels.state["received"] == 5 and A.channels.state["sent"] == 3 and A.channels.state["skipped"] == 1, str({k: A.channels.state[k] for k in ("received", "sent", "skipped")}))
n2 = A.poll_channels()
check("re-poll drafts nothing twice", n2 == 0, str(n2))
st = A.respond("/channels")
check("/channels shows the mailbox, the page and the counts", "shop@test.local" in st and "facebook page PAGE1 + instagram IG1" in st and "5 received" in st and "3 replies sent" in st, st)
check("/status lists the channels", "channels: e-mail shop@test.local" in A.status_text() and "facebook page PAGE1" in A.status_text(), A.status_text().splitlines()[5] if len(A.status_text().splitlines()) > 5 else A.status_text())
log_text = "".join(open(p).read() for p in __import__("glob").glob("state/test_channels/logs/*.jsonl"))
check("no secret in the logs", "s3cretpassw0rd" not in log_text and "TOKEN1234567890" not in log_text)

print(f"\nCHANNELS SCORE: {score}/{total}", flush=True)
srv.shutdown()
os._exit(0 if score == total else 1)
