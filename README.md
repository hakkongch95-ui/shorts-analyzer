# 🎬 Shorts Analyzer

> YouTube Shorts · TikTok · Instagram Reels 의 Views, Likes, Comments, Shares를  
> Excel 파일에서 일괄 수집합니다. **300개 이상 URL 병렬 처리 지원.**

**🌐 웹 UI:** https://hakkongch95-ui.github.io/shorts-analyzer/

---

## 지원 지표

| 플랫폼 | Views | Likes | Comments | Shares | Saves |
|---|:---:|:---:|:---:|:---:|:---:|
| YouTube Shorts | ✅ | ✅* | ✅ | — | — |
| TikTok | ✅ | ✅ | ✅ | ✅ | — |
| Instagram Reels | ✅ | ✅ | ✅ | — | — |

> \* YouTube 좋아요는 크리에이터가 숨길 경우 N/A  
> Saves는 모든 플랫폼에서 비공개 지표 (항상 N/A)

---

## 🚀 웹 UI 사용 방법

### 1단계 — 백엔드 배포 (Render.com, 무료)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/hakkongch95-ui/shorts-analyzer)

버튼 클릭 → Render.com 계정으로 로그인 → **"Apply"** 클릭  
배포 완료 후 `https://shorts-analyzer-api.onrender.com` 형태의 URL 발급됨

### 2단계 — 프론트엔드 설정

1. https://hakkongch95-ui.github.io/shorts-analyzer/ 접속
2. **⚙ 설정** 클릭
3. **백엔드 API URL** 에 Render 주소 입력 → **연결 테스트** → **저장**

### 3단계 — 분석

- **Excel 업로드**: URL이 담긴 Excel 파일을 드래그 → 열 번호 지정 → 🚀 분석 시작
- **직접 입력**: URL을 한 줄씩 붙여넣기 → 🚀 분석 시작
- 결과는 실시간으로 표에 표시되며, Excel / CSV로 다운로드 가능

---

## 💻 CLI 사용 방법 (로컬 Python)

### 설치

```bash
git clone https://github.com/hakkongch95-ui/shorts-analyzer.git
cd shorts-analyzer
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 실행

```bash
# 기본 사용
python shorts_analyzer.py urls.xlsx

# URL이 D열(4번)에 있는 경우
python shorts_analyzer.py urls.xlsx --column 4

# 출력 파일 지정
python shorts_analyzer.py urls.xlsx --output results.xlsx

# Instagram 비공개 콘텐츠 (쿠키 파일 필요)
python shorts_analyzer.py urls.xlsx --cookies cookies.txt
```

---

## 🛠 백엔드 직접 실행

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
# → http://localhost:8000
# 웹 UI 설정에서 http://localhost:8000 입력 후 사용
```

---

## ⚙ 300+ URL 최적화

백엔드는 플랫폼별 비동기 병렬 처리를 사용합니다:

| 설정 | 기본값 | 설명 |
|---|---|---|
| 동시 처리 수 | 10 | 최대 20까지 설정 가능 |
| 요청 지연 | 0.3s | 0 = 최대 속도 (차단 위험) |

> Instagram은 반복 요청 시 차단될 수 있습니다. 100개 이상은 지연 0.5s 이상 권장.

---

## 오류 코드

| 상태 | 의미 |
|---|---|
| `Success` | 정상 수집 |
| `Private / Unavailable` | 비공개 또는 계정 정지 |
| `Not Found (404)` | 삭제되었거나 URL 오류 |
| `Login Required` | 로그인 필요 (`--cookies` 사용) |
| `Video Removed` | 영상 삭제됨 |

---

## License

[MIT](LICENSE)
