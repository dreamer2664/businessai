#!/usr/bin/env python3
"""A chat page in your browser to talk to the builder — no Telegram, no chat app.

    python3 scripts/talk.py            → opens http://localhost:8787 (a small chat window)

You type at the bottom; your messages are saved to owner/inbox.md in the GitHub repo.
The builder's answers (builder/replies.md) appear in the same window, refreshed every 20 s.
Nothing else is needed: the token in .secrets/env does the GitHub part.
"""
import base64
import html
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("BAI_TALK_PORT", "8787"))


def _env():
    env = dict(os.environ)
    f = ROOT / ".secrets" / "env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


ENV = _env()
OWNER = ENV.get("GH_OWNER", "dreamer2664")
REPO = ENV.get("GH_REPO", "businessai")
TOKEN = ENV.get("GITHUB_TOKEN", "")
API = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/"
LOCK = threading.Lock()


def _req(path, method="GET", body=None, raw=False):
    url = API + path + ("?ref=main" if method == "GET" else "")
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github.raw" if raw else "application/vnd.github+json")
    req.add_header("User-Agent", "businessai-talk")
    data = json.dumps(body).encode() if body is not None else None
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            out = r.read()
            return out.decode() if raw else json.loads(out)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise RuntimeError(f"GitHub said {e.code}: {e.read()[:200].decode(errors='replace')}")


def _lines(text, who):
    out = []
    for line in (text or "").splitlines():
        m = re.match(r"^- (\d{4}-\d\d-\d\d \d\d:\d\d) \((owner|builder)\): ?(.*)$", line)
        if m:
            out.append({"t": m.group(1), "who": m.group(2), "text": m.group(3)})
        elif out and line.startswith("  "):
            out[-1]["text"] += "\n" + line.strip()
    return out


def conversation():
    mine = _lines(_req("owner/inbox.md", raw=True), "owner")
    theirs = _lines(_req("builder/replies.md", raw=True), "builder")
    return sorted(mine + theirs, key=lambda x: x["t"])


def send(msg):
    with LOCK:
        for _ in range(3):
            cur = _req("owner/inbox.md")
            old = base64.b64decode(cur["content"]).decode() if cur else "# Notes from the owner to the builder\n\n"
            stamp = time.strftime("%Y-%m-%d %H:%M")
            new = old.rstrip("\n") + f"\n- {stamp} (owner): {msg.strip()}\n"
            body = {"message": f"owner note {stamp}", "content": base64.b64encode(new.encode()).decode()}
            if cur:
                body["sha"] = cur["sha"]
            try:
                _req("owner/inbox.md", method="PUT", body=body)
                return True
            except RuntimeError as e:
                if "409" not in str(e):
                    raise
                time.sleep(1)
    return False


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Business AI — talk to the builder</title>
<style>
body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#f3f4f6;color:#111}
header{background:#111827;color:#fff;padding:12px 18px;font-weight:600}
header small{opacity:.7;font-weight:400;margin-left:10px}
#log{padding:16px;max-width:860px;margin:0 auto;padding-bottom:110px}
.m{margin:10px 0;padding:10px 14px;border-radius:12px;max-width:80%;white-space:pre-wrap;line-height:1.4;box-shadow:0 1px 2px rgba(0,0,0,.08)}
.owner{background:#dbeafe;margin-left:auto}
.builder{background:#fff}
.t{font-size:11px;color:#6b7280;margin-bottom:4px}
form{position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #e5e7eb;padding:10px;display:flex;gap:8px}
textarea{flex:1;font:inherit;padding:10px;border:1px solid #d1d5db;border-radius:8px;resize:none;height:56px}
button{font:inherit;padding:0 18px;border:0;border-radius:8px;background:#2563eb;color:#fff;cursor:pointer}
#st{font-size:12px;color:#6b7280;text-align:center;padding:6px}
</style></head><body>
<header>Business AI — talk to the builder <small>your words → GitHub → the builder answers here (refresh every 20 s)</small></header>
<div id="log"></div><div id="st"></div>
<form id="f"><textarea id="x" placeholder="Write here… (Enter to send, Shift+Enter for a new line)"></textarea><button>Send</button></form>
<script>
const log=document.getElementById('log'),st=document.getElementById('st'),x=document.getElementById('x');
let last='';
async function load(){try{const r=await fetch('/api/conv');const j=await r.json();const h=j.map(m=>`<div class="m ${m.who}"><div class="t">${m.who==='owner'?'you':'builder'} · ${m.t}</div>${esc(m.text)}</div>`).join('');
if(h!==last){log.innerHTML=h;last=h;window.scrollTo(0,document.body.scrollHeight);}st.textContent='updated '+new Date().toLocaleTimeString();}catch(e){st.textContent='cannot reach GitHub right now — retrying';}}
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])).replace(/(https?:\\/\\/\\S+)/g,'<a href="$1" target="_blank">$1</a>')}
document.getElementById('f').onsubmit=async e=>{e.preventDefault();const v=x.value.trim();if(!v)return;x.value='';st.textContent='sending…';
const r=await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:v})});st.textContent=r.ok?'sent ✅ — the builder reads it on its next turn':'send failed — try again';load();};
x.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();document.getElementById('f').requestSubmit();}});
load();setInterval(load,20000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/conv"):
            try:
                self._send(200, json.dumps(conversation()), "application/json")
            except Exception as e:
                self._send(502, json.dumps({"error": str(e)[:200]}), "application/json")
            return
        self._send(200, PAGE)

    def do_POST(self):
        if self.path.startswith("/api/send"):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                text = json.loads(self.rfile.read(n) or b"{}").get("text", "").strip()
                ok = bool(text) and send(text)
                self._send(200 if ok else 500, json.dumps({"ok": ok}), "application/json")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)[:200]}), "application/json")
            return
        self._send(404, "no")


def main():
    if not TOKEN:
        print("No GITHUB_TOKEN in .secrets/env — I can't reach the repo from here.")
        sys.exit(1)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    url = f"http://localhost:{PORT}"
    print(f"Talk to the builder here: {url}   (Ctrl-C to close)")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
