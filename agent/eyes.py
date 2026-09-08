"""Eyes — the agent looks at pictures of screens (milestone 6).

Two layers, both free and local:
  1. OCR (tesseract, ~0.6 s): every word on the screen with its exact pixel box → "where is the 'Add to cart' button?"
     gives coordinates the hands can click. Optional: without tesseract the agent still sees, it just can't point.
  2. A tiny vision-language model (LFM2-VL-450M, 210 MB + 100 MB projector, ~550 MB RAM, ~4 s per question on a
     768-px screenshot) served by the same llama-server binary as the thinking model, on its own port, started on
     first look and stopped after EYES_IDLE seconds → "what is this page? is there a login wall? what does the error say?"

Frugal rules: screenshots are downscaled to ≤ 768 px wide JPEG before the model sees them (~30 KB, ~260 tokens);
the eyes never run at the same time as a big thinking call on a 2 GB machine (Tasks.low_mem: the thinking model is
stopped first); nothing is uploaded anywhere.

Public API (all return plain Python, never raise on model trouble):
  look(image, question)      → str answer
  describe(image)            → dict(kind, title, summary, warnings)   kind: page|login|captcha|error|dialog|desktop|other
  read(image)                → list of words [{text, x, y, w, h, conf}] (screen pixels)
  find(image, text)          → [(cx, cy, matched_text)] centres of the best OCR matches, best first
  compare(before, after)     → str: what changed (used after a click)
Images: bytes (PNG/JPEG), a path, or a PIL.Image.
"""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request

from . import config

EYES_DIR = config.ROOT / "release" / "eyes"
MODEL_FILE = EYES_DIR / "model.gguf"
MMPROJ_FILE = EYES_DIR / "mmproj.gguf"
SERVER_BIN = config.ROOT / "release" / "llm" / "llama-server"
PORT = int(os.environ.get("BAI_EYES_PORT", "8093"))
IDLE_STOP = int(os.environ.get("BAI_EYES_IDLE", "300"))
THREADS = os.environ.get("BAI_LLM_THREADS") or str(max(1, (os.cpu_count() or 2) - 1))
MAX_W = 768

MODEL_URLS = {
    "model.gguf": "https://huggingface.co/LiquidAI/LFM2-VL-450M-GGUF/resolve/main/LFM2-VL-450M-Q4_0.gguf",
    "mmproj.gguf": "https://huggingface.co/LiquidAI/LFM2-VL-450M-GGUF/resolve/main/mmproj-LFM2-VL-450M-Q8_0.gguf",
}

DESCRIBE_PROMPT = ("Look at this screenshot. Answer in JSON only: {\"kind\": one of page|login|captcha|error|dialog|desktop|other, "
                   "\"title\": the page or app title in a few words, \"summary\": one plain sentence saying what is on the screen, "
                   "\"warnings\": a list with any of: login wall, captcha, error message, popup, payment step, empty page}")


def _to_pil(image):
    from PIL import Image
    if hasattr(image, "size") and hasattr(image, "save"):
        return image.convert("RGB")
    if isinstance(image, (bytes, bytearray)):
        return Image.open(io.BytesIO(image)).convert("RGB")
    return Image.open(str(image)).convert("RGB")


def _small_jpeg(im, max_w=MAX_W):
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


class Eyes:
    def __init__(self, log=None, planner=None):
        self.log = log or (lambda kind, **f: None)
        self.planner = planner          # so the eyes can ask the thinking model to step aside on small machines
        self._proc = None
        self._lock = threading.Lock()
        self.last_used = 0
        self.looks = 0
        self.last_error = ""
        self.ocr = bool(shutil.which("tesseract"))

    # ---- install / lifecycle ------------------------------------------------------
    def installed(self):
        return MODEL_FILE.exists() and MMPROJ_FILE.exists() and SERVER_BIN.exists()

    def install(self, progress=None):
        """Download the vision model (~310 MB, once). Returns a plain sentence."""
        EYES_DIR.mkdir(parents=True, exist_ok=True)
        for name, url in MODEL_URLS.items():
            dst = EYES_DIR / name
            if dst.exists() and dst.stat().st_size > 1_000_000:
                continue
            tmp = dst.with_suffix(".part")
            try:
                with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                    done = 0
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if progress and done % (50 << 20) < (1 << 20):
                            progress(f"{name}: {done >> 20} MB")
                os.replace(tmp, dst)
            except Exception as e:
                tmp.unlink(missing_ok=True)
                return f"could not download {name}: {str(e)[:120]}"
        return f"eyes installed: {sum(p.stat().st_size for p in EYES_DIR.glob('*.gguf')) >> 20} MB in release/eyes"

    def _ping(self, timeout=2):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=timeout) as r:
                return r.status == 200
        except Exception:
            return False

    def _start(self):
        if self._proc and self._proc.poll() is None:
            return True
        if not self.installed():
            self.last_error = "not installed — /eyes install"
            return False
        if self.planner is not None and hasattr(self.planner, "stop") and self._mem_available_mb() < 1500:
            self.planner.stop()                 # 2 GB machines: one model at a time
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        logf = open(config.LOG_DIR / "eyes.log", "ab")
        try:
            self._proc = subprocess.Popen([str(SERVER_BIN), "-m", str(MODEL_FILE), "--mmproj", str(MMPROJ_FILE), "--host", "127.0.0.1",
                                           "--port", str(PORT), "-c", "4096", "-np", "1", "-t", THREADS, "--no-warmup"],
                                          stdout=logf, stderr=subprocess.STDOUT)
        except OSError as e:
            self.last_error = f"cannot start the eyes: {e}"
            return False
        t0 = time.time()
        while time.time() - t0 < 120:
            if self._ping():
                self.log("eyes_started", ms=int((time.time() - t0) * 1000))
                self.last_error = ""
                return True
            if self._proc.poll() is not None:
                break
            time.sleep(0.5)
        try:
            tail = (config.LOG_DIR / "eyes.log").read_text(errors="replace")[-400:]
        except Exception:
            tail = ""
        self.last_error = "eyes server exited: " + " | ".join(l for l in tail.splitlines() if l.strip())[-200:]
        self.log("eyes_start_failed", error=self.last_error)
        self._proc = None
        return False

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(10)
            except Exception:
                self._proc.kill()
            self.log("eyes_stopped")
        self._proc = None

    def tick(self):
        if self._proc and not self._lock.locked() and time.time() - self.last_used > IDLE_STOP:
            self.stop()

    @staticmethod
    def _mem_available_mb():
        try:
            for line in open("/proc/meminfo"):
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
        except Exception:
            pass
        return 99999

    def describe_status(self):
        if not self.installed():
            return "eyes: not installed (/eyes install, 310 MB)"
        state = "awake" if self._ping() else "asleep"
        return f"eyes: vision model {(MODEL_FILE.stat().st_size + MMPROJ_FILE.stat().st_size) >> 20} MB, {state}, {self.looks} looks" + \
               ("" if self.ocr else " · no OCR (sudo apt install tesseract-ocr for exact clicking)")

    # ---- looking ---------------------------------------------------------------------
    def look(self, image, question, max_tokens=120):
        """Ask the vision model one question about the image. Returns '' on failure (never raises)."""
        with self._lock:
            if not (self._ping() or self._start()):
                return ""
            try:
                jpeg = _small_jpeg(_to_pil(image))
                b64 = base64.b64encode(jpeg).decode()
                body = {"messages": [{"role": "user", "content": [
                            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
                            {"type": "text", "text": question}]}],
                        "max_tokens": max_tokens, "temperature": 0, "cache_prompt": False}
                req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", data=json.dumps(body).encode(),
                                             headers={"Content-Type": "application/json"})
                t0 = time.time()
                with urllib.request.urlopen(req, timeout=240) as r:
                    j = json.loads(r.read())
                self.looks += 1
                self.last_used = time.time()
                ans = (j["choices"][0]["message"]["content"] or "").strip()
                self.log("eyes_look", ms=int((time.time() - t0) * 1000), q=question[:60], a=ans[:80])
                return ans
            except Exception as e:
                self.last_error = str(e)[:160]
                self.log("eyes_failed", error=self.last_error)
                return ""

    def describe(self, image):
        """What is on the screen? kind + title + one-sentence summary + hard-evidence warnings (OCR beats the model here)."""
        summary = self.look(image, "In one plain sentence: what is shown on this screen?", max_tokens=60)
        title = self.look(image, "What is the name of this website, app or page? Answer with the name only.", max_tokens=16)
        title = re.sub(r"^(the )?(name of )?(this |the )?(website|app|page|store) (is|appears to be)\s*", "", title, flags=re.I).strip(" .\"'")
        kind_raw = self.look(image, "Is this a normal web page, a login form, a captcha test, an error message, a popup dialog, "
                                    "or a computer desktop? Answer with one of: page, login, captcha, error, dialog, desktop.", max_tokens=8).lower()
        kind = next((k for k in ("captcha", "login", "error", "dialog", "desktop", "page") if k in kind_raw), "other")
        out = {"kind": kind, "title": title[:80], "summary": summary[:300], "warnings": []}
        words = " ".join(w["text"].lower() for w in self.read(image)) if self.ocr else (summary + " " + kind_raw).lower()
        if re.search(r"\b(captcha|not a robot|verify you are human|unusual traffic|are you human)\b", words):
            out["warnings"].append("captcha"); out["kind"] = "captcha"
        elif re.search(r"\b(password|forgot (your )?password|(sign|log) in to (continue|see|view|watch)|create an account to)\b", words):
            out["warnings"].append("login wall"); out["kind"] = "login" if out["kind"] in ("page", "other", "dialog") else out["kind"]
        elif out["kind"] == "login":
            out["kind"] = "page"                                        # the model saw a 'Sign in' button, not a wall
        if re.search(r"\b(checkout|place order|pay now|card number|cvv|complete purchase)\b", words):
            out["warnings"].append("payment step")
        if re.search(r"\b(error|went wrong|not found|404|503|unavailable)\b", words):
            out["warnings"].append("error message")
        out["warnings"] = list(dict.fromkeys(out["warnings"]))
        return out

    def compare(self, before, after):
        """What changed between two screenshots (after a click)? OCR diff first, model sentence second."""
        if self.ocr:
            a = {w["text"] for w in self.read(before) if len(w["text"]) > 2}
            b = {w["text"] for w in self.read(after) if len(w["text"]) > 2}
            gone, new = sorted(a - b)[:12], sorted(b - a)[:12]
            if not gone and not new:
                return "nothing visible changed"
            return ("new on screen: " + " ".join(new) if new else "") + (" · gone: " + " ".join(gone) if gone else "")
        return self.look(after, "In one sentence: what does this screen show now?") or "could not compare"

    # ---- OCR -------------------------------------------------------------------------------
    def _ocr_pass(self, im, tag, scale=1):
        buf = io.BytesIO()
        im.save(buf, "PNG")
        r = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "11", "tsv"], input=buf.getvalue(), capture_output=True, timeout=60)
        words = []
        for line in r.stdout.decode(errors="replace").splitlines()[1:]:
            p = line.split("\t")
            if len(p) == 12 and p[11].strip() and float(p[10]) >= 30:
                words.append({"text": p[11].strip(), "x": int(p[6]) // scale, "y": int(p[7]) // scale, "w": int(p[8]) // scale,
                              "h": int(p[9]) // scale, "conf": float(p[10]), "line": (tag, int(p[2]), int(p[3]), int(p[4]))})
        return words

    @staticmethod
    def _light_on_colour(im):
        """Second OCR view for light labels on coloured buttons/bars. Per pixel: how much brighter than its surroundings
        (25 px window) is it? Light text on a darker button stands out strongly; the page background does not.
        The result is grey-level (edges preserved), then upscaled 2x for tesseract."""
        from PIL import ImageFilter, Image
        g = im.convert("L")
        try:
            import numpy as np
        except ImportError:
            return Image.eval(g, lambda v: 255 - v)
        a = np.array(g).astype(np.int16)
        mean = np.array(g.filter(ImageFilter.BoxBlur(12))).astype(np.int16)
        diff = np.clip(a - mean, 0, 255)                                  # brighter-than-surroundings amount
        diff = np.where(mean < 200, diff, 0)                              # only inside non-white regions
        out = (255 - np.clip(diff * 3, 0, 255)).astype("uint8")           # strong light-on-dark → black ink
        img = Image.fromarray(out)
        return img.resize((img.width * 2, img.height * 2), Image.LANCZOS)

    @staticmethod
    def _without_borders(im):
        """Third OCR view: erase long thin lines (button borders, input boxes, table rules) — tesseract drops words
        that sit inside a tight frame ('Pay now' in a bordered button)."""
        from PIL import Image, ImageFilter
        g = im.convert("L")
        try:
            import numpy as np
        except ImportError:
            return g
        a = np.array(g)
        dark = a < 200
        def runs(mask, axis, minlen):
            out = np.zeros_like(mask)
            m = mask if axis == 1 else mask.T
            o = out if axis == 1 else out.T
            for i in range(m.shape[0]):
                row = m[i]
                if row.sum() < minlen:
                    continue
                d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
                for s0, e0 in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
                    if e0 - s0 >= minlen:
                        o[i, s0:e0] = 1
            return out
        lines = runs(dark, 1, 40) | runs(dark, 0, 25)
        lines = np.array(Image.fromarray((lines * 255).astype("uint8")).filter(ImageFilter.MaxFilter(3))) > 0
        a = a.copy()
        a[lines] = 255
        return Image.fromarray(a)

    def read(self, image):
        """Words with pixel boxes: [{text,x,y,w,h,conf}] in the coordinates of the given image.
        Two passes — normal and colour-inverted — so white text on coloured buttons and bars is read too."""
        if not self.ocr:
            return []
        key = id(image) if not isinstance(image, (bytes, bytearray, str)) else hash(image if isinstance(image, str) else bytes(image[:4096]) + bytes(len(image)))
        if getattr(self, "_ocr_cache_key", None) == key:
            return self._ocr_cache
        try:
            im = _to_pil(image)
            words = self._ocr_pass(im, 0)
            def overlaps(w):
                for v in words:
                    if abs(v["x"] - w["x"]) < max(8, v["w"] // 2) and abs(v["y"] - w["y"]) < max(6, v["h"] // 2):
                        return True
                return False
            words += [w for w in self._ocr_pass(self._light_on_colour(im), 1, scale=2) if not overlaps(w)]     # white labels on colour
            words += [w for w in self._ocr_pass(self._without_borders(im), 2) if not overlaps(w)]     # labels inside boxes
            self._ocr_cache_key, self._ocr_cache = key, words
            return words
        except Exception as e:
            self.log("ocr_failed", error=str(e)[:100])
            return []

    def lines(self, image):
        """OCR grouped into text lines: [{text, x, y, w, h}] — for reading a screen top to bottom."""
        groups = {}
        for w in self.read(image):
            groups.setdefault(w["line"], []).append(w)
        out = []
        for key in sorted(groups, key=lambda k: (groups[k][0]["y"], groups[k][0]["x"])):
            ws = sorted(groups[key], key=lambda w: w["x"])
            ws = [w for w in ws if w["conf"] >= 40 and (w["h"] >= 6 or w["text"].isalnum())]     # drop noise specks like ':' '=' 'ee'
            if not ws:
                continue
            # split a tesseract line at wide gaps (menus: "Home   Shop   Cart (2)   Account" → 4 targets)
            chunks, cur = [], [ws[0]]
            for prev, w in zip(ws, ws[1:]):
                gap = w["x"] - (prev["x"] + prev["w"])
                if gap > max(12, int(0.9 * max(prev["h"], w["h"]))):
                    chunks.append(cur)
                    cur = []
                cur.append(w)
            chunks.append(cur)
            for ch in chunks:
                x0, y0 = min(w["x"] for w in ch), min(w["y"] for w in ch)
                x1, y1 = max(w["x"] + w["w"] for w in ch), max(w["y"] + w["h"] for w in ch)
                out.append({"text": " ".join(w["text"] for w in ch), "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "view": key[0]})
        out.sort(key=lambda l: (l["y"] // 12, l["x"]))
        return out

    def text(self, image, limit=4000):
        return "\n".join(l["text"] for l in self.lines(image))[:limit]

    def find(self, image, text):
        """Centres of the screen elements whose OCR text best matches `text` (case-insensitive, multi-word ok)."""
        want = re.sub(r"[^a-z0-9 ]", "", text.lower()).split()
        if not want:
            return []
        hits = []
        for l in self.lines(image):
            have = re.sub(r"[^a-z0-9 ]", "", l["text"].lower())
            hv = have.split()
            if not hv:
                continue
            # score: all wanted words present in order (best) / most present / substring
            if " ".join(want) in have:
                score = 3
                if set(hv) == set(want) or (len(hv) <= len(want) + 1 and hv[:len(want)] == want):
                    score = 4                                                 # whole-line exact match beats a substring inside a longer label
            else:
                score = sum(1 for w in want if w in hv) / len(want)
                if score < 0.6:
                    continue
            cx, cy = l["x"] + l["w"] // 2, l["y"] + l["h"] // 2
            if len(hv) > len(want) + 2:                                       # long line: locate the wanted words inside it
                pos = have.find(want[0])
                if pos >= 0:
                    frac0 = pos / max(1, len(have))
                    frac1 = min(1.0, (pos + len(" ".join(want))) / max(1, len(have)))
                    cx = int(l["x"] + l["w"] * (frac0 + frac1) / 2)
            button_like = l.get("view", 0) == 1 or len(hv) <= len(want) + 1
            hits.append((score + (0.5 if button_like else 0) + (0.2 if l.get("view", 0) == 1 else 0), cx, cy, l["text"]))
        hits.sort(key=lambda h: (-h[0], -h[2]))                             # best score, then lower on the screen (buttons sit below titles)
        return [(cx, cy, t) for _, cx, cy, t in hits]
