"""Static inline-SVG charts for the HTML/PDF report.

No JavaScript and no CDN, so the charts render identically on screen, offline and in the PDF, and are sized for an
A4 page (labels are truncated with the full text kept as a hover title, never clipped)."""
from __future__ import annotations

import math
from datetime import datetime
from html import escape

INK, CLAY, CLAY_SOFT, MUTED, GRID, TEXT2 = "#141413", "#D97757", "#EFC3B1", "#B9B6AA", "#ECEAE2", "#5E5D59"
SERIES = [CLAY, INK, "#9C9A92", "#5B7FA6", "#C15F3C", "#3BA55C", "#E8A58C", "#73726C"]
W = 680


def _trunc(s: str, n: int) -> str:
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _fmt(v, unit=""):
    if v is None:
        return "–"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:.1f}{unit}"
    return f"{int(v)}{unit}"


def _wrap(body: str, h: int, width: int = W) -> str:
    return (f'<svg class="svgc" viewBox="0 0 {width} {h}" width="100%" preserveAspectRatio="xMinYMin meet" '
            f'role="img" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Inter, Arial, sans-serif">{body}</svg>')


def hbar(rows: list[dict], vmax: float | None = None, unit: str = "", label_w: int = 210, row_h: int = 26,
         color: str = INK, hi_color: str = CLAY) -> str:
    """rows: [{"label", "value", "hi": bool, "color": optional, "note": optional right-side note}]"""
    if not rows:
        return ""
    if not vmax:
        top = max((r["value"] or 0) for r in rows) or 1
        # whole-number axis for counts: round the scale up to a multiple of 4 ticks
        vmax = math.ceil(top / 4) * 4 if all(float(r["value"] or 0).is_integer() for r in rows) else top
    x0, x1 = label_w + 8, W - 70
    h = row_h * len(rows) + 22
    out = []
    for t in range(5):  # light vertical grid
        gx = x0 + (x1 - x0) * t / 4
        out.append(f'<line x1="{gx:.1f}" y1="4" x2="{gx:.1f}" y2="{h - 18}" stroke="{GRID}"/>'
                   f'<text x="{gx:.1f}" y="{h - 4}" font-size="10" fill="{TEXT2}" text-anchor="middle">{_fmt(float(vmax * t / 4), unit)}</text>')
    for i, r in enumerate(rows):
        y = 6 + i * row_h
        v = r["value"] or 0
        bw = max(2.0, (x1 - x0) * v / vmax) if v else 0
        col = r.get("color") or (hi_color if r.get("hi") else color)
        lab = escape(_trunc(r["label"], int(label_w / 6.4)))
        weight = "700" if r.get("hi") else "400"
        out.append(f'<g><title>{escape(str(r["label"]))}: {_fmt(v, unit)}</title>'
                   f'<text x="{label_w}" y="{y + row_h / 2 + 2:.1f}" font-size="11.5" font-weight="{weight}" fill="{INK}" text-anchor="end">{lab}</text>'
                   f'<rect x="{x0}" y="{y + 4}" width="{bw:.1f}" height="{row_h - 10}" rx="4" fill="{col}"/>'
                   f'<text x="{x0 + bw + 6:.1f}" y="{y + row_h / 2 + 2:.1f}" font-size="11" font-weight="600" fill="{INK}">{_fmt(v, unit)}'
                   f'{(" · " + escape(r["note"])) if r.get("note") else ""}</text></g>')
    return _wrap("".join(out), h)


def donut(items: list[dict], size: int = 200) -> str:
    """items: [{"label", "value"}] -> donut with a legend showing count and share."""
    items = [i for i in items if i["value"]]
    total = sum(i["value"] for i in items)
    if not total:
        return ""
    cx = cy = size / 2
    r, rin = size / 2 - 6, size / 2 - 46
    out, a0 = [], -math.pi / 2
    for k, it in enumerate(items):
        frac = it["value"] / total
        a1 = a0 + 2 * math.pi * frac
        col = SERIES[k % len(SERIES)]
        if frac >= 0.9999:
            out.append(f'<circle cx="{cx}" cy="{cy}" r="{(r + rin) / 2}" fill="none" stroke="{col}" stroke-width="{r - rin}"/>')
        else:
            large = 1 if a1 - a0 > math.pi else 0
            p = lambda rad, a: (cx + rad * math.cos(a), cy + rad * math.sin(a))
            (ax, ay), (bx, by), (cx2, cy2), (dx, dy) = p(r, a0), p(r, a1), p(rin, a1), p(rin, a0)
            out.append(f'<path d="M{ax:.1f},{ay:.1f} A{r},{r} 0 {large} 1 {bx:.1f},{by:.1f} L{cx2:.1f},{cy2:.1f} '
                       f'A{rin},{rin} 0 {large} 0 {dx:.1f},{dy:.1f} Z" fill="{col}" stroke="#fff" stroke-width="2">'
                       f'<title>{escape(it["label"])}: {it["value"]}</title></path>')
        a0 = a1
    out.append(f'<text x="{cx}" y="{cy - 2}" font-size="22" font-weight="700" text-anchor="middle" fill="{INK}">{total}</text>'
               f'<text x="{cx}" y="{cy + 15}" font-size="10" text-anchor="middle" fill="{TEXT2}">ads</text>')
    lx = size + 30
    for k, it in enumerate(items):
        y = 24 + k * 24
        out.append(f'<rect x="{lx}" y="{y - 10}" width="12" height="12" rx="3" fill="{SERIES[k % len(SERIES)]}"/>'
                   f'<text x="{lx + 20}" y="{y}" font-size="12" fill="{INK}">{escape(_trunc(it["label"], 34))}</text>'
                   f'<text x="{W - 10}" y="{y}" font-size="12" font-weight="600" text-anchor="end" fill="{INK}">'
                   f'{it["value"]} · {round(100 * it["value"] / total)}%</text>')
    return _wrap("".join(out), max(size, 24 * len(items) + 16))


def grouped_hbar(dims: list[str], series: list[tuple[str, list, str]], vmax: float = 10, label_w: int = 150) -> str:
    """Several series per dimension (e.g. you / competitor avg / best) as thin side-by-side bars + legend."""
    series = [s for s in series if s[1]]
    if not dims or not series:
        return ""
    n = len(series)
    bar_h, gap = 9, 12
    grp = n * (bar_h + 2) + gap
    x0, x1 = label_w + 8, W - 40
    out = []
    lx = x0
    for name, _, col in series:  # legend
        out.append(f'<rect x="{lx}" y="2" width="12" height="12" rx="3" fill="{col}"/>'
                   f'<text x="{lx + 18}" y="12" font-size="11.5" fill="{INK}">{escape(_trunc(name, 30))}</text>')
        lx += 30 + 7 * min(30, len(name))
    top = 26
    for i, d in enumerate(dims):
        y = top + i * grp
        out.append(f'<text x="{label_w}" y="{y + grp / 2 - 3:.1f}" font-size="11.5" fill="{INK}" text-anchor="end">{escape(_trunc(d, 24))}</text>')
        for k, (name, vals, col) in enumerate(series):
            v = vals[i] if i < len(vals) and isinstance(vals[i], (int, float)) else 0
            by = y + k * (bar_h + 2)
            out.append(f'<rect x="{x0}" y="{by}" width="{max(2, (x1 - x0) * v / vmax):.1f}" height="{bar_h}" rx="3" fill="{col}">'
                       f'<title>{escape(name)} · {escape(d)}: {v}</title></rect>'
                       f'<text x="{x0 + (x1 - x0) * v / vmax + 5:.1f}" y="{by + bar_h - 1}" font-size="9.5" fill="{TEXT2}">{_fmt(v)}</text>')
    return _wrap("".join(out), top + grp * len(dims))


def timeline(rows: list[tuple[str, list[float]]], label_w: int = 190, row_h: int = 26) -> str:
    """rows: [(advertiser, [start timestamps])] -> dot plot of when each currently active ad was launched."""
    rows = [(n, [t for t in ts if t]) for n, ts in rows]
    rows = [r for r in rows if r[1]]
    if not rows:
        return ""
    lo = min(min(ts) for _, ts in rows)
    hi = max(max(ts) for _, ts in rows + [("now", [datetime.now().timestamp()])])
    span = max(hi - lo, 86400 * 7)
    x0, x1 = label_w + 14, W - 16
    h = row_h * len(rows) + 30
    X = lambda t: x0 + (x1 - x0) * (t - lo) / span
    out = []
    # month ticks
    d = datetime.fromtimestamp(lo).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ticks = []
    while d.timestamp() <= hi:
        if d.timestamp() >= lo:
            ticks.append(d)
        d = d.replace(year=d.year + (d.month == 12), month=d.month % 12 + 1)
    step = max(1, math.ceil(len(ticks) / 8))
    for t in ticks[::step]:
        x = X(t.timestamp())
        out.append(f'<line x1="{x:.1f}" y1="2" x2="{x:.1f}" y2="{h - 22}" stroke="{GRID}"/>'
                   f'<text x="{x:.1f}" y="{h - 8}" font-size="10" fill="{TEXT2}" text-anchor="middle">{t:%b %y}</text>')
    for i, (name, ts) in enumerate(rows):
        y = 4 + i * row_h + row_h / 2
        out.append(f'<text x="{label_w}" y="{y + 4:.1f}" font-size="11.5" fill="{INK}" text-anchor="end">'
                   f'<title>{escape(name)}</title>{escape(_trunc(name, int(label_w / 6.4)))}</text>'
                   f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{GRID}" stroke-dasharray="2 3"/>')
        for t in ts:
            out.append(f'<circle cx="{X(t):.1f}" cy="{y:.1f}" r="5.5" fill="{SERIES[i % len(SERIES)]}" fill-opacity=".7" '
                       f'stroke="#fff"><title>{escape(name)}: launched {datetime.fromtimestamp(t):%d %b %Y}</title></circle>')
    return _wrap("".join(out), h)
