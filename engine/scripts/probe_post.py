import os, sys, shutil, json, threading
sys.path.insert(0, "/home/user/businessai")
STATE = "/tmp/bai_probe_post"; shutil.rmtree(STATE, ignore_errors=True)
os.environ["BAI_STATE"] = STATE; os.environ["BAI_STORE_PORT"] = "8192"; os.environ.pop("DISPLAY", None)
# fake Meta Graph API
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
calls = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = self.rfile.read(n)
        calls.append((self.path.split("?")[0], self.headers.get("Content-Type", "")[:30], len(body), b"source" in body))
        out = json.dumps({"id": "123_456", "post_id": "123_456"}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
srv = ThreadingHTTPServer(("127.0.0.1", 8191), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["META_PAGE_ID"] = "123"; os.environ["META_PAGE_TOKEN"] = "tok"; os.environ["META_API"] = "http://127.0.0.1:8191/v21.0"
from agent import core
class FakeBot:
    def __init__(self): self.sent = []; self.docs = []
    def get_me(self): return {"username": "fake"}
    def send(self, chat, text, buttons=None, **k): self.sent.append((text, buttons)); return {"message_id": len(self.sent)}
    def send_document(self, chat, path, caption="", **k): self.docs.append((path, caption, k.get("field")))
    def __getattr__(self, n): return lambda *a, **k: None
core.Bot = lambda *a, **k: FakeBot()
A = core.Agent(); A.owner_id = 1
A.planner.available = lambda: False; A.planner.installed = lambda: False
A.tasks.run = lambda c: "fake report"; A.log = lambda *a, **k: None
for _ in range(2): A.store.simulate_day()
import time
print(A.respond("make a banner for facebook saying: Free shipping over 39 euro")[:80])
r = A.respond("post it"); print(r)
for _ in range(60):
    if A.posts: break
    time.sleep(0.5)
pid = next(iter(A.posts)); d = A.posts[pid]
print("draft has photo:", bool(d.get("photo")), "| banner line:", "with the banner I made" in A.bot.sent[-1][0])
A.handle_callback({"id": "1", "from": {"id": 1, "username": "dreamer2664"}, "message": {"chat": {"id": 1}, "message_id": 5, "text": "x"}, "data": f"p:ok:{pid}"})
print("→", A.bot.sent[-1][0][:120])
print("graph calls:", calls)
