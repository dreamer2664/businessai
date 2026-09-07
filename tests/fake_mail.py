"""A tiny local mail server for tests: IMAP (read) + SMTP (send), one mailbox, in memory. No TLS, no internet.

    python3 tests/fake_mail.py [imap_port] [smtp_port]      (defaults 1143 / 1025)

Only the IMAP verbs agent/channels.py uses are implemented: LOGIN, SELECT, UID SEARCH UNSEEN, UID FETCH (BODY.PEEK[]),
UID STORE +FLAGS (\\Seen), LOGOUT. Anything the shop sends by SMTP is kept in `sent` and can be read back over a control
socket (port smtp_port+1): "SENT" → JSON list; "DELIVER <json>" → puts a mail in the mailbox; "RESET".
"""
import asyncio
import email
import logging
import warnings

warnings.filterwarnings("ignore")
logging.getLogger("mail.log").setLevel(logging.CRITICAL)
import email.message
import email.utils
import json
import socketserver
import sys
import threading
import time

from aiosmtpd.controller import Controller

USER, PASSWORD = "shop@test.local", "secret"


class Mailbox:
    def __init__(self):
        self.msgs = {}          # uid -> {"raw": bytes, "seen": bool}
        self.next_uid = 1
        self.sent = []
        self.lock = threading.Lock()

    def deliver(self, raw: bytes):
        with self.lock:
            uid = self.next_uid
            self.next_uid += 1
            self.msgs[uid] = {"raw": raw, "seen": False}
            return uid

    def reset(self):
        with self.lock:
            self.msgs.clear()
            self.sent.clear()
            self.next_uid = 1


BOX = Mailbox()


def make_mail(frm, to, subject, body, headers=None):
    m = email.message.EmailMessage()
    m["From"], m["To"], m["Subject"] = frm, to, subject
    m["Date"] = email.utils.formatdate(localtime=True)
    m["Message-ID"] = email.utils.make_msgid(domain="test.local")
    for k, v in (headers or {}).items():
        m[k] = v
    m.set_content(body)
    return m.as_bytes()


# ---- IMAP -----------------------------------------------------------------------------------
class IMAPHandler(socketserver.StreamRequestHandler):
    def send(self, line):
        self.wfile.write((line + "\r\n").encode())

    def handle(self):
        self.send("* OK fake IMAP ready")
        selected = False
        while True:
            line = self.rfile.readline()
            if not line:
                return
            try:
                text = line.decode(errors="replace").strip()
            except Exception:
                return
            parts = text.split(" ", 2)
            if len(parts) < 2:
                continue
            tag, cmd = parts[0], parts[1].upper()
            rest = parts[2] if len(parts) > 2 else ""
            if cmd == "CAPABILITY":
                self.send("* CAPABILITY IMAP4rev1 AUTH=PLAIN")
                self.send(f"{tag} OK done")
            elif cmd == "LOGIN":
                u, p = [x.strip('"') for x in rest.split(" ", 1)]
                self.send(f"{tag} OK logged in" if (u, p) == (USER, PASSWORD) else f"{tag} NO wrong password")
            elif cmd in ("SELECT", "EXAMINE"):
                selected = True
                self.send(f"* {len(BOX.msgs)} EXISTS")
                self.send("* FLAGS (\\Seen)")
                self.send(f"{tag} OK [READ-WRITE] selected")
            elif cmd == "UID":
                sub = rest.split(" ", 1)
                verb = sub[0].upper()
                arg = sub[1] if len(sub) > 1 else ""
                if verb == "SEARCH":
                    with BOX.lock:
                        if "UNSEEN" in arg.upper():
                            uids = [u for u, m in BOX.msgs.items() if not m["seen"]]
                        else:
                            uids = list(BOX.msgs)
                    self.send("* SEARCH " + " ".join(str(u) for u in uids))
                    self.send(f"{tag} OK search done")
                elif verb == "FETCH":
                    uid = int(arg.split()[0])
                    m = BOX.msgs.get(uid)
                    if m:
                        raw = m["raw"]
                        self.wfile.write(f"* {uid} FETCH (UID {uid} BODY[] {{{len(raw)}}}\r\n".encode() + raw + b")\r\n")
                    self.send(f"{tag} OK fetch done")
                elif verb == "STORE":
                    uid = int(arg.split()[0])
                    with BOX.lock:
                        if uid in BOX.msgs and "SEEN" in arg.upper():
                            BOX.msgs[uid]["seen"] = "+FLAGS" in arg.upper()
                    self.send(f"* {uid} FETCH (UID {uid} FLAGS (\\Seen))")
                    self.send(f"{tag} OK store done")
                else:
                    self.send(f"{tag} BAD unknown uid command")
            elif cmd == "NOOP":
                self.send(f"{tag} OK")
            elif cmd == "LOGOUT":
                self.send("* BYE")
                self.send(f"{tag} OK bye")
                return
            else:
                self.send(f"{tag} BAD not implemented")


class ThreadedTCP(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


# ---- SMTP -----------------------------------------------------------------------------------
class Authenticator:
    def __call__(self, server, session, envelope, mechanism, auth_data):
        from aiosmtpd.smtp import AuthResult
        ok = getattr(auth_data, "login", b"").decode(errors="replace") == USER and getattr(auth_data, "password", b"").decode(errors="replace") == PASSWORD
        return AuthResult(success=ok, handled=True)


class SMTPSink:
    async def handle_DATA(self, server, session, envelope):
        with BOX.lock:
            BOX.sent.append({"from": envelope.mail_from, "to": envelope.rcpt_tos, "raw": envelope.content.decode(errors="replace"), "t": time.time()})
        return "250 Message accepted"


# ---- control --------------------------------------------------------------------------------
class ControlHandler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline().decode(errors="replace").strip()
        if line == "SENT":
            with BOX.lock:
                out = []
                for s in BOX.sent:
                    m = email.message_from_string(s["raw"])
                    out.append({"to": s["to"], "subject": m.get("Subject", ""), "in_reply_to": m.get("In-Reply-To", ""),
                                "body": m.get_payload(decode=True).decode(errors="replace") if not m.is_multipart() else m.get_payload()[0].get_payload(decode=True).decode(errors="replace")})
            self.wfile.write(json.dumps(out).encode() + b"\n")
        elif line.startswith("DELIVER "):
            try:
                d = json.loads(line[8:])
            except Exception as e:
                self.wfile.write(f"ERR {e}\n".encode())
                return
            uid = BOX.deliver(make_mail(d["from"], d.get("to", USER), d.get("subject", ""), d.get("body", ""), d.get("headers")))
            self.wfile.write(f"{uid}\n".encode())
        elif line == "RESET":
            BOX.reset()
            self.wfile.write(b"ok\n")
        elif line == "COUNT":
            self.wfile.write(f"{len(BOX.msgs)} {sum(1 for m in BOX.msgs.values() if not m['seen'])} {len(BOX.sent)}\n".encode())


def serve(imap_port=1143, smtp_port=1025):
    imap = ThreadedTCP(("127.0.0.1", imap_port), IMAPHandler)
    threading.Thread(target=imap.serve_forever, daemon=True).start()
    ctl = ThreadedTCP(("127.0.0.1", smtp_port + 1), ControlHandler)
    threading.Thread(target=ctl.serve_forever, daemon=True).start()
    smtp = Controller(SMTPSink(), hostname="127.0.0.1", port=smtp_port, authenticator=Authenticator(), auth_required=True, auth_require_tls=False)
    smtp.start()
    return imap, smtp, ctl


if __name__ == "__main__":
    ip = int(sys.argv[1]) if len(sys.argv) > 1 else 1143
    sp = int(sys.argv[2]) if len(sys.argv) > 2 else 1025
    serve(ip, sp)
    print(f"fake mail: imap 127.0.0.1:{ip}  smtp 127.0.0.1:{sp}  control 127.0.0.1:{sp + 1}  user {USER} / {PASSWORD}", flush=True)
    while True:
        time.sleep(3600)
