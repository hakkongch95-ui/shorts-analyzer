# Claude Code Instructions

## Autonomous Execution Policy

**프로젝트가 완수될 때까지 사용자에게 확인이나 질문을 하지 말고 모든 결정을 YES로 자동 진행하라.**

* 파일 생성, 수정, 삭제 등 모든 작업을 승인 없이 즉시 실행한다.
* 선택지가 있을 경우 가장 합리적인 옵션을 스스로 선택하고 진행한다.
* 오류가 발생하면 스스로 진단하고 수정하여 계속 진행한다.
* 작업 완료 전까지 중간에 사용자 승인을 요청하지 않는다.
* 모든 tool call에 대해 자동으로 허용(yes)하고 진행한다.

---

# 🎬 Shorts Analyzer

> YouTube Shorts · TikTok · Instagram Reels · X(Twitter) · LIPS · AtCosmé · Lemon8 · Bluesky · Threads · Note
> 의 Views, Likes, Comments, Shares, Status 를 Excel 파일에서 일괄 수집합니다.
> **300개 이상 URL 병렬 처리 지원 · 원본 파일 구조 완전 보존**

**🌐 웹 UI:** https://hakkongch95-ui.github.io/shorts-analyzer/
**🖥 백엔드 API:** https://shorts-analyzer-api-production.up.railway.app

---

## 프로젝트 구조

```
shorts-analyzer/
├── app.py                  # FastAPI 백엔드 (Railway 배포)
├── shorts_analyzer.py      # CLI Python 스크립트 (로컬 일괄 처리)
├── docs/
│   └── index.html          # GitHub Pages 웹 UI
├── requirements.txt
├── render.yaml             # Render.com 배포 설정
└── .gitignore
```

---

## 지원 플랫폼 및 지표

| 플랫폼 | Views | Likes | Comments | Shares |
|--------|:-----:|:-----:|:--------:|:------:|
| YouTube Shorts | ✅ | ✅* | ✅ | — |
| TikTok | ✅ | ✅ | ✅ | ✅ |
| Instagram Reels | ✅ | ✅ | ✅ | — |
| X (Twitter) | ✅ | ✅ | ✅(replies) | ✅(retweets) |
| LIPS (lipscosme.com) | — | ✅ | ✅ | ✅(clips) |
| AtCosmé (cosme.net) | — | ✅(helpful) | — | — |
| Lemon8 | — | ✅ | ✅ | — |
| Bluesky | — | ✅ | ✅(replies) | ✅(reposts) |
| Threads | — | — | — | — |
| Note (note.com) | — | ✅ | ✅ | — |

> \* YouTube 좋아요는 크리에이터가 숨길 경우 N/A

---

## 핵심 설계 원칙

### Excel 처리 (shorts_analyzer.py · 웹 UI)

1. **원본 훼손 없음**: 원본 파일을 복사 후 결과를 삽입하거나, 새 파일로 저장
2. **각 URL 열 바로 우측에 결과 삽입**: URL 열 → [Views, Likes, Comments, Shares, Status] 5열
3. **다중 URL 열 자동 감지**: `http`로 시작하는 셀이 있으면 자동으로 URL 열로 인식
4. **혼합 플랫폼 열 처리**: URL의 80% 이상이 동일 플랫폼이면 해당 접두어(TT\_, IG\_ 등) 사용; 혼합이면 접두어 없이 일반 이름 사용
5. **Status 열**: 성공/실패 메시지를 별도 열로 관리 (Views 열을 에러 메시지로 오염하지 않음)

### 출력 열 구조 예시 (list_check.xlsx 기준)

```
[TikTok URL] [TT_Views][TT_Likes][TT_Comments][TT_Shares][TT_Status]
[YouTube URL] [YT_Views][YT_Likes][YT_Comments][YT_Shares][YT_Status]
[Instagram URL] [IG_Views][IG_Likes][IG_Comments][IG_Shares][IG_Status]
[X URL] [X_Views][X_Likes][X_Comments][X_Shares][X_Status]
[Other URL] [LIPS_Views][LIPS_Likes][LIPS_Comments][LIPS_Shares][LIPS_Status]
```

---

## CLI 사용법 (shorts_analyzer.py)

```bash
# 기본 사용
python shorts_analyzer.py list_check.xlsx

# 출력 파일 지정
python shorts_analyzer.py list_check.xlsx -o result.xlsx

# 로컬 백엔드 사용
python shorts_analyzer.py list_check.xlsx --api http://localhost:8000

# Instagram Session ID 사용
python shorts_analyzer.py list_check.xlsx --session YOUR_SESSION_ID

# 동시 처리 수 조정
python shorts_analyzer.py list_check.xlsx --concurrent 3 --delay 0.5
```

### 인수 목록

| 인수 | 기본값 | 설명 |
|------|--------|------|
| `input` | (필수) | 입력 Excel 파일 |
| `-o` / `--output` | `{원본명}_result.xlsx` | 출력 파일 경로 |
| `--api` | Railway URL | 백엔드 API 주소 |
| `--session` | 없음 | Instagram Session ID |
| `--delay` | 0.3 | 요청 간 딜레이 (초) |
| `--concurrent` | 5 | 동시 요청 수 |

---

## 웹 UI 사용법

### 1단계 — 설정 (⚙ 설정 버튼)

| 설정 | 필요 시점 | 설명 |
|------|-----------|------|
| YouTube Data API 키 | YouTube URL 처리 시 | 백엔드 없이 YouTube만 처리 가능. 무료, 하루 10,000회 |
| 백엔드 API URL | TikTok·Instagram·X·LIPS 등 | Railway/Render 백엔드 URL 입력 |
| Instagram Session ID | Instagram 안정성 향상 시 | instagram.com → F12 → Application → Cookies → sessionid |

### 2단계 — 분석

**Excel 업로드 탭**
1. `.xlsx` 파일 드래그 또는 클릭
2. URL 열 자동 감지 — 열 정보 및 URL 수 표시
3. 🚀 분석 시작 클릭

**URL 직접 입력 탭**
1. 한 줄에 URL 하나씩 입력
2. 🚀 분석 시작 클릭

### 3단계 — 결과 내보내기

| 버튼 | 설명 |
|------|------|
| 📥 Excel (원본 구조) | 원본 Excel 구조 유지 + 각 URL 열 바로 우측에 결과 삽입 |
| 📥 Excel (결과만) | 단순 결과 테이블 (Platform, URL, Views, Likes, Comments, Shares, Status) |
| 📋 CSV 복사 | 결과를 CSV 형식으로 클립보드 복사 |

---

## 백엔드 아키텍처 (app.py)

### 플랫폼별 수집 방식

| 플랫폼 | 방식 | 비고 |
|--------|------|------|
| YouTube | Data API v3 → HTML 스크래핑 → innertube → yt-dlp | API 키 있으면 완전한 통계 |
| TikTok | TikWM API (residential proxy) | 1 req/s 제한 |
| Instagram | GraphQL(인증) → GraphQL(비인증) → embed → proxy → yt-dlp → instaloader | 6단계 폴백 |
| X (Twitter) | FxTwitter 공개 API | 개인 API 키 불필요 |
| LIPS | HTML 스크래핑 | Mobile UA 필요 |
| AtCosmé | HTML 스크래핑 | rating + helpful count |
| Lemon8 | HTML Remix 스크립트 파싱 | URL 디코딩 필요 |
| Bluesky | AT Protocol 공개 API | 인증 불필요 |
| Threads | HTTP 200 확인만 | 공개 지표 없음 |
| Note | note.com 공개 API v3 | 인증 불필요 |

### 동시성 제어

- Instagram: Semaphore(2) — 동시 2개 제한, rate-limit 방지
- TikTok: Semaphore(1) + 1.1s sleep — 1 req/s 유지
- 전체: Semaphore(concurrent) — 기본 10, 최대 20

### API 엔드포인트

```
POST /analyze
  Body: { urls: string[], delay: float, concurrent: int, yt_key: string, insta_session: string }
  Response: SSE stream (data: {...result...}\n\n)

GET /health
  Response: { ok: true, version: string, instagram_auth: bool, platforms: [...] }
```

---

## 보안 정책

### API 키 관리

| 키 | 위치 | 노출 리스크 | 비고 |
|----|------|------------|------|
| YouTube Data API 키 | 클라이언트 localStorage | 낮음 (사용자 로컬에만 저장) | 하드코딩 없음 |
| Instagram Session ID | 클라이언트 localStorage / 서버 환경변수 | 낮음 | 환경변수 `INSTAGRAM_SESSION_ID` 권장 |
| YouTube innertube 키 | app.py 코드 내 | 없음 | YouTube 자체 공개 웹 플레이어 키, 개인 키 아님 |

- `.gitignore`에 `*_result.xlsx`, `*.env`, `.env.*` 포함 → 결과 파일·환경 파일 커밋 방지
- 개인 API 키 하드코딩 없음
- CORS: `allow_origins=["*"]` (공개 API, 클라이언트 전용)

### 환경변수 (서버 배포 시)

```
INSTAGRAM_SESSION_ID=your_session_id   # Instagram 인증 (선택)
YT_INNERTUBE_KEY=custom_key            # YouTube innertube 키 오버라이드 (선택)
```

---

## 오류 코드

| 상태 | 의미 |
|------|------|
| `Success` | 정상 수집 |
| `Private / Unavailable` | 비공개 또는 계정 정지 |
| `Not Found (404)` | 삭제되었거나 URL 오류 |
| `Rate Limited (429)` | 요청 한도 초과 |
| `Instagram 요청 한도 초과 — Session ID 입력 필요` | Instagram IP 차단 |
| `Login Required` | 로그인 필요 |
| `Video Removed` | 영상 삭제됨 |
| `Timeout (45s)` | 응답 시간 초과 |
| `백엔드 필요 — ⚙ 설정에서 백엔드 URL 입력` | 웹 UI에서 백엔드 미설정 |

---

## 배포 이력

| 버전 | 날짜 | 주요 변경사항 |
|------|------|--------------|
| v2.2.0 | 2026-04-19 | 전 플랫폼 완전 지원 (10개), Status 열 추가, 원본 구조 보존 Excel 내보내기, 다중 열 자동 감지, 보안 강화 |
| v2.1.2 | 2026-04-17 | Instagram rate-limit 재시도 + backoff, 동시 2개 제한 |
| v2.1.1 | 2026-04-17 | 웹 UI 버전 배지 업데이트 |
| v2.1.0 | 2026-04-16 | LIPS/Lemon8/Bluesky/Threads/Note 플랫폼 배지 추가 |
| v2.0.0 | 2026-04-16 | vt.tiktok 단축 URL, Bluesky/Threads/Note 지원, 범용 URL 폴백 |

---

## 개발 환경 설정

```bash
git clone https://github.com/hakkongch95-ui/shorts-analyzer.git
cd shorts-analyzer
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 로컬 백엔드 실행

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
# → http://localhost:8000
# 웹 UI 설정에서 http://localhost:8000 입력
```

### GitHub Pages 배포

`docs/index.html`이 GitHub Pages 소스. `master` 브랜치 push 시 자동 배포.

```bash
git add docs/index.html
git commit -m "update web UI"
git push origin master
```

---

## License

[MIT](LICENSE)
