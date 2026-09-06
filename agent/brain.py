"""Adapter to the knowledge brain (the C engine inherited from kdr-brain).

Milestone 0: the brain may not exist yet (no packs). Then ask() returns None
and the agent says so honestly. Once release/businessai-brain + brain.kdr +
packs/*.kdw exist, ask() runs the engine's `ask` command and returns the
answer text; later milestones switch to the long-running `serve` mode.
"""
import os
import shutil
import subprocess

from . import config


class Brain:
    def __init__(self):
        self.bin = config.BRAIN_BIN if os.path.isfile(config.BRAIN_BIN) else shutil.which("businessai-brain")
        self.kdr = config.BRAIN_KDR if os.path.isfile(config.BRAIN_KDR) else None
        self.packs = sorted(str(p) for p in config.PACKS_DIR.glob("*.kdw")) if config.PACKS_DIR.exists() else []

    @property
    def ready(self):
        return bool(self.bin and self.kdr)

    def describe(self):
        if not self.ready:
            return "not installed yet (no knowledge packs)"
        mb = lambda p: f"{os.path.getsize(p) / 1e6:.0f} MB"
        packs = ", ".join(f"{os.path.basename(p)} {mb(p)}" for p in self.packs) or "no packs"
        return f"engine {mb(self.bin)}, brain.kdr {mb(self.kdr)}, {packs}"

    def ask(self, question, timeout=60):
        if not self.ready or not question:
            return None
        cmd = [self.bin, self.kdr]
        for p in self.packs[:1]:          # engine takes one --wiki pack for now
            cmd += ["--wiki", p]
        cmd += ["ask", question]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except (subprocess.TimeoutExpired, OSError):
            return None
        ans = out.stdout.strip()
        return ans or None
