# web/services/generation.py
import re
from typing import List, Dict, Tuple

BANNED_PHRASES = {
    "unbelievable","shocking","insane","secret hacks","groundbreaking",
    "must-see","click here","you won’t believe","crazy","exposed"
}

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())

def _limit(text: str, n: int) -> str:
    t = _clean(text)
    return t if len(t) <= n else t[:n-1].rstrip() + "…"

def _filter_clickbait(text: str) -> str:
    t = text
    for p in BANNED_PHRASES:
        t = re.sub(re.escape(p), "", t, flags=re.IGNORECASE)
    return _clean(t)

def suggest_titles(keyword: str, entities: List[str]) -> List[str]:
    """Return up to 5 safe, concise title candidates (≤70 chars)."""
    k = _clean(keyword)
    ents = [e for e in entities if len(e) >= 3][:5]
    patterns = [
        f"{k}: " + (" ".join(ents[:2]) if ents else "Complete Guide"),
        f"{k} — " + (" & ".join(ents[:2]) if ents else "What You Need to Know"),
        f"How to {k} " + (f"({ents[0]})" if ents else ""),
        f"{k} Explained " + (f"in {ents[0].title()}" if ents else ""),
        f"{k}: Tips, Mistakes, Best Practices",
    ]
    out = []
    for p in patterns:
        t = _filter_clickbait(_limit(p, 70))
        if t and t not in out:
            out.append(t)
    return out[:5]

def suggest_description(keyword: str, entities: List[str]) -> str:
    """150–1500 chars target; we’ll generate a compact outline paragraph."""
    k = _clean(keyword)
    lines = [
        f"{k} — In this video, we cover the key points and common pitfalls so you can act with confidence.",
        ("We’ll touch on: " + ", ".join(entities[:6])) if entities else "",
        "Timestamps: 00:00 Intro · 00:30 Basics · 02:00 Examples · 04:00 Tips · 05:30 Wrap-up.",
        "If this helped, consider subscribing and leaving a comment with your questions.",
        "Resources and credits are in the description below."
    ]
    desc = _filter_clickbait(_clean(". ".join([l for l in lines if l])))
    return _limit(desc, 1200)  # safe middle of our 150–1500 band

def suggest_tags(keyword: str, entities: List[str]) -> List[str]:
    base = [keyword]
    base += [e for e in entities[:12]]
    # light variations
    variants = []
    for e in entities[:6]:
        variants += [f"{keyword} {e}", f"{e} {keyword}"]
    # dedupe and trim
    seen, tags = set(), []
    for t in base + variants:
        tt = _clean(t)
        if tt and tt.lower() not in seen:
            seen.add(tt.lower()); tags.append(tt)
        if len(tags) >= 20:
            break
    return tags  # aim 10–20 as our Optimize score expects

def hashtags_from_tags(tags: List[str], keyword: str) -> List[str]:
    raw = [f"#{re.sub(r'\\s+', '', keyword)}"] + [f"#{re.sub(r'\\s+', '', t)}" for t in tags]
    seen, out = set(), []
    for h in raw:
        h = h[:30]  # avoid super long hashtags
        if len(h) >= 3 and h.lower() not in seen:
            seen.add(h.lower()); out.append(h)
        if len(out) == 15:
            break
    return out

def score_metadata(title: str, description: str, tags: List[str], hashtags: List[str]) -> Tuple[int, Dict[str,int], List[str]]:
    fixes = []
    total = 0
    breakdown = {}

    # Title ≤70 & non-empty (max 25)
    tl = len(title or "")
    s_title_len = 25 if 1 <= tl <= 70 else (0 if tl == 0 else max(8, 25 - int((tl-70)/10)))
    if tl == 0:
        fixes.append("Add a title (≤ 70 chars).")
    elif tl > 70:
        fixes.append(f"Trim title to ≤ 70 (current {tl}).")
    breakdown["Title length"] = s_title_len; total += s_title_len

    # Description 150–1500 (max 25)
    dl = len(description or "")
    if 150 <= dl <= 1500:
        s_desc = 25
    elif dl == 0:
        s_desc = 0; fixes.append("Add a description (150–1500 chars).")
    else:
        delta = (150 - dl) if dl < 150 else (dl - 1500)
        s_desc = max(5, 25 - int(delta/100))
    breakdown["Description length"] = s_desc; total += s_desc

    # Tags count 10–20 (max 20)
    tc = len(tags or [])
    s_tags = 20 if 10 <= tc <= 20 else (0 if tc == 0 else min(18, int(tc*1.2)))
    if tc == 0:
        fixes.append("Add tags (aim for 10–20).")
    breakdown["Tags count"] = s_tags; total += s_tags

    # Hashtags ≤15 (max 10)
    hc = len(hashtags or [])
    s_hash = 10 if 1 <= hc <= 15 else (0 if hc == 0 else 6)
    if hc == 0:
        fixes.append("Add a few hashtags (≤ 15).")
    breakdown["Hashtags count"] = s_hash; total += s_hash

    # Clickbait check (max 20)
    clickbait_hit = any(p.lower() in (title or "").lower() for p in BANNED_PHRASES)
    s_cb = 0 if clickbait_hit else 20
    if clickbait_hit:
        fixes.append("Remove clickbait terms (policy-safe titles perform better long-term).")
    breakdown["No clickbait"] = s_cb; total += s_cb

    total = max(0, min(100, total))
    return total, breakdown, fixes


from django.conf import settings
from google import genai


# Create a singleton client using the API key from settings
client = genai.Client(api_key=settings.GOOGLE_API_KEY)


def generate_content(prompt: str) -> str:
    """
    Call Gemini (via Google Gen AI SDK) to generate content.
    Falls back to a clear message if the key is missing or an error happens.
    """
    if not settings.GOOGLE_API_KEY:
        return "⚠️ AI is not configured. Set GOOGLE_API_KEY in your .env file."

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",  # fast + cheap model
            contents=prompt,
        )
        # response.text is the plain text output
        return response.text or "(No text returned by the AI.)"
    except Exception as e:
        # Fail gracefully, don’t crash the site
        return f"⚠️ AI error: {e}"


