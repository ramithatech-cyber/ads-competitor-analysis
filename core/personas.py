"""Simulate how 30 buyer personas react to an ad in their feed (OpenAI)."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from .llm import chat_json

PERSONA_PROMPT = """Create exactly 30 diverse, realistic buyer personas from India who scroll Facebook/Instagram
and could plausibly see ads for the product below. Mix ages, genders, cities (metro + tier 2/3), incomes,
professions, and attitudes (sceptics, bargain hunters, loyalists, impulse buyers, non-buyers).
Make it a REAL feed audience, not just the target market: about 12 core-target buyers, 8 adjacent/occasional
buyers and 10 people with little or no interest in this category.
Return JSON: {"personas": [{"id": 1, "name": "first name", "role": "short role e.g. 'gym owner'", "age": 31,
"city": "Pune", "gender": "male|female", "income": "low|mid|high", "traits": "1 short sentence of buying psychology"}]}"""

REACT_PROMPT = """You simulate a real Instagram/Facebook feed. For EACH persona, decide honestly how they react to this
ad in the first 3 seconds and after. Calibrate to reality:
- People scroll past most ads. A typical ad stops 3-9 of 30 people; only an exceptional, highly relevant ad stops 12+.
- "stopped" = paused for 2+ seconds. Non-stoppers have watch_seconds under 1.5.
- "clicked" only if they stopped AND would actually tap through now; usually 0-3 people of 30.
- Generic claims, weak hooks, plain text creatives and irrelevance to the persona mean they scroll on.
- Judge every ad by the same standard; you do not know whose ad this is.
Return JSON: {"reactions": [{"id": persona id, "stopped": true|false, "watch_seconds": 0.0-30.0,
"clicked": true|false, "sentiment": "positive|neutral|negative", "reason": "max 14 words, first person"}]}
Include all 30 personas."""


def generate_personas(profile: dict) -> list[dict]:
    prof = {k: profile.get(k) for k in ("product", "category", "industry", "target_audience", "usp", "offer")}
    res = chat_json([{"role": "system", "content": PERSONA_PROMPT},
                     {"role": "user", "content": json.dumps(prof, ensure_ascii=False)}], temperature=0.8)
    personas = res.get("personas", [])[:30]
    for i, p in enumerate(personas, 1):
        p["id"] = i
    return personas


def react(personas: list[dict], ad: dict, media: dict | None = None) -> dict:
    """media = {"frames": [data urls], "times": [s], "transcript": str} for video ads (user's or competitor's)."""
    compact = [{k: p.get(k) for k in ("id", "role", "age", "city", "gender", "income", "traits")} for p in personas]
    # Every ad is judged on its real creative, with the same treatment for the user and the competitors:
    # video -> key frames in order + what is said; image -> the image; text -> the copy alone.
    media = media or {}
    frames = media.get("frames") or []
    has_img = (ad.get("image") or "").startswith("data:")
    keys = ("advertiser", "format", "headline", "body", "cta", "offer") + (() if frames or has_img else ("visual",))
    ad_desc = {k: ad.get(k) for k in keys if ad.get(k)}
    if media.get("transcript") or ad.get("transcript"):
        ad_desc["voiceover"] = (media.get("transcript") or ad.get("transcript"))[:1500]
    content = [{"type": "text", "text": "AD:\n" + json.dumps(ad_desc, ensure_ascii=False)
                + "\n\nPERSONAS:\n" + json.dumps(compact, ensure_ascii=False)}]
    if frames:
        times = media.get("times") or []
        dur = media.get("duration")
        content.append({"type": "text", "text": "This is a VIDEO ad"
                        + (f" lasting {dur}s. For this ad watch_seconds is the moment the person scrolls away "
                           f"(0-{dur}); {dur} means they watched to the end. Make the reason say what made them leave "
                           "or stay at that moment" if dur else "")
                        + ". Key frames in order" + (" (at " + ", ".join(f"{t}s" for t in times) + ")" if times else "")
                        + ". The first frame is what people see in the first second:"})
        content += [{"type": "image_url", "image_url": {"url": f, "detail": "low"}} for f in frames[:5]]
    elif has_img:
        content += [{"type": "text", "text": "The ad's creative as it appears in the feed:"},
                    {"type": "image_url", "image_url": {"url": ad["image"], "detail": "low"}}]
    res =chat_json([{"role": "system", "content": REACT_PROMPT}, {"role": "user", "content": content}], temperature=0.5)
    by_id = {r.get("id"): r for r in res.get("reactions", [])}
    reactions = []
    cap = media.get("duration") if frames else None
    for p in personas:
        r = by_id.get(p["id"], {})
        try:
            ws = max(0.0, float(r.get("watch_seconds") or 0))
        except (TypeError, ValueError):
            ws = 0.0
        reactions.append({"id": p["id"], "stopped": bool(r.get("stopped")), "clicked": bool(r.get("clicked")),
                          "watch_seconds": round(min(ws, cap), 1) if cap else ws,
                          "sentiment": r.get("sentiment", "neutral"), "reason": r.get("reason", "")})
    stopped = [r for r in reactions if r["stopped"]]
    return {
        "ad_id": ad["id"], "reactions": reactions,
        "stopped": len(stopped), "clicked": sum(r["clicked"] for r in reactions),
        "stop_rate": round(100 * len(stopped) / max(1, len(reactions)), 1),
        "avg_watch": round(sum(r["watch_seconds"] for r in reactions) / max(1, len(reactions)), 1),
    }


def simulate_feed(personas: list[dict], ads: list[dict], on_result=None, media: dict | None = None) -> list[dict]:
    results: dict = {}
    media = media or {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(react, personas, ad, media.get(ad["id"])): ad["id"] for ad in ads}
        for f, ad_id in futs.items():
            try:
                results[ad_id] = f.result()
            except Exception as e:
                results[ad_id] = {"ad_id": ad_id, "error": str(e), "reactions": [], "stopped": 0, "clicked": 0,
                                  "stop_rate": 0, "avg_watch": 0}
            if on_result:
                on_result(results[ad_id])
    return [results[a["id"]] for a in ads]


def user_ad_card(profile: dict, image_data_url: str | None = None, raw_text: str = "",
                 video_url: str | None = None) -> dict:
    """The user's ad exactly as they gave it: their caption/copy, their image or video. No AI-written copy.

    For a video the voiceover is kept separately (it is what people hear, not the caption under the post)."""
    kind = profile.get("input_type", "text")
    return {"id": "you", "is_user": True, "advertiser": profile.get("brand_name") or "Your brand",
            "format": kind.upper(), "headline": None, "body": raw_text.strip() or None,
            "hook": profile.get("hook"), "cta": profile.get("cta"), "offer": profile.get("offer"),
            "transcript": profile.get("transcript") or None, "visual": profile.get("creative_summary"),
            "image": image_data_url, "video": video_url if kind == "video" else None}


def _num(v) -> int:
    try:
        return 0 if v is None or v != v else int(v)
    except (TypeError, ValueError):
        return 0


def _domain(url, caption):
    import re
    from urllib.parse import urlparse
    try:
        host = str(caption).strip() if caption else urlparse(url or "").netloc
    except Exception:
        return None
    host = re.sub(r"^(https?://)?(www\.)?", "", host, flags=re.I).split("/")[0]
    return host.upper() or None


def competitor_ad_cards(df, competitors: list[dict], screen: dict | None = None, limit: int = 7) -> list[dict]:
    """One real ad per rival: the longest-running ad that sells the same thing as the user's ad.

    `screen` is the ad-level check from competitor_analysis.screen_ads ({ad_id: {"match", "sells"}}). Ads judged
    'same' come first, then 'adjacent'; ads judged unrelated are never shown."""
    from .media import embed_many

    screen = screen or {}
    rel = {c["page_name"]: c.get("relevance") for c in competitors}
    picks = {}
    for name in [c["page_name"] for c in competitors if c.get("relevance") in ("direct", "indirect")]:
        g = df[(df["page_name"] == name) & (df["body"].fillna("").str.len() > 20)]
        g = g[~g["body"].str.contains("{{", regex=False)].sort_values("days_running", ascending=False)
        best = None
        for _, a in g.iterrows():
            m = (screen.get(a["ad_archive_id"]) or {}).get("match") if screen else "same"
            if m not in ("same", "adjacent"):
                continue
            if best is None or (m == "same" and best[1] != "same"):
                best = (a, m)
            if m == "same":
                break
        if best is not None:
            picks[name] = best
    order = sorted(picks.items(), key=lambda kv: (kv[1][1] != "same", rel.get(kv[0]) != "direct",
                                                   -_num(kv[1][0]["days_running"])))[:limit]

    cards = []
    for name, (a, match) in order:
        imgs = list(a["image_urls"] or [])
        poster = (a["video_preview_urls"] or [None])[0]
        cards.append({"id": a["ad_archive_id"], "is_user": False, "advertiser": name, "format": a["display_format"],
                      "headline": a["title"] or None, "body": (a["body"] or "")[:900], "cta": a["cta_text"],
                      "link_description": a.get("link_description") or None,
                      "domain": _domain(a.get("link_url"), a.get("caption")),
                      "image": poster or (imgs[0] if imgs else None), "images": imgs[:5] if len(imgs) > 1 else [],
                      "video": (a["video_urls"] or [None])[0],
                      "profile_pic": a["page_profile_picture_url"], "days_running": _num(a["days_running"]),
                      "start_date": _num(a["start_date"]) or None,
                      "platforms": list(a["publisher_platform"] or []),
                      "ad_library_url": a["ad_library_url"], "match": match,
                      "sells": (screen.get(a["ad_archive_id"]) or {}).get("sells"),
                      "relevance": rel.get(name), "visual": f"{a['display_format']} creative"})

    # Embed creatives so the phone, the simulation and the PDF show exactly the same image.
    flat = [c["image"] for c in cards] + [u for c in cards for u in c["images"]] + [c["profile_pic"] for c in cards]
    emb = dict(zip(flat, embed_many(flat)))
    for c in cards:
        c["image"] = emb.get(c["image"]) or c["image"]
        c["images"] = [emb.get(u) or u for u in c["images"]]
        c["profile_pic"] = emb.get(c["profile_pic"]) or c["profile_pic"]
    return cards
