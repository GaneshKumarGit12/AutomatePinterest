import os
import shutil
import subprocess
import asyncio
from typing import Optional, Any, Dict, List

try:
    from playwright.async_api import async_playwright, BrowserContext, Page
except ImportError:
    async_playwright = None  # type: ignore
    BrowserContext = Any  # type: ignore
    Page = Any  # type: ignore

USER_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "user_data", "automation_session"))
SESSIONS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "user_data", "sessions"))

_playwright_instance = None
_persistent_context: Optional[BrowserContext] = None
_persistent_contexts: Dict[str, Any] = {}


def get_session_dir(session_name: Optional[str] = None) -> str:
    """
    Resolves persistent user data dir. Default and Facebook accounts share
    USER_DATA_DIR (automation_session) so existing logins remain active.
    Instagram and Threads use dedicated isolated subdirectories.
    """
    if not session_name:
        return USER_DATA_DIR
    s_low = str(session_name).replace("-", "_").lower()
    if s_low in ["default", "automation_session", "facebook_shared", "facebook_main", "worldnewzs", "latestnews", "facebook_group"]:
        return USER_DATA_DIR
    if "insta" in s_low:
        session_dir = os.path.join(SESSIONS_ROOT, "product_insta")
    elif "thread" in s_low:
        session_dir = os.path.join(SESSIONS_ROOT, "product_threads")
    else:
        clean_name = "".join(c for c in session_name if c.isalnum() or c in ("-", "_")).lower()
        session_dir = os.path.join(SESSIONS_ROOT, clean_name)
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


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


def get_proxy_config() -> Optional[Dict[str, str]]:
    """
    Parses residential or custom proxy settings from environment variables.
    Supports PROXY_SERVER, RESIDENTIAL_PROXY_URL, or PROXY_USERNAME + PROXY_PASSWORD.
    Accepts standard formats: http://host:port, http://user:pass@host:port, or socks5://...
    """
    raw = os.environ.get("PROXY_SERVER") or os.environ.get("RESIDENTIAL_PROXY_URL") or os.environ.get("PROXY_URL")
    if not raw:
        return None

    raw = raw.strip()
    user = os.environ.get("PROXY_USERNAME", "")
    pwd = os.environ.get("PROXY_PASSWORD", "")

    # Check if user:pass is embedded in the URL
    if "@" in raw:
        try:
            from urllib.parse import urlparse
            p = urlparse(raw)
            server = f"{p.scheme}://{p.hostname}:{p.port}"
            username = p.username or user
            password = p.password or pwd
            cfg = {"server": server}
            if username:
                cfg["username"] = username
            if password:
                cfg["password"] = password
            return cfg
        except Exception:
            return {"server": raw}

    cfg = {"server": raw}
    if user:
        cfg["username"] = user
    if pwd:
        cfg["password"] = pwd
    return cfg


STEALTH_EVASION_SCRIPT = """
(() => {
    // 1. Mask navigator.webdriver
    try {
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true,
        });
    } catch (_) {}

    // 2. Mock chrome.runtime
    try {
        if (!window.chrome) {
            window.chrome = {};
        }
        if (!window.chrome.runtime) {
            window.chrome.runtime = {
                id: 'aapbdbdomjkkjkaonfhkkikfgjllcleb',
                connect: () => {},
                sendMessage: () => {},
            };
        }
    } catch (_) {}

    // 3. Emulate standard languages
    try {
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
            configurable: true,
        });
    } catch (_) {}

    // 4. Emulate realistic plugins count
    try {
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
            configurable: true,
        });
    } catch (_) {}

    // 5. Mask permissions query
    try {
        const origQuery = navigator.permissions && navigator.permissions.query;
        if (origQuery) {
            navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : origQuery(parameters);
        }
    } catch (_) {}
})();
"""


async def get_active_ip_info() -> Dict[str, Any]:
    """Checks public egress IP address and residential proxy status."""
    proxy_cfg = get_proxy_config()
    info = {
        "hasProxy": bool(proxy_cfg),
        "enabled": bool(proxy_cfg),
        "proxyServer": proxy_cfg.get("server") if proxy_cfg else None,
        "server": proxy_cfg.get("server") if proxy_cfg else None,
        "isResidential": bool(os.environ.get("RESIDENTIAL_PROXY_URL") or os.environ.get("PROXY_SERVER")),
    }
    try:
        import urllib.request
        import json
        req = urllib.request.Request(
            "https://api.ipify.org?format=json",
            headers={"User-Agent": "AutomatePinterest/2.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode("utf-8"))
            ip_val = data.get("ip")
            info["currentIp"] = ip_val
            info["egressIp"] = ip_val
    except Exception as e:
        info["currentIp"] = "Direct"
        info["egressIp"] = "Direct"
        info["note"] = str(e)
    return info


async def get_browser_context(session_name: Optional[str] = None) -> BrowserContext:
    """Launches or returns the headful persistent browser context with multi-tier fallback, proxy, and stealth."""
    global _playwright_instance, _persistent_context, _persistent_contexts

    data_dir = get_session_dir(session_name)

    # Check cached context for this session data_dir
    existing_ctx = _persistent_contexts.get(data_dir)
    if existing_ctx:
        try:
            if len(existing_ctx.pages) > 0:
                if not session_name or session_name in ["default", "automation_session", "facebook_shared"]:
                    _persistent_context = existing_ctx
                return existing_ctx
        except Exception:
            _persistent_contexts.pop(data_dir, None)
            if _persistent_context == existing_ctx:
                _persistent_context = None

    if not session_name or session_name in ["default", "automation_session", "facebook_shared"]:
        if _persistent_context:
            try:
                if len(_persistent_context.pages) > 0:
                    _persistent_contexts[data_dir] = _persistent_context
                    return _persistent_context
            except Exception:
                _persistent_context = None

    kill_stale_automation_processes()
    clean_stale_lockfiles(data_dir)

    if not _playwright_instance:
        _playwright_instance = await async_playwright().start()

    proxy_cfg = get_proxy_config()
    if proxy_cfg:
        print(f"[Session Manager] 🛡️ Routing browser traffic through Proxy: {proxy_cfg.get('server')}")

    launch_args = [
        "--start-maximized",
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-infobars",
    ]

    # Attempt 1: Native Edge persistent profile
    try:
        launch_kwargs = {
            "user_data_dir": data_dir,
            "channel": "msedge",
            "headless": False,
            "viewport": None,
            "slow_mo": 80,
            "ignore_default_args": ["--enable-automation"],
            "args": launch_args,
        }
        if proxy_cfg:
            launch_kwargs["proxy"] = proxy_cfg

        ctx = await _playwright_instance.chromium.launch_persistent_context(**launch_kwargs)
        ctx.set_default_timeout(15000)
        ctx.set_default_navigation_timeout(60000)
        try:
            await ctx.add_init_script(STEALTH_EVASION_SCRIPT)
        except Exception:
            pass
        _persistent_contexts[data_dir] = ctx
        if not session_name or session_name in ["default", "automation_session", "facebook_shared"]:
            _persistent_context = ctx
        return ctx
    except Exception as e1:
        print(f"[Session] Attempt 1 failed (Edge persistent for {os.path.basename(data_dir)}): {e1}")

    # Attempt 2: Chromium persistent profile
    try:
        fresh_dir = os.path.join(data_dir, "fresh_profile")
        clean_stale_lockfiles(fresh_dir)
        launch_kwargs2 = {
            "user_data_dir": fresh_dir,
            "headless": False,
            "viewport": None,
            "slow_mo": 80,
            "ignore_default_args": ["--enable-automation"],
            "args": launch_args,
        }
        if proxy_cfg:
            launch_kwargs2["proxy"] = proxy_cfg

        ctx = await _playwright_instance.chromium.launch_persistent_context(**launch_kwargs2)
        ctx.set_default_timeout(15000)
        ctx.set_default_navigation_timeout(60000)
        try:
            await ctx.add_init_script(STEALTH_EVASION_SCRIPT)
        except Exception:
            pass
        _persistent_contexts[data_dir] = ctx
        if not session_name or session_name in ["default", "automation_session", "facebook_shared"]:
            _persistent_context = ctx
        return ctx
    except Exception as e2:
        print(f"[Session] Attempt 2 failed (Chromium persistent for {os.path.basename(data_dir)}): {e2}")

    # Attempt 3: Standard headful browser launch (guaranteed success)
    try:
        launch_kwargs3 = {
            "headless": False,
            "slow_mo": 80,
            "args": launch_args,
        }
        if proxy_cfg:
            launch_kwargs3["proxy"] = proxy_cfg

        browser = await _playwright_instance.chromium.launch(**launch_kwargs3)
        context_kwargs = {"viewport": None}
        if proxy_cfg:
            context_kwargs["proxy"] = proxy_cfg
        ctx = await browser.new_context(**context_kwargs)
        ctx.set_default_timeout(15000)
        ctx.set_default_navigation_timeout(60000)
        try:
            await ctx.add_init_script(STEALTH_EVASION_SCRIPT)
        except Exception:
            pass
        _persistent_contexts[data_dir] = ctx
        if not session_name or session_name in ["default", "automation_session", "facebook_shared"]:
            _persistent_context = ctx
        return ctx
    except Exception as e3:
        print(f"[Session] Attempt 3 failed (Standard browser): {e3}")
        raise e3


async def close_browser_context(session_name: Optional[str] = None):
    """Closes active persistent context cleanly."""
    global _persistent_context, _playwright_instance, _persistent_contexts
    if session_name:
        data_dir = get_session_dir(session_name)
        ctx = _persistent_contexts.pop(data_dir, None)
        if ctx:
            try:
                await ctx.close()
            except Exception:
                pass
        if _persistent_context == ctx:
            _persistent_context = None
    else:
        for d_dir, ctx in list(_persistent_contexts.items()):
            try:
                await ctx.close()
            except Exception:
                pass
        _persistent_contexts.clear()
        if _persistent_context:
            try:
                await _persistent_context.close()
            except Exception:
                pass
            _persistent_context = None

    if len(_persistent_contexts) == 0 and _playwright_instance:
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
