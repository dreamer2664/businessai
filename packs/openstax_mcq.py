"""Extract the multiple-choice "Knowledge Check" questions (with the marked correct answer)
from OpenStax books into a test bank. These pages are NOT part of the knowledge pack.

Usage: python3 packs/openstax_mcq.py packs/openstax_books.json tests/mcq_<slug>.jsonl <slug>
Each line: {"book","section","q","choices":[...],"answer": index}
"""
import html as H
import json
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import openstax_fetch as of  # noqa: E402


def txt(x):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def main():
    books = json.load(open(sys.argv[1]))
    out = open(sys.argv[2], "w", encoding="utf-8")
    slug = sys.argv[3]
    b = books[slug]
    n = 0
    for pid, title in b["pages"]:
        if not re.match(r"^\d+\.\d+\s", title):
            continue
        url = f"https://openstax.org/apps/archive/{b['ver']}/contents/{b['uuid']}@{b['sha']}:{pid.split('@')[0]}.json"
        try:
            h = json.loads(of.get(url)).get("content", "")
        except Exception as e:
            print("!", title, e); continue
        for q in re.finditer(r'<div data-type="exercise-question"[^>]*data-formats="multiple-choice".*?</ol>', h, re.S):
            block = q.group(0)
            stem = re.search(r'data-type="question-stem">(.*?)</div>\s*<ol', block, re.S)
            if not stem:
                continue
            stem = txt(stem.group(1))
            choices, answer = [], None
            for i, li in enumerate(re.finditer(r'<li data-type="question-answer" data-correctness="([\d.]+)">(.*?)</li>', block, re.S)):
                choices.append(txt(li.group(2)))
                if float(li.group(1)) >= 1.0:
                    answer = i
            if answer is None or len(choices) < 3 or len(stem) < 15:
                continue
            out.write(json.dumps({"book": slug, "section": re.sub(r"^[\d.\s]+", "", title), "q": stem,
                                  "choices": choices, "answer": answer}, ensure_ascii=False) + "\n")
            n += 1
    print(slug, n, "questions")


if __name__ == "__main__":
    main()
