# AutomatePinterest — Architecture & Operations Manual

## 1. Overview
**AutomatePinterest** is an automated web agent engine built with **Python FastAPI**, **Browser-Use (CDP Framework)**, and **React + TypeScript + MUI** that automates repinning Amazon deal cards from WorldNewzs into Pinterest boards under the **Dhanvi Collections** account (`ganeshkumardevarasetty`).

---

## 2. Core 11-Step Automation Process
For every product deal on every selected page:
1. **Navigate Deals URL**: Confirm `https://worldnewzs.in/amazon-products`.
2. **Select Deal Card**: Extract 6 deal cards for the active page.
3. **Open Pin Creation**: Open Pinterest Pin Creation URL (`https://www.pinterest.com/pin/create/button/?...`).
4. **Click "Create board"**: Trigger board creation modal.
5. **Truncate Title (50 chars)**: Strictly truncate title to **maximum 50 characters** (hard cut).
6. **Paste to Board Name**: Type truncated title into board name input.
7. **Add Collaborators**: Dynamically auto-discover and select all connected Pinterest account collaborators (e.g. `Kousi Devarasetty`, `LuxeLace`, `Tarun sales`, and any newly added users).
8. **Create Board & "See it"**: Click "Create" board and handle "See it now".
9. **Click Red "Save" Pin**: Click red pin save button.
10. **Strict Verify Save State**: Verify Save button transitions from red to **dark grey disabled ("Saved" state)** or receives toast confirmation.
11. **Close Tab & Next Card**: Close Pinterest tab, return to deals, and process next card.

---

## 3. Technology Stack
* **Backend**: Python 3.13, FastAPI, Uvicorn, Browser-Use, Playwright Python, ReportLab, SSE-Starlette.
* **Frontend**: React 18, TypeScript, Vite, Material UI (MUI), Axios, Lazy Loading (`React.lazy` + `Suspense`).
* **Reports**: ReportLab generating dated PDF reports (`AutomatePinterest_YYYY-MM-DD_X.pdf`) in `C:\Downloads\AutomatePinterest`.

---

## 4. Running the Application
```bash
# Start FastAPI backend & production frontend
npm start

# Access the dashboard
http://localhost:3001
```
