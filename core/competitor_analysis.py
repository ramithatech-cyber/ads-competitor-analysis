"""Aggregate scraped ads per advertiser and run the OpenAI competitive analysis."""
from __future__ import annotations

import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import pandas as pd

from .evidence import is_verbatim, norm, real_hooks, real_offers, threat_score
from .llm import chat_json, classify_model

DIMENSIONS = ["Hook strength", "Offer clarity", "Emotional appeal", "Social proof", "Urgency", "CTA clarity", "Visual appeal"]

ANALYSIS_PROMPT = f"""You are a senior competitive-intelligence analyst for Facebook/Instagram ads in India.
You get (1) the USER's product/ad profile and (2) the competitors found in the Facebook Ads Library, already
classified as direct or indirect, with stats and their competing ad copy.
Base everything ONLY on the evidence given (their real ad copy). Do not invent numbers, offers, claims or quotes.
If something is not visible in the copy, do not state it. Relevance, hooks, offers and threat are computed separately,
so do not output them.

Return JSON:
{{
  "executive_summary": "5-7 sentence summary of the competitive landscape and what the user should do",
  "competitors": [
    {{"page_name": "exact name as given",
      "positioning": "1 sentence grounded in their copy", "key_messages": ["claims they actually make"],
      "creative_style": "short", "strengths": ["..."], "weaknesses": ["..."]}}
  ],
  "market_themes": [{{"theme": "e.g. 'Lab-tested purity'", "keywords": ["3-6 lowercase words/short phrases that literally appear in ads using this theme"], "description": "short"}}],
  "scores": {{"dimensions": {json.dumps(DIMENSIONS)},
             "user": [1-10 per dimension for the USER's input],
             "competitor_avg": [1-10 per dimension, average of direct competitors],
             "best_competitor": {{"name": "...", "values": [1-10 per dimension]}}}},
  "user_ad_feedback": {{"strengths": ["..."], "weaknesses": ["..."]}},
  "gaps_opportunities": ["white-space the user can own that competitors are NOT doing"],
  "recommendations": [{{"title": "...", "detail": "...", "priority": "high|medium|low"}}],
  "ad_copy_ideas": [{{"hook": "...", "body": "...", "cta": "..."}}],
  "suggested_keywords_to_monitor": ["..."]
}}
Include every competitor provided in "competitors". Give 3 ad_copy_ideas, 5-8 recommendations, 5-8 market_themes.
Only output JSON."""


def ads_dataframe(ads: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(ads)
    if df.empty:
        return df
    df["start_dt"] = pd.to_datetime(df["start_date"], unit="s", errors="coerce")
    df["has_video"] = df["video_urls"].apply(bool)
    return df


def _key(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _site(url) -> str:
    """'https://ryl.dharaneetharan.in/x' -> 'dharaneetharan' (the registered name, no subdomain or TLD)."""
    url = str(url or "").strip()
    host = (urlparse(url if "://" in url else "https://" + url).hostname or "").lower().removeprefix("www.")
    if host.endswith(("facebook.com", "fb.me", "instagram.com", "wa.me", "whatsapp.com", "bit.ly", "linktr.ee")):
        return ""
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "ac", "gov"):  # example.co.in
        parts = parts[:-1]
    return _key(parts[-2]) if len(parts) >= 2 else ""


# Words that say nothing about WHO the advertiser is; a name made only of these never identifies the user.
GENERIC = set("""ai business coach coaching academy institute digital marketing online course courses training school
official india indian global learning learn solutions media tech technology technologies the and of by with for
skills skill career careers growth mastery class classes program programme education edu hub labs lab studio
pvt ltd limited private company group agency consulting consultancy services team community club page tamil
hindi english nadu chennai bangalore mumbai delhi live free masterclass workshop seminar webinar founder ceo""".split())


def _name_match(key: str, name: str) -> bool:
    """key (e.g. 'dharaneetharan') matches 'Dharaneetharan G D' only on whole words, never mid-word."""
    words = re.findall(r"[a-z0-9]+", str(name or "").lower())
    joined = "".join(words)
    if not key or not joined:
        return False
    if len(joined) >= 5 and key.startswith(joined):  # 'Social Eagle' vs brand 'SocialEagle.AI'
        return True
    starts, ends, pos = set(), set(), 0
    for w in words:
        starts.add(pos)
        pos += len(w)
        ends.add(pos)
    i = joined.find(key)
    while i != -1:
        if i in starts and i + len(key) in ends:
            return True
        i = joined.find(key, i + 1)
    return False


def find_own_pages(df: pd.DataFrame, profile: dict, brand: str = "") -> dict[str, str]:
    """Advertisers in the scrape that are the USER themself (their brand, founder/presenter page, own website,
    or the very same ad copy). They must never be shown as competitors. Returns {page_name: reason}."""
    if df.empty:
        return {}
    names = [profile.get("brand_name"), *re.split(r"[,;/]", brand or ""), *(profile.get("self_names") or [])]
    src = str(profile.get("source_url") or "")
    m = re.search(r"(?:instagram|facebook)\.com/(?!p/|reel/|reels/|watch|share)([\w.\-]+)", src, re.I)
    if m:
        names.append(m.group(1))
    names = [n for n in names if n and not set(re.findall(r"[a-z0-9]+", str(n).lower())) <= GENERIC]
    keys = {_key(n) for n in names if len(_key(n)) >= 4}
    # Distinctive brand / event names ('Reclaim Your Life 2.0') written inside a rival's own copy mean it is the user.
    phrases = {norm(n): str(n).strip() for n in names if len(norm(n)) >= 6}
    sites = {s for s in (_site(u) for u in [src, *(profile.get("websites") or [])]) if len(s) >= 4} | keys
    # The user's own words: if a "rival" runs this exact copy, it is the user's own ad.
    own_text = [t for t in (profile.get("hook"), profile.get("transcript"), profile.get("_raw_text")) if t and len(norm(t)) >= 25]

    out = {}
    for name, g in df.groupby("page_name"):
        uri = str(g["page_profile_uri"].dropna().iloc[0]) if g["page_profile_uri"].notna().any() else ""
        handle = _key(re.sub(r".*facebook\.com/(profile\.php\?id=)?", "", uri).strip("/"))
        if any(_name_match(k, name) or (len(handle) >= 5 and (handle == k or handle.startswith(k))) for k in keys):
            out[name] = "same name as your brand"
            continue
        ad_sites = {_site(u) for u in g["link_url"].dropna()} | {_site(c) for c in g.get("caption", pd.Series(dtype=str)).dropna()}
        if sites & {a for a in ad_sites if len(a) >= 4}:
            out[name] = "links to your website"
            continue
        bodies = [b for b in g["body"].dropna() if b]
        copy = " " + norm(" ".join(bodies + list(g["title"].dropna()))) + " "
        named = next((ph for ph in phrases if f" {ph} " in copy), None)
        if named:
            out[name] = f"their ads mention '{phrases[named]}'"
            continue
        if own_text and any(is_verbatim(t[:160], bodies, 0.9) for t in own_text):
            out[name] = "runs the same ad copy as yours"
    return out


def aggregate_advertisers(df: pd.DataFrame, exclude_brand: str | None = None, top_n: int | None = None) -> list[dict]:
    if df.empty:
        return []
    if exclude_brand:
        b = exclude_brand.lower().strip()
        df = df[~df["page_name"].str.lower().str.contains(b, regex=False)]
    out = []
    for name, g in df.groupby("page_name"):
        bodies = [t for t in g.sort_values("days_running", ascending=False)["body"].dropna().unique() if t and "{{" not in t]
        titles = [t for t in g["title"].dropna().unique() if t and "{{" not in t]
        out.append({
            "page_name": name,
            "page_profile_uri": g["page_profile_uri"].dropna().iloc[0] if g["page_profile_uri"].notna().any() else None,
            "profile_pic": g["page_profile_picture_url"].dropna().iloc[0] if g["page_profile_picture_url"].notna().any() else None,
            "page_categories": sorted({c for cs in g["page_categories"] for c in (cs or [])}),
            "page_likes": int(g["page_like_count"].max()) if g["page_like_count"].notna().any() else None,
            "active_ads": int(len(g)),
            "max_days_running": int(g["days_running"].max()) if g["days_running"].notna().any() else None,
            "avg_days_running": round(float(g["days_running"].mean()), 1) if g["days_running"].notna().any() else None,
            "formats": dict(Counter(g["display_format"])),
            "platforms": dict(Counter(p for ps in g["publisher_platform"] for p in ps)),
            "ctas": dict(Counter(c for c in g["cta_text"].dropna())),
            "keywords_matched": sorted(set(g["matched_keyword"])),
            "sample_copy": [t[:500] for t in bodies[:4]],
            "sample_titles": titles[:3],
            "all_copy": [t[:1200] for t in bodies[:8]] + titles[:5],
            "hooks": real_hooks(bodies, titles),
            "offers": real_offers(bodies + titles + list(g["link_description"].dropna())),
            "ads": [{"url": r["ad_library_url"], "hook": (real_hooks([r["body"] or ""], [r["title"] or ""], 1) or [""])[0],
                     "days": int(r["days_running"] or 0), "format": r["display_format"],
                     "image": (r["image_urls"] or r["video_preview_urls"] or [None])[0]}
                    for _, r in g.sort_values("days_running", ascending=False).head(3).iterrows()],
            # Every ad, so classification can look at the ones that match the user's product (dropped before output).
            "_ads": [{"id": str(r["ad_archive_id"]), "body": r["body"] or "", "title": r["title"] or "",
                      "link_description": r.get("link_description") or "", "days": int(r["days_running"] or 0),
                      "url": r["ad_library_url"], "format": r["display_format"],
                      "image": (r["image_urls"] or r["video_preview_urls"] or [None])[0]}
                     for _, r in g.sort_values("days_running", ascending=False).iterrows()],
        })
    out.sort(key=lambda x: (x["active_ads"], x["page_likes"] or 0), reverse=True)
    return out[:top_n] if top_n else out


CLASSIFY_PROMPT = """You decide which Facebook advertisers are real competitors of the USER's offer.
Think like the USER's buyer: would this buyer seriously consider this advertiser's offer instead of the user's?
- "direct": sells the same kind of product/service for the same buyer goal (e.g. both teach the same subject, both sell
  the same product type), even if price, duration, level, language, city, brand size or online/offline differ.
- "indirect": a substitute for the same buyer goal: the user's subject is a MAJOR part of a broader offer (a named module
  or half of a bundle), a different format for the same goal (degree vs short course, app vs coaching), or a neighbouring
  niche the same buyer actively compares.
- "irrelevant": a different buyer goal; the user's subject is only a passing buzzword in a list of many unrelated items;
  no clear offer (opinion posts, news, job posts, exam-dump sellers); a product that merely CONTAINS or USES the
  user's product as an ingredient, material or tool (a snack fried in the oil, a cake made with the flour); or an
  unrelated product.
Big advertisers run ads for many products: judge each advertiser by its MOST relevant ad. One matching ad is enough.
Base every decision ONLY on the ad copy shown.
USER OFFER.market defines the user's core subject (with the other names sellers use for it) and the buyer goal:
use it as the yardstick. Any of its "also_called" names counts as the core subject, and so do its sub-topics and the
tools typical of it (if the subject were "photography course", "Master Lightroom editing" would be the core subject).
The broader parent field taught as a whole counts as at least "major" ("design course" for a logo-design course).
Rate each advertiser on its MOST relevant ad, ignoring its other, unrelated ads.
First rate "overlap" = how central the USER's core subject is to that ad's offer:
  "main"  - it IS what the ad sells (the headline course/product is about it)
  "major" - a named major part: in the program's name next to one other subject ("Data Science with X", "Y + X"),
            a headline module, or the explicit focus of a broader program
  "minor" - one item in a list of many courses/skills, or used only as an adjective/tool for a DIFFERENT subject
            (e.g. "AI-powered marketing", "MBA with AI tools", "X course with AI")
  "none"  - not there at all
Then: main -> direct (or indirect if the buyer goal clearly differs); major -> indirect; minor or none -> irrelevant.
For each advertiser return:
  "overlap", "relevance", "sells" (max 8 words: what their matching ad sells),
  "evidence" (3-12 words COPIED EXACTLY from that ad which prove what it sells; "" if irrelevant),
  "matching_ads" (ids of their ads that compete with the user's offer; [] if irrelevant).
Return JSON: {"advertisers": [{"page_name": "exact name as given", "overlap": "main|major|minor|none",
  "relevance": "direct|indirect|irrelevant",
  "sells": "...", "evidence": "...", "matching_ads": ["..."]}]}. Include every advertiser. Only output JSON."""

RECHECK_PROMPT = CLASSIFY_PROMPT + """

SECOND LOOK: these advertisers were first rated "minor" from a short snippet; you now see their full ad copy.
Re-rate them with the same rules. Ask: would someone about to buy the USER's offer realistically stop and compare
this ad's offer (it teaches/sells the core subject itself, a sub-topic or tool of it, or the parent field as a whole)?
If yes, overlap is "main" or "major". Keep "minor" only when the core subject is truly a passing item or an adjective."""

STOP = set("""a an and the of for to in on with by your you our is are be from at as or this that it its we us get
just now new more best top india""".split())


def _terms(profile: dict) -> set[str]:
    """Words describing what the user sells, to show the classifier each advertiser's closest ads first."""
    parts = [profile.get(k) for k in ("product", "category", "hook", "usp", "industry")]
    parts += list(profile.get("search_keywords") or []) + list(profile.get("key_features") or [])
    return {w for w in norm(" ".join(str(p) for p in parts if p)).split() if len(w) > 1 and w not in STOP}


def _ad_key(a: dict) -> str:
    return norm(a["body"] or a["title"])[:200]


def _closest_ads(ads: list[dict], terms: set[str], n: int = 5) -> list[dict]:
    seen, uniq = set(), []
    for a in ads:
        k = _ad_key(a)
        if k and k not in seen and "{{" not in (a["body"] or ""):
            seen.add(k)
            uniq.append(a)

    def hits(a):
        return len(terms & set(norm(f"{a['title']} {a['body']} {a['link_description']}").split()))
    return sorted(uniq, key=lambda a: (-hits(a), -a["days"]))[:n]


MARKET_PROMPT = """Define the market a product competes in, so ads can be checked for real competitors consistently.
Describe the CATEGORY the buyer is shopping in - what they actually learn or get - not the product's marketing title
or the job title it promises (a course called "Become a Growth Hacker in 30 days" is a digital-marketing course).
Name the subject the way buyers search for it, broadly enough to cover its everyday names.
Return JSON: {"core_subject": "plain words, e.g. 'spoken English course' or 'whey protein supplement'",
"also_called": ["8-15 words/phrases sellers use for the same subject: short forms, sub-topics, typical tool/brand
names. Not this product's features or perks"],
"buyer_goal": "1 sentence: what the buyer wants to achieve by buying it"}. Only output JSON."""


def define_market(prof: dict) -> dict:
    """One shared definition of the user's market, so every classification batch judges against the same yardstick."""
    try:
        return chat_json([{"role": "system", "content": MARKET_PROMPT},
                          {"role": "user", "content": json.dumps(prof, ensure_ascii=False)}], temperature=0, model_name=classify_model())
    except Exception:
        return {}


def classify_advertisers(profile: dict, advertisers: list[dict], batch: int = 6) -> dict[str, dict]:
    """{page_name: {"relevance", "sells", "evidence", "matching_ads"}} for every advertiser, judged on its closest ads."""
    prof = {k: profile.get(k) for k in ("product", "category", "industry", "target_audience", "usp", "key_features",
                                        "hook", "offer") if profile.get(k)}
    market = define_market(prof)
    if market:
        prof["market"] = market
    terms = _terms(profile) | {w for p in market.get("also_called") or [] for w in norm(str(p)).split()
                               if len(w) > 1 and w not in STOP}
    items = [{"page_name": a["page_name"], "page_categories": a["page_categories"],
              "ads": [{"id": x["id"], "title": x["title"][:120], "copy": x["body"][:420]}
                      for x in _closest_ads(a["_ads"], terms)]}
             for a in advertisers]

    def run(prompt, chunk):
        res = chat_json([{"role": "system", "content": prompt},
                         {"role": "user", "content": "USER OFFER:\n" + json.dumps(prof, ensure_ascii=False)
                          + "\n\nADVERTISERS:\n" + json.dumps(chunk, ensure_ascii=False)}],
                        temperature=0, model_name=classify_model())
        return res.get("advertisers") or []
    chunks = [items[i:i + batch] for i in range(0, len(items), batch)]
    with ThreadPoolExecutor(max_workers=4) as ex:
        out = [c for res in ex.map(lambda ch: run(CLASSIFY_PROMPT, ch), chunks) for c in res]
    cls = {str(c.get("page_name", "")).strip().lower(): c for c in out}

    # Second look at the "minor" calls, the borderline ones, with their full ad copy instead of a snippet.
    by_name = {a["page_name"].strip().lower(): a for a in advertisers}
    again = [{"page_name": a["page_name"], "ads": [{"id": x["id"], "title": x["title"][:160], "copy": x["body"][:1400]}
                                                   for x in _closest_ads(a["_ads"], terms, 3)]}
             for n, a in by_name.items() if (cls.get(n) or {}).get("overlap") == "minor"]
    if again:
        with ThreadPoolExecutor(max_workers=4) as ex:
            redo = [c for res in ex.map(lambda ch: run(RECHECK_PROMPT, ch), [again[i:i + batch] for i in range(0, len(again), batch)])
                    for c in res]
        for c in redo:
            n = str(c.get("page_name", "")).strip().lower()
            if n in cls and c.get("overlap") in ("main", "major"):
                cls[n] = c
    return cls


def run_analysis(profile: dict, advertisers: list[dict]) -> dict:
    prof = {k: v for k, v in profile.items() if not k.startswith("_")}
    cls = classify_advertisers(profile, advertisers)

    merged = []
    for a in advertisers:
        c = cls.get(a["page_name"].strip().lower(), {})
        rel = c.get("relevance") if c.get("relevance") in ("direct", "indirect", "irrelevant") else "irrelevant"
        # The overlap rating caps relevance: a passing mention never makes a competitor, only "main" can be direct.
        ov = c.get("overlap")
        if ov not in ("main", "major"):
            rel = "irrelevant"
        elif ov == "major" and rel == "direct":
            rel = "indirect"
        texts = [t for x in a["_ads"] for t in (x["body"], x["title"], x["link_description"]) if t]
        # A relevance claim must be backed by a phrase that really appears in their ads; otherwise downgrade it.
        ev = c.get("evidence") or ""
        if rel != "irrelevant" and not is_verbatim(ev, texts):
            rel, ev = ("indirect" if rel == "direct" else "irrelevant"), ""
        ids = {str(i) for i in c.get("matching_ads") or []}
        # The same copy often runs as several ads: every ad carrying a matching ad's copy competes too.
        keys = {_ad_key(x) for x in a["_ads"] if x["id"] in ids}
        match = [x for x in a["_ads"] if _ad_key(x) in keys] if rel != "irrelevant" else []
        m = {k: v for k, v in a.items() if k != "_ads"}
        if match:  # describe the rival by the ads that compete with the user, not its whole catalogue
            bodies = [x["body"] for x in match if x["body"]]
            titles = [x["title"] for x in match if x["title"]]
            m.update(hooks=real_hooks(bodies, titles) or m["hooks"],
                     offers=real_offers(bodies + titles + [x["link_description"] for x in match]) or m["offers"],
                     sample_copy=[t[:500] for t in bodies[:4]] or m["sample_copy"],
                     max_days_running=max(x["days"] for x in match),
                     ads=[{"url": x["url"], "hook": (real_hooks([x["body"]], [x["title"]], 1) or [""])[0],
                           "days": x["days"], "format": x["format"], "image": x["image"]} for x in match[:3]])
        merged.append({**m, "relevance": rel, "evidence": ev or None,
                       "sells": c.get("sells") if rel != "irrelevant" else None,
                       "competing_ads": len(match) or (1 if rel != "irrelevant" else 0)})

    # Threat counts only the ads that compete with the user, so a big catalogue does not inflate it.
    max_ads = max((m["competing_ads"] for m in merged), default=1) or 1
    max_days = max((m["max_days_running"] or 0 for m in merged), default=1)
    max_likes = max((m["page_likes"] or 0 for m in merged), default=1)
    for m in merged:
        m["threat_score"] = threat_score(m["relevance"], m["competing_ads"], m["max_days_running"], m["page_likes"],
                                         max_ads, max_days, max_likes)
    merged.sort(key=lambda m: m["threat_score"], reverse=True)

    relevant = [m for m in merged if m["relevance"] != "irrelevant"]
    compact = [{k: m[k] for k in ("page_name", "relevance", "sells", "page_categories", "page_likes", "competing_ads",
                                  "max_days_running", "formats", "ctas", "sample_titles", "sample_copy")}
               for m in relevant[:20]]
    user_msg = ("USER PROFILE:\n" + json.dumps(prof, ensure_ascii=False, indent=1)
                + "\n\nCOMPETITORS FROM ADS LIBRARY:\n"
                + (json.dumps(compact, ensure_ascii=False, indent=1) if compact else "None sell a comparable offer."))
    result = chat_json([{"role": "system", "content": ANALYSIS_PROMPT}, {"role": "user", "content": user_msg}],
                       temperature=0)

    by_name = {c.get("page_name", "").strip().lower(): c for c in result.get("competitors", [])}
    for m in relevant:
        c = by_name.get(m["page_name"].strip().lower(), {})
        m.update({k: c[k] for k in ("positioning", "key_messages", "creative_style", "strengths", "weaknesses") if k in c})

    # Theme prevalence = share of relevant competitors whose real copy contains one of the theme keywords.
    pool = relevant or merged
    texts = {m["page_name"]: norm(" ".join(m["all_copy"])) for m in pool}
    themes = []
    for t in result.get("market_themes") or []:
        kws = [norm(k) for k in t.get("keywords") or [] if norm(k)]
        users = [n for n, txt in texts.items() if any(k in txt for k in kws)]
        if users:
            themes.append({**t, "prevalence": round(100 * len(users) / len(texts)), "used_by": users})
    result["market_themes"] = sorted(themes, key=lambda t: t["prevalence"], reverse=True)
    result["competitors"] = merged

    # The "best competitor" on the scorecard must be a real, relevant advertiser from this run.
    bc = (result.get("scores") or {}).get("best_competitor") or {}
    rel_names = {m["page_name"].strip().lower(): m["page_name"] for m in relevant}
    if bc and (bc.get("name") or "").strip().lower() not in rel_names:
        result["scores"]["best_competitor"] = None
    elif bc:
        bc["name"] = rel_names[bc["name"].strip().lower()]
    return result


SCREEN_PROMPT = """You check which real Facebook ads belong in a side-by-side test against the USER's ad.
For each candidate ad decide from its OWN copy:
- "same": it advertises the same type of product/service to the same buyer as the user (a true head-to-head rival ad)
- "adjacent": same field and buyer, but a different product type/level
- "no": anything else (different field, brand awareness with no product, job post, event, unclear)
Give "sells" = what this specific ad sells, max 8 words, taken from its copy.
Return JSON: {"ads": [{"id": "...", "match": "same|adjacent|no", "sells": "..."}]}. Include every id. Only output JSON."""


def screen_ads(profile: dict, df: pd.DataFrame, competitors: list[dict], per_advertiser: int = 4) -> dict[str, dict]:
    """Ad-level relevance check, so the feed shows each rival's ad that actually competes with the user's ad."""
    names = [c["page_name"] for c in competitors if c.get("relevance") in ("direct", "indirect")]
    cand = []
    for name in names:
        g = df[(df["page_name"] == name) & (df["body"].fillna("").str.len() > 20)]
        g = g[~g["body"].str.contains("{{", regex=False)].sort_values("days_running", ascending=False)
        for _, r in g.drop_duplicates("body").head(per_advertiser).iterrows():
            cand.append({"id": r["ad_archive_id"], "advertiser": name, "title": r["title"] or "",
                         "copy": (r["body"] or "")[:450]})
    if not cand:
        return {}
    prof = {k: profile.get(k) for k in ("product", "category", "target_audience", "usp", "hook")}
    res = chat_json([{"role": "system", "content": SCREEN_PROMPT},
                     {"role": "user", "content": "USER AD:\n" + json.dumps(prof, ensure_ascii=False)
                      + "\n\nCANDIDATE ADS:\n" + json.dumps(cand, ensure_ascii=False)}], temperature=0, model_name=classify_model())
    valid = {c["id"] for c in cand}
    return {str(a.get("id")): a for a in res.get("ads", []) if str(a.get("id")) in valid}
