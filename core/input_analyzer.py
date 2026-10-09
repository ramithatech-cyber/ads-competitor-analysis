"""Understand the user's input (text / image / video / scraped link) with OpenAI and build a product profile."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile

from .llm import chat_json, get_client, with_retry

PROFILE_PROMPT = """You are a senior performance-marketing strategist.
Analyse the advertisement / product material provided and return JSON with exactly these keys:
{
  "brand_name": "brand if visible/known else null",
  "product": "what is being sold, short",
  "category": "SPECIFIC product category a buyer would compare against, e.g. 'whey protein supplement' or 'generative AI certification course' (never vague like 'online course' or 'product')",
  "industry": "broad industry",
  "key_features": ["..."],
  "target_audience": "who it is for",
  "usp": "main unique selling proposition",
  "tone": "tone/style of the creative",
  "offer": "discount/offer if any else null",
  "hook": "the opening hook quoted VERBATIM (keep every word): for text/image the first line or main headline; for a video the first spoken sentence from the transcript, or the opening frame's text if nobody speaks; else null",
  "on_creative_text": "all text visible on the image/frames, verbatim, including non-English words, else null",
  "cta": "call to action if any else null",
  "creative_summary": "2-3 sentence description of the input",
  "self_names": ["every name that identifies the ADVERTISER itself, as written/spoken: brand and company names, the founder's / presenter's / speaker's name if they introduce themselves or it is shown, social handles"],
  "websites": ["website domains or URLs shown, spoken or linked for the advertiser, e.g. 'socialeagle.ai'"],
  "search_keywords": ["4-6 keyword phrases (2-3 words, no brand names) that DIRECT competitors selling the same thing in India literally write in their Facebook ad copy, most specific first"]
}
Rules: only state what is visible or given. Never invent offers, prices, numbers or features. Keywords must name the
specific product type (e.g. 'generative ai course', 'ai agents course', not 'online course', 'learning', 'career').
Only output JSON."""


def _img_part(b64: str, mime: str = "image/jpeg") -> dict:
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "low"}}


def extract_video(path: str, n_frames: int = 6, transcribe: bool = True) -> tuple[list[str], str, list[float], dict]:
    """Return (base64 jpeg frames, transcript, frame times in seconds, {"duration", "segments"}).

    The first frame is taken at ~0.5s so the opening (the hook) is always seen, then n_frames evenly spaced.
    segments = [{"start", "end", "text"}] of the voiceover, so points about the audio can be placed in time."""
    import cv2

    frames: list[str] = []
    times: list[float] = []
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    meta = {"duration": round(total / fps, 1) if total else None, "segments": []}
    idxs = [int(total * (i + 0.5) / n_frames) for i in range(n_frames)] if total else []
    if total:
        idxs = sorted({min(total - 1, int(fps * 0.5)), *idxs})
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = 768 / max(h, w)
        if scale < 1:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            frames.append(base64.b64encode(buf.tobytes()).decode())
            times.append(round(i / fps, 1))
    cap.release()

    transcript = ""
    if not transcribe:
        return frames, transcript, times, meta
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        audio = os.path.join(tempfile.mkdtemp(), "audio.mp3")
        subprocess.run([ffmpeg, "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", audio],
                       capture_output=True, check=True, timeout=180)
        if os.path.getsize(audio) > 1000:
            model = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")
            with open(audio, "rb") as f:
                def verbose():
                    f.seek(0)
                    return get_client().audio.transcriptions.create(model=model, file=f, response_format="verbose_json")
                try:  # timestamped segments (whisper-1); fall back to plain text for models without them
                    res = with_retry(verbose)
                    meta["segments"] = [{"start": round(float(g.start), 1), "end": round(float(g.end), 1),
                                         "text": g.text.strip()} for g in (getattr(res, "segments", None) or [])]
                except Exception:
                    f.seek(0)
                    res = with_retry(lambda: (f.seek(0), get_client().audio.transcriptions.create(model=model, file=f))[1])
                transcript = res.text
    except Exception:  # video without audio, etc.
        transcript = ""
    return frames, (transcript or "").strip(), times, meta


def analyze_input(kind: str, text: str = "", file_bytes: bytes | None = None,
                  file_name: str = "", mime: str = "", page: dict | None = None) -> dict:
    """page = what core.link_scraper read from the user's link (title, description, visible text)."""
    content: list = [{"type": "text", "text": f"Input type: {kind}"}]
    extra = {}
    if text:
        content.append({"type": "text", "text": f"Text / description provided by user:\n{text}"})
    if page:
        info = {k: page.get(k) for k in ("final_url", "site_name", "title", "description") if page.get(k)}
        content.append({"type": "text", "text": "The user gave a LINK. Content scraped from that page "
                        "(meta tags, then visible text; ignore navigation, cookie and login boilerplate):\n"
                        + json.dumps(info, ensure_ascii=False) + "\n\n" + (page.get("text") or "")[:6000]})

    if kind == "image" and file_bytes:
        content.append(_img_part(base64.b64encode(file_bytes).decode(), mime or "image/jpeg"))
    elif kind == "video" and file_bytes:
        suffix = os.path.splitext(file_name)[1] or ".mp4"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(file_bytes)
        tmp.close()
        frames, transcript, times, meta = extract_video(tmp.name, n_frames=8)
        extra = {"video_frames": frames, "transcript": transcript, "frame_times": times, "video_path": tmp.name, **meta}
        content.append({"type": "text", "text": f"Video audio transcript:\n{transcript or '(no speech)'}"})
        content.append({"type": "text", "text": f"{len(frames)} frames from the video follow, in order, taken at "
                        + ", ".join(f"{t}s" for t in times) + ". The first one is the opening (the hook):"})
        content += [_img_part(f) for f in frames]

    profile = chat_json([{"role": "system", "content": PROFILE_PROMPT},
                         {"role": "user", "content": content}])
    profile["input_type"] = kind
    profile["_raw_text"] = text or ""
    if page:
        profile["source_url"] = page.get("final_url") or page.get("url")
    if extra.get("transcript"):
        profile["transcript"] = extra["transcript"]
    profile["_frames"] = extra.get("video_frames", [])
    profile["_frame_times"] = extra.get("frame_times", [])
    profile["_video_path"] = extra.get("video_path")
    profile["_duration"] = extra.get("duration")
    profile["_segments"] = extra.get("segments") or []
    return profile
