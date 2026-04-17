"""
Shorts Analyzer — FastAPI Backend v1.5.0
- YouTube: Data API v3 (yt_key) → HTML scraping → yt-dlp
- TikTok:  TikWM API (residential proxy, 1 req/s)
- Instagram: instaloader with session auth (INSTAGRAM_SESSION_ID env var)
             → yt-dlp fallback
"""

import asyncio
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import requests as _requests

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import yt_dlp
import instaloader

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Shorts Analyzer API", version="1.9.5")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# ── Shared instances ──────────────────────────────────────────────────────────

def _make_instaloader(session_id: str = "") -> instaloader.Instaloader:
    L = instaloader.Instaloader(
        quiet=True,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
    )
    sid = session_id.strip() or os.environ.get("INSTAGRAM_SESSION_ID", "").strip()
    if sid:
        L.context._session.cookies.set("sessionid", sid, domain=".instagram.com")
        L.context._session.cookies.set("ig_did",    "",  domain=".instagram.com")
    return L

_instaloader = _make_instaloader()  # 기본 인스턴스 (env var 사용)
_executor = ThreadPoolExecutor(max_workers=20)

# TikTok: 1 req/s 제한
_tiktok_sem: Optional[asyncio.Semaphore] = None

_YT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _platform_key(url: str) -> str:
    u = url.lower()
    if "instagram.com" in u:                   return "instagram"
    if "tiktok.com" in u:                      return "tiktok"
    if "youtube.com" in u or "youtu.be" in u:  return "youtube"
    if "x.com" in u or "twitter.com" in u:     return "x"
    return "other"

def _platform_display(url: str) -> str:
    return {
        "instagram": "Instagram Reels",
        "tiktok":    "TikTok",
        "youtube":   "YouTube Shorts",
        "x":         "X (Twitter)",
        "other":     "Unknown",
    }[_platform_key(url)]

def _classify_error(msg: str, platform: str = "") -> str:
    m = msg.lower()
    if "private" in m:                                   return "Private / Unavailable"
    if "404" in m or "not found" in m:                   return "Not Found (404)"
    if "429" in m or "too many" in m:
        if platform == "instagram":
            return "Instagram 요청 한도 초과 — 설정에서 Session ID 입력 필요"
        return "Rate Limited (429)"
    if "login" in m or "sign in" in m or "bot" in m:
        if platform == "instagram":
            return "Instagram 인증 필요 — ⚙ 설정에서 Session ID 입력"
        return "Login Required"
    if "removed" in m or "deleted" in m:                 return "Video Removed"
    if "queryre" in m:                                   return "Not Found (404)"
    return f"Error: {msg[:80]}"

def _extract_youtube_id(url: str) -> Optional[str]:
    m = re.search(r"(?:shorts/|watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None

def _parse_int(s) -> Optional[int]:
    if s is None:
        return None
    digits = re.sub(r"[^\d]", "", str(s))
    return int(digits) if digits else None

# ── Platform fetchers ─────────────────────────────────────────────────────────

_IG_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_IG_EMBED_HEADERS = {
    "User-Agent": _IG_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "iframe",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Referer": "https://www.google.com/",
}

def _extract_instagram_shortcode(url: str) -> Optional[str]:
    """지원 형식: /p/, /reel/, /reels/, /tv/, /{user}/reel/, /share/..."""
    patterns = [
        r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
        r"instagram\.com/[^/]+/(?:reel|reels|p)/([A-Za-z0-9_-]+)",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None

def _resolve_instagram_share(url: str) -> str:
    """Instagram /share/ URL은 최종 /reel/{shortcode}/로 리디렉션됨."""
    try:
        r = _requests.get(
            url,
            headers={"User-Agent": _IG_UA},
            allow_redirects=True,
            timeout=10,
        )
        return r.url
    except Exception:
        return url

def _fetch_instagram_graphql(shortcode: str, session_id: str = "") -> dict:
    """Instagram GraphQL 직접 호출 — instaloader 의존성 없이 view count 포함."""
    cookies = {}
    if session_id:
        cookies["sessionid"] = session_id

    r = _requests.get(
        "https://www.instagram.com/graphql/query",
        params={
            "variables": json.dumps({"shortcode": shortcode}),
            "doc_id": "8845758582119845",
        },
        headers={
            "User-Agent": _IG_UA,
            "x-ig-app-id": "936619743392459",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"https://www.instagram.com/p/{shortcode}/",
        },
        cookies=cookies,
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()

    media = (
        body.get("data", {}).get("xdt_shortcode_media")
        or body.get("data", {}).get("shortcode_media")
    )
    if not media:
        raise ValueError("Instagram 응답에서 미디어 정보 없음")

    # video_play_count = Instagram 표시 재생수, video_view_count = 3초 이상 조회수
    views    = media.get("video_play_count") or media.get("video_view_count")
    likes    = (media.get("edge_media_preview_like") or {}).get("count")
    comments = (media.get("edge_media_to_parent_comment") or
                media.get("edge_media_to_comment") or {}).get("count")
    if likes is not None and likes < 0:
        likes = None
    if comments is not None and comments < 0:
        comments = None
    is_video = media.get("is_video", False)
    return {
        "views":    views,
        "likes":    likes,
        "comments": comments,
        "shares":   None,
        "is_video": is_video,
    }

def _parse_ig_embed_html(html: str, shortcode: str) -> dict:
    """embed/captioned HTML에서 views/likes 추출. shortcode 일치 확인."""
    if shortcode not in html:
        raise ValueError("embed 응답이 다른 포스트 (캐시 오염)")
    views: Optional[int] = None
    likes: Optional[int] = None
    for pat in (r'"video_view_count":\s*(\d+)',
                r'"video_play_count":\s*(\d+)'):
        m = re.search(pat, html)
        if m:
            v = int(m.group(1))
            if v > 0:
                views = v; break
    m = re.search(r'"edge_media_preview_like":\s*\{\s*"count":\s*(-?\d+)', html)
    if m:
        v = int(m.group(1))
        if v >= 0:
            likes = v
    if likes is None:
        m = re.search(r'(\d[\d,]*)\s+likes\b', html, flags=re.IGNORECASE)
        if m: likes = _parse_int(m.group(1))
    return {"views": views, "likes": likes, "comments": None, "shares": None}

def _fetch_instagram_embed(shortcode: str) -> dict:
    """Instagram 공개 embed 페이지 — iframe 헤더로 SPA 쉘 방지."""
    r = _requests.get(
        f"https://www.instagram.com/p/{shortcode}/embed/captioned/",
        headers=_IG_EMBED_HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    html = r.text
    # Railway 등 rate-limited IP에서는 Instagram이 약 800KB 짜리 SPA 쉘을 반환함.
    # 실제 embed 페이지에만 있는 'EmbedSimple' 마커로 구분.
    if "EmbedSimple" not in html:
        raise ValueError("embed shell (IP rate-limited)")
    data = _parse_ig_embed_html(html, shortcode)
    if data["views"] is None and data["likes"] is None:
        raise ValueError("embed 파싱 실패")
    return data

_IG_PROXIES = (
    "https://api.codetabs.com/v1/proxy/?quest={}",
)

def _fetch_instagram_via_proxy(shortcode: str) -> dict:
    """Rate-limited IP 우회용 공용 CORS 프록시 경유."""
    target = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    last_err: Optional[str] = None
    for tpl in _IG_PROXIES:
        try:
            r = _requests.get(
                tpl.format(target),
                headers=_IG_EMBED_HEADERS,
                timeout=25,
            )
            if r.status_code != 200 or "EmbedSimple" not in r.text:
                last_err = f"{tpl.split('/')[2]}: status={r.status_code} shell={('EmbedSimple' not in r.text)}"
                continue
            data = _parse_ig_embed_html(r.text, shortcode)
            if data["views"] is not None or data["likes"] is not None:
                return data
            last_err = f"{tpl.split('/')[2]}: parse empty"
        except Exception as e:
            last_err = f"{tpl.split('/')[2]}: {e}"
    raise ValueError(f"proxy 모두 실패 ({last_err})")

def _fetch_instagram_ytdlp(url: str, session_id: str = "") -> dict:
    """yt-dlp fallback — 세션 쿠키 지원."""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    if session_id:
        import tempfile, http.cookiejar
        jar = http.cookiejar.MozillaCookieJar()
        c = http.cookiejar.Cookie(
            version=0, name="sessionid", value=session_id,
            port=None, port_specified=False,
            domain=".instagram.com", domain_specified=True, domain_initial_dot=True,
            path="/", path_specified=True, secure=True, expires=0,
            discard=True, comment=None, comment_url=None, rest={}, rfc2109=False,
        )
        jar.set_cookie(c)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w")
        jar.save(tmp.name)
        tmp.close()
        opts["cookiefile"] = tmp.name
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "views":    info.get("view_count"),
        "likes":    info.get("like_count"),
        "comments": info.get("comment_count"),
        "shares":   None,
    }

def _check_instagram_private(shortcode: str) -> bool:
    """비공개 게시물인지 확인 (og:description 없으면 비공개/로그인 필요)."""
    try:
        chk = _requests.get(
            f"https://www.instagram.com/p/{shortcode}/",
            headers={"User-Agent": _IG_UA},
            timeout=10,
        )
        return chk.status_code == 200 and "og:description" not in chk.text
    except Exception:
        return False

def _fetch_instagram(url: str, insta_session: str = "") -> dict:
    if "/share/" in url.lower():
        url = _resolve_instagram_share(url)

    shortcode = _extract_instagram_shortcode(url)
    if not shortcode:
        if re.match(r"https?://(?:www\.)?instagram\.com/[^/]+/?(?:\?.*)?$", url):
            raise ValueError("Instagram 프로필 URL — 게시물 URL을 입력하세요 (/p/ 또는 /reel/)")
        raise ValueError("Instagram URL 파싱 실패")

    errors = []

    import time as _time

    # 1차: 세션 있으면 정식 GraphQL (가장 정확 — views 포함)
    if insta_session:
        try:
            return _fetch_instagram_graphql(shortcode, insta_session)
        except Exception as e:
            errors.append(f"graphql(auth):{e}")

    # 2차: GraphQL 비인증 (views 포함, 로컬 IP에서 동작)
    for attempt in range(3):
        try:
            result = _fetch_instagram_graphql(shortcode, "")
            # GraphQL 성공 + views/likes 중 하나라도 있으면 반환
            if result.get("views") is not None or result.get("likes") is not None:
                return result
            # 데이터가 없으면 embed로 계속 시도
            errors.append(f"graphql({attempt+1}):data empty")
            break
        except Exception as e:
            errors.append(f"graphql({attempt+1}):{e}")
            if attempt < 2:
                _time.sleep(1.0 * (attempt + 1))

    # 3차: Instagram embed 페이지 — GraphQL이 비어있을 때 보완 (likes 확보)
    embed_result = None
    try:
        embed_result = _fetch_instagram_embed(shortcode)
    except Exception as e:
        errors.append(f"embed:{e}")

    # embed + GraphQL 결과 병합 (GraphQL views + embed likes)
    if embed_result is not None:
        gql_views = None
        for attempt in range(2):
            try:
                gql = _fetch_instagram_graphql(shortcode, "")
                if gql.get("views") is not None:
                    gql_views = gql["views"]
                    break
            except Exception:
                if attempt < 1:
                    _time.sleep(1.0)
        if gql_views is not None:
            embed_result["views"] = gql_views
        return embed_result

    # 4차: 공용 프록시 경유
    try:
        return _fetch_instagram_via_proxy(shortcode)
    except Exception as e:
        errors.append(f"proxy:{e}")

    # 5차: yt-dlp (세션 있으면 쿠키 전달)
    try:
        return _fetch_instagram_ytdlp(url, insta_session)
    except Exception as e:
        errors.append(f"ytdlp:{e}")

    # 6차: 세션 있을 때만 instaloader 사용
    if insta_session:
        try:
            il = _make_instaloader(insta_session)
            post = instaloader.Post.from_shortcode(il.context, shortcode)
            return {
                "views":    post.video_view_count if post.is_video else None,
                "likes":    post.likes,
                "comments": post.comments,
                "shares":   None,
            }
        except Exception as e:
            errors.append(f"instaloader:{e}")

    # 모든 경로 실패 → 비공개 게시물인지 확인
    if _check_instagram_private(shortcode):
        raise RuntimeError("비공개 게시물 — 로그인 필요 (설정에서 Session ID 입력)")

    raise RuntimeError("Instagram 조회 실패 — 설정에서 Session ID를 입력하면 해결됩니다")

def _fetch_tiktok_tikwm(url: str) -> dict:
    resp = _requests.get(
        "https://www.tikwm.com/api/",
        params={"url": url},
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise ValueError(body.get("msg", "TikWM API 오류"))
    d = body["data"]
    return {
        "views":    d.get("play_count"),
        "likes":    d.get("digg_count"),
        "comments": d.get("comment_count"),
        "shares":   d.get("share_count"),
    }

def _extract_tweet_id(url: str) -> Optional[str]:
    m = re.search(r"/status/(\d+)", url)
    return m.group(1) if m else None

def _fetch_x_fxtwitter(tweet_id: str) -> dict:
    """FxTwitter API로 X(Twitter) 트윗 메트릭 조회."""
    resp = _requests.get(
        f"https://api.fxtwitter.com/status/{tweet_id}",
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    resp.raise_for_status()
    body = resp.json()
    tweet = body.get("tweet")
    if not tweet:
        raise ValueError("트윗 정보 없음")
    return {
        "views":    tweet.get("views"),
        "likes":    tweet.get("likes"),
        "comments": tweet.get("replies"),
        "shares":   tweet.get("retweets"),
    }

def _fetch_x(url: str) -> dict:
    tweet_id = _extract_tweet_id(url)
    if not tweet_id:
        raise ValueError("X(Twitter) URL에서 트윗 ID를 추출할 수 없습니다")
    return _fetch_x_fxtwitter(tweet_id)

def _fetch_youtube_api(video_id: str, yt_key: str) -> dict:
    resp = _requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "statistics", "id": video_id, "key": yt_key},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise ValueError(body["error"].get("message", "YouTube API error"))
    items = body.get("items", [])
    if not items:
        raise ValueError("Not Found (404)")
    s = items[0].get("statistics", {})
    return {
        "views":    int(s["viewCount"])    if "viewCount"    in s else None,
        "likes":    int(s["likeCount"])    if "likeCount"    in s else None,
        "comments": int(s["commentCount"]) if "commentCount" in s else None,
        "shares":   None,
    }

def _fetch_youtube_html(url: str) -> dict:
    resp = _requests.get(url, headers=_YT_HEADERS, timeout=20, allow_redirects=True)
    resp.raise_for_status()
    html = resp.text
    if "viewCount" not in html:
        raise ValueError("viewCount not found — bot block")
    views    = _parse_int(re.search(r'"viewCount":"(\d+)"', html) and
                          re.search(r'"viewCount":"(\d+)"', html).group(1))
    likes    = _parse_int(re.search(r'"likeCount":"(\d+)"', html) and
                          re.search(r'"likeCount":"(\d+)"', html).group(1))
    comments = _parse_int(re.search(r'"commentCount":\{"simpleText":"([^"]+)"', html) and
                          re.search(r'"commentCount":\{"simpleText":"([^"]+)"', html).group(1))
    if views is None:
        raise ValueError("viewCount parse failed")
    return {"views": views, "likes": likes, "comments": comments, "shares": None}

def _fetch_youtube_innertube(video_id: str) -> dict:
    """YouTube 내부 player API — 서버 IP 차단 없이 viewCount 반환."""
    payload = {
        "videoId": video_id,
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20240101.00.00",
                "hl": "en",
                "gl": "US",
            }
        },
    }
    resp = _requests.post(
        "https://www.youtube.com/youtubei/v1/player"
        "?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    status = body.get("playabilityStatus", {}).get("status", "")
    if status not in ("OK", ""):
        raise ValueError(f"YouTube playability: {status}")
    vd = body.get("videoDetails", {})
    view_count = vd.get("viewCount")
    return {
        "views":    int(view_count) if view_count else None,
        "likes":    None,   # innertube player에서 제공 안 됨
        "comments": None,   # innertube player에서 제공 안 됨
        "shares":   None,
    }

def _fetch_youtube_ytdlp(url: str) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extractor_args": {"youtube": {"player_client": ["tv_embedded"]}},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "views":    info.get("view_count"),
        "likes":    info.get("like_count"),
        "comments": info.get("comment_count"),
        "shares":   None,
    }

def _fetch_youtube(url: str, yt_key: str) -> dict:
    vid = _extract_youtube_id(url)

    # 1순위: YouTube Data API v3 (key 있을 때) — 완전한 통계
    if yt_key and vid:
        return _fetch_youtube_api(vid, yt_key)

    # 2순위: HTML 스크래핑
    try:
        return _fetch_youtube_html(url)
    except Exception:
        pass

    # 3순위: innertube player (viewCount만, likes/comments 없음)
    if vid:
        try:
            return _fetch_youtube_innertube(vid)
        except Exception:
            pass

    # 4순위: yt-dlp fallback
    return _fetch_youtube_ytdlp(url)

# ── Async fetch ────────────────────────────────────────────────────────────────

async def _fetch_tiktok_async(url: str, loop) -> dict:
    global _tiktok_sem
    if _tiktok_sem is None:
        _tiktok_sem = asyncio.Semaphore(1)
    async with _tiktok_sem:
        result = await loop.run_in_executor(_executor, _fetch_tiktok_tikwm, url)
        await asyncio.sleep(1.1)
        return result

async def _fetch_one(
    url: str, idx: int, total: int,
    semaphore: asyncio.Semaphore,
    delay: float,
    yt_key: str,
    insta_session: str,
) -> dict:
    async with semaphore:
        loop = asyncio.get_event_loop()
        base = {
            "idx": idx, "total": total, "url": url,
            "platform": _platform_display(url),
            "views": None, "likes": None,
            "comments": None, "shares": None, "saves": None,
        }
        try:
            key = _platform_key(url)
            if key == "instagram":
                raw = await asyncio.wait_for(
                    loop.run_in_executor(_executor, _fetch_instagram, url, insta_session),
                    timeout=45,
                )
            elif key == "tiktok":
                raw = await asyncio.wait_for(_fetch_tiktok_async(url, loop), timeout=60)
            elif key == "youtube":
                raw = await asyncio.wait_for(
                    loop.run_in_executor(_executor, _fetch_youtube, url, yt_key),
                    timeout=60,
                )
            elif key == "x":
                raw = await asyncio.wait_for(
                    loop.run_in_executor(_executor, _fetch_x, url),
                    timeout=30,
                )
            else:
                raise ValueError("지원하지 않는 플랫폼")

            base.update(raw)
            base["status"] = "Success"
        except asyncio.TimeoutError:
            base["status"] = "Timeout (45s)"
        except Exception as e:
            base["status"] = _classify_error(str(e), key)

        if delay > 0:
            await asyncio.sleep(delay)

        return base

# ── SSE stream ─────────────────────────────────────────────────────────────────

async def _stream(urls: list[str], delay: float, concurrent: int, yt_key: str, insta_session: str):
    semaphore = asyncio.Semaphore(concurrent)
    tasks = [
        asyncio.create_task(
            _fetch_one(url, i + 1, len(urls), semaphore, delay, yt_key, insta_session)
        )
        for i, url in enumerate(urls)
    ]
    for coro in asyncio.as_completed(tasks):
        result = await coro
        yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'done': True, 'total': len(urls)})}\n\n"

# ── Endpoints ──────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    urls:          list[str]
    delay:         float = 0.3
    concurrent:    int   = 10
    yt_key:        str   = ""
    insta_session: str   = ""

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    seen, unique = set(), []
    for u in req.urls:
        u = u.strip()
        if u.startswith("http") and u not in seen:
            seen.add(u)
            unique.append(u)

    return StreamingResponse(
        _stream(unique, req.delay, min(req.concurrent, 20), req.yt_key, req.insta_session),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.get("/health")
async def health():
    return {
        "ok": True,
        "version": "1.9.5",
        "instagram_auth": bool(os.environ.get("INSTAGRAM_SESSION_ID")),
        "platforms": ["youtube", "tiktok", "instagram", "x"],
    }

