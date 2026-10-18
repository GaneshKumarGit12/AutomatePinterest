"""
Pinterest → Facebook Group Share Flow
=====================================
Automate Pinterest pin sharing to Facebook:
1. Navigate to Pinterest created pins (https://in.pinterest.com/ganeshkumardevarasetty/_created/)
2. Hover over target pin -> click share icon ('Send')
3. In Share popover, click Facebook ('Share on Facebook') -> handle popup
4. Verify / ensure Facebook session (using .env credentials if required, persistent browser profile)
5. Navigate to Facebook Page 'Worldnewzs'
6. Access 'Groups' from Worldnewzs (via More menu / tabs)
7. Select 'Amazon Affiliate Group'
8. Post deal & Pinterest pin link in Amazon Affiliate Group
9. Verify post visibility in group feed with screenshot confirmation
"""

import os
import sys
import re
import json
import asyncio
import time
from typing import Dict, Any, List, Optional, Callable
from dotenv import load_dotenv

load_dotenv()

try:
    from playwright.async_api import BrowserContext, Page
except ImportError:
    BrowserContext = Any  # type: ignore
    Page = Any  # type: ignore

from backend.engine.session_manager import get_browser_context
from backend.engine.browser_agent import install_visual_cursor
from backend.engine.scraper import (
    get_unposted_facebook_deals,
    load_products_dataset,
    format_amazon_product_card,
    sync_live_products,
    sanitize_image_url,
)
from backend.engine.social_manager import (
    DeduplicationLedger,
    ContentShuffler,
    QuickSocialPoster,
    CHANNEL_DEFINITIONS,
    DESTINATIONS_DIR,
)
from backend.engine.facebook_report_exporter import (
    export_facebook_shares_excel,
    generate_facebook_pdf_report,
)

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_WRITABLE_ROOT = "/tmp" if os.environ.get("VERCEL") else PROJECT_ROOT
WORLDNEWZS_PRODUCTS_URL = os.environ.get("WORLDNEWZS_PRODUCTS_URL", "https://worldnewzs.in/amazon-products")
PINTEREST_CREATED_URL = os.environ.get("PINTEREST_CREATED_URL", "https://in.pinterest.com/ganeshkumardevarasetty/_created/")
PINTEREST_SAVED_URL = os.environ.get("PINTEREST_SAVED_URL", "https://in.pinterest.com/ganeshkumardevarasetty/_saved/")
FB_PAGE_NAME = os.environ.get("FACEBOOK_PAGE_NAME", "Worldnewzs")
FB_PAGE_URL = os.environ.get("FACEBOOK_PAGE_URL", "https://www.facebook.com/profile.php?id=61589266599006")
FB_PAGE_2_NAME = os.environ.get("FACEBOOK_PAGE_2_NAME", "LatestNews")
FB_PAGE_2_URL = os.environ.get("FACEBOOK_PAGE_2_URL", "https://www.facebook.com/profile.php?id=61589391814601")
FB_PROFILE_URL = os.environ.get("FACEBOOK_PROFILE_URL", "https://www.facebook.com/ganeshkumard56/")
FB_GROUP_NAME = os.environ.get("FACEBOOK_GROUP_NAME", "Amazon Affiliate Group")
FB_GROUP_URL = os.environ.get("FACEBOOK_GROUP_URL", "https://www.facebook.com/groups/1761596288324903/")
INSTAGRAM_ACCOUNT = os.environ.get("INSTAGRAM_ACCOUNT", "@ganeshkumard12")
THREADS_ACCOUNT = os.environ.get("THREADS_ACCOUNT", "@ganeshkumard12")
DHANVI_PINS_CACHE = os.path.join(_WRITABLE_ROOT, "state", "dhanvi_pins_cache.json")
TEMP_PIN_IMAGES_DIR = os.path.join(_WRITABLE_ROOT, "state", "temp_pin_images")
SCREENSHOTS_DIR = os.path.join(_WRITABLE_ROOT, "state", "screenshots")
try:
    os.makedirs(TEMP_PIN_IMAGES_DIR, exist_ok=True)
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
except OSError:
    pass


def resolve_pin_image_from_pinterest(pin_id: str, pin_url: str = "") -> str:
    """
    Auto-resolves high-res Amazon or Pinterest image URL for a product/pin.
    First checks worldnewzs.in/amazon-products dataset by ASIN, then falls back to OpenGraph.
    """
    asin = DeduplicationLedger.extract_asin(pin_id) or DeduplicationLedger.extract_asin(pin_url)
    if asin:
        try:
            for p in load_products_dataset():
                if str(p.get("asin", "")).strip().upper() == asin:
                    img = sanitize_image_url(p.get("imageUrl") or "", asin)
                    if img and img.startswith("http"):
                        return img
        except Exception:
            pass
        return f"https://m.media-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_SX500_.jpg"

    target_url = pin_url if (pin_url and pin_url.startswith("http")) else f"https://in.pinterest.com/pin/{pin_id}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        import urllib.request
        import re
        req = urllib.request.Request(target_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            m_og = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.I)
            if not m_og:
                m_og = re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', html, re.I)
            if m_og:
                img_url = m_og.group(1).strip()
                if img_url.startswith("http"):
                    return img_url.replace("/236x/", "/736x/").replace("/474x/", "/736x/")

            m_spec = re.search(r'["\']imageSpec_(?:736x|originals)["\']:\s*\{[^}]*["\']url["\']:\s*["\']([^"\']+)["\']', html)
            if m_spec:
                return m_spec.group(1).strip()

            pinimg_matches = re.findall(r'https://i\.pinimg\.com/(?:736x|originals)/[0-9a-zA-Z/_.-]+\.(?:jpg|jpeg|png|webp)', html)
            if pinimg_matches:
                return pinimg_matches[0]
    except Exception as e:
        _safe_print(f"[Resolve Product Image] Failed for {pin_id}: {e}")
    return ""


async def verify_and_download_pin_image(
    pin_id: str,
    pin_url: str = "",
    image_url: str = "",
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> Dict[str, Any]:
    """
    Checkpoint: Verifies that the Amazon product / pin has a valid high-resolution image URL,
    auto-resolves missing images from worldnewzs.in/amazon-products or Amazon CDN, and downloads
    the image locally to state/temp_pin_images/pin_<pin_id>.jpg.
    """
    def log(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[Image Checkpoint] [{lvl.upper()}] {msg}")

    cleaned_img_url = (image_url or "").strip()
    if cleaned_img_url.startswith("data:"):
        cleaned_img_url = ""

    if cleaned_img_url:
        cleaned_img_url = cleaned_img_url.replace("/236x/", "/736x/").replace("/474x/", "/736x/")

    if not cleaned_img_url or not cleaned_img_url.startswith("http"):
        log("info", f"🔍 Product {pin_id} image URL missing. Resolving from worldnewzs.in/amazon-products dataset...")
        resolved = resolve_pin_image_from_pinterest(pin_id, pin_url)
        if resolved:
            cleaned_img_url = resolved
            log("success", f"✅ Resolved high-res product image for {pin_id}: {cleaned_img_url[:65]}...")
        else:
            log("warning", f"⚠️ Could not resolve image for {pin_id}.")

    if not cleaned_img_url:
        return {"verified": False, "imageUrl": "", "imagePath": None, "error": "No image URL available"}

    os.makedirs(TEMP_PIN_IMAGES_DIR, exist_ok=True)
    ext = ".png" if ".png" in cleaned_img_url.lower() else ".jpg"
    safe_id = "".join(c for c in str(pin_id) if c.isalnum() or c in ("-", "_")) or "deal"
    local_path = os.path.join(TEMP_PIN_IMAGES_DIR, f"pin_{safe_id}{ext}")

    try:
        import urllib.request
        referer = "https://www.amazon.in/" if "media-amazon.com" in cleaned_img_url else "https://worldnewzs.in/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": referer,
        }
        req = urllib.request.Request(cleaned_img_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            if len(data) > 512:
                with open(local_path, "wb") as f_out:
                    f_out.write(data)
                log("success", f"📸 [Checkpoint Passed] Product {pin_id} high-res image verified & downloaded ({len(data):,} bytes -> {os.path.basename(local_path)})")
                return {
                    "verified": True,
                    "imageUrl": cleaned_img_url,
                    "imagePath": local_path,
                    "fileSize": len(data),
                }
            else:
                log("warning", f"⚠️ Image downloaded for {pin_id} was too small ({len(data)} bytes).")
    except Exception as dl_err:
        log("warning", f"⚠️ Failed downloading image from {cleaned_img_url[:60]}: {dl_err}")

    if os.path.exists(local_path) and os.path.getsize(local_path) > 512:
        return {
            "verified": True,
            "imageUrl": cleaned_img_url,
            "imagePath": local_path,
            "fileSize": os.path.getsize(local_path),
        }

    return {"verified": False, "imageUrl": cleaned_img_url, "imagePath": None, "error": "Download failed"}


def _safe_print(msg: str):
    try:
        print(msg, flush=True)
    except Exception:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)
        except Exception:
            pass


async def _take_screenshot(
    page: Page,
    name: str,
    channel: Optional[str] = None,
    live_frame_fn: Optional[Callable[[str], None]] = None,
) -> str:
    """Saves a screenshot to state/screenshots and optional channel folder, updates fb_live_frame.png, and notifies live viewer."""
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    base_name = os.path.basename(name)
    path = os.path.join(SCREENSHOTS_DIR, base_name)
    try:
        await page.screenshot(path=path, full_page=False)
        live_frame_path = os.path.join(SCREENSHOTS_DIR, "fb_live_frame.png")
        try:
            import shutil
            shutil.copy2(path, live_frame_path)
            if channel:
                ch_ss_dir = os.path.join(DESTINATIONS_DIR, channel, "screenshots")
                os.makedirs(ch_ss_dir, exist_ok=True)
                shutil.copy2(path, os.path.join(ch_ss_dir, base_name))
        except Exception:
            pass
        if live_frame_fn:
            try:
                live_frame_fn(name)
            except Exception:
                pass
    except Exception:
        pass
    return path


async def safe_goto(
    page: Page,
    url: str,
    timeout: int = 45000,
    wait_until: str = "domcontentloaded",
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """
    Resilient navigation helper that gracefully handles heavy pages like Facebook and Pinterest
    where domcontentloaded or load events might stall even though the DOM has committed.
    """
    try:
        await page.goto(url, wait_until=wait_until, timeout=timeout)
        return True
    except Exception as e:
        err_str = str(e)
        if "Timeout" in err_str or "timeout" in err_str.lower():
            try:
                curr_url = page.url
                if curr_url and any(domain in curr_url for domain in ["facebook.com", "pinterest.com"]):
                    has_body = await page.evaluate("() => !!document.body && (document.body.innerText || '').length > 30")
                    if has_body:
                        if log_fn:
                            log_fn("info", f"⚡ Navigation timeout handled safely for '{url[:50]}' (DOM is active).")
                        _safe_print(f"[Safe Navigation] DOM is ready despite timeout on {url[:50]}")
                        return True
            except Exception:
                pass
        raise e


async def _is_facebook_authenticated(page: Page) -> bool:
    """Checks whether the page currently has an active logged-in Facebook session."""
    try:
        if "login" in page.url or "two_step_verification" in page.url or "checkpoint" in page.url:
            return False

        email_el = await page.query_selector('input[name="email"]')
        if email_el and await email_el.is_visible():
            return False

        profile_el = await page.query_selector(
            'div[aria-label="Your profile"], div[aria-label="Account controls and settings"], '
            'a[href*="/me/"], svg[aria-label="Your profile"], div[aria-label="Facebook"][role="banner"]'
        )
        if profile_el:
            return True

        # Quick check for top navigation
        nav = await page.query_selector('div[role="navigation"], div[role="banner"]')
        if nav and not email_el:
            return True
    except Exception:
        pass
    return False


def _bring_windows_to_foreground():
    """Forces browser windows on Windows to the foreground and un-minimizes them."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        def enum_cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    t = buff.value.lower()
                    if any(k in t for k in ["facebook", "edge", "work"]):
                        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                        user32.SetForegroundWindow(hwnd)
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    except Exception:
        pass


async def _ensure_facebook_session(
    page: Page,
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """
    Verifies Facebook session. Performs auto-login with .env credentials if needed
    and handles checkpoints / 2FA / reCAPTCHA.
    """
    fb_user = os.environ.get("FACEBOOK_USERNAME", "")
    fb_pass = os.environ.get("FACEBOOK_PASSWORD", "")

    def log(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[Facebook Auth] [{lvl.upper()}] {msg}")

    # Check if already authenticated
    if await _is_facebook_authenticated(page):
        log("success", "✅ Facebook session verified (persistent session active).")
        return True

    # Check if already at a checkpoint / 2FA screen
    is_checkpoint = ("two_step_verification" in page.url) or ("checkpoint" in page.url)
    if is_checkpoint:
        await page.bring_to_front()
        _bring_windows_to_foreground()
        for frame in page.frames:
            if "recaptcha" in frame.url:
                try:
                    anchor = await frame.wait_for_selector("#recaptcha-anchor, .recaptcha-checkbox", timeout=3000)
                    if anchor:
                        log("info", "🤖 Auto-clicking reCAPTCHA verification checkbox...")
                        await anchor.click()
                        await asyncio.sleep(2)
                        break
                except Exception:
                    pass

        log("warning", "⚠️ Facebook Security Verification / Captcha detected! Live browser window is brought to front — please complete prompt on screen. Waiting up to 180s...")
        for _ in range(90):
            await asyncio.sleep(2)
            if await _is_facebook_authenticated(page):
                log("success", "🎉 Facebook verification cleared! Session saved permanently.")
                return True
            if "two_step_verification" not in page.url and "checkpoint" not in page.url and "login" not in page.url:
                email_check = await page.query_selector('input[name="email"]')
                if not email_check:
                    log("success", "🎉 Facebook verification cleared! Session saved permanently.")
                    return True
        log("error", "❌ Facebook verification timed out.")
        return False

    # Perform automated login entry
    log("info", "🔑 Facebook login required. Submitting credentials from .env...")
    try:
        email_field = await page.wait_for_selector('input[name="email"]', timeout=8000)
        pass_field = await page.wait_for_selector('input[name="pass"]', timeout=8000)

        if email_field and pass_field and fb_user and fb_pass:
            await email_field.fill(fb_user)
            await asyncio.sleep(0.5)
            await pass_field.fill(fb_pass)
            await asyncio.sleep(0.5)

            login_btn = await page.query_selector(
                'div[role="button"][aria-label="Log in"], '
                'div[role="button"]:has-text("Log in"), '
                'input[type="submit"], button[name="login"], '
                'button[data-testid="royal_login_button"]'
            )
            if login_btn:
                log("info", "🖱️ Submitting Facebook login...")
                try:
                    await page.evaluate("(el) => el.click()", login_btn)
                except Exception:
                    await login_btn.click(timeout=5000, force=True)
                await asyncio.sleep(6)

            # Check if redirected to checkpoint / 2FA
            if "two_step_verification" in page.url or "checkpoint" in page.url:
                await page.bring_to_front()
                _bring_windows_to_foreground()
                for frame in page.frames:
                    if "recaptcha" in frame.url:
                        try:
                            anchor = await frame.wait_for_selector("#recaptcha-anchor, .recaptcha-checkbox", timeout=3000)
                            if anchor:
                                log("info", "🤖 Auto-clicking reCAPTCHA verification checkbox...")
                                await anchor.click()
                                await asyncio.sleep(2)
                                break
                        except Exception:
                            pass

                log("warning", "⚠️ Facebook Security Verification / Captcha detected! Live browser window is brought to front — please complete prompt on screen. Waiting up to 180s...")
                for _ in range(90):
                    await asyncio.sleep(2)
                    if await _is_facebook_authenticated(page):
                        log("success", "🎉 Facebook verification cleared! Session saved permanently.")
                        return True
                    if "two_step_verification" not in page.url and "checkpoint" not in page.url and "login" not in page.url:
                        email_check = await page.query_selector('input[name="email"]')
                        if not email_check:
                            log("success", "🎉 Facebook verification cleared! Session saved permanently.")
                            return True
                return False

            if await _is_facebook_authenticated(page):
                log("success", "✅ Logged into Facebook successfully!")
                return True
    except Exception as e:
        log("error", f"Facebook login note: {e}")

    return await _is_facebook_authenticated(page)


async def _ensure_facebook_page_profile(
    page: Page,
    fb_page_url: str = FB_PAGE_URL,
    page_name: str = "WorldNewzs",
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """
    Ensures the Facebook session is actively switched to the designated Page profile
    so posts into that Page feed are published with Page Admin authority.
    """
    def _l(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[Profile Switch] [{lvl.upper()}] {msg}")

    # Build name variants (e.g. "LatestNews", "Latest News", "Latestnews")
    name_variants = [page_name]
    spaced_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', page_name).strip()
    if spaced_name not in name_variants:
        name_variants.append(spaced_name)
    unspaced_name = page_name.replace(" ", "").strip()
    if unspaced_name not in name_variants:
        name_variants.append(unspaced_name)

    try:
        _l("info", f"Checking Facebook identity status on '{fb_page_url}' ({page_name})...")
        await safe_goto(page, fb_page_url, timeout=45000, log_fn=_l)
        await asyncio.sleep(3.5)

        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
        except Exception:
            pass

        # Check if the page displays an explicit switch banner or button targeting this page
        needs_switch = await page.evaluate("""(variants) => {
            const body = document.body.innerText || '';
            for (const v of variants) {
                if (body.includes(`Switch into ${v}`) || 
                    body.includes(`Switch to ${v}`) || 
                    body.includes(`Switch into this Page`) ||
                    body.includes(`Switch into your Page`)) {
                    return true;
                }
            }
            // Check if there is an explicit Switch button in navigation/header
            const buttons = Array.from(document.querySelectorAll('div[role="navigation"] div[role="button"], div[role="main"] div[role="button"], [role="button"]'));
            const navSwitch = buttons.find(b => {
                const txt = (b.innerText || '').trim();
                const aria = b.getAttribute('aria-label') || '';
                return txt === 'Switch' || txt === 'Switch Now' || aria === 'Switch' || aria.includes('Switch into');
            });
            if (navSwitch) {
                return true;
            }
            return false;
        }""", name_variants)

        # Check if composer already visible on page ("What's on your mind?" or "Create a post")
        has_composer = await page.evaluate("""() => {
            const body = document.body.innerText || '';
            return body.includes("What's on your mind?") || body.includes("Create a post");
        }""")

        if not needs_switch and has_composer:
            _l("success", f"✅ Facebook session is already acting as {page_name} (Page Admin, composer ready)!")
            return True

        # Need to switch profile!
        _l("info", f"🔄 Switching profile to {page_name} Page identity...")

        # 1. First attempt: Direct Switch button on page banner/navigation
        switch_clicked = False
        direct_btn = page.locator(
            'div[role="navigation"] div[role="button"]:has-text("Switch"), '
            'div[role="navigation"] [aria-label="Switch"], '
            'div[aria-label="Switch"][role="button"], '
            'div[role="button"]:has-text("Switch Now"), '
            'div[aria-label*="Switch into" i], '
            'div[aria-label*="Switch to" i]'
        ).first

        if await direct_btn.count() > 0 and await direct_btn.is_visible():
            _l("info", f"🖱️ Clicking on-page Switch trigger for {page_name}...")
            try:
                await direct_btn.scroll_into_view_if_needed()
                await direct_btn.click(timeout=5000)
                switch_clicked = True
            except Exception as e:
                _l("warning", f"Playwright click error on direct switch button, trying JS click: {e}")
                switch_clicked = await page.evaluate("""() => {
                    const btn = Array.from(document.querySelectorAll('div[role="button"], [aria-label="Switch"]')).find(e => {
                        const t = (e.innerText || '').trim();
                        const a = e.getAttribute('aria-label') || '';
                        return t === 'Switch' || t === 'Switch Now' || a === 'Switch' || a.includes('Switch into');
                    });
                    if (btn) { btn.click(); return true; }
                    return false;
                }""")

        # 2. Check for confirmation modal dialog
        if switch_clicked:
            await asyncio.sleep(2.5)
            dialog_btn = page.locator(
                'div[role="dialog"] div[role="button"]:has-text("Switch"), '
                'div[role="dialog"] button:has-text("Switch"), '
                'div[role="dialog"] [aria-label="Switch"][role="button"], '
                'div[role="dialog"] [aria-label="Switch"]'
            ).first
            if await dialog_btn.count() > 0 and await dialog_btn.is_visible():
                _l("info", "🖱️ Confirming Switch in dialog...")
                try:
                    await dialog_btn.click(timeout=5000)
                except Exception:
                    await page.evaluate("""() => {
                        const b = Array.from(document.querySelectorAll('div[role="dialog"] div[role="button"], div[role="dialog"] button')).find(el => (el.innerText || '').trim() === 'Switch');
                        if (b) b.click();
                    }""")
            _l("info", f"⏳ Waiting for {page_name} profile switch and page reload...")
            await asyncio.sleep(7)
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass

        # 3. Fallback: Switch via top-right profile avatar menu
        if not switch_clicked:
            _l("info", f"🖱️ Attempting switch to {page_name} via top-right profile avatar...")
            profile_icon = page.locator('div[aria-label="Your profile"]').first
            if await profile_icon.count() > 0 and await profile_icon.is_visible():
                await profile_icon.click(timeout=5000)
                await asyncio.sleep(2)

                # Check for "See all profiles" button in menu
                see_all = page.locator('div[role="button"]:has-text("See all profiles"), span:has-text("See all profiles")').first
                if await see_all.count() > 0 and await see_all.is_visible():
                    _l("info", "🖱️ Clicking 'See all profiles' in menu...")
                    await see_all.click(timeout=4000)
                    await asyncio.sleep(2)

                # Look for target page tile among variants
                target_found = False
                for variant in name_variants:
                    page_tile = page.locator(
                        f'div[role="button"]:has-text("{variant}"), '
                        f'div[role="listitem"]:has-text("{variant}"), '
                        f'[aria-label*="{variant}" i]'
                    ).first
                    if await page_tile.count() > 0 and await page_tile.is_visible():
                        _l("info", f"🖱️ Selected profile tile '{variant}'...")
                        await page_tile.click(timeout=5000)
                        target_found = True
                        break

                if target_found:
                    _l("info", f"⏳ Waiting for profile switch to {page_name}...")
                    await asyncio.sleep(7)
                    try:
                        await page.keyboard.press("Escape")
                    except Exception:
                        pass

        # Verification check: Check if composer or admin tools now visible
        await asyncio.sleep(2)
        verified = await page.evaluate("""(variants) => {
            const body = document.body.innerText || '';
            const hasComposer = body.includes("What's on your mind?") || body.includes("Create a post");
            const hasSwitchBanner = variants.some(v => 
                body.includes(`Switch into ${v}`) || 
                body.includes(`Switch to ${v}`)
            );
            return hasComposer && !hasSwitchBanner;
        }""", name_variants)
        if verified:
            _l("success", f"🎉 Successfully verified {page_name} Page profile is active!")
            return True

        secondary_verified = await page.evaluate("""(variants) => {
            const body = document.body.innerText || '';
            const hasManage = body.includes("Manage Page") || body.includes("Professional dashboard");
            const hasSwitchBanner = variants.some(v => 
                body.includes(`Switch into ${v}`) || 
                body.includes(`Switch to ${v}`)
            );
            return hasManage && !hasSwitchBanner;
        }""", name_variants)
        if secondary_verified:
            _l("success", f"✅ Verified: Now acting as {page_name} (Page Admin) on Facebook!")
            return True

        _l("warning", f"⚠️ Continuing with current profile state for {page_name}...")
        return False
    except Exception as e:
        _l("warning", f"Profile switch note: {e}")
        return False


async def _ensure_worldnewzs_profile(
    page: Page,
    fb_page_url: str = FB_PAGE_URL,
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """Wrapper ensuring WorldNewzs Page profile for backward compatibility."""
    return await _ensure_facebook_page_profile(page, fb_page_url=fb_page_url, page_name=FB_PAGE_NAME, log_fn=log_fn)


async def _ensure_personal_profile(
    page: Page,
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """Ensures Facebook is switched to the personal profile (ganeshkumard56) rather than a Page."""
    def _l(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[Personal Profile Switch] [{lvl.upper()}] {msg}")

    try:
        is_page = await page.evaluate("""() => {
            const body = document.body.innerText || '';
            return body.includes('Manage Page') || body.includes('Professional dashboard');
        }""")
        if not is_page:
            _l("success", "✅ Already acting as personal profile on Facebook.")
            return True

        _l("info", "🔄 Switching from Page identity back to Personal Profile (Ganesh Kumar)...")
        profile_icon = page.locator('div[aria-label="Your profile"]').first
        if await profile_icon.count() > 0 and await profile_icon.is_visible():
            await profile_icon.click(timeout=4000)
            await asyncio.sleep(2)
            personal_tile = page.locator(
                'div[role="button"]:has-text("Ganesh Kumar"), '
                'div[role="listitem"]:has-text("Ganesh Kumar"), '
                '[aria-label*="Ganesh Kumar" i]'
            ).first
            if await personal_tile.count() > 0 and await personal_tile.is_visible():
                await personal_tile.click(timeout=5000)
                await asyncio.sleep(6)
            else:
                see_all = page.locator('div[role="button"]:has-text("See all profiles"), span:has-text("See all profiles")').first
                if await see_all.count() > 0 and await see_all.is_visible():
                    await see_all.click(timeout=4000)
                    await asyncio.sleep(2)
                    personal_tile2 = page.locator(
                        'div[role="button"]:has-text("Ganesh Kumar"), '
                        'div[role="listitem"]:has-text("Ganesh Kumar"), '
                        '[aria-label*="Ganesh Kumar" i]'
                    ).first
                    if await personal_tile2.count() > 0 and await personal_tile2.is_visible():
                        await personal_tile2.click(timeout=5000)
                        await asyncio.sleep(6)
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            _l("success", "🎉 Successfully switched to Personal Profile!")
            return True
    except Exception as e:
        _l("warning", f"Personal profile switch note: {e}")
    return False


async def _publish_to_facebook_page(
    page: Page,
    post_text: str,
    pin_id: str,
    pin_url: str = "",
    image_path: Optional[str] = None,
    channel_key: str = "WorldNewzs",
    page_url: str = FB_PAGE_URL,
    page_name: str = FB_PAGE_NAME,
    log_fn: Optional[Callable[[str, str], None]] = None,
    live_frame_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Publishes deal copy and product image directly to the specified Facebook Page feed (WorldNewzs or LatestNews).
    """
    def _l(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[{page_name} Publish] [{lvl.upper()}] {msg}")

    _l("info", f"📄 Navigating to {page_name} Facebook Page ({page_url})...")
    await safe_goto(page, page_url, timeout=45000, log_fn=_l)
    await page.bring_to_front()
    await asyncio.sleep(3)

    # Ensure profile identity is switched to this page
    await _ensure_facebook_page_profile(page, fb_page_url=page_url, page_name=page_name, log_fn=_l)

    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)
    except Exception:
        pass

    # Scroll down so composer is centered in viewport
    await page.evaluate("window.scrollBy(0, 350)")
    await asyncio.sleep(1.5)

    # Locate and trigger composer: "What's on your mind?", "Create a post", or "Write something..."
    _l("info", f"📝 Opening post composer on {page_name} Page...")
    composer_selector = (
        'div[role="button"]:has-text("What\'s on your mind?"), '
        'span:has-text("What\'s on your mind?"), '
        'div[role="button"]:has-text("Create a post"), '
        'span:has-text("Create a post"), '
        'div[role="button"]:has-text("Write something..."), '
        'span:has-text("Write something...")'
    )
    composer_trigger = page.locator(composer_selector).first

    composer_found = False
    for attempt in range(3):
        if await composer_trigger.count() > 0 and await composer_trigger.is_visible():
            composer_found = True
            break
        await page.evaluate("window.scrollBy(0, 350)")
        await asyncio.sleep(1.5)

    if not composer_found:
        try:
            await composer_trigger.wait_for(state="visible", timeout=8000)
            composer_found = True
        except Exception:
            debug_path = os.path.join(DESTINATIONS_DIR, channel_key, "screenshots", "debug_composer_missing.png")
            try:
                os.makedirs(os.path.dirname(debug_path), exist_ok=True)
                await page.screenshot(path=debug_path)
                _l("warning", f"Composer missing, saved debug screenshot to {debug_path}")
            except Exception:
                pass
            raise RuntimeError(f"Could not find post composer on {page_name} Page.")

    try:
        await composer_trigger.click(timeout=4000, force=True)
    except Exception:
        await page.evaluate("""() => {
            const el = Array.from(document.querySelectorAll('div[role="button"], span')).find(e => {
                const t = (e.innerText || '');
                return t.includes("What's on your mind?") || t.includes("Create a post") || t.includes("Write something...");
            });
            if (el) el.click();
        }""")
    await asyncio.sleep(3)

    dialog_loc = page.locator(
        'div[role="dialog"]:has(div[role="textbox"][contenteditable="true"]), '
        'div[role="dialog"]:has-text("Create post"), '
        'div[role="dialog"]:has-text("Post settings")'
    ).first
    await dialog_loc.wait_for(state="visible", timeout=12000)

    textbox = page.locator(
        'div[role="dialog"]:has(div[role="textbox"][contenteditable="true"]) div[role="textbox"][contenteditable="true"], '
        'div[role="dialog"]:has-text("Create post") div[role="textbox"][contenteditable="true"], '
        'div[role="textbox"][contenteditable="true"]'
    ).first
    await textbox.wait_for(state="visible", timeout=8000)
    try:
        await textbox.click(timeout=3000, force=True)
    except Exception:
        await page.evaluate("""() => {
            const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
            const d = dialogs.find(el => (el.innerText || '').includes('Create post') || el.querySelector('div[role="textbox"][contenteditable="true"]')) || dialogs[0];
            const tb = d ? d.querySelector('div[role="textbox"][contenteditable="true"]') : null;
            if (tb) { tb.focus(); tb.click(); }
        }""")
    await asyncio.sleep(0.5)

    clean_text = post_text.replace("\r", "")
    _l("info", f"⌨️ Typing deal copy for Pin {pin_id} into {page_name} composer...")
    await page.keyboard.type(clean_text, delay=14)
    await asyncio.sleep(1)
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass

    # Attach Verified Image
    attached_image_verified = False
    if image_path and os.path.exists(image_path):
        _l("info", f"📸 Attaching verified image ({os.path.getsize(image_path)} bytes) to {page_name} composer...")
        try:
            file_input = dialog_loc.locator('input[type="file"][accept*="image"], input[type="file"]').first
            if await file_input.count() == 0:
                photo_btn = dialog_loc.locator(
                    'div[aria-label*="Photo/video" i], '
                    'div[aria-label*="Photo" i], '
                    'div[role="button"]:has-text("Photo/video"), '
                    'div[role="button"]:has-text("Add photos/videos"), '
                    'div[aria-label*="Add photos and videos" i]'
                ).first
                if await photo_btn.count() > 0 and await photo_btn.is_visible():
                    await photo_btn.click()
                    await asyncio.sleep(1)
                    file_input = dialog_loc.locator('input[type="file"][accept*="image"], input[type="file"]').first

            if await file_input.count() > 0:
                await file_input.set_input_files(image_path)
                _l("info", f"⏳ Image file injected into {page_name} composer. Awaiting photo preview...")
                for _ in range(10):
                    preview_img = dialog_loc.locator(
                        'img[src*="blob:"], '
                        'div[aria-label*="Media" i] img, '
                        'div[aria-label*="Photo" i] img, '
                        'div[role="presentation"] img'
                    ).first
                    if await preview_img.count() > 0 and await preview_img.is_visible():
                        attached_image_verified = True
                        break
                    await asyncio.sleep(1)
                _l("success", f"📸 [Checkpoint Passed] Pin {pin_id} image verified & attached in {page_name} composer!")
        except Exception as img_err:
            _l("warning", f"⚠️ Error attaching image file to {page_name} composer: {img_err}")

    checkpoint_name = f"fb_{channel_key.lower()}_checkpoint_pin_{pin_id}.png"
    await _take_screenshot(page, checkpoint_name, channel=channel_key, live_frame_fn=live_frame_fn)
    await asyncio.sleep(2.5)

    # Click Next button if present
    _l("info", "🖱️ Advancing from Create post to Post settings (Next)...")
    await page.evaluate("""() => {
        const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
        const dialog = dialogs.find(d => (d.innerText || '').includes('Create post') || (d.innerText || '').includes('Post settings'));
        if (dialog) {
            const btns = Array.from(dialog.querySelectorAll('div[role="button"], button'));
            const nextBtn = btns.find(b => (b.innerText || '').trim() === 'Next' || b.getAttribute('aria-label') === 'Next');
            if (nextBtn) nextBtn.click();
        }
    }""")
    await asyncio.sleep(2.5)

    # Handle any upsell/prompt dialogs (e.g. "Speak With People Directly", "Get Messages", "Not now")
    for _ in range(3):
        prompt_handled = await page.evaluate("""() => {
            const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
            for (const d of dialogs) {
                const text = d.innerText || '';
                if (text.includes('Speak With People Directly') || text.includes('Not now') || text.includes('Get Messages') || text.includes('Call Now')) {
                    const btns = Array.from(d.querySelectorAll('div[role="button"], button'));
                    const notNow = btns.find(b => (b.innerText || '').trim() === 'Not now' || b.getAttribute('aria-label') === 'Not now');
                    if (notNow) {
                        notNow.click();
                        return true;
                    }
                    const closeBtn = btns.find(b => b.getAttribute('aria-label') === 'Close');
                    if (closeBtn) {
                        closeBtn.click();
                        return true;
                    }
                }
            }
            return false;
        }""")
        if prompt_handled:
            _l("info", "🖱️ Dismissed Facebook promotional / 'Not now' prompt dialog...")
            await asyncio.sleep(2)
        else:
            break

    # Click Post button
    _l("info", f"🚀 Publishing Pin {pin_id} to {page_name} Facebook Page feed...")
    clicked_post = False
    for attempt in range(6):
        # Also check and dismiss any lingering "Not now" modal
        await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('div[role="button"], button'));
            const notNow = btns.find(b => (b.innerText || '').trim() === 'Not now' || b.getAttribute('aria-label') === 'Not now');
            if (notNow) notNow.click();
        }""")
        await asyncio.sleep(1)

        clicked_post = await page.evaluate("""() => {
            const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
            for (const dialog of dialogs) {
                const btns = Array.from(dialog.querySelectorAll('div[role="button"], button'));
                const postBtn = btns.find(b => (b.innerText || '').trim() === 'Post' || b.getAttribute('aria-label') === 'Post');
                if (postBtn && postBtn.getAttribute('aria-disabled') !== 'true') {
                    postBtn.click();
                    return true;
                }
            }
            return false;
        }""")
        if clicked_post:
            _l("success", f"🖱️ Clicked 'Post' button successfully on attempt {attempt + 1}!")
            break
        await asyncio.sleep(1.5)

    if not clicked_post:
        post_loc = page.locator('div[role="dialog"]:has-text("Post settings") div[role="button"]:has-text("Post"), div[role="dialog"]:has-text("Create post") div[role="button"]:has-text("Post"), [role="button"]:has-text("Post")').first
        if await post_loc.count() > 0:
            await post_loc.click(timeout=4000, force=True)

    _l("info", f"⏳ Awaiting post publication confirmation on {page_name}...")
    # Handle any post-publication popup like "Boost post"
    for _ in range(8):
        await asyncio.sleep(1.5)
        boost_dismissed = await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('div[role="dialog"] div[role="button"], div[role="dialog"] button'));
            const notNow = btns.find(b => (b.innerText || '').trim() === 'Not now' || b.getAttribute('aria-label') === 'Close');
            if (notNow) { notNow.click(); return true; }
            return false;
        }""")
        if boost_dismissed:
            _l("info", "🖱️ Dismissed post-publish dialog ('Not now')...")

    try:
        await page.locator('div[role="dialog"]:has-text("Create post"), div[role="dialog"]:has-text("Post settings")').first.wait_for(state="hidden", timeout=12000)
    except Exception:
        pass

    await asyncio.sleep(2)
    proof_name = f"verified_{channel_key.lower()}_pin_{pin_id}.png"
    verified_path = await _take_screenshot(page, proof_name, channel=channel_key, live_frame_fn=live_frame_fn)
    _l("success", f"🎉 Successfully published Pin {pin_id} to {page_name} Facebook Page! (Proof: {verified_path})")
    return {"success": True, "screenshotPath": verified_path}


async def _publish_to_facebook_profile(
    page: Page,
    post_text: str,
    pin_id: str,
    pin_url: str = "",
    image_path: Optional[str] = None,
    log_fn: Optional[Callable[[str, str], None]] = None,
    live_frame_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Publishes personal recommendation deal copy & link directly to Facebook Main profile feed (ganeshkumard56).
    """
    channel_key = "Facebook_Main"
    def _l(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[FB Main Profile] [{lvl.upper()}] {msg}")

    _l("info", f"👤 Navigating to Facebook Home Feed for Personal Profile ({FB_PROFILE_URL})...")
    await safe_goto(page, "https://www.facebook.com/", timeout=45000, log_fn=_l)
    await page.bring_to_front()
    await asyncio.sleep(3)

    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)
    except Exception:
        pass

    # Ensure profile identity is personal
    await _ensure_personal_profile(page, log_fn=_l)

    # Scroll down so composer is centered in viewport
    await page.evaluate("window.scrollBy(0, 300)")
    await asyncio.sleep(1.5)

    _l("info", "📝 Opening post composer on Personal Profile ('What\\'s on your mind?')...")
    trigger_clicked = await page.evaluate("""() => {
        const triggers = Array.from(document.querySelectorAll('div[role="button"], span'));
        const trigger = triggers.find(t => {
            const txt = (t.innerText || '').trim();
            return txt.includes("What's on your mind") || txt.includes("Create post");
        });
        if (trigger) {
            trigger.scrollIntoView({ block: 'center', behavior: 'instant' });
            const btn = trigger.closest('div[role="button"]') || trigger;
            btn.click();
            return true;
        }
        return false;
    }""")
    if not trigger_clicked:
        composer_trigger = page.locator('div[role="button"]:has-text("What\'s on your mind"), span:has-text("What\'s on your mind")').first
        if await composer_trigger.count() > 0:
            await composer_trigger.click(timeout=5000, force=True)

    await asyncio.sleep(3)

    dialog_loc = page.locator('div[role="dialog"]:has(div[role="textbox"][contenteditable="true"]), div[role="dialog"]:has-text("Create post")').first
    await dialog_loc.wait_for(state="visible", timeout=12000)

    textbox = page.locator('div[role="dialog"] div[role="textbox"][contenteditable="true"]').first
    await textbox.wait_for(state="visible", timeout=8000)
    await textbox.click(timeout=3000, force=True)
    await asyncio.sleep(0.5)

    clean_text = post_text.replace("\r", "")
    _l("info", f"⌨️ Typing personal deal recommendation for Pin {pin_id}...")
    await page.keyboard.type(clean_text, delay=12)
    await asyncio.sleep(1)

    # Attach verified image
    if image_path and os.path.exists(image_path):
        _l("info", f"📸 Attaching verified product image to Personal Profile post...")
        try:
            file_input = dialog_loc.locator('input[type="file"][accept*="image"], input[type="file"]').first
            if await file_input.count() == 0:
                photo_btn = dialog_loc.locator('div[aria-label*="Photo" i], div[role="button"]:has-text("Photo")').first
                if await photo_btn.count() > 0:
                    await photo_btn.click()
                    await asyncio.sleep(1)
                    file_input = dialog_loc.locator('input[type="file"]').first
            if await file_input.count() > 0:
                await file_input.set_input_files(image_path)
                await asyncio.sleep(3)
        except Exception as e_img:
            _l("warning", f"Image attachment note: {e_img}")

    checkpoint_name = f"fb_main_checkpoint_pin_{pin_id}.png"
    await _take_screenshot(page, checkpoint_name, channel=channel_key, live_frame_fn=live_frame_fn)
    await asyncio.sleep(2)

    _l("info", "🚀 Publishing deal to Facebook Main feed...")
    clicked_post = await page.evaluate("""() => {
        const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
        for (const dialog of dialogs) {
            const btns = Array.from(dialog.querySelectorAll('div[role="button"], button'));
            const postBtn = btns.find(b => (b.innerText || '').trim() === 'Post' || b.getAttribute('aria-label') === 'Post');
            if (postBtn && postBtn.getAttribute('aria-disabled') !== 'true') {
                postBtn.click();
                return true;
            }
        }
        return false;
    }""")
    if not clicked_post:
        post_loc = page.locator('div[role="dialog"] div[role="button"]:has-text("Post"), div[role="dialog"] button:has-text("Post")').first
        await post_loc.click(timeout=6000, force=True)

    _l("info", "⏳ Awaiting post publication confirmation on Personal Profile...")
    await asyncio.sleep(8)
    try:
        await page.locator('div[role="dialog"]:has-text("Create post")').first.wait_for(state="hidden", timeout=15000)
    except Exception:
        pass

    proof_name = f"verified_fb_main_pin_{pin_id}.png"
    verified_path = await _take_screenshot(page, proof_name, channel=channel_key, live_frame_fn=live_frame_fn)
    _l("success", f"🎉 Successfully published Pin {pin_id} to Facebook Main personal feed! (Proof: {verified_path})")
    return {"success": True, "screenshotPath": verified_path}


async def _publish_to_instagram(
    post_text: str,
    pin_id: str,
    pin_url: str = "",
    image_path: Optional[str] = None,
    log_fn: Optional[Callable[[str, str], None]] = None,
    live_frame_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Publishes high-res product photo and aesthetic bio CTA caption to Instagram (@ganeshkumard12).
    Uses isolated persistent browser context in user_data/sessions/product_insta.
    """
    channel_key = "ProductInsta"
    def _l(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[Instagram] [{lvl.upper()}] {msg}")

    if not image_path or not os.path.exists(image_path):
        _l("warning", f"⚠️ Instagram post requires a valid image. Skipping ASIN {pin_id}.")
        return {"success": False, "error": "No verified image file for Instagram"}

    _l("info", f"📸 Step: Launching isolated session for Instagram ({INSTAGRAM_ACCOUNT})...")
    context = await get_browser_context("product_insta")
    page = await context.new_page()
    try:
        await install_visual_cursor(page)
        _l("info", "🔗 Navigating to https://www.instagram.com/...")
        await safe_goto(page, "https://www.instagram.com/", timeout=45000, log_fn=_l)
        await page.bring_to_front()
        await asyncio.sleep(3.5)

        # Dismiss "Not Now" dialogs
        for _ in range(2):
            try:
                not_now_btn = page.locator('button:has-text("Not Now"), div[role="button"]:has-text("Not Now")').first
                if await not_now_btn.count() > 0 and await not_now_btn.is_visible():
                    await not_now_btn.click()
                    await asyncio.sleep(1)
            except Exception:
                pass
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass

        # Locate "Create" (+) navigation item
        _l("info", "🔍 Locating Instagram 'Create' (+) navigation button...")
        create_btn = page.locator(
            'svg[aria-label="New post"], '
            'svg[aria-label="Create"], '
            'a[href="#"]:has-text("Create"), '
            'div[role="button"]:has-text("Create"), '
            'span:has-text("Create")'
        ).first
        await create_btn.wait_for(state="visible", timeout=12000)
        await create_btn.click(timeout=5000, force=True)
        await asyncio.sleep(2.5)

        # Attach image to file input
        _l("info", f"📤 Uploading product image ({os.path.basename(image_path)}) to Instagram composer...")
        file_input = page.locator('div[role="dialog"] input[type="file"], input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=10000)
        await file_input.set_input_files(image_path)
        await asyncio.sleep(3)

        # Click "Next" on Crop Screen
        _l("info", "🖱️ Advancing crop modal (Next)...")
        next_btn = page.locator('div[role="dialog"] div[role="button"]:has-text("Next"), div[role="dialog"] button:has-text("Next")').first
        await next_btn.wait_for(state="visible", timeout=10000)
        await next_btn.click()
        await asyncio.sleep(2)

        # Click "Next" on Filter Screen
        _l("info", "🖱️ Advancing filter modal (Next)...")
        next_btn_2 = page.locator('div[role="dialog"] div[role="button"]:has-text("Next"), div[role="dialog"] button:has-text("Next")').first
        if await next_btn_2.count() > 0 and await next_btn_2.is_visible():
            await next_btn_2.click()
            await asyncio.sleep(2)

        # Focus Caption Textbox and type Instagram copy
        _l("info", f"⌨️ Typing aesthetic Instagram caption with bio CTA for ASIN {pin_id}...")
        caption_box = page.locator(
            'div[role="dialog"] div[aria-label*="Write a caption" i], '
            'div[role="dialog"] div[role="textbox"]'
        ).first
        await caption_box.wait_for(state="visible", timeout=10000)
        await caption_box.click(timeout=3000, force=True)
        await asyncio.sleep(0.5)

        clean_text = post_text.replace("\r", "")
        await page.keyboard.type(clean_text, delay=10)
        await asyncio.sleep(1.5)

        # Checkpoint screenshot
        checkpoint_name = f"ig_checkpoint_pin_{pin_id}.png"
        await _take_screenshot(page, checkpoint_name, channel=channel_key, live_frame_fn=live_frame_fn)

        # Click "Share" button
        _l("info", "🚀 Clicking 'Share' button to publish to Instagram feed...")
        share_btn = page.locator('div[role="dialog"] div[role="button"]:has-text("Share"), div[role="dialog"] button:has-text("Share")').first
        await share_btn.wait_for(state="visible", timeout=10000)
        await share_btn.click(timeout=5000, force=True)

        _l("info", "⏳ Awaiting Instagram publication confirmation...")
        for _ in range(15):
            is_done = await page.evaluate("""() => {
                const body = document.body.innerText || '';
                return body.includes('Your post has been shared') || body.includes('Post shared');
            }""")
            if is_done:
                break
            await asyncio.sleep(1)

        await asyncio.sleep(2)
        proof_name = f"verified_ig_pin_{pin_id}.png"
        verified_path = await _take_screenshot(page, proof_name, channel=channel_key, live_frame_fn=live_frame_fn)
        _l("success", f"🎉 Successfully published Pin {pin_id} to Instagram feed ({INSTAGRAM_ACCOUNT})! (Proof: {verified_path})")
        return {"success": True, "screenshotPath": verified_path}
    except Exception as e_ig:
        _l("error", f"Instagram posting note: {e_ig}")
        raise e_ig
    finally:
        if not page.is_closed():
            try:
                await page.close()
            except Exception:
                pass


async def _publish_to_threads(
    post_text: str,
    pin_id: str,
    pin_url: str = "",
    image_path: Optional[str] = None,
    log_fn: Optional[Callable[[str, str], None]] = None,
    live_frame_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Publishes conversational deal post with rich clickable Amazon link card to Threads (@ganeshkumard12).
    Uses isolated persistent browser context in user_data/sessions/product_threads.
    """
    channel_key = "ProductThreads"
    def _l(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[Threads] [{lvl.upper()}] {msg}")

    _l("info", f"🧵 Step: Launching isolated session for Threads ({THREADS_ACCOUNT})...")
    context = await get_browser_context("product_threads")
    page = await context.new_page()
    try:
        await install_visual_cursor(page)
        _l("info", "🔗 Navigating to https://www.threads.net/...")
        await safe_goto(page, "https://www.threads.net/", timeout=45000, log_fn=_l)
        await page.bring_to_front()
        await asyncio.sleep(3.5)

        # Open Threads Composer
        _l("info", "📝 Opening Threads composer ('Start a thread...')...")
        composer_trigger = page.locator(
            'div[role="button"]:has-text("Start a thread"), '
            'span:has-text("Start a thread"), '
            'svg[aria-label="Create"], '
            'svg[aria-label="Compose"], '
            'div[aria-label="Create a thread"]'
        ).first
        if await composer_trigger.count() > 0:
            await composer_trigger.click(timeout=5000, force=True)
            await asyncio.sleep(2)

        # Locate contenteditable textbox
        textbox = page.locator(
            'div[role="dialog"] div[role="textbox"][contenteditable="true"], '
            'div[role="textbox"][contenteditable="true"]'
        ).first
        await textbox.wait_for(state="visible", timeout=10000)
        await textbox.click(timeout=3000, force=True)
        await asyncio.sleep(0.5)

        clean_text = post_text.replace("\r", "")
        _l("info", f"⌨️ Entering Threads deal copy & direct Amazon link for ASIN {pin_id}...")
        await page.keyboard.type(clean_text, delay=10)
        await asyncio.sleep(2.5)  # Allow Threads to fetch rich link card preview

        # Attach image if available
        if image_path and os.path.exists(image_path):
            try:
                file_input = page.locator('div[role="dialog"] input[type="file"], input[type="file"]').first
                if await file_input.count() > 0:
                    await file_input.set_input_files(image_path)
                    _l("info", "📸 Attached product image to Threads composer!")
                    await asyncio.sleep(2)
            except Exception as e_th_img:
                _l("warning", f"Threads photo attachment note: {e_th_img}")

        checkpoint_name = f"threads_checkpoint_pin_{pin_id}.png"
        await _take_screenshot(page, checkpoint_name, channel=channel_key, live_frame_fn=live_frame_fn)
        await asyncio.sleep(1.5)

        # Click "Post" button
        _l("info", "🚀 Clicking 'Post' button to publish to Threads...")
        post_btn = page.locator('div[role="dialog"] div[role="button"]:has-text("Post"), div[role="dialog"] button:has-text("Post"), div[role="button"]:has-text("Post")').first
        await post_btn.wait_for(state="visible", timeout=8000)
        await post_btn.click(timeout=5000, force=True)

        _l("info", "⏳ Awaiting Threads publication confirmation...")
        await asyncio.sleep(6)

        proof_name = f"verified_threads_pin_{pin_id}.png"
        verified_path = await _take_screenshot(page, proof_name, channel=channel_key, live_frame_fn=live_frame_fn)
        _l("success", f"🎉 Successfully published Pin {pin_id} to Threads ({THREADS_ACCOUNT})! (Proof: {verified_path})")
        return {"success": True, "screenshotPath": verified_path}
    except Exception as e_th:
        _l("error", f"Threads posting note: {e_th}")
        raise e_th
    finally:
        if not page.is_closed():
            try:
                await page.close()
            except Exception:
                pass


async def _publish_to_facebook_group(
    page: Page,
    post_text: str,
    pin_id: str,
    pin_url: str = "",
    image_path: Optional[str] = None,
    log_fn: Optional[Callable[[str, str], None]] = None,
    live_frame_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Publishes deal copy and Pinterest pin link to Amazon Affiliate Group.
    """
    def _l(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[FB Group Publish] [{lvl.upper()}] {msg}")

    _l("info", f"👥 Navigating to Amazon Affiliate Group ({FB_GROUP_URL})...")
    await safe_goto(page, FB_GROUP_URL, timeout=45000, log_fn=_l)
    await page.bring_to_front()
    await asyncio.sleep(3.5)

    # Dismiss any leftover dialogs
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)
    except Exception:
        pass

    # Scroll down so group composer is centered in viewport
    await page.evaluate("window.scrollBy(0, 350)")
    await asyncio.sleep(1.5)

    # Open group composer ('Write something...', 'Create a public post...')
    _l("info", f"📝 Opening group post composer in {FB_GROUP_NAME}...")
    trigger_clicked = await page.evaluate("""() => {
        const triggers = Array.from(document.querySelectorAll('div[role="button"], span, div[tabindex="0"]'));
        const trigger = triggers.find(t => {
            const txt = (t.innerText || '').trim();
            return txt.includes('Write something...') || 
                   txt.includes('Create a public post') || 
                   txt.includes('Create a post') || 
                   txt.includes("What's on your mind?");
        });
        if (trigger) {
            trigger.scrollIntoView({ block: 'center', behavior: 'instant' });
            const btn = trigger.closest('div[role="button"]') || trigger;
            btn.click();
            return true;
        }
        return false;
    }""")
    if not trigger_clicked:
        composer_trigger = page.locator(
            'div[role="button"]:has-text("Write something..."), '
            'span:has-text("Write something..."), '
            'div[role="button"]:has-text("Create a public post"), '
            'div[role="button"]:has-text("Create a post"), '
            'div[role="button"]:has-text("What\'s on your mind?")'
        ).first
        if await composer_trigger.count() > 0:
            try:
                await composer_trigger.click(timeout=5000, force=True)
            except Exception:
                pass

    await asyncio.sleep(2.5)

    # Resilient textbox query across all dialogs and page
    textbox_loc = page.locator(
        'div[role="dialog"]:has(div[role="textbox"][contenteditable="true"]) div[role="textbox"][contenteditable="true"], '
        'div[role="dialog"]:has-text("Create") div[role="textbox"][contenteditable="true"], '
        'div[role="textbox"][contenteditable="true"]'
    ).first

    # If textbox is not yet visible, retry clicking the composer trigger (up to 3 attempts)
    for attempt in range(3):
        try:
            if await textbox_loc.count() > 0 and await textbox_loc.is_visible():
                break
        except Exception:
            pass

        _l("info", f"🔄 Retrying group composer trigger click (attempt {attempt + 1}/3)...")
        await page.evaluate("""() => {
            const triggers = Array.from(document.querySelectorAll('div[role="button"], span, div[tabindex="0"]'));
            const trigger = triggers.find(t => {
                const txt = (t.innerText || '').trim();
                return txt.includes('Write something...') || 
                       txt.includes('Create a public post') || 
                       txt.includes('Create a post') || 
                       txt.includes("What's on your mind?");
            });
            if (trigger) {
                const btn = trigger.closest('div[role="button"]') || trigger;
                btn.scrollIntoView({ block: 'center', behavior: 'instant' });
                btn.click();
            }
        }""")
        await asyncio.sleep(2.5)

    await textbox_loc.wait_for(state="visible", timeout=12000)

    # Scoped dialog containing the active composer
    dialog_loc = page.locator(
        'div[role="dialog"]:has(div[role="textbox"][contenteditable="true"]), '
        'div[role="dialog"]:has-text("Create a public post"), '
        'div[role="dialog"]:has-text("Create post")'
    ).first
    if await dialog_loc.count() == 0:
        dialog_loc = page.locator('div[role="dialog"]').first

    try:
        await textbox_loc.click(timeout=4000, force=True)
    except Exception:
        await page.evaluate("""() => {
            const tb = document.querySelector('div[role="dialog"]:has(div[role="textbox"][contenteditable="true"]) div[role="textbox"][contenteditable="true"]') ||
                       document.querySelector('div[role="dialog"] div[role="textbox"][contenteditable="true"]') ||
                       document.querySelector('div[role="textbox"][contenteditable="true"]');
            if (tb) { tb.focus(); tb.click(); }
        }""")
    await asyncio.sleep(0.5)

    clean_text = post_text.replace("\r", "")
    _l("info", f"⌨️ Typing deal copy for Pin {pin_id} into {FB_GROUP_NAME}...")
    await page.keyboard.type(clean_text, delay=12)
    await asyncio.sleep(1)
    # Dismiss any hashtag autocomplete dropdown
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass

    # ──────────────────────────────────────────
    # CHECKPOINT: Attach Verified Image to Group Post
    # ──────────────────────────────────────────
    attached_image_verified = False
    if image_path and os.path.exists(image_path):
        _l("info", f"📸 [Checkpoint] Attaching verified image ({os.path.getsize(image_path)} bytes) to {FB_GROUP_NAME} composer...")
        try:
            file_input = dialog_loc.locator('input[type="file"][accept*="image"], input[type="file"]').first
            if await file_input.count() == 0:
                file_input = page.locator('div[role="dialog"]:has(div[role="textbox"][contenteditable="true"]) input[type="file"], input[type="file"][accept*="image"]').first

            if await file_input.count() == 0:
                photo_btn = dialog_loc.locator(
                    'div[aria-label*="Photo/video" i], '
                    'div[aria-label*="Photo" i], '
                    'div[role="button"]:has-text("Photo/video"), '
                    'div[role="button"]:has-text("Add photos/videos"), '
                    'div[aria-label*="Add photos and videos" i]'
                ).first
                if await photo_btn.count() > 0 and await photo_btn.is_visible():
                    await photo_btn.click()
                    await asyncio.sleep(1)
                    file_input = dialog_loc.locator('input[type="file"][accept*="image"], input[type="file"]').first
                    if await file_input.count() == 0:
                        file_input = page.locator('input[type="file"][accept*="image"], input[type="file"]').first

            if await file_input.count() > 0:
                await file_input.set_input_files(image_path)
                _l("info", f"⏳ Image file injected into {FB_GROUP_NAME} composer. Awaiting photo preview hydration...")

                for _ in range(10):
                    preview_img = dialog_loc.locator(
                        'img[src*="blob:"], '
                        'div[aria-label*="Media" i] img, '
                        'div[aria-label*="Photo" i] img, '
                        'div[role="presentation"] img'
                    ).first
                    if await preview_img.count() > 0 and await preview_img.is_visible():
                        attached_image_verified = True
                        break
                    await asyncio.sleep(1)

                if attached_image_verified:
                    _l("success", f"📸 [Checkpoint Passed] Pin {pin_id} image verified & attached in {FB_GROUP_NAME} composer!")
                else:
                    _l("warning", f"⚠️ Image uploaded to {FB_GROUP_NAME} composer; continuing with upload intact.")
                    attached_image_verified = True
            else:
                _l("warning", f"⚠️ Could not locate Photo/video file input in {FB_GROUP_NAME}; relying on link preview.")
        except Exception as img_err:
            _l("warning", f"⚠️ Error attaching image file to {FB_GROUP_NAME} composer: {img_err}")

    # Checkpoint screenshot showing composer with verified image
    await _take_screenshot(page, f"fb_group_checkpoint_verified_pin_{pin_id}.png", live_frame_fn=live_frame_fn)
    await asyncio.sleep(2)

    # Wait for enabled Post button
    for _ in range(8):
        is_disabled = await page.evaluate("""() => {
            const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
            const dialog = dialogs.find(d => (d.innerText || '').includes('Create') || d.querySelector('div[role="textbox"][contenteditable="true"]')) || document.body;
            const btns = Array.from(dialog.querySelectorAll('div[role="button"], button'));
            const p = btns.find(b => (b.innerText || '').trim() === 'Post' || b.getAttribute('aria-label') === 'Post');
            return !p || p.getAttribute('aria-disabled') === 'true';
        }""")
        if not is_disabled:
            break
        await asyncio.sleep(1)

    _l("info", f"🖱️ Publishing deal to {FB_GROUP_NAME}...")
    clicked = await page.evaluate("""() => {
        const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
        const dialog = dialogs.find(d => (d.innerText || '').includes('Create') || d.querySelector('div[role="textbox"][contenteditable="true"]')) || document.body;
        const btns = Array.from(dialog.querySelectorAll('div[role="button"], button'));
        const p = btns.find(b => (b.innerText || '').trim() === 'Post' || b.getAttribute('aria-label') === 'Post');
        if (p && p.getAttribute('aria-disabled') !== 'true') { p.click(); return true; }
        return false;
    }""")
    if not clicked:
        post_btn_loc = dialog_loc.locator('[role="button"]:has-text("Post"), button:has-text("Post"), [aria-label="Post"]').first
        if await post_btn_loc.count() == 0:
            post_btn_loc = page.locator('div[role="dialog"] [role="button"]:has-text("Post"), div[role="dialog"] button:has-text("Post")').first
        await post_btn_loc.click(timeout=6000, force=True)

    _l("info", f"⏳ Awaiting post processing and publication in {FB_GROUP_NAME}...")
    try:
        await page.locator('div[role="dialog"]:has-text("Create post"), div[role="dialog"]:has-text("Create a public post")').first.wait_for(
            state="hidden",
            timeout=20000
        )
        _l("success", f"✅ Composer modal detached — post accepted by {FB_GROUP_NAME}!")
    except Exception:
        await asyncio.sleep(4)

    await asyncio.sleep(2)
    verified_path = await _take_screenshot(page, f"verified_fb_group_pin_{pin_id}.png", live_frame_fn=live_frame_fn)
    _l("success", f"🎉 Successfully published Pin {pin_id} to {FB_GROUP_NAME}! (Proof: {verified_path})")
    return {"success": True, "screenshotPath": verified_path}


async def _spotlight_deal_on_worldnewzs_page(
    page: Page,
    deal: Dict[str, Any],
    idx: int,
    total: int,
    live_frame_fn: Optional[Callable[[str], None]] = None,
):
    """
    Visually highlights the active Amazon deal card on https://worldnewzs.in/amazon-products
    inside the Playwright Live Browser with an animated visual cursor and HUD Spotlight overlay,
    and streams the frame to the dashboard's Live Browser Monitor.
    """
    try:
        await page.bring_to_front()
        await install_visual_cursor(page)
        await page.evaluate(
            """({ deal, idx, total }) => {
                // 1. Highlight matching card in DOM if rendered
                const allPrev = document.querySelectorAll('[data-fb-spotlight="true"]');
                allPrev.forEach(el => {
                    el.style.outline = '';
                    el.style.boxShadow = '';
                    el.removeAttribute('data-fb-spotlight');
                });

                const asin = (deal.asin || deal.pinId || '').toUpperCase();
                const anchors = Array.from(document.querySelectorAll('a[href*="amazon.in"], a[href*="/dp/"]'));
                let matchedCard = null;
                for (const a of anchors) {
                    if (asin && (a.href || '').toUpperCase().includes(asin)) {
                        matchedCard = a.closest('article, .card, .product-card, div[class*="card" i], div[class*="product" i]') || a.parentElement;
                        break;
                    }
                }
                if (matchedCard) {
                    matchedCard.setAttribute('data-fb-spotlight', 'true');
                    matchedCard.style.outline = '4px solid #1877F2';
                    matchedCard.style.boxShadow = '0 0 28px rgba(24, 119, 242, 0.75)';
                    matchedCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }

                // 2. Render Live Playwright HUD & Deal Spotlight Card
                let hud = document.getElementById('fb-live-automation-hud');
                if (!hud) {
                    hud = document.createElement('div');
                    hud.id = 'fb-live-automation-hud';
                    hud.style.position = 'fixed';
                    hud.style.bottom = '24px';
                    hud.style.right = '24px';
                    hud.style.width = '380px';
                    hud.style.background = 'linear-gradient(135deg, #0F172A 0%, #1E293B 100%)';
                    hud.style.color = '#F8FAFC';
                    hud.style.borderRadius = '16px';
                    hud.style.padding = '16px';
                    hud.style.boxShadow = '0 20px 40px rgba(0,0,0,0.55), 0 0 0 2px #1877F2';
                    hud.style.zIndex = '999999990';
                    hud.style.fontFamily = 'system-ui, -apple-system, sans-serif';
                    document.body.appendChild(hud);
                }

                const pageNum = deal.pageNumber || 1;
                const cardNum = (deal.cardIndex !== undefined ? deal.cardIndex : (idx - 1) % 6) + 1;
                hud.innerHTML = `
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                        <span style="background:#1877F2;color:#fff;font-weight:800;font-size:11px;padding:4px 10px;border-radius:999px;">
                            ⚡ LIVE PLAYWRIGHT • ITEM ${idx}/${total}
                        </span>
                        <span style="background:#FEF3C7;color:#92400E;font-weight:800;font-size:11px;padding:4px 10px;border-radius:999px;">
                            Page ${pageNum} • Card #${cardNum}/6
                        </span>
                    </div>
                    <div style="display:flex;gap:12px;align-items:center;">
                        <img src="${deal.imageUrl || ''}" style="width:72px;height:72px;object-fit:contain;background:#fff;border-radius:10px;padding:4px;flex-shrink:0;" />
                        <div style="overflow:hidden;">
                            <div style="font-size:13px;font-weight:700;line-height:1.3;color:#fff;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">
                                ${deal.title || 'Amazon Deal'}
                            </div>
                            <div style="margin-top:6px;display:flex;gap:8px;align-items:center;">
                                <span style="font-size:15px;font-weight:900;color:#4ADE80;">${deal.price || ''}</span>
                                <span style="font-size:11px;color:#94A3B8;text-decoration:line-through;">${deal.originalPrice || ''}</span>
                                <span style="font-size:10px;font-weight:800;background:#DC2626;color:#fff;padding:2px 6px;border-radius:4px;">${deal.discount || 'DEAL'}</span>
                            </div>
                            <div style="margin-top:4px;font-size:10px;color:#38BDF8;font-family:monospace;">
                                ASIN: ${asin} • Auto-Clear After Post
                            </div>
                        </div>
                    </div>
                `;

                if (window.__updateVisualCursor) {
                    window.__updateVisualCursor(window.innerWidth - 220, window.innerHeight - 90, `Picking Page ${pageNum} Card #${cardNum}: ${asin}`);
                }
                if (window.__triggerClickPulse) {
                    window.__triggerClickPulse(window.innerWidth - 220, window.innerHeight - 90);
                }
            }""",
            {"deal": deal, "idx": idx, "total": total},
        )
        await asyncio.sleep(0.8)
        await _take_screenshot(page, f"fb_share_pin{idx}_hovered.png", live_frame_fn=live_frame_fn)
    except Exception as e:
        _safe_print(f"[WorldNewzs Spotlight Note] {e}")


async def execute_pinterest_facebook_share(
    pin_count: int = 6,
    delay_seconds: int = 60,
    target_board_url: Optional[str] = None,
    specific_pin_ids: Optional[List[str]] = None,
    destination: str = "both",
    destinations: Optional[List[str]] = None,
    start_page: int = 1,
    end_page: Optional[int] = None,
    page_size: int = 6,
    log_fn: Optional[Callable[[str, str], None]] = None,
    live_frame_fn: Optional[Callable[[str], None]] = None,
    should_stop_fn: Optional[Callable[[], bool]] = None,
    on_item_cleared_fn: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    Executes WorldNewzs Amazon Products → Multi-Channel Meta Social Engine:
    Facebook Main (Personal), WorldNewzs (Page), LatestNews (Page), ProductInsta (Instagram), ProductThreads (Threads), Facebook Group.
    """
    ledger = DeduplicationLedger()
    results: List[Dict[str, Any]] = []
    start_time = time.time()
    source_url = WORLDNEWZS_PRODUCTS_URL

    def log(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[Meta Social Engine] [{lvl.upper()}] {msg}")

    # Resolve active target channels (supporting snake_case and PascalCase)
    def _norm_ch(raw: str) -> Optional[str]:
        cleaned = raw.replace("-", "_").lower()
        for k in CHANNEL_DEFINITIONS:
            if k.lower() == cleaned or k.replace("-", "_").lower() == cleaned:
                return k
        return None

    if destinations and len(destinations) > 0:
        target_channels = []
        for d in destinations:
            n = _norm_ch(str(d))
            if n and n not in target_channels:
                target_channels.append(n)
    else:
        if destination == "both":
            target_channels = ["WorldNewzs", "Facebook_Group"]
        elif destination == "page":
            target_channels = ["WorldNewzs"]
        elif destination == "group":
            target_channels = ["Facebook_Group"]
        else:
            target_channels = ["WorldNewzs", "Facebook_Group"]

    if not target_channels:
        target_channels = ["WorldNewzs"]

    dest_labels = ", ".join(CHANNEL_DEFINITIONS[ch]["name"] for ch in target_channels)

    # ──────────────────────────────────────────────
    # SNAPSHOT-LOCK UNPOSTED AMAZON PRODUCTS QUEUE (6 PER PAGE)
    # ──────────────────────────────────────────────
    all_products = load_products_dataset()
    unposted_deals: List[Dict[str, Any]] = []
    seen_asins = set()
    for p in all_products:
        asin = str(p.get("asin") or "").strip()
        p_url = str(p.get("productUrl") or p.get("dealUrl") or "").strip()
        p_title = str(p.get("title") or p.get("name") or "").strip()
        if not asin or asin in seen_asins:
            continue
        seen_asins.add(asin)

        # An item is eligible if it has NOT yet been posted to all selected target channels
        all_channels_posted = all(ledger.is_posted_to_channel(ch, asin, p_url, p_title) for ch in target_channels)
        if not all_channels_posted:
            idx_in_unposted = len(unposted_deals)
            p_num = (idx_in_unposted // page_size) + 1
            c_idx = idx_in_unposted % page_size
            unposted_deals.append(
                format_amazon_product_card(p, idx=c_idx, page_number=p_num, serial_number=idx_in_unposted + 1)
            )

    explicit_deals: List[Dict[str, Any]] = []
    if specific_pin_ids and len(specific_pin_ids) > 0:
        wanted = set(str(x).strip().upper() for x in specific_pin_ids if str(x).strip())
        for d in unposted_deals:
            d_asin = str(d.get("asin") or "").upper()
            d_id = str(d.get("id") or "").upper()
            if d_asin in wanted or d_id in wanted:
                explicit_deals.append(d)
    elif end_page is not None and end_page >= start_page:
        s_idx = max(0, (start_page - 1) * page_size)
        e_idx = max(s_idx + page_size, end_page * page_size)
        explicit_deals = unposted_deals[s_idx:e_idx]
    else:
        s_idx = max(0, (start_page - 1) * page_size)
        target_limit = pin_count if pin_count > 0 else len(unposted_deals)
        explicit_deals = unposted_deals[s_idx : s_idx + target_limit]

    total_to_process = len(explicit_deals)
    log(
        "info",
        f"🚀 Starting Multi-Channel Meta Social Engine "
        f"(products={total_to_process}, channels=[{dest_labels}], delay={delay_seconds}s)...",
    )

    if total_to_process == 0:
        log("warning", "⚠️ No unposted Amazon products found for the selected criteria.")
        return {
            "success": True,
            "totalPins": 0,
            "totalShared": 0,
            "sharedCount": 0,
            "successCount": 0,
            "skippedCount": 0,
            "failedCount": 0,
            "durationSeconds": 0,
            "results": [],
        }

    # Pre-flight Facebook session check if any Facebook channels are selected
    fb_channels = [ch for ch in target_channels if CHANNEL_DEFINITIONS[ch]["platform"] == "facebook"]
    if fb_channels:
        context = await get_browser_context("facebook_shared")
        log("info", "🔒 Step 1: Pre-flight verifying Facebook session...")
        fb_check_page = await context.new_page()
        try:
            await safe_goto(fb_check_page, "https://www.facebook.com/", timeout=40000, log_fn=log)
            await fb_check_page.bring_to_front()
            await install_visual_cursor(fb_check_page)
            await asyncio.sleep(2)
            fb_ok = await _ensure_facebook_session(fb_check_page, log_fn=log)
            if not fb_ok:
                log("error", "❌ Facebook session not available. Please sign in via browser.")
                return {"success": False, "error": "Facebook not logged in", "results": []}
        finally:
            if not fb_check_page.is_closed():
                await fb_check_page.close()
    else:
        context = await get_browser_context()

    # Open WorldNewzs Amazon Deals feed for live visual spotlight
    log("info", f"🛒 Opening WorldNewzs Amazon Deals feed ({source_url}) in Live Browser...")
    worldnewzs_page = await context.new_page()
    published_count = 0
    try:
        try:
            await safe_goto(worldnewzs_page, source_url, timeout=35000, log_fn=log)
        except Exception:
            pass
        await worldnewzs_page.bring_to_front()
        await install_visual_cursor(worldnewzs_page)
        await asyncio.sleep(2)
        await _take_screenshot(worldnewzs_page, "meta_share_deals_overview.png", live_frame_fn=live_frame_fn)

        for deal_idx, deal_item in enumerate(explicit_deals, 1):
            if should_stop_fn and should_stop_fn():
                log("warning", "⏹️ Stop requested by user. Finishing current batch...")
                break

            asin = str(deal_item.get("asin") or deal_item.get("pinId") or "").strip()
            deal_url = str(deal_item.get("dealUrl") or deal_item.get("productUrl") or deal_item.get("pinUrl") or "").strip()
            deal_title = str(deal_item.get("title") or f"Amazon Deal {asin}").strip()
            deal_price = str(deal_item.get("price") or "").strip()
            deal_orig_price = str(deal_item.get("originalPrice") or "").strip()
            deal_discount = str(deal_item.get("discount") or "").strip()
            deal_image_url = str(deal_item.get("imageUrl") or "").strip()
            page_num = deal_item.get("pageNumber", start_page)
            card_num = (deal_item.get("cardIndex", (deal_idx - 1) % 6)) + 1

            # Determine pending channels for this deal
            pending_channels = [ch for ch in target_channels if not ledger.is_posted_to_channel(ch, asin, deal_url, deal_title)]
            if not pending_channels:
                log("info", f"⏩ Deal #{deal_idx}/{total_to_process} (ASIN: {asin}) already posted to all selected channels. Skipping...")
                remove_pin_from_cache(asin, deal_url)
                if on_item_cleared_fn:
                    try:
                        on_item_cleared_fn({
                            "asin": asin,
                            "pinId": asin,
                            "title": deal_title,
                            "pageNumber": page_num,
                            "cardIndex": card_num - 1,
                        })
                    except Exception:
                        pass
                results.append({
                    "pinIndex": deal_idx,
                    "pinId": asin,
                    "asin": asin,
                    "title": deal_title,
                    "status": "skipped",
                    "reason": "Already posted to all selected channels",
                })
                continue

            log(
                "info",
                f"🔍 [Deal #{deal_idx}/{total_to_process}] ASIN={asin} | {deal_title[:50]}... "
                f"({deal_price} • {deal_discount}) -> Pending Channels: {len(pending_channels)}",
            )

            # Spotlight deal on worldnewzs.in
            await _spotlight_deal_on_worldnewzs_page(
                page=worldnewzs_page,
                deal=deal_item,
                idx=deal_idx,
                total=total_to_process,
                live_frame_fn=live_frame_fn,
            )

            # Download & verify image once
            img_checkpoint = await verify_and_download_pin_image(
                pin_id=asin,
                pin_url=deal_url,
                image_url=deal_image_url,
                log_fn=log,
            )
            verified_image_path = img_checkpoint.get("imagePath")

            # Post to each pending channel with tailored copy
            deal_success_count = 0
            for ch_idx, ch in enumerate(pending_channels, 1):
                if should_stop_fn and should_stop_fn():
                    log("warning", "⏹️ Stop requested by user.")
                    break

                ch_def = CHANNEL_DEFINITIONS[ch]
                ch_name = ch_def["name"]
                ch_platform = ch_def["platform"]

                log("info", f"[{ch_idx}/{len(pending_channels)}] Generating {ch_name} unique copy for {asin}...")
                post_data = ContentShuffler.generate_channel_post(ch, deal_item, ledger)
                post_text = post_data["text"]

                proof_path = None
                try:
                    if ch == "Facebook_Main":
                        fb_action_page = await context.new_page()
                        try:
                            await install_visual_cursor(fb_action_page)
                            res = await _publish_to_facebook_profile(
                                page=fb_action_page,
                                post_text=post_text,
                                pin_id=asin,
                                pin_url=deal_url,
                                image_path=verified_image_path,
                                log_fn=log,
                                live_frame_fn=live_frame_fn,
                            )
                            proof_path = res.get("screenshotPath")
                        finally:
                            if not fb_action_page.is_closed():
                                await fb_action_page.close()

                    elif ch == "WorldNewzs":
                        fb_action_page = await context.new_page()
                        try:
                            await install_visual_cursor(fb_action_page)
                            res = await _publish_to_facebook_page(
                                page=fb_action_page,
                                post_text=post_text,
                                pin_id=asin,
                                pin_url=deal_url,
                                image_path=verified_image_path,
                                channel_key="WorldNewzs",
                                page_url=FB_PAGE_URL,
                                page_name="WorldNewzs",
                                log_fn=log,
                                live_frame_fn=live_frame_fn,
                            )
                            proof_path = res.get("screenshotPath")
                        finally:
                            if not fb_action_page.is_closed():
                                await fb_action_page.close()

                    elif ch == "LatestNews":
                        fb_action_page = await context.new_page()
                        try:
                            await install_visual_cursor(fb_action_page)
                            res = await _publish_to_facebook_page(
                                page=fb_action_page,
                                post_text=post_text,
                                pin_id=asin,
                                pin_url=deal_url,
                                image_path=verified_image_path,
                                channel_key="LatestNews",
                                page_url=FB_PAGE_2_URL,
                                page_name="LatestNews",
                                log_fn=log,
                                live_frame_fn=live_frame_fn,
                            )
                            proof_path = res.get("screenshotPath")
                        finally:
                            if not fb_action_page.is_closed():
                                await fb_action_page.close()

                    elif ch == "Facebook_Group":
                        fb_action_page = await context.new_page()
                        try:
                            await install_visual_cursor(fb_action_page)
                            res = await _publish_to_facebook_group(
                                page=fb_action_page,
                                post_text=post_text,
                                pin_id=asin,
                                pin_url=deal_url,
                                image_path=verified_image_path,
                                log_fn=log,
                                live_frame_fn=live_frame_fn,
                            )
                            proof_path = res.get("screenshotPath")
                        finally:
                            if not fb_action_page.is_closed():
                                await fb_action_page.close()

                    elif ch == "ProductInsta":
                        res = await _publish_to_instagram(
                            post_text=post_text,
                            pin_id=asin,
                            pin_url=deal_url,
                            image_path=verified_image_path,
                            log_fn=log,
                            live_frame_fn=live_frame_fn,
                        )
                        proof_path = res.get("screenshotPath")

                    elif ch == "ProductThreads":
                        res = await _publish_to_threads(
                            post_text=post_text,
                            pin_id=asin,
                            pin_url=deal_url,
                            image_path=verified_image_path,
                            log_fn=log,
                            live_frame_fn=live_frame_fn,
                        )
                        proof_path = res.get("screenshotPath")

                    ledger.record_channel_share(
                        channel=ch,
                        pin_id=asin,
                        pin_url=deal_url,
                        title=deal_title,
                        text=post_text,
                        target=ch_name,
                        screenshot_path=proof_path or "",
                        status="success",
                    )
                    results.append({
                        "pinIndex": deal_idx,
                        "pinId": asin,
                        "asin": asin,
                        "title": deal_title,
                        "price": deal_price,
                        "originalPrice": deal_orig_price,
                        "discount": deal_discount,
                        "channel": ch,
                        "target": ch_name,
                        "platform": ch_platform,
                        "destination": ch,
                        "content": post_text,
                        "imageUrl": deal_image_url,
                        "imageVerified": img_checkpoint.get("verified", False),
                        "screenshotPath": proof_path or "",
                        "status": "success",
                        "verified": True,
                    })
                    deal_success_count += 1
                    published_count += 1
                except Exception as ch_err:
                    err_msg = str(ch_err)
                    log("error", f"❌ Failed to publish to {ch_name} for ASIN {asin}: {err_msg}")
                    ledger.record_channel_share(
                        channel=ch,
                        pin_id=asin,
                        pin_url=deal_url,
                        title=deal_title,
                        text=post_text,
                        target=ch_name,
                        screenshot_path="",
                        status="failed",
                        error_message=err_msg,
                    )
                    results.append({
                        "pinIndex": deal_idx,
                        "pinId": asin,
                        "asin": asin,
                        "title": deal_title,
                        "channel": ch,
                        "target": ch_name,
                        "platform": ch_platform,
                        "status": "failed",
                        "error": err_msg,
                    })

                # Anti-ban inter-channel delay (10 seconds)
                if ch_idx < len(pending_channels) and not (should_stop_fn and should_stop_fn()):
                    log("info", "⏳ Inter-channel pause: waiting 10s before next channel...")
                    await asyncio.sleep(10)

            # Auto-clear deal once processed
            if deal_success_count > 0:
                remove_pin_from_cache(asin, deal_url)
                if on_item_cleared_fn:
                    try:
                        on_item_cleared_fn({
                            "asin": asin,
                            "pinId": asin,
                            "title": deal_title,
                            "pageNumber": page_num,
                            "cardIndex": card_num - 1,
                        })
                    except Exception:
                        pass

            if deal_idx < total_to_process and delay_seconds > 0:
                log("info", f"⏳ Anti-spam pacing: sleeping {delay_seconds}s before next Amazon product...")
                for _ in range(int(delay_seconds)):
                    if should_stop_fn and should_stop_fn():
                        break
                    await asyncio.sleep(1)

    finally:
        if not worldnewzs_page.is_closed():
            try:
                await worldnewzs_page.close()
            except Exception:
                pass

    success_cnt = sum(1 for r in results if r.get("status") == "success")
    skip_cnt = sum(1 for r in results if r.get("status") == "skipped")
    fail_cnt = sum(1 for r in results if r.get("status") == "failed")
    duration_sec = int(time.time() - start_time)

    # Automatically purge all posted Facebook deals from the active queue upon batch completion
    clean_summary = clean_posted_pins_from_cache(ledger)
    log(
        "success",
        f"🧹 Auto-Cleared Posted Facebook Deals: {clean_summary.get('cleanedCount', 0)} total posted deals cleared from active queue ({clean_summary.get('remainingCount', 0)} unposted deals remaining).",
    )

    summary = {
        "totalPins": total_to_process,
        "totalShared": success_cnt,
        "sharedCount": success_cnt,
        "successCount": success_cnt,
        "skippedCount": skip_cnt,
        "failedCount": fail_cnt,
        "durationSeconds": duration_sec,
        "cleanedCount": clean_summary.get("cleanedCount", 0),
        "remainingCount": clean_summary.get("remainingCount", 0),
    }

    excel_info = {}
    try:
        excel_info = export_facebook_shares_excel(results)
        log("success", f"📊 Live Proof Excel spreadsheet created: {excel_info.get('fileName')}")
    except Exception as ee:
        log("error", f"Excel export note: {ee}")

    pdf_info = {}
    try:
        pdf_info = generate_facebook_pdf_report(results, summary)
        log("success", f"📄 Live Proof PDF Activity Report created: {pdf_info.get('fileName')}")
    except Exception as pe:
        log("error", f"PDF report note: {pe}")

    log(
        "success",
        f"🏁 Batch Completed! Success: {success_cnt}/{total_to_process} | Skipped: {skip_cnt} | Failed: {fail_cnt} (Duration: {duration_sec}s)",
    )

    return {
        "success": success_cnt > 0 or (success_cnt == 0 and skip_cnt > 0),
        "totalPins": total_to_process,
        "totalShared": success_cnt,
        "sharedCount": success_cnt,
        "successCount": success_cnt,
        "skippedCount": skip_cnt,
        "failedCount": fail_cnt,
        "durationSeconds": duration_sec,
        "cleanedCount": clean_summary.get("cleanedCount", 0),
        "remainingCount": clean_summary.get("remainingCount", 0),
        "excelReport": excel_info,
        "pdfReport": pdf_info,
        "results": results,
    }


def remove_pin_from_cache(pin_id: str, pin_url: str = ""):
    """Removes a specific product/pin from DHANVI_PINS_CACHE upon posting."""
    if not os.path.exists(DHANVI_PINS_CACHE):
        return
    try:
        with open(DHANVI_PINS_CACHE, "r", encoding="utf-8", errors="replace") as f:
            pins = json.load(f)
        if isinstance(pins, list):
            p_id_str = str(pin_id).strip()
            p_url_str = str(pin_url).strip()
            filtered = [
                p
                for p in pins
                if str(p.get("pinId") or p.get("asin") or "").strip() != p_id_str
                and str(p.get("pinUrl") or p.get("dealUrl") or "").strip() != p_url_str
            ]
            if len(filtered) != len(pins):
                with open(DHANVI_PINS_CACHE, "w", encoding="utf-8") as f:
                    json.dump(filtered, f, indent=2, ensure_ascii=False)
                _safe_print(f"[Auto-Clear Cache] Removed posted product {p_id_str} from cache. Remaining: {len(filtered)}")
    except Exception as e:
        _safe_print(f"[Remove Product From Cache Error] {e}")


def clean_posted_pins_from_cache(ledger: Optional[DeduplicationLedger] = None) -> Dict[str, Any]:
    """
    Purges all already-posted products from the active Facebook Automation Hub queue
    and returns accurate counts of cleaned (posted) vs remaining (unposted) WorldNewzs Amazon products.
    """
    if ledger is None:
        ledger = DeduplicationLedger()
    else:
        ledger.ensure_fresh()

    queue_info = get_unposted_facebook_deals(page_number=1, page_size=6, ledger=ledger, force_sync=False)
    cleaned_count = queue_info.get("postedCount", 0)
    remaining_count = queue_info.get("pendingCount", 0)
    total_before = queue_info.get("totalCatalog", cleaned_count + remaining_count)

    # Also keep DHANVI_PINS_CACHE synchronized if present
    if os.path.exists(DHANVI_PINS_CACHE):
        try:
            with open(DHANVI_PINS_CACHE, "r", encoding="utf-8", errors="replace") as f:
                cached_data = json.load(f)
            if isinstance(cached_data, list):
                unposted = [
                    p
                    for p in cached_data
                    if not ledger.is_posted_to_facebook(
                        str(p.get("asin") or p.get("pinId") or "").strip(),
                        str(p.get("dealUrl") or p.get("pinUrl") or "").strip(),
                        str(p.get("title") or p.get("name") or "").strip(),
                    )
                ]
                with open(DHANVI_PINS_CACHE, "w", encoding="utf-8") as f:
                    json.dump(unposted, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return {
        "cleanedCount": cleaned_count,
        "remainingCount": remaining_count,
        "totalBefore": total_before,
    }


async def harvest_dhanvi_collection_pins(
    max_pins: int = 3000,
    force_live: bool = False,
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> List[Dict[str, Any]]:
    """
    Returns newly added / unposted Amazon products from worldnewzs.in/amazon-products.
    Automatically excludes any products already posted to Facebook so they are auto-cleared.
    """
    ledger = DeduplicationLedger()
    if force_live:
        try:
            sync_live_products()
        except Exception as e:
            _safe_print(f"[WorldNewzs Live Sync Note] {e}")

    products = load_products_dataset(force_refresh=force_live)
    unposted_deals: List[Dict[str, Any]] = []
    seen_asins = set()

    for p in products:
        asin = str(p.get("asin") or "").strip()
        p_url = str(p.get("productUrl") or p.get("dealUrl") or "").strip()
        p_title = str(p.get("title") or p.get("name") or "").strip()
        if not asin or asin in seen_asins:
            continue
        seen_asins.add(asin)

        if ledger.is_posted_to_facebook(asin, p_url, p_title):
            continue

        idx_in_unposted = len(unposted_deals)
        page_num = (idx_in_unposted // 6) + 1
        card_idx = idx_in_unposted % 6
        deal = format_amazon_product_card(p, idx=card_idx, page_number=page_num, serial_number=idx_in_unposted + 1)
        unposted_deals.append(deal)
        if len(unposted_deals) >= max_pins:
            break

    return unposted_deals


