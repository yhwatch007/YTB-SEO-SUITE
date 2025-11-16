# web/views.py
import re
import math
import json
from collections import Counter

from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator

from .services.youtube import search_videos, YouTubeError
from .models import Optimization
from .services.generation import generate_content  # Gemini wrapper


def home(request):
    return render(request, "home.html")


# ===================== DISCOVER =====================

def discover(request):
    q = request.GET.get("q", "").strip()

    # basic bar
    n = int(request.GET.get("n", "10") or 10)
    n_options = [5, 10, 15, 20]

    # advanced
    sort = request.GET.get("sort", "ranking")  # likes, comments, views, ranking, published
    text_filter = request.GET.get("filter", "").strip().lower()
    min_len_min = request.GET.get("min_len_min", "").strip()
    max_len_min = request.GET.get("max_len_min", "").strip()
    min_len_sec = int(min_len_min) * 60 if min_len_min.isdigit() else None
    max_len_sec = int(max_len_min) * 60 if max_len_min.isdigit() else None

    sort_options = [
        ("likes", "Likes"),
        ("comments", "Comments"),
        ("views", "Views"),
        ("ranking", "Ranking"),
        ("published", "Published"),
    ]

    region = getattr(settings, "YOUTUBE_DEFAULT_REGION", "US")
    results, error = [], None

    # aggregated stats defaults
    avg_likes = avg_views = avg_comments = avg_ratio = None
    sentiment_emoji, sentiment_text = "😶", "No data yet"
    difficulty1 = difficulty5 = 0

    ai_insight = None  # 👈 AI summary for Discover

    if q:
        try:
            data = search_videos(q, max_results=n, region=region)

            # filter + ratio
            processed = []
            for v in data:
                if min_len_sec is not None and v["duration_sec"] < min_len_sec:
                    continue
                if max_len_sec is not None and v["duration_sec"] > max_len_sec:
                    continue
                if text_filter:
                    blob = (v["title"] + " " + (v.get("description") or "")).lower()
                    if text_filter not in blob:
                        continue
                v["ratio"] = (v["likes"] / v["views"]) if v["views"] > 0 else None
                processed.append(v)

            # sorting
            if sort == "likes":
                processed.sort(key=lambda x: x["likes"], reverse=True)
            elif sort == "comments":
                processed.sort(key=lambda x: x["comments"], reverse=True)
            elif sort == "views":
                processed.sort(key=lambda x: x["views"], reverse=True)
            elif sort == "published":
                processed.sort(key=lambda x: x["published"], reverse=True)
            # else 'ranking' = API order

            results = processed

            # aggregates (sidebar)
            if results:
                nres = len(results)
                avg_likes = sum(v["likes"] for v in results) / nres
                avg_views = sum(v["views"] for v in results) / nres
                avg_comments = sum(v["comments"] for v in results) / nres
                ratios = [v["ratio"] for v in results if v["ratio"] is not None]
                avg_ratio = (sum(ratios) / len(ratios)) if ratios else None

                if avg_ratio is None or avg_ratio < 0.01:
                    sentiment_emoji, sentiment_text = "😞", "People don't seem to like these videos"
                elif avg_ratio < 0.04:
                    sentiment_emoji, sentiment_text = "😐", "Audience sentiment looks average"
                else:
                    sentiment_emoji, sentiment_text = "😊", "Audience seems to like these videos"

                top_sorted = sorted(results, key=lambda x: x["views"], reverse=True)
                top1 = top_sorted[0]["views"] if top_sorted else 0
                top5 = top_sorted[4]["views"] if len(top_sorted) >= 5 else (
                    top_sorted[-1]["views"] if top_sorted else 0
                )

                def score(v):
                    return min(100, int(math.log10(v + 1) * 20))

                difficulty1, difficulty5 = score(top1), score(top5)

                # ---- AI insight for Discover ----
                sample = [
                    {
                        "title": v["title"],
                        "views": v["views"],
                        "likes": v["likes"],
                        "comments": v["comments"],
                        "duration_sec": v["duration_sec"],
                    }
                    for v in results[:8]
                ]
                prompt = f"""
You are a senior YouTube SEO strategist.

Analyze this search results snapshot for keyword: "{q}"

DATA (JSON list):
{json.dumps(sample, indent=2)}

In 5 bullet points, answer:
- How competitive is this keyword (low/medium/high) and why?
- What style of videos are winning (tutorials, shorts, reviews, etc.)?
- What angle would you recommend for a new video to stand out?
- Suggested ideal video length.
- Any quick-win ideas for title hooks.

Answer concisely in markdown bullet points only.
"""
                ai_insight = generate_content(prompt)

        except YouTubeError as e:
            error = str(e)
        except Exception as e:
            error = f"Unexpected error: {e}"

    return render(request, "discover.html", {
        "q": q,
        "n": n,
        "n_options": n_options,
        "results": results,
        "error": error,
        "sort": sort,
        "sort_options": sort_options,
        "text_filter": request.GET.get("filter", ""),
        "min_len_min": min_len_min,
        "max_len_min": max_len_min,
        "avg": {
            "likes": avg_likes,
            "views": avg_views,
            "comments": avg_comments,
            "ratio": avg_ratio,
        },
        "sentiment": {
            "emoji": sentiment_emoji,
            "text": sentiment_text,
        },
        "difficulty": {
            "top1": difficulty1,
            "top5": difficulty5,
        },
        "ai_insight": ai_insight,
    })


# ===================== OPTIMIZE HELPERS =====================

STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "without", "in", "on", "of", "to", "from", "by", "at", "is", "are",
    "be", "this", "that", "those", "these", "it", "its", "as", "you", "your", "yours", "ours", "we", "us", "our",
    "how", "what", "why", "when", "where", "who", "will", "can", "could", "should", "would", "i", "me", "my",
    "vs", "vs.", "&", "-", "_", "best", "new", "top", "2023", "2024", "2025"
}

# ---- New: advanced optimization scoring based on YT ranking blueprint ----

POWER_WORDS = {
    "secret", "secrets", "mistake", "mistakes", "hidden", "insane", "crazy",
    "shocking", "simple", "easy", "ultimate", "pro", "advanced", "powerful",
    "killer", "dangerous", "hack", "hacks", "fix", "fixes", "broken"
}

CURIOSITY_PHRASES = [
    "no one tells you",
    "nobody tells you",
    "what no one",
    "what nobody",
    "the truth about",
    "you won't believe",
    "stop doing this",
    "before you",
    "no one is talking about",
]

LOSS_AVERSION_WORDS = {
    "stop", "avoid", "never", "lose", "losing", "wasting", "ruin", "kill"
}


def _count_occurrences(text: str, words: set[str]) -> int:
    if not text:
        return 0
    tokens = re.findall(r"[A-Za-z0-9']+", text.lower())
    return sum(1 for t in tokens if t in words)


def _has_any_phrase(text: str, phrases: list[str]) -> bool:
    if not text:
        return False
    tl = text.lower()
    return any(p in tl for p in phrases)


def _has_chapters(description: str) -> bool:
    """Rough check for timestamps like 0:00, 12:34, 1:02:45."""
    if not description:
        return False
    return bool(re.search(r"\b\d{1,2}:\d{2}(:\d{2})?\b", description))


def _word_count(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _env_stats_from_serp(serp):
    """Compute environment difficulty stats from SERP (views, likes, comments)."""
    if not serp:
        return {
            "median_views": 0,
            "median_likes_per_1k": 0.0,
            "median_comments_per_1k": 0.0,
        }
    views_list = [v["views"] for v in serp if v.get("views") is not None]
    if not views_list:
        views_list = [0]
    views_sorted = sorted(views_list)
    mid = len(views_sorted) // 2
    if len(views_sorted) % 2 == 0:
        median_views = (views_sorted[mid - 1] + views_sorted[mid]) / 2
    else:
        median_views = views_sorted[mid]

    likes_per_1k = []
    comments_per_1k = []
    for v in serp:
        vw = max(v.get("views") or 0, 1)
        likes = v.get("likes") or 0
        comments = v.get("comments") or 0
        likes_per_1k.append(likes * 1000 / vw)
        comments_per_1k.append(comments * 1000 / vw)
    likes_per_1k.sort()
    comments_per_1k.sort()
    mid_l = len(likes_per_1k) // 2
    mid_c = len(comments_per_1k) // 2
    med_likes_1k = likes_per_1k[mid_l] if likes_per_1k else 0.0
    med_comments_1k = comments_per_1k[mid_c] if comments_per_1k else 0.0

    return {
        "median_views": int(median_views),
        "median_likes_per_1k": med_likes_1k,
        "median_comments_per_1k": med_comments_1k,
    }

def score_holistic_package(
    main_keyword: str,
    title: str,
    description: str,
    tags_list: list[str],
    entities: list[str],
    serp,
    has_custom_thumbnail: bool,
    in_playlists: bool,
):
    """
    Returns (overall_score, pillars:dict, fixes:list)

    Pillars (0–100 scaled):
      - Search Relevance (max 30)
      - Click-Through Potential (max 25)
      - Retention Potential (max 25)
      - Environment & Session Setup (max 20)
    """
    fixes: list[str] = []
    pillars: dict[str, dict] = {}

    kw = (main_keyword or "").strip().lower()
    t = (title or "").strip()
    d = (description or "").strip()
    tags_clean = [t.strip().lower() for t in tags_list if t and t.strip()]
    ents = entities or []

    title_lc = t.lower()
    desc_lc = d.lower()

    # ---------- Pillar 1: Search Relevance (0–30) ----------
    p1_score = 0
    p1_max = 30
    p1_details = []

    # Keyword in title & early
    if kw:
        if kw in title_lc:
            p1_score += 8
            p1_details.append("Main keyword present in title.")
            idx = title_lc.find(kw)
            if idx <= 15:
                p1_score += 4
                p1_details.append("Keyword appears early in the title.")
        else:
            p1_details.append("Keyword is missing from title.")
            fixes.append("Include the main keyword in the title.")

        # keyword "above the fold" in description (first ~80 chars)
        if kw in desc_lc[:80]:
            p1_score += 6
            p1_details.append("Keyword appears early in the description.")
        elif kw in desc_lc:
            p1_score += 3
            p1_details.append("Keyword appears in the description (not early).")
        else:
            fixes.append("Mention the main keyword near the start of the description.")

    # Description length – aim for at least ~250 words (Search best practice)
    desc_words = _word_count(d)
    if desc_words == 0:
        p1_details.append("No description text.")
        fixes.append("Add a descriptive, keyword-rich description (min 150–250 words).")
    elif desc_words < 120:
        p1_score += 4
        p1_details.append("Short description – add more context and variations of your keyword.")
        fixes.append("Expand the description to better explain the content and include related phrases.")
    elif 120 <= desc_words <= 350:
        p1_score += 8
        p1_details.append("Solid description length for Search.")
    elif desc_words > 350:
        p1_score += 6
        p1_details.append("Very detailed description – good for Search, ensure it remains readable.")

    # Entities & semantic coverage
    ent_matches = 0
    for e in ents:
        if e.lower() in title_lc or e.lower() in desc_lc:
            ent_matches += 1
    if ent_matches:
        bonus = min(8, ent_matches * 2)
        p1_score += bonus
        p1_details.append(f"Includes {ent_matches} important topic entities from top results.")
    else:
        p1_details.append("Does not clearly reflect SERP entities in title/description.")
        fixes.append("Include 2–4 of the important terms your competitors use (entities).")

    # Tags: tiny weight
    if tags_clean:
        if kw and any(kw in t for t in tags_clean):
            p1_score += 2
            p1_details.append("Keyword appears in tags (ok but low-importance).")
        elif len(tags_clean) >= 5:
            p1_score += 1
            p1_details.append("Tags present (low-importance).")

    p1_score = min(p1_max, max(0, p1_score))
    p1_pct = int(p1_score / p1_max * 100) if p1_max else 0
    pillars["Search Relevance"] = {
        "score": p1_score,
        "max": p1_max,
        "pct": p1_pct,
        "details": p1_details,
    }

    # ---------- Pillar 2: Click-Through Potential (0–25) ----------
    p2_score = 0
    p2_max = 25
    p2_details = []

    tlen = len(t)
    if tlen == 0:
        p2_details.append("No title – cannot generate clicks.")
        fixes.append("Add a compelling title (≤ 70 characters).")
    elif tlen <= 70:
        p2_score += 6
        p2_details.append("Title length is within the recommended range.")
    else:
        p2_score += 3
        p2_details.append("Title is quite long; may get truncated on mobile.")
        fixes.append("Shorten the title so the key hook fits in the first ~60–70 characters.")

    # Power words & emotion
    pw_count = _count_occurrences(t, POWER_WORDS)
    if pw_count >= 2:
        p2_score += 5
        p2_details.append("Title uses strong emotional/power words to stand out.")
    elif pw_count == 1:
        p2_score += 3
        p2_details.append("Title includes one emotional/power word.")
    else:
        p2_details.append("Title may be too neutral; consider adding one emotional/power word.")

    # Curiosity & loss aversion
    if _has_any_phrase(t, CURIOSITY_PHRASES):
        p2_score += 4
        p2_details.append("Title creates a curiosity gap (very good for CTR).")
    la_count = _count_occurrences(t, LOSS_AVERSION_WORDS)
    if la_count >= 1:
        p2_score += 2
        p2_details.append("Title uses loss-aversion language (e.g., 'stop', 'avoid').")

    # Numbers / structured format
    if re.search(r"\b\d+\b", t):
        p2_score += 3
        p2_details.append("Number in the title suggests structure (lists, steps).")

    # Direct address
    if re.search(r"\byou\b|\byour\b", t.lower()):
        p2_score += 2
        p2_details.append("Title speaks directly to the viewer ('you', 'your').")

    # Custom thumbnail?
    if has_custom_thumbnail:
        p2_score += 3
        p2_details.append("Custom thumbnail enabled – critical for CTR.")
    else:
        fixes.append("Design and upload a custom thumbnail; default frames perform poorly for CTR.")

    p2_score = min(p2_max, max(0, p2_score))
    p2_pct = int(p2_score / p2_max * 100) if p2_max else 0
    pillars["Click-Through Potential"] = {
        "score": p2_score,
        "max": p2_max,
        "pct": p2_pct,
        "details": p2_details,
    }

    # ---------- Pillar 3: Retention Potential (0–25) ----------
    p3_score = 0
    p3_max = 25
    p3_details = []

    if desc_words == 0:
        p3_details.append("No description – hard to set expectations or reinforce the hook.")
    elif desc_words < 80:
        p3_score += 4
        p3_details.append("Very short description – add more context and structure.")
    elif 80 <= desc_words <= 300:
        p3_score += 8
        p3_details.append("Good description length for setting expectations.")
    else:
        p3_score += 6
        p3_details.append("Long description – may be strong if well structured.")

    # Chapters
    if _has_chapters(d):
        p3_score += 7
        p3_details.append("Description includes timestamps/chapters – helps segment-based retention.")
    else:
        fixes.append("Add timestamps/chapters in the description for easier navigation and better retention.")

    # Hook language in first lines
    first_200 = d[:200].lower()
    if any(word in first_200 for word in ["in this video", "you will learn", "we cover", "step-by-step", "tutorial"]):
        p3_score += 5
        p3_details.append("First lines clearly state the value and structure (good hook for retention).")
    else:
        fixes.append("Use the first 1–2 lines of the description to clearly state what the viewer will get.")

    # Series hint
    if re.search(r"\bpart\s+\d+\b|\bepisode\s+\d+\b", d.lower()):
        p3_score += 3
        p3_details.append("Part of a series – can improve binge-watching and overall retention.")

    p3_score = min(p3_max, max(0, p3_score))
    p3_pct = int(p3_score / p3_max * 100) if p3_max else 0
    pillars["Retention Potential"] = {
        "score": p3_score,
        "max": p3_max,
        "pct": p3_pct,
        "details": p3_details,
    }

    # ---------- Pillar 4: Environment & Session Setup (0–20) ----------
    p4_score = 0
    p4_max = 20
    p4_details = []

    env = _env_stats_from_serp(serp or [])
    med_views = env["median_views"]

    if med_views == 0:
        p4_score += 6
        p4_details.append("No clear competition data – environment may be open.")
    elif med_views < 50000:
        p4_score += 10
        p4_details.append(f"Median views ≈ {med_views:,} – relatively low competition.")
    elif 50000 <= med_views <= 200000:
        p4_score += 7
        p4_details.append(f"Median views ≈ {med_views:,} – moderate competition.")
    else:
        p4_score += 4
        p4_details.append(f"Median views ≈ {med_views:,} – heavy competition; title/thumbnail must be exceptional.")
        fixes.append("Environment is competitive – lean harder into a bold hook and strong thumbnail contrast.")

    if in_playlists:
        p4_score += 5
        p4_details.append("Video will be in playlists – good for session time and binge-watching.")
    else:
        fixes.append("Add this video to at least one relevant playlist to increase session watch time.")

    if any(word in desc_lc for word in ["watch next", "next video", "playlist", "series", "part 2", "episode 2"]):
        p4_score += 5
        p4_details.append("Description hints at next videos/playlist – good for extending sessions.")
    else:
        fixes.append("Add a clear call-to-action to a relevant 'next video' or playlist to extend session time.")

    p4_score = min(p4_max, max(0, p4_score))
    p4_pct = int(p4_score / p4_max * 100) if p4_max else 0
    pillars["Environment & Session"] = {
        "score": p4_score,
        "max": p4_max,
        "pct": p4_pct,
        "details": p4_details,
    }

    # ---------- Aggregate ----------
    overall = p1_score + p2_score + p3_score + p4_score
    overall = max(0, min(100, overall))

    return overall, pillars, fixes


def _tokenize(text: str):
    if not text:
        return []
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    return [w for w in words if len(w) >= 3 and w not in STOPWORDS]


def _extract_top_entities(strings, top_k=10):
    counter = Counter()
    for s in strings:
        counter.update(_tokenize(s))
    return [w for w, _ in counter.most_common(top_k)]


def _score_optimize(main_keyword, title, description, tags_list, entities):
    """Return (score, breakdown:dict, fixes:list)"""
    fixes = []
    total = 0
    breakdown = {}

    # 1) Title-entity coverage (max 40)
    title_lc = (title or "").lower()
    matches = [e for e in entities if e in title_lc]
    cov = min(len(matches), 10)
    s_title_cov = cov * 4
    total += s_title_cov
    breakdown["Title covers entities"] = s_title_cov

    # 2) Description length (max 20)
    desc_len = len(description or "")
    if 150 <= desc_len <= 1500:
        s_desc = 20
    elif desc_len == 0:
        s_desc = 0
        fixes.append("Add a description (aim for 150–1500 characters).")
    else:
        if desc_len < 150:
            delta = 150 - desc_len
        else:
            delta = desc_len - 1500
        s_desc = max(2, 20 - int(delta / 100))
    total += s_desc
    breakdown["Description length"] = s_desc

    # 3) Tags count (max 15)
    tcount = len([t for t in tags_list if t])
    if 10 <= tcount <= 20:
        s_tags = 15
    elif tcount == 0:
        s_tags = 0
        fixes.append("Add tags (aim for 10–20 relevant tags).")
    else:
        s_tags = min(15, int(tcount * 1.2))
    total += s_tags
    breakdown["Tags count"] = s_tags

    # 4) Title length & clarity (max 10)
    tlen = len(title or "")
    if 1 <= tlen <= 70:
        s_tlen = 10
    elif tlen == 0:
        s_tlen = 0
        fixes.append("Add a title (keep it ≤ 70 characters).")
    else:
        s_tlen = max(3, 10 - int((tlen - 70) / 10))
        fixes.append(f"Title is long ({tlen} chars). Trim below 70 if possible.")
    total += s_tlen
    breakdown["Title length"] = s_tlen

    # 5) Keyword presence (max 15)
    mk = (main_keyword or "").lower().strip()
    if mk and mk in title_lc:
        s_kw = 15
    else:
        s_kw = 5 if mk else 0
        if mk:
            fixes.append("Include the main keyword in the title.")
    total += s_kw
    breakdown["Main keyword presence"] = s_kw

    missing = [e for e in entities if e not in title_lc][:5]
    if missing:
        fixes.append("Consider adding these important terms to the title: " + ", ".join(missing))

    total = max(0, min(100, total))
    return total, breakdown, fixes


# -------- Suggested metadata helpers --------

def _firstn(seq, n):
    return [x for x in seq[:n] if x]


def suggest_titles(keyword: str, entities: list[str]) -> list[str]:
    kw = (keyword or "").strip()
    ents = _firstn(entities, 3)
    base = " ".join(ents).title() if ents else kw.title()

    t1 = f"{kw} — {base} Explained" if kw else f"{base} Explained"
    t2 = f"{kw}: Tips, {ents[0].title() if ents else 'Guide'}, & Best Practices" if kw else f"{base}: Tips & Best Practices"
    t3 = f"{kw} ({', '.join(e.title() for e in ents)})" if kw and ents else (kw or base)

    def clamp(s):
        return s[:70].rstrip(" -:,")
    return [clamp(t) for t in [t1, t2, t3]]


def suggest_description(keyword: str, entities: list[str]) -> str:
    kw = (keyword or "").strip()
    ents = _firstn(entities, 6)
    bullets = ", ".join(ents) if ents else ""
    parts = []
    if kw:
        parts.append(f"In this video, we cover {kw} step-by-step so you can get results faster.")
    if bullets:
        parts.append(f"We’ll touch on: {bullets}.")
    parts.append("Timestamps and resources are included below. Leave your questions in the comments!")
    desc = " ".join(parts)
    return desc[:1500]


def suggest_tags(keyword: str, entities: list[str]) -> list[str]:
    kw = (keyword or "").strip()
    tags = []
    if kw:
        tags.append(kw)
    tags += _firstn(entities, 9)
    seen = set()
    out = []
    for t in tags:
        t = t.strip()
        if t and t not in seen:
            out.append(t)
            seen.add(t)
    return out


def hashtags_from_tags(tags: list[str], keyword: str) -> list[str]:
    def clean(s):
        s = re.sub(r"[^A-Za-z0-9]", "", s)
        return s

    base = []
    if keyword:
        base.append(clean(keyword))
    base += [clean(t) for t in tags]
    seen = set()
    h = []
    for x in base:
        if x and x.lower() not in seen:
            h.append("#" + x)
            seen.add(x.lower())
        if len(h) >= 6:
            break
    return h


def score_metadata(title: str, description: str, tags_list: list[str], hashtags_list: list[str]):
    total = 0
    breakdown = {}
    fixes = []

    # Title length
    tlen = len(title or "")
    if 1 <= tlen <= 70:
        s_tlen = 25
    elif tlen == 0:
        s_tlen = 0
        fixes.append("Add a title (keep it ≤ 70 characters).")
    else:
        s_tlen = max(8, 25 - int((tlen - 70) / 5))
        fixes.append(f"Title is long ({tlen} chars). Consider trimming below 70.")
    total += s_tlen
    breakdown["Title length & clarity"] = s_tlen

    # Description length
    dlen = len(description or "")
    if 150 <= dlen <= 1500:
        s_desc = 25
    elif dlen == 0:
        s_desc = 0
        fixes.append("Add a description (aim for 150–1500 characters).")
    else:
        delta = 150 - dlen if dlen < 150 else dlen - 1500
        s_desc = max(5, 25 - int(delta / 80))
    total += s_desc
    breakdown["Description adequacy"] = s_desc

    # Tags count
    tcount = len([t for t in tags_list if t])
    if 10 <= tcount <= 20:
        s_tags = 25
    elif tcount == 0:
        s_tags = 0
        fixes.append("Add tags (aim for 10–20 relevant tags).")
    else:
        s_tags = min(25, int(tcount * 1.6))
    total += s_tags
    breakdown["Tags coverage"] = s_tags

    # Hashtags
    hcount = len([h for h in hashtags_list if h])
    if 3 <= hcount <= 6:
        s_hash = 25
    elif hcount == 0:
        s_hash = 5
        fixes.append("Add a small set of hashtags (3–6).")
    else:
        s_hash = max(10, 25 - abs(4 - hcount) * 3)
    total += s_hash
    breakdown["Hashtags"] = s_hash

    total = max(0, min(100, total))
    return total, breakdown, fixes


# ===================== OPTIMIZE VIEW (with AI) =====================

def optimize(request):
    """
    GET -> analyze inputs with advanced, pillar-based scoring + rule-based + AI suggestions.
    POST -> save optimization to Library.
    """
    if request.method == "POST":
        # read submitted fields and save
        kw = request.POST.get("keyword", "").strip()
        title = request.POST.get("title", "").strip()
        desc = request.POST.get("description", "").strip()
        tags_raw = request.POST.get("tags", "").strip()
        has_custom_thumbnail = bool(request.POST.get("has_custom_thumbnail"))
        in_playlists = bool(request.POST.get("in_playlists"))
        score = int(request.POST.get("score", "0") or 0)
        entities = request.POST.get("entities", "")

        Optimization.objects.create(
            keyword=kw,
            title=title,
            description=desc,
            tags_text=tags_raw,
            has_custom_thumbnail=has_custom_thumbnail,
            in_playlists=in_playlists,
            score=score,
            entities=entities,
        )
        messages.success(request, "Optimization saved to Library ✅")
        return redirect("library")

    # default GET (analyze)
    kw = request.GET.get("keyword", "").strip()
    title = request.GET.get("title", "").strip()
    desc = request.GET.get("description", "").strip()
    tags_raw = request.GET.get("tags", "").strip()
    action = request.GET.get("action")
    tags = [t.strip() for t in tags_raw.split(",")] if tags_raw else []
    has_custom_thumbnail = bool(request.GET.get("has_custom_thumbnail"))
    in_playlists = bool(request.GET.get("in_playlists"))

    analysis = None
    error = None

    if action == "analyze":
        try:
            region = getattr(settings, "YOUTUBE_DEFAULT_REGION", "US")
            serp = search_videos(kw, max_results=15, region=region) if kw else []
            corpus = [(v["title"] or "") + " " + (v["description"] or "") for v in serp]
            entities = _extract_top_entities(corpus, top_k=10)

            # ---- NEW: advanced holistic scoring ----
            overall_score, pillars, pillar_fixes = score_holistic_package(
                kw, title, desc, tags, entities, serp, has_custom_thumbnail, in_playlists
            )

            # Legacy-style metadata-only score (still useful)
            meta_score, meta_breakdown, meta_fixes = score_metadata(
                title or "", desc or "", tags or [], hashtags_from_tags(tags, kw)
            )

            # combine all fixes
            all_fixes = pillar_fixes + meta_fixes

            analysis = {
                "entities": entities,
                "score": overall_score,
                # simple breakdown for template (pillar name -> score)
                "breakdown": {name: info["score"] for name, info in pillars.items()},
                "pillars": pillars,
                "fixes": all_fixes,
                "serp_count": len(serp),
                "title_len": len(title),
                "desc_len": len(desc),
                "tags_count": len(tags),
                "checks": {
                    "custom_thumbnail": has_custom_thumbnail,
                    "in_playlists": in_playlists,
                },
                "meta_score": meta_score,
                "meta_breakdown": meta_breakdown,
                "meta_fixes": meta_fixes,
            }

            # ---------- rule-based suggestions ----------
            suggested_titles = suggest_titles(kw, entities)
            suggested_desc = suggest_description(kw, entities)
            suggested_tags = suggest_tags(kw, entities)
            suggested_hash = hashtags_from_tags(suggested_tags, kw)

            analysis.update({
                "suggested_titles": suggested_titles,
                "suggested_description": suggested_desc,
                "suggested_tags": suggested_tags,
                "suggested_hashtags": suggested_hash,
            })

            # ---------- AI-powered suggestions (Gemini) ----------
            if kw or title or desc:
                ai_payload = {
                    "keyword": kw,
                    "current_title": title,
                    "current_description": desc,
                    "current_tags": tags,
                    "entities": entities,
                }
                ai_prompt = f"""
                You are a senior YouTube SEO strategist.

                Improve this video package for both Search and Recommendation.

                DATA (JSON):
                {json.dumps(ai_payload, indent=2)}

                Return ONLY valid JSON with this exact structure:
                {{
                  "titles": ["title1", "title2", "title3"],
                  "description": "rewritten description",
                  "tags": ["tag1", "tag2", "tag3"],
                  "hashtags": ["#tag1", "#tag2", "#tag3"]
                }}
                """
                try:
                    ai_raw = generate_content(ai_prompt)
                    try:
                        ai_json = json.loads(ai_raw)
                        analysis["ai_metadata"] = ai_json
                    except Exception:
                        analysis["ai_metadata_raw"] = ai_raw
                except Exception as e:
                    # don't kill the whole analysis if AI fails
                    analysis["ai_error"] = str(e)

        except YouTubeError as e:
            error = str(e)
        except Exception as e:
            error = f"Unexpected error: {e}"

    return render(request, "optimize.html", {
        "keyword": kw,
        "title": title,
        "description": desc,
        "tags": tags_raw,
        "has_custom_thumbnail": has_custom_thumbnail,
        "in_playlists": in_playlists,
        "analysis": analysis,
        "error": error,
    })


# ===================== LIBRARY =====================

def library(request):
    qs = Optimization.objects.order_by("-created_at")
    p = Paginator(qs, 10)
    page = p.get_page(request.GET.get("page", 1))
    return render(request, "library.html", {"page": page})


# ===================== AI GENERATOR (already working) =====================

def ai_generator(request):
    """
    Handles AI content generation.
    GET: form only.
    POST: send topic to AI and show result.
    """
    context = {}

    if request.method == "POST":
        topic = request.POST.get("topic", "").strip()
        if topic:
            prompt = f"""
Generate a full set of YouTube metadata for a video about this topic:

TOPIC: "{topic}"

Please provide:
1. Title: 5 catchy, SEO-friendly title options (under 70 characters).
2. Description: A sample 2-paragraph video description that includes a call-to-action.
3. Tags: A comma-separated list of 15-20 relevant tags.
4. Hashtags: 3-5 relevant hashtags.
"""
            response = generate_content(prompt)
            context["topic"] = topic
            context["response"] = response

    return render(request, "ai_generator.html", context)


# ===================== TAG / HASHTAG FINDERS (AI) =====================

def tag_finder(request):
    topic = ""
    tags_text = None

    if request.method == "POST":
        topic = request.POST.get("topic", "").strip()
        if topic:
            prompt = f"""
You are a YouTube SEO assistant.

Generate 25 SEO-friendly YouTube tags for a video about: "{topic}".

Return them as a single comma-separated line only, no explanation.
"""
            tags_text = generate_content(prompt).strip()

    return render(request, "tag_finder.html", {
        "topic": topic,
        "tags_text": tags_text,
    })


def hashtag_finder(request):
    topic = ""
    hashtags_text = None

    if request.method == "POST":
        topic = request.POST.get("topic", "").strip()
        if topic:
            prompt = f"""
You are a YouTube SEO assistant.

Generate 15 short, brand-safe YouTube hashtags for a video about: "{topic}".

Return them as a single space-separated line like: #tag1 #tag2 #tag3
"""
            hashtags_text = generate_content(prompt).strip()

    return render(request, "hashtag_finder.html", {
        "topic": topic,
        "hashtags_text": hashtags_text,
    })


# ===================== YOUTUBE LOOKUP (no AI yet) =====================

def youtube_lookup(request):
    # To properly add AI here we would need a video-details service.
    # For now, leave this as a placeholder page.
    return render(request, "youtube_lookup.html")
