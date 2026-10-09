"""Competitor Ad Intelligence - Streamlit app.

Run:  .venv\\Scripts\\streamlit run app.py
"""
import json
import os
import subprocess
import sys
import tempfile

import streamlit as st

from core.competitor_analysis import ads_dataframe, aggregate_advertisers, run_analysis
from core.input_analyzer import analyze_input
from core.report import build_charts, build_html, top_ads

st.set_page_config(page_title="Competitor Ad Intelligence", page_icon="📊", layout="wide")
ROOT = os.path.dirname(os.path.abspath(__file__))

with st.sidebar:
    st.header("Settings")
    if not os.getenv("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY not found. Add it to the .env file and restart.")
    country = st.text_input("Ads Library country (ISO code)", "IN")
    max_ads = st.slider("Max ads per keyword", 20, 150, 60, 10)
    max_kw = st.slider("Keywords to search", 1, 6, 4)
    top_n = st.slider("Advertisers to analyse", 5, 30, 15)
    st.caption(f"Model: {os.getenv('OPENAI_MODEL', 'gpt-4o')}")

st.title("📊 Competitor Ad Intelligence")
st.write("Upload your ad (video / image) or describe your product. The app finds competitors running ads in the "
         "**Facebook Ads Library**, analyses them with OpenAI and builds a report with visuals.")

kind = st.radio("Input type", ["text", "image", "video"], horizontal=True)
text = st.text_area("Text / product description / ad copy" + (" (optional)" if kind != "text" else ""), height=120)
upload = None
if kind == "image":
    upload = st.file_uploader("Upload image", type=["png", "jpg", "jpeg", "webp"])
    if upload:
        st.image(upload, width=320)
elif kind == "video":
    upload = st.file_uploader("Upload video", type=["mp4", "mov", "webm", "mkv", "avi"])
    if upload:
        st.video(upload)
brand = st.text_input("Your brand name (optional - excluded from competitors)")

if st.button("🔍 Find & analyse competitors", type="primary"):
    if kind == "text" and not text.strip():
        st.warning("Please enter some text."); st.stop()
    if kind != "text" and not upload:
        st.warning(f"Please upload a {kind}."); st.stop()

    with st.status("Working...", expanded=True) as status:
        st.write("🧠 Understanding your input with OpenAI...")
        profile = analyze_input(kind, text, upload.getvalue() if upload else None,
                                upload.name if upload else "", upload.type if upload else "")
        if brand:
            profile["brand_name"] = brand
        keywords = (profile.get("search_keywords") or [profile.get("category") or text[:40]])[:max_kw]
        st.write(f"Category: **{profile.get('category')}** · Search keywords: `{', '.join(keywords)}`")

        st.write("🌐 Scraping Facebook Ads Library (takes ~20-40s per keyword)...")
        out = os.path.join(tempfile.mkdtemp(), "ads.json")
        proc = subprocess.Popen([sys.executable, "-m", "core.ads_scraper", "--keywords", *keywords, "--country", country,
                                 "--max-ads", str(max_ads), "--out", out], cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        log_box = st.empty(); lines = []
        for line in proc.stdout:
            lines.append(line.rstrip()); log_box.code("\n".join(lines[-8:]))
        proc.wait()
        if proc.returncode != 0 or not os.path.exists(out):
            status.update(label="Scraping failed", state="error"); st.stop()
        scraped = json.load(open(out, encoding="utf-8"))
        df = ads_dataframe(scraped["ads"])
        if df.empty:
            status.update(label="No ads found for these keywords", state="error"); st.stop()

        st.write(f"📈 Analysing {len(df)} ads from {df['page_name'].nunique()} advertisers...")
        advertisers = aggregate_advertisers(df, profile.get("brand_name"), top_n)
        analysis = run_analysis(profile, advertisers)
        figs = build_charts(analysis, df)
        report_html = build_html(profile, analysis, df, figs, scraped)
        st.session_state["result"] = dict(profile=profile, analysis=analysis, df=df, figs=figs, html=report_html, scraped=scraped)
        status.update(label="Done!", state="complete", expanded=False)

res = st.session_state.get("result")
if res:
    profile, analysis, df, figs = res["profile"], res["analysis"], res["df"], res["figs"]
    comps = [c for c in analysis["competitors"] if c.get("relevance") in ("direct", "indirect")]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ads analysed", len(df))
    c2.metric("Advertisers", df["page_name"].nunique())
    c3.metric("Direct competitors", sum(1 for c in comps if c.get("relevance") == "direct"))
    c4.metric("Category", profile.get("category") or "-")

    d1, d2, d3 = st.columns(3)
    d1.download_button("⬇️ Download HTML report", res["html"], "competitor_report.html", "text/html", type="primary")
    d2.download_button("⬇️ Ads data (CSV)", df.drop(columns=["start_dt"]).to_csv(index=False), "ads.csv", "text/csv")
    d3.download_button("⬇️ Analysis (JSON)", json.dumps({k: v for k, v in profile.items() if not k.startswith('_')} | {"analysis": analysis},
                                                      ensure_ascii=False, indent=2, default=str), "analysis.json", "application/json")

    t1, t2, t3, t4, t5 = st.tabs(["Summary", "Visuals", "Competitors", "Top ads", "Recommendations"])
    with t1:
        st.subheader("Executive summary"); st.write(analysis.get("executive_summary"))
        st.subheader("Your input")
        st.json({k: v for k, v in profile.items() if not k.startswith("_")}, expanded=False)
        fb = analysis.get("user_ad_feedback") or {}
        a, b = st.columns(2)
        a.markdown("**Strengths**\n" + "\n".join(f"- {x}" for x in fb.get("strengths", [])))
        b.markdown("**Weaknesses**\n" + "\n".join(f"- {x}" for x in fb.get("weaknesses", [])))
    with t2:
        keys = list(figs)
        for i in range(0, len(keys), 2):
            cols = st.columns(2)
            for col, k in zip(cols, keys[i:i + 2]):
                col.markdown(figs[k], unsafe_allow_html=True)
    with t3:
        for c in comps:
            with st.expander(f"{c['page_name']} — {c.get('relevance')} · {c['active_ads']} ads · threat {c.get('threat_score', '-')}/10"):
                l, r = st.columns([1, 2])
                l.write(f"**Page likes:** {c.get('page_likes') or '-'}")
                l.write(f"**Longest-running ad:** {c.get('max_days_running') or '-'} days")
                l.write(f"**Formats:** {c.get('formats')}")
                l.write(f"**CTAs:** {c.get('ctas')}")
                if c.get("page_profile_uri"):
                    l.markdown(f"[Facebook page ↗]({c['page_profile_uri']})")
                r.write(f"**Positioning:** {c.get('positioning', '')}")
                for label, key in [("Key messages", "key_messages"), ("Hooks", "hooks"), ("Offers", "offers"),
                                   ("Strengths", "strengths"), ("Weaknesses", "weaknesses")]:
                    if c.get(key):
                        r.markdown(f"**{label}:** " + "; ".join(map(str, c[key])))
    with t4:
        ads = top_ads(df, [c["page_name"] for c in comps], 18)
        cols = st.columns(3)
        for i, (_, a) in enumerate(ads.iterrows()):
            with cols[i % 3].container(border=True):
                img = (a["image_urls"] or a["video_preview_urls"] or [None])[0]
                if img:
                    st.image(img, width="stretch")
                st.markdown(f"**{a['page_name']}** · {a['display_format']} · {a['days_running']} days running")
                st.caption((a["body"] or "")[:280])
                st.markdown(f"[View in Ads Library ↗]({a['ad_library_url']})")
    with t5:
        st.subheader("Gaps & opportunities")
        st.markdown("\n".join(f"- {g}" for g in analysis.get("gaps_opportunities", [])))
        st.subheader("Recommendations")
        for r in analysis.get("recommendations", []):
            icon = {"high": "🔴", "medium": "🟠"}.get(r.get("priority"), "🟢")
            st.markdown(f"{icon} **{r.get('title')}** — {r.get('detail')}")
        st.subheader("Ad copy ideas")
        for idea in analysis.get("ad_copy_ideas", []):
            with st.container(border=True):
                st.markdown(f"**Hook:** {idea.get('hook')}\n\n{idea.get('body')}\n\n**CTA:** {idea.get('cta')}")
