---
name: runapplication
description: Runs, manages, and terminates the AutomatePinterest full-stack application (FastAPI backend on port 3001 serving the React Vite production frontend). Use this skill whenever the user says "run application", "start the app", "launch application", "run npm start", "exit application", "stop application", or asks to run/restart/stop the AutomatePinterest service.
compatibility: Windows pwsh shell, Python venv with uvicorn, Node.js with npm.
---

# Run Application Skill

Instructions for launching, monitoring, and cleanly exiting the AutomatePinterest application.

## Overview
AutomatePinterest runs as a unified full-stack server on port `3001`:
- **Backend**: FastAPI (`backend/main.py`) powered by Uvicorn.
- **Frontend**: React + TypeScript + MUI bundle compiled in `dist/` and mounted statically at `/` by FastAPI.

---

## 1. Procedure to Run the Application

### Step 1: Check and Free Port 3001 (if occupied)
If port 3001 is already held by an orphaned process:
```powershell
powershell -Command "Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
```

### Step 2: Start the Application as a Daemon
Execute `npm start` with `IsDaemon=true` in `c:\AutomatePinterest`:
```bash
npm start
```
This runs:
```powershell
.\venv\Scripts\uvicorn.exe backend.main:app --port 3001 --host 0.0.0.0
```

### Step 3: Verify the Server is Healthy
Wait 2-3 seconds for Uvicorn to initialize, then verify:
1. Port 3001 is listening:
   ```powershell
   Get-NetTCPConnection -LocalPort 3001 -State Listen
   ```
2. HTTP endpoint returns status 200:
   - Dashboard: `http://localhost:3001/`
   - Session Status: `http://localhost:3001/api/social/session-status`
   - Deals API: `http://localhost:3001/api/deals?page=1`

---

## 2. Procedure to Exit / Stop the Application

When the user requests `/runapplication exit application` or asks to stop/terminate the service:

### Step 1: Terminate the Active Server Task / Process
1. If running as a background task, terminate the task using `manage_task(Action='kill', TaskId=...)`.
2. Stop the processes holding port 3001:
   ```powershell
   Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
   ```

### Step 2: Confirm Port 3001 is Free
Verify that no process is listening on port 3001:
```powershell
Get-NetTCPConnection -LocalPort 3001 -State Listen -ErrorAction SilentlyContinue
```
If the command outputs nothing or errors with not found, port 3001 is completely free and shutdown is confirmed.

---

## 3. Known Issues & Troubleshooting Memory

### Issue: `[ERROR] ❌ Failed to open Facebook share popup for Pin <pin_id>`
- **Error Signature**:
  ```text
  [WARNING] Popup open note: Timeout 12000ms exceeded while waiting for event "popup"
  [ERROR] ❌ Failed to open Facebook share popup for Pin <pin_id>.
  ```
- **Root Cause Analysis**:
  1. **Global Selector Scope Bleed**: When scrolling down long Pinterest feeds (`_created/`), using a generic fallback like `pinterest_page.query_selector('button[aria-label="Send"]')` mistakenly matched the profile/board header's "Share profile" button instead of the target pin's Send button. This opened the profile share popover rather than the pin's share popover.
  2. **Card Virtualization**: Pinterest unmounts or virtualizes off-screen DOM nodes. Pin cards must be targeted by their exact attribute `div[data-test-pin-id="{pin_id}"]` and scrolled directly into view using `card.scrollIntoView({ block: 'center' })` before querying child buttons.
  3. **Strict Button Scoping**: The pin's Send button must be queried strictly within the active pin container:
     ```python
     card_sel = f'div[data-test-pin-id="{pin_id}"]'
     send_btn = await card.query_selector('button[aria-label="Send"]')
     ```
  4. **Stale Popover Backdrop**: If a popover was previously opened, pressing `Escape` ensures any lingering popovers or backdrops are cleared before interacting with the next pin.
  5. **Facebook Account Switch / OAuth Handshake**:
     - If the active Facebook session is on a Page profile, Facebook triggers `forced_account_switch`, requiring submission to switch to the personal profile.
     - On first-time connection, Facebook displays an OAuth consent screen (`Continue as...`). Once consent completes and the OAuth popup closes, clicking `button[aria-label="Share on Facebook"]` again immediately opens the real `share_channel/#` post composer with the Pinterest link preview.

### Issue: `Facebook posting error for Pin #X: ElementHandle.click: Element is not attached to the DOM`
- **Error Signature**:
  ```text
  [Pinterest→FB] [ERROR] ❌ Facebook posting error for Pin #5: ElementHandle.click: Element is not attached to the DOM
  Call log:
    - attempting click action
      - waiting for element to be visible, enabled and stable
  ```
- **Root Cause Analysis**:
  1. **Premature ElementHandle Capture**: The composer's `div[role="textbox"]` was previously retrieved as an `ElementHandle` *before* the 8-second image/link preview hydration loop.
  2. **React DOM Remounting**: When Facebook asynchronously receives and renders the Open Graph card (image thumbnail, title, and link card), React completely unmounts and remounts the dialog's composer tree.
  3. **Stale ElementHandle Invalidation**: Attempting to call `.click()` on the pre-hydration `ElementHandle` failed because its underlying DOM node was no longer attached to the document.
- **Solution & Permanent Architecture**:
  1. **Post-Hydration Resolution**: Always query the `div[role="textbox"]` **after** the preview hydration loop has completed and the DOM has stabilized.
  2. **Playwright Locators**: Always use `popup.locator('div[role="textbox"]').first` instead of `ElementHandle`. Locators lazily re-evaluate against the live DOM on each action and auto-retry without stale node errors.
  3. **Resilient Evaluate Fallback**: Wrap clicks with evaluate fallbacks (`tb.focus(); tb.click()`) to directly focus and interact with the composer even if React is actively re-rendering.
  4. **Share Button Protection**: Apply the same locator pattern to the `Share` button with wait-for-enabled polling and evaluate dispatch.

### Issue: `Pinterest 'Share on Facebook' popup posts to Personal Profile / Page Feed instead of Target Facebook Group ('Amazon Affiliate Group')`
- **Error Signature / Observation**:
  - `fb_share_complete_pin_<id>.png` showed the pin posted to the personal profile timeline (`Ganeshkumar Devarasetty`) or Page (`Worldnewzs`), NOT inside the target Facebook group `Amazon Affiliate Group` (`https://www.facebook.com/groups/1761596288324903/`).
- **Root Cause Analysis**:
  1. **Meta `dialog/share` Popup Restriction**: Pinterest's native share button triggers Meta's legacy `https://www.facebook.com/dialog/share` popup. Meta has deprecated group sharing in this endpoint, locking the destination pill to `Feed` (`aria-disabled="true"`). The popup cannot publish directly to Facebook Groups.
  2. **Hidden Messenger Dialog Collision**: Facebook injects a hidden `<div role="dialog" aria-label="Messenger">` into the DOM. Generic selectors like `div[role="dialog"]` match Messenger first, causing a 12-second timeout when looking for composer textboxes or Post buttons.
- **Solution & Permanent Architecture**:
  1. **Direct Group Navigation**: After extracting pin details and link from Pinterest `_created/`, navigate directly to `FB_GROUP_URL` (`https://www.facebook.com/groups/1761596288324903/`).
  2. **Group Post Composer**: Open the group's "Write something..." composer.
  3. **OpenGraph Hydration**: Enter shuffled copy and the Pinterest pin link; wait 5 seconds for Facebook's native OpenGraph crawler to hydrate the rich Pinterest preview card (image, title, domain).
  4. **Messenger Dialog Exclusion**: Always scope locators using `div[role="dialog"]:not([aria-label="Messenger"])` to prevent Messenger collision.
  5. **Direct Publication & Ledger**: Click `Post`, verify composer closure and appearance in the group feed, capture screenshot verification (`verified_fb_group_pin_<id>.png`), and record in `DeduplicationLedger`.

### Issue: `Selected posts are not reflected in Facebook Group 'Amazon Affiliate Group' / All selected posts skipped`
- **Error Signature**:
  ```text
  ⏩ Pin #1 (ID: 472230...) is ALREADY on Facebook. Skipping to next unposted pin...
  Batch Completed! Success: 0/5 | Skipped: 5 | Failed: 0
  ```
- **Root Cause Analysis**:
  1. **Synthetic/Mock Cache Generation**: `harvest_dhanvi_collection_pins` previously generated mock cards combining scraped Amazon product details with old historical `shared_pin_ids`. Because those IDs were already in `shared_pin_ids`, they carried `ON FB` green badges and were rejected by `check_facebook_candidate()`.
  2. **Deduplication Blocking Explicit Manual Selections**: When users specifically check cards in the Facebook Automation Hub and click "Share to Facebook", the backend ran them through the blind unposted deduplication filter, skipping all user-selected pins.
  3. **Facebook Post Button Polymorphism**: Inside the group composer modal, Meta renders the "Post" button either as native `<button>` or `<div role="button">`.
- **Solution & Permanent Architecture**:
  1. **Live Real Pinterest Harvesting**: Populate `dhanvi_pins_cache.json` with genuine pins scraped directly from `in.pinterest.com/ganeshkumardevarasetty/_created/` (real 19-digit pin IDs, real URLs, authentic media, accurate prices).
  2. **Manual Selection Deduplication Override**: When `specific_pin_ids` are passed, bypass duplicate checking and scroll search, and directly process each user-selected pin.
  3. **Polymorphic Post Button Locator**: Use `div[role="dialog"]:not([aria-label="Messenger"]) [role="button"], div[role="dialog"]:not([aria-label="Messenger"]) button` matching exact or regex `"Post"` or `aria-label="Post"`.

