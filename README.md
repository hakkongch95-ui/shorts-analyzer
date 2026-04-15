# Shorts Analyzer

> Fetch engagement metrics for **YouTube Shorts**, **TikTok**, and **Instagram Reels** directly from an Excel file.

---

## Features

| Platform | Views | Likes | Comments | Shares | Saves |
|---|:---:|:---:|:---:|:---:|:---:|
| YouTube Shorts | ✅ | ✅ * | ✅ | — | — |
| TikTok | ✅ | ✅ | ✅ | ✅ | — |
| Instagram Reels | ✅ | ✅ | ✅ | — | — |

> \* YouTube likes may be hidden by the creator.  
> Saves are never publicly accessible on any platform.

---

## Requirements

- Python **3.8+**
- Internet connection

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/hakkongch95-ui/shorts-analyzer.git
cd shorts-analyzer

# 2. (Recommended) Create a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Usage

### Prepare your Excel file

Put video URLs in **column A** (one URL per row). A header row is optional.

```
| Video URL                                          |
|----------------------------------------------------|
| https://www.youtube.com/shorts/abc123              |
| https://www.tiktok.com/@user/video/123456789       |
| https://www.instagram.com/reel/xyz789/             |
```

### Run

```bash
# Basic — results saved as input_analyzed.xlsx
python shorts_analyzer.py urls.xlsx

# URLs are in column B (2)
python shorts_analyzer.py urls.xlsx --column 2

# Custom output file name
python shorts_analyzer.py urls.xlsx --output results.xlsx

# Use cookies for login-required / age-restricted content
python shorts_analyzer.py urls.xlsx --cookies cookies.txt

# Adjust delay between requests (default: 1.5 s)
python shorts_analyzer.py urls.xlsx --delay 2
```

### Output

The script writes these columns **immediately to the right** of your URL column:

| Platform | Views | Likes | Comments | Shares | Saves | Status |
|---|---|---|---|---|---|---|
| YouTube Shorts | 1,234,567 | 45,678 | 3,210 | N/A | N/A | Success |
| TikTok | 9,876,543 | 512,300 | 28,400 | 74,200 | N/A | Success |
| Instagram Reels | 234,100 | 18,900 | 1,540 | N/A | N/A | Success |

Rows are **colour-coded**: green = success, red = error, yellow = N/A.

---

## Handling Login-Required Content

Some Instagram or TikTok posts require a logged-in session.

1. Install a browser extension such as **Get cookies.txt LOCALLY** (Chrome / Firefox).
2. Visit the platform while logged in and export `cookies.txt` (Netscape format).
3. Pass the file to the script:

```bash
python shorts_analyzer.py urls.xlsx --cookies cookies.txt
```

> **Never commit `cookies.txt` to Git.** It is already in `.gitignore`.

---

## Error Reference

| Status | Meaning |
|---|---|
| `Success` | Metrics fetched successfully |
| `Private / Unavailable` | Video is private or account is suspended |
| `Not Found (404)` | URL is broken or video was deleted |
| `Login Required — use --cookies` | Content requires authentication |
| `Video Removed` | Video was taken down |
| `Error: ...` | Unexpected error (message shown inline) |

---

## Limitations

- **Saves** are an internal metric on all platforms and cannot be scraped publicly.
- **Shares** are only available on TikTok.
- Instagram may block repeated requests — use `--delay 3` or `--cookies` if needed.
- YouTube like counts are hidden when the creator disables them.
- Metrics reflect the value **at the time the script is run**.

---

## Contributing

Pull requests are welcome. Please open an issue first to discuss larger changes.

---

## License

[MIT](LICENSE)
