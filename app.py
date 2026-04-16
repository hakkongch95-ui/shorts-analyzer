"""
Shorts Analyzer — FastAPI Backend
Async parallel scraping for YouTube Shorts, TikTok, Instagram Reels.
"""

import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor

import requests as _requests

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import yt_dlp
import instaloader

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Shorts Analyzer API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# ── Shared instances ──────────────────────────────────────────────────────────

_instaloader = instaloader.Instaloader(
    quiet=True,
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
)

_executor = ThreadPoolExecutor(max_workers=20)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _platform_key(url: str) -> str:
    u = url.lower()
    if "instagram.com" in u:                        return "instagram"
    if "tiktok.com" in u:                           return "tiktok"
    if "youtube.com" in u or "youtu.be" in u:       return "youtube"
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
    if "private" in m:                     return "Private / Unavailable"
    if "404" in m or "not found" in m:     return "Not Found (404)"
    if "login" in m or "sign in" in m:     return "Login Required"
    if "removed" in m or "deleted" in m:   return "Video Removed"
    if "queryre" in m:                     return "Not Found (404)"
    return f"Error: {msg[:80]}"

# ── Platform fetchers (sync, run in executor) ─────────────────────────────────

def _fetch_instagram(url: str) -> dict:
    # /p/, /reel/, /reels/, /tv/ 모두 지원
    m = re.search(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", url)
    if not m:
        raise ValueError("Instagram URL 파싱 실패")
    post = instaloader.Post.from_shortcode(_instaloader.context, m.group(1))
    return {
        "views":    post.video_view_count if post.is_video else None,
        "likes":    post.likes,
        "comments": post.comments,
        "shares":   None,
    }

def _fetch_tiktok(url: str) -> dict:
    """TikWM API 경유 — 서버 IP 차단 우회."""
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

def _fetch_youtube(url: str) -> dict:
    """tv_embedded 클라이언트 — Login Required / format unavailable 우회."""
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

# ── Async fetch ────────────────────────────────────────────────────────────────

async def _fetch_one(
    url: str, idx: int, total: int,
    semaphore: asyncio.Semaphore,
    delay: float,
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
                raw = await loop.run_in_executor(_executor, _fetch_instagram, url)
            elif key == "tiktok":
                raw = await loop.run_in_executor(_executor, _fetch_tiktok, url)
            else:
                raw = await loop.run_in_executor(_executor, _fetch_youtube, url)

            base.update(raw)
            base["status"] = "Success"
        except Exception as e:
            base["status"] = _classify_error(str(e))

        if delay > 0:
            await asyncio.sleep(delay)

        return base

# ── SSE stream ─────────────────────────────────────────────────────────────────

async def _stream(urls: list[str], delay: float, concurrent: int):
    semaphore = asyncio.Semaphore(concurrent)

    tasks = [
        asyncio.create_task(_fetch_one(url, i + 1, len(urls), semaphore, delay))
        for i, url in enumerate(urls)
    ]

    for coro in asyncio.as_completed(tasks):
        result = await coro
        yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"

    yield f"data: {json.dumps({'done': True, 'total': len(urls)})}\n\n"

# ── Endpoints ──────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    urls:       list[str]
    delay:      float = 0.3
    concurrent: int   = 10

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    seen, unique = set(), []
    for u in req.urls:
        u = u.strip()
        if u.startswith("http") and u not in seen:
            seen.add(u)
            unique.append(u)

    return StreamingResponse(
        _stream(unique, req.delay, min(req.concurrent, 20)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.get("/health")
async def health():
    return {"ok": True, "version": "1.1.0"}
