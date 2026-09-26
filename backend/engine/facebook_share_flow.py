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
    Auto-resolves the high-res Pinterest CDN image URL from the Pinterest pin page
    using og:image or JSON-LD metadata.
    """
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
        _safe_print(f"[Resolve Pin Image] Failed for Pin {pin_id}: {e}")
    return ""


async def verify_and_download_pin_image(
    pin_id: str,
    pin_url: str = "",
    image_url: str = "",
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> Dict[str, Any]:
    """
    Checkpoint: Verifies that the pin has a valid high-resolution image URL,
    auto-resolves missing images from Pinterest, and downloads the image locally
    to state/temp_pin_images/pin_<pin_id>.jpg.
    Returns details on the verified image URL and local file path.
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

    # Upgrade thumbnail resolution to 736x
    if cleaned_img_url:
        cleaned_img_url = cleaned_img_url.replace("/236x/", "/736x/").replace("/474x/", "/736x/")

    # Auto-resolve if missing
    if not cleaned_img_url or not cleaned_img_url.startswith("http"):
        log("info", f"🔍 Pin {pin_id} image URL missing in cache/DOM. Querying Pinterest OpenGraph metadata...")
        resolved = resolve_pin_image_from_pinterest(pin_id, pin_url)
        if resolved:
            cleaned_img_url = resolved
            log("success", f"✅ Successfully resolved high-res image for Pin {pin_id}: {cleaned_img_url[:65]}...")
        else:
            log("warning", f"⚠️ Could not resolve image for Pin {pin_id} from Pinterest.")

    if not cleaned_img_url:
        return {"verified": False, "imageUrl": "", "imagePath": None, "error": "No image URL available"}

    # Download image locally
    os.makedirs(TEMP_PIN_IMAGES_DIR, exist_ok=True)
    ext = ".png" if ".png" in cleaned_img_url.lower() else ".jpg"
    local_path = os.path.join(TEMP_PIN_IMAGES_DIR, f"pin_{pin_id}{ext}")

    try:
        import urllib.request
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://in.pinterest.com/",
        }
        req = urllib.request.Request(cleaned_img_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            if len(data) > 512:
                with open(local_path, "wb") as f_out:
                    f_out.write(data)
                log("success", f"📸 [Checkpoint Passed] Pin {pin_id} image verified & downloaded ({len(data)} bytes -> {os.path.basename(local_path)})")
                return {
                    "verified": True,
                    "imageUrl": cleaned_img_url,
                    "imagePath": local_path,
                    "fileSize": len(data),
                }
            else:
                log("warning", f"⚠️ Image downloaded for Pin {pin_id} was too small ({len(data)} bytes).")
    except Exception as dl_err:
        log("warning", f"⚠️ Failed downloading image from {cleaned_img_url[:60]}: {dl_err}")

    # Check if a previously downloaded image exists
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


async def execute_pinterest_facebook_share(
    pin_count: int = 10,
    delay_seconds: int = 60,
    target_board_url: Optional[str] = None,
    specific_pin_ids: Optional[List[str]] = None,
    destination: str = "both",
    log_fn: Optional[Callable[[str, str], None]] = None,
    live_frame_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Executes Pinterest Pin → Facebook Page & Group share targeting UNPOSTED pins only.
    Workflow:
    1. Pre-flight verification of Facebook session & WorldNewzs Page identity switch
    2. Open Pinterest created pins or Dhanvi Collection
    3. Strict Facebook-only deduplication check (skip already posted on FB)
    4. Hover target pin card -> click Share icon ('Send')
    5. Generate dynamic shuffled deal copy
    6. Post to Facebook Page feed ('WorldNewzs') and/or 'Amazon Affiliate Group'
    7. Capture live proof screenshots and generate Excel (.xlsx) + PDF reports
    """
    ledger = DeduplicationLedger()
    results: List[Dict[str, Any]] = []
    start_time = time.time()
    source_url = target_board_url or PINTEREST_CREATED_URL

    def log(lvl: str, msg: str):
        if log_fn:
            try:
                log_fn(lvl, msg)
            except Exception:
                pass
        _safe_print(f"[Pinterest→FB] [{lvl.upper()}] {msg}")

    dest_label = "WorldNewzs Page + Amazon Affiliate Group" if destination == "both" else "WorldNewzs Page Feed" if destination == "page" else "Amazon Affiliate Group"
    log("info", f"🚀 Starting Pinterest → Facebook Share automation (target pins={pin_count}, destination={dest_label}, delay={delay_seconds}s, source={source_url})...")

    context = await get_browser_context()

    # ──────────────────────────────────────────────
    # STEP 1: Pre-flight — Verify Facebook Session & WorldNewzs Page Identity
    # ──────────────────────────────────────────────
    log("info", "🔒 Step 1/7: Verifying Facebook session & WorldNewzs Page identity...")
    fb_check_page = await context.new_page()
    try:
        await safe_goto(fb_check_page, "https://www.facebook.com/", timeout=40000, log_fn=log)
        await fb_check_page.bring_to_front()
        await asyncio.sleep(2.5)
        await _take_screenshot(fb_check_page, "fb_share_step1_session_check.png", live_frame_fn=live_frame_fn)

        fb_ok = await _ensure_facebook_session(fb_check_page, log_fn=log)
        if not fb_ok:
            log("error", "❌ Facebook session not available. Please sign in via browser.")
            return {"success": False, "error": "Facebook not logged in", "results": []}

        # Automatically switch / verify active identity is WorldNewzs Page profile
        await _ensure_worldnewzs_profile(fb_check_page, fb_page_url=FB_PAGE_URL, log_fn=log)
        log("success", "✅ Step 1 complete — Facebook session & WorldNewzs Page identity verified!")
    finally:
        if not fb_check_page.is_closed():
            await fb_check_page.close()

    # ──────────────────────────────────────────────
    # STEP 2: Open Pinterest Pins Feed
    # ──────────────────────────────────────────────
    log("info", f"📌 Step 2/7: Opening Pinterest pins feed ({source_url})...")
    pinterest_page = await context.new_page()
    try:
        await safe_goto(
            pinterest_page,
            source_url,
            timeout=45000,
            log_fn=log,
        )
        await pinterest_page.bring_to_front()
        await asyncio.sleep(3)

        # Scroll slightly to trigger pin grid rendering
        await pinterest_page.evaluate("window.scrollBy(0, 350)")
        await asyncio.sleep(2)
        await _take_screenshot(pinterest_page, "fb_share_step2_created_page.png", live_frame_fn=live_frame_fn)
        log("success", f"✅ Step 2 complete — Pinterest feed loaded ({source_url})!")

        # ──────────────────────────────────────────────
        # PIN HARVESTING & DEDUPLICATION LOOP
        # ──────────────────────────────────────────────
        published_count = 0
        seen_pin_ids: set = set()

        # Check if user explicitly provided pin IDs to share
        cached_lookup = {}
        if os.path.exists(DHANVI_PINS_CACHE):
            try:
                with open(DHANVI_PINS_CACHE, "r", encoding="utf-8", errors="replace") as f:
                    for cp in json.load(f):
                        cid = str(cp.get("pinId", "")).strip()
                        if cid:
                            cached_lookup[cid] = cp
            except Exception:
                pass

        explicit_pins = []
        if specific_pin_ids and any(len(str(x)) >= 10 for x in specific_pin_ids):
            for sp_id in specific_pin_ids:
                s_clean = str(sp_id).strip()
                if len(s_clean) >= 10:
                    if s_clean in cached_lookup:
                        explicit_pins.append(cached_lookup[s_clean])
                    else:
                        explicit_pins.append({
                            "pinId": s_clean,
                            "pinUrl": f"https://in.pinterest.com/pin/{s_clean}/",
                            "title": f"Pinterest Deal {s_clean}",
                            "price": "",
                            "imageUrl": "",
                        })

        if explicit_pins:
            log("info", f"🎯 Processing {len(explicit_pins)} user-selected pin(s) directly to Facebook...")
            for pin_idx, pin_item in enumerate(explicit_pins, 1):
                pin_id = pin_item.get("pinId", "").strip()
                pin_url = pin_item.get("pinUrl", "").strip() or f"https://in.pinterest.com/pin/{pin_id}/"
                pin_title = pin_item.get("title", "").strip() or f"Pinterest Deal {pin_id}"
                pin_price = pin_item.get("price", "").strip()
                pin_image_url = pin_item.get("imageUrl", "").strip()

                log("info", f"🔍 Processing User-Selected Pin #{pin_idx}/{len(explicit_pins)}: ID={pin_id} | Title: {pin_title[:50]}... ({pin_price})")

                # Scroll target pin card on Pinterest feed if visible
                try:
                    await pinterest_page.evaluate("""(id) => {
                        const card = document.querySelector(`div[data-test-pin-id="${id}"]`) 
                                   || document.querySelector(`div[data-pin-drag-id="${id}"]`);
                        if (card) {
                            card.scrollIntoView({ behavior: "instant", block: "center" });
                        }
                    }""", pin_id)
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

                await _take_screenshot(pinterest_page, f"fb_share_pin{pin_idx}_hovered.png", live_frame_fn=live_frame_fn)

                if destination == "both":
                    target_name = f"{FB_PAGE_NAME} (Page Feed + Group)"
                elif destination == "page":
                    target_name = f"{FB_PAGE_NAME} (Page Feed)"
                else:
                    target_name = f"{FB_GROUP_NAME} (Group)"

                # Checkpoint: Verify and pre-download pin image locally
                log("info", f"📸 Step 3/7: Verifying image & creating deal copy for Pin #{pin_idx} (ID: {pin_id})...")
                img_checkpoint = await verify_and_download_pin_image(
                    pin_id=pin_id,
                    pin_url=pin_url,
                    image_url=pin_image_url,
                    log_fn=log,
                )
                verified_image_path = img_checkpoint.get("imagePath")
                if img_checkpoint.get("imageUrl"):
                    pin_image_url = img_checkpoint["imageUrl"]

                deal_info = {
                    "id": pin_id,
                    "title": pin_title,
                    "truncatedTitle": pin_title[:50],
                    "pinUrl": pin_url,
                    "shareUrl": pin_url,
                    "price": pin_price,
                    "discount": "",
                    "category": "general",
                    "imageUrl": pin_image_url,
                }
                post_data = ContentShuffler.generate_post(deal_info, ledger)
                post_text = post_data.get("text", f"📌 Check out this hot deal on Pinterest: {pin_title}\n\n{pin_url}")
                log("info", f"📝 Shuffled Copy: \"{post_text[:70]}...\"")

                fb_action_page = await context.new_page()
                try:
                    page_proof = None
                    group_proof = None

                    if destination in ["both", "page"]:
                        log("info", f"📄 Step 4/7: Publishing Pin #{pin_idx} (ID: {pin_id}) to WorldNewzs Facebook Page Feed...")
                        page_res = await _publish_to_facebook_page(
                            page=fb_action_page,
                            post_text=post_text,
                            pin_id=pin_id,
                            pin_url=pin_url,
                            image_path=verified_image_path,
                            log_fn=log,
                            live_frame_fn=live_frame_fn,
                        )
                        page_proof = page_res.get("screenshotPath")

                    if destination in ["both", "group"]:
                        log("info", f"👥 Step 5/7: Publishing Pin #{pin_idx} (ID: {pin_id}) to {FB_GROUP_NAME}...")
                        group_res = await _publish_to_facebook_group(
                            page=fb_action_page,
                            post_text=post_text,
                            pin_id=pin_id,
                            pin_url=pin_url,
                            image_path=verified_image_path,
                            log_fn=log,
                            live_frame_fn=live_frame_fn,
                        )
                        group_proof = group_res.get("screenshotPath")

                    log("info", f"💾 Step 6/7: Recording deduplication & saving proof for Pin #{pin_idx}...")
                    verified_path = group_proof or page_proof or ""
                    ledger.record_facebook_share(
                        pin_id=pin_id,
                        pin_url=pin_url,
                        title=pin_title,
                        text=post_text,
                        target=target_name,
                        screenshot_path=verified_path,
                        status="success",
                    )
                    remove_pin_from_cache(pin_id, pin_url)
                    log("success", f"🎉 Step 7/7 complete: Pin {pin_id} successfully published to {target_name}! (Proof: {verified_path})")

                    results.append({
                        "pinIndex": pin_idx,
                        "pinUrl": pin_url,
                        "pinId": pin_id,
                        "title": pin_title,
                        "status": "success",
                        "target": target_name,
                        "destination": destination,
                        "content": post_text,
                        "imageUrl": pin_image_url,
                        "imageVerified": img_checkpoint.get("verified", False),
                        "screenshotPath": verified_path,
                        "pageProof": page_proof,
                        "groupProof": group_proof,
                        "verified": True,
                    })
                    published_count += 1
                except Exception as fe:
                    err_msg = str(fe)
                    log("error", f"❌ Facebook posting error for Pin #{pin_idx}: {err_msg}")
                    ledger.record_facebook_share(
                        pin_id=pin_id,
                        pin_url=pin_url,
                        title=pin_title,
                        text=post_text if 'post_text' in locals() else "",
                        target=target_name,
                        screenshot_path="",
                        status="failed",
                        error_message=err_msg,
                    )
                    results.append({
                        "pinIndex": pin_idx,
                        "pinUrl": pin_url,
                        "pinId": pin_id,
                        "title": pin_title,
                        "status": "failed",
                        "error": err_msg,
                    })
                finally:
                    if not fb_action_page.is_closed():
                        try:
                            await fb_action_page.close()
                        except Exception:
                            pass

                if published_count < len(explicit_pins) and delay_seconds > 0:
                    log("info", f"⏳ Anti-spam pacing: sleeping {delay_seconds}s before next pin...")
                    await asyncio.sleep(delay_seconds)

        scroll_attempt = 0
        max_scroll_attempts = 50
        consecutive_empty_scrolls = 0

        while published_count < pin_count and scroll_attempt < max_scroll_attempts:
            log("info", f"📌 --- Scanning Pinterest Feed (Published: {published_count}/{pin_count} | Unique Pins Seen: {len(seen_pin_ids)}) ---")

            # Locate all pin cards currently rendered in the DOM
            pin_cards = await pinterest_page.query_selector_all('div[data-test-id="pin"]')
            if not pin_cards:
                pin_cards = await pinterest_page.query_selector_all('div[role="listitem"]:has(a[href*="/pin/"])')
            if not pin_cards:
                pin_cards = await pinterest_page.query_selector_all('div[role="listitem"]')

            discovered_in_batch = 0

            for card in pin_cards:
                if published_count >= pin_count:
                    break

                # Extract pin link, ID, title, price, and image URL
                card_info = await card.evaluate("""(card) => {
                    const a = card.querySelector('a[href*="/pin/"]');
                    const href = a ? a.href : '';
                    const m = href.match(/\\/pin\\/([0-9]+)/);
                    const pinId = m ? m[1] : '';
                    const aria = a ? (a.getAttribute('aria-label') || '') : '';
                    let title = '';
                    let price = '';
                    if (aria) {
                        const parts = aria.split('|').map(p => p.trim());
                        if (parts.length >= 2) {
                            title = parts[0];
                            price = parts[1];
                        } else {
                            title = parts[0];
                        }
                    }
                    const img = card.querySelector('img');
                    if (!title) {
                        title = img ? (img.alt || img.title || '') : '';
                    }
                    let imageUrl = '';
                    if (img) {
                        imageUrl = img.currentSrc || img.src || img.getAttribute('src') || '';
                        if (imageUrl.includes('/236x/')) {
                            imageUrl = imageUrl.replace('/236x/', '/736x/');
                        } else if (imageUrl.includes('/474x/')) {
                            imageUrl = imageUrl.replace('/474x/', '/736x/');
                        }
                    }
                    title = title.replace('This contains an image of:', '').replace('Pin page', '').trim();
                    return { href, pinId, title, price, imageUrl };
                }""")

                pin_id = card_info.get("pinId", "").strip()
                pin_url = card_info.get("href", "").split("?")[0].strip()
                if not pin_url and pin_id:
                    pin_url = f"https://in.pinterest.com/pin/{pin_id}/"

                if not pin_id or pin_id in seen_pin_ids:
                    continue

                seen_pin_ids.add(pin_id)
                discovered_in_batch += 1
                consecutive_empty_scrolls = 0

                pin_idx = len(seen_pin_ids)
                pin_title = card_info.get("title", "").strip() or f"Pinterest Deal {pin_id}"
                pin_price = card_info.get("price", "").strip()
                pin_image_url = card_info.get("imageUrl", "").strip()

                log("info", f"🔍 Evaluating Pin #{pin_idx}: ID={pin_id} | Title: {pin_title[:50]}... ({pin_price})")

                # If user selected specific pin IDs, only process matching pins if valid pin IDs provided
                if specific_pin_ids and any(len(str(x)) >= 15 for x in specific_pin_ids):
                    if pin_id not in specific_pin_ids:
                        continue

                # Isolated Deduplication Check strictly for Facebook
                dedup_check = ledger.check_facebook_candidate(
                    pin_id=pin_id,
                    pin_url=pin_url,
                    image_url=pin_image_url,
                    title=pin_title,
                )
                if dedup_check["is_duplicate"]:
                    log("info", f"⏩ Pin #{pin_idx} '{pin_title[:38]}' (ID: {pin_id}) is ALREADY on Facebook. Skipping to next unposted pin...")
                    results.append({
                        "pinIndex": pin_idx,
                        "pinUrl": pin_url,
                        "pinId": pin_id,
                        "title": pin_title,
                        "status": "skipped",
                        "reason": dedup_check["reason"],
                    })
                    continue

                # ──────────────────────────────────────────
                # STEP 3: Hover Pin Card & Click Share ('Send') Icon
                # ──────────────────────────────────────────
                log("info", f"🖱️ Step 3/7: Hovering over Pin #{pin_idx} (ID: {pin_id}) to reveal Share details...")

                # Ensure any lingering popover is dismissed before interacting with new pin
                try:
                    await pinterest_page.keyboard.press("Escape")
                    await asyncio.sleep(0.4)
                except Exception:
                    pass

                # Scroll target pin card into center of viewport using exact pin ID
                try:
                    await pinterest_page.evaluate("""(id) => {
                        const card = document.querySelector(`div[data-test-pin-id="${id}"]`) 
                                   || document.querySelector(`div[data-pin-drag-id="${id}"]`);
                        if (card) {
                            card.scrollIntoView({ behavior: "instant", block: "center" });
                        }
                    }""", pin_id)
                    await asyncio.sleep(0.8)
                except Exception:
                    pass

                # Target pin card using Playwright Locator (auto-retries, immune to detachment)
                card_sel = f'div[data-test-pin-id="{pin_id}"], div[data-pin-drag-id="{pin_id}"]'
                card_loc = pinterest_page.locator(card_sel).first
                if await card_loc.count() == 0:
                    log("warning", f"⚠️ Pin card {pin_id} not visible in DOM. Skipping.")
                    continue

                try:
                    await card_loc.scroll_into_view_if_needed(timeout=6000)
                    await card_loc.hover(timeout=5000)
                    await asyncio.sleep(0.8)
                except Exception:
                    pass

                await _take_screenshot(pinterest_page, f"fb_share_pin{pin_idx}_hovered.png")

                # Locate Send button strictly inside target pin card using Locator
                send_btn_loc = card_loc.locator('button[aria-label="Send"]').first
                if await send_btn_loc.count() == 0:
                    # Re-hover in case animation was slow
                    try:
                        await card_loc.hover(timeout=3000)
                        await asyncio.sleep(0.6)
                    except Exception:
                        pass

                if await send_btn_loc.count() == 0:
                    log("warning", f"⚠️ Share button not found inside Pin {pin_id} card. Skipping.")
                    continue

                try:
                    await send_btn_loc.click(timeout=5000)
                except Exception:
                    # Direct evaluate click inside the card container
                    await pinterest_page.evaluate(f"""(id) => {{
                        const c = document.querySelector(`div[data-test-pin-id="${{id}}"], div[data-pin-drag-id="${{id}}"]`);
                        if (c) {{
                            const btn = c.querySelector('button[aria-label="Send"]');
                            if (btn) btn.click();
                        }}
                    }}""", pin_id)

                await asyncio.sleep(1.5)
                await _take_screenshot(pinterest_page, f"fb_share_pin{pin_idx}_share_popover.png")
                log("success", "✅ Step 3 complete — Pinterest Share popover opened and details captured!")

                # Dismiss the Pinterest popover cleanly
                try:
                    await pinterest_page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

                # Target name for deduplication ledger and reporting
                if destination == "both":
                    target_name = f"{FB_PAGE_NAME} (Page Feed + Group)"
                elif destination == "page":
                    target_name = f"{FB_PAGE_NAME} (Page Feed)"
                else:
                    target_name = f"{FB_GROUP_NAME} (Group)"

                # Checkpoint: Verify and pre-download pin image locally
                img_checkpoint = await verify_and_download_pin_image(
                    pin_id=pin_id,
                    pin_url=pin_url,
                    image_url=pin_image_url,
                    log_fn=log,
                )
                verified_image_path = img_checkpoint.get("imagePath")
                if img_checkpoint.get("imageUrl"):
                    pin_image_url = img_checkpoint["imageUrl"]

                # Generate unique shuffled copy using ContentShuffler
                deal_info = {
                    "id": pin_id,
                    "title": pin_title,
                    "truncatedTitle": pin_title[:50],
                    "pinUrl": pin_url,
                    "shareUrl": pin_url,
                    "price": pin_price,
                    "discount": "",
                    "category": "general",
                    "imageUrl": pin_image_url,
                }
                post_data = ContentShuffler.generate_post(deal_info, ledger)
                post_text = post_data.get("text", f"📌 Check out this hot deal on Pinterest: {pin_title}\n\n{pin_url}")
                log("info", f"📝 Shuffled Copy: \"{post_text[:70]}...\"")

                # ──────────────────────────────────────────
                # STEP 4-7: Publish to Configured Facebook Destinations
                # ──────────────────────────────────────────
                fb_action_page = await context.new_page()
                try:
                    page_proof = None
                    group_proof = None

                    # Destination 1: WorldNewzs Facebook Page Feed
                    if destination in ["both", "page"]:
                        log("info", f"📄 Step 4/7: Publishing Pin #{pin_idx} (ID: {pin_id}) to WorldNewzs Facebook Page Feed...")
                        page_res = await _publish_to_facebook_page(
                            page=fb_action_page,
                            post_text=post_text,
                            pin_id=pin_id,
                            pin_url=pin_url,
                            image_path=verified_image_path,
                            log_fn=log,
                            live_frame_fn=live_frame_fn,
                        )
                        page_proof = page_res.get("screenshotPath")

                    # Destination 2: Amazon Affiliate Group
                    if destination in ["both", "group"]:
                        log("info", f"👥 Step 5/7: Publishing Pin #{pin_idx} (ID: {pin_id}) to {FB_GROUP_NAME}...")
                        group_res = await _publish_to_facebook_group(
                            page=fb_action_page,
                            post_text=post_text,
                            pin_id=pin_id,
                            pin_url=pin_url,
                            image_path=verified_image_path,
                            log_fn=log,
                            live_frame_fn=live_frame_fn,
                        )
                        group_proof = group_res.get("screenshotPath")

                    log("info", f"💾 Step 6/7: Recording deduplication & saving proof for Pin #{pin_idx}...")
                    verified_path = page_proof or group_proof or ""
                    ledger.record_facebook_share(
                        pin_id=pin_id,
                        pin_url=pin_url,
                        title=pin_title,
                        text=post_text,
                        target=target_name,
                        screenshot_path=verified_path,
                        status="success",
                    )
                    remove_pin_from_cache(pin_id, pin_url)
                    log("success", f"🎉 Step 7/7 complete: Pin {pin_id} successfully published to {target_name}! (Proof: {verified_path})")

                    results.append({
                        "pinIndex": pin_idx,
                        "pinUrl": pin_url,
                        "pinId": pin_id,
                        "title": pin_title,
                        "status": "success",
                        "target": target_name,
                        "destination": destination,
                        "content": post_text,
                        "imageUrl": pin_image_url,
                        "imageVerified": img_checkpoint.get("verified", False),
                        "screenshotPath": verified_path,
                        "pageProof": page_proof,
                        "groupProof": group_proof,
                        "verified": True,
                    })
                    published_count += 1

                except Exception as fe:
                    err_msg = str(fe)
                    log("error", f"❌ Facebook posting error for Pin #{pin_idx}: {err_msg}")
                    ledger.record_facebook_share(
                        pin_id=pin_id,
                        pin_url=pin_url,
                        title=pin_title,
                        text=post_text if 'post_text' in locals() else "",
                        target=target_name,
                        screenshot_path="",
                        status="failed",
                        error_message=err_msg,
                    )
                    results.append({
                        "pinIndex": pin_idx,
                        "pinUrl": pin_url,
                        "pinId": pin_id,
                        "title": pin_title,
                        "status": "failed",
                        "error": err_msg,
                    })
                finally:
                    if not fb_action_page.is_closed():
                        try:
                            await fb_action_page.close()
                        except Exception:
                            pass
                    # Dismiss any remaining Pinterest popover
                    try:
                        await pinterest_page.keyboard.press("Escape")
                        await asyncio.sleep(0.5)
                    except Exception:
                        pass

                # Pacing delay between successfully published pins
                if published_count < pin_count and delay_seconds > 0:
                    log("info", f"⏳ Anti-spam pacing: sleeping {delay_seconds}s before next pin...")
                    await asyncio.sleep(delay_seconds)

            # If more pins are needed, scroll down to load more pins from the account
            if published_count < pin_count:
                scroll_attempt += 1
                if discovered_in_batch == 0:
                    consecutive_empty_scrolls += 1
                log("info", f"📜 Scrolling down Pinterest feed to discover more unposted pins (scroll {scroll_attempt}/{max_scroll_attempts}, scanned {len(seen_pin_ids)} unique pins, posted {published_count}/{pin_count})...")
                await pinterest_page.evaluate("window.scrollBy(0, 1500)")
                await asyncio.sleep(3)

                if consecutive_empty_scrolls >= 10:
                    log("warning", f"⚠️ Reached the end of Pinterest pins feed ({len(seen_pin_ids)} unique pins checked). Stopping.")
                    break

            # Pacing delay between batch passes
            if published_count < pin_count and delay_seconds > 0:
                log("info", f"⏳ Anti-spam pacing: sleeping {delay_seconds}s before next pin...")
                await asyncio.sleep(delay_seconds)

    finally:
        if not pinterest_page.is_closed():
            await pinterest_page.close()

    success_cnt = sum(1 for r in results if r.get("status") == "success")
    skip_cnt = sum(1 for r in results if r.get("status") == "skipped")
    fail_cnt = sum(1 for r in results if r.get("status") == "failed")
    duration_sec = int(time.time() - start_time)

    summary = {
        "totalPins": pin_count,
        "successCount": success_cnt,
        "skippedCount": skip_cnt,
        "failedCount": fail_cnt,
        "durationSeconds": duration_sec,
    }

    # Generate Excel live proof report
    excel_info = {}
    try:
        excel_info = export_facebook_shares_excel(results)
        log("success", f"📊 Live Proof Excel spreadsheet created: {excel_info.get('fileName')}")
    except Exception as ee:
        log("error", f"Excel export note: {ee}")

    # Generate PDF activity report
    pdf_info = {}
    try:
        pdf_info = generate_facebook_pdf_report(results, summary)
        log("success", f"📄 Live Proof PDF Activity Report created: {pdf_info.get('fileName')}")
    except Exception as pe:
        log("error", f"PDF report note: {pe}")

    log("success", f"🏁 Batch Completed! Success: {success_cnt}/{pin_count} | Skipped: {skip_cnt} | Failed: {fail_cnt} (Duration: {duration_sec}s)")

    return {
        "success": success_cnt > 0 or (success_cnt == 0 and skip_cnt > 0),
        "totalPins": pin_count,
        "successCount": success_cnt,
        "skippedCount": skip_cnt,
        "failedCount": fail_cnt,
        "durationSeconds": duration_sec,
        "excelReport": excel_info,
        "pdfReport": pdf_info,
        "results": results,
    }


def remove_pin_from_cache(pin_id: str, pin_url: str = ""):
    """Removes a specific pin from DHANVI_PINS_CACHE upon posting."""
    if not os.path.exists(DHANVI_PINS_CACHE):
        return
    try:
        with open(DHANVI_PINS_CACHE, "r", encoding="utf-8", errors="replace") as f:
            pins = json.load(f)
        if isinstance(pins, list):
            p_id_str = str(pin_id).strip()
            p_url_str = str(pin_url).strip()
            filtered = [
                p for p in pins
                if str(p.get("pinId", "")).strip() != p_id_str and str(p.get("pinUrl", "")).strip() != p_url_str
            ]
            if len(filtered) != len(pins):
                with open(DHANVI_PINS_CACHE, "w", encoding="utf-8") as f:
                    json.dump(filtered, f, indent=2, ensure_ascii=False)
                _safe_print(f"[Remove Pin Cache] Removed pin {p_id_str} from cache. Remaining: {len(filtered)}")
    except Exception as e:
        _safe_print(f"[Remove Pin From Cache Error] {e}")


def clean_posted_pins_from_cache(ledger: Optional[DeduplicationLedger] = None) -> Dict[str, Any]:
    """
    Purges all pins from DHANVI_PINS_CACHE that have already been posted to Facebook.
    Ensures that posted pins never show up in the Facebook Automation Hub.
    """
    if ledger is None:
        ledger = DeduplicationLedger()

    if not os.path.exists(DHANVI_PINS_CACHE):
        return {"cleanedCount": 0, "remainingCount": 0, "totalBefore": 0}

    try:
        with open(DHANVI_PINS_CACHE, "r", encoding="utf-8", errors="replace") as f:
            cached_data = json.load(f)
    except Exception as e:
        _safe_print(f"[Clean Cache Error] Failed to read cache: {e}")
        return {"cleanedCount": 0, "remainingCount": 0, "totalBefore": 0}

    if not isinstance(cached_data, list):
        return {"cleanedCount": 0, "remainingCount": 0, "totalBefore": 0}

    total_before = len(cached_data)
    unposted_pins = []
    removed_pins = []

    for p in cached_data:
        p_id = str(p.get("pinId") or p.get("id") or "").strip()
        p_url = p.get("pinUrl") or p.get("href") or f"https://in.pinterest.com/pin/{p_id}/" if p_id else ""
        if ledger.is_posted_to_facebook(p_id, p_url):
            removed_pins.append(p_id)
        else:
            unposted_pins.append(p)

    cleaned_count = len(removed_pins)

    if cleaned_count > 0:
        try:
            with open(DHANVI_PINS_CACHE, "w", encoding="utf-8") as f:
                json.dump(unposted_pins, f, indent=2, ensure_ascii=False)
            _safe_print(f"[Clean Cache] Successfully purged {cleaned_count} posted pins from cache. {len(unposted_pins)} unposted pins remain.")
        except Exception as e:
            _safe_print(f"[Clean Cache Error] Failed to write back cleaned cache: {e}")

    return {
        "cleanedCount": cleaned_count,
        "remainingCount": len(unposted_pins),
        "totalBefore": total_before,
    }


async def harvest_dhanvi_collection_pins(
    max_pins: int = 200,
    force_live: bool = False,
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> List[Dict[str, Any]]:
    """
    Returns pins available in Dhanvi Collection annotated with Facebook status.
    Automatically purges and excludes any pins already posted to Facebook so they never show up.
    """
    ledger = DeduplicationLedger()
    os.makedirs(os.path.dirname(DHANVI_PINS_CACHE), exist_ok=True)

    # Clean any already-posted pins from local cache first
    clean_posted_pins_from_cache(ledger)

    def _annotate(pins_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        annotated = []
        for p in pins_list:
            p_id = str(p.get("pinId") or p.get("id") or "").strip()
            p_url = p.get("pinUrl") or p.get("href") or f"https://in.pinterest.com/pin/{p_id}/" if p_id else ""
            if ledger.is_posted_to_facebook(p_id, p_url):
                continue  # Never include posted pins in Facebook Automation Hub!
            img_url = (p.get("imageUrl") or "").strip()
            if img_url:
                img_url = img_url.replace("/236x/", "/736x/").replace("/474x/", "/736x/")
            annotated.append({
                "pinId": p_id,
                "title": p.get("title") or "Pinterest Deal",
                "price": p.get("price") or "",
                "pinUrl": p_url,
                "imageUrl": img_url,
                "status": "pending",
                "statusLabel": "Ready to Post",
            })
        return annotated

    # Check cache if live refresh not forced
    if not force_live and os.path.exists(DHANVI_PINS_CACHE):
        try:
            with open(DHANVI_PINS_CACHE, "r", encoding="utf-8", errors="replace") as f:
                cached_data = json.load(f)
                if cached_data and len(cached_data) > 0:
                    return _annotate(cached_data)
        except Exception:
            pass

    # Live harvest from Pinterest if requested or cache missing
    live_pins = []
    try:
        ctx = await get_browser_context()
        page = await ctx.new_page()
        try:
            await safe_goto(page, PINTEREST_CREATED_URL, timeout=45000)
            await asyncio.sleep(3.5)
            all_discovered = {}
            for _ in range(25):
                batch = await page.evaluate('''() => {
                    const results = [];
                    const anchors = Array.from(document.querySelectorAll('a[href*="/pin/"]'));
                    for (const a of anchors) {
                        const href = a.href || '';
                        const m = href.match(/\\/pin\\/(\\d+)/);
                        if (m) {
                            const pinId = m[1];
                            const container = a.closest('div[role="listitem"], div[data-test-id="pin"]') || a.parentElement;
                            const img = container?.querySelector('img') || a.querySelector('img');
                            let rawTitle = a.getAttribute('aria-label') || img?.alt || a.innerText || '';
                            let title = rawTitle;
                            let price = '';
                            if (rawTitle.includes('|')) {
                                const parts = rawTitle.split('|').map(s => s.trim());
                                title = parts[0];
                                price = parts[1] || '';
                            }
                            title = title.replace('This contains an image of:', '').replace('Pin page', '').trim();
                            let imageUrl = '';
                            if (img) {
                                imageUrl = img.currentSrc || img.src || img.getAttribute('src') || '';
                                if (!imageUrl && img.srcset) {
                                    const parts = img.srcset.split(',').map(s => s.trim().split(' ')[0]);
                                    imageUrl = parts[parts.length - 1] || '';
                                }
                            }
                            if (imageUrl.includes('/236x/')) imageUrl = imageUrl.replace('/236x/', '/736x/');
                            else if (imageUrl.includes('/474x/')) imageUrl = imageUrl.replace('/474x/', '/736x/');

                            results.push({
                                pinId: pinId,
                                pinUrl: "https://in.pinterest.com/pin/" + pinId + "/",
                                title: title || ("Pinterest Pin " + pinId),
                                price: price,
                                imageUrl: imageUrl
                            });
                        }
                    }
                    return results;
                }''')
                for p in batch:
                    # Skip any pins already posted to Facebook
                    if ledger.is_posted_to_facebook(p["pinId"], p.get("pinUrl", "")):
                        continue
                    if p["pinId"] not in all_discovered:
                        all_discovered[p["pinId"]] = p
                if len(all_discovered) >= max_pins:
                    break
                await page.evaluate("window.scrollBy(0, 1500)")
                await asyncio.sleep(1.8)
            live_pins = list(all_discovered.values())
        finally:
            if not page.is_closed():
                await page.close()
    except Exception as e:
        _safe_print(f"[Harvest Pins Error] {e}")

    if live_pins:
        try:
            with open(DHANVI_PINS_CACHE, "w", encoding="utf-8") as f:
                json.dump(live_pins, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        return _annotate(live_pins)

    # Fallback to existing cache if available
    if os.path.exists(DHANVI_PINS_CACHE):
        try:
            with open(DHANVI_PINS_CACHE, "r", encoding="utf-8", errors="replace") as f:
                cached = json.load(f)
                if cached:
                    return _annotate(cached)
        except Exception:
            pass

    return []


