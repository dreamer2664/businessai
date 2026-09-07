"""Fetch the web guides listed in packs/sources/web_urls.tsv (topic<TAB>url) as clean text.
   python3 packs/web_fetch.py packs/sources/web_urls.tsv ~/.cache/bai/web/web.tsv"""
import html, re, sys, time, urllib.request
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40) as r: return r.read().decode('utf-8', 'ignore')
def extract(h):
    h = re.sub(r'<(script|style|noscript|svg|nav|footer|header|form|aside|figure|iframe)\b.*?</\1>', ' ', h, flags=re.S | re.I)
    m = re.search(r'<article\b.*?</article>', h, re.S | re.I) or re.search(r'<main\b.*?</main>', h, re.S | re.I); body = m.group(0) if m else h
    t = re.search(r'<title>(.*?)</title>', h, re.S | re.I); title = html.unescape(t.group(1)).strip() if t else ''
    paras = []
    for m in re.finditer(r'<(h[1-4]|p|li)\b[^>]*>(.*?)</\1>', body, re.S | re.I):
        s = html.unescape(re.sub(r'<[^>]+>', ' ', m.group(2))); s = re.sub(r'\s+', ' ', s).strip()
        if not s: continue
        if m.group(1).lower().startswith('h'):
            if len(s) < 120: paras.append('## ' + s)
        elif len(s) >= 50 or (paras and paras[-1].startswith('## ') and len(s) >= 25): paras.append(s)
    return title, paras
src, dst = sys.argv[1], sys.argv[2]
try: have = set(l.split('\t')[2] for l in open(dst, encoding='utf-8') if l.count('\t') >= 3)
except FileNotFoundError: have = set()
out = open(dst, 'a', encoding='utf-8'); n = 0
for line in open(src, encoding='utf-8'):
    if '\t' not in line: continue
    topic, u = line.rstrip('\n').split('\t')[:2]
    if u in have: continue
    try:
        title, paras = extract(get(u)); txt = '\n'.join(paras)
        if len(txt) < (1000 if topic == 'eu-law' else 2000): print('thin', u); continue
        out.write(f"{title}\t{topic}\t{u}\t{txt.replace(chr(9), ' ').replace(chr(10), chr(92) + 'n')}\n"); out.flush(); n += 1
    except Exception as e: print('FAIL', u, str(e)[:60], flush=True)
    time.sleep(0.5)
print('fetched', n)
