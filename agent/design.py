"""Logos and social banners without paid tools: clean SVG built from the shop's name, colours and product theme, rendered
to PNG with the headless browser we already have (agent.pdfout's Chromium). Three logo styles are proposed side by side
(wordmark / monogram badge / icon + name) so the owner picks one instead of getting a single guess. Everything is
deterministic and small — no image model, no fonts to download (system-ui / serif stacks render everywhere)."""
import html
import pathlib
import re
import subprocess
import sys

from . import config

# theme → (accent colour, soft background, icon key)
THEMES = [
    (re.compile(r"\b(eco|green|nest|bamboo|natural|bio|leaf|plant|garden|earth|organic|sustainab|cork|beeswax)\b", re.I), ("#2f5d3a", "#eef5ef", "leaf")),
    (re.compile(r"\b(coffee|caf[eè]|roast|bean|espresso|tea)\b", re.I), ("#5b3a29", "#faf6f0", "cup")),
    (re.compile(r"\b(sea|ocean|marine|blue|wave|surf|beach)\b", re.I), ("#1f5f8b", "#eef5fb", "wave")),
    (re.compile(r"\b(light|lamp|led|sun|solar|bright|glow)\b", re.I), ("#b8742a", "#fff8ee", "spark")),
    (re.compile(r"\b(pet|dog|cat|vet|paw)\b", re.I), ("#2a6f4e", "#eef7f2", "paw")),
    (re.compile(r"\b(baby|kids|toy|child)\b", re.I), ("#c2557a", "#fdf3f8", "star")),
    (re.compile(r"\b(tech|gadget|phone|digital|pixel|byte|cloud)\b", re.I), ("#274060", "#f2f5f9", "dot")),
    (re.compile(r"\b(home|house|casa|interior|deco|nordic|living)\b", re.I), ("#444444", "#f6f6f6", "house")),
]

ICONS = {
    "leaf": "<path d='M50 88 C20 70 18 30 60 12 C70 50 60 75 50 88 Z' fill='{a}'/><path d='M50 86 C48 60 56 40 62 20' stroke='{bg}' stroke-width='4' fill='none' stroke-linecap='round'/>",
    "cup": "<path d='M22 34 h48 v26 a24 24 0 0 1 -48 0 z' fill='{a}'/><path d='M70 40 h8 a10 10 0 0 1 0 20 h-8' stroke='{a}' stroke-width='6' fill='none'/><path d='M36 14 q4 8 0 16 M50 14 q4 8 0 16' stroke='{a}' stroke-width='4' fill='none' stroke-linecap='round'/>",
    "wave": "<path d='M10 55 q15 -20 30 0 t30 0 t30 0' stroke='{a}' stroke-width='9' fill='none' stroke-linecap='round'/><path d='M10 75 q15 -20 30 0 t30 0 t30 0' stroke='{a}' stroke-width='9' fill='none' stroke-linecap='round' opacity='.55'/>",
    "spark": "<circle cx='50' cy='50' r='16' fill='{a}'/>" + "".join(f"<line x1='50' y1='50' x2='{50 + 40 * __import__('math').cos(i * 0.785):.1f}' y2='{50 + 40 * __import__('math').sin(i * 0.785):.1f}' stroke='{{a}}' stroke-width='6' stroke-linecap='round' transform='translate(0 0)' opacity='.8'/>" for i in range(8)),
    "paw": "<ellipse cx='50' cy='62' rx='18' ry='15' fill='{a}'/><circle cx='30' cy='42' r='8' fill='{a}'/><circle cx='44' cy='30' r='8' fill='{a}'/><circle cx='58' cy='30' r='8' fill='{a}'/><circle cx='72' cy='42' r='8' fill='{a}'/>",
    "star": "<path d='M50 12 l11 26 28 2 -21 18 7 27 -25 -15 -25 15 7 -27 -21 -18 28 -2 z' fill='{a}'/>",
    "dot": "<circle cx='36' cy='36' r='14' fill='{a}'/><circle cx='66' cy='36' r='14' fill='{a}' opacity='.6'/><circle cx='36' cy='66' r='14' fill='{a}' opacity='.6'/><circle cx='66' cy='66' r='14' fill='{a}' opacity='.3'/>",
    "house": "<path d='M18 52 L50 22 L82 52' stroke='{a}' stroke-width='8' fill='none' stroke-linecap='round' stroke-linejoin='round'/><path d='M28 48 v34 h44 v-34' stroke='{a}' stroke-width='8' fill='none' stroke-linejoin='round'/>",
}

_CHILD = r'''
import sys
from playwright.sync_api import sync_playwright
src, dst, w, h = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
    pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
    pg.goto("file://" + src, wait_until="load")
    # exact fit: shrink any <text data-fit> whose measured width exceeds its allowed box (the SVG has no text wrapping)
    pg.evaluate("""() => { const groups = {};
        for (const t of document.querySelectorAll('text[data-fit]')) {
            const maxw = parseFloat(t.getAttribute('data-fit')); let fs = parseFloat(t.getAttribute('font-size'));
            let n = 0; while (t.getComputedTextLength() > maxw && fs > 10 && n++ < 40) { fs *= 0.95; t.setAttribute('font-size', fs.toFixed(1)); }
            const g = t.getAttribute('data-group'); if (g) { groups[g] = Math.min(groups[g] || 1e9, fs); } }
        for (const t of document.querySelectorAll('text[data-group]')) {          // lines of one headline share the smallest size that fits
            const g = t.getAttribute('data-group'); const fs0 = parseFloat(t.getAttribute('data-fs0') || t.getAttribute('font-size'));
            t.setAttribute('font-size', groups[g].toFixed(1));
            const shift = (fs0 - groups[g]) * 0.5; if (shift > 0) { t.setAttribute('y', (parseFloat(t.getAttribute('y')) - shift * parseInt(t.getAttribute('data-i') || 0)).toFixed(1)); } } }""")
    pg.screenshot(path=dst, omit_background=False)
    b.close()
print("ok")
'''


def theme_for(name, hint=""):
    txt = f"{name} {hint}"
    for rx, th in THEMES:
        if rx.search(txt):
            return th
    return ("#2f2f4f", "#f4f4f8", "star")


def _initials(name):
    words = [w for w in re.split(r"[\s\-—&]+", name) if w and w.lower() not in ("the", "and", "of", "di", "e", "il", "la")]
    return "".join(w[0] for w in words[:2]).upper() or name[:1].upper()


def logo_svgs(name, tagline="", hint=""):
    """→ list of (style, svg_text). Three different styles, same colours, so the owner compares like for like."""
    accent, bg, icon_key = theme_for(name, hint)
    icon = ICONS[icon_key].format(a=accent, bg=bg)
    n, tg, ini = html.escape(name), html.escape(tagline), html.escape(_initials(name))
    size = 64 if len(name) <= 12 else (48 if len(name) <= 18 else 36)
    out = []
    out.append(("wordmark", f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 260' width='800' height='260'>
<rect width='800' height='260' fill='white'/>
<text data-fit='720' x='400' y='{130 if not tagline else 118}' text-anchor='middle' font-family='Georgia, "DejaVu Serif", serif' font-size='{size + 8}' font-weight='700' fill='{accent}' letter-spacing='2'>{n}</text>
<rect x='340' y='{150 if not tagline else 138}' width='120' height='5' rx='2' fill='{accent}' opacity='.6'/>
{f"<text x='400' y='190' text-anchor='middle' font-family='system-ui, sans-serif' font-size='22' fill='#555' letter-spacing='5'>{tg.upper()}</text>" if tagline else ""}
</svg>"""))
    out.append(("badge", f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 260' width='800' height='260'>
<rect width='800' height='260' fill='white'/>
<circle cx='150' cy='130' r='100' fill='{accent}'/>
<circle cx='150' cy='130' r='88' fill='none' stroke='{bg}' stroke-width='3' opacity='.7'/>
<text x='150' y='{152 if len(ini) == 1 else 150}' text-anchor='middle' font-family='Georgia, "DejaVu Serif", serif' font-size='{96 if len(ini) == 1 else 76}' font-weight='700' fill='white'>{ini}</text>
<text data-fit='480' x='290' y='{122 if tagline else 145}' font-family='system-ui, sans-serif' font-size='{size}' font-weight='700' fill='#1b1b1b'>{n}</text>
{f"<text x='292' y='165' font-family='system-ui, sans-serif' font-size='22' fill='{accent}' letter-spacing='4'>{tg.upper()}</text>" if tagline else ""}
</svg>"""))
    out.append(("icon", f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 260' width='800' height='260'>
<rect width='800' height='260' fill='white'/>
<rect x='60' y='40' width='180' height='180' rx='36' fill='{bg}'/>
<g transform='translate(80 60) scale(1.4)'>{icon}</g>
<text data-fit='480' x='290' y='{122 if tagline else 145}' font-family='system-ui, sans-serif' font-size='{size}' font-weight='600' fill='{accent}'>{n}</text>
{f"<text x='292' y='165' font-family='system-ui, sans-serif' font-size='22' fill='#555'>{tg}</text>" if tagline else ""}
</svg>"""))
    return out


def banner_svg(name, headline, sub="", hint="", size=(1080, 1080)):
    """A square (Instagram) or wide (Facebook) banner: colour block, big headline, shop name small. No photos needed."""
    accent, bg, icon_key = theme_for(name, hint)
    w, h = size
    icon = ICONS[icon_key].format(a=accent, bg=bg)
    headline = re.sub(r"(€|\$|£)\s+(\d)", "\\1\\2", headline)                # "€ 39" stays together on a line
    # pick the biggest size whose wrap fits in ≤ 4 lines; bold serif ≈ 0.6 em per character on average
    max_lines = 4 if h > w else (2 if w > h * 1.5 else 3)

    def _wid(txt):                                                                # rough advance width in em for a bold serif
        return sum(0.72 if ch.isupper() or ch in "%€$£@" else (0.6 if ch.isdigit() or ch in "mw" else (0.3 if ch in " .,:;'!il|" else 0.55)) for ch in txt)

    lines = []
    for fs in (110, 96, 84, 72, 64, 56, 48, 40, 34):
        cap_em = w * 0.82 / fs
        words, lines, cur = headline.split(), [], ""
        for wd in words:
            if _wid((cur + " " + wd).strip()) > cap_em and cur:
                lines.append(cur)
                cur = wd
            else:
                cur = (cur + " " + wd).strip()
        if cur:
            lines.append(cur)
        if len(lines) <= max_lines and all(_wid(l) <= cap_em for l in lines):
            break
    lines = lines[:max_lines]
    lines = [re.sub(r"(€|\$|£)(\d)", "\\1 \\2", l) for l in lines]
    y0 = h * 0.46 - (len(lines) - 1) * fs * 0.62
    text = "".join(f"<text data-fit='{w * 0.84:.0f}' data-group='h' data-fs0='{fs}' data-i='{i}' x='{w * 0.09:.0f}' y='{y0 + i * fs * 1.15:.0f}' font-family='Georgia, \"DejaVu Serif\", serif' font-size='{fs}' font-weight='700' fill='#1b1b1b'>{html.escape(l)}</text>" for i, l in enumerate(lines))
    sfs = max(28, int(fs * 0.38))
    scap = max(8, int(w * 0.84 / (sfs * 0.55)))
    sub_lines = []
    if sub:
        cur = ""
        for wd in sub.split():
            if len(cur) + len(wd) + 1 > scap and cur:
                sub_lines.append(cur)
                cur = wd
            else:
                cur = (cur + " " + wd).strip()
        if cur:
            sub_lines.append(cur)
        sub_lines = sub_lines[:2]
    sub_svg = "".join(f"<text data-fit='{w * 0.84:.0f}' x='{w * 0.09:.0f}' y='{y0 + (len(lines) - 1) * fs * 1.15 + fs * 0.9 + i * sfs * 1.3:.0f}' font-family='system-ui, sans-serif' font-size='{sfs}' fill='#444'>{html.escape(l)}</text>" for i, l in enumerate(sub_lines))
    return f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {w} {h}' width='{w}' height='{h}'>
<rect width='{w}' height='{h}' fill='{bg}'/>
<rect x='0' y='0' width='{w * 0.035:.0f}' height='{h}' fill='{accent}'/>
<g transform='translate({w * 0.78:.0f} {h * 0.04:.0f}) scale({w / 620:.2f})' opacity='.16'>{icon}</g>
{text}
{sub_svg}
<text x='{w * 0.09:.0f}' y='{h * 0.9:.0f}' font-family='system-ui, sans-serif' font-size='{fs * 0.38:.0f}' font-weight='700' fill='{accent}' letter-spacing='3'>{html.escape(name.upper())}</text>
</svg>"""


def render_png(svg_text, out_path, width, height, timeout=60):
    """SVG → PNG (2× for crisp phones) via headless Chromium. Returns the PNG path or None (the SVG is always kept)."""
    out = pathlib.Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    svg_path = out.with_suffix(".svg")
    svg_path.write_text(svg_text, encoding="utf-8")
    html_path = out.with_suffix(".html")
    html_path.write_text(f"<!doctype html><html><body style='margin:0;background:white'>{svg_text}</body></html>", encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, "-c", _CHILD, str(html_path.resolve()), str(out.resolve()), str(width), str(height)], capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 1000:
            return out
    except Exception:
        pass
    return None


def make_logos(name, tagline="", hint="", out_dir=None):
    """→ list of dicts {style, svg, png} written under <state>/design/logos/."""
    out_dir = pathlib.Path(out_dir) if out_dir else config.STATE_DIR / "design" / "logos"
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "shop"
    res = []
    for style, svg in logo_svgs(name, tagline, hint):
        png = render_png(svg, out_dir / f"{slug}-{style}.png", 800, 260)
        res.append({"style": style, "svg": str((out_dir / f"{slug}-{style}.svg")), "png": str(png) if png else None})
    return res


def make_banner(name, headline, sub="", hint="", platform="instagram", out_dir=None):
    out_dir = pathlib.Path(out_dir) if out_dir else config.STATE_DIR / "design" / "banners"
    size = (1080, 1080) if platform in ("instagram", "ig", "square") else ((1080, 1920) if platform in ("story", "stories", "reel") else (1200, 630))
    slug = re.sub(r"[^a-z0-9]+", "-", headline.lower()).strip("-")[:30] or "banner"
    svg = banner_svg(name, headline, sub, hint, size)
    png = render_png(svg, out_dir / f"{slug}-{platform}.png", *size)
    return {"svg": str(out_dir / f"{slug}-{platform}.svg"), "png": str(png) if png else None, "size": size}
