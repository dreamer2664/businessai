"""A tiny fake site for scoring sign-ups: / → Sign up link → form (email, password, name, terms) → code page → welcome.
Optionally a checkbox CAPTCHA before the form (?captcha=1). Codes are 'mailed' to a list the scorer reads."""
import http.server, urllib.parse, threading, random, json
MAILBOX = []          # (to, subject, body)
STATE = {"users": {}, "codes": {}, "captcha_ok": set()}
PAGE = "<html><head><title>{t}</title></head><body style='font-family:sans-serif;margin:30px'>{b}</body></html>"
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, body, title="FakeMarket"):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(PAGE.format(t=title, b=body).encode())
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path == "/":
            self._send("<h1>FakeMarket</h1><p>Reviews are for members.</p><a href='/signup'>Sign up</a> · <a href='/login'>Log in</a>")
        elif u.path == "/signup":
            if self.server.captcha and self.client_address[0] not in STATE["captcha_ok"]:
                self._send("<h1>Security check</h1><p>Please verify you are human.</p><form method=post action='/captcha'><label><input type=checkbox name=human> I'm not a robot</label><button type=submit>Continue</button></form>", "Verify you are human")
            else:
                self._send("<h1>Create your account</h1><form method=post action='/signup'>"
                           "<p><label>Email address <input type=email name=email></label></p><p><label>Password <input type=password name=password></label></p>"
                           "<p><label>First name <input name=first></label> <label>Last name <input name=last></label></p>"
                           "<p><label><input type=checkbox name=terms> I agree to the terms and privacy policy</label></p>"
                           "<p><label><input type=checkbox name=news> Send me marketing offers</label></p><button type=submit>Create account</button></form>")
        elif u.path == "/verify":
            self._send("<h1>Check your email</h1><p>We sent a verification code to your inbox. Enter the code below.</p><form method=post action='/verify'><label>Verification code <input name=code inputmode=numeric></label><button type=submit>Verify</button></form>")
        elif u.path == "/welcome":
            self._send("<h1>Welcome, Business!</h1><p>Your account is active. You can now read all reviews.</p><a href='/logout'>Log out</a>")
        elif u.path == "/login":
            self._send("<h1>Log in</h1><form method=post action='/login'><p><label>Email address <input type=email name=email></label></p><p><label>Password <input type=password name=password></label></p><button type=submit>Log in</button></form>")
        else:
            self.send_response(404); self.end_headers()
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); f = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode()).items()}
        u = urllib.parse.urlparse(self.path)
        if u.path == "/captcha":
            if f.get("human"): STATE["captcha_ok"].add(self.client_address[0])
            self.send_response(303); self.send_header("Location", "/signup"); self.end_headers()
        elif u.path == "/signup":
            if not (f.get("email") and f.get("password") and f.get("terms")):
                return self._send("<h1>Create your account</h1><p style='color:red'>Error: email, password and terms are required. Try again.</p>")
            code = f"{random.randint(0, 999999):06d}"; STATE["codes"][f["email"]] = code; STATE["users"][f["email"]] = f
            MAILBOX.append((f["email"], "Your FakeMarket verification code", f"Hi {f.get('first','')}, your code is {code}. It expires in 10 minutes."))
            self.send_response(303); self.send_header("Location", "/verify"); self.end_headers()
        elif u.path == "/verify":
            ok = any(f.get("code") == c for c in STATE["codes"].values())
            if ok:
                self.send_response(303); self.send_header("Location", "/welcome"); self.end_headers()
            else:
                self._send("<h1>Check your email</h1><p style='color:red'>Invalid code. Try again.</p><form method=post action='/verify'><label>Verification code <input name=code></label><button type=submit>Verify</button></form>")
        elif u.path == "/login":
            usr = STATE["users"].get(f.get("email"))
            if usr and usr["password"] == f.get("password"):
                self.send_response(303); self.send_header("Location", "/welcome"); self.end_headers()
            else:
                self._send("<h1>Log in</h1><p style='color:red'>Incorrect email or password.</p>")
def serve(port, captcha=False):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H); srv.captcha = captcha
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
