"""Deterministic, evidence-based facts pulled straight from real ad copy (no LLM)."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

OFFER_RE = re.compile(
    r"[^.!?\n]*(?:₹\s?\d[\d,]*|rs\.?\s?\d[\d,]*|\d{1,3}\s?%\s?(?:off|discount|cashback)?|flat\s+\d+|\bfree\b|"
    r"\bdiscount\b|\bcashback\b|\bcoupon\b|\bpromo\s?code\b|\buse\s+code\b|\bbuy\s?\d\s?get\s?\d\b|\bbogo\b|"
    r"\bemi\b|\brefund\b|\bmoney[- ]back\b|\blimited\s+(?:time|offer|seats|period)\b|\bsale\b)[^.!?\n]*",
    re.I,
)


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()  # "𝐃𝐚𝐭𝐚" (styled Unicode in ads) -> "data"
    text = re.sub(r"[^\w\s₹%]", " ", text)  # drop punctuation & emoji
    return re.sub(r"\s+", " ", text).strip()


def first_line(body: str, limit: int = 120) -> str:
    """The hook = first non-empty line / sentence of the ad, verbatim."""
    for line in (body or "").splitlines():
        line = line.strip()
        if len(norm(line)) >= 4:
            m = re.match(r"(.+?[.!?])(\s|$)", line)
            hook = m.group(1) if m and len(m.group(1)) >= 12 else line
            return hook[:limit].rstrip() + ("…" if len(hook) > limit else "")
    return ""


def real_hooks(bodies: list[str], titles: list[str], n: int = 3) -> list[str]:
    seen, out = set(), []
    for t in [first_line(b) for b in bodies] + [t for t in titles if t]:
        k = norm(t)
        if k and k not in seen and "{{" not in t:
            seen.add(k)
            out.append(t)
        if len(out) >= n:
            break
    return out


def real_offers(texts: list[str], n: int = 3) -> list[str]:
    seen, out = set(), []
    for text in texts:
        for m in OFFER_RE.finditer(text or ""):
            snip = re.sub(r"\s+", " ", m.group(0)).strip(" -•*|")
            if not 6 <= len(snip) <= 140:
                snip = snip[:140].rstrip() + "…" if len(snip) > 140 else ""
            k = norm(snip)
            if k and k not in seen:
                seen.add(k)
                out.append(snip)
            if len(out) >= n:
                return out
    return out


def is_verbatim(quote: str, texts: list[str], threshold: float = 0.85) -> bool:
    """True if `quote` really appears in one of `texts` (tolerant of punctuation, emoji and small typos)."""
    q = norm(quote).replace("…", "")
    if len(q) < 4:
        return False
    for t in texts:
        t = norm(t)
        if not t:
            continue
        if q in t:
            return True
        m = SequenceMatcher(None, q, t, autojunk=False).find_longest_match(0, len(q), 0, len(t))
        if m.size >= threshold * len(q):
            return True
    return False


def threat_score(relevance: str, active_ads: int, max_days: int | None, likes: int | None,
                 max_ads: int, max_days_all: int, max_likes: int) -> float:
    """Explainable 0-10 score: relevance 40%, ad volume 25%, longest-running ad 20%, page size 15%."""
    rel = {"direct": 1.0, "indirect": 0.5}.get(relevance, 0.0)
    ads = active_ads / max_ads if max_ads else 0
    days = (max_days or 0) / max_days_all if max_days_all else 0
    size = (likes or 0) ** 0.5 / max_likes ** 0.5 if max_likes else 0
    return round(10 * (0.4 * rel + 0.25 * ads + 0.2 * days + 0.15 * size), 1)
