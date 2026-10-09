"""Head-to-head: the user's ad vs their #1 competitor, point by point (positives and negatives of both sides)."""
from __future__ import annotations

import json

from .llm import chat_json

H2H_PROMPT = """You are a senior competitive strategist comparing a client's Facebook/Instagram ad with their #1
competitor in India, head to head. You get the client's ad, the competitor's real ads from the Facebook Ads Library
(copy, hooks, offers, CTAs, how long they run) and how 30 simulated buyers reacted to both ads in the same feed.
Be specific, quote real words from the ads, never generic advice. Be honest about where the competitor is better.
NEVER invent facts, prices, numbers, ratings or testimonials; if something is not visible for a side, say "Not shown".
Attached creatives are labelled CLIENT or COMPETITOR right before each image; judge what you actually see.
Video ads come as key frames with timestamps plus the voiceover transcript.

Compare on exactly these aspects, in this order: {aspects}.
{focus}

Return JSON:
{
  "winner": "you|them|tie",
  "verdict": "2 sentences: who wins overall and the single biggest reason",
  "rows": [{"aspect": "...", "you": "max 12 words", "them": "max 12 words", "edge": "you|them|tie", "why": "max 14 words"}],
  "you": {"positives": ["max 14 words, 3-5 items"], "negatives": ["max 14 words, 3-5 items"]},
  "them": {"positives": ["max 14 words, 3-5 items"], "negatives": ["max 14 words, 3-5 items"]},
  "details": [{"aspect": "same names as rows", "you": "2-4 sentences with quotes", "them": "2-4 sentences with quotes",
               "takeaway": "1-2 sentences: exactly what the client should do"}],
  "steal": ["2-4 things that work for the competitor the client should adapt (not copy)"],
  "attack": ["2-4 competitor weaknesses the client can position against"],
  "actions": [{"title": "max 8 words", "detail": "1-2 sentences", "priority": "high|medium|low"}]
}
One row and one detail per aspect. 4-6 actions. Only output JSON."""


BASE = ["Hook", "Offer & price", "Unique selling point", "Trust & social proof", "Emotional appeal", "Urgency",
        "Call to action"]
TAIL = ["Audience fit", "Clarity of message"]
# Aspects follow the client's input type so every format gets a fair, format-specific comparison.
ASPECTS = {
    "text": (BASE + ["Copy & readability"] + TAIL,
             "The client's ad is text only: judge copy structure, length, line breaks, emojis and scannability. "
             "Compare it with the competitor's copy AND creative, and say what visual the client should add."),
    "image": (BASE + ["Creative & visual", "Text on image"] + TAIL,
              "Both creatives are images: compare layout, focal point, colours, product visibility and on-image text."),
    "video": (BASE + ["First 3 seconds", "Voiceover & sound", "Pacing & story", "Creative & visual"] + TAIL,
              "The client's ad is a video: compare the opening frames (the scroll-stop moment), what the voiceover says "
              "and when, scene changes and pacing. If the competitor's ad is a static image, say what each format "
              "gains or loses. Quote timestamps like 0:03 where useful."),
}


def pick_top(competitors: list[dict]) -> dict | None:
    """#1 competitor = highest threat score among direct rivals (competitors are already sorted by threat)."""
    for rel in ("direct", "indirect"):
        for c in competitors:
            if c.get("relevance") == rel:
                return c
    return None


def _num(v):
    return v if isinstance(v, (int, float)) else None


def _creative(label: str, card: dict | None, m: dict | None, image: str | None = None) -> list[dict]:
    """Labelled image parts for one side: video key frames (max 4) if we have them, else the still image."""
    m = m or {}
    frames = [(f, t) for f, t in zip(m.get("frames") or [], m.get("times") or [])][:4]
    if frames:
        out = [{"type": "text", "text": f"{label} VIDEO, key frames:"}]
        for f, t in frames:
            out += [{"type": "text", "text": f"{label} @ {int(t) // 60}:{int(t) % 60:02d}"},
                    {"type": "image_url", "image_url": {"url": f, "detail": "low"}}]
        return out
    img = image or (card or {}).get("image")
    if (img or "").startswith("data:"):
        return [{"type": "text", "text": f"{label} creative:"}, {"type": "image_url", "image_url": {"url": img, "detail": "low"}}]
    return []


def head_to_head(profile: dict, competitors: list[dict], feed: list[dict], reactions: list[dict],
                 user_image: str | None = None, kind: str = "text", media: dict | None = None) -> dict | None:
    top = pick_top(competitors)
    if not top:
        return None
    you = feed[0]
    their_ad = next((a for a in feed[1:] if a.get("advertiser") == top["page_name"]), None)
    res = {r.get("ad_id"): r for r in reactions}
    r_you, r_them = res.get(you["id"]) or {}, res.get((their_ad or {}).get("id")) or {}

    # Hard numbers: taken straight from the simulation and the Ads Library, never from the LLM.
    facts = [{"label": "Buyers who stopped (of 30)", "you": _num(r_you.get("stopped")),
              "them": _num(r_them.get("stopped")) if their_ad else None, "higher_is_better": True},
             {"label": "Would click (of 30)", "you": _num(r_you.get("clicked")),
              "them": _num(r_them.get("clicked")) if their_ad else None, "higher_is_better": True},
             {"label": "Avg. watch time (s)", "you": _num(r_you.get("avg_watch")),
              "them": _num(r_them.get("avg_watch")) if their_ad else None, "higher_is_better": True},
             {"label": "Active ads in Ads Library", "you": None, "them": top.get("active_ads"), "higher_is_better": True},
             {"label": "Longest-running ad (days)", "you": None, "them": top.get("max_days_running"), "higher_is_better": True}]

    client = {k: you.get(k) for k in ("advertiser", "format", "hook", "body", "cta", "offer", "transcript") if you.get(k)}
    client.update({k: profile.get(k) for k in ("product", "category", "target_audience", "usp", "key_features", "tone")
                   if profile.get(k)})
    rival = {k: top.get(k) for k in ("page_name", "sells", "positioning", "key_messages", "creative_style", "hooks",
                                     "offers", "ctas", "formats", "active_ads", "max_days_running", "page_likes",
                                     "sample_titles", "sample_copy") if top.get(k)}
    if their_ad:
        rival["ad_in_feed"] = {k: their_ad.get(k) for k in ("format", "headline", "body", "cta", "link_description",
                                                           "transcript", "days_running") if their_ad.get(k)}

    def buyer_voice(r):
        return [x.get("reason") for x in (r.get("reactions") or []) if x.get("reason")][:12]
    sim = {"client": {"stopped": r_you.get("stopped"), "clicked": r_you.get("clicked"), "said": buyer_voice(r_you)},
           "competitor": {"stopped": r_them.get("stopped"), "clicked": r_them.get("clicked"),
                          "said": buyer_voice(r_them)} if their_ad else "competitor ad was not in the feed"}

    content = [{"type": "text", "text": "CLIENT AD:\n" + json.dumps(client, ensure_ascii=False)
                + "\n\nCOMPETITOR:\n" + json.dumps(rival, ensure_ascii=False)
                + "\n\nSIMULATED BUYERS (same feed, 30 people):\n" + json.dumps(sim, ensure_ascii=False)}]
    media = media or {}
    them_media = media.get((their_ad or {}).get("id")) or {}
    if them_media.get("transcript"):
        rival.setdefault("ad_in_feed", {})["transcript"] = them_media["transcript"][:800]
    content += _creative("CLIENT", you, media.get("you"), user_image)
    content += _creative("COMPETITOR", their_ad, them_media)

    kind = kind if kind in ASPECTS else "text"
    aspects, focus = ASPECTS[kind]
    prompt = H2H_PROMPT.replace("{aspects}", ", ".join(aspects)).replace("{focus}", focus)
    out = chat_json([{"role": "system", "content": prompt}, {"role": "user", "content": content}], temperature=0.2)
    out["winner"] = out.get("winner") if out.get("winner") in ("you", "them", "tie") else "tie"
    for r in out.get("rows") or []:
        r["edge"] = r.get("edge") if r.get("edge") in ("you", "them", "tie") else "tie"
    score = {"you": 0, "them": 0, "tie": 0}
    for r in out.get("rows") or []:
        score[r["edge"]] += 1
    return {**out, "facts": facts, "score": score, "input_kind": kind,
            "competitor": {k: top.get(k) for k in ("page_name", "profile_pic", "page_categories", "sells", "relevance",
                                                   "threat_score", "page_profile_uri", "hooks", "offers", "ads")},
            "their_ad": {**{k: their_ad.get(k) for k in ("ad_library_url", "image", "headline", "body", "format", "days_running")},
                         "frames": [{"src": f, "t": t} for f, t in zip(them_media.get("frames") or [], them_media.get("times") or [])][:4]}
            if their_ad else None}
