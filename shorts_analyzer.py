#!/usr/bin/env python3
"""
Shorts Analyzer
Fetch engagement metrics (views, likes, comments, shares) for
Instagram Reels, YouTube Shorts, and TikTok from an Excel file.

Usage:
    python shorts_analyzer.py input.xlsx
    python shorts_analyzer.py input.xlsx --column 2 --output results.xlsx
    python shorts_analyzer.py input.xlsx --cookies cookies.txt
"""

import sys
import time
import argparse
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    print("Error: yt-dlp not installed. Run: pip install yt-dlp")
    sys.exit(1)

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
except ImportError:
    print("Error: openpyxl not installed. Run: pip install openpyxl")
    sys.exit(1)


# ── Constants ──────────────────────────────────────────────────────────────────

METRIC_HEADERS = ["Platform", "Views", "Likes", "Comments", "Shares", "Saves", "Status"]
DEFAULT_DELAY  = 1.5   # seconds between requests to avoid rate limiting

# Header cell style
HEADER_BG    = "1565C0"   # dark blue
HEADER_FG    = "FFFFFF"   # white
SUCCESS_BG   = "E8F5E9"   # light green
ERROR_BG     = "FFEBEE"   # light red
NA_BG        = "FFF9C4"   # light yellow


# ── Helpers ────────────────────────────────────────────────────────────────────

def detect_platform(url: str) -> str:
    u = url.lower()
    if "youtube.com/shorts" in u or "youtu.be" in u or "youtube.com/watch" in u:
        return "YouTube Shorts"
    if "tiktok.com" in u:
        return "TikTok"
    if "instagram.com" in u:
        return "Instagram Reels"
    return "Unknown"


def fmt(n) -> str:
    """Format a number with commas, or return 'N/A'."""
    if n is None:
        return "N/A"
    return f"{n:,}"


# ── Core fetch ─────────────────────────────────────────────────────────────────

def fetch_metrics(url: str, cookies_file: str = None) -> dict:
    """
    Use yt-dlp to extract engagement metrics for a given video URL.
    Returns a dict with keys: platform, views, likes, comments, shares, saves, status.

    Note:
      - 'saves' is not publicly exposed by any platform; always returns None.
      - 'likes' may be None for YouTube if the creator has disabled the count.
      - 'shares' is only available on TikTok (as repost_count).
    """
    opts = {
        "quiet":        True,
        "no_warnings":  True,
        "skip_download": True,
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file

    base = {
        "platform": detect_platform(url),
        "views":    None,
        "likes":    None,
        "comments": None,
        "shares":   None,
        "saves":    None,   # never publicly available
        "status":   "Success",
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        base.update({
            "views":    info.get("view_count"),
            "likes":    info.get("like_count"),
            "comments": info.get("comment_count"),
            "shares":   info.get("repost_count"),   # TikTok only
        })
        return base

    except yt_dlp.utils.DownloadError as e:
        msg = str(e).lower()
        if "private" in msg:
            status = "Private / Unavailable"
        elif "404" in msg or "not found" in msg:
            status = "Not Found (404)"
        elif "login" in msg or "sign in" in msg or "age" in msg:
            status = "Login Required — use --cookies"
        elif "removed" in msg or "deleted" in msg:
            status = "Video Removed"
        else:
            status = f"Error: {str(e)[:90]}"
        base["status"] = status
        return base

    except Exception as e:
        base["status"] = f"Error: {str(e)[:90]}"
        return base


# ── Excel I/O ──────────────────────────────────────────────────────────────────

def _style_header_cell(cell, text: str):
    cell.value = text
    cell.font      = Font(bold=True, color=HEADER_FG)
    cell.fill      = PatternFill(start_color=HEADER_BG, end_color=HEADER_BG, fill_type="solid")
    cell.alignment = Alignment(horizontal="center", vertical="center")


def _style_data_cell(cell, bg: str):
    cell.fill      = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
    cell.alignment = Alignment(horizontal="center", vertical="center")


def process_excel(
    input_path:   str,
    url_column:   int   = 1,
    output_path:  str   = None,
    cookies_file: str   = None,
    delay:        float = DEFAULT_DELAY,
) -> str:
    p = Path(input_path)
    if output_path is None:
        output_path = str(p.parent / f"{p.stem}_analyzed{p.suffix}")

    wb = openpyxl.load_workbook(input_path)
    ws = wb.active

    # ── detect header row ──────────────────────────────────────────────────────
    first_val = ws.cell(row=1, column=url_column).value
    has_header = bool(
        first_val
        and isinstance(first_val, str)
        and not first_val.strip().startswith("http")
    )
    start_row  = 2 if has_header else 1
    header_row = 1 if has_header else None

    metrics_start_col = url_column + 1

    # ── write metric headers ───────────────────────────────────────────────────
    if header_row:
        for i, h in enumerate(METRIC_HEADERS):
            _style_header_cell(
                ws.cell(row=header_row, column=metrics_start_col + i), h
            )

    # ── collect valid URLs ─────────────────────────────────────────────────────
    rows_to_process = []
    for row in ws.iter_rows(min_row=start_row, max_row=ws.max_row):
        cell = row[url_column - 1]
        val  = cell.value
        if val and isinstance(val, str) and val.strip().startswith("http"):
            rows_to_process.append((cell.row, val.strip()))

    total = len(rows_to_process)
    if total == 0:
        print("No valid URLs found in the specified column.")
        return output_path

    print(f"Found {total} URL(s) to process.\n")
    ok_count  = 0
    err_count = 0

    for idx, (row_num, url) in enumerate(rows_to_process, 1):
        print(f"[{idx:>3}/{total}]  {url[:72]}")
        metrics = fetch_metrics(url, cookies_file)

        values = [
            metrics["platform"],
            metrics["views"],
            metrics["likes"],
            metrics["comments"],
            metrics["shares"],
            metrics["saves"],
            metrics["status"],
        ]

        success = metrics["status"] == "Success"
        bg = SUCCESS_BG if success else ERROR_BG

        for col_offset, val in enumerate(values):
            c = ws.cell(row=row_num, column=metrics_start_col + col_offset)
            c.value = val
            _style_data_cell(c, bg)
            # Saves column always gets yellow bg (always N/A)
            if col_offset == 5:
                _style_data_cell(c, NA_BG)

        if success:
            ok_count += 1
            print(
                f"         ✓  Views:{fmt(metrics['views']):>12}  "
                f"Likes:{fmt(metrics['likes']):>12}  "
                f"Comments:{fmt(metrics['comments']):>10}  "
                f"Shares:{fmt(metrics['shares']):>10}"
            )
        else:
            err_count += 1
            print(f"         ✗  {metrics['status']}")

        if idx < total:
            time.sleep(delay)

    # ── auto-width ─────────────────────────────────────────────────────────────
    for col_offset, header in enumerate(METRIC_HEADERS):
        col_letter = get_column_letter(metrics_start_col + col_offset)
        ws.column_dimensions[col_letter].width = max(14, len(header) + 6)

    wb.save(output_path)

    print(f"\n{'─' * 65}")
    print(f"  Done!  {ok_count} success  |  {err_count} error(s)  |  total {total}")
    print(f"  Saved → {output_path}")
    print(f"{'─' * 65}")

    return output_path


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Shorts Analyzer — fetch engagement metrics for short-form videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python shorts_analyzer.py urls.xlsx
  python shorts_analyzer.py urls.xlsx --column 2
  python shorts_analyzer.py urls.xlsx --output results.xlsx
  python shorts_analyzer.py urls.xlsx --cookies cookies.txt --delay 2

notes:
  • Supported platforms : YouTube Shorts, TikTok, Instagram Reels
  • Available metrics   : Views, Likes, Comments, Shares (TikTok only)
  • 'Saves' is never publicly accessible on any platform (shown as N/A)
  • For Instagram login-required content, export cookies via a browser
    extension (e.g. 'Get cookies.txt LOCALLY') and pass with --cookies
""",
    )
    parser.add_argument("input",
        help="Excel file (.xlsx) containing video URLs")
    parser.add_argument("-c", "--column", type=int, default=1,
        metavar="N",
        help="column number that contains URLs — 1 = column A (default: 1)")
    parser.add_argument("-o", "--output", default=None,
        metavar="FILE",
        help="output file path (default: <input>_analyzed.xlsx)")
    parser.add_argument("--cookies", default=None,
        metavar="FILE",
        help="Netscape-format cookies.txt for age-restricted / login-required content")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
        metavar="SEC",
        help=f"seconds to wait between requests (default: {DEFAULT_DELAY})")

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: file not found — {args.input}")
        sys.exit(1)

    if not args.input.lower().endswith((".xlsx", ".xls")):
        print("Error: input must be an Excel file (.xlsx or .xls)")
        sys.exit(1)

    process_excel(
        input_path   = args.input,
        url_column   = args.column,
        output_path  = args.output,
        cookies_file = args.cookies,
        delay        = args.delay,
    )


if __name__ == "__main__":
    main()
