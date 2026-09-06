"""The thinking model ("planner") behind the agent.

Talks to any OpenAI-compatible chat endpoint:
  - local llama-server (default: http://127.0.0.1:8081, started by scripts/run_model.sh)
  - or a hosted model when BAI_LLM_URL / BAI_LLM_KEY / BAI_LLM_MODEL are set in .secrets/env.
Everything it is asked is grounded: the caller passes evidence (knowledge-pack passages,
page text) and the prompt tells it to answer from the evidence and say "unsure" otherwise.

Public API:
  Planner().available()                       -> bool
  Planner().chat(system, user, max_tokens)     -> str
  Planner().mcq(question, choices, evidence)   -> (index, confidence, raw)
  Planner().answer(question, evidence)         -> str
  Planner().plan(goal, tools)                  -> list of steps (text)
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

from . import config

DEFAULT_URL = os.environ.get("BAI_LLM_URL", "http://127.0.0.1:8081/v1/chat/completions")
DEFAULT_MODEL = os.environ.get("BAI_LLM_MODEL", "local")
API_KEY = os.environ.get("BAI_LLM_KEY", "")

SYSTEM = ("You are the thinking part of a small business AI that helps its owner run an online store. "
          "Be brief, concrete and honest. Use only the EVIDENCE you are given; if it does not contain the answer, say 'unsure'. "
          "Never invent prices, names or numbers.")


class Planner:
    def __init__(self, url=None, model=None, key=None, timeout=120):
        self.url = url or DEFAULT_URL
        self.model = model or DEFAULT_MODEL
        self.key = key or API_KEY
        self.timeout = timeout
        self._ok = None
        self.calls = 0
        self.tokens = 0

    def available(self, recheck=False):
        if self._ok is None or recheck:
            try:
                self.chat("Reply with OK.", "ping", max_tokens=3, timeout=20)
                self._ok = True
            except Exception:
                self._ok = False
        return self._ok

    def describe(self):
        if self.url.startswith("http://127.0.0.1") or self.url.startswith("http://localhost"):
            where = "local"
        else:
            where = re.sub(r"^https?://([^/]+).*", r"\1", self.url)
        return f"{self.model} @ {where} ({'up' if self.available() else 'down'}), {self.calls} calls, {self.tokens} tokens"

    # ---- raw chat --------------------------------------------------------
    def chat(self, system, user, max_tokens=256, temperature=0.0, timeout=None, stop=None):
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": max_tokens, "temperature": temperature}
        if stop:
            body["stop"] = stop
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        if self.key:
            req.add_header("Authorization", f"Bearer {self.key}")
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
            d = json.loads(r.read().decode())
        self.calls += 1
        self.tokens += int(d.get("usage", {}).get("total_tokens", 0))
        txt = d["choices"][0]["message"]["content"].strip()
        return txt

    # ---- grounded skills -------------------------------------------------
    def mcq(self, question, choices, evidence):
        """Pick a choice from evidence. Returns (index, confidence 0..1, raw)."""
        letters = "ABCDEFGH"
        opts = "\n".join(f"{letters[i]}. {c}" for i, c in enumerate(choices))
        ev = evidence.strip()[:3500] if evidence else "(none)"
        user = (f"EVIDENCE:\n{ev}\n\nQUESTION: {question}\n{opts}\n\n"
                f"Think about which option the evidence supports. Reply with exactly one line: 'Answer: <letter>' "
                f"followed by 'Confidence: high|medium|low'.")
        raw = self.chat(SYSTEM, user, max_tokens=24)
        m = re.search(r"Answer:\s*\(?([A-H])\b", raw) or re.search(r"\b([A-H])[.)]", raw) or re.search(r"\b([A-H])\b", raw)
        idx = letters.index(m.group(1)) if m and letters.index(m.group(1)) < len(choices) else 0
        cm = re.search(r"Confidence:\s*(high|medium|low)", raw, re.I)
        conf = {"high": 0.9, "medium": 0.6, "low": 0.3}.get((cm.group(1).lower() if cm else "medium"), 0.6)
        return idx, conf, raw

    def answer(self, question, evidence, max_tokens=200):
        ev = evidence.strip()[:4000] if evidence else "(none)"
        return self.chat(SYSTEM, f"EVIDENCE:\n{ev}\n\nQUESTION: {question}\n\nAnswer in 1-3 sentences from the evidence, then name the source title in brackets.",
                         max_tokens=max_tokens)

    def plan(self, goal, tools, max_steps=6):
        user = (f"GOAL: {goal}\n\nTOOLS I can use: {', '.join(tools)}\n\n"
                f"Write a numbered plan of at most {max_steps} short steps, each using one tool. No explanations.")
        raw = self.chat(SYSTEM, user, max_tokens=220)
        steps = [re.sub(r"^\s*\d+[.)]\s*", "", l).strip() for l in raw.splitlines() if re.match(r"^\s*\d+[.)]", l)]
        return steps or [raw]
