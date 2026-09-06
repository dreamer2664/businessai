"""'Watching' videos the frugal way: read their captions.

YouTube publishes captions (human or auto-generated) for most videos. We fetch the caption text through
YouTube's own public player endpoint — no API key, no login, no video download — and hand the transcript
to the thinking model for a summary. A 20-minute talk is ~120 KB of XML → ~20 KB of text.

    search(query, n)      -> [{"id", "title"}]
    transcript(video_id)  -> (plain text or "", meta{title, channel, seconds, language, auto})
    url_id(url_or_id)     -> 11-char video id or None
"""
import html
import json
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def url_id(s):
    s = s.strip()
    if _ID.match(s):
        return s
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", s)
    return m.group(1) if m else None


def search(query, n=8):
    u = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    page = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20).read().decode("utf-8", "replace")
    out, seen = [], set()
    for m in re.finditer(r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"(.*?)"longBylineText"', page):
        vid, blob = m.group(1), m.group(2)
        if vid in seen:
            continue
        seen.add(vid)
        t = re.search(r'"title":\{"runs":\[\{"text":"(.*?)"\}', blob)
        try:
            title = json.loads(f'"{t.group(1)}"') if t else vid
        except Exception:
            title = t.group(1) if t else vid
        out.append({"id": vid, "title": title})
        if len(out) >= n:
            break
    return out


def _tracks(video_id):
    """Caption tracks via the Android player client (the web client often returns empty caption files)."""
    body = json.dumps({"context": {"client": {"clientName": "ANDROID", "clientVersion": "20.10.38", "androidSdkVersion": 30, "hl": "en"}},
                       "videoId": video_id}).encode()
    req = urllib.request.Request("https://www.youtube.com/youtubei/v1/player?prettyPrint=false", data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip"})
    d = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace"))
    vd = d.get("videoDetails", {})
    tracks = d.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
    return tracks, {"title": vd.get("title", ""), "channel": vd.get("author", ""), "seconds": int(vd.get("lengthSeconds", 0) or 0)}


def transcript(video_id, prefer=("en", "en-US", "en-GB")):
    tracks, meta = _tracks(video_id)
    if not tracks:
        return "", meta
    track = next((t for p in prefer for t in tracks if t.get("languageCode") == p and t.get("kind") != "asr"), None) \
        or next((t for p in prefer for t in tracks if t.get("languageCode") == p), None) or tracks[0]
    xml = urllib.request.urlopen(urllib.request.Request(track["baseUrl"], headers=UA), timeout=30).read().decode("utf-8", "replace")
    parts = []
    for p in re.findall(r"<p[^>]*>(.*?)</p>", xml, re.S):
        txt = html.unescape(re.sub(r"<[^>]+>", "", p)).replace("\n", " ").strip()
        if txt:
            parts.append(txt)
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()
    meta["language"] = track.get("languageCode")
    meta["auto"] = track.get("kind") == "asr"
    return text, meta
