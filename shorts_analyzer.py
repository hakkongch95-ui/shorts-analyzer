#!/usr/bin/env python3
"""
Shorts Analyzer — Excel Batch Processor
엑셀 파일의 모든 URL 열을 분석하여 각 URL 열 우측에 결과 열을 삽입합니다.

Usage:
    python shorts_analyzer.py list_check.xlsx
    python shorts_analyzer.py list_check.xlsx --api http://localhost:8000
    python shorts_analyzer.py list_check.xlsx --session YOUR_SESSION_ID
"""

import sys
import json
import time
import argparse
import urllib.request
from copy import copy
from pathlib import Path

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    print("Error: openpyxl not installed. Run: pip install openpyxl")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_API = "https://shorts-analyzer-api-production.up.railway.app"
METRIC_HEADERS = ["Views", "Likes", "Comments", "Shares"]

# URL이 들어있는 열 번호 (1-indexed)
URL_COLUMNS = [3, 5, 7, 9, 10]  # C, E, G, I, J

# Style
HEADER_FILL = PatternFill(start_color="1565C0", end_color="1565C0", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=10)
SUCCESS_FILL = PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid")
ERROR_FILL = PatternFill(start_color="FFEBEE", end_color="FFEBEE", fill_type="solid")
CENTER = Alignment(horizontal="center", vertical="center")


# ── API call ──────────────────────────────────────────────────────────────────

def analyze_urls(urls: list[str], api_base: str, session_id: str = "",
                 delay: float = 0.3, concurrent: int = 5) -> dict:
    """
    API에 URL 목록을 보내고 {url: result_dict} 매핑을 반환합니다.
    result_dict: {views, likes, comments, shares, status}
    """
    if not urls:
        return {}

    body = json.dumps({
        "urls": urls,
        "delay": delay,
        "concurrent": concurrent,
        "yt_key": "",
        "insta_session": session_id,
    }).encode()

    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/analyze",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    results = {}
    with urllib.request.urlopen(req, timeout=600) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload:
                continue
            obj = json.loads(payload)
            if obj.get("done"):
                continue
            results[obj["url"]] = obj

    return results


def sanitize_value(val):
    """음수값(-1 등)을 None으로 변환합니다."""
    if val is None:
        return None
    if isinstance(val, (int, float)) and val < 0:
        return None
    return val


# ── Excel processing ──────────────────────────────────────────────────────────

def _copy_cell_style(src, dst):
    """셀 스타일을 복사합니다."""
    if src.has_style:
        dst.font = copy(src.font)
        dst.fill = copy(src.fill)
        dst.alignment = copy(src.alignment)
        dst.border = copy(src.border)
        dst.number_format = src.number_format


def process_excel(input_path: str, output_path: str = None,
                  api_base: str = DEFAULT_API, session_id: str = "",
                  delay: float = 0.3, concurrent: int = 5):
    p = Path(input_path)
    if output_path is None:
        output_path = str(p.parent / f"{p.stem}_result{p.suffix}")

    wb = openpyxl.load_workbook(input_path)
    ws = wb.active
    max_row = ws.max_row
    max_col = ws.max_column

    # ── 1단계: URL 열 위치 확인 (실제 데이터 있는 열만) ─────────────────────
    active_url_cols = []
    for col_idx in URL_COLUMNS:
        if col_idx > max_col:
            continue
        has_url = False
        for row in range(2, max_row + 1):
            val = ws.cell(row=row, column=col_idx).value
            if val and str(val).strip().startswith("http"):
                has_url = True
                break
        if has_url:
            active_url_cols.append(col_idx)

    print(f"활성 URL 열: {active_url_cols}")
    print(f"원본: {max_row}행 x {max_col}열")

    # ── 2단계: 모든 URL 수집 (중복 제거) ────────────────────────────────────
    url_set = set()
    url_cell_map = []  # (row, orig_col, url)

    for col_idx in active_url_cols:
        for row in range(2, max_row + 1):
            val = ws.cell(row=row, column=col_idx).value
            if val and str(val).strip().startswith("http"):
                url = str(val).strip()
                url_set.add(url)
                url_cell_map.append((row, col_idx, url))

    unique_urls = list(url_set)
    print(f"분석 대상 URL: {len(unique_urls)}개 (고유), 총 셀: {len(url_cell_map)}개")

    # ── 3단계: API 호출 (배치) ──────────────────────────────────────────────
    print(f"\nAPI 호출 중 ({api_base})...")
    batch_size = 50
    all_results = {}

    for i in range(0, len(unique_urls), batch_size):
        batch = unique_urls[i:i + batch_size]
        print(f"  배치 {i // batch_size + 1}: {len(batch)}개 URL 처리 중...")
        try:
            batch_results = analyze_urls(batch, api_base, session_id, delay, concurrent)
            all_results.update(batch_results)
        except Exception as e:
            print(f"  ⚠ 배치 실패: {e}")
        if i + batch_size < len(unique_urls):
            time.sleep(1)

    ok = sum(1 for r in all_results.values() if r.get("status") == "Success")
    print(f"분석 완료: {ok}/{len(unique_urls)} 성공\n")

    # ── 4단계: 새 열 구조 매핑 ──────────────────────────────────────────────
    # 원본 열 → 새 열 매핑 (URL 열 뒤에 4개 메트릭 열 삽입)
    # 오른쪽부터 처리해서 왼쪽 열 번호가 변하지 않도록 함
    sorted_url_cols = sorted(active_url_cols)

    # orig_col → new_col 매핑 테이블 구성
    col_mapping = {}  # orig_col → new_col
    metric_insert_points = {}  # orig_url_col → new_col (첫 메트릭 열 위치)

    new_col = 1
    for orig in range(1, max_col + 1):
        col_mapping[orig] = new_col
        new_col += 1
        if orig in sorted_url_cols:
            metric_insert_points[orig] = new_col
            new_col += len(METRIC_HEADERS)  # 4칸 건너뜀

    new_max_col = new_col - 1
    print(f"결과: {max_row}행 x {new_max_col}열 (메트릭 {len(active_url_cols) * len(METRIC_HEADERS)}열 추가)")

    # ── 5단계: 새 워크북 생성 ───────────────────────────────────────────────
    wb_out = openpyxl.Workbook()
    ws_out = wb_out.active
    ws_out.title = ws.title

    # 헤더 행 복사 + 메트릭 헤더 삽입
    for orig_col in range(1, max_col + 1):
        src = ws.cell(row=1, column=orig_col)
        dst = ws_out.cell(row=1, column=col_mapping[orig_col])
        dst.value = src.value
        _copy_cell_style(src, dst)

    for url_col, insert_col in metric_insert_points.items():
        # URL 열 헤더에서 플랫폼명 추출
        url_header = str(ws.cell(row=1, column=url_col).value or "")
        platform = ""
        if "tiktok" in url_header.lower():
            platform = "TT_"
        elif "youtube" in url_header.lower():
            platform = "YT_"
        elif "instagram" in url_header.lower():
            platform = "IG_"
        elif "twitter" in url_header.lower() or "x(" in url_header.lower():
            platform = "X_"
        else:
            platform = "Other_"

        for i, header in enumerate(METRIC_HEADERS):
            cell = ws_out.cell(row=1, column=insert_col + i)
            cell.value = f"{platform}{header}"
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = CENTER

    # 데이터 행 복사 + 메트릭 값 채우기
    for row in range(2, max_row + 1):
        # 원본 데이터 복사
        for orig_col in range(1, max_col + 1):
            src = ws.cell(row=row, column=orig_col)
            dst = ws_out.cell(row=row, column=col_mapping[orig_col])
            dst.value = src.value
            _copy_cell_style(src, dst)

        # 각 URL 열의 메트릭 값 채우기
        for url_col, insert_col in metric_insert_points.items():
            val = ws.cell(row=row, column=url_col).value
            url = str(val).strip() if val else ""

            if url.startswith("http") and url in all_results:
                result = all_results[url]
                is_success = result.get("status") == "Success"
                fill = SUCCESS_FILL if is_success else ERROR_FILL

                metrics = [
                    sanitize_value(result.get("views")),
                    sanitize_value(result.get("likes")),
                    sanitize_value(result.get("comments")),
                    sanitize_value(result.get("shares")),
                ]

                for i, metric_val in enumerate(metrics):
                    cell = ws_out.cell(row=row, column=insert_col + i)
                    if is_success:
                        cell.value = metric_val
                    else:
                        # 에러 시 첫 열에만 상태 메시지 표시
                        cell.value = result.get("status", "") if i == 0 else None
                    cell.fill = fill
                    cell.alignment = CENTER

    # ── 6단계: 열 너비 조정 ─────────────────────────────────────────────────
    for url_col, insert_col in metric_insert_points.items():
        for i in range(len(METRIC_HEADERS)):
            col_letter = openpyxl.utils.get_column_letter(insert_col + i)
            ws_out.column_dimensions[col_letter].width = 14

    # 원본 열 너비 복사
    for orig_col in range(1, max_col + 1):
        orig_letter = openpyxl.utils.get_column_letter(orig_col)
        new_letter = openpyxl.utils.get_column_letter(col_mapping[orig_col])
        if ws.column_dimensions[orig_letter].width:
            ws_out.column_dimensions[new_letter].width = ws.column_dimensions[orig_letter].width

    wb_out.save(output_path)
    print(f"저장 완료: {output_path}")
    return output_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Shorts Analyzer — 엑셀 파일의 모든 URL 열을 분석",
    )
    parser.add_argument("input", help="입력 엑셀 파일 (.xlsx)")
    parser.add_argument("-o", "--output", default=None, help="출력 파일 경로")
    parser.add_argument("--api", default=DEFAULT_API, help=f"API 주소 (기본: {DEFAULT_API})")
    parser.add_argument("--session", default="", help="Instagram Session ID")
    parser.add_argument("--delay", type=float, default=0.3, help="요청 간 딜레이 (초)")
    parser.add_argument("--concurrent", type=int, default=5, help="동시 요청 수")

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: 파일 없음 — {args.input}")
        sys.exit(1)

    process_excel(
        input_path=args.input,
        output_path=args.output,
        api_base=args.api,
        session_id=args.session,
        delay=args.delay,
        concurrent=args.concurrent,
    )


if __name__ == "__main__":
    main()
