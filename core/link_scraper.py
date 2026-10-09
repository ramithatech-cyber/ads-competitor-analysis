"""Scrape an ad / product / landing-page link so it can be analysed like a text, image or video input.

Runs as a standalone subprocess so Playwright gets its own event loop (same as ads_scraper):

    python -m core.link_scraper --url https://example.com/product --out page.json

Output JSON: {"url", "final_url", "kind": "page|image|video", "title", "description", "site_name",
              "text", "image_file", "image_mime", "video_file", "video_mime"}
A direct image/video URL is downloaded as-is; a web page is rendered and its meta tags + visible text are read.
If the page carries a video (og:video, a <video> tag, or a reel/post on Instagram, Facebook, YouTube, TikTok, X...)
the video is downloaded (yt-dlp for social platforms) so it gets the full video analysis; otherwise its preview
image (og:image) is downloaded so it gets the full image analysis.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
MAX_TEXT = 6000
MAX_MEDIA = 60 * 1024 * 1024
MAX_VIDEO_SECONDS = 600
# Platforms whose videos are streamed (blob:/DASH) and need yt-dlp to download.
VIDEO_HOSTS = ("instagram.com", "facebook.com", "fb.watch", "youtube.com", "youtu.be", "tiktok.com", "x.com",
               "twitter.com", "linkedin.com", "vimeo.com", "dailymotion.com", "threads.net")
EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
       "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}

META_JS = """() => {
  const m = (sel) => { const el = document.querySelector(sel); return el ? (el.content || el.getAttribute('href') || '').trim() : '' };
  const imgs = [...document.images].filter(i => i.naturalWidth >= 300 && i.naturalHeight >= 200)
    .sort((a, b) => b.naturalWidth * b.naturalHeight - a.naturalWidth * a.naturalHeight).map(i => i.currentSrc || i.src);
  return {
    title: m('meta[property="og:title"]') || m('meta[name="twitter:title"]') || document.title || '',
    description: m('meta[property="og:description"]') || m('meta[name="description"]') || m('meta[name="twitter:description"]'),
    site_name: m('meta[property="og:site_name"]'),
    image: m('meta[property="og:image"]') || m('meta[property="og:image:url"]') || m('meta[name="twitter:image"]') || imgs[0] || '',
    images: imgs.slice(0, 3),
    video: m('meta[property="og:video:secure_url"]') || m('meta[property="og:video:url"]') || m('meta[property="og:video"]'),
    video_tags: [...document.querySelectorAll('video, video source')].map(v => v.currentSrc || v.src || '')
      .filter(u => /^https?:/.test(u)),
    og_type: m('meta[property="og:type"]'),
    text: (document.body ? document.body.innerText : '').replace(/\\n{3,}/g, '\\n\\n').trim(),
  }
}"""


def _media_type(url: str) -> str | None:
    """Content-Type of a URL if it is a direct image/video file, else None."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as r:
            ct = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    except Exception:
        ct = ""
    if not ct:
        path = url.split("?")[0].lower()
        for ext, mime in ((".jpg", "image/jpeg"), (".jpeg", "image/jpeg"), (".png", "image/png"), (".webp", "image/webp"),
                          (".mp4", "video/mp4"), (".webm", "video/webm"), (".mov", "video/quicktime")):
            if path.endswith(ext):
                return mime
    return ct if ct.startswith(("image/", "video/")) else None


def _save(data: bytes, mime: str) -> str:
    path = os.path.join(tempfile.mkdtemp(), "media" + EXT.get(mime, ".bin"))
    with open(path, "wb") as f:
        f.write(data)
    return path


def _download(ctx, url: str, attempts: int = 3) -> tuple[bytes, str] | None:
    for i in range(attempts):  # CDNs (Instagram/Facebook) sometimes reset the first connection
        try:
            r = ctx.request.get(url, timeout=30000)
            mime = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
            body = r.body()
            if r.ok and mime.startswith(("image/", "video/")) and 0 < len(body) <= MAX_MEDIA:
                return body, mime
            if r.status < 500:
                return None
        except Exception as e:
            if i == attempts - 1:
                print(f"Could not download {url[:80]}: {str(e).splitlines()[0]}", flush=True)
        time.sleep(1 + i)
    return None


def _ytdlp(url: str) -> tuple[str, str] | None:
    """Download a social-media video (reel, post, short) as one mp4 with audio, or None if there is no video."""
    try:
        import imageio_ffmpeg
        import yt_dlp
    except ImportError:
        print("yt-dlp not installed: run  pip install yt-dlp  to read videos from social links", flush=True)
        return None
    folder = tempfile.mkdtemp()
    class _Silent:  # yt-dlp's own progress/deprecation output would flood the job log
        def debug(self, msg): pass
        def info(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): pass
    opts = {"outtmpl": os.path.join(folder, "video.%(ext)s"), "noplaylist": True, "quiet": True, "no_warnings": True,
            "noprogress": True, "logger": _Silent(),
            "format": "b[ext=mp4][vcodec!=none][acodec!=none]/bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b",
            "merge_output_format": "mp4", "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
            "max_filesize": MAX_MEDIA, "user_agent": USER_AGENT,
            "match_filter": lambda info, *a, **k: None if (info.get("duration") or 0) <= MAX_VIDEO_SECONDS
            else "video longer than 10 minutes"}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        print(f"No downloadable video at this link ({str(e).splitlines()[0][:120]})", flush=True)
        return None
    if info and info.get("_type") == "playlist":  # carousel: take the first video in it
        info = next((e for e in info.get("entries") or [] if e), None)
    files = [os.path.join(folder, f) for f in os.listdir(folder) if not f.endswith((".part", ".ytdl"))]
    vids = [f for f in files if f.lower().endswith((".mp4", ".webm", ".mov", ".mkv"))]
    if not vids:
        return None
    path = max(vids, key=os.path.getsize)
    ext = os.path.splitext(path)[1].lower()
    return path, {".webm": "video/webm", ".mov": "video/quicktime", ".mkv": "video/x-matroska"}.get(ext, "video/mp4")


def scrape(url: str) -> dict:
    out = {"url": url, "final_url": url, "kind": "page", "title": "", "description": "", "site_name": "",
           "text": "", "image_file": None, "image_mime": None, "video_file": None, "video_mime": None}
    direct = _media_type(url)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=USER_AGENT, locale="en-IN", viewport={"width": 1280, "height": 900})
        try:
            if direct:
                got = _download(ctx, url)
                if not got:
                    raise RuntimeError("Could not download the media file at this link")
                data, mime = got
                kind = "video" if mime.startswith("video/") else "image"
                out.update(kind=kind, **{f"{kind}_file": _save(data, mime), f"{kind}_mime": mime})
                print(f"Downloaded {kind} ({len(data) // 1024} KB)", flush=True)
                return out

            page = ctx.new_page()
            print(f"Opening {url}", flush=True)
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass  # busy pages never go idle; what has loaded is enough
            meta = page.evaluate(META_JS)
            out["final_url"] = page.url
            out.update({k: (meta.get(k) or "").strip() for k in ("title", "description", "site_name")})
            # Instagram/Facebook: '12 likes, 3 comments - brand on May 1, 2026: "caption"' -> the caption itself.
            m = re.match(r'^[\d,.]+[KM]? likes?, [\d,.]+[KM]? comments? - .+? on [^:]+: "(.*)"\.?$', out["description"], re.S)
            if m:
                out["description"] = m.group(1).strip()
            out["text"] = (meta.get("text") or "")[:MAX_TEXT]
            print(f"Read page: {out['title'][:80] or '(no title)'} · {len(out['text'])} chars", flush=True)

            # Video first: a reel/video post gets the full video analysis (frames + voiceover + timeline).
            host = (urlparse(out["final_url"]).hostname or "").lower()
            social = any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS)
            for v in [meta.get("video")] + (meta.get("video_tags") or []):
                if v and not social:
                    got = _download(ctx, page.evaluate("(u) => new URL(u, location.href).href", v))
                    if got and got[1].startswith("video/"):
                        out.update(kind="video", video_file=_save(*got), video_mime=got[1])
                        print(f"Downloaded video from the page ({len(got[0]) // 1024} KB)", flush=True)
                        break
            has_video_hint = bool(meta.get("video") or meta.get("video_tags")
                                  or (meta.get("og_type") or "").startswith("video"))
            if out["kind"] != "video" and (social or has_video_hint):
                print("Looking for a video in this post…", flush=True)
                got = _ytdlp(out["final_url"])
                if got:
                    out.update(kind="video", video_file=got[0], video_mime=got[1])
                    print(f"Downloaded video ({os.path.getsize(got[0]) // 1024} KB)", flush=True)

            for img in dict.fromkeys(u for u in [meta.get("image")] + (meta.get("images") or []) if u):
                got = _download(ctx, page.evaluate("(u) => new URL(u, location.href).href", img))
                if got and got[1].startswith("image/"):
                    out["image_file"], out["image_mime"] = _save(*got), got[1]
                    print(f"Downloaded {'poster' if out['kind'] == 'video' else 'ad'} image ({len(got[0]) // 1024} KB)", flush=True)
                    break
        finally:
            browser.close()
    if not (out["title"] or out["description"] or out["text"] or out["image_file"] or out["video_file"]):
        raise RuntimeError("The page returned no readable content (it may need a login)")
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # page titles can contain any character
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if not re.match(r"^https?://", a.url, re.I):
        print("Link must start with http:// or https://", flush=True)
        sys.exit(2)
    try:
        res = scrape(a.url)
    except Exception as e:
        print(f"Link scraping failed: {e}", flush=True)
        sys.exit(1)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
