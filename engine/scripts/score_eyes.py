"""Score the eyes: python3 engine/scripts/score_eyes.py [--no-model]   (draws test screens, checks OCR positions + vision answers)"""
import re, sys, time
sys.path.insert(0, ".")
from PIL import Image, ImageDraw, ImageFont
from agent.eyes import Eyes

def font(sz, bold=False):
    try:
        return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf", sz)
    except Exception:
        return ImageFont.load_default()

def draw_shop():
    W, H = 1024, 640
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im); F, FB, FS = font(18), font(26, True), font(14)
    d.rectangle([0, 0, W, 60], fill=(30, 60, 120)); d.text((20, 18), "Green Nest — Eco Home Store", font=FB, fill="white")
    d.text((700, 22), "Home   Shop   Cart (2)   Account", font=F, fill="white")
    d.rectangle([40, 100, 480, 520], outline=(200, 200, 200)); d.text((150, 290), "[product photo]", font=F, fill=(150, 150, 150))
    d.text((520, 110), "Bamboo Toothbrush Set (4 pcs)", font=FB, fill="black"); d.text((520, 160), "€ 12,90   incl. VAT", font=FB, fill=(20, 120, 20))
    d.text((520, 210), "In stock — ships in 2-3 business days", font=F, fill="black")
    d.text((520, 250), "Quantity:", font=F, fill="black"); d.rectangle([620, 244, 680, 276], outline="black"); d.text((640, 250), "1", font=F, fill="black")
    d.rectangle([520, 310, 760, 360], fill=(230, 120, 20)); d.text((560, 322), "Add to cart", font=FB, fill="white")
    d.rectangle([780, 310, 980, 360], outline=(30, 60, 120), width=2); d.text((820, 325), "Buy now", font=F, fill=(30, 60, 120))
    d.text((520, 400), "Email for restock alerts:", font=F, fill="black"); d.rectangle([520, 430, 860, 466], outline="black"); d.text((530, 438), "you@example.com", font=FS, fill=(130, 130, 130))
    d.rectangle([870, 430, 980, 466], fill=(30, 60, 120)); d.text((890, 438), "Notify me", font=F, fill="white")
    d.text((40, 560), "Free returns within 30 days · Customer reviews: 4.6/5 (213)", font=FS, fill=(80, 80, 80))
    return im

def draw_login():
    im = Image.new("RGB", (800, 500), "white"); d = ImageDraw.Draw(im); F = font(18)
    d.text((300, 60), "Sign in", font=font(26, True), fill="black"); d.text((250, 140), "Email", font=F, fill="black"); d.rectangle([250, 165, 550, 200], outline="black")
    d.text((250, 230), "Password", font=F, fill="black"); d.rectangle([250, 255, 550, 290], outline="black")
    d.rectangle([250, 320, 550, 360], fill=(30, 60, 120)); d.text((360, 330), "Sign in", font=F, fill="white"); d.text((250, 390), "Forgot password?", font=F, fill=(30, 60, 120))
    return im

def draw_captcha():
    im = Image.new("RGB", (800, 500), (245, 245, 245)); d = ImageDraw.Draw(im); F = font(18)
    d.text((200, 120), "Checking your browser before accessing the site", font=F, fill="black")
    d.rectangle([250, 220, 550, 300], fill="white", outline=(180, 180, 180)); d.rectangle([270, 245, 300, 275], outline="black", width=2)
    d.text((320, 250), "I'm not a robot", font=F, fill="black"); d.text((440, 280), "reCAPTCHA", font=font(12), fill=(120, 120, 120))
    return im

def draw_error():
    im = Image.new("RGB", (800, 500), "white"); d = ImageDraw.Draw(im)
    d.text((300, 150), "404", font=font(48, True), fill=(60, 60, 60)); d.text((230, 230), "Page not found", font=font(28), fill=(60, 60, 60))
    d.text((190, 290), "The page you are looking for does not exist.", font=font(18), fill=(100, 100, 100))
    return im

def draw_desktop():
    im = Image.new("RGB", (1280, 800), "white"); d = ImageDraw.Draw(im); F = font(18)
    d.rectangle([0, 0, 1280, 140], fill=(245, 245, 245)); d.text((20, 168), "Green Nest test", font=font(24, True), fill="black")
    d.rectangle([20, 230, 196, 282], fill=(230, 120, 20)); d.text((50, 245), "Add to cart", font=font(22), fill="white")
    d.rectangle([236, 236, 386, 284], fill=(240, 240, 240), outline=(120, 120, 120)); d.text((270, 249), "Pay now", font=font(20), fill="black")
    d.text((20, 320), "empty", font=font(24), fill="black"); d.rectangle([20, 380, 420, 420], outline=(120, 120, 120)); d.text((30, 390), "search here", font=F, fill=(150, 150, 150))
    return im

SCREENS = {"shop": draw_shop, "login": draw_login, "captcha": draw_captcha, "error": draw_error, "desktop": draw_desktop}
no_model = "--no-model" in sys.argv
E = Eyes(); imgs = {k: f() for k, f in SCREENS.items()}
rows = [l.rstrip("\n").split("\t") for l in open("tests/eyes.txt", encoding="utf-8") if l.strip() and not l.startswith("#")]
tot = ok = skipped = 0; t0 = time.time(); notes = []
try:
    for name, check, exp in rows:
        im = imgs[name]
        if check.startswith("find "):
            hits = E.find(im, check[5:]); ex, ey = map(int, exp.split(","))
            good = bool(hits) and abs(hits[0][0] - ex) <= 25 and abs(hits[0][1] - ey) <= 25; got = hits[:1]
        elif check == "kind":
            if no_model and not E.ocr: skipped += 1; continue
            d = E.describe(im); good = d["kind"] == exp or (exp in ("login", "captcha") and exp.replace("login", "login wall") in d["warnings"]); got = (d["kind"], d["warnings"])
        elif check.startswith("look "):
            if no_model: skipped += 1; continue
            a = E.look(im, check[5:]).lower(); good = any(x.lower() in a for x in exp.split("|")); got = a[:80]
        else:
            continue
        tot += 1; ok += good
        notes.append(f"  {'OK ' if good else 'MISS'} {name:8s} {check[:40]:40s} → {got}")
    print(f"TOTAL {ok}/{tot}" + (f" ({skipped} skipped without the model)" if skipped else "") + f"  ({time.time()-t0:.0f}s)"); print("\n".join(notes))
finally:
    E.stop()
