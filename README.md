# AutomatePinterest

**AutomatePinterest** is a full-stack browser automation engine built with **Python FastAPI**, **Playwright / Browser-Use (CDP)**, and **React 18 + TypeScript + Material UI (MUI)**. It automates creating Pinterest boards & pins for Amazon Flash Deals sourced from WorldNewzs.in, cross-posting pins to Facebook Pages & Groups with 5-layer deduplication, and generating daily PDF & Excel activity reports.

---

## Architecture

```text
AutomatePinterest/
├── backend/
│   ├── __init__.py
│   ├── main.py                          # FastAPI server (REST + SSE on Port 3001)
│   ├── requirements.txt                 # Python dependencies
│   └── engine/
│       ├── __init__.py
│       ├── browser_agent.py             # Visual cursor & smooth mouse trajectory engine
│       ├── pinterest_flow.py            # 11-step Pinterest board & pin automation pipeline
│       ├── facebook_share_flow.py       # Pinterest -> Facebook Page & Group automation flow
│       ├── facebook_report_exporter.py  # Excel (.xlsx) & PDF live-proof report exporter
│       ├── pdf_reporter.py              # ReportLab generator for daily PDF activity reports
│       ├── scraper.py                   # WorldNewzs deals dataset loader & 50-char truncator
│       ├── session_manager.py           # Persistent headful browser context & session manager
│       └── social_manager.py            # 5-layer deduplication ledger & content shuffler
├── src/
│   ├── components/
│   │   ├── PageDeckView.tsx             # Pagewise deal selector, sync & range controller
│   │   ├── ExecutionPipeline.tsx        # Real-time 11-step visual progress pipeline
│   │   ├── SocialMediaHub.tsx           # Facebook & Twitter automation hub with live proof viewer
│   │   ├── ReportManager.tsx            # Daily PDF report viewer & download center
│   │   └── ActivityLog.tsx              # Real-time SSE streaming log terminal
│   ├── data/
│   │   └── amazonProducts.json          # Cached Amazon deals dataset
│   ├── services/
│   │   ├── api.ts                       # Typed Axios client for FastAPI endpoints
│   │   └── sse.ts                       # Singleton EventSource manager with auto-reconnect
│   ├── types/
│   │   └── index.ts                     # Shared TypeScript interfaces
│   ├── App.tsx                          # Root React dashboard component
│   └── main.tsx                         # Application entry point
├── scripts/
│   ├── copy_edge_cookies.ps1            # Syncs native Microsoft Edge cookies to automation profile
│   ├── open_pinterest_chrome.bat        # Helper script to launch Pinterest login
│   ├── open_pinterest_chrome.ps1        # PowerShell helper for Pinterest session
│   └── share_pins_to_social.py          # CLI utility for deduplication & social sharing tests
├── state/
│   └── .gitkeep                         # Runtime state, deduplication ledger & screenshots (gitignored)
├── .env.example                         # Environment variable template (safe to commit)
├── package.json                         # Frontend dependencies & application scripts
├── tsconfig.json                        # TypeScript compiler configuration
└── vite.config.ts                       # Vite bundler & dev proxy configuration
```

---

## Core Workflows

### 1. 11-Step Pinterest Board & Pin Pipeline
For each product deal card (6 cards per page) across the user-selected page range:
1. **Navigate Deals URL**: Confirm `https://worldnewzs.in/amazon-products`.
2. **Select Deal Card**: Load the 6 deal cards for the active page.
3. **Open Pin Creation**: Open the Pinterest Pin Builder URL with product media and affiliate link.
4. **Click "Create board"**: Trigger the board creation modal (or reuse existing matching board).
5. **Truncate Title (50 chars)**: Strictly truncate the product title to a maximum of **50 characters** (hard cut).
6. **Paste to Board Name**: Enter the truncated title into the board name field.
7. **Add Collaborators**: Dynamically discover and assign connected Pinterest collaborators.
8. **Create Board & "See it"**: Submit the board and follow the "See it now" redirect.
9. **Click Red "Save" Pin**: Trigger the red Save button.
10. **Strict Verify Save State**: Verify the Save button transitions to dark grey disabled (`Saved`) state.
11. **Close Tab & Next Card**: Close the Pinterest tab and advance to the next card.

### 2. Pinterest → Facebook Page & Group Automation
- Harvests unposted pins from the Pinterest account (`_created/`).
- Enforces **5-layer deduplication** (`DeduplicationLedger`) so pins are never double-posted.
- Shuffles post copy, CTAs, emojis, and category hashtags (`ContentShuffler`).
- Verifies and attaches high-resolution product images (`state/temp_pin_images/`).
- Publishes to the configured Facebook Page feed and/or Facebook Group with anti-spam pacing.
- Captures proof screenshots (`state/screenshots/`) and compiles `.xlsx` and `.pdf` reports.

---

## Getting Started

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** & **npm**
- **Microsoft Edge** or **Chromium** (via Playwright)

### 1. Clone & Configure Environment
```powershell
cp .env.example .env
```
Edit `.env` with your Pinterest and Social Media credentials and target URLs. Never commit `.env` to version control.

### 2. Install Backend Dependencies
```powershell
python -m venv venv
.\venv\Scripts\pip install -r backend/requirements.txt
.\venv\Scripts\playwright install chromium
```

### 3. Install Frontend Dependencies & Build Production Bundle
```powershell
npm install
npm run build
```

### 4. Start the Application
```powershell
npm start
```
The unified FastAPI server + React production dashboard will start at **`http://localhost:3001`**.

---

## Security & Best Practices
- **Zero Hardcoded Secrets**: All credentials (`PINTEREST_PASSWORD`, `TWITTER_PASSWORD`, `FACEBOOK_PASSWORD`) are loaded exclusively from `.env` at runtime.
- **Path Traversal Protection**: Report and proof download endpoints sanitize file names with `os.path.basename` and enforce directory containment.
- **Scoped CORS**: `CORSMiddleware` restricts cross-origin requests to configured local origins (`CORS_ALLOWED_ORIGINS`).
- **Clean Git Hygiene**: `.env`, browser profiles (`user_data/`), runtime ledgers (`state/*.json`), and screenshots (`state/screenshots/`) are excluded via `.gitignore`.
