"""Turn what the agent read into lasting knowledge: notes → dense facts → release/packs/learned.kdw

The "bulk-feed, then trim" routine:
  1. bulk: every research / summary / visit / video note lands in state/notes.jsonl (agent/memory.py)
  2. trim: digest() asks the thinking model to boil each new note down to 2-6 short, self-contained facts
     (numbers kept, hype/filler dropped); facts are de-duplicated against what is already known
  3. pack: build() writes the facts as passages and builds learned.kdw with the same engine/pipeline as the
     business pack. The brain searches every *.kdw in release/packs, so answers use learned facts at once.

State: state/learned/facts.jsonl (one fact per line: {t, topic, text, url}), state/learned/digested.txt (note ids).
Sizes: a fact ≈ 150 bytes of text + 128 dims × 1 byte → ~40 KB per 100 facts. Cap: MAX_FACTS (default 5000, ~2 MB).

CLI:  python3 -m agent.learn digest [n]   |   python3 -m agent.learn build   |   python3 -m agent.learn status
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

from . import config

LEARN_DIR = config.STATE_DIR / "learned"
FACTS = LEARN_DIR / "facts.jsonl"
DIGESTED = LEARN_DIR / "digested.txt"
PACK = config.PACKS_DIR / "learned.kdw"
MAX_FACTS = int(os.environ.get("BAI_MAX_FACTS", "5000"))
MIN_NEW_FOR_BUILD = 10

DIGEST_PROMPT = ("Below is a note the assistant wrote after reading a web page or video. Extract the FACTS a store owner "
                 "could use later: numbers, definitions, rules of thumb, steps, named tools or suppliers, warnings. "
                 "Rules: each fact is ONE self-contained sentence (max 30 words) that makes sense without the note; keep "
                 "numbers and names; drop opinions, sales pitches, and anything vague. Output 2-6 lines, each starting "
                 "with '- '. If the note has no usable facts, output exactly: - none")


def _note_id(rec):
    return hashlib.sha1((rec.get("t", "") + rec.get("topic", "") + rec.get("text", "")[:200]).encode()).hexdigest()[:12]


def _load_facts():
    if not FACTS.exists():
        return []
    return [json.loads(l) for l in FACTS.read_text(encoding="utf-8").splitlines() if l.strip()]


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


class Learner:
    def __init__(self, planner=None, memory=None, log=None):
        self.planner = planner
        self.memory = memory
        self.log = log or (lambda kind, **f: None)
        LEARN_DIR.mkdir(parents=True, exist_ok=True)
        self.digested = set(DIGESTED.read_text().split()) if DIGESTED.exists() else set()
        self.new_since_build = int((LEARN_DIR / "new_since_build").read_text() or 0) if (LEARN_DIR / "new_since_build").exists() else 0

    # ---- trim: notes → facts -------------------------------------------------
    LEARN_KINDS = ("research", "summary", "video", "study")      # page visits / supplier tables are situational, not knowledge

    def pending(self):
        if not self.memory:
            return []
        return [r for r in self.memory.notes(limit=100000)
                if _note_id(r) not in self.digested and len(r.get("text", "")) > 80 and r.get("kind") in self.LEARN_KINDS
                and not re.search(r"almost nothing|won't guess|not on this page|Task failed", r.get("text", ""))]

    def digest(self, max_notes=5):
        """Digest up to max_notes new notes into facts. Returns (notes_done, facts_added)."""
        if not (self.planner and self.planner.installed()):
            return 0, 0
        facts = _load_facts()
        seen = {_norm(f["text"])[:80] for f in facts}
        done = added = 0
        for rec in self.pending()[:max_notes]:
            try:
                raw = self.planner.chat("You extract reusable facts from notes. Output only the list.",
                                        f"{DIGEST_PROMPT}\n\nTOPIC: {rec.get('topic', '')}\nNOTE:\n{rec['text'][:3000]}",
                                        max_tokens=260, timeout=240)
            except Exception as e:
                self.log("digest_failed", error=str(e)[:100])
                break
            lines = [re.sub(r"^[-•*\d.)\s]+", "", l).strip() for l in raw.splitlines()]
            lines = [l for l in lines if 20 <= len(l) <= 260 and not l.lower().startswith("none") and self._useful(l)]
            url = (rec.get("sources") or [""])[0]
            with open(FACTS, "a", encoding="utf-8") as f:
                for l in lines:
                    key = _norm(l)[:80]
                    if key in seen or len(key) < 15:
                        continue
                    seen.add(key)
                    f.write(json.dumps({"t": rec["t"], "topic": rec.get("topic", "")[:100], "text": l, "url": url}, ensure_ascii=False) + "\n")
                    added += 1
            self.digested.add(_note_id(rec))
            done += 1
        DIGESTED.write_text("\n".join(sorted(self.digested)))
        self.new_since_build += added
        (LEARN_DIR / "new_since_build").write_text(str(self.new_since_build))
        if done:
            self.log("digest", notes=done, facts=added, total=len(facts) + added)
        return done, added

    @staticmethod
    def _useful(fact):
        """Quality gate: a fact must carry something concrete (number, named thing, or a defining/prescriptive verb)."""
        low = fact.lower()
        if re.search(r"\b(is popular|are popular|is trending|are trending|is a popular choice|is important|is key|can help|may vary|it depends)\b", low):
            return False
        if re.search(r"\b(try searching|start watching|see more|click|sign in|subscribe)\b", low):
            return False
        concrete = bool(re.search(r"\d", fact)) or bool(re.search(r"\b[A-Z][a-zA-Z]{2,}\b", fact[1:])) or \
            bool(re.search(r"\b(means|refers to|is defined|should|must|never|always|avoid|requires|costs?|takes|charges?|ships?)\b", low))
        return concrete
    def build(self, force=False):
        """Build release/packs/learned.kdw from the facts (grouped by topic → one 'article' per topic)."""
        facts = _load_facts()
        if not facts:
            return "no facts yet"
        if not force and self.new_since_build < MIN_NEW_FOR_BUILD:
            return f"only {self.new_since_build} new facts since the last build (builds at {MIN_NEW_FOR_BUILD})"
        if len(facts) > MAX_FACTS:                       # keep the newest; the oldest drop off
            facts = facts[-MAX_FACTS:]
            FACTS.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in facts), encoding="utf-8")
        by_topic = {}
        for f in facts:
            by_topic.setdefault(f["topic"] or "misc", []).append(f)
        ext = tempfile.mkdtemp(prefix="learned_")
        with open(os.path.join(ext, "articles.tsv"), "w", encoding="utf-8") as fa, \
             open(os.path.join(ext, "passages.tsv"), "w", encoding="utf-8") as fp:
            for aid, (topic, fs) in enumerate(by_topic.items()):
                url = next((f["url"] for f in fs if f.get("url")), "")
                path = re.sub(r"^https?://", "", url)[:200] or f"learned/{aid}"
                fa.write(f"{aid}\t{path}\t{topic[:120]}\n")
                # passages of ~3 facts each so the retriever sees dense, on-topic text
                for i in range(0, len(fs), 3):
                    chunk = " ".join(f["text"].replace("\t", " ").replace("\n", " ") for f in fs[i:i + 3])
                    fp.write(f"{aid}\t{topic}: {chunk}\n")
        tmp_out = str(PACK) + ".tmp"
        r = subprocess.run([sys.executable, str(config.ROOT / "packs/build_pack.py"), ext, tmp_out], capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not os.path.exists(tmp_out):
            self.log("learned_build_failed", error=(r.stderr or r.stdout)[-300:])
            return "build failed: " + (r.stderr or r.stdout)[-200:]
        os.replace(tmp_out, PACK)
        self.new_since_build = 0
        (LEARN_DIR / "new_since_build").write_text("0")
        self.log("learned_build", facts=len(facts), topics=len(by_topic), mb=round(PACK.stat().st_size / 1e6, 2))
        return f"learned.kdw rebuilt: {len(facts)} facts, {len(by_topic)} topics, {PACK.stat().st_size / 1e6:.2f} MB"

    def status(self):
        n = len(_load_facts())
        size = f"{PACK.stat().st_size / 1e6:.2f} MB" if PACK.exists() else "not built yet"
        return f"learned: {n} facts from {len(self.digested)} notes ({len(self.pending())} notes waiting), pack {size}, {self.new_since_build} new since build"

    def recent(self, k=8):
        return _load_facts()[-k:]


def main(argv):
    from .planner import Planner
    from .memory import Memory
    L = Learner(Planner(), Memory())
    cmd = argv[0] if argv else "status"
    if cmd == "digest":
        print(L.digest(int(argv[1]) if len(argv) > 1 else 5))
    elif cmd == "build":
        print(L.build(force=True))
    print(L.status())
    L.planner.stop()


if __name__ == "__main__":
    main(sys.argv[1:])
