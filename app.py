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

app = FastAPI(title="Shorts Analyzer API", version="1.6.0")

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
    return "other"

def _platform_display(url: str) -> str:
    return {
        "instagram": "Instagram Reels",
        "tiktok":    "TikTok",
        "youtube":   "YouTube Shorts",
        "other":     "Unknown",
    }[_platform_key(url)]

def _classify_error(msg: str) -> str:
    m = msg.lower()
    if "private" in m:                               return "Private / Unavailable"
    if "404" in m or "not found" in m:               return "Not Found (404)"
    if "login" in m or "sign in" in m or "bot" in m: return "Login Required"
    if "removed" in m or "deleted" in m:             return "Video Removed"
    if "queryre" in m:                               return "Not Found (404)"
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

def _fetch_instagram(url: str, insta_session: str = "") -> dict:
    m = re.search(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", url)
    if not m:
        raise ValueError("Instagram URL 파싱 실패")
    shortcode = m.group(1)

    # 세션 제공 시 전용 instaloader 인스턴스 생성
    il = _make_instaloader(insta_session) if insta_session else _instaloader

    # 1차: instaloader (retry 최대 2회)
    last_err = None
    for attempt in range(2):
        try:
            if attempt > 0:
                import time; time.sleep(3 * attempt)
            post = instaloader.Post.from_shortcode(il.context, shortcode)
            return {
                "views":    post.video_view_count if post.is_video else None,
                "likes":    post.likes,
                "comments": post.comments,
                "shares":   None,
            }
        except Exception as e:
            last_err = e
            continue

    # 2차: yt-dlp fallback
    try:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "views":    info.get("view_count"),
            "likes":    info.get("like_count"),
            "comments": info.get("comment_count"),
            "shares":   None,
        }
    except Exception:
        raise last_err or ValueError("Instagram 수집 실패")

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
    if yt_key and vid:
        return _fetch_youtube_api(vid, yt_key)
    try:
        return _fetch_youtube_html(url)
    except Exception:
        pass
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
                raw = await loop.run_in_executor(
                    _executor, _fetch_instagram, url, insta_session
                )
            elif key == "tiktok":
                raw = await _fetch_tiktok_async(url, loop)
            elif key == "youtube":
                raw = await loop.run_in_executor(_executor, _fetch_youtube, url, yt_key)
            else:
                raise ValueError("지원하지 않는 플랫폼")

            base.update(raw)
            base["status"] = "Success"
        except Exception as e:
            base["status"] = _classify_error(str(e))

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
        "version": "1.6.0",
        "instagram_auth": bool(os.environ.get("INSTAGRAM_SESSION_ID")),
    }
