"""Desktop — a screen the agent can look at and a mouse/keyboard it can move (milestone 7).

Where the screen comes from:
  * a real display (DISPLAY set — the owner's WSLg/X desktop): screenshots and clicks land on that desktop;
  * otherwise the agent's own private virtual display (Xvfb :99, 1280x800) started on demand — its browser opens
    there as a real window, so the same eyes/hands work everywhere.
Tools: scrot/xwd for screenshots, xdotool for mouse + keyboard (both free apt packages; install_desktop.sh).
Without them the agent can still see through the browser (Playwright screenshots) — see() falls back to that.

Safety (never bypassed):
  * every click/type is logged with a screenshot before and after (state/desktop/);
  * clicks on buttons whose OCR label looks like money/publish/destroy (buy, pay, checkout, place order, confirm,
    send, post, publish, delete, remove, submit, subscribe, sign in) are refused unless allow_actions=True — and the
    agent only sets that after the owner tapped Approve for that exact step;
  * typing never includes secrets (the .secrets file is never read by this module);
  * a hard cap of MAX_ACTIONS per task and a screenshot the owner can always request with /screen.
"""
import os
import shutil
import subprocess
import time

from . import config

SHOTS = config.STATE_DIR / "desktop"
VDISPLAY = os.environ.get("BAI_VDISPLAY", ":99")
VSIZE = os.environ.get("BAI_VSIZE", "1280x800")
DANGER = ("buy", "pay", "checkout", "place order", "order now", "confirm", "send", "post", "publish", "delete", "remove",
          "submit", "subscribe", "sign in", "log in", "login", "purchase", "complete", "agree", "accept all", "install")
MAX_ACTIONS = 40


class Desktop:
    def __init__(self, log=None, eyes=None):
        self.log = log or (lambda kind, **f: None)
        self.eyes = eyes
        self.display = os.environ.get("DISPLAY") or ""
        self.own_x = None                     # our Xvfb process, if we started one
        self.actions = 0
        self.allow_actions = False
        self.have_xdotool = bool(shutil.which("xdotool"))
        self.have_shot = bool(shutil.which("scrot") or shutil.which("import") or shutil.which("xwd"))
        SHOTS.mkdir(parents=True, exist_ok=True)

    # ---- display ------------------------------------------------------------------------
    def available(self):
        return bool(self.display or shutil.which("Xvfb")) and self.have_xdotool and self.have_shot

    def describe_status(self):
        if not self.have_xdotool or not self.have_shot:
            return "desktop: tools missing (sh scripts/install_desktop.sh) — I can still see through my browser"
        where = f"the real display {self.display}" if self.display and self.own_x is None else (f"my own virtual screen {VDISPLAY}" if self.own_x else "no screen yet (starts on first use)")
        return f"desktop: {where} · {self.actions} actions this session"

    def ensure_display(self):
        """Make sure there is a display to look at; start a private Xvfb if the machine has none."""
        if self.display and self._display_ok(self.display):
            return self.display
        if not shutil.which("Xvfb"):
            return ""
        if self.own_x is None or self.own_x.poll() is not None:
            if not self._display_ok(VDISPLAY):
                self.own_x = subprocess.Popen(["Xvfb", VDISPLAY, "-screen", "0", VSIZE + "x24", "-nolisten", "tcp"],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for _ in range(40):
                    if self._display_ok(VDISPLAY):
                        break
                    time.sleep(0.25)
                self.log("vdisplay_started", display=VDISPLAY, size=VSIZE)
        self.display = VDISPLAY
        os.environ["DISPLAY"] = VDISPLAY           # so a browser started later opens on it
        return self.display

    @staticmethod
    def _display_ok(disp):
        try:
            return subprocess.run(["xdpyinfo"], env=dict(os.environ, DISPLAY=disp), capture_output=True, timeout=5).returncode == 0
        except Exception:
            return False

    def _env(self):
        return dict(os.environ, DISPLAY=self.display or VDISPLAY)

    def size(self):
        try:
            out = subprocess.run(["xdpyinfo"], env=self._env(), capture_output=True, text=True, timeout=5).stdout
            import re
            m = re.search(r"dimensions:\s+(\d+)x(\d+)", out)
            return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        except Exception:
            return (0, 0)

    # ---- seeing ----------------------------------------------------------------------------
    def screenshot(self, tag="shot"):
        """PNG bytes of the whole screen (and a copy in state/desktop/). '' if no screen."""
        if not self.ensure_display():
            return b""
        path = SHOTS / f"{int(time.time() * 1000)}_{tag}.png"
        try:
            if shutil.which("scrot"):
                subprocess.run(["scrot", "-o", str(path)], env=self._env(), capture_output=True, timeout=15)
            elif shutil.which("import"):
                subprocess.run(["import", "-window", "root", str(path)], env=self._env(), capture_output=True, timeout=15)
            else:
                xwd = subprocess.run(["xwd", "-root", "-silent"], env=self._env(), capture_output=True, timeout=15).stdout
                from PIL import Image
                import io
                Image.open(io.BytesIO(xwd)).save(path)
            data = path.read_bytes()
            self._prune()
            return data
        except Exception as e:
            self.log("screenshot_failed", error=str(e)[:100])
            return b""

    def _prune(self, keep=60):
        shots = sorted(SHOTS.glob("*.png"))
        for p in shots[:-keep]:
            p.unlink(missing_ok=True)

    def see(self, question=None):
        """What is on the screen right now? → dict(shot=bytes, text=OCR text, description, warnings, answer)."""
        shot = self.screenshot("see")
        out = {"shot": shot, "text": "", "description": "", "warnings": [], "answer": ""}
        if not shot:
            out["description"] = "no screen available"
            return out
        if self.eyes:
            out["text"] = self.eyes.text(shot, limit=3000)
            d = self.eyes.describe(shot)
            out["description"] = f"{d['title']} — {d['summary']}".strip(" —")
            out["warnings"] = d["warnings"]
            out["kind"] = d["kind"]
            if question:
                out["answer"] = self.eyes.look(shot, question)
        return out

    # ---- acting ---------------------------------------------------------------------------
    def _guard(self, label):
        if self.actions >= MAX_ACTIONS:
            return "stopped: too many actions for one task — tell me to continue if this is right"
        low = (label or "").lower()
        if not self.allow_actions and any(d in low for d in DANGER):
            return f"refused: '{label}' looks like a money/publish/destroy button — I need your approval for that step"
        return ""

    def _xdo(self, *args):
        if not self.have_xdotool:
            return False
        r = subprocess.run(["xdotool", *args], env=self._env(), capture_output=True, timeout=20)
        return r.returncode == 0

    def move(self, x, y):
        return self._xdo("mousemove", str(int(x)), str(int(y)))

    def click(self, x, y, label="", button=1, double=False):
        """Click at screen pixels. `label` = what the agent believes it is clicking (for the safety guard + log)."""
        why = self._guard(label)
        if why:
            self.log("click_refused", x=x, y=y, label=label, why=why)
            return why
        before = self.screenshot("before")
        ok = self._xdo("mousemove", str(int(x)), str(int(y))) and self._xdo("click", *(["--repeat", "2"] if double else []), str(button))
        time.sleep(0.8)
        after = self.screenshot("after")
        self.actions += 1
        change = self.eyes.compare(before, after) if (self.eyes and before and after) else ""
        self.log("click", x=x, y=y, label=label[:60], ok=ok, change=change[:120])
        return f"clicked {label or f'({x},{y})'} → {change or 'done'}" if ok else "click failed"

    def click_text(self, text, occurrence=0):
        """Find `text` on the screen with OCR and click its centre."""
        shot = self.screenshot("find")
        if not shot or not self.eyes:
            return "cannot see the screen"
        hits = self.eyes.find(shot, text)
        if not hits:
            return f"could not find '{text}' on the screen"
        cx, cy, matched = hits[min(occurrence, len(hits) - 1)]
        return self.click(cx, cy, label=matched)

    def type(self, text, enter=False):
        """Type text where the cursor is (never secrets)."""
        if self.actions >= MAX_ACTIONS:
            return "stopped: too many actions"
        if any(k in text.lower() for k in ("password", "token", "secret", "cvv")):
            return "refused: I don't type passwords or card details"
        ok = self._xdo("type", "--delay", "20", "--", text)
        if ok and enter:
            ok = self._xdo("key", "Return")
        self.actions += 1
        self.log("type", chars=len(text), enter=enter, ok=ok)
        return "typed" if ok else "typing failed"

    def key(self, combo):
        """Press a key or combo, e.g. 'Return', 'ctrl+l', 'Page_Down', 'Escape'."""
        if self.actions >= MAX_ACTIONS:
            return "stopped: too many actions"
        if combo.lower() in ("alt+f4", "ctrl+alt+delete", "super+l"):
            return "refused: that key combination closes or locks things"
        ok = self._xdo("key", combo)
        self.actions += 1
        self.log("key", combo=combo, ok=ok)
        return f"pressed {combo}" if ok else "key failed"

    def scroll(self, down=True, times=3):
        for _ in range(times):
            self._xdo("click", "5" if down else "4")
        self.actions += 1
        return f"scrolled {'down' if down else 'up'}"

    def new_task(self, allow_actions=False):
        self.actions = 0
        self.allow_actions = allow_actions

    def stop(self):
        if self.own_x and self.own_x.poll() is None:
            self.own_x.terminate()
            try:
                self.own_x.wait(5)
            except Exception:
                self.own_x.kill()
        self.own_x = None
