"""Adapter to the knowledge brain (the C engine inherited from kdr-brain).

The brain = engine binary (release/kdr-brain-lite) + brain.kdr (retriever + reader
models) + knowledge packs (release/packs/*.kdw, e.g. business.kdw).
ask() runs the engine's `wiki` command against the pack and returns the answer
sentence with its source title; None when the brain is not installed or unsure.
"""
import json
import os
import shutil
import subprocess

from . import config


class Brain:
    def __init__(self):
        self.bin = config.BRAIN_BIN if os.path.isfile(config.BRAIN_BIN) else shutil.which("kdr-brain-lite")
        self.kdr = config.BRAIN_KDR if os.path.isfile(config.BRAIN_KDR) else None
        self.packs = sorted(str(p) for p in config.PACKS_DIR.glob("*.kdw")) if config.PACKS_DIR.exists() else []

    @property
    def ready(self):
        return bool(self.bin and self.kdr and self.packs)

    def describe(self):
        if not (self.bin and self.kdr):
            return "engine not installed (run scripts/get_brain.sh)"
        mb = lambda p: f"{os.path.getsize(p) / 1e6:.1f} MB"
        packs = ", ".join(f"{os.path.basename(p)} {mb(p)}" for p in self.packs) or "no knowledge packs yet"
        return f"engine {mb(self.bin)} + models {mb(self.kdr)}; packs: {packs}"

    def refresh(self):
        self.packs = sorted(str(p) for p in config.PACKS_DIR.glob("*.kdw")) if config.PACKS_DIR.exists() else []
        return self.packs

    def ask_raw(self, question, pack=None, timeout=60):
        if pack is None:
            self.refresh()
        if not self.ready or not question:
            return None
        pack = pack or self.packs[0]
        cmd = [self.bin, self.kdr, "--wiki", pack, "wiki", question]
        env = dict(os.environ); env.setdefault("KDR_WIKI_READK", "3")   # tuned on tests/business.txt: 52/55, 2.5x faster
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
            return json.loads(out.stdout)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            return None

    def ask(self, question, min_conf=0.35):
        """Best answer across packs, formatted for the owner. None if the brain isn't confident."""
        best = None
        for pack in self.refresh():
            d = self.ask_raw(question, pack)
            if d and (best is None or d.get("confidence", 0) > best.get("confidence", 0)):
                best = d
        if not best or best.get("confidence", 0) < min_conf or not best.get("answer"):
            return None
        sent = (best.get("sentence") or best["answer"]).strip()
        ans = best["answer"].strip()
        text = sent if ans.lower() in sent.lower() else f"{ans}. {sent}"
        if len(text) > 700:
            text = text[:700].rsplit(" ", 1)[0] + "…"
        src = best.get("title") or ""
        return f"{text}\n— {src} (business pack, confidence {best['confidence']:.2f})"
