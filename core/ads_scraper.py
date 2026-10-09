"""Scrape the public Facebook Ads Library (no Meta token needed).

Runs as a standalone subprocess so Playwright gets its own event loop
(avoids Streamlit/asyncio issues on Windows):

    python -m core.ads_scraper --keywords "whey protein" "protein powder" --country IN --max-ads 60 --out ads.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
SCRIPT_JSON_RE = re.compile(r'<script type="application/json"[^>]*>(.*?)</script>', re.S)


def _walk_ads(obj, found: dict):
    """Recursively collect ad nodes (dicts that have ad_archive_id + snapshot)."""
    if isinstance(obj, dict):
        if "ad_archive_id" in obj and isinstance(obj.get("snapshot"), dict):
            found.setdefault(str(obj["ad_archive_id"]), obj)
            return
        for v in obj.values():
            _walk_ads(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _walk_ads(v, found)


def _walk_total(obj):
    if isinstance(obj, dict):
        conn = obj.get("search_results_connection")
        if isinstance(conn, dict) and isinstance(conn.get("count"), int):
            return conn["count"]
        for v in obj.values():
            r = _walk_total(v)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _walk_total(v)
            if r is not None:
                return r
    return None


def _parse_json_blobs(text: str):
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("for (;;);"):
            line = line[len("for (;;);"):]
        try:
            yield json.loads(line)
        except Exception:
            continue


def _clean_text(t):
    if isinstance(t, dict):
        t = t.get("text")
    if not isinstance(t, str):
        return ""
    # Dynamic product ads use template tokens like {{product.name}}
    return t.strip()


def normalize(node: dict, keyword: str) -> dict:
    snap = node.get("snapshot") or {}
    cards = snap.get("cards") or []
    images = [i.get("resized_image_url") or i.get("original_image_url") for i in (snap.get("images") or [])]
    videos = snap.get("videos") or []
    video_urls = [v.get("video_sd_url") or v.get("video_hd_url") for v in videos]
    video_previews = [v.get("video_preview_image_url") for v in videos]
    for c in cards:
        if c.get("resized_image_url") or c.get("original_image_url"):
            images.append(c.get("resized_image_url") or c.get("original_image_url"))
        if c.get("video_sd_url") or c.get("video_hd_url"):
            video_urls.append(c.get("video_sd_url") or c.get("video_hd_url"))
            video_previews.append(c.get("video_preview_image_url"))

    body = _clean_text(snap.get("body"))
    if (not body or "{{" in body) and cards:
        body = _clean_text(cards[0].get("body")) or body
    title = _clean_text(snap.get("title"))
    if (not title or "{{" in title) and cards:
        title = _clean_text(cards[0].get("title")) or title

    fmt = (snap.get("display_format") or "").upper()
    if not fmt:
        fmt = "VIDEO" if video_urls else ("CAROUSEL" if len(cards) > 1 else "IMAGE")

    start, end = node.get("start_date"), node.get("end_date")
    now = time.time()
    days_running = int((min(now, end or now) - start) / 86400) if start else None

    return {
        "ad_archive_id": str(node.get("ad_archive_id")),
        "ad_library_url": f"https://www.facebook.com/ads/library/?id={node.get('ad_archive_id')}",
        "page_id": str(node.get("page_id") or snap.get("page_id") or ""),
        "page_name": node.get("page_name") or snap.get("page_name") or "Unknown",
        "page_profile_uri": snap.get("page_profile_uri"),
        "page_profile_picture_url": snap.get("page_profile_picture_url"),
        "page_like_count": snap.get("page_like_count"),
        "page_categories": snap.get("page_categories") or [],
        "is_active": node.get("is_active"),
        "start_date": start,
        "end_date": end,
        "days_running": days_running,
        "publisher_platform": node.get("publisher_platform") or [],
        "display_format": fmt,
        "body": body,
        "title": title,
        "link_description": _clean_text(snap.get("link_description")),
        "caption": snap.get("caption"),
        "cta_text": snap.get("cta_text"),
        "cta_type": snap.get("cta_type"),
        "link_url": snap.get("link_url") or (cards[0].get("link_url") if cards else None),
        "image_urls": [u for u in images if u][:5],
        "video_urls": [u for u in video_urls if u][:3],
        "video_preview_urls": [u for u in video_previews if u][:3],
        "num_cards": len(cards),
        "collation_count": node.get("collation_count"),
        "matched_keyword": keyword,
    }


def scrape_keyword(page, keyword: str, country: str, max_ads: int, log) -> tuple[list[dict], int | None]:
    found: dict = {}
    totals: list = []

    def on_response(resp):
        if "graphql" not in resp.url:
            return
        try:
            text = resp.text()
        except Exception:
            return
        if "ad_archive_id" not in text:
            return
        for blob in _parse_json_blobs(text):
            _walk_ads(blob, found)

    page.on("response", on_response)
    url = (
        "https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
        f"&country={country}&q={quote_plus(keyword)}&search_type=keyword_unordered&media_type=all"
    )
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)

        # Initial results are embedded in the HTML as JSON script tags.
        html = page.content()
        for m in SCRIPT_JSON_RE.finditer(html):
            if "ad_archive_id" not in m.group(1) and "search_results_connection" not in m.group(1):
                continue
            try:
                blob = json.loads(m.group(1))
            except Exception:
                continue
            _walk_ads(blob, found)
            t = _walk_total(blob)
            if t is not None:
                totals.append(t)

        # Infinite scroll loads more via GraphQL.
        stagnant = 0
        while len(found) < max_ads and stagnant < 4:
            before = len(found)
            page.mouse.wheel(0, 6000)
            page.wait_for_timeout(2500)
            stagnant = stagnant + 1 if len(found) == before else 0
    except Exception as e:  # keep partial results
        log(f"  ! error on '{keyword}': {e}")
    finally:
        page.remove_listener("response", on_response)

    ads = [normalize(n, keyword) for n in list(found.values())[:max_ads]]
    return ads, (totals[0] if totals else None)


def scrape(keywords: list[str], country: str = "IN", max_ads: int = 60, headless: bool = True, log=print) -> dict:
    all_ads: dict = {}
    totals: dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="en-US", user_agent=USER_AGENT, viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        for kw in keywords:
            log(f"Searching Ads Library: '{kw}' ({country})")
            ads, total = scrape_keyword(page, kw, country, max_ads, log)
            totals[kw] = total
            new = 0
            for a in ads:
                if a["ad_archive_id"] not in all_ads:
                    all_ads[a["ad_archive_id"]] = a
                    new += 1
            log(f"  -> {len(ads)} ads fetched ({new} new), ~{total if total is not None else '?'} total in library")
        browser.close()
    return {"country": country, "keywords": keywords, "keyword_totals": totals,
            "scraped_at": int(time.time()), "ads": list(all_ads.values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keywords", nargs="+", required=True)
    ap.add_argument("--country", default="IN")
    ap.add_argument("--max-ads", type=int, default=60)
    ap.add_argument("--out", required=True)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    def log(msg):
        print(msg, flush=True)

    result = scrape(args.keywords, args.country, args.max_ads, not args.headed, log)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    log(f"DONE {len(result['ads'])} unique ads")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
