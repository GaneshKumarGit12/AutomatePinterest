import os
import shutil
import subprocess
import asyncio
from typing import Optional, Any

try:
    from playwright.async_api import async_playwright, BrowserContext, Page
except ImportError:
    async_playwright = None  # type: ignore
    BrowserContext = Any  # type: ignore
    Page = Any  # type: ignore

USER_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "user_data", "automation_session"))

_playwright_instance = None
_persistent_context: Optional[BrowserContext] = None


def kill_stale_automation_processes():
    """Kills any orphaned background msedge/chromium processes holding locks."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*automation_session*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def clean_stale_lockfiles(data_dir: str):
    """Removes Chromium ProcessSingleton lock files to prevent startup crash."""
    os.makedirs(data_dir, exist_ok=True)
    for fname in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
        fpath = os.path.join(data_dir, fname)
        if os.path.exists(fpath):
            try:
                if os.path.isdir(fpath):
                    shutil.rmtree(fpath, ignore_errors=True)
                else:
                    os.remove(fpath)
            except Exception:
                pass


async def get_browser_context() -> BrowserContext:
    """Launches or returns the headful persistent browser context with multi-tier fallback."""
    global _playwright_instance, _persistent_context

    if _persistent_context:
        try:
            if len(_persistent_context.pages) > 0:
                return _persistent_context
        except Exception:
            _persistent_context = None

    kill_stale_automation_processes()
    clean_stale_lockfiles(USER_DATA_DIR)

    if not _playwright_instance:
        _playwright_instance = await async_playwright().start()

    launch_args = [
        "--start-maximized",
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-infobars",
    ]

    # Attempt 1: Native Edge persistent profile
    try:
        _persistent_context = await _playwright_instance.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="msedge",
            headless=False,
            viewport=None,
            slow_mo=80,
            ignore_default_args=["--enable-automation"],
            args=launch_args,
        )
        _persistent_context.set_default_timeout(15000)
        _persistent_context.set_default_navigation_timeout(60000)
        return _persistent_context
    except Exception as e1:
        print(f"[Session] Attempt 1 failed (Edge persistent): {e1}")

    # Attempt 2: Chromium persistent profile
    try:
        fresh_dir = os.path.join(USER_DATA_DIR, "fresh_profile")
        clean_stale_lockfiles(fresh_dir)
        _persistent_context = await _playwright_instance.chromium.launch_persistent_context(
            user_data_dir=fresh_dir,
            headless=False,
            viewport=None,
            slow_mo=80,
            ignore_default_args=["--enable-automation"],
            args=launch_args,
        )
        _persistent_context.set_default_timeout(15000)
        _persistent_context.set_default_navigation_timeout(60000)
        return _persistent_context
    except Exception as e2:
        print(f"[Session] Attempt 2 failed (Chromium persistent): {e2}")

    # Attempt 3: Standard headful browser launch (guaranteed success)
    try:
        browser = await _playwright_instance.chromium.launch(
            headless=False,
            slow_mo=80,
            args=launch_args,
        )
        _persistent_context = await browser.new_context(viewport=None)
        _persistent_context.set_default_timeout(15000)
        _persistent_context.set_default_navigation_timeout(60000)
        return _persistent_context
    except Exception as e3:
        print(f"[Session] Attempt 3 failed (Standard browser): {e3}")
        raise e3


async def close_browser_context():
    """Closes active persistent context cleanly."""
    global _persistent_context, _playwright_instance
    if _persistent_context:
        try:
            await _persistent_context.close()
        except Exception:
            pass
        _persistent_context = None

    if _playwright_instance:
        try:
            await _playwright_instance.stop()
        except Exception:
            pass
        _playwright_instance = None


def launch_native_edge_login():
    """Launches native Microsoft Edge process on desktop to Pinterest login."""
    try:
        subprocess.Popen(["powershell", "-Command", "Start-Process msedge 'https://www.pinterest.com/login'"])
    except Exception as e:
        print(f"[Session] Error launching Edge login: {e}")


async def check_is_owner_authenticated(page: Page) -> bool:
    """Checks if current page has an active authenticated owner session."""
    try:
        res = await page.evaluate(
            """() => {
                const hasLoginBtn = Array.from(document.querySelectorAll('button, a')).some(el => {
                    const txt = (el.textContent || '').trim().toLowerCase();
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    const href = (el.getAttribute('href') || '').toLowerCase();
                    return txt === 'log in' || aria === 'log in' || href.includes('/login') || el.getAttribute('data-test-id') === 'simple-login-button';
                });
                const hasHeaderProfile = !!document.querySelector(
                    '[data-test-id="header-profile"], [aria-label*="profile" i], [data-test-id="saved-tab"]'
                );
                const hasFollowBtn = Array.from(document.querySelectorAll('button, div[role="button"]')).some(el => {
                    const txt = (el.textContent || '').trim().toLowerCase();
                    return txt === 'follow';
                });

                return hasHeaderProfile && !hasLoginBtn && !hasFollowBtn;
            }"""
        )
        return bool(res)
    except Exception:
        return False


async def ensure_pinterest_authenticated(context: BrowserContext, page: Optional[Page] = None) -> bool:
    """Ensures Pinterest owner session is active, performing automated credential login if needed."""
    email = os.environ.get("PINTEREST_EMAIL", "ganeshkumard56@gmail.com")
    password = os.environ.get("PINTEREST_PASSWORD", "")
    target_page = page or (context.pages[0] if context.pages else await context.new_page())
    await target_page.bring_to_front()

    # Check if already authenticated on Pinterest
    current_url = getattr(target_page, "url", "")
    if "pinterest.com" not in current_url:
        await target_page.goto("https://in.pinterest.com/ganeshkumardevarasetty/_saved/", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2.5)

    if await check_is_owner_authenticated(target_page):
        return True

    print(f"[Session Manager] Authenticating Pinterest session for {email}...")
    await target_page.goto("https://www.pinterest.com/login/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(2.5)

    if await check_is_owner_authenticated(target_page):
        return True

    # Fill email
    try:
        email_sel = 'input[id="email"], input[name="id"], input[type="email"]'
        email_field = await target_page.wait_for_selector(email_sel, timeout=8000)
        if email_field:
            try:
                await email_field.click(timeout=5000, force=True)
            except Exception:
                await target_page.evaluate('(el) => el.focus()', email_field)
            await email_field.fill("")
            await email_field.type(email, delay=35)
            await asyncio.sleep(0.4)

        # Fill password
        pass_sel = 'input[id="password"], input[name="password"], input[type="password"]'
        pass_field = await target_page.wait_for_selector(pass_sel, timeout=8000)
        if pass_field and password:
            try:
                await pass_field.click(timeout=5000, force=True)
            except Exception:
                await target_page.evaluate('(el) => el.focus()', pass_field)
            await pass_field.fill("")
            await pass_field.type(password, delay=35)
            await asyncio.sleep(0.4)

            # Submit
            submit_sel = 'button[type="submit"], [data-test-id="registerFormSubmitButton"]'
            submit_btn = await target_page.query_selector(submit_sel)
            if submit_btn:
                try:
                    await target_page.evaluate('(el) => el.click()', submit_btn)
                except Exception:
                    await submit_btn.click(timeout=5000, force=True)
            else:
                await pass_field.press("Enter")

        # Wait for authentication to resolve
        await asyncio.sleep(3.5)
        for _ in range(12):
            if await check_is_owner_authenticated(target_page):
                print("[Session Manager] Owner session successfully authenticated and verified!")
                return True
            if "/login" not in target_page.url:
                profile_elem = await target_page.query_selector('[data-test-id="header-profile"], [aria-label*="profile" i]')
                if profile_elem:
                    print("[Session Manager] Authenticated via redirect!")
                    return True
            await asyncio.sleep(1.5)

    except Exception as e:
        print(f"[Session Manager] Login attempt note: {e}")

    return await check_is_owner_authenticated(target_page)
