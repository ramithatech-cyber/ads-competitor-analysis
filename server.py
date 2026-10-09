"""FastAPI backend for the React portal.

Run:  .venv\\Scripts\\python server.py      ->  http://localhost:8765
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from core.ad_review import review_ad
from core.competitor_analysis import ads_dataframe, aggregate_advertisers, find_own_pages, run_analysis, screen_ads
from core.head_to_head import head_to_head
from core.input_analyzer import analyze_input
from core.media import video_media
from core.personas import competitor_ad_cards, generate_personas, simulate_feed, user_ad_card
from core.report import build_charts, build_html

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "web", "dist")
app = FastAPI(title="Persona Ad Portal")
JOBS: dict[str, dict] = {}


def _log(job, msg):
    job["logs"].append({"t": round(time.time() - job["started"], 1), "msg": msg})


def _summary_stats(df, comps):
    # Market charts describe relevant competitors only, not every ad the keyword search returned.
    names = [c["page_name"] for c in comps if c.get("relevance") in ("direct", "indirect")]
    rel = df[df["page_name"].isin(names)]

    def counts(col, explode=False):
        s = rel[col].explode() if explode else rel[col]
        return [{"name": str(k), "value": int(v)} for k, v in s.dropna().value_counts().head(8).items()]
    return {
        "total_ads": int(len(df)), "advertisers": int(df["page_name"].nunique()),
        "relevant_ads": int(len(rel)), "relevant_advertisers": len(names),
        "direct": sum(1 for c in comps if c.get("relevance") == "direct"),
        "formats": counts("display_format"), "platforms": counts("publisher_platform", True), "ctas": counts("cta_text"),
    }


def _scrape_link(job, url):
    """Run core.link_scraper and turn the link into (kind, caption text, media bytes, file name, mime, page)."""
    out = os.path.join(tempfile.mkdtemp(), "page.json")
    proc = subprocess.Popen([sys.executable, "-m", "core.link_scraper", "--url", url, "--out", out], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    for line in proc.stdout:
        if line.strip():
            _log(job, line.strip())
    proc.wait()
    if proc.returncode != 0 or not os.path.exists(out):
        raise RuntimeError("Could not read that link. Check the URL is public, or upload the ad instead.")
    page = json.load(open(out, encoding="utf-8"))
    caption = page.get("description") or page.get("title") or ""
    context = page if (caption or page.get("text")) else None  # direct media links have no page around them
    if page.get("video_file"):  # video link / reel / video post: full video analysis, same as a video upload
        path = page["video_file"]
        return "video", caption, open(path, "rb").read(), os.path.basename(path), page["video_mime"], context
    if page["kind"] == "image":  # direct image link: same as an image upload
        return "image", "", open(page["image_file"], "rb").read(), "image", page["image_mime"], None
    if page.get("image_file"):  # page with a preview image: full image analysis, same as an image upload
        return "image", caption, open(page["image_file"], "rb").read(), "preview", page["image_mime"], page
    return "text", caption or (page.get("text") or "")[:600], None, "", "", page


def run_job(job_id, kind, text, file_bytes, file_name, mime, brand, country, max_ads, n_keywords):
    job = JOBS[job_id]
    try:
        job["stage"] = "understanding"
        page = None
        if kind == "link":
            url = text.strip()
            _log(job, f"Scraping your link: {url}")
            kind, text, file_bytes, file_name, mime, page = _scrape_link(job, url)
            job["source_url"] = url
            _log(job, f"Link read as {kind} input")
        _log(job, f"Reading your {kind} with OpenAI")
        profile = analyze_input(kind, text, file_bytes, file_name, mime, page)
        if brand:
            profile["brand_name"] = brand
        image_url = None
        if kind == "image" and file_bytes:
            image_url = f"data:{mime or 'image/jpeg'};base64,{base64.b64encode(file_bytes).decode()}"
        elif kind == "video" and profile.get("_frames"):
            # Poster = the opening frame (what people see before deciding to keep watching).
            image_url = "data:image/jpeg;base64," + profile["_frames"][0]
            job["_video"] = (profile.get("_video_path"), mime or "video/mp4")
            job["user_frames"] = [{"t": t, "src": "data:image/jpeg;base64," + f}
                                  for f, t in zip(profile["_frames"], profile.get("_frame_times") or [])]
        job["profile"] = {k: v for k, v in profile.items() if not k.startswith("_")}
        _log(job, f"Category: {profile.get('category')}")

        # Personas in parallel with scraping.
        persona_box = {}

        def make_personas():
            try:
                persona_box["p"] = generate_personas(profile)
                job["personas"] = persona_box["p"]
                _log(job, f"{len(persona_box['p'])} buyer personas created")
            except Exception as e:
                persona_box["err"] = e
        pt = threading.Thread(target=make_personas)
        pt.start()

        job["stage"] = "scraping"
        keywords = (profile.get("search_keywords") or [profile.get("category") or text[:40]])[:n_keywords]
        job["keywords"] = keywords
        out = os.path.join(tempfile.mkdtemp(), "ads.json")
        proc = subprocess.Popen([sys.executable, "-m", "core.ads_scraper", "--keywords", *keywords, "--country", country,
                                 "--max-ads", str(max_ads), "--out", out], cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            if line.strip():
                _log(job, line.strip())
        proc.wait()
        if proc.returncode != 0 or not os.path.exists(out):
            raise RuntimeError("Ads Library scraping failed")
        scraped = json.load(open(out, encoding="utf-8"))
        df = ads_dataframe(scraped["ads"])
        if df.empty:
            raise RuntimeError("No ads found in the Ads Library for these keywords")
        own = find_own_pages(df, profile, brand)
        if own:
            # The user's own pages (brand, founder page, same website or same ad) are never competitors.
            job["own_pages"] = [{"page_name": n, "reason": r, "ads": int((df["page_name"] == n).sum())} for n, r in own.items()]
            _log(job, "Left out your own pages: " + ", ".join(f"{n} ({r})" for n, r in own.items()))
            df = df[~df["page_name"].isin(own)]
            if df.empty:
                raise RuntimeError("Only your own ads were found for these keywords. Try another country.")
        job["ads_found"] = len(df)

        job["stage"] = "analysing"
        _log(job, f"Analysing {len(df)} ads from {df['page_name'].nunique()} advertisers")
        advertisers = aggregate_advertisers(df, profile.get("brand_name"))
        analysis = run_analysis(profile, advertisers)
        comps = analysis["competitors"]
        job["analysis"] = analysis
        job["stats"] = _summary_stats(df, comps)

        pt.join()
        if "err" in persona_box:
            raise persona_box["err"]
        personas = persona_box["p"]

        _log(job, "Checking which rival ads sell the same thing as yours")
        try:
            screen = screen_ads(profile, df, comps)
        except Exception as e:  # fall back to advertiser-level relevance
            _log(job, f"Ad-level check skipped: {e}")
            screen = {}
        rivals = competitor_ad_cards(df, comps, screen, 7)
        if not rivals:
            raise RuntimeError("No competitor ads selling a comparable product were found. "
                               "Try a more specific description or another country.")
        media = {}
        if kind == "video" and profile.get("_frames"):
            media["you"] = {"frames": [x["src"] for x in job.get("user_frames", [])],
                            "times": profile.get("_frame_times") or [], "transcript": profile.get("transcript") or "",
                            "duration": profile.get("_duration"), "segments": profile.get("_segments") or []}
            job["video_meta"] = {"duration": profile.get("_duration"), "segments": profile.get("_segments") or []}
        if any(r.get("video") for r in rivals):
            _log(job, "Watching rival video ads (key frames + voiceover)")
            media.update(video_media(rivals))
            for r in rivals:
                if (media.get(r["id"]) or {}).get("transcript"):
                    r["transcript"] = media[r["id"]]["transcript"]
        job["stage"] = "simulating"
        video_url = f"/api/jobs/{job_id}/video" if kind == "video" else None
        feed = [user_ad_card(profile, image_url, text, video_url)] + rivals
        job["feed"] = feed
        job["reactions"] = []
        _log(job, f"Testing {len(feed)} ads against {len(personas)} personas")
        results = simulate_feed(personas, feed, on_result=lambda r: job["reactions"].append(r), media=media)
        job["reactions"] = results

        job["stage"] = "reviewing"
        _log(job, "Reviewing your hook, edge and improvements vs competitors")
        h2h_box = {}

        def make_h2h():
            try:
                h2h_box["v"] = head_to_head(profile, comps, feed, results, image_url, kind, media)
                if h2h_box["v"]:
                    _log(job, f"Head-to-head vs {h2h_box['v']['competitor']['page_name']} ready")
            except Exception as e:  # optional section: never fail the whole run for it
                traceback.print_exc()
                _log(job, f"Head-to-head skipped: {e}")
        ht = threading.Thread(target=make_h2h)
        ht.start()
        job["review"] = review_ad(profile, feed[0], feed[1:], results, personas, image_url, media)
        ht.join()
        job["head_to_head"] = h2h_box.get("v")

        figs = build_charts(analysis, df)
        job["report_html"] = build_html(profile, analysis, df, figs, scraped, job["review"], image_url,
                                        sim={"feed": feed, "reactions": results, "personas": personas},
                                        user_frames=job.get("user_frames"), video_meta=job.get("video_meta"))
        job["stage"] = "done"
        _log(job, "Done")
    except Exception as e:
        traceback.print_exc()
        job["stage"] = "error"
        job["error"] = str(e)
        _log(job, f"Error: {e}")


@app.post("/api/analyze")
async def analyze(kind: str = Form(...), text: str = Form(""), brand: str = Form(""), country: str = Form("IN"),
                  max_ads: int = Form(50), n_keywords: int = Form(3), file: UploadFile | None = File(None)):
    if kind not in ("text", "image", "video", "link"):
        raise HTTPException(400, "kind must be text, image, video or link")
    data = await file.read() if file else None
    if kind == "text" and not text.strip():
        raise HTTPException(400, "Text is required")
    if kind == "link" and not text.strip().lower().startswith(("http://", "https://")):
        raise HTTPException(400, "Paste a full link starting with http:// or https://")
    if kind in ("image", "video") and not data:
        raise HTTPException(400, f"Upload a {kind}")
    job_id = uuid.uuid4().hex[:10]
    JOBS[job_id] = {"id": job_id, "stage": "queued", "logs": [], "started": time.time()}
    threading.Thread(target=run_job, daemon=True, args=(job_id, kind, text, data, file.filename if file else "",
                                                         file.content_type if file else "", brand, country.upper(),
                                                         max_ads, n_keywords)).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404)
    return {k: v for k, v in job.items() if k not in ("report_html", "report_pdf") and not k.startswith("_")}


@app.get("/api/jobs/{job_id}/video")
def job_video(job_id: str):
    job = JOBS.get(job_id)
    path, mime = (job or {}).get("_video") or (None, None)
    if not path or not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path, media_type=mime)


@app.get("/api/jobs/{job_id}/report", response_class=HTMLResponse)
def job_report(job_id: str):
    job = JOBS.get(job_id)
    if not job or "report_html" not in job:
        raise HTTPException(404, "Report not ready")
    return HTMLResponse(job["report_html"], headers={"Content-Disposition": 'attachment; filename="competitor_report.html"'})


@app.get("/api/jobs/{job_id}/report.pdf")
def job_report_pdf(job_id: str):
    job = JOBS.get(job_id)
    if not job or "report_html" not in job:
        raise HTTPException(404, "Report not ready")
    if not job.get("report_pdf") or not os.path.exists(job["report_pdf"]):
        tmp = tempfile.mkdtemp()
        html_path, pdf_path = os.path.join(tmp, "report.html"), os.path.join(tmp, "competitor_report.pdf")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(job["report_html"])
        proc = subprocess.run([sys.executable, "-m", "core.pdf_export", html_path, pdf_path], cwd=ROOT,
                              capture_output=True, text=True, timeout=180)
        if proc.returncode != 0 or not os.path.exists(pdf_path):
            raise HTTPException(500, f"PDF export failed: {proc.stderr[-400:]}")
        job["report_pdf"] = pdf_path
    name = f"ad_report_{(job.get('profile') or {}).get('brand_name') or 'competitors'}.pdf".replace(" ", "_")
    return FileResponse(job["report_pdf"], media_type="application/pdf", filename=name)


if os.path.isdir(DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        return FileResponse(os.path.join(DIST, "index.html"))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8765")))
