"""Social media rehearsal (milestone 18): learn a posting interface *before* go-live, by doing it on a stage.

Real platforms lock robot log-ins and every public word needs the owner's approval — so the rehearsal happens on
Postly (tests/social/server.py), a small fake network the agent serves on its own machine, and on any *staging* URL the
owner gives it. What gets learned (and scored):
  1. log in with its own account (Accounts) and find the composer ("New post", "What's new?", "Publish");
  2. post a draft that already passed Social's checks, with a photo when there is one (upload through the file input);
  3. read the page back: did the post appear? what did the platform say (limit errors)? → adapt (shorten, cut hashtags);
  4. read the comments under the post, draft replies with Inbox (the same reply gate as customer messages);
  5. keep a note per platform in state/social_map.json: which labels the composer/publish/photo/comment controls had,
     the character limit it hit, how long a publish took — so the real thing is a repeat, not a first attempt.

Nothing here touches a real network: `post()` refuses any host that is not local or explicitly given by the owner as a stage.
"""
import json
import re
import time
import urllib.parse

from . import config

MAP_FILE = config.STATE_DIR / "social_map.json"
STAGE_HOSTS = ("127.0.0.1", "localhost", "0.0.0.0")
COMPOSER_WORDS = re.compile(r"what'?s (new|happening|on your mind)|write (a )?(post|caption)|new post|create post|compose|share something|start a post|caption|text", re.I)
PUBLISH_WORDS = re.compile(r"^(publish|post|share|tweet|send|pubblica|condividi)\b", re.I)
NEWPOST_WORDS = re.compile(r"new post|create|compose|post something|write|nuovo post|\+", re.I)
PHOTO_WORDS = re.compile(r"photo|image|picture|media|upload|foto|immagine", re.I)
COMMENT_WORDS = re.compile(r"reply|comment|risposta|commenta|write a reply|add a comment", re.I)


def _load_map():
    try:
        return json.loads(MAP_FILE.read_text())
    except Exception:
        return {}


def _save_map(m):
    MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    MAP_FILE.write_text(json.dumps(m, ensure_ascii=False, indent=1))


class Rehearsal:
    def __init__(self, tasks, accounts=None, social=None, inbox=None, log=None, viewer=None, eyes=None, extra_stages=()):
        self.T = tasks
        self.accounts = accounts
        self.social = social
        self.inbox = inbox
        self.log = log or (lambda kind, **f: None)
        self.viewer = viewer
        self.eyes = eyes
        self.stages = set(extra_stages)
        self.map = _load_map()

    # ---- safety ------------------------------------------------------------------------------------------------
    def is_stage(self, url):
        host = urllib.parse.urlparse(url).hostname or ""
        return host in STAGE_HOSTS or host in self.stages or any(host.endswith("." + s) for s in self.stages)

    # ---- the rehearsal ---------------------------------------------------------------------------------------------
    def post(self, url, text, image=None, reply_to_comments=True, file_for_owner=True):
        """Post `text` on the stage at `url` (+ photo). Returns a dict report: ok, post_url, learned, comments, replies, note.
        Safe to call from any thread (browser work is moved to the hands thread)."""
        if not self.is_stage(url):
            return {"ok": False, "note": f"{url} is not a rehearsal stage — real platforms only through the approved-post flow"}
        return self.T.on_hands(self._post, url, text, image, reply_to_comments, file_for_owner, timeout=600)

    def reply(self, post_url, text):
        """Post an approved reply under a rehearsal post (the same move as answering a comment for real). True when it shows up."""
        if not self.is_stage(post_url):
            return False
        return self.T.on_hands(self._reply, post_url, text, timeout=180)

    def _post(self, url, text, image, reply_to_comments, file_for_owner):
        t0 = time.time()
        site = urllib.parse.urlparse(url).netloc
        rep = {"ok": False, "site": site, "post_url": "", "learned": {}, "comments": [], "replies": [], "note": "", "attempts": 0}
        with self.T._session() as b:
            if self.viewer:
                self.viewer.task = f"rehearsing a post on {site}"
            # 1) logged in?
            if self.accounts:
                ok, note = self.accounts.ensure_account(b, url, why="rehearsing social posting", allow_signup=True, quiet=True)
                if not ok:
                    rep["note"] = f"could not log in: {note}"
                    return rep
            b.open(url)
            b.read()
            # 2) composer
            if not self._open_composer(b):
                rep["note"] = "found no composer (New post / What's new?)"
                return rep
            attempt_text = text
            for attempt in range(3):
                rep["attempts"] = attempt + 1
                box = self._composer_box(b)
                if not box:
                    rep["note"] = "composer box not found"
                    return rep
                b.type(box["n"], attempt_text)
                self.map.setdefault(site, {})["composer"] = box.get("label") or "textbox"
                typed = self._value(b, box["n"])
                if typed is not None and len(typed) < len(attempt_text) - 2:            # silently cut by the composer (maxlength) → learn the limit
                    limit = len(typed)
                    self.map[site]["char_limit"] = limit
                    rep["learned"].setdefault("errors", []).append(f"the composer silently cuts at {limit} characters")
                    self.log("rehearsal_cut", site=site, limit=limit)
                    attempt_text = self._adapt(attempt_text, f"too long: {len(attempt_text)}/{limit}", site)
                    b.type(box["n"], attempt_text)
                if image:
                    self._attach(b, image, site)
                pub = self._publish_button(b)
                if not pub:
                    rep["note"] = "no Publish button"
                    return rep
                self.map[site]["publish"] = pub.get("label")
                t1 = time.time()
                b.click(pub["n"])
                time.sleep(0.8)
                page = b.extract_text()
                err = self._error_text(page)
                if err:
                    self.log("rehearsal_refused", site=site, error=err[:80], attempt=attempt + 1)
                    rep["learned"].setdefault("errors", []).append(err[:120])
                    attempt_text = self._adapt(attempt_text, err, site)
                    b.open(url)
                    b.read()
                    if not self._open_composer(b):
                        break
                    continue
                if attempt_text[:40] in page or urllib.parse.urlparse(b.page.url).path.startswith("/p/"):
                    rep["ok"] = True
                    rep["post_url"] = b.page.url
                    rep["text"] = attempt_text
                    self.map[site]["publish_seconds"] = round(time.time() - t1, 1)
                    break
                rep["note"] = "published but could not see the post afterwards"
                break
            if not rep["ok"]:
                rep["note"] = rep["note"] or "the platform kept refusing the post"
                _save_map(self.map)
                return rep
            # 4) comments under the post
            if reply_to_comments:
                time.sleep(2.5)                                   # the fake buyer comments after ~1.5 s; real platforms: come back later
                b.open(rep["post_url"])
                b.read()
                rep["comments"] = self._comments(b)
                for c in rep["comments"][:3]:
                    if self.inbox:
                        if file_for_owner:
                            rec = self.inbox.add("social", c["who"], c["text"], subject=f"comment on {site}", extra={"post_url": rep["post_url"]})
                        else:
                            rec = {"id": "rehearsal", "channel": "social", "from": c["who"], "text": c["text"], "subject": ""}
                        d = self.inbox.draft(rec)
                        rep["replies"].append({"to": c["who"], "comment": c["text"], "draft": d.get("text", ""), "kind": d.get("kind"), "checks": d.get("checks", []), "inbox_id": rec["id"]})
                self.map[site]["comment_box"] = next((it.get("label") for it in b.items if it["role"] == "textbox" and COMMENT_WORDS.search(it.get("label") or "")), None)
        self.T._release_page()
        self.map[site]["last_rehearsal"] = time.strftime("%Y-%m-%d %H:%M")
        self.map[site]["rehearsals"] = self.map[site].get("rehearsals", 0) + 1
        _save_map(self.map)
        rep["learned"].update({k: v for k, v in self.map[site].items()})
        rep["seconds"] = round(time.time() - t0, 1)
        self.log("rehearsal_done", site=site, ok=rep["ok"], attempts=rep["attempts"], comments=len(rep["comments"]))
        return rep

    # ---- pieces ------------------------------------------------------------------------------------------------------
    def _open_composer(self, b):
        if self._composer_box(b):
            return True
        for it in b.items:
            if it["role"] in ("link", "button") and NEWPOST_WORDS.search(it.get("label") or "") and not re.search(r"log ?in|sign ?up", it.get("label") or "", re.I):
                try:
                    b.click(it["n"])
                    b.read()
                except Exception:
                    continue
                if self._composer_box(b):
                    return True
        return False

    def _composer_box(self, b):
        b.read()
        boxes = [it for it in b.items if it["role"] == "textbox" and not re.search(r"search|e-?mail|password|cerca", it.get("label") or "", re.I)]
        for it in boxes:
            if COMPOSER_WORDS.search(it.get("label") or ""):
                return it
        return boxes[0] if boxes and b.page.evaluate("document.querySelectorAll('textarea').length") else None

    @staticmethod
    def _value(b, n):
        try:
            return b.page.evaluate("n => { const e = document.querySelector(`[data-bai='${n}']`); return e ? (e.value ?? null) : null; }", int(n))
        except Exception:
            return None

    def _reply(self, post_url, text):
        with self.T._session() as b:
            if self.accounts:                                     # the browser may have been closed since the post → log in again
                ok, note = self.accounts.ensure_account(b, post_url, why="answering a comment", allow_signup=False, quiet=True)
                if not ok:
                    self.log("rehearsal_reply_login_failed", note=note[:80])
                    return False
            b.open(post_url)
            b.read()
            box = next((it for it in b.items if it["role"] == "textbox" and COMMENT_WORDS.search(it.get("label") or "")), None)
            if not box:
                box = next((it for it in b.items if it["role"] == "textbox" and not re.search(r"search|e-?mail|password", it.get("label") or "", re.I)), None)
            if not box:
                return False
            b.type(box["n"], text)
            btn = next((it for it in b.items if it["role"] == "button" and COMMENT_WORDS.search(it.get("label") or "")), None) or self._publish_button(b)
            if not btn:
                return False
            b.click(btn["n"])
            time.sleep(0.5)
            ok = text[:40] in b.extract_text()
        self.T._release_page()
        self.log("rehearsal_reply", ok=ok)
        return ok

    def _publish_button(self, b):
        b.read()
        for it in b.items:
            if it["role"] == "button" and PUBLISH_WORDS.search((it.get("label") or "").strip()):
                return it
        return next((it for it in b.items if it["role"] == "button" and not re.search(r"log|cancel|close|menu", it.get("label") or "", re.I)), None)

    def _attach(self, b, image, site):
        try:
            inp = b.page.locator("input[type=file]").first
            if inp.count() == 0:
                return False
            inp.set_input_files(str(image))
            self.map.setdefault(site, {})["photo"] = "file input"
            return True
        except Exception as e:
            self.log("rehearsal_photo_failed", error=str(e)[:80])
            return False

    @staticmethod
    def _error_text(page):
        m = re.search(r"(too long[^.\n]*|too many hashtags[^.\n]*|write something first[^.\n]*|troppo lung[^.\n]*|limit[^.\n]*exceeded[^.\n]*)", page, re.I)
        return m.group(1).strip() if m else ""

    def _adapt(self, text, err, site):
        m = re.search(r"(\d+)\s*/\s*(\d+)", err)
        if "hashtag" in err.lower():
            mx = re.search(r"max (\d+)", err)
            keep = int(mx.group(1)) if mx else 3
            tags = re.findall(r"#\w+", text)
            for t in tags[keep:]:
                text = text.replace(" " + t, "").replace(t, "")
            self.map.setdefault(site, {})["max_hashtags"] = keep
            return text.strip()
        if m or "too long" in err.lower():
            limit = int(m.group(2)) if m else max(60, len(text) - 80)
            self.map.setdefault(site, {})["char_limit"] = limit
            body, _, tags = text.rpartition("\n")
            if not body:
                body, tags = text, ""
            while len(body) + (len(tags) + 1 if tags else 0) > limit and " " in body:
                body = body.rsplit(" ", 1)[0].rstrip(",;:")
            text = (body.rstrip(".") + ".") if body else text[:limit]
            if tags and len(text) + 1 + len(tags) <= limit:
                text += "\n" + tags
            return text[:limit]
        return text[: max(60, int(len(text) * 0.8))]

    def _comments(self, b):
        out = []
        try:
            rows = b.page.evaluate("Array.from(document.querySelectorAll('.comment, [class*=comment], li[id*=comment]')).map(e => e.innerText.trim()).slice(0, 12)")
        except Exception:
            rows = []
        for r in rows:
            r = re.sub(r"\s+", " ", r)
            m = re.match(r"^@?([\w.]+)\s+(.{3,})$", r)
            if m:
                out.append({"who": m.group(1), "text": m.group(2)[:300]})
        return out

    # ---- reporting ----------------------------------------------------------------------------------------------------
    def report_text(self, rep):
        if not rep.get("ok"):
            return f"🎭 Rehearsal on {rep.get('site', '?')} failed: {rep.get('note', '')}"
        lines = [f"🎭 Rehearsal on {rep['site']}: posted in {rep['attempts']} attempt{'s' if rep['attempts'] != 1 else ''} ({rep.get('seconds', 0)}s)"]
        if rep["learned"].get("errors"):
            lines.append("  learned the hard way: " + "; ".join(rep["learned"]["errors"][:2]))
        if rep["learned"].get("char_limit") or rep["learned"].get("max_hashtags"):
            lines.append(f"  limits noted: {rep['learned'].get('char_limit', '?')} characters, {rep['learned'].get('max_hashtags', '?')} hashtags")
        if rep.get("comments"):
            lines.append(f"  {len(rep['comments'])} comment(s) under it; reply drafts ready: " + " | ".join(f"@{r['to']}: “{r['draft'][:70]}”" for r in rep["replies"][:2]))
        return "\n".join(lines)

    def map_text(self):
        if not self.map:
            return "No platform rehearsed yet. Say 'rehearse posting' and I'll practise on my stage."
        out = []
        for site, m in self.map.items():
            out.append(f"• {site}: {m.get('rehearsals', 0)} rehearsal(s), composer '{m.get('composer')}', publish '{m.get('publish')}', "
                       f"photo {'yes' if m.get('photo') else 'not found'}, limit {m.get('char_limit', 'not hit')} chars, {m.get('max_hashtags', '?')} tags, last {m.get('last_rehearsal', '-')}")
        return "\n".join(out)
