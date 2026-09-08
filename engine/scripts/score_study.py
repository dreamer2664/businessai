"""Self-study score (milestone 17): PDF density judge, ideas from short videos (rule fallback), long videos → chaptered
course notes resumed across sessions, ideas doc sync, quiet-session cycling, owner videos pending at start.
Offline: transcripts are stubbed. Run:  python3 engine/scripts/score_study.py --show | tail -30"""
import json
import os
import shutil
import sys
import time

os.environ["BAI_STATE"] = "/tmp/bai_study_score"
shutil.rmtree(os.environ["BAI_STATE"], ignore_errors=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent import study as S_mod                       # noqa: E402
from agent.study import Study                          # noqa: E402
from agent import video                                # noqa: E402
from agent import library                              # noqa: E402

SHOW = "--show" in sys.argv
checks = []


def check(name, ok, note=""):
    checks.append((name, bool(ok)))
    if SHOW or not ok:
        print(("✅" if ok else "❌"), name, ("— " + str(note)[:120]) if note else "")


t0 = time.time()


class Mem:
    def __init__(self):
        self.recs = []

    def note(self, kind, topic, text, sources=None):
        self.recs.append({"kind": kind, "topic": topic, "text": text, "sources": sources or []})

    def notes(self, query=None, limit=5, days=None):
        return self.recs[-limit:]


mem = Mem()
S = Study(tasks=None, planner=None, google=None, memory=mem, log=lambda k, **f: None)

# 1) density judge
dense = ("Step 1: compute landed cost = product + shipping + duties. Step 2: price at 2.5x to 4x landed cost. Table 3 shows margins by category. "
         "Figure 2 compares conversion rates: 1.5% average, 3% good. Checklist: supplier feedback ≥ 95%, dispute rate < 2%, processing time ≤ 3 days. ") * 12
fluff = ("In today's fast-paced world, entrepreneurs are increasingly looking for exciting opportunities. This amazing journey will unlock your potential and "
         "transform your mindset. Imagine the possibilities! It is truly a game changer for anyone ready to dream big. ") * 12
d1, d2 = S_mod._density(dense), S_mod._density(fluff)
check("density: dense manual scores high", d1 >= 4.0, f"{d1:.1f}")
check("density: fluff scores low", d2 < 4.0, f"{d2:.1f}")
check("density: dense >> fluff", d1 > d2 + 5, f"{d1:.1f} vs {d2:.1f}")

# 2) ideas from a short transcript (rule fallback)
short = ("Here are three ideas. You can sell custom pet portraits printed on demand, margins around 60 percent. Another idea: rent out camera gear locally "
         "through a simple booking page, about 40 dollars a day. Also, a subscription box for specialty coffee at 25 euros a month works well in cities. "
         "Subscribe to my channel for more!")
ideas = S._ideas_from(short, "3 business ideas")
check("ideas: rule fallback extracts concrete ideas", 2 <= len(ideas) <= 4 and any("portrait" in i.lower() or "coffee" in i.lower() for i in ideas), ideas)
check("ideas: no 'subscribe' filler kept", not any("subscribe" in i.lower() for i in ideas), ideas)

# 3) video session with stubbed transcripts: one short, one long course
LONG = ("In 2025 Shopify processed over 378 billion dollars in sales, a 30 percent increase. " * 3 +
        "The first rule: never spend more than 20 percent of your budget on the first test campaign. " +
        "Aim for a 3x return on ad spend before scaling. Ship within 3 days or refund rates climb above 10 percent. " +
        "Welcome back, in this video I show you my course. ") * 400                                  # ≈ 240k chars → course (27 chunks)
META = {"vid_short": ("short", {"title": "3 side hustles that work", "channel": "x", "seconds": 300, "language": "en", "auto": True}),
        "vid_long": (LONG, {"title": "Complete Dropshipping Course (11 hours)", "channel": "y", "seconds": 39600, "language": "en", "auto": True})}
META["vid_short"] = (short, META["vid_short"][1])
video.transcript = lambda vid: META.get(vid, ("", {}))
video.url_id = lambda url: url.rsplit("/", 1)[-1]
S_mod.video.transcript = video.transcript
S_mod.video.url_id = video.url_id
out = S.video_session(urls=["https://youtu.be/vid_short"])
check("short video → ideas jotted", "Jotted" in out and "business ideas" in out, out[:100])
ideas_file = S_mod.config.STATE_DIR / "ideas.jsonl"
check("ideas.jsonl written with source", ideas_file.exists() and "vid_short" in ideas_file.read_text())
docs = list(library.LIB_DIR.glob("*.html"))
check("ideas document synced to the library", any("idea" in p.name.lower() for p in docs), [p.name for p in docs])
check("memory note kind 'ideas'", any(r["kind"] == "ideas" for r in mem.recs))

out2 = S.video_session(urls=["https://youtu.be/vid_long"])
check("long video → course notes instead of ideas", "Course" in out2 and "lessons noted" in out2, out2[:120])
prog = json.loads((S_mod.config.STATE_DIR / "course_vid_long.json").read_text())
n_total = -(-len(LONG) // 9000)
check("course progress saved, not finished in one go (chunked)", 0 < prog["done"] < n_total, f"{prog['done']}/{n_total}")
lessons = [l["text"] for l in prog["lessons"]]
check("lessons are concrete (numbers / rules), not welcome-talk", lessons and all("welcome" not in l.lower() for l in lessons) and any("%" in l or "percent" in l or "3x" in l for l in lessons), lessons[:3])
check("owner's course is resumable via pending_courses", "https://youtu.be/vid_long" in S.pending_courses() or any("vid_long" in u for u in S.pending_courses()), S.pending_courses())
before = prog["done"]
S.course_session("https://youtu.be/vid_long", max_chunks=3)
prog2 = json.loads((S_mod.config.STATE_DIR / "course_vid_long.json").read_text())
check("second session continues where it stopped", prog2["done"] == min(n_total, before + 3), f"{before} → {prog2['done']}")
check("course notes document in the library", any("course" in p.name.lower() for p in library.LIB_DIR.glob("*.html")))

# 4) quiet sessions cycle and prefer pending courses
kinds = []
S.pdf_session = lambda topic=None: (kinds.append("pdf") or "📚 pdf")
S.video_session = lambda query=None, urls=None: (kinds.append("video") or "💡 video")
S.brainstorm = lambda: (kinds.append("brain") or "🧠 brainstorm")
S.course_session = lambda url, max_chunks=None: (kinds.append("course") or "🎓 course")
for n in range(4):
    S.quiet_session(n)
check("quiet sessions: courses first when pending, then pdf/video/brainstorm mix", kinds.count("course") >= 1 and "video" in kinds or "pdf" in kinds, kinds)
S.pending_courses = lambda: []
kinds.clear()
for n in range(4):
    S.quiet_session(n)
check("quiet sessions without courses: pdf, video, pdf, brainstorm", kinds == ["pdf", "video", "pdf", "brain"], kinds)

# 5) owner's two videos are known and pending on a fresh state
shutil.rmtree(os.environ["BAI_STATE"], ignore_errors=True)
S2 = Study(tasks=None, planner=None, google=None, memory=None, log=lambda k, **f: None)
pend = S2.pending_courses()
check("fresh start: the owner's two courses are pending", any("DNdBJ5tgyjI" in u for u in pend) and any("vo6aDcnPzCU" in u for u in pend), pend)

ok = sum(1 for _, o in checks if o)
print(f"\nSCORE study {ok}/{len(checks)}  ({time.time() - t0:.1f}s)")
sys.exit(0 if ok == len(checks) else 1)
