"""Memory: what the agent learned, what it has to do, what it did today.

Plain files under state/ (git-ignored), readable by the owner:
  state/notes.jsonl   one line per note: {t, kind, topic, text, sources}
  state/todo.json     {"items": [{id, text, status, t, done_t}], "goals": [{id, topic, runs, t}], "day": "YYYY-MM-DD", "used": n}

Goals are standing learning topics ("learn about print-on-demand suppliers in Europe"). When the agent is idle it
works on one goal per slot, at most DAILY_BUDGET research runs per day, and keeps the notes. That — and only that —
is what makes it look around on its own.
"""
import datetime as _dt
import json
import re
import time

from . import config

NOTES = config.STATE_DIR / "notes.jsonl"
TODO = config.STATE_DIR / "todo.json"
DAILY_BUDGET = 6          # self-directed research runs per day (each ≈ 3 pages)


def _now():
    return _dt.datetime.now().isoformat(timespec="seconds")


class Memory:
    def __init__(self):
        config.ensure_dirs()
        try:
            self.todo = json.loads(TODO.read_text())
        except Exception:
            self.todo = {"items": [], "goals": [], "day": "", "used": 0}
        self._roll_day()

    def _save(self):
        TODO.write_text(json.dumps(self.todo, ensure_ascii=False, indent=1))

    def _roll_day(self):
        today = _dt.date.today().isoformat()
        if self.todo.get("day") != today:
            self.todo["day"], self.todo["used"] = today, 0
            self._save()

    # ---- notes ----------------------------------------------------------
    def note(self, kind, topic, text, sources=None):
        rec = {"t": _now(), "kind": kind, "topic": topic[:120], "text": text[:4000], "sources": (sources or [])[:8]}
        with open(NOTES, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def notes(self, query=None, limit=5, days=None):
        if not NOTES.exists():
            return []
        out = []
        cutoff = (_dt.datetime.now() - _dt.timedelta(days=days)).isoformat() if days else ""
        words = set(re.findall(r"[a-z0-9]{3,}", (query or "").lower()))
        for line in NOTES.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if cutoff and r["t"] < cutoff:
                continue
            if words:
                hay = (r["topic"] + " " + r["text"]).lower()
                score = sum(w in hay for w in words)
                if score == 0:
                    continue
                r["_score"] = score
            out.append(r)
        if words:
            out.sort(key=lambda r: (-r["_score"], r["t"]))
        else:
            out.reverse()
        return out[:limit]

    def recall(self, query, max_chars=1500):
        """Evidence-style text from earlier notes (used by the planner before browsing again)."""
        parts = []
        for r in self.notes(query, limit=3):
            parts.append(f"[my note {r['t'][:10]} on {r['topic']}] {r['text'][:600]}")
        return "\n".join(parts)[:max_chars]

    # ---- to-do -----------------------------------------------------------
    def add(self, text):
        i = 1 + max([x["id"] for x in self.todo["items"]] or [0])
        self.todo["items"].append({"id": i, "text": text[:200], "status": "open", "t": _now()})
        self._save()
        return i

    def done(self, i):
        for x in self.todo["items"]:
            if x["id"] == int(i) and x["status"] == "open":
                x["status"], x["done_t"] = "done", _now()
                self._save()
                return x
        return None

    def open_items(self):
        return [x for x in self.todo["items"] if x["status"] == "open"]

    def list_text(self):
        items = self.open_items()
        goals = self.todo["goals"]
        out = ["To-do:"] + [f"  {x['id']}. {x['text']}" for x in items] if items else ["To-do: (empty)"]
        out += ["Learning goals:"] + [f"  g{g['id']}. {g['topic']} ({g['runs']} sessions)" for g in goals] if goals else ["Learning goals: (none — add one with /goal <topic>)"]
        out.append(f"Self-study budget today: {self.todo['used']}/{DAILY_BUDGET} runs used")
        return "\n".join(out)

    # ---- learning goals (self-directed research) ---------------------------
    def add_goal(self, topic):
        i = 1 + max([g["id"] for g in self.todo["goals"]] or [0])
        self.todo["goals"].append({"id": i, "topic": topic[:150], "runs": 0, "t": _now(), "angles": []})
        self._save()
        return i

    def drop_goal(self, i):
        before = len(self.todo["goals"])
        self.todo["goals"] = [g for g in self.todo["goals"] if g["id"] != int(i)]
        self._save()
        return len(self.todo["goals"]) < before

    def next_goal(self):
        """The goal to study next (least studied first), or None when the day's budget is spent."""
        self._roll_day()
        if self.todo["used"] >= DAILY_BUDGET or not self.todo["goals"]:
            return None
        return min(self.todo["goals"], key=lambda g: g["runs"])

    def studied(self, goal_id, angle):
        for g in self.todo["goals"]:
            if g["id"] == goal_id:
                g["runs"] += 1
                g.setdefault("angles", []).append(angle[:100])
        self.todo["used"] += 1
        self._save()

    # ---- daily report ------------------------------------------------------
    def daily_report(self):
        today = self.notes(limit=50, days=1)
        done = [x for x in self.todo["items"] if x.get("done_t", "")[:10] == _dt.date.today().isoformat()]
        if not today and not done:
            return None
        out = [f"Daily report {_dt.date.today().isoformat()}"]
        kinds = {}
        for r in today:
            kinds.setdefault(r["kind"], []).append(r["topic"])
        for k, topics in kinds.items():
            out.append(f"• {k}: " + "; ".join(dict.fromkeys(topics)))
        if done:
            out.append("• finished to-dos: " + "; ".join(x["text"] for x in done))
        if self.open_items():
            out.append(f"• still open: {len(self.open_items())} to-do(s)")
        out.append(f"• self-study runs: {self.todo['used']}/{DAILY_BUDGET}")
        return "\n".join(out)
