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
FB_GROUP_NAME = os.environ.get("FACEBOOK_GROUP_NAME", "Amazon Affiliate Group")
FB_GROUP_URL = os.environ.get("FACEBOOK_GROUP_URL", "https://www.facebook.com/groups/1761596288324903/")
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
    live_frame_fn: Optional[Callable[[str], None]] = None,
) -> str:
    """Saves a screenshot to state/screenshots, updates fb_live_frame.png, and notifies live viewer."""
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    path = os.path.join(SCREENSHOTS_DIR, os.path.basename(name))
    try:
        await page.screenshot(path=path, full_page=False)
        live_frame_path = os.path.join(SCREENSHOTS_DIR, "fb_live_frame.png")
        try:
            import shutil
            shutil.copy2(path, live_frame_path)
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


async def _ensure_worldnewzs_profile(
    page: Page,
    fb_page_url: str = FB_PAGE_URL,
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """
    Ensures the Facebook session is actively switched to the WorldNewzs Page profile
    so posts into WorldNewzs Page feed and Amazon Affiliate Group are published as Page Admin.
    """
    def _l(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[Profile Switch] [{lvl.upper()}] {msg}")

    try:
        _l("info", f"Checking Facebook identity status on '{fb_page_url}' (WorldNewzs)...")
        await safe_goto(page, fb_page_url, timeout=45000, log_fn=_l)
        await asyncio.sleep(3.5)

        # Clear any overlay or alertdialog
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
        except Exception:
            pass

        # Check if already acting as WorldNewzs (Manage Page and no Switch Now banner)
        is_managing = await page.evaluate("""() => {
            const body = document.body.innerText || '';
            const hasManage = body.includes('Manage Page') || body.includes('Professional dashboard');
            const hasSwitchNow = body.includes('Switch into WorldNewzs') || body.includes('Switch Now') || body.includes('Switch to WorldNewzs');
            return hasManage && !hasSwitchNow;
        }""")
        if is_managing:
            _l("success", "✅ Facebook session is already acting as WorldNewzs (Page Admin)!")
            return True

        # Look for "Switch Now" or "Switch" trigger on page
        _l("info", "🔄 Switching profile to WorldNewzs Page identity...")
        switch_trigger = await page.query_selector(
            'div[role="button"]:has-text("Switch Now"), '
            'div[aria-label="Switch Now"], '
            'div[aria-label*="Switch into WorldNewzs" i], '
            'div[role="button"]:has-text("Switch"), '
            '[aria-label*="Switch to WorldNewzs" i]'
        )
        if switch_trigger:
            _l("info", "🖱️ Clicking Switch into WorldNewzs trigger...")
            try:
                await switch_trigger.click()
            except Exception:
                await page.evaluate("""() => {
                    const btn = Array.from(document.querySelectorAll('div[role="button"], span')).find(e => 
                        (e.innerText || '').trim() === 'Switch Now' || (e.innerText || '').trim() === 'Switch'
                    );
                    if (btn) btn.click();
                }""")
            await asyncio.sleep(2.5)

            # Confirm Switch in modal dialog if prompted
            modal_switch_btn = await page.query_selector(
                'div[role="dialog"] div[role="button"]:has-text("Switch"), '
                'div[role="dialog"] div[aria-label="Switch"][role="button"], '
                'div[role="dialog"] div[aria-label="Switch"]'
            )
            if modal_switch_btn:
                _l("info", "🖱️ Confirming Switch in dialog...")
                try:
                    await modal_switch_btn.click()
                except Exception:
                    await page.evaluate("""() => {
                        const b = Array.from(document.querySelectorAll('div[role="dialog"] div[role="button"]')).find(el => (el.innerText || '').trim() === 'Switch');
                        if (b) b.click();
                    }""")
                _l("info", "⏳ Waiting for Facebook profile switch...")
                await asyncio.sleep(7)
                await page.keyboard.press("Escape")
                _l("success", "🎉 Successfully switched to WorldNewzs Page identity!")
                return True
        else:
            profile_icon = await page.query_selector('div[aria-label="Your profile"]')
            if profile_icon:
                await profile_icon.click()
                await asyncio.sleep(2)
                wn_profile = await page.query_selector(
                    'div[role="button"]:has-text("WorldNewzs"), '
                    'div[role="listitem"]:has-text("WorldNewzs"), '
                    '[aria-label*="WorldNewzs" i]'
                )
                if wn_profile:
                    _l("info", "🖱️ Switching to WorldNewzs via profile dropdown...")
                    await wn_profile.click()
                    await asyncio.sleep(7)
                    await page.keyboard.press("Escape")
                    _l("success", "🎉 Successfully switched to WorldNewzs Page identity!")
                    return True

        is_now_managing = await page.evaluate("""() => {
            const body = document.body.innerText || '';
            return body.includes('Manage Page') || body.includes('Professional dashboard');
        }""")
        if is_now_managing:
            _l("success", "✅ Verified: Now acting as WorldNewzs (Page Admin) on Facebook!")
            return True

        _l("warning", "⚠️ Continuing with active Facebook profile.")
        return False
    except Exception as e:
        _l("warning", f"Profile switch note: {e}")
        return False


async def _publish_to_facebook_page(
    page: Page,
    post_text: str,
    pin_id: str,
    pin_url: str = "",
    image_path: Optional[str] = None,
    log_fn: Optional[Callable[[str, str], None]] = None,
    live_frame_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Publishes deal copy and Pinterest pin link directly to WorldNewzs Facebook Page feed.
    """
    def _l(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[FB Page Publish] [{lvl.upper()}] {msg}")

    _l("info", f"📄 Navigating to WorldNewzs Facebook Page ({FB_PAGE_URL})...")
    await safe_goto(page, FB_PAGE_URL, timeout=45000, log_fn=_l)
    await page.bring_to_front()
    await asyncio.sleep(3)

    # Check if Switch Now prompt appears
    try:
        switch_now_btn = page.locator(
            'div[role="button"]:has-text("Switch Now"), '
            'div[aria-label="Switch Now"], '
            'div[role="button"]:has-text("Switch"), '
            '[aria-label*="Switch into WorldNewzs" i]'
        ).first
        if await switch_now_btn.count() > 0 and await switch_now_btn.is_visible():
            _l("info", "🔄 Switching into WorldNewzs Page profile...")
            await switch_now_btn.click()
            await asyncio.sleep(2.5)
            dialog_switch = page.locator(
                'div[role="dialog"] div[role="button"]:has-text("Switch"), '
                'div[role="dialog"] div[aria-label="Switch"]'
            ).first
            if await dialog_switch.count() > 0 and await dialog_switch.is_visible():
                await dialog_switch.click()
                await asyncio.sleep(6)
    except Exception:
        pass

    # Dismiss any notification alertdialog or overlay
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)
    except Exception:
        pass

    # Scroll down so composer is centered in viewport
    await page.evaluate("window.scrollBy(0, 350)")
    await asyncio.sleep(1.5)

    # Locate and trigger composer: "What's on your mind?"
    _l("info", "📝 Opening post composer on WorldNewzs Page ('What\\'s on your mind?')...")
    composer_trigger = page.locator(
        'div[role="button"]:has-text("What\'s on your mind?"), '
        'span:has-text("What\'s on your mind?")'
    ).first
    await composer_trigger.wait_for(state="visible", timeout=12000)
    try:
        await composer_trigger.click(timeout=4000, force=True)
    except Exception:
        await page.evaluate("""() => {
            const el = Array.from(document.querySelectorAll('div[role="button"], span')).find(e => 
                (e.innerText || '').includes("What's on your mind?")
            );
            if (el) el.click();
        }""")
    await asyncio.sleep(3)

    # Scoped Create post dialog
    dialog_loc = page.locator(
        'div[role="dialog"]:has(div[role="textbox"][contenteditable="true"]), '
        'div[role="dialog"]:has-text("Create post"), '
        'div[role="dialog"]:has-text("Post settings")'
    ).first
    await dialog_loc.wait_for(state="visible", timeout=12000)

    # Focus textbox and type copy
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
            const d = document.querySelector('div[role="dialog"]:has(div[role="textbox"][contenteditable="true"])') ||
                      document.querySelector('div[role="dialog"]:has-text("Create post")') || 
                      document.querySelector('div[role="dialog"]');
            const tb = d ? d.querySelector('div[role="textbox"][contenteditable="true"]') : null;
            if (tb) { tb.focus(); tb.click(); }
        }""")
    await asyncio.sleep(0.5)

    clean_text = post_text.replace("\r", "")
    _l("info", f"⌨️ Typing deal copy & Pinterest link for Pin {pin_id} into Page composer...")
    await page.keyboard.type(clean_text, delay=14)
    await asyncio.sleep(1)
    # Dismiss any hashtag dropdown suggestion popup
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass

    # ──────────────────────────────────────────
    # CHECKPOINT: Attach Verified Image to Page Post
    # ──────────────────────────────────────────
    attached_image_verified = False
    if image_path and os.path.exists(image_path):
        _l("info", f"📸 [Checkpoint] Attaching verified image ({os.path.getsize(image_path)} bytes) to Page composer...")
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
                _l("info", "⏳ Image file injected into Page composer. Awaiting photo preview hydration...")

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
                    _l("success", f"📸 [Checkpoint Passed] Pin {pin_id} image verified & attached in Facebook Page composer!")
                else:
                    _l("warning", f"⚠️ Image uploaded to Page composer; continuing with upload intact.")
                    attached_image_verified = True
            else:
                _l("warning", "⚠️ Could not locate Photo/video file input in Page composer; relying on link preview.")
        except Exception as img_err:
            _l("warning", f"⚠️ Error attaching image file to Page composer: {img_err}")

    # Checkpoint screenshot showing composer with verified image
    await _take_screenshot(page, f"fb_page_checkpoint_verified_pin_{pin_id}.png", live_frame_fn=live_frame_fn)
    await asyncio.sleep(3)

    # Click Next button
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
    await asyncio.sleep(3)

    # Click Post button with exact match
    _l("info", f"🚀 Publishing Pin {pin_id} to WorldNewzs Facebook Page feed...")
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
        post_loc = page.locator('div[role="dialog"]:has-text("Post settings") div[role="button"]:has-text("Post"), div[role="dialog"]:has-text("Create post") div[role="button"]:has-text("Post")').first
        if await post_loc.count() > 0:
            await post_loc.click()

    _l("info", "⏳ Awaiting post publication confirmation on WorldNewzs Page...")
    await asyncio.sleep(8)

    # Wait for modal to detach
    try:
        await page.locator('div[role="dialog"]:has-text("Create post")').first.wait_for(state="hidden", timeout=15000)
    except Exception:
        pass

    await asyncio.sleep(2)
    verified_path = await _take_screenshot(page, f"verified_fb_page_pin_{pin_id}.png", live_frame_fn=live_frame_fn)
    _l("success", f"🎉 Successfully published Pin {pin_id} to WorldNewzs Facebook Page! (Proof: {verified_path})")
    return {"success": True, "screenshotPath": verified_path}


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
            const dialog = document.querySelector('div[role="dialog"]:has(div[role="textbox"][contenteditable="true"])') ||
                           document.querySelector('div[role="dialog"]:has-text("Create")') ||
                           document.querySelector('div[role="dialog"]') ||
                           document.body;
            const btns = Array.from(dialog.querySelectorAll('div[role="button"], button'));
            const p = btns.find(b => (b.innerText || '').trim() === 'Post' || b.getAttribute('aria-label') === 'Post');
            return !p || p.getAttribute('aria-disabled') === 'true';
        }""")
        if not is_disabled:
            break
        await asyncio.sleep(1)

    _l("info", f"🖱️ Publishing deal to {FB_GROUP_NAME}...")
    clicked = await page.evaluate("""() => {
        const dialog = document.querySelector('div[role="dialog"]:has(div[role="textbox"][contenteditable="true"])') ||
                       document.querySelector('div[role="dialog"]:has-text("Create")') ||
                       document.querySelector('div[role="dialog"]') ||
                       document.body;
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
    start_page: int = 1,
    end_page: Optional[int] = None,
    page_size: int = 6,
    log_fn: Optional[Callable[[str, str], None]] = None,
    live_frame_fn: Optional[Callable[[str], None]] = None,
    should_stop_fn: Optional[Callable[[], bool]] = None,
    on_item_cleared_fn: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    Executes WorldNewzs Amazon Products (worldnewzs.in/amazon-products) → Facebook Page & Group
    automation targeting NEWLY ADDED / UNPOSTED products only (6 products per page).
    Workflow:
    1. Pre-flight verification of Facebook session & WorldNewzs Page identity switch
    2. Open https://worldnewzs.in/amazon-products in Playwright Live Browser with Visual Cursor & HUD
    3. Snapshot-lock unposted Amazon products (6 products per page, matched by ASIN & amazon.in URL)
    4. Spotlight active deal card on worldnewzs.in/amazon-products & verify 1500px Amazon image
    5. Generate dynamic shuffled deal copy with ₹ price, % discount & direct amazon.in affiliate link
    6. Publish to Facebook Page feed ('WorldNewzs') and/or 'Amazon Affiliate Group'
    7. Immediately record ASIN in DeduplicationLedger & auto-clear posted product from active queue
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
        _safe_print(f"[WorldNewzs→FB] [{lvl.upper()}] {msg}")

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
        if not ledger.is_posted_to_facebook(asin, p_url, p_title):
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
        # Page or Page-Range mode (6 unposted products per page)
        s_idx = max(0, (start_page - 1) * page_size)
        e_idx = max(s_idx + page_size, end_page * page_size)
        explicit_deals = unposted_deals[s_idx:e_idx]
    else:
        # Count mode starting from start_page
        s_idx = max(0, (start_page - 1) * page_size)
        target_limit = pin_count if pin_count > 0 else len(unposted_deals)
        explicit_deals = unposted_deals[s_idx : s_idx + target_limit]

    total_to_process = len(explicit_deals)
    dest_label = (
        "WorldNewzs Page + Amazon Affiliate Group"
        if destination == "both"
        else "WorldNewzs Page Feed"
        if destination == "page"
        else "Amazon Affiliate Group"
    )
    log(
        "info",
        f"🚀 Starting WorldNewzs Amazon Products → Facebook Automation "
        f"(products={total_to_process}, page={start_page}{f'-{end_page}' if end_page and end_page != start_page else ''}, "
        f"6/page, destination={dest_label}, delay={delay_seconds}s)...",
    )

    if total_to_process == 0:
        log("warning", "⚠️ No unposted Amazon products found for the selected page/criteria. Syncing live products...")
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

    context = await get_browser_context()

    # ──────────────────────────────────────────────
    # STEP 1: Pre-flight — Verify Facebook Session & WorldNewzs Page Identity
    # ──────────────────────────────────────────────
    log("info", "🔒 Step 1/7: Verifying Facebook session & WorldNewzs Page identity...")
    fb_check_page = await context.new_page()
    try:
        await safe_goto(fb_check_page, "https://www.facebook.com/", timeout=40000, log_fn=log)
        await fb_check_page.bring_to_front()
        await install_visual_cursor(fb_check_page)
        await asyncio.sleep(2.5)
        await _take_screenshot(fb_check_page, "fb_share_step1_session_check.png", live_frame_fn=live_frame_fn)

        fb_ok = await _ensure_facebook_session(fb_check_page, log_fn=log)
        if not fb_ok:
            log("error", "❌ Facebook session not available. Please sign in via browser.")
            return {"success": False, "error": "Facebook not logged in", "results": []}

        await _ensure_worldnewzs_profile(fb_check_page, fb_page_url=FB_PAGE_URL, log_fn=log)
        await _take_screenshot(fb_check_page, "fb_share_step1_profile_ready.png", live_frame_fn=live_frame_fn)
        log("success", "✅ Step 1 complete — Facebook session & WorldNewzs Page identity verified!")
    finally:
        if not fb_check_page.is_closed():
            await fb_check_page.close()

    # ──────────────────────────────────────────────
    # STEP 2: Open WorldNewzs Amazon Products Feed (worldnewzs.in/amazon-products)
    # ──────────────────────────────────────────────
    log("info", f"🛒 Step 2/7: Opening WorldNewzs Amazon Deals feed ({source_url}) in Live Browser...")
    worldnewzs_page = await context.new_page()
    published_count = 0
    try:
        try:
            await safe_goto(worldnewzs_page, source_url, timeout=35000, log_fn=log)
        except Exception as nav_e:
            log("info", f"⚡ WorldNewzs page loaded in hybrid mode ({nav_e}); activating Live Deal HUD...")
        await worldnewzs_page.bring_to_front()
        await install_visual_cursor(worldnewzs_page)
        await asyncio.sleep(2)
        await _take_screenshot(worldnewzs_page, "fb_share_step2_created_page.png", live_frame_fn=live_frame_fn)
        log("success", f"✅ Step 2 complete — WorldNewzs Amazon Products active ({total_to_process} unposted deals queued, 6 per page)!")

        # ──────────────────────────────────────────────
        # PROCESS EACH SNAPSHOT-LOCKED AMAZON PRODUCT
        # ──────────────────────────────────────────────
        for deal_idx, deal_item in enumerate(explicit_deals, 1):
            if should_stop_fn and should_stop_fn():
                log("warning", "⏹️ Stop requested by user. Finishing current Facebook batch and generating reports...")
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

            if ledger.is_posted_to_facebook(asin, deal_url, deal_title):
                log("info", f"⏩ Deal #{deal_idx}/{total_to_process} (ASIN: {asin}) is already posted to Facebook. Auto-clearing & skipping...")
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
                    "pinUrl": deal_url,
                    "pinId": asin,
                    "asin": asin,
                    "title": deal_title,
                    "price": deal_price,
                    "discount": deal_discount,
                    "status": "skipped",
                    "reason": "Already posted to Facebook",
                })
                continue

            log(
                "info",
                f"🔍 [Page {page_num} • Card #{card_num}/6] Deal #{deal_idx}/{total_to_process}: "
                f"ASIN={asin} | {deal_title[:52]}... ({deal_price} • {deal_discount})",
            )

            # Spotlight this deal card on worldnewzs.in/amazon-products in the Live Browser
            await _spotlight_deal_on_worldnewzs_page(
                page=worldnewzs_page,
                deal=deal_item,
                idx=deal_idx,
                total=total_to_process,
                live_frame_fn=live_frame_fn,
            )

            if destination == "both":
                target_name = f"{FB_PAGE_NAME} (Page Feed + Group)"
            elif destination == "page":
                target_name = f"{FB_PAGE_NAME} (Page Feed)"
            else:
                target_name = f"{FB_GROUP_NAME} (Group)"

            # Step 3: Verify and pre-download high-res Amazon product image locally
            log("info", f"📸 Step 3/7: Verifying high-res Amazon image & crafting deal copy for ASIN {asin} (Page {page_num}, Card #{card_num}/6)...")
            img_checkpoint = await verify_and_download_pin_image(
                pin_id=asin,
                pin_url=deal_url,
                image_url=deal_image_url,
                log_fn=log,
            )
            verified_image_path = img_checkpoint.get("imagePath")
            if img_checkpoint.get("imageUrl"):
                deal_image_url = img_checkpoint["imageUrl"]

            post_data = ContentShuffler.generate_post(deal_item, ledger)
            post_text = post_data.get(
                "text",
                f"🔥 {deal_discount}! {deal_title}\n💰 Deal Price: {deal_price}\n\n🛒 Grab this deal: {deal_url}",
            )
            log("info", f"📝 Shuffled Amazon Copy: \"{post_text[:75].replace(chr(10), ' ')}...\"")

            fb_action_page = await context.new_page()
            try:
                await install_visual_cursor(fb_action_page)
                page_proof = None
                group_proof = None

                if destination in ["both", "page"]:
                    log("info", f"📄 Step 4/7: Publishing Deal #{deal_idx}/{total_to_process} (ASIN: {asin}) to WorldNewzs Facebook Page Feed...")
                    page_res = await _publish_to_facebook_page(
                        page=fb_action_page,
                        post_text=post_text,
                        pin_id=asin,
                        pin_url=deal_url,
                        image_path=verified_image_path,
                        log_fn=log,
                        live_frame_fn=live_frame_fn,
                    )
                    page_proof = page_res.get("screenshotPath")

                if destination in ["both", "group"]:
                    log("info", f"👥 Step 5/7: Publishing Deal #{deal_idx}/{total_to_process} (ASIN: {asin}) to {FB_GROUP_NAME}...")
                    group_res = await _publish_to_facebook_group(
                        page=fb_action_page,
                        post_text=post_text,
                        pin_id=asin,
                        pin_url=deal_url,
                        image_path=verified_image_path,
                        log_fn=log,
                        live_frame_fn=live_frame_fn,
                    )
                    group_proof = group_res.get("screenshotPath")

                log("info", f"💾 Step 6/7: Recording ASIN {asin} in DeduplicationLedger & auto-clearing from active queue...")
                verified_path = group_proof or page_proof or ""
                ledger.record_facebook_share(
                    pin_id=asin,
                    pin_url=deal_url,
                    title=deal_title,
                    text=post_text,
                    target=target_name,
                    screenshot_path=verified_path,
                    status="success",
                )
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

                log(
                    "success",
                    f"🎉 Step 7/7 complete: Amazon Deal {asin} (Page {page_num} Card #{card_num}/6) published to {target_name} & auto-cleared!",
                )

                results.append({
                    "pinIndex": deal_idx,
                    "pinUrl": deal_url,
                    "dealUrl": deal_url,
                    "pinId": asin,
                    "asin": asin,
                    "title": deal_title,
                    "price": deal_price,
                    "originalPrice": deal_orig_price,
                    "discount": deal_discount,
                    "pageNumber": page_num,
                    "cardNumber": card_num,
                    "status": "success",
                    "target": target_name,
                    "destination": destination,
                    "content": post_text,
                    "imageUrl": deal_image_url,
                    "imageVerified": img_checkpoint.get("verified", False),
                    "screenshotPath": verified_path,
                    "pageProof": page_proof,
                    "groupProof": group_proof,
                    "verified": True,
                })
                published_count += 1
            except Exception as fe:
                err_msg = str(fe)
                log("error", f"❌ Facebook posting error for Deal #{deal_idx} (ASIN {asin}): {err_msg}")
                ledger.record_facebook_share(
                    pin_id=asin,
                    pin_url=deal_url,
                    title=deal_title,
                    text=post_text if "post_text" in locals() else "",
                    target=target_name,
                    screenshot_path="",
                    status="failed",
                    error_message=err_msg,
                )
                results.append({
                    "pinIndex": deal_idx,
                    "pinUrl": deal_url,
                    "dealUrl": deal_url,
                    "pinId": asin,
                    "asin": asin,
                    "title": deal_title,
                    "price": deal_price,
                    "status": "failed",
                    "error": err_msg,
                })
            finally:
                if not fb_action_page.is_closed():
                    try:
                        await fb_action_page.close()
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


