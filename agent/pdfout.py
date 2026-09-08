"""HTML → PDF with the browser we already have (headless Chromium via Playwright), in a separate process so it never
touches the hands thread. Used for shipping labels / packing slips and any document that must print cleanly from a phone.
No extra libraries: falls back to None when Playwright/Chromium is missing — the caller then sends the HTML instead."""
import pathlib
import subprocess
import sys

_CHILD = r'''
import sys
from playwright.sync_api import sync_playwright
src, dst = sys.argv[1], sys.argv[2]
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
    pg = b.new_page()
    pg.goto("file://" + src, wait_until="load")
    pg.pdf(path=dst, format="A4", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
    b.close()
print("ok")
'''


def html_to_pdf(html_path, pdf_path=None, timeout=90):
    """Return the PDF path (pathlib.Path) or None if the conversion is not possible on this machine."""
    src = pathlib.Path(html_path).resolve()
    dst = pathlib.Path(pdf_path) if pdf_path else src.with_suffix(".pdf")
    try:
        r = subprocess.run([sys.executable, "-c", _CHILD, str(src), str(dst)], capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    if r.returncode == 0 and dst.exists() and dst.stat().st_size > 500:
        return dst
    return None
