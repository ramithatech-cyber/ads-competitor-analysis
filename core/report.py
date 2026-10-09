"""Self-contained HTML report (also rendered to PDF).

Every block is labelled with where its content comes from, so readers can tell facts from judgement:
  From Ads Library = copied from the public Facebook Ads Library
  Counted          = computed from that data with a fixed formula
  AI judgement     = OpenAI's reading of the real ads (quotes are verified against the ad text)
  Simulation       = 30 AI buyer personas; an estimate, not real audience data
Charts are inline SVG (see svgcharts.py): no JavaScript or CDN, so they look the same on screen and in the PDF."""
from __future__ import annotations

import html
from collections import Counter
from datetime import datetime

import pandas as pd

from . import svgcharts as sc
from .media import embed_many

e = html.escape


def _relevant(comps, include_indirect=True):
    keep = {"direct", "indirect"} if include_indirect else {"direct"}
    return [c for c in comps if c.get("relevance") in keep]


def build_charts(analysis: dict, df: pd.DataFrame) -> dict[str, str]:
    """Market charts as inline SVG strings. Only relevant competitors are counted."""
    comps = _relevant(analysis["competitors"])[:12]
    names = [c["page_name"] for c in comps]
    rel_df = df[df["page_name"].isin(names)] if not df.empty else df
    ch: dict[str, str] = {}
    if not comps:
        return ch

    ch["ads_per_competitor"] = sc.hbar([{"label": c["page_name"], "value": c.get("competing_ads", c["active_ads"]),
                                         "color": sc.CLAY if c.get("relevance") == "direct" else sc.MUTED} for c in comps])
    tc = sorted(comps, key=lambda c: c.get("threat_score") or 0, reverse=True)
    ch["threat"] = sc.hbar([{"label": c["page_name"], "value": c.get("threat_score") or 0, "hi": i == 0}
                            for i, c in enumerate(tc)], vmax=10)
    lg = sorted([c for c in comps if c.get("max_days_running")], key=lambda c: c["max_days_running"], reverse=True)[:10]
    ch["longevity"] = sc.hbar([{"label": c["page_name"], "value": c["max_days_running"], "hi": i == 0}
                               for i, c in enumerate(lg)], unit="d")

    th = analysis.get("market_themes") or []
    if th:
        ch["themes"] = sc.hbar([{"label": t.get("theme"), "value": t.get("prevalence", 0),
                                 "note": f"{len(t.get('used_by') or [])} of {len(comps)}"} for t in th], vmax=100, unit="%")
    if not rel_df.empty:
        fc = Counter(rel_df["display_format"]).most_common()
        ch["formats"] = sc.donut([{"label": k, "value": v} for k, v in fc])
        pc = Counter(p for ps in rel_df["publisher_platform"] for p in ps).most_common()
        ch["platforms"] = sc.hbar([{"label": k.replace("_", " ").title(), "value": v} for k, v in pc], color=sc.CLAY)
        cc = Counter(c for c in rel_df["cta_text"].dropna() if c).most_common(8)
        if cc:
            ch["ctas"] = sc.hbar([{"label": k, "value": v} for k, v in cc])
        t = rel_df.dropna(subset=["start_date"])
        top = [n for n in names if n in set(t["page_name"])][:10]
        ch["timeline"] = sc.timeline([(n, list(t[t["page_name"] == n]["start_date"])) for n in top])

    s = analysis.get("scores") or {}
    dims = s.get("dimensions") or []
    bc = s.get("best_competitor") or {}
    ch["scorecard"] = sc.grouped_hbar(dims, [("Your ad", s.get("user"), sc.CLAY),
                                             ("Competitor average", s.get("competitor_avg"), sc.INK),
                                             (f"Best: {bc.get('name')}", bc.get("values"), "#9C9A92") if bc else ("", None, "")])
    return ch


def top_ads(df: pd.DataFrame, names: list[str], n: int = 12) -> pd.DataFrame:
    if df.empty:
        return df
    d = df[df["page_name"].isin(names)].copy()
    d = d[d["body"].fillna("").str.len() > 0]
    return d.sort_values("days_running", ascending=False).drop_duplicates("body").head(n)


# ── small building blocks ────────────────────────────────────────────────────────────────────────────────────────

SRC = {"fact": "From Ads Library", "count": "Counted", "ai": "AI judgement", "sim": "Simulation", "you": "Your ad as given"}


def tag(kind: str) -> str:
    return f'<span class="src {kind}">{SRC[kind]}</span>'


def _li(items):
    return "".join(f"<li>{e(str(i))}</li>" for i in (items or []) if i)


def _num(v):
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "–"


def _compact(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return "–"
    return f"{v / 1e6:.1f}M" if v >= 1e6 else f"{v / 1e3:.1f}K" if v >= 1e4 else f"{v:,}"


def chart_card(title: str, svg: str, src: str, note: str = "") -> str:
    if not svg:
        return ""
    return (f'<div class="card chart"><div class="ch-h"><h3>{e(title)}</h3>{tag(src)}</div>'
            f'{f"<p class=note>{note}</p>" if note else ""}{svg}</div>')


def section(n: int, title: str, sub: str, body: str, new_page: bool = False) -> str:
    if not body.strip():
        return ""
    return (f'<section class="{"pb" if new_page else ""}"><div class="sec-h"><span class="sec-n">{n:02d}</span>'
            f'<div><h2>{e(title)}</h2><p>{e(sub)}</p></div></div>{body}</section>')


KIND_COLOR = {"strength": "#3BA55C", "weakness": "#E5484D", "fix": "#D97757"}
KIND_LABEL = {"strength": "✓ Keep", "weakness": "✗ Weak", "fix": "→ Fix"}


# ── sections ─────────────────────────────────────────────────────────────────────────────────────────────────────

def scroll_test_html(sim: dict | None) -> str:
    if not sim or not sim.get("reactions"):
        return ""
    feed, reactions, personas = sim["feed"], sim["reactions"], sim.get("personas") or []
    by_ad = {r["ad_id"]: r for r in reactions}
    rows = []
    for ad in feed:
        r = by_ad.get(ad["id"]) or {}
        rows.append({"label": "★ Your ad" if ad.get("is_user") else ad["advertiser"], "value": r.get("stop_rate") or 0,
                     "hi": ad.get("is_user"), "note": f"{r.get('stopped', 0)}/30 stopped · {r.get('clicked', 0)} click"})
    rows.sort(key=lambda x: x["value"], reverse=True)
    rank = next((i + 1 for i, r in enumerate(rows) if r["hi"]), "-")
    mine = by_ad.get("you") or {}
    pmap = {p["id"]: p for p in personas}

    def quote(x):
        p = pmap.get(x["id"], {})
        state = "clicked" if x["clicked"] else f"stopped {x['watch_seconds']:.0f}s" if x["stopped"] else "scrolled past"
        return (f'<div class="q {"yes" if x["stopped"] else ""}"><b>{e(p.get("name", "?"))}, {e(str(p.get("age", "")))}</b>'
                f' <small>{e(p.get("role", ""))} · {e(p.get("city", ""))}</small><span class="pill">{state}</span>'
                f'<div>“{e(x.get("reason", ""))}”</div></div>')
    rs = mine.get("reactions") or []
    stopped = sorted([x for x in rs if x["stopped"]], key=lambda x: -x["watch_seconds"])[:6]
    passed = [x for x in rs if not x["stopped"]][:6]
    return f"""<div class="callout"><div class="big">{mine.get('stopped', 0)}<small>/30</small></div>
<div><b>simulated buyers stopped on your ad</b>, ranked <b>#{rank} of {len(rows)}</b> ads in the same feed.
<br><small>{mine.get('clicked', 0)} would click · average watch {mine.get('avg_watch', 0)}s · the other {len(rows) - 1} ads are
real competitor ads from the Ads Library.</small></div>{tag('sim')}</div>
{chart_card('Stop rate per ad in the feed (% of 30 buyers)', sc.hbar(rows, vmax=100, unit='%', label_w=200), 'sim')}
<div class="grid2 avoid"><div class="card"><h3>Why buyers stopped</h3>{''.join(map(quote, stopped)) or '<p class=muted>Nobody stopped.</p>'}</div>
<div class="card"><h3>Why buyers scrolled past</h3>{''.join(map(quote, passed)) or '<p class=muted>Everyone stopped.</p>'}</div></div>"""


def _highlight(text: str, anns: list[dict]) -> str:
    """The user's own ad text with each annotation quote marked and numbered."""
    spans = []
    low = text.lower()
    for a in anns:
        q = a.get("quote") or ""
        i = low.find(q.lower()) if q else -1
        if i >= 0 and not any(i < x[1] and i + len(q) > x[0] for x in spans):
            spans.append((i, i + len(q), a))
    out, pos = "", 0
    for st, en, a in sorted(spans, key=lambda x: x[0]):
        col = KIND_COLOR.get(a.get("kind"), "#D97757")
        out += e(text[pos:st]) + (f"<mark style='background:{col}22;border-bottom:2px solid {col}'>{e(text[st:en])}"
                                  f"<sup style='color:{col}'>{a['n']}</sup></mark>")
        pos = en
    return f"<div class='adtext'>{out + e(text[pos:])}</div>"


def annotated_html(rv: dict, image: str | None, text: str | None = None, is_video: bool = False) -> str:
    anns = rv.get("annotations") or []
    if not anns:
        return ""
    visual = ""
    if text and not (image and rv.get("has_image")):
        visual = _highlight(text, anns)
    if image and rv.get("has_image"):
        marks = ""
        for a in anns:
            b = a.get("box")
            if not b:
                continue
            col = KIND_COLOR.get(a.get("kind"), "#D97757")
            marks += (f"<span class='abox' style='left:{b['x'] * 100:.1f}%;top:{b['y'] * 100:.1f}%;width:{b['w'] * 100:.1f}%;"
                      f"height:{b['h'] * 100:.1f}%;border-color:{col}'><i style='background:{col}'>{a['n']}</i></span>")
        visual = (f"<div><div class='aimg'><img src='{image}'>{marks}</div>"
                  f"{'<small>Opening frame of your video (the first second people see).</small>' if is_video else ''}</div>")
    items = "".join(
        f"<div class='aitem'><span class='apin' style='background:{KIND_COLOR.get(a.get('kind'), '#D97757')}'>{a['n']}</span>"
        f"<div><b>{KIND_LABEL.get(a.get('kind'), '')} · {e(a.get('label', ''))}</b>"
        f"{('<br><i>“' + e(a['quote']) + '”</i>') if a.get('quote') else ''}<br><small>{e(a.get('note', ''))}</small></div></div>"
        for a in anns)
    return (f"<div class='card annot {'' if visual else 'solo'}'>{visual}<div><div class='ch-h'><h3>Your ad, marked up</h3>"
            f"{tag('ai')}</div>{items}</div></div>")


def video_strip_html(frames: list[dict] | None, transcript: str | None, caption: str | None) -> str:
    if not frames:
        return ""
    cells = "".join(f"<div><img src='{f['src']}'><small>{f['t']}s</small></div>" for f in frames)
    return (f"<div class='card avoid'><div class='ch-h'><h3>Your video, frame by frame</h3>{tag('you')}</div>"
            f"<div class='vstrip'>{cells}</div>"
            + (f"<p><b>Caption:</b> {e(caption)}</p>" if caption else "")
            + (f"<p><b>Voiceover (transcribed):</b> <span class='muted'>{e(transcript)}</span></p>" if transcript else
               "<p class='muted'>No speech detected in the video.</p>") + "</div>")


def _retention(rs: list[dict], t: float) -> float:
    return 100 * sum(r["watch_seconds"] >= t for r in rs) / len(rs) if rs else 0


def video_timeline_html(rv: dict, sim: dict | None, frames: list[dict] | None, vmeta: dict | None,
                        caption: str | None) -> str:
    """Static version of the portal's Video timeline: drop-off curve + time-coded pins on one time axis,
    the key frames aligned under it, then every pin with the exact frame (and box) it refers to."""
    frames, vmeta, anns = frames or [], vmeta or {}, rv.get("annotations") or []
    reactions = (sim or {}).get("reactions") or []
    mine = next((r.get("reactions") or [] for r in reactions if r.get("ad_id") == "you"), [])
    rivals = [r["reactions"] for r in reactions if r.get("ad_id") != "you" and r.get("reactions")]
    dur = vmeta.get("duration") or (frames[-1]["t"] if frames else 1) or 1
    W, L, R, B, LANE = 680, 34, 10, 20, 19
    X = lambda t: L + (W - L - R) * min(max(t, 0), dur) / dur
    lanes, placed = {}, []  # pins at the same moment stack upwards instead of overlapping
    for a in anns:
        lane = 0
        while any(pl == lane and abs(X(pt) - X(a["t"])) < 18 for pt, pl in placed):
            lane += 1
        placed.append((a["t"], lane))
        lanes[a["n"]] = lane
    T = (max(lanes.values(), default=0) + 1) * LANE + 6
    H = T + 112
    CY = lambda a: T - 13 - lanes[a["n"]] * LANE
    Y = lambda p: T + (H - T - B) * (100 - p) / 100
    steps = [min(dur, i / 4) for i in range(int(dur * 4) + 2)]
    pts = lambda f: " ".join(f"{'M' if i == 0 else 'L'}{X(t):.1f},{Y(100 if t == 0 else f(t)):.1f}" for i, t in enumerate(steps))
    you = pts(lambda t: _retention(mine, t))
    svg = [f'<line x1="{L}" x2="{W - R}" y1="{Y(p)}" y2="{Y(p)}" stroke="{sc.GRID}"/><text x="{L - 4}" y="{Y(p) + 3}" '
           f'font-size="9" text-anchor="end" fill="{sc.TEXT2}">{p}%</text>' for p in (0, 50, 100)]
    svg.append(f'<path d="{you} L{X(dur):.1f},{Y(0)} L{X(0)},{Y(0)} Z" fill="{sc.CLAY}" fill-opacity=".16"/>'
               f'<path d="{you}" fill="none" stroke="{sc.CLAY}" stroke-width="2.2"/>')
    if rivals:
        svg.append(f'<path d="{pts(lambda t: sum(_retention(r, t) for r in rivals) / len(rivals))}" fill="none" '
                   f'stroke="{sc.INK}" stroke-width="1.3" stroke-dasharray="4 3"/>')
    tick = 1 if dur <= 20 else 5
    svg += [f'<text x="{X(t):.1f}" y="{H - 5}" font-size="9" text-anchor="middle" fill="{sc.TEXT2}">{t}s</text>'
            for t in range(0, int(dur) + 1, tick)]
    for a in anns:
        col = KIND_COLOR.get(a.get("kind"), sc.CLAY)
        svg.append(f'<line x1="{X(a["t"]):.1f}" x2="{X(a["t"]):.1f}" y1="{CY(a) + 8}" y2="{H - B}" stroke="{col}" stroke-dasharray="2 2" opacity=".6"/>'
                   f'<circle cx="{X(a["t"]):.1f}" cy="{CY(a)}" r="8" fill="{col}" stroke="#fff" stroke-width="1.5"/>'
                   f'<text x="{X(a["t"]):.1f}" y="{CY(a) + 3.5}" font-size="9.5" font-weight="800" fill="#fff" text-anchor="middle">{a["n"]}</text>')
    chart = sc._wrap("".join(svg), H)
    strip = "".join(f"<div><img src='{f['src']}'><small>{f['t']}s</small></div>" for f in frames)
    at3 = round(_retention(mine, min(3, dur)))
    full = sum(r["watch_seconds"] >= dur - 0.05 for r in mine)
    riv3 = round(sum(_retention(r, min(3, dur)) for r in rivals) / len(rivals)) if rivals else None

    def pin(a):
        col = KIND_COLOR.get(a.get("kind"), sc.CLAY)
        thumb = ""
        if a.get("frame") is not None and a["frame"] < len(frames):
            b = a.get("box") or {}
            box = (f"<span class='abox' style='left:{b['x'] * 100:.0f}%;top:{b['y'] * 100:.0f}%;width:{b['w'] * 100:.0f}%;"
                   f"height:{b['h'] * 100:.0f}%;border-color:{col}'></span>") if b else ""
            thumb = f"<div class='vt-th'><img src='{frames[a['frame']]['src']}'>{box}</div>"
        else:
            thumb = "<div class='vt-th audio'>🎙</div>"
        return (f"<div class='vt-pin'>{thumb}<div><b><span class='apin' style='background:{col}'>{a['n']}</span>"
                f"{a['t']}s · {KIND_LABEL.get(a.get('kind'), '')} · {e(a.get('label', ''))}</b>"
                f"{('<i>“' + e(a['quote']) + '”</i>') if a.get('quote') else ''}<small>{e(a.get('note', ''))}</small></div></div>")
    voice = " ".join(f"<span><b>{g['start']}s</b> {e(g['text'])}</span>" for g in vmeta.get("segments") or [])
    return f"""<div class="card vt"><div class="ch-h"><h3>Video timeline · where buyers leave, and why</h3>{tag('sim')}{tag('ai')}
<span class="vt-lg"><i class="you"></i>You <i class="rival"></i>Rival ads avg</span></div>
{chart}<div class="vt-strip" style="padding:0 {100 * R / W:.1f}% 0 {100 * L / W:.1f}%">{strip}</div>
<div class="vt-stats"><span><b>{at3}%</b> still watching at 3s</span><span><b>{full}/{len(mine) or 30}</b> watched to the end</span>
{f"<span><b>{riv3}%</b> rival ads avg at 3s</span>" if riv3 is not None else ''}<span><b>{dur}s</b> video length</span></div>
<div class="vt-pins">{''.join(pin(a) for a in anns)}</div>
{f"<p class='vt-voice'><b>Caption:</b> {e(caption)}</p>" if caption else ''}
{f"<p class='vt-voice'><b>Voiceover:</b> {voice}</p>" if voice else ''}</div>"""


def review_html(rv: dict | None, image: str | None = None, user_ad: dict | None = None,
                user_frames: list[dict] | None = None, sim: dict | None = None, video_meta: dict | None = None) -> str:
    if not rv:
        return ""
    h, st, ia, scd = rv.get("hook") or {}, rv.get("standout") or {}, rv.get("improved_ad") or {}, rv.get("scorecard") or {}
    metrics = "".join(f"<div class='mrow'><span>{e(k)}</span><span class='mtrack'><i style='width:{10 * (v or 0)}%'></i></span><b>{v}</b></div>"
                      for k, v in (h.get("metrics") or {}).items())
    comp_hooks = "".join(f"<tr><td><b>{e(c.get('advertiser', ''))}</b></td><td>“{e(c.get('hook', ''))}”</td><td>{e(c.get('type', ''))}</td>"
                         f"<td class=c>{c.get('score', '')}</td><td>{e(c.get('lesson', ''))}</td></tr>" for c in h.get("competitor_hooks", []))
    rewrites = "".join(f"<li><b>“{e(r.get('hook', ''))}”</b> <small>({e(r.get('type', ''))}) {e(r.get('why', ''))}</small></li>" for r in h.get("rewrites", []))

    def quad(title, items, extra):
        lis = "".join(f"<li><b>{e(x.get('label') or x.get('point') or '')}</b> <small>{e(extra(x))}</small></li>" if isinstance(x, dict)
                      else f"<li>{e(str(x))}</li>" for x in (items or []))
        return f"<div class='quad'><h4>{title}</h4><ul>{lis or '<li class=muted>none found</li>'}</ul></div>"
    quads = (quad("🏆 Only you", st.get("unique"), lambda x: " · ".join(filter(None, [x.get("point"), x.get("evidence")])))
             + quad("👥 Everyone says it", st.get("shared"), lambda x: f"{x.get('point', '')} (also: {', '.join(x.get('competitors', []))})")
             + quad("⚠️ They have, you don't", st.get("missing"), lambda x: f"{x.get('point', '')} ({', '.join(x.get('who', []))})"
                    + (f" “{x['evidence']}”" if x.get("evidence") else ""))
             + quad("🚀 Nobody owns it yet", st.get("unclaimed"), lambda x: x.get("point", "") if x.get("label") else ""))
    imps = "".join(
        f"<div class='rec {e(i.get('impact', 'medium'))}'><div class='rec-h'><b>{e(i.get('title') or i.get('fix', ''))}</b>"
        f"<span class='pill'>{e(i.get('area', ''))}</span><span class='pill {e(i.get('impact', ''))}'>{e(i.get('impact', ''))} impact</span></div>"
        f"<p><small>NOW</small> {e(i.get('problem', ''))}<br><small>DO</small> {e(i.get('fix', ''))}"
        f"{('<br><small>EXAMPLE</small> ' + e(i['example'])) if i.get('example') else ''}"
        f"{('<br><small>SEEN IN</small> ' + e(i['inspired_by'])) if i.get('inspired_by') else ''}</p></div>"
        for i in rv.get("improvements", []))
    ua = user_ad or {}
    is_video = ua.get("format") == "VIDEO"
    if rv.get("timeline"):
        top = video_timeline_html(rv, sim, user_frames, video_meta, ua.get("body"))
    else:
        top = (video_strip_html(user_frames, ua.get("transcript"), ua.get("body")) if is_video else "") \
            + annotated_html(rv, image, None if is_video else ua.get("body"), is_video)
    return f"""{top}
<div class="card hook avoid"><div class="ch-h"><h3>Hook check · first 3 seconds</h3>{tag('ai')}</div>
<div class="hook-grid"><div><blockquote>“{e(h.get('text', ''))}”</blockquote>
<p><span class="pill">{e(h.get('type', ''))}</span> {e(h.get('verdict', ''))}</p>
<div class="grid2 tight"><div><b>Works</b><ul>{_li(h.get('works'))}</ul></div><div><b>Fails</b><ul>{_li(h.get('fails'))}</ul></div></div></div>
<div class="score-box"><div class="ring"><b>{h.get('score', '–')}</b><small>/10</small></div>{metrics}</div></div></div>
{f'''<div class="card avoid"><div class="ch-h"><h3>Competitor hooks in the same feed</h3>{tag('fact')}{tag('ai')}</div>
<p class="note">Hooks are quoted exactly from the competitors' live ads (verified against the ad text); type, score and lesson are AI judgement.</p>
<table><tr><th>Advertiser</th><th>Hook (verbatim)</th><th>Type</th><th>Score</th><th>Lesson</th></tr>{comp_hooks}</table></div>''' if comp_hooks else ''}
<div class="card avoid"><div class="ch-h"><h3>Hooks to test instead</h3>{tag('ai')}</div><ol>{rewrites}</ol></div>
<div class="card avoid"><div class="ch-h"><h3>Stand-out map</h3>{tag('ai')}</div>
<p>{e(st.get('positioning_now', ''))}</p><div class="quads">{quads}</div>
{f"<p class='pos'>🎯 <b>Suggested positioning:</b> {e(st['positioning_suggested'])}</p>" if st.get('positioning_suggested') else ''}</div>
<div class="ch-h"><h3>How to improve your ad</h3>{tag('ai')}<span class="muted small">Ad score now {scd.get('before', '–')}/100 → est. {scd.get('after_estimate', '–')}/100 after fixes</span></div>
{imps}
<div class="card improved avoid"><div class="ch-h"><h3>Improved version</h3>{tag('ai')}</div><h4>{e(ia.get('hook', ''))}</h4>
<p class="pre">{e(ia.get('primary_text', ''))}</p><p><b>Headline:</b> {e(ia.get('headline', ''))} · <b>CTA:</b> {e(ia.get('cta', ''))}<br>
<b>Visual:</b> {e(ia.get('visual_direction', ''))}</p></div>"""


def competitors_html(comps: list[dict], charts: dict) -> str:
    rows = "".join(
        f"<tr><td><b>{e(c['page_name'])}</b><br><small>{e(', '.join(c.get('page_categories') or []))}</small></td>"
        f"<td><span class='rel {e(c['relevance'])}'>{e(c['relevance'])}</span></td>"
        f"<td>{e(c.get('sells') or '–')}{('<br><small>“' + e(c['evidence']) + '”</small>') if c.get('evidence') else ''}</td>"
        f"<td class=c>{c.get('competing_ads', c['active_ads'])}</td><td class=c>{c.get('max_days_running') or '–'}</td>"
        f"<td class=c>{_compact(c.get('page_likes'))}</td><td class=c><b>{c.get('threat_score', '–')}</b></td></tr>"
        for c in comps)
    table = (f"<div class='card'><div class='ch-h'><h3>Who you are up against</h3>{tag('fact')}{tag('count')}{tag('ai')}</div>"
             "<p class='note'>Ads, longest ad and page likes come straight from the Ads Library. Relevance and “sells” are AI "
             "judgement, each backed by the quoted phrase from that advertiser's own ad.</p>"
             "<table><tr><th>Advertiser</th><th>Type</th><th>Sells (with proof from their ad)</th><th>Competing ads</th>"
             f"<th>Longest ad (days)</th><th>Page likes</th><th>Threat /10</th></tr>{rows}</table></div>")
    return (table
            + chart_card("Threat score (0-10)", charts.get("threat", ""), "count",
                         "Formula: relevance 40% + ads competing with yours 25% + longest-running ad 20% + page size 15%.")
            + chart_card("Competing ads per competitor", charts.get("ads_per_competitor", ""), "fact", "Orange = direct competitor.")
            + chart_card("Longest-running active ad (days)", charts.get("longevity", ""), "count",
                         "Ads that keep running for months are usually the ones that make money."))


def profiles_html(comps: list[dict]) -> str:
    cards = []
    for c in comps:
        hooks = "".join(f"<q>{e(x)}</q>" for x in c.get("hooks") or [])
        offers = "".join(f"<span class='chip'>{e(x)}</span>" for x in c.get("offers") or [])
        thumbs = "".join(f"<a href='{e(a['url'])}'><img src='{a['image']}'><small>{a['days']}d · {e(a['format'] or '')}</small></a>"
                         for a in c.get("ads") or [] if a.get("image", "").startswith("data:"))
        pic = (f"<img class='pp' src='{c['profile_pic']}'>" if (c.get("profile_pic") or "").startswith("data:")
               else f"<span class='pp'>{e(c['page_name'][:1])}</span>")
        cards.append(f"""<div class="card prof avoid"><div class="prof-h">{pic}<div><b>{e(c['page_name'])}</b>
<small>{e(', '.join(c.get('page_categories') or []))}</small></div><span class="rel {e(c['relevance'])}">{e(c['relevance'])}</span></div>
<div class="kv"><span><b>{c.get('competing_ads', c['active_ads'])}</b>competing ads</span><span><b>{c.get('max_days_running') or '–'}</b>longest ad (d)</span>
<span><b>{_compact(c.get('page_likes'))}</b>page likes</span><span><b>{c.get('threat_score', '–')}</b>threat /10</span></div>
{f"<div class='blk'>{tag('fact')} <b>Hooks</b>{hooks}</div>" if hooks else ''}
{f"<div class='blk'>{tag('fact')} <b>Offers</b><div class='chips'>{offers}</div></div>" if offers else ''}
{f'''<div class="blk">{tag('ai')} <b>Positioning</b><p>{e(c['positioning'])}</p>
<div class="grid2 tight"><div><small>STRENGTHS</small><ul>{_li(c.get('strengths'))}</ul></div><div><small>WEAKNESSES</small><ul>{_li(c.get('weaknesses'))}</ul></div></div></div>''' if c.get('positioning') else ''}
{f"<div class='thumbs'>{thumbs}</div>" if thumbs else ''}
{f"<a class='lnk' href='{e(c['page_profile_uri'])}'>Facebook page ↗</a>" if c.get('page_profile_uri') else ''}</div>""")
    return f"<div class='flex2'>{''.join(cards)}</div>"


def feed_ads_html(sim: dict | None) -> str:
    rivals = [a for a in (sim or {}).get("feed", []) if not a.get("is_user")]
    if not rivals:
        return ""
    by_ad = {r["ad_id"]: r for r in (sim or {}).get("reactions", [])}
    out = []
    for a in rivals:
        r = by_ad.get(a["id"]) or {}
        img = a.get("image") if (a.get("image") or "").startswith("data:") else None
        started = datetime.fromtimestamp(a["start_date"]).strftime("%d %b %Y") if a.get("start_date") else "–"
        out.append(f"""<div class="fad avoid">{f"<img src='{img}'>" if img else f"<div class='noimg'>{e(a.get('format') or '')}</div>"}
<div class="fad-b"><b>{e(a['advertiser'])}</b><small>{e(a.get('format') or '')} · live since {started} ({a.get('days_running', 0)} days)</small>
{f"<div class='sells'>Sells: {e(a['sells'])}</div>" if a.get('sells') else ''}
<p>{e((a.get('body') or '')[:260])}{'…' if len(a.get('body') or '') > 260 else ''}</p>
{f"<p class='muted'>🎙 “{e(a['transcript'][:160])}{'…' if len(a['transcript']) > 160 else ''}”</p>" if a.get('transcript') else ''}
<div class="fad-f"><span class="pill">{r.get('stopped', 0)}/30 stopped</span><a href="{e(a.get('ad_library_url') or '')}">View in Ads Library ↗</a></div></div></div>""")
    return (f"<p class='note'>{tag('fact')} These are the real competitor ads (copy and creative as published) that were put "
            f"in the same feed as your ad. Each one was checked to sell something comparable to your product.</p>"
            f"<div class='fads'>{''.join(out)}</div>")


def methodology_html(meta: dict, analysis: dict, df: pd.DataFrame, n_rel: int, has_sim: bool) -> str:
    totals = meta.get("keyword_totals") or {}
    kw = "".join(f"<tr><td>{e(k)}</td><td class=c>{_num(v) if v is not None else '–'}</td></tr>" for k, v in totals.items())
    scraped = datetime.fromtimestamp(meta["scraped_at"]).strftime("%d %b %Y %H:%M") if meta.get("scraped_at") else "–"
    return f"""<div class="grid2"><div class="card"><h3>Data source</h3><ul>
<li>Public Facebook Ads Library, <b>active ads only</b>, country <b>{e(meta.get('country', 'IN'))}</b>, collected {scraped}.</li>
<li>{len(df)} ads from {df['page_name'].nunique() if not df.empty else 0} advertisers were returned by the keyword search;
{n_rel} advertisers were judged relevant and used for every market chart.</li>
<li>Days running = today minus the ad's start date in the Ads Library. Page likes as shown in the Ads Library.</li></ul>
<table><tr><th>Search keyword</th><th>Ads in library</th></tr>{kw}</table></div>
<div class="card"><h3>How each label is produced</h3><ul>
<li>{tag('fact')} copied as-is: ad copy, hooks (first line of the ad), offers (price / discount / free / refund phrases found in the copy), formats, placements, CTA buttons, dates.</li>
<li>{tag('count')} fixed formulas on that data: counts, shares, longest ad, theme prevalence (% of relevant competitors whose copy contains the theme's words), threat score (relevance 40%, ads competing with yours 25%, longest ad 20%, page size 15%).</li>
<li>{tag('ai')} OpenAI's reading of the real ads: relevance, positioning, strengths, scores and suggestions. Competitor quotes are checked against the ad text and removed if they cannot be found; a "direct competitor" label needs a quote from that advertiser's own ad.</li>
{f"<li>{tag('sim')} 30 AI buyer personas react to each ad (copy + creative). These are estimates for comparing ads, not real audience data.</li>" if has_sim else ''}
</ul></div></div>"""


CSS = """
:root{--ink:#141413;--ink2:#3D3D3A;--muted:#73726C;--line:#E8E6DC;--cream:#F7F6F1;--clay:#D97757;--clay2:#C15F3C;--tint:#FBEDE6}
*{box-sizing:border-box} body{font-family:"Segoe UI",Inter,Arial,"Nirmala UI",sans-serif;background:#fff;color:var(--ink);margin:0;padding:24px;font-size:13px;line-height:1.5}
.wrap{max-width:1000px;margin:auto} h1,h2,h3,h4{margin:0;line-height:1.25} h3{font-size:14px} h4{font-size:13px;margin-bottom:4px}
small,.muted{color:var(--muted)} .small{font-size:11px} ul,ol{margin:4px 0;padding-left:18px} li{margin:2px 0}
.cover{background:var(--ink);color:#fff;border-radius:18px;padding:26px 28px;margin-bottom:14px}
.cover .eyebrow{color:var(--clay);font-weight:700;letter-spacing:.12em;font-size:11px;text-transform:uppercase}
.cover h1{font-size:28px;margin:6px 0} .cover p{margin:0;color:#D9D6CC} .cover .meta{margin-top:10px;font-size:11px;color:#B9B6AA}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:12px 0}
.kpi{border:1px solid var(--line);border-radius:12px;padding:10px 12px;background:#fff} .kpi b{display:block;font-size:22px;color:var(--clay2)} .kpi span{font-size:11px;color:var(--muted)}
.legend{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;font-size:11px;color:var(--muted);margin:6px 0 4px}
.src{display:inline-block;font-size:9.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;border-radius:99px;padding:2px 8px;white-space:nowrap;vertical-align:middle}
.src.fact{background:#E3F1E7;color:#1F6B36}.src.count{background:#E4ECF6;color:#2E5383}.src.ai{background:var(--tint);color:var(--clay2)}.src.sim{background:#EFE9F8;color:#5B3E91}
section{margin-top:26px} .pb{break-before:page;page-break-before:always}
.sec-h{display:flex;gap:12px;align-items:center;border-bottom:2px solid var(--ink);padding-bottom:8px;margin-bottom:12px;break-after:avoid}
.sec-n{font-size:22px;font-weight:800;color:var(--clay)} .sec-h h2{font-size:20px} .sec-h p{margin:2px 0 0;color:var(--muted);font-size:12px}
.card{background:#fff;border-radius:14px;padding:14px 16px;border:1px solid var(--line);margin:10px 0}
.ch-h{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px} .ch-h h3{margin-right:4px}
.note{color:var(--muted);font-size:11.5px;margin:2px 0 8px} .chart svg{display:block}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px} .grid2>.card{margin:0} .grid2.tight{gap:8px}
.avoid,.card,.rec,.fad,tr,.q{break-inside:avoid;page-break-inside:avoid}
table{width:100%;border-collapse:collapse;font-size:12px} td,th{border-bottom:1px solid var(--line);padding:7px 6px;vertical-align:top;text-align:left} th{font-size:10.5px;text-transform:uppercase;color:var(--muted);letter-spacing:.04em} td.c{text-align:center;white-space:nowrap}
.pill{display:inline-block;background:var(--cream);border:1px solid var(--line);border-radius:99px;padding:1px 8px;font-size:10.5px;margin-left:4px}
.pill.high{background:#FDE2E2;border-color:#F5B5B5}.pill.medium{background:#FDEBD8;border-color:#F3C99B}
.rel{font-size:10px;font-weight:700;border-radius:99px;padding:2px 8px;text-transform:uppercase}.rel.direct{background:var(--clay);color:#fff}.rel.indirect{background:#FEF3C7;color:#92400E}
.callout{display:flex;gap:16px;align-items:center;background:var(--tint);border-radius:14px;padding:14px 18px}
.callout .big{font-size:40px;font-weight:800;color:var(--clay2);line-height:1} .callout .big small{font-size:16px}
.q{border-top:1px solid var(--line);padding:6px 0;font-size:12px} .q.yes b{color:var(--clay2)} .q .pill{float:right}
.annot{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}.annot.solo{grid-template-columns:1fr}
.aimg{position:relative} .aimg img{width:100%;border-radius:10px;display:block}
.abox{position:absolute;border:2.5px solid;border-radius:6px;box-shadow:0 0 0 1px #fff8}
.abox i{position:absolute;top:-10px;left:-10px;width:20px;height:20px;border-radius:50%;color:#fff;font-style:normal;font-weight:800;font-size:11px;display:flex;align-items:center;justify-content:center;border:2px solid #fff}
.aitem{display:flex;gap:10px;padding:7px 0;border-bottom:1px solid var(--line);font-size:12.5px}
.apin{flex:none;width:22px;height:22px;border-radius:50%;color:#fff;font-weight:800;font-size:11px;display:flex;align-items:center;justify-content:center}
.hook-grid{display:grid;grid-template-columns:1.4fr 1fr;gap:16px} blockquote{margin:0 0 8px;font-size:18px;font-weight:700}
.score-box .ring{font-size:30px;font-weight:800;color:var(--clay2);margin-bottom:6px} .score-box .ring small{font-size:13px;color:var(--muted)}
.mrow{display:grid;grid-template-columns:100px 1fr 20px;gap:8px;align-items:center;font-size:11.5px;margin:3px 0}
.mtrack{height:8px;background:var(--cream);border-radius:99px;overflow:hidden}.mtrack i{display:block;height:100%;background:var(--clay)}
.quads{display:grid;grid-template-columns:1fr 1fr;gap:10px}.quad{background:var(--cream);border-radius:10px;padding:10px 12px}
.pos{background:var(--tint);border-radius:10px;padding:8px 12px;margin:10px 0 0}
.rec{border:1px solid var(--line);border-left:5px solid #94A3B8;border-radius:10px;padding:9px 14px;margin:8px 0}.rec.high{border-left-color:#E5484D}.rec.medium{border-left-color:#F59E0B}
.rec p{margin:4px 0 0} .rec small{font-weight:700;font-size:9.5px;letter-spacing:.06em;margin-right:4px} .rec-h{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.improved{background:var(--cream)}
.adtext{white-space:pre-wrap;background:var(--cream);border-radius:10px;padding:12px 14px;font-size:13px;line-height:1.7}.adtext mark{padding:1px 2px;border-radius:3px;color:inherit}.adtext sup{font-weight:800;margin-left:1px}
.vstrip{display:flex;gap:6px;margin:4px 0 8px}.vstrip>div{flex:1;min-width:0;text-align:center}.vstrip img{width:100%;border-radius:6px;display:block;background:#000}
.src.you{background:#EEECE4;color:var(--ink2)}
.vt .ch-h{margin-bottom:2px}.vt-lg{margin-left:auto;font-size:10.5px;color:var(--muted);display:flex;align-items:center;gap:4px}
.vt-lg i{display:inline-block;width:16px;border-top:2.5px solid var(--clay);margin-left:6px}.vt-lg i.rival{border-top:2px dashed var(--ink)}
.vt-strip{display:flex;gap:3px;margin-top:2px}.vt-strip>div{flex:1;min-width:0;text-align:center}.vt-strip img{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:4px;display:block;background:#000}.vt-strip small{font-size:8.5px}
.vt-stats{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}.vt-stats span{background:var(--cream);border-radius:8px;padding:3px 9px;font-size:11px}.vt-stats b{color:var(--clay2)}
.vt-pins{display:grid;grid-template-columns:1fr 1fr;gap:5px 12px}.vt-pin{display:flex;gap:8px;align-items:flex-start;break-inside:avoid;font-size:11.5px;line-height:1.35}
.vt-pin b{display:flex;align-items:center;gap:5px}.vt-pin .apin{width:18px;height:18px;font-size:10px}.vt-pin i,.vt-pin small{display:block}
.vt-th{position:relative;flex:none;width:44px;height:44px;border-radius:6px;overflow:hidden;background:#000}.vt-th img{width:100%;height:100%;object-fit:fill;display:block}
.vt-th .abox{border-width:2px;box-shadow:none}.vt-th.audio{display:flex;align-items:center;justify-content:center;background:var(--cream);font-size:18px}
.vt-voice{margin:6px 0 0;font-size:11px;color:var(--ink2)}.vt-voice span{margin-right:6px}.vt-voice span b{color:var(--clay2);font-weight:700} .pre{white-space:pre-wrap}
.prof-h{display:flex;gap:10px;align-items:center}.prof-h>div{flex:1}.prof-h small{display:block}
.pp{width:36px;height:36px;border-radius:50%;object-fit:cover;background:var(--tint);display:flex;align-items:center;justify-content:center;font-weight:800;color:var(--clay2);flex:none}
.kv{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:10px 0}.kv span{background:var(--cream);border-radius:8px;padding:6px;text-align:center;font-size:10px;color:var(--muted)}.kv b{display:block;font-size:15px;color:var(--ink)}
.blk{margin-top:8px} .blk p{margin:4px 0} q{display:block;border-left:3px solid var(--clay);padding:3px 8px;margin:4px 0;background:var(--cream);border-radius:0 6px 6px 0;font-size:12px}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}.chip{background:#E3F1E7;color:#1F6B36;border-radius:6px;padding:2px 8px;font-size:11px}
.thumbs{display:flex;gap:6px;margin-top:8px}.thumbs a{width:31%;text-decoration:none;color:var(--muted)}.thumbs img{width:100%;height:90px;object-fit:cover;border-radius:8px;display:block;background:var(--cream)}
.lnk,a{color:var(--clay2)} .lnk{display:inline-block;margin-top:6px;font-size:11.5px}
.flex2{display:flex;flex-wrap:wrap;gap:12px}.flex2>.card{width:calc(50% - 6px);margin:0}
.fads{display:flex;flex-wrap:wrap;gap:12px}.fads>.fad{width:calc(33.33% - 8px)}.fad{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff}
.fad img,.fad .noimg{width:100%;height:190px;object-fit:contain;background:var(--cream);display:flex;align-items:center;justify-content:center;color:var(--muted)}
.fad-b{padding:10px 12px;font-size:11.5px}.fad-b small{display:block}.fad-b p{margin:6px 0;color:var(--ink2)}.sells{font-weight:600;color:var(--clay2);margin-top:4px}
.fad-f{display:flex;justify-content:space-between;align-items:center}.fad-f .pill{margin:0}
.ideas{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.idea{background:var(--cream)}.idea .pre{margin:6px 0}
@media screen and (max-width:700px){.flex2>.card,.fads>.fad{width:100%}.grid2,.annot,.hook-grid,.quads,.fads,.ideas{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}}
@media print{body{padding:0}.wrap{max-width:none}}
"""


def build_html(profile: dict, analysis: dict, df: pd.DataFrame, figs: dict, meta: dict, review: dict | None = None,
               user_image: str | None = None, sim: dict | None = None, user_frames: list[dict] | None = None,
               video_meta: dict | None = None) -> str:
    charts = figs or {}
    comps = _relevant(analysis["competitors"])
    direct = sum(1 for c in comps if c.get("relevance") == "direct")

    # Embed competitor pictures (profile + ad thumbnails) so they always show up in the PDF.
    urls = [c.get("profile_pic") for c in comps] + [a.get("image") for c in comps for a in (c.get("ads") or [])[:3]]
    emb = dict(zip(urls, embed_many(urls)))
    comps = [{**c, "profile_pic": emb.get(c.get("profile_pic")),
              "ads": [{**a, "image": emb.get(a.get("image")) or ""} for a in (c.get("ads") or [])[:3]]} for c in comps]

    mine = next((r for r in (sim or {}).get("reactions", []) if r.get("ad_id") == "you"), None)
    kpis = [(len(df), "active ads scanned"), (df["page_name"].nunique() if not df.empty else 0, "advertisers found"),
            (len(comps), "relevant competitors"), (direct, "direct competitors")]
    kpis.append((f"{mine['stopped']}/30", "buyers stopped on your ad") if mine else (e(profile.get("category") or "–"), "category"))
    kpi_html = "".join(f"<div class='kpi'><b>{v}</b><span>{lab}</span></div>" for v, lab in kpis)

    fb = analysis.get("user_ad_feedback") or {}
    recs = "".join(f"<div class='rec {e(r.get('priority', 'medium'))}'><div class='rec-h'><b>{e(r.get('title', ''))}</b>"
                   f"<span class='pill {e(r.get('priority', ''))}'>{e(r.get('priority', ''))}</span></div><p>{e(r.get('detail', ''))}</p></div>"
                   for r in analysis.get("recommendations", []))
    ideas = "".join(f"<div class='card idea avoid'><b>{e(i.get('hook', ''))}</b><p class='pre'>{e(i.get('body', ''))}</p>"
                    f"<span class='pill'>{e(i.get('cta', ''))}</span></div>" for i in analysis.get("ad_copy_ideas", []))

    your_input = f"""<div class="card avoid"><div class="ch-h"><h3>What we read from your ad</h3>{tag('ai')}</div>
<p><b>{e(profile.get('product') or '')}</b>{(' by ' + e(profile['brand_name'])) if profile.get('brand_name') else ''} ·
<small>{e(profile.get('category') or '')}</small></p><p>{e(profile.get('creative_summary') or '')}</p>
<p><b>USP:</b> {e(profile.get('usp') or '–')}<br><b>Audience:</b> {e(profile.get('target_audience') or '–')}
{('<br><b>Offer:</b> ' + e(profile['offer'])) if profile.get('offer') else ''}</p>
<div class="grid2 tight"><div><b>Strengths vs market</b><ul>{_li(fb.get('strengths'))}</ul></div>
<div><b>Weaknesses vs market</b><ul>{_li(fb.get('weaknesses'))}</ul></div></div></div>"""

    market = (chart_card("Messaging themes across the market", charts.get("themes", ""), "count",
                           "% of relevant competitors whose real ad copy uses each theme (counted, not guessed).")
              + chart_card("Ad formats used", charts.get("formats", ""), "fact", "DPA = catalogue ads · DCO = dynamic creative.")
              + chart_card("Placements", charts.get("platforms", ""), "fact", "Number of ads running on each placement.")
              + chart_card("Call-to-action buttons", charts.get("ctas", ""), "fact")
              + chart_card("When competitors launched their currently active ads", charts.get("timeline", ""), "fact",
                           "Each dot is one live ad. Many recent dots = actively testing new creatives.")
              + chart_card("Creative scorecard: you vs competitors (1-10)", charts.get("scorecard", ""), "ai",
                           "AI rating of the ad copy on each dimension, for direction only."))

    playbook = (f"<div class='card'><div class='ch-h'><h3>Gaps you can own</h3>{tag('ai')}</div><ul>{_li(analysis.get('gaps_opportunities'))}</ul></div>"
                + f"<div class='ch-h' style='margin-top:14px'><h3>Recommendations</h3>{tag('ai')}</div>{recs}"
                + (f"<div class='ch-h' style='margin-top:14px'><h3>Ad copy ideas</h3>{tag('ai')}</div><div class='ideas'>{ideas}</div>" if ideas else "")
                + (f"<div class='card'><b>Keywords to keep monitoring:</b> {e(', '.join(analysis.get('suggested_keywords_to_monitor') or []))}</div>"
                   if analysis.get("suggested_keywords_to_monitor") else ""))

    secs, n = [], 0

    def add(title, sub, body, new_page=False):
        nonlocal n
        if body and body.strip():
            n += 1
            secs.append(section(n, title, sub, body, new_page))

    add("Executive summary", "The competitive picture in one paragraph",
        f"<div class='card'><div class='ch-h'>{tag('ai')}</div><p style='margin:0;font-size:13.5px'>{e(analysis.get('executive_summary', ''))}</p></div>" + your_input)
    add("Scroll test", "Your ad in a feed next to real competitor ads, shown to 30 simulated buyers", scroll_test_html(sim), True)
    add("Your ad, reviewed", "Hook, differentiation and concrete fixes", review_html(review, user_image, next((a for a in (sim or {}).get("feed", []) if a.get("is_user")), None), user_frames, sim, video_meta), True)
    add("Competitor landscape", "Who is advertising against you right now", competitors_html(comps, charts) if comps else "", True)
    add("Competitor profiles", "What each rival says, in their own words", profiles_html(comps) if comps else "", True)
    add("Rival ads used in the test", "Real ads from the Ads Library, as published", feed_ads_html(sim), True)
    add("Market patterns", "How the relevant competitors advertise", market, True)
    add("Playbook", "What to do next", playbook, True)
    add("Methodology & data sources", "How every number in this report was produced",
        methodology_html(meta, analysis, df, len(comps), bool(sim)), True)

    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Competitor Ad Report</title><style>{CSS}</style></head><body><div class="wrap">
<div class="cover"><div class="eyebrow">Competitor Ad Intelligence Report</div>
<h1>{e(profile.get('brand_name') or profile.get('product') or 'Your ad')} vs the market</h1>
<p>{e(profile.get('product') or '')}{(' · ' + e(profile.get('category'))) if profile.get('category') else ''}</p>
<div class="meta">Facebook Ads Library · country {e(meta.get('country', 'IN'))} · keywords: {e(', '.join(meta.get('keywords', [])))} ·
generated {datetime.now():%d %b %Y %H:%M}</div></div>
<div class="kpis">{kpi_html}</div>
<div class="legend"><b>Labels:</b> {tag('fact')} copied from the public Ads Library {tag('count')} computed from that data
{tag('ai')} OpenAI's reading of the real ads {tag('sim') if sim else ''}{' simulated buyers, an estimate' if sim else ''}</div>
{''.join(secs)}
</div></body></html>"""
