"""The thinking model ("planner") behind the agent.

Runs a local llama.cpp server (release/llm/llama-server + release/llm/model.gguf, fetched by
scripts/get_model.sh) and talks to it over the OpenAI-compatible API. Any other OpenAI-compatible
endpoint works too: set BAI_LLM_URL (+ BAI_LLM_KEY, BAI_LLM_MODEL) in .secrets/env.

Frugal: the server is started on first use and stopped after IDLE_STOP seconds without a call,
so the RAM (~1.3 GB for the default model) is only taken while the agent is thinking.

Everything it does is grounded: the caller passes evidence (knowledge-pack passages, page text);
the prompt says to answer from the evidence and to say so when the evidence isn't enough.

Public API:
  Planner().available()                   -> bool (starts the local server if needed)
  Planner().intent(message)               -> {"kind": ask|research|summarize|compare|chat|command, "topic": str}
  Planner().answer(question, evidence)    -> str (2-5 sentences, sources named)
  Planner().brief(topic, notes)           -> str (short research brief from several page notes)
  Planner().mcq(question, choices, evidence) -> (index, confidence, raw)
  Planner().chat(system, user, ...)       -> raw completion
"""
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

from . import config

LLM_DIR = config.ROOT / "release" / "llm"
SERVER_BIN = LLM_DIR / "llama-server"
MODEL_FILE = LLM_DIR / "model.gguf"
PORT = int(os.environ.get("BAI_LLM_PORT", "8091"))
REMOTE_URL = os.environ.get("BAI_LLM_URL", "")
IDLE_STOP = int(os.environ.get("BAI_LLM_IDLE", "600"))
THREADS = os.environ.get("BAI_LLM_THREADS") or str(max(1, (os.cpu_count() or 2) - 1))

SYSTEM = ("You are the thinking part of a small business AI that helps its owner run an online store (dropshipping, "
          "marketing, suppliers, customers). Be brief, concrete and honest. Use only the EVIDENCE you are given; if it "
          "does not contain the answer, say so plainly. Never invent prices, names, dates or numbers.")

INTENT_PROMPT = """Classify the owner's message for a business assistant. Reply with one JSON object only:
{"kind": KIND, "topic": TOPIC}
KIND is one of:
- "ask": a question that can be answered from general business knowledge (what is X, how does Y work, difference between, is it worth it)
- "research": the owner wants something looked up, checked, found or investigated on the web (find out, look up, check, search, what do people say, latest, prices of)
- "summarize": the message contains a URL to read or summarize
- "compare": the owner wants suppliers / options / prices for a product compared
- "chat": greetings, thanks, small talk, feedback, or instructions about how to behave
TOPIC is the subject in a few words (for summarize: the URL). Examples:
"can you find out how epacket shipping works" -> {"kind": "research", "topic": "how ePacket shipping works"}
"what is a good margin for dropshipping" -> {"kind": "ask", "topic": "good profit margin for dropshipping"}
"look for suppliers of bamboo toothbrushes" -> {"kind": "compare", "topic": "bamboo toothbrush"}
"thanks that was useful" -> {"kind": "chat", "topic": "thanks"}
Message: """


class Planner:
    def __init__(self, log=None):
        self.log = log or (lambda kind, **f: None)
        self.remote = bool(REMOTE_URL)
        self.url = REMOTE_URL or f"http://127.0.0.1:{PORT}/v1/chat/completions"
        self.model = os.environ.get("BAI_LLM_MODEL", "local")
        self.key = os.environ.get("BAI_LLM_KEY", "")
        self._proc = None
        self._lock = threading.Lock()
        self.last_used = 0
        self.calls = self.tokens = 0

    # ---- local server lifecycle -----------------------------------------
    def installed(self):
        return self.remote or (SERVER_BIN.exists() and MODEL_FILE.exists())

    def _ping(self, timeout=2):
        try:
            with urllib.request.urlopen(self.url.rsplit("/v1/", 1)[0] + "/health", timeout=timeout) as r:
                return r.status == 200
        except Exception:
            return False

    def _start(self):
        if self.remote or (self._proc and self._proc.poll() is None):
            return True
        if not self.installed():
            return False
        env = dict(os.environ, LD_LIBRARY_PATH=str(LLM_DIR))
        self._proc = subprocess.Popen([str(SERVER_BIN), "-m", str(MODEL_FILE), "--host", "127.0.0.1", "--port", str(PORT),
                                       "-c", "6144", "-t", THREADS, "--no-warmup", "--log-disable"],
                                      env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()
        while time.time() - t0 < 90:
            if self._ping():
                self.log("llm_started", ms=int((time.time() - t0) * 1000))
                return True
            if self._proc.poll() is not None:
                break
            time.sleep(0.5)
        self.log("llm_start_failed")
        self._proc = None
        return False

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(10)
            except Exception:
                self._proc.kill()
            self.log("llm_stopped")
        self._proc = None

    def tick(self):
        """Call periodically: frees the RAM after IDLE_STOP seconds without a call."""
        if self._proc and not self._lock.locked() and time.time() - self.last_used > IDLE_STOP:
            self.stop()

    def available(self):
        if self.remote:
            return True
        return self._ping() or self._start()

    def describe(self):
        if not self.installed():
            return "thinking model: not installed (sh scripts/get_model.sh)"
        where = "remote " + re.sub(r"^https?://([^/]+).*", r"\1", self.url) if self.remote else f"local {MODEL_FILE.stat().st_size >> 20} MB"
        state = "running" if (self.remote or self._ping()) else "asleep"
        return f"thinking model: {where}, {state}, {self.calls} calls"

    # ---- raw chat ---------------------------------------------------------
    def chat(self, system, user, max_tokens=256, temperature=0.0, timeout=180, stop=None):
        with self._lock:
            if not self.available():
                raise RuntimeError("thinking model not available")
            body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "max_tokens": max_tokens, "temperature": temperature}
            if stop:
                body["stop"] = stop
            req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            if self.key:
                req.add_header("Authorization", f"Bearer {self.key}")
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode())
            self.last_used = time.time()
            self.calls += 1
            self.tokens += int(d.get("usage", {}).get("total_tokens", 0))
            self.log("llm_call", ms=int((time.time() - t0) * 1000), tokens=d.get("usage", {}).get("total_tokens"))
            return d["choices"][0]["message"]["content"].strip()

    # ---- skills -----------------------------------------------------------
    def intent(self, message):
        """What does the owner want? Cheap regex first; the model only for the unclear middle."""
        m = message.strip()
        low = m.lower()
        url = re.search(r"https?://\S+", m)
        if url:
            return {"kind": "summarize", "topic": url.group(0)}
        if re.search(r"^(hi|hello|hey|thanks|thank you|ok|okay|good (morning|evening|night)|bye)\b", low) and len(low) < 40:
            return {"kind": "chat", "topic": m}
        if re.search(r"\b(find|look|search|check|research|investigate|dig|see what|what do people|latest|current|today)\b", low) and \
           re.search(r"\b(supplier|suppliers|vendors?|wholesale|manufacturer)s?\b", low) and re.search(r"\b(compare|options|prices?|for)\b", low):
            return {"kind": "compare", "topic": re.sub(r".*\b(of|for)\b", "", low).strip(" ?.") or m}
        try:
            raw = self.chat("You classify messages. Output JSON only.", INTENT_PROMPT + json.dumps(m), max_tokens=60, stop=["\n\n"])
            j = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            kind = j.get("kind", "ask")
            if kind not in ("ask", "research", "summarize", "compare", "chat"):
                kind = "ask"
            return {"kind": kind, "topic": str(j.get("topic") or m)[:120]}
        except Exception as e:
            self.log("intent_fallback", error=str(e)[:80])
            wants_web = bool(re.search(r"\b(find|look up|search|check|research|investigate|latest|current|online)\b", low))
            return {"kind": "research" if wants_web else "ask", "topic": re.sub(r"^(can you|could you|please|would you)\s+", "", low).strip(" ?.")}

    def answer(self, question, evidence, max_tokens=220):
        ev = (evidence or "").strip()[:5000] or "(no evidence found)"
        user = (f"EVIDENCE:\n{ev}\n\nOWNER'S QUESTION: {question}\n\n"
                "Write the answer for the owner in 2-5 plain sentences, using only the evidence. Include concrete numbers or steps when "
                "the evidence has them. End with one line 'Sources: ' naming the source titles you used. If the evidence does not "
                "answer the question, say what is missing instead of guessing.")
        return self.chat(SYSTEM, user, max_tokens=max_tokens)

    def brief(self, topic, notes, max_tokens=300):
        """notes: list of (title, url, [key sentences]) → one short brief with sources."""
        ev = "\n\n".join(f"[{i+1}] {t}\n{u}\n" + "\n".join(f"- {s}" for s in ks) for i, (t, u, ks) in enumerate(notes))
        user = (f"NOTES FROM {len(notes)} WEB PAGES:\n{ev[:5500]}\n\nTOPIC: {topic}\n\n"
                "Write a short brief for the owner: first a 2-4 sentence direct answer, then up to 4 bullet points with the most useful "
                "concrete facts (numbers, steps, warnings). Cite pages as [1], [2]. Do not add anything that is not in the notes.")
        return self.chat(SYSTEM, user, max_tokens=max_tokens)

    def mcq(self, question, choices, evidence):
        letters = "ABCDEFGH"
        opts = "\n".join(f"{letters[i]}. {c}" for i, c in enumerate(choices))
        ev = (evidence or "").strip()[:3500] or "(none)"
        user = (f"EVIDENCE:\n{ev}\n\nQUESTION: {question}\n{opts}\n\nReply with exactly one line: 'Answer: <letter>' then "
                "'Confidence: high|medium|low'.")
        raw = self.chat(SYSTEM, user, max_tokens=24)
        m = re.search(r"Answer:\s*\(?([A-H])\b", raw) or re.search(r"\b([A-H])[.)]", raw) or re.search(r"\b([A-H])\b", raw)
        idx = letters.index(m.group(1)) if m and letters.index(m.group(1)) < len(choices) else 0
        cm = re.search(r"Confidence:\s*(high|medium|low)", raw, re.I)
        conf = {"high": 0.9, "medium": 0.6, "low": 0.3}.get((cm.group(1).lower() if cm else "medium"), 0.6)
        return idx, conf, raw

    def reply(self, message):
        """Small talk / instructions, no evidence needed."""
        return self.chat("You are a friendly, concise business assistant talking to your owner on Telegram. One or two sentences.",
                         message, max_tokens=60, temperature=0.3)
