"""Download ad creatives once and embed them as data URLs, so the phone feed, the buyer simulation and the
PDF all show the exact same image (Facebook CDN links are signed, expire and often block hot-linking)."""
from __future__ import annotations

import base64
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
_cache: dict[str, str | None] = {}


def to_data_url(url: str | None, max_bytes: int = 2_500_000) -> str | None:
    if not url or url.startswith("data:"):
        return url
    if url in _cache:
        return _cache[url]
    out = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.facebook.com/"})
        with urllib.request.urlopen(req, timeout=12) as r:
            mime = (r.headers.get_content_type() or "image/jpeg")
            data = r.read(max_bytes + 1)
        if mime.startswith("image/") and 0 < len(data) <= max_bytes:
            out = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    except Exception:
        out = None
    _cache[url] = out
    return out


def embed_many(urls: list[str | None]) -> list[str | None]:
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(to_data_url, urls))


def _video_media(url: str, max_bytes: int = 40_000_000) -> dict | None:
    """Download one ad video and return its key frames (data URLs), frame times and voiceover transcript."""
    import os
    import tempfile

    from .input_analyzer import extract_video

    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.facebook.com/"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read(max_bytes + 1)
        if not data or len(data) > max_bytes:
            return None
        path = os.path.join(tempfile.mkdtemp(), "ad.mp4")
        with open(path, "wb") as f:
            f.write(data)
        frames, transcript, times, meta = extract_video(path, n_frames=4)
        if not frames:
            return None
        return {"frames": ["data:image/jpeg;base64," + f for f in frames], "times": times, "transcript": transcript,
                "duration": meta["duration"]}
    except Exception:
        return None


def video_media(cards: list[dict]) -> dict[str, dict]:
    """{ad_id: {"frames", "times", "transcript"}} for every video ad in the feed (downloaded in parallel)."""
    vids = [c for c in cards if c.get("video")]
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(lambda c: _video_media(c["video"]), vids))
    return {c["id"]: r for c, r in zip(vids, res) if r}
