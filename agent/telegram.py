"""Minimal Telegram Bot API client (standard library only, no dependencies).

Only the handful of calls the agent needs: getMe, getUpdates (long polling),
sendMessage (with optional tap-buttons), answerCallbackQuery,
editMessageReplyMarkup, sendDocument.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config


class TelegramError(Exception):
    pass


class Bot:
    def __init__(self, token=None, timeout=35):
        self.token = token or config.TELEGRAM_BOT_TOKEN
        if not self.token:
            raise TelegramError("TELEGRAM_BOT_TOKEN missing (put it in .secrets/env)")
        self.base = f"https://api.telegram.org/bot{self.token}/"
        self.timeout = timeout

    # ---- low level -----------------------------------------------------
    def call(self, method, _timeout=None, **params):
        data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                for k, v in params.items() if v is not None}
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(self.base + method, data=body)
        try:
            with urllib.request.urlopen(req, timeout=_timeout or self.timeout) as r:
                out = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                out = json.loads(e.read().decode())
            except Exception:
                out = {"ok": False, "description": f"HTTP {e.code}"}
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise TelegramError(f"network: {config.redact(str(e))}")
        if not out.get("ok"):
            raise TelegramError(f"{method}: {out.get('error_code')} {out.get('description')}")
        return out["result"]

    # ---- helpers -------------------------------------------------------
    def get_me(self):
        return self.call("getMe", _timeout=15)

    def get_updates(self, offset=None, timeout=30):
        return self.call("getUpdates", _timeout=timeout + 10, offset=offset, timeout=timeout,
                         allowed_updates=["message", "callback_query"])

    def send(self, chat_id, text, buttons=None, parse_mode=None, reply_to=None):
        """buttons: list of rows, each a list of (label, data) tuples -> inline keyboard."""
        text = config.redact(text)
        markup = None
        if buttons:
            markup = {"inline_keyboard": [[{"text": lab, "callback_data": str(dat)[:64]}
                                           for lab, dat in row] for row in buttons]}
        # Telegram caps messages at 4096 chars; split long ones
        chunks = [text[i:i + 4000] for i in range(0, max(len(text), 1), 4000)]
        last = None
        for i, c in enumerate(chunks):
            last = self.call("sendMessage", chat_id=chat_id, text=c, parse_mode=parse_mode,
                             reply_markup=markup if i == len(chunks) - 1 else None,
                             reply_to_message_id=reply_to, disable_web_page_preview=True)
        return last

    def answer_callback(self, callback_id, text=None):
        try:
            return self.call("answerCallbackQuery", _timeout=10, callback_query_id=callback_id, text=text)
        except TelegramError:
            return None

    def clear_buttons(self, chat_id, message_id, new_text=None):
        try:
            if new_text is not None:
                return self.call("editMessageText", chat_id=chat_id, message_id=message_id,
                                 text=config.redact(new_text), reply_markup={"inline_keyboard": []})
            return self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                             reply_markup={"inline_keyboard": []})
        except TelegramError:
            return None

    def send_document(self, chat_id, path, caption=None):
        """Upload a file (multipart) — used for reports/screenshots later."""
        boundary = f"----bai{int(time.time() * 1000)}"
        with open(path, "rb") as f:
            payload = f.read()
        name = str(path).split("/")[-1]
        parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n"]
        if caption:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{config.redact(caption)}\r\n")
        head = "".join(parts).encode()
        head += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{name}\"\r\n"
                 f"Content-Type: application/octet-stream\r\n\r\n").encode()
        body = head + payload + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.base + "sendDocument", data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read().decode())
        if not out.get("ok"):
            raise TelegramError(f"sendDocument: {out.get('description')}")
        return out["result"]
