"""Answer multiple-choice questions with the knowledge brain (no external model).

Strategy per question:
 1. retrieve passages for the question stem (+ for each choice appended to the stem);
 2. score each choice by evidence: how strongly the passages that match the stem also
    contain the choice's words (lexical support), plus the extractive reader's own span
    (if its answer overlaps a choice, that choice gets a bonus);
 3. handle negations ("NOT", "EXCEPT", "least"): pick the LEAST supported choice;
 4. "all of the above" wins when every other choice is well supported.

Reports a confidence so the caller can escalate the unsure ones (owner / bigger model).
"""
import json
import math
import os
import re
import subprocess

from . import config

STOP = set("""a an the of to in on for and or is are was were be been being what which who whom whose that this these those
it its as at by with from into than then there their they them he she his her we you your our i not no nor do does did
can could should would will may might must have has had having about above after again against all am any because before
below between both but down during each few further here how if more most much only other out over own same so some such
too under until up very when where while why one two three four five following best correct true describes example
type kind term called known refers refer known""".split())


def toks(t):
    return [w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in STOP and len(w) > 1]


def stem_words(t):
    return set(w[:6] for w in toks(t))


class MCQSolver:
    def __init__(self, pack=None, readk="3"):
        self.bin = config.BRAIN_BIN
        self.kdr = config.BRAIN_KDR
        self.pack = pack or (sorted(str(p) for p in config.PACKS_DIR.glob("*.kdw")) or [None])[0]
        self.env = dict(os.environ)
        self.env.setdefault("KDR_WIKI_READK", readk)

    def brain(self, q):
        out = subprocess.run([self.bin, self.kdr, "--wiki", self.pack, "wiki", q], capture_output=True, text=True,
                             timeout=60, env=self.env).stdout
        try:
            return json.loads(out)
        except ValueError:
            return {"hits": [], "answer": "", "confidence": 0}

    def hits_text(self, q, k=8):
        d = self.brain(q)
        hits = d.get("hits", [])[:k]
        return d, [(h.get("score", 0), (h.get("text") or "").lower()) for h in hits]

    def support(self, choice, hits):
        """Evidence score for a choice: retrieval-weighted fraction of the choice's stem-words present in each passage."""
        cw = stem_words(choice)
        if not cw:
            return 0.0
        best, total = 0.0, 0.0
        for rank, (score, text) in enumerate(hits):
            tw = stem_words(text)
            frac = len(cw & tw) / len(cw)
            w = score / (1 + 0.15 * rank)
            total += frac * w
            best = max(best, frac * w)
        return 0.6 * best + 0.4 * total / max(1, len(hits)) ** 0.5

    def answer(self, q, choices):
        stem = q.strip()
        negated = bool(re.search(r"\b(NOT|EXCEPT|LEAST|FALSE|INCORRECT)\b", stem)) or bool(re.search(r"\b(not|except|least likely|is false|incorrect)\b", stem))
        d, hits = self.hits_text(stem)
        reader = (d.get("answer") or "").lower()
        reader_conf = float(d.get("confidence") or 0)
        scores = []
        for c in choices:
            cl = c.lower().strip(" .")
            if re.fullmatch(r"(all|none) of the above|both [a-d] and [a-d]|all of these", cl):
                scores.append(None)
                continue
            s = self.support(c, hits)
            # second retrieval with the choice in the query rewards choices that co-occur with the stem in one passage
            _, hits2 = self.hits_text(f"{stem} {c}", k=4)
            s += 0.5 * self.support(c, hits2) * (1.0 if any(len(stem_words(stem) & stem_words(t)) >= 3 for _, t in hits2) else 0.3)
            if reader and reader_conf >= 0.4:
                ov = len(stem_words(reader) & stem_words(c)) / max(1, len(stem_words(c)))
                s += 0.35 * ov * reader_conf
            scores.append(s)
        real = [s for s in scores if s is not None]
        if not real:
            return 0, 0.0, scores
        # "all of the above": every other choice is supported comparably
        if None in scores:
            mn, mx = min(real), max(real)
            if mn > 0 and mn >= 0.7 * mx and not negated:
                return scores.index(None), 0.5, scores
            scores = [(-1 if s is None else s) for s in scores]
        pick_fn = min if negated else max
        cand = [i for i, s in enumerate(scores) if s >= 0]
        best = pick_fn(cand, key=lambda i: scores[i])
        srt = sorted((scores[i] for i in cand), reverse=not negated)
        gap = abs(srt[0] - srt[1]) if len(srt) > 1 else srt[0]
        conf = min(1.0, gap / (abs(srt[0]) + 1e-6)) if srt[0] else 0.0
        return best, conf, scores


def run_bank(path, n=None, seed=1, pack=None, verbose=False):
    import random
    qs = [json.loads(l) for l in open(path, encoding="utf-8")]
    if n:
        random.seed(seed); qs = random.sample(qs, min(n, len(qs)))
    solver = MCQSolver(pack)
    ok = 0; confs = []
    for i, q in enumerate(qs):
        pred, conf, sc = solver.answer(q["q"], q["choices"])
        good = pred == q["answer"]; ok += good; confs.append((conf, good))
        if verbose:
            print(f"{'OK ' if good else 'X  '} c={conf:.2f} {q['q'][:80]!r} -> {q['choices'][pred][:40]!r} (true: {q['choices'][q['answer']][:40]!r})", flush=True)
    confs.sort(reverse=True)
    top = confs[: max(1, len(confs) // 2)]
    print(f"MCQ {ok}/{len(qs)} = {100*ok/len(qs):.0f}%   (most-confident half: {100*sum(g for _, g in top)/len(top):.0f}%)")
    return ok, len(qs)


if __name__ == "__main__":
    import sys
    run_bank(sys.argv[1], n=int(sys.argv[2]) if len(sys.argv) > 2 else None, verbose="-v" in sys.argv)
