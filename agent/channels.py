"""Real customer channels (milestone 10) — the same draft → Approve / Edit / Reject flow as the practice inbox, but the messages
come from real places and the approved reply goes back the same way:

   e-mail     — any mailbox (Gmail, Outlook, Aruba, …) through IMAP (read) and SMTP (send). Nothing to install.
   facebook   — Facebook Page messages (Messenger) through the official Meta Graph API, polled (no public server needed).
   instagram  — Instagram DMs of the professional account linked to that Page, same API.

Rules that never change:
   * reading is automatic; SENDING happens only after the owner tapped "Approve & send" (or typed his own version);
   * auto-replies, bounces, newsletters and our own messages are never answered;
   * every message is remembered by its id (state/channels.json) so a re-poll never drafts twice;
   * passwords/tokens live in .secrets/env only and are redacted from every log and message.

Settings (.secrets/env):
   MAIL_USER=shop@example.com  MAIL_PASSWORD=<app password>  MAIL_IMAP_HOST=imap.gmail.com  MAIL_SMTP_HOST=smtp.gmail.com
   optional: MAIL_IMAP_PORT=993  MAIL_SMTP_PORT=587  MAIL_FOLDER=INBOX  MAIL_FROM_NAME=Green Nest  MAIL_IMAP_SSL=1  MAIL_SMTP_TLS=1
   META_PAGE_ID=1234567890  META_PAGE_TOKEN=EAAB…  optional: META_IG_ID=<instagram business account id>  META_API=https://graph.facebook.com/v21.0
   CHANNELS_INTERVAL=180  (seconds between polls)
"""
import datetime as _dt
import email
import email.utils
import html as _html
import imaplib
import json
import os
import re
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.header import decode_header, make_header
from email.message import EmailMessage

from . import config

STATE = config.STATE_DIR / "channels.json"
REAL = ("email", "facebook", "instagram")

# senders / headers that are machines, not customers
NOREPLY_RE = re.compile(r"(no-?reply|do-?not-?reply|mailer-daemon|postmaster|notifications?@|newsletter|bounce|auto-?mail)", re.I)
QUOTE_START_RE = re.compile(r"^(On .{5,120} wrote:|Il giorno .{5,120} ha scritto:|Am .{5,120} schrieb .*:|Le .{5,120} a écrit :|El .{5,120} escribió:|"
                            r"-{2,}\s*(Original|Forwarded) Message\s*-{2,}|_{5,}|From: .+|Da: .+|Von: .+|De: .+)$", re.I)
SIG_RE = re.compile(r"^(-- ?|__+|Sent from my .+|Inviato da .+|Envoyé de .+)$", re.I)


def _now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _dec(value):
    """Decode an RFC 2047 header ('=?utf-8?q?…') into plain text."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return str(value).strip()


def html_to_text(raw):
    raw = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = _html.unescape(raw)
    raw = re.sub(r"[ \t\xa0]+", " ", raw)
    return re.sub(r"\n\s*\n+", "\n\n", raw).strip()


def clean_body(text, limit=2500):
    """The customer's own words: quoted history, signatures and blank runs removed."""
    out = []
    for line in (text or "").replace("\r", "").split("\n"):
        s = line.strip()
        if QUOTE_START_RE.match(s) or SIG_RE.match(s):
            break
        if s.startswith(">"):
            continue
        out.append(line.rstrip())
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return body[:limit]


def message_text(msg):
    """Best text of an email.message.Message: text/plain first, else HTML turned into text."""
    plain, htmlp = None, None
    for part in msg.walk():
        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition", "").startswith("attachment"):
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
        except Exception:
            continue
        if part.get_content_type() == "text/plain" and plain is None:
            plain = text
        elif part.get_content_type() == "text/html" and htmlp is None:
            htmlp = text
    text = plain if plain and plain.strip() else html_to_text(htmlp or "")
    if re.search(r"<(html|body|div|p|br)\b", text or "", re.I):           # HTML wrongly labelled as plain text
        text = html_to_text(text)
    return clean_body(text)


def is_machine_mail(msg, our_address=""):
    """Auto-replies, bounces, list mail and no-reply senders: never answered."""
    frm = _dec(msg.get("From", ""))
    addr = (email.utils.parseaddr(frm)[1] or "").lower()
    if NOREPLY_RE.search(addr) or NOREPLY_RE.search(frm):
        return "no-reply sender"
    if (msg.get("Auto-Submitted", "") or "no").lower() != "no":
        return "auto-submitted"
    if (msg.get("Precedence", "") or "").lower() in ("bulk", "list", "junk"):
        return "bulk/list mail"
    if msg.get("List-Unsubscribe") or msg.get("List-Id"):
        return "mailing list"
    if re.match(r"(?i)^(auto(matic)?[ -]?reply|out of (the )?office|automatische antwort|risposta automatica|delivery status|undeliverable)", _dec(msg.get("Subject", ""))):
        return "auto-reply subject"
    if msg.get_content_type() in ("multipart/report",):
        return "delivery report"
    return ""


class EmailChannel:
    name = "email"

    def __init__(self, log=None):
        self.log = log or (lambda *a, **k: None)
        e = os.environ.get
        self.user = e("MAIL_USER", "")
        self.password = e("MAIL_PASSWORD", "")
        self.imap_host = e("MAIL_IMAP_HOST", "")
        self.smtp_host = e("MAIL_SMTP_HOST", "")
        self.imap_port = int(e("MAIL_IMAP_PORT", "993") or 993)
        self.smtp_port = int(e("MAIL_SMTP_PORT", "587") or 587)
        self.folder = e("MAIL_FOLDER", "INBOX")
        self.from_name = e("MAIL_FROM_NAME", "")
        self.imap_ssl = e("MAIL_IMAP_SSL", "1") != "0"
        self.smtp_tls = e("MAIL_SMTP_TLS", "1") != "0"
        self.mark_seen = e("MAIL_MARK_SEEN", "1") != "0"
        self.last_error = ""

    def configured(self):
        return bool(self.user and self.password and self.imap_host and self.smtp_host)

    def describe(self):
        return f"e-mail {self.user} (imap {self.imap_host}, smtp {self.smtp_host})" if self.configured() else "e-mail: not set up (MAIL_USER, MAIL_PASSWORD, MAIL_IMAP_HOST, MAIL_SMTP_HOST in .secrets/env)"

    def _connect(self):
        if self.imap_ssl:
            return imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=30)
        return imaplib.IMAP4(self.imap_host, self.imap_port, timeout=30)

    def fetch_new(self, known_ids, limit=20):
        """Unseen mails as records [{ref, from, from_name, addr, subject, text, message_id, date}] — machines skipped, known ids skipped."""
        out, skipped = [], []
        M = self._connect()
        try:
            M.login(self.user, self.password)
            typ, _ = M.select(self.folder)
            if typ != "OK":
                raise RuntimeError(f"cannot open folder {self.folder}")
            typ, data = M.uid("search", None, "UNSEEN")
            uids = (data[0] or b"").split()[-limit:] if typ == "OK" else []
            for uid in uids:
                uid_s = uid.decode() if isinstance(uid, bytes) else str(uid)
                ref = f"email:{self.user}:{uid_s}"
                typ, parts = M.uid("fetch", uid, "(BODY.PEEK[])")
                raw = next((p[1] for p in parts if isinstance(p, tuple) and len(p) > 1), None) if typ == "OK" else None
                if not raw:
                    continue
                msg = email.message_from_bytes(raw)
                mid = (msg.get("Message-ID") or "").strip()
                key = f"email:{mid}" if mid else ref
                if key in known_ids or ref in known_ids:
                    continue
                why = is_machine_mail(msg, self.user)
                if why:
                    skipped.append((key, why))
                    if self.mark_seen:
                        M.uid("store", uid, "+FLAGS", "(\\Seen)")
                    continue
                name, addr = email.utils.parseaddr(_dec(msg.get("From", "")))
                text = message_text(msg)
                subject = _dec(msg.get("Subject", ""))
                if not text and not subject:
                    skipped.append((key, "empty"))
                    continue
                out.append({"ref": key, "uid": uid_s, "from": name or addr, "from_name": name, "addr": addr, "subject": subject, "text": text,
                            "message_id": mid, "references": (msg.get("References") or "").strip(), "date": msg.get("Date", "")})
                if self.mark_seen:
                    M.uid("store", uid, "+FLAGS", "(\\Seen)")
        finally:
            try:
                M.logout()
            except Exception:
                pass
        return out, skipped

    def send(self, rec, text):
        """Reply to `rec` (an inbox record with channel=email). Returns (ok, info). Called ONLY after the owner's approval."""
        to = rec.get("addr") or email.utils.parseaddr(rec.get("from", ""))[1]
        if not to:
            return False, "no e-mail address to reply to"
        msg = EmailMessage()
        msg["From"] = email.utils.formataddr((self.from_name, self.user)) if self.from_name else self.user
        msg["To"] = email.utils.formataddr((rec.get("from_name") or "", to)) if rec.get("from_name") else to
        subj = rec.get("subject") or "your message"
        msg["Subject"] = subj if re.match(r"(?i)^(re|aw|r|ris|sv|vs)\s*:", subj) else f"Re: {subj}"
        if rec.get("message_id"):
            msg["In-Reply-To"] = rec["message_id"]
            msg["References"] = (rec.get("references", "") + " " + rec["message_id"]).strip()
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid(domain=(self.user.split("@")[-1] or None))
        quoted = "\n".join("> " + l for l in (rec.get("text") or "").splitlines()[:12])
        body = text.rstrip() + (f"\n\n\n{rec.get('from', 'You')} wrote:\n{quoted}" if quoted else "")
        msg.set_content(body, charset="utf-8")
        try:
            if self.smtp_port == 465:
                S = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30, context=ssl.create_default_context())
            else:
                S = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            with S:
                S.ehlo()
                if self.smtp_tls and self.smtp_port != 465 and S.has_extn("starttls"):
                    S.starttls(context=ssl.create_default_context())
                    S.ehlo()
                if S.has_extn("auth"):
                    S.login(self.user, self.password)
                S.send_message(msg)
        except Exception as e:
            self.last_error = config.redact(str(e))[:200]
            return False, self.last_error
        return True, f"sent to {to}"

    def check(self):
        """Connect once to both servers; a plain sentence about what works."""
        res = []
        try:
            M = self._connect()
            M.login(self.user, self.password)
            typ, data = M.select(self.folder, readonly=True)
            typ2, unseen = M.uid("search", None, "UNSEEN")
            n = len((unseen[0] or b"").split()) if typ2 == "OK" else "?"
            M.logout()
            res.append(f"mailbox ok — {n} unread in {self.folder}")
        except Exception as e:
            res.append(f"mailbox FAILED: {config.redact(str(e))[:120]}")
        try:
            if self.smtp_port == 465:
                S = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30)
            else:
                S = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            with S:
                S.ehlo()
                if self.smtp_tls and self.smtp_port != 465 and S.has_extn("starttls"):
                    S.starttls(context=ssl.create_default_context())
                    S.ehlo()
                if S.has_extn("auth"):
                    S.login(self.user, self.password)
            res.append("sending ok")
        except Exception as e:
            res.append(f"sending FAILED: {config.redact(str(e))[:120]}")
        return "; ".join(res)


class MetaChannel:
    """Facebook Page inbox + Instagram DMs through the Graph API (official). Polled — needs no public server.
    Needs a Page access token with pages_messaging (+ instagram_manage_messages for Instagram)."""
    name = "meta"

    def __init__(self, log=None):
        self.log = log or (lambda *a, **k: None)
        e = os.environ.get
        self.page_id = e("META_PAGE_ID", "")
        self.token = e("META_PAGE_TOKEN", "")
        self.ig_id = e("META_IG_ID", "")
        self.api = e("META_API", "https://graph.facebook.com/v21.0").rstrip("/")
        self.last_error = ""

    def configured(self):
        return bool(self.page_id and self.token)

    def describe(self):
        if not self.configured():
            return "facebook/instagram: not set up (META_PAGE_ID and META_PAGE_TOKEN in .secrets/env)"
        return f"facebook page {self.page_id}" + (f" + instagram {self.ig_id}" if self.ig_id else "")

    def _get(self, path, **params):
        params["access_token"] = self.token
        url = f"{self.api}/{path}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
            return json.loads(r.read().decode())

    def _post(self, path, body):
        url = f"{self.api}/{path}?access_token={urllib.parse.quote(self.token)}"
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    def fetch_new(self, known_ids, limit=25):
        """Latest customer messages from the Page's conversations (Messenger and, when linked, Instagram)."""
        out, skipped = [], []
        platforms = [("facebook", {})] + ([("instagram", {"platform": "instagram"})] if self.ig_id else [])
        ours = {self.page_id, self.ig_id}
        for channel, extra in platforms:
            try:
                d = self._get(f"{self.page_id}/conversations", fields="participants,updated_time,messages.limit(5){message,from,created_time,id}",
                              limit=limit, **extra)
            except urllib.error.HTTPError as e:
                self.last_error = config.redact(self._explain(e))[:200]
                self.log("channel_error", channel=channel, error=self.last_error)
                continue
            except Exception as e:
                self.last_error = config.redact(str(e))[:200]
                self.log("channel_error", channel=channel, error=self.last_error)
                continue
            for conv in d.get("data", []):
                msgs = (conv.get("messages") or {}).get("data") or []
                # the newest message from the customer, unless we (the page) already answered after it
                for m in msgs:                                  # newest first
                    frm = m.get("from") or {}
                    if frm.get("id") in ours:
                        break                                   # our reply is the latest → nothing to answer
                    key = f"{channel}:{m.get('id')}"
                    if key in known_ids:
                        break
                    if not (m.get("message") or "").strip():
                        skipped.append((key, "no text (attachment/sticker)"))
                        break
                    out.append({"ref": key, "from": frm.get("name") or frm.get("username") or frm.get("id", "customer"), "addr": frm.get("id", ""),
                                "subject": "", "text": m["message"].strip()[:2500], "conversation": conv.get("id", ""), "channel": channel,
                                "date": m.get("created_time", "")})
                    break
        return out, skipped

    def send(self, rec, text):
        """Reply inside the 24-hour customer-service window (messaging_type RESPONSE). Only after the owner's approval."""
        psid = rec.get("addr")
        if not psid:
            return False, "no recipient id"
        body = {"recipient": {"id": psid}, "messaging_type": "RESPONSE", "message": {"text": text[:1900]}}
        try:
            d = self._post(f"{self.page_id}/messages", body)
        except urllib.error.HTTPError as e:
            self.last_error = config.redact(self._explain(e))[:200]
            return False, self.last_error
        except Exception as e:
            self.last_error = config.redact(str(e))[:200]
            return False, self.last_error
        return True, f"sent ({d.get('message_id', 'ok')})"

    @staticmethod
    def _explain(e):
        """Graph API errors carry a JSON body with the real reason (expired token, missing permission)."""
        try:
            return json.loads(e.read().decode()).get("error", {}).get("message", "") or str(e)
        except Exception:
            return str(e)

    def check(self):
        try:
            d = self._get(self.page_id, fields="name")
            return f"page ok — {d.get('name', self.page_id)}"
        except urllib.error.HTTPError as e:
            return f"page FAILED: {config.redact(self._explain(e))[:140]}"
        except Exception as e:
            return f"page FAILED: {config.redact(str(e))[:120]}"


class Channels:
    """All configured channels; keeps the seen-ids ledger and hands new messages to the Inbox."""

    def __init__(self, inbox=None, log=None):
        self.inbox = inbox
        self.log = log or (lambda *a, **k: None)
        self.email = EmailChannel(log=self.log)
        self.meta = MetaChannel(log=self.log)
        self.interval = int(os.environ.get("CHANNELS_INTERVAL", "180") or 180)
        self.last_poll = 0.0
        self.lock = threading.Lock()
        self.state = self._load()

    def _load(self):
        try:
            return json.loads(STATE.read_text())
        except Exception:
            return {"seen": [], "polls": 0, "received": 0, "sent": 0, "skipped": 0, "last": ""}

    def _save(self):
        self.state["seen"] = self.state["seen"][-5000:]
        config.ensure_dirs()
        STATE.write_text(json.dumps(self.state))

    def active(self):
        return [c for c in (self.email, self.meta) if c.configured()]

    def configured(self):
        return bool(self.active())

    def due(self):
        return self.configured() and time.time() - self.last_poll >= self.interval

    def poll(self):
        """Fetch new customer messages from every configured channel and add them to the inbox. Returns the new inbox records."""
        if not self.lock.acquire(blocking=False):
            return []
        try:
            self.last_poll = time.time()
            known = set(self.state["seen"])
            new = []
            for ch in self.active():
                try:
                    recs, skipped = ch.fetch_new(known)
                except Exception as e:
                    self.log("channel_error", channel=ch.name, error=config.redact(str(e))[:200])
                    continue
                for key, why in skipped:
                    known.add(key)
                    self.state["seen"].append(key)
                    self.state["skipped"] += 1
                    self.log("channel_skipped", channel=ch.name, why=why)
                for r in recs:
                    known.add(r["ref"])
                    self.state["seen"].append(r["ref"])
                    self.state["received"] += 1
                    channel = r.get("channel") or ch.name
                    if self.inbox:
                        rec = self.inbox.add(channel, r["from"], r["text"], subject=r.get("subject", ""),
                                             extra={k: r[k] for k in ("addr", "from_name", "message_id", "references", "conversation", "date") if r.get(k)})
                        new.append(rec)
                    self.log("channel_message", channel=channel, sender=r["from"][:60], subject=(r.get("subject") or "")[:80])
            self.state["polls"] += 1
            self.state["last"] = _now()
            self._save()
            return new
        finally:
            self.lock.release()

    def send(self, rec, text):
        """Deliver an APPROVED reply through the record's channel. (ok, info)."""
        ch = rec.get("channel")
        if ch == "email":
            ok, info = self.email.send(rec, text)
        elif ch in ("facebook", "instagram"):
            ok, info = self.meta.send(rec, text)
        else:
            return False, f"'{ch}' is not a sending channel"
        if ok:
            self.state["sent"] += 1
            self._save()
        self.log("channel_sent" if ok else "channel_send_failed", channel=ch, info=info[:120])
        return ok, info

    def status(self):
        if not self.configured():
            return ("No real channels yet. To connect your shop e-mail add MAIL_USER, MAIL_PASSWORD, MAIL_IMAP_HOST and MAIL_SMTP_HOST to "
                    ".secrets/env (docs/CHANNELS.md explains it step by step); Facebook/Instagram need META_PAGE_ID and META_PAGE_TOKEN.")
        st = self.state
        last = st.get("last") or "never"
        lines = [c.describe() for c in self.active()]
        lines.append(f"checked every {self.interval // 60} min · last check {last[:16].replace('T', ' ')} · {st['received']} received, "
                     f"{st['sent']} replies sent (each one approved by you), {st['skipped']} skipped (auto-replies, newsletters, no-reply senders)")
        return "\n".join(lines)

    def check(self):
        if not self.configured():
            return self.status()
        return "\n".join(f"{c.name}: {c.check()}" for c in self.active())
