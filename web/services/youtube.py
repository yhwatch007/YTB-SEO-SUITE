import requests
from django.conf import settings

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

class YouTubeError(Exception):
    pass

def _require_key():
    api_key = settings.YOUTUBE_API_KEY
    if not api_key:
        raise YouTubeError("Missing YOUTUBE_API_KEY. Add it to your .env file.")
    return api_key

def _iso8601_to_seconds(s: str) -> int:
    # Examples: PT9M12S, PT1H02M03S
    if not s or not s.startswith("PT"):
        return 0
    h = m = sec = 0
    num = ""
    for ch in s[2:]:
        if ch.isdigit():
            num += ch
        else:
            if ch == "H":
                h = int(num or 0)
            elif ch == "M":
                m = int(num or 0)
            elif ch == "S":
                sec = int(num or 0)
            num = ""
    return h * 3600 + m * 60 + sec

def search_videos(query: str, max_results: int = 5, region: str = None):
    """
    Returns list of dicts:
    { id,title,channel,thumb,url,views,likes,comments,published,description,duration_sec }
    """
    api_key = _require_key()
    region = region or settings.YOUTUBE_DEFAULT_REGION

    # 1) search -> ids
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max(1, min(int(max_results), 20)),
        "regionCode": region,
        "key": api_key,
    }
    r = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=10)
    if r.status_code != 200:
        raise YouTubeError(f"Search error: {r.status_code} {r.text}")

    data = r.json()
    ids = [it["id"]["videoId"] for it in data.get("items", []) if "id" in it and "videoId" in it["id"]]
    if not ids:
        return []

    # 2) videos -> stats + details
    params2 = {
        "part": "snippet,statistics,contentDetails",
        "id": ",".join(ids),
        "key": api_key,
    }
    r2 = requests.get(YOUTUBE_VIDEOS_URL, params=params2, timeout=10)
    if r2.status_code != 200:
        raise YouTubeError(f"Videos error: {r2.status_code} {r2.text}")

    out = []
    for v in r2.json().get("items", []):
        sn = v.get("snippet", {})
        st = v.get("statistics", {})
        cd = v.get("contentDetails", {})
        vid = v.get("id")
        out.append({
            "id": vid,
            "title": sn.get("title", ""),
            "channel": sn.get("channelTitle", ""),
            "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "url": f"https://www.youtube.com/watch?v={vid}",
            "views": int(st.get("viewCount", 0) or 0),
            "likes": int(st.get("likeCount", 0) or 0),          # may be hidden → 0
            "comments": int(st.get("commentCount", 0) or 0),    # may be disabled → 0
            "published": sn.get("publishedAt", "")[:10],
            "description": sn.get("description", "") or "",
            "duration_sec": _iso8601_to_seconds(cd.get("duration")),
        })
    return out
