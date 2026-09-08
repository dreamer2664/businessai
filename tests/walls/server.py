"""A tiny site with bot walls, for practising CAPTCHAs (milestone 15) — runs on 127.0.0.1 only.

  /easy/<name>   checkbox wall ("I'm not a robot") the first time, then the article
  /hard/<name>   a wall that never passes (like DataDome/Turnstile from a headless browser)
  /open/<name>   the article straight away
  /captcha       POST target of the checkbox form (remembers the client for the rest of the run)

Articles carry sentences that key_sentences() picks up for the topic "shipping days".
"""
import http.server, urllib.parse, threading

STATE = {"passed": set(), "hits": []}

ARTICLES = {
    "carrier": ("Carrier guide", "Shipping days explained: standard parcel shipping inside Italy takes 2 to 3 business days on average. "
                                 "Express shipping days are 1 to 2, and it typically costs 4 euros more per parcel. "
                                 "Most carriers count shipping days from the pickup scan, not from the order time."),
    "europe": ("Europe delivery", "Delivery to Germany or France usually means 4 to 6 shipping days with economy services. "
                                  "Priority shipping days across the EU average 2 to 4 and cost about 9 euros for a small parcel. "
                                  "Shipping days are longer in December because carriers are saturated."),
    "customs": ("Customs times", "Shipping days from China to Italy average 12 to 20 with ePacket-style services. "
                                 "Customs clearance adds 1 to 3 days and duties apply above 150 euros of goods value."),
}


def article(name):
    title, body = ARTICLES.get(name, ("Missing", "Nothing here."))
    return f"<html><head><title>{title}</title></head><body><h1>{title}</h1><p>{body}</p><p>Written by the shipping desk.</p></body></html>"


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, html, code=200):
        data = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        parts = [p for p in u.path.split("/") if p]
        STATE["hits"].append(u.path)
        if len(parts) == 2 and parts[0] == "easy":
            if self.client_address[0] not in STATE["passed"]:
                return self._send("<html><head><title>Verify you are human</title></head><body><h1>Security check</h1>"
                                  "<p>Please verify you are human before continuing.</p>"
                                  f"<form method=post action='/captcha'><input type=hidden name=next value='{u.path}'>"
                                  "<label><input type=checkbox name=human> I'm not a robot</label> <button type=submit>Continue</button></form></body></html>")
            return self._send(article(parts[1]))
        if len(parts) == 2 and parts[0] == "hard":
            return self._send("<html><head><title>Just a moment...</title></head><body><h1>Checking your browser</h1>"
                              "<p>Please complete the CAPTCHA to continue. Verify you are human.</p>"
                              "<div class='captcha' id='px-captcha'>Press and hold is not available.</div></body></html>", 403)
        if len(parts) == 2 and parts[0] == "open":
            return self._send(article(parts[1]))
        if u.path == "/":
            return self._send("<html><head><title>Walls</title></head><body><h1>Walls</h1>" +
                              "".join(f"<p><a href='/{k}/{n}'>{k} {n}</a></p>" for k in ("easy", "hard", "open") for n in ARTICLES) + "</body></html>")
        return self._send("<html><body>not found</body></html>", 404)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        f = dict(urllib.parse.parse_qsl(self.rfile.read(n).decode(errors="replace")))
        if u.path == "/captcha":
            if f.get("human"):
                STATE["passed"].add(self.client_address[0])
            nxt = f.get("next") or "/"
            self.send_response(303)
            self.send_header("Location", nxt)
            self.end_headers()
            return
        return self._send("<html><body>not found</body></html>", 404)


def serve(port):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    return srv


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8089
    print("walls on", port)
    serve(port).serve_forever()
