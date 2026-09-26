---
name: automate-pinterest
description: Build and maintain a Python FastAPI and Browser-Use (CDP-based) browser automation tool that scrapes Amazon deal cards from WorldNewzs.in and creates matching Pinterest boards/pins for each product, looping across a user-configurable number of pagination pages, and generating a dated PDF activity report. Use this skill whenever the user asks to build, modify, debug, or extend the "AutomatePinterest" tool, its React/TypeScript/MUI frontend, its Python FastAPI backend, its Browser-Use CDP automation scripts, its env-based URL/config management, or its daily PDF reporting output.
compatibility: Requires Python 3.11+, FastAPI, Uvicorn, Browser-Use, Playwright Python, ReportLab, a Pinterest account with UI access, React + Vite + TypeScript + MUI + axios on the frontend.
---

# Automate Pinterest (Python FastAPI + Browser-Use CDP Architecture)

Automates repinning Amazon "Flash Deal" products (sourced from WorldNewzs.in) onto Pinterest boards, one product per board, looping through a user-selected number of pagination pages, and produces a dated PDF activity report at the end of each run.

## Confirmed 11-Step Workflow (Per Product Card)

For each product card, on each page, up to the user-selected page count:

1. **Navigate Deals URL**: Confirm source URL (`https://worldnewzs.in/amazon-products`).
2. **Select Deal Card**: Extract the 6 deal cards for the active page (from local dataset or live DOM).
3. **Open Pin Creation**: Open Pinterest Pin Creation URL (`https://www.pinterest.com/pin/create/button/?...`).
4. **Click "Create board"**: Trigger the Pinterest board creation modal.
5. **Truncate Title (50 chars)**: Strictly truncate the title to **maximum 50 characters** (hard cut).
6. **Paste to Board Name**: Type the truncated title into the board name field.
7. **Add Collaborators**: Dynamically auto-discover and select all connected Pinterest account collaborators (e.g. `Kousi Devarasetty`, `LuxeLace`, `Tarun sales`, and any newly added users).

8. **Create Board & "See it"**: Click "Create" board and handle the "See it now" redirect.
9. **Click Red "Save" Pin**: Trigger the red pin save button.
10. **Strict Verify Save State**: Confirm Save button transitions from red to **dark grey / disabled ("Saved" state)** or receives confirmation toast.
11. **Close Tab & Next Card**: Close the Pinterest tab, return to deals, and loop to the next card.

## System Architecture

```
automate-pinterest/
├── backend/
│   ├── main.py                  # FastAPI application with REST + SSE endpoints (Port 3001)
│   ├── engine/
│   │   ├── browser_agent.py     # Browser-Use visual mouse pointer & coordinate engine
│   │   ├── pinterest_flow.py    # 11-step Pinterest board & pin automation pipeline
│   │   ├── scraper.py           # Deals dataset loader & 50-character title truncator
│   │   ├── pdf_reporter.py      # ReportLab generator for daily PDF reports
│   │   └── session_manager.py   # Headful browser context & Edge DPAPI session sync
│   └── requirements.txt         # Python dependencies
├── src/
│   ├── components/
│   │   ├── PageDeckView.tsx     # Pagewise selection (Page 1 to 230) with lazy loading
│   │   ├── ExecutionPipeline.tsx# Interactive 11-step visual matrix with progress badges
│   │   ├── ReportManager.tsx    # PDF report viewer & download center
│   │   └── ActivityLog.tsx      # Real-time streaming log terminal
│   ├── services/
│   │   └── api.ts               # Axios client interfacing with FastAPI
│   └── App.tsx                  # React + TypeScript + MUI root with React.Suspense
```

**Configuration (.env)**:
```
WORLDNEWZS_URL=https://worldnewzs.in/amazon-products
PINTEREST_BASE_URL=https://www.pinterest.com
PINTEREST_PROFILE_URL=https://in.pinterest.com/ganeshkumardevarasetty/_saved/
PINTEREST_EMAIL=your_email@example.com
PINTEREST_PASSWORD=your_password_here
REPORT_OUTPUT_DIR=C:\Downloads\AutomatePinterest
```

## Pagewise Selection & Execution

- Users can browse through pages (e.g., Page 1, Page 2, Page 5) using the MUI pagination toolbar.
- The 6 product cards for the active page are displayed with lazy-loaded images, prices, discounts, and real-time 50-character title truncation badges.
- Clicking **"Run 11-Steps for Page X"** triggers the Python Browser-Use CDP agent to automate all 6 cards through the exact 11 steps.
- At the end of the batch, a dated PDF activity report (`AutomatePinterest_YYYY-MM-DD_X.pdf`) is compiled in `C:\Downloads\AutomatePinterest`.
