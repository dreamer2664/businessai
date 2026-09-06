"""Fetch OpenStax business textbooks as clean text (no PDFs, no filler).

OpenStax books (CC BY 4.0) are served page-by-page as JSON containing the page
HTML. We keep only teaching prose: section headings and paragraphs. Dropped:
end-of-chapter material (key terms, summaries, exercises, cases), figure
captions, tables of contents, learning-objective lists, exhibits, links, and
"Preface"/"Index"/"Answer Key" pages.

Usage: python3 packs/openstax_fetch.py <books.json> <out_dir>
  books.json: {slug: {ver, sha, uuid, pages:[[id, title], ...]}}  (see packs/openstax_books.json)
Output: <out_dir>/<slug>.tsv — one section per line: title<TAB>chapter_title<TAB>text
"""
import html as htmlmod
import json
import os
import re
import sys
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (businessai pack builder; CC-BY content)"}
SKIP_TITLE = re.compile(r"^(preface|index|answer key|references|glossary|key terms|summary of learning outcomes|"
                        r"chapter review|critical thinking|ethics activity|working the net|creative thinking|"
                        r"preparing for tomorrow|hot links|team activity|managerial skills|business challenge|"
                        r"key points|review questions|managing your finances|management skills application|"
                        r"suggested resources|videos|case|multiple choice|discussion questions|casing|"
                        r"be the manager|chapter summary|summary|exercises|solutions|endnotes|bibliography)\b", re.I)
# blocks whose whole content we drop
DROP_BLOCK = re.compile(
    r'<(figure|table|iframe|aside|nav)\b.*?</\1>|'
    r'<div[^>]+data-type="(?:note|example|exercise|glossary|footnote-refs|equation)"[^>]*>.*?</div>|'
    r'<section[^>]+class="[^"]*(?:learning-objectives|key-terms|summary|review-questions|references|'
    r'critical-thinking|exercise|problem|casing)[^"]*"[^>]*>.*?</section>|'
    r'<span[^>]+data-type="(?:footnote-number|footnote-ref)"[^>]*>.*?</span>|'
    r'<span[^>]+class="os-number"[^>]*>.*?</span>', re.S | re.I)


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read().decode()
        except Exception as e:  # noqa
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def clean(page_html):
    h = page_html
    # OpenStax exercises/notes are nested divs; a regex can't match nesting, so strip by data-type openers iteratively
    for _ in range(3):
        h2 = DROP_BLOCK.sub(" ", h)
        if h2 == h:
            break
        h = h2
    paras = []
    # keep headings as their own short lines (they anchor retrieval)
    for m in re.finditer(r"<(h[1-6]|p|li)\b[^>]*>(.*?)</\1>", h, re.S | re.I):
        tag, inner = m.group(1).lower(), m.group(2)
        t = re.sub(r"<[^>]+>", " ", inner)
        t = htmlmod.unescape(t)
        t = re.sub(r"\s+", " ", t).strip()
        if not t:
            continue
        if tag.startswith("h"):
            if len(t) < 120:
                paras.append("## " + t)
            continue
        if tag == "li" and len(t) < 40:
            continue                      # bullet fragments carry little meaning alone
        if len(t) < 60 and not paras:
            continue
        # drop boilerplate lines
        if re.match(r"^(learning objectives?|by the end of this section|figure \d|exhibit \d|table \d|"
                    r"source:|credit:|\(credit|watch|visit|read|check out|link to learning|© )", t, re.I):
            continue
        paras.append(t)
    return paras


def main():
    books = json.load(open(sys.argv[1]))
    out_dir = sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    only = sys.argv[3].split(",") if len(sys.argv) > 3 else None
    for slug, b in books.items():
        if only and slug not in only:
            continue
        out = os.path.join(out_dir, slug + ".tsv")
        if os.path.exists(out):
            print(slug, "exists, skip"); continue
        n_pages = n_par = n_chars = 0
        chapter = ""
        with open(out + ".tmp", "w", encoding="utf-8") as f:
            for pid, title in b["pages"]:
                short = pid.split("@")[0]
                if re.match(r"^\d+(\.\d+)?$", title.strip()):
                    continue
                if SKIP_TITLE.search(re.sub(r"^[\d.\s]+", "", title)) or SKIP_TITLE.search(title):
                    continue
                if re.match(r"^introduction$", title.strip(), re.I):
                    pass  # chapter intros carry real prose; keep them
                url = f"https://openstax.org/apps/archive/{b['ver']}/contents/{b['uuid']}@{b['sha']}:{short}.json"
                try:
                    j = json.loads(get(url))
                except Exception as e:
                    print(f"  ! {slug} {title}: {e}"); continue
                paras = clean(j.get("content", ""))
                # chapter title = nearest heading in the tree; approximate by numbered title prefix
                m = re.match(r"^(\d+)\.\d+\s", title)
                if m:
                    chapter = f"ch{m.group(1)}"
                text = "\n".join(paras)
                if len(text) < 300:
                    continue
                f.write(f"{title}\t{chapter}\t{text.replace(chr(9), ' ')}\n".replace("\n", "\\n") + "\n")
                n_pages += 1; n_par += len(paras); n_chars += len(text)
        os.rename(out + ".tmp", out)
        print(f"{slug}: {n_pages} sections, {n_par} paragraphs, {n_chars/1e6:.2f} M chars", flush=True)


if __name__ == "__main__":
    main()
