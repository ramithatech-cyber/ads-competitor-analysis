"""Deep dive on the user's own ad: hook, differentiation vs competitors, concrete improvements,
plus annotations pinned onto the creative itself."""
from __future__ import annotations

import base64
import json
import re

from .evidence import first_line, is_verbatim
from .llm import chat_json

COLS = "ABCDEFGHIJ"

REVIEW_PROMPT = """You are a world-class direct-response creative strategist reviewing a client's Facebook/Instagram ad
against the competitor ads currently running in the same market (India). Be specific and honest, quote real words
from the ads, never generic advice. Use the simulated buyer feedback (who stopped / scrolled and why) as evidence.
The output is shown VISUALLY to a busy founder: every label must be glanceable. Respect the word limits strictly.
Rules:
- If a creative image is attached, first read EVERY piece of text on it exactly as written (including words in Tamil,
  Hindi or other languages, badges, logos, tool names). Quote the hook verbatim, never paraphrase it.
- Language, region, format, price, guarantee, mentorship etc. can be differentiators; check each competitor before
  calling something unique or shared.
- An explicit language-of-delivery claim (e.g. "in தமிழ்", "Hindi mein") is deliberate audience targeting chosen by
  the client. Treat it as a differentiator unless competitors in the feed make the same claim. NEVER mark it as a
  weakness, never suggest removing, translating or "broadening" the language; you may suggest making it MORE visible.
- NEVER invent facts, numbers, ratings, student counts or testimonials. When an example needs a number the client must
  supply, use a placeholder like [X]+ students or [rating]★.
- TEXT ad: the hook is the first line of the client's text, quoted exactly; every "quote" must be copied exactly from it.
- VIDEO ad: you get its key frames in order with timestamps, and the voiceover transcript. The hook is the first ~3
  seconds: the first spoken sentence (quote it exactly from the transcript) and/or the opening frame's text. Judge pacing,
  when the offer and CTA appear, and whether the opening frame stops the scroll. Mention timestamps ("at 12s") in notes
  and improvements when a point is about a later moment. Competitor videos come with their own transcript and you may
  quote their spoken first line as their hook.

ANNOTATIONS (pinned on the client's creative):
- VIDEO: annotations are TIME-CODED pins on the video timeline. Each gridded frame is labelled with its timestamp.
  Give "t" = the timestamp (seconds) of the frame you are pointing at plus "cells" on THAT frame's grid; for a point
  about the voiceover give "t" = the start of that transcript segment, "cells": null and "quote" = the exact spoken
  words. Spread 6-8 pins across the whole video: the opening/hook, when the brand, offer and proof appear, the CTA,
  and the moments where the simulated buyers scroll away ("drop_off" in the client ad) - say what is on screen then.
- If a GRIDDED copy of the image is attached: it has a 10x10 reference grid, columns A-J left to right, rows 1-10 top
  to bottom (the grid is NOT part of the ad). For each annotation give "cells" as the tight rectangle "C2:H3"
  (top-left cell : bottom-right cell) covering the exact element you are talking about.
- If there is no image (text ad): give "quote" = an exact substring of the client's ad text instead of cells.
- 5-7 annotations mixing kinds: "strength" (keep it), "weakness" (hurts stopping/clicking), "fix" (something to add/change here).

Return JSON:
{
  "annotations": [{"n": 1, "kind": "strength|weakness|fix", "t": "seconds (video only) or null", "cells": "C2:H3 or null", "quote": "exact text or null",
                   "label": "max 4 words", "note": "max 14 words"}],
  "hook": {
    "text": "the client's actual hook, verbatim",
    "type": "one of: offer, problem, curiosity, bold claim, question, social proof, announcement, story, fear/urgency, other",
    "score": 1-10,
    "verdict": "max 12 words",
    "metrics": {"Scroll-stopping": 1-10, "Clarity": 1-10, "Specificity": 1-10, "Emotion": 1-10, "Urgency": 1-10},
    "works": ["max 7 words each, 2-3 items"], "fails": ["max 7 words each, 2-3 items"],
    "competitor_hooks": [{"advertiser": "exact advertiser name from the feed", "hook": "COPY-PASTE the first line or headline of that advertiser's ad exactly as given", "type": "...", "score": 1-10, "lesson": "max 8 words"}],
    "rewrites": [{"hook": "new hook", "type": "...", "why": "max 10 words"}]
  },
  "standout": {
    "positioning_now": "max 12 words",
    "unique": [{"label": "max 4 words", "point": "short", "evidence": "quote or detail"}],
    "shared": [{"label": "max 4 words", "point": "short", "competitors": ["names"]}],
    "missing": [{"label": "max 4 words", "point": "short", "who": ["names"], "evidence": "quote"}],
    "unclaimed": [{"label": "max 4 words", "point": "short"}],
    "positioning_suggested": "max 16 words"
  },
  "improvements": [{"area": "Hook|Offer|Visual|Copy|CTA|Social proof|Trust|Audience|Format",
                    "title": "max 6 words", "problem": "max 12 words", "fix": "max 14 words",
                    "example": "concrete rewritten line or visual instruction", "inspired_by": "competitor name or null",
                    "impact": "high|medium|low"}],
  "improved_ad": {"hook": "...", "primary_text": "3-5 short lines", "headline": "...",
                  "cta": "button text", "visual_direction": "max 20 words"},
  "scorecard": {"before": 1-100, "after_estimate": 1-100, "summary": "max 14 words"}
}
Give 3-5 competitor_hooks, 3 rewrites, 2-4 items in each standout list where evidence allows, 6-8 improvements sorted
by impact. Only output JSON."""


def _grid_overlay(data_url: str, max_side: int = 1024) -> str | None:
    """Draw a labelled 10x10 reference grid on the image so the model can point at regions."""
    try:
        import cv2
        import numpy as np

        raw = base64.b64decode(data_url.split(",", 1)[1])
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        scale = max_side / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
            h, w = img.shape[:2]
        overlay = img.copy()
        for i in range(1, 10):
            cv2.line(overlay, (int(w * i / 10), 0), (int(w * i / 10), h), (0, 255, 255), 1)
            cv2.line(overlay, (0, int(h * i / 10)), (w, int(h * i / 10)), (0, 255, 255), 1)
        img = cv2.addWeighted(overlay, 0.65, img, 0.35, 0)
        fs = max(0.4, w / 1600)
        for i in range(10):
            for j in range(10):
                x, y = int(w * i / 10) + 3, int(h * j / 10) + int(18 * fs * 1.6)
                label = f"{COLS[i]}{j + 1}"
                cv2.putText(img, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(img, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 255, 255), 1, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode() if ok else None
    except Exception:
        return None


def _cells_to_box(cells: str | None):
    """'C2:H3' -> normalized {x, y, w, h}."""
    if not cells:
        return None
    m = re.findall(r"([A-J])\s*(10|[1-9])", cells.upper())
    if not m:
        return None
    xs = [COLS.index(c) for c, _ in m]
    ys = [int(r) - 1 for _, r in m]
    x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
    return {"x": x0 / 10, "y": y0 / 10, "w": (x1 - x0) / 10, "h": (y1 - y0) / 10}


def review_ad(profile: dict, user_card: dict, competitor_cards: list[dict], reactions: list[dict],
              personas: list[dict], image_data_url: str | None = None, media: dict | None = None) -> dict:
    """media = {ad_id: {"frames", "times", "transcript"}} for video ads (the user's is under "you")."""
    media = media or {}
    by_ad = {r["ad_id"]: r for r in reactions}
    pmap = {p["id"]: p for p in personas}

    def feedback(ad_id):
        r = by_ad.get(ad_id) or {}
        rs = r.get("reactions", [])
        fmt = lambda x: f"{pmap.get(x['id'], {}).get('role', '?')}: {x['reason']}"
        return {"stopped": r.get("stopped"), "clicked": r.get("clicked"), "stop_rate": r.get("stop_rate"),
                "why_stopped": [fmt(x) for x in rs if x["stopped"]][:10],
                "why_scrolled": [fmt(x) for x in rs if not x["stopped"]][:12]}

    mine = {k: user_card.get(k) for k in ("advertiser", "format", "headline", "body", "hook", "cta", "offer")}
    mine.update({"usp": profile.get("usp"), "key_features": profile.get("key_features"),
                 "creative_summary": profile.get("creative_summary"), "transcript": profile.get("transcript"),
                 "on_creative_text": profile.get("on_creative_text"), "buyer_feedback": feedback("you")})
    comps = [{"advertiser": c["advertiser"], "format": c.get("format"), "headline": c.get("headline"),
              "body": (c.get("body") or "")[:600], "cta": c.get("cta"), "days_running": c.get("days_running"),
              **({"voiceover": media[c["id"]]["transcript"][:600]} if (media.get(c["id"]) or {}).get("transcript") else {}),
              "buyer_feedback": {k: v for k, v in feedback(c["id"]).items() if k in ("stop_rate", "why_stopped")}}
             for c in competitor_cards]

    mv = media.get("you") or {}
    is_video = bool(mv.get("frames"))
    if is_video:
        mine["duration_seconds"] = mv.get("duration")
        mine["voiceover_segments"] = mv.get("segments") or None
        mine["drop_off"] = drop_off(by_ad.get("you"), mv.get("duration"))
    content = [{"type": "text", "text": "CLIENT AD:\n" + json.dumps(mine, ensure_ascii=False, indent=1)
                + "\n\nCOMPETITOR ADS IN THE SAME FEED:\n" + json.dumps(comps, ensure_ascii=False, indent=1)}]
    gridded = _grid_overlay(image_data_url) if image_data_url and not is_video else None
    if image_data_url and not is_video:
        content.append({"type": "text", "text": "The client's creative (original):"})
        content.append({"type": "image_url", "image_url": {"url": image_data_url, "detail": "high"}})
    if gridded:
        content.append({"type": "text", "text": "Same creative with the A-J / 1-10 reference grid for annotations:"})
        content.append({"type": "image_url", "image_url": {"url": gridded, "detail": "high"}})
    times = mv.get("times") or []
    if is_video:
        content.append({"type": "text", "text": "The client's VIDEO: each key frame below carries the A-J / 1-10 grid "
                        "(not part of the ad) and is preceded by its timestamp."})
        for f, t in zip(mv["frames"], times):
            content += [{"type": "text", "text": f"FRAME at t={t}s"},
                        {"type": "image_url", "image_url": {"url": _grid_overlay(f, 640) or f, "detail": "high"}}]

    result = chat_json([{"role": "system", "content": REVIEW_PROMPT}, {"role": "user", "content": content}], temperature=0.2)

    # Keep only competitor hooks that really appear in that advertiser's ad (no invented quotes).
    texts = {c["advertiser"].strip().lower(): [c.get("headline") or "", c.get("body") or "",
                                               (media.get(c["id"]) or {}).get("transcript") or ""] for c in competitor_cards}
    hook = result.get("hook") or {}
    result["hook"] = hook

    # The client's own hook and highlighted quotes must exist in what they actually wrote / said.
    # Video: the hook is what is said or shown first, so the voiceover and on-screen text come before the caption.
    kind = profile.get("input_type")
    own = [t for t in ((user_card.get("transcript"), profile.get("on_creative_text"), user_card.get("body"))
                       if kind == "video" else (user_card.get("body"),)) if t]
    if own and kind in ("text", "video") and not is_verbatim(hook.get("text") or "", own):
        fallback = profile.get("hook") if is_verbatim(profile.get("hook") or "", own) else first_line(own[0])
        if fallback:
            hook["text"] = fallback
    for a in result.get("annotations") or []:
        if a.get("quote") and not (user_card.get("body") and a["quote"].lower() in user_card["body"].lower()):
            a["quote"] = None
    verified = []
    for ch in hook.get("competitor_hooks") or []:
        src = texts.get((ch.get("advertiser") or "").strip().lower())
        if src and is_verbatim(ch.get("hook", ""), src):
            ch["verified"] = True
            verified.append(ch)
    hook["competitor_hooks"] = verified

    # Competitor names and "evidence" quotes must point at real ads in this feed; drop anything that doesn't.
    real = {c["advertiser"].strip().lower(): c["advertiser"] for c in competitor_cards}
    names = lambda xs: [real[n.strip().lower()] for n in (xs or []) if isinstance(n, str) and n.strip().lower() in real]
    st = result.get("standout") or {}
    for s in st.get("shared") or []:
        s["competitors"] = names(s.get("competitors"))
    st["shared"] = [s for s in st.get("shared") or [] if s["competitors"]]
    for m in st.get("missing") or []:
        m["who"] = names(m.get("who"))
        src = [t for w in m["who"] for t in texts.get(w.strip().lower(), [])]
        if m.get("evidence") and not is_verbatim(m["evidence"], src):
            m["evidence"] = None
    st["missing"] = [m for m in st.get("missing") or [] if m["who"]]
    for imp in result.get("improvements") or []:
        n = (imp.get("inspired_by") or "").strip().lower()
        imp["inspired_by"] = real.get(n)
    for i, a in enumerate(result.get("annotations") or [], 1):
        a["n"] = i
        a["box"] = _cells_to_box(a.get("cells")) if gridded else None
    result["has_image"] = bool(gridded)
    if is_video:
        result["annotations"] = _place_on_timeline(result.get("annotations") or [], times, mv.get("duration"))
        result["timeline"] = True
    return result


def drop_off(reaction: dict | None, duration: float | None) -> list[dict]:
    """When the simulated buyers scrolled away, per 1-second bucket: [{"t", "left", "still_watching", "reasons"}]."""
    rs = (reaction or {}).get("reactions") or []
    if not rs or not duration:
        return []
    out = []
    for s in range(int(duration) + 1):
        left = [r for r in rs if s <= r["watch_seconds"] < s + 1 and r["watch_seconds"] < duration]
        if left:
            out.append({"t": s, "left": len(left), "still_watching": sum(r["watch_seconds"] >= s + 1 for r in rs),
                        "of": len(rs), "reasons": [r["reason"] for r in left][:4]})
    return out


def _place_on_timeline(anns: list[dict], times: list[float], duration: float | None) -> list[dict]:
    """Snap each pin to a real moment: visual pins to the nearest key frame (box on that frame), audio pins to their time."""
    dur = duration or (times[-1] if times else 0)
    for a in anns:
        try:
            t = float(a.get("t"))
        except (TypeError, ValueError):
            t = times[0] if times else 0.0
        t = max(0.0, min(t, dur)) if dur else max(0.0, t)
        box = _cells_to_box(a.get("cells"))
        if box and times:
            k = min(range(len(times)), key=lambda i: abs(times[i] - t))
            a.update(frame=k, t=times[k], box=box)
        else:
            a.update(frame=None, t=round(t, 1), box=None)
    anns.sort(key=lambda a: a["t"])
    for i, a in enumerate(anns, 1):
        a["n"] = i
    return anns
