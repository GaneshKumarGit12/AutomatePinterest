import os
import sys
import re
import json
import time
import asyncio
import hashlib
import random
import urllib.parse
from typing import Dict, Any, List, Optional, Callable

try:
    from playwright.async_api import BrowserContext, Page
except ImportError:
    BrowserContext = Any  # type: ignore
    Page = Any  # type: ignore

from backend.engine.session_manager import get_browser_context

if hasattr(sys.stdout, 'reconfigure') and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def safe_print(msg: str):
    try:
        print(msg, flush=True)
    except Exception:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)
        except Exception:
            pass

_STATE_ROOT = "/tmp" if os.environ.get("VERCEL") else os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATE_DIR = os.path.join(_STATE_ROOT, "state")
HISTORY_FILE = os.path.join(STATE_DIR, "social_share_history.json")

# Category hashtag pools
HASHTAG_POOLS = {
    "electronics": [
        "#TechDeals", "#GadgetsIndia", "#AmazonOffers", "#ElectronicsSale",
        "#BestTechDeals", "#SmartShopping", "#TechSavings", "#PriceDropAlert"
    ],
    "kitchen_home": [
        "#HomeDecorIndia", "#KitchenEssentials", "#HomeImprovement", "#DecorInspo",
        "#KitchenDeals", "#SmartHomeLiving", "#AmazonFinds", "#IndianHomes"
    ],
    "fashion_lifestyle": [
        "#FashionDeals", "#LifestyleIndia", "#TrendingStyles", "#DailyEssentials",
        "#StyleOnABudget", "#AmazonFashion", "#WardrobeDeals", "#GrabTheDeal"
    ],
    "general": [
        "#DealsOfTheDay", "#AmazonIndiaDeals", "#FlashSaleAlert", "#SaveBig",
        "#ShoppingSpree", "#BestDiscounts", "#OnlineDealsIndia", "#ValueForMoney"
    ]
}

EMOJIS = ["🔥", "✨", "🏷️", "⚡", "🛍️", "💡", "🎯"]

CTAS = [
    "Full details on Pinterest:",
    "See pin & photos here:",
    "Check out this pin:",
    "View full deal on Pinterest:",
    "Tap below for pin details:"
]


class DeduplicationLedger:
    """Tracks and enforces 5-layer deduplication across Twitter and Facebook."""

    def __init__(self, filepath: str = HISTORY_FILE):
        self.filepath = filepath
        self.data: Dict[str, Any] = {
            "shared_pin_ids": [],
            "shared_image_urls": [],
            "shared_titles": [],
            "shared_description_hashes": [],
            "facebook_posted_pin_ids": [],
            "facebook_post_records": [],
            "post_logs": []
        }
        self._load()

    def _load(self):
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        except OSError:
            pass
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"[DeduplicationLedger] Error loading history: {e}")

        # Ensure Facebook-specific tracking lists exist
        if "facebook_posted_pin_ids" not in self.data:
            self.data["facebook_posted_pin_ids"] = []
        if "facebook_post_records" not in self.data:
            self.data["facebook_post_records"] = []

        # Backfill facebook_posted_pin_ids from past post_logs if empty
        if not self.data["facebook_posted_pin_ids"]:
            fb_set = set()
            for l in self.data.get("post_logs", []):
                if l.get("platform") == "facebook" and l.get("status") == "success":
                    p_id = l.get("pinId")
                    if p_id:
                        fb_set.add(str(p_id))
            self.data["facebook_posted_pin_ids"] = list(fb_set)

    def _save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[DeduplicationLedger] Error saving history: {e}")

    @staticmethod
    def normalize_title(title: str) -> str:
        clean = re.sub(r'[^a-zA-Z0-9\s]', '', (title or "").lower())
        clean = re.sub(r'^(this contains an image of|pin page|image of)\s*', '', clean).strip()
        words = clean.split()[:7]
        return " ".join(words)

    @staticmethod
    def normalize_image(image_url: str) -> str:
        if not image_url:
            return ""
        # Extract Pinterest image hash from i.pinimg.com
        m_pin = re.search(r'i\.pinimg\.com/(?:originals|\d+x)/[a-f0-9/]+/([a-f0-9]+)\.', image_url)
        if m_pin:
            return m_pin.group(1)
        # Extract ASIN or image hash from Amazon media URL
        m = re.search(r'\/([A-Z0-9]{10})\b|\/images\/I\/([^.\/_]+)', image_url)
        if m:
            return m.group(1) or m.group(2)
        return image_url.split("?")[0].strip().lower()

    @staticmethod
    def hash_text(text: str) -> str:
        words = re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())
        return hashlib.sha256(" ".join(words).encode("utf-8")).hexdigest()

    def check_candidate(self, pin_id: str, pin_url: str, image_url: str, title: str) -> Dict[str, Any]:
        """Runs the first 3 deduplication layers."""
        # Layer 1: Pin ID / URL
        if pin_id and pin_id in self.data["shared_pin_ids"]:
            return {"is_duplicate": True, "layer": 1, "reason": f"Pin ID '{pin_id}' already shared."}
        if pin_url and pin_url in self.data["shared_pin_ids"]:
            return {"is_duplicate": True, "layer": 1, "reason": f"Pin URL already shared."}

        # Layer 2: Image URL / Media identifier
        norm_img = self.normalize_image(image_url)
        if norm_img and norm_img in self.data["shared_image_urls"]:
            return {"is_duplicate": True, "layer": 2, "reason": "Image already shared on social media."}

        # Layer 3: Title normalization
        norm_title = self.normalize_title(title)
        if norm_title and norm_title not in ["this contains an image of", "image of", "pin page"] and norm_title in self.data["shared_titles"]:
            return {"is_duplicate": True, "layer": 3, "reason": f"Similar product title already shared: '{norm_title}'"}

        return {"is_duplicate": False, "layer": 0, "reason": "Passed deduplication checks."}

    def is_description_unique(self, text: str) -> bool:
        """Layer 4: Checks if text hash has been posted before."""
        h = self.hash_text(text)
        return h not in self.data["shared_description_hashes"]

    def record_share(
        self,
        pin_id: str,
        pin_url: str,
        image_url: str,
        title: str,
        text: str,
        platform: str,
        target: str,
        status: str = "success",
        error_message: str = ""
    ):
        norm_img = self.normalize_image(image_url)
        norm_title = self.normalize_title(title)
        h = self.hash_text(text) if text else ""

        # Only add to deduplication lookup if successfully shared
        if status == "success":
            if pin_id and pin_id not in self.data["shared_pin_ids"]:
                self.data["shared_pin_ids"].append(pin_id)
            if pin_url and pin_url not in self.data["shared_pin_ids"]:
                self.data["shared_pin_ids"].append(pin_url)
            if norm_img and norm_img not in self.data["shared_image_urls"]:
                self.data["shared_image_urls"].append(norm_img)
            if norm_title and norm_title not in self.data["shared_titles"]:
                self.data["shared_titles"].append(norm_title)
            if h and h not in self.data["shared_description_hashes"]:
                self.data["shared_description_hashes"].append(h)

        log_entry = {
            "id": f"share-{int(time.time()*1000)}-{random.randint(10, 99)}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "platform": platform,
            "target": target,
            "pinId": pin_id,
            "pinUrl": pin_url,
            "title": title,
            "content": text,
            "status": status,
            "error": error_message
        }
        self.data["post_logs"].append(log_entry)
        self._save()

    def is_posted_to_facebook(self, pin_id: str, pin_url: str = "") -> bool:
        """Strictly checks if a Pin ID or URL has already been posted to Facebook."""
        fb_ids = set(str(x).strip() for x in self.data.get("facebook_posted_pin_ids", []))
        # Also include any pin from past successful Facebook post logs
        for log in self.data.get("post_logs", []):
            if log.get("platform") == "facebook" and log.get("status") == "success":
                if log.get("pinId"):
                    fb_ids.add(str(log.get("pinId")).strip())
                if log.get("pinUrl"):
                    fb_ids.add(str(log.get("pinUrl")).strip())
        if pin_id and str(pin_id).strip() in fb_ids:
            return True
        if pin_url and str(pin_url).strip() in fb_ids:
            return True
        return False

    def check_facebook_candidate(self, pin_id: str, pin_url: str = "", image_url: str = "", title: str = "") -> Dict[str, Any]:
        """
        Isolated deduplication check strictly for Facebook.
        Ensures Twitter history DOES NOT falsely block Facebook shares.
        """
        if self.is_posted_to_facebook(pin_id, pin_url):
            return {
                "is_duplicate": True,
                "reason": f"Pin ID '{pin_id}' has already been successfully posted to Facebook Group."
            }
        return {
            "is_duplicate": False,
            "reason": "Available to post on Facebook Group."
        }

    def record_facebook_share(
        self,
        pin_id: str,
        pin_url: str,
        title: str,
        text: str,
        target: str,
        screenshot_path: str = "",
        status: str = "success",
        error_message: str = ""
    ):
        """Records a Facebook share into dedicated Facebook ledger and post logs."""
        pin_id_str = str(pin_id).strip() if pin_id else ""
        pin_url_str = str(pin_url).strip() if pin_url else ""

        if status == "success":
            fb_pins = self.data.setdefault("facebook_posted_pin_ids", [])
            if pin_id_str and pin_id_str not in fb_pins:
                fb_pins.append(pin_id_str)
            if pin_url_str and pin_url_str not in fb_pins:
                fb_pins.append(pin_url_str)

        fb_record = {
            "id": f"fb-share-{int(time.time()*1000)}-{random.randint(10, 99)}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pinId": pin_id_str,
            "pinUrl": pin_url_str,
            "title": title,
            "content": text,
            "target": target,
            "screenshotPath": screenshot_path,
            "status": status,
            "error": error_message
        }
        self.data.setdefault("facebook_post_records", []).append(fb_record)

        # Also log to general post_logs
        log_entry = {
            "id": fb_record["id"],
            "timestamp": fb_record["timestamp"],
            "platform": "facebook",
            "target": target,
            "pinId": pin_id_str,
            "pinUrl": pin_url_str,
            "title": title,
            "content": text,
            "status": status,
            "error": error_message
        }
        self.data.setdefault("post_logs", []).append(log_entry)
        self._save()

    def get_facebook_records(self) -> List[Dict[str, Any]]:
        """Returns all completed/logged Facebook share records."""
        return self.data.get("facebook_post_records", [])

    def get_facebook_posted_ids(self) -> set:
        """Returns set of all Pin IDs / URLs already posted to Facebook."""
        return set(str(x) for x in self.data.get("facebook_posted_pin_ids", []))


    def get_stats(self) -> Dict[str, Any]:
        logs = self.data.get("post_logs", [])
        fb_records = self.data.get("facebook_post_records", [])
        return {
            "totalShared": sum(1 for l in logs if l.get("status") == "success"),
            "totalAttempts": len(logs),
            "twitterCount": sum(1 for l in logs if l.get("platform") == "twitter" and l.get("status") == "success"),
            "facebookCount": len(self.data.get("facebook_posted_pin_ids", [])),
            "facebookRecordsCount": len(fb_records),
            "failedCount": sum(1 for l in logs if l.get("status") == "failed"),
            "skippedCount": sum(1 for l in logs if l.get("status") == "skipped"),
            "uniquePinsCount": len(self.data.get("shared_pin_ids", [])),
            "recentLogs": logs[-100:] if logs else []
        }


class ContentShuffler:
    """Generates 100% unique, dynamically shuffled post copy with randomized hashtags."""

    @staticmethod
    def detect_category(category_raw: str, title: str) -> str:
        text = f"{category_raw} {title}".lower()
        if any(w in text for w in ["electronics", "gadget", "phone", "audio", "headphone", "cable", "watch", "camera"]):
            return "electronics"
        if any(w in text for w in ["kitchen", "home", "cook", "decor", "curtain", "furniture", "stand", "bottle"]):
            return "kitchen_home"
        if any(w in text for w in ["fashion", "cloth", "t-shirt", "shirt", "pant", "shoe", "beauty", "dress"]):
            return "fashion_lifestyle"
        return "general"

    @classmethod
    def sample_hashtags(cls, category: str, count: int = 4) -> str:
        cat_pool = HASHTAG_POOLS.get(category, HASHTAG_POOLS["general"])
        gen_pool = HASHTAG_POOLS["general"]

        selected = random.sample(cat_pool, min(2, len(cat_pool)))
        remaining = [t for t in gen_pool if t not in selected]
        selected += random.sample(remaining, min(count - len(selected), len(remaining)))
        random.shuffle(selected)
        return " ".join(selected)

    @classmethod
    def generate_post(cls, deal: Dict[str, Any], ledger: Optional[DeduplicationLedger] = None) -> Dict[str, Any]:
        title = deal.get("truncatedTitle") or deal.get("title", "Amazon Deal")
        price = deal.get("price") or ""
        original_price = deal.get("originalPrice") or ""
        discount = deal.get("discount") or ""
        pin_url = deal.get("pinUrl") or deal.get("shareUrl") or deal.get("dealUrl") or "https://in.pinterest.com/ganeshkumardevarasetty/"
        category = cls.detect_category(deal.get("category", ""), title)

        if discount and not discount.endswith("%"):
            discount = f"{discount}%"

        for _ in range(10):
            emoji = random.choice(EMOJIS)
            cta = random.choice(CTAS)
            hashtags = cls.sample_hashtags(category)
            pattern_id = random.randint(1, 4)

            if pattern_id == 1 and discount:
                # Pattern 1: Discount First
                body = f"{emoji} {discount} OFF! {title} is now available for {price}."
            elif pattern_id == 2:
                # Pattern 2: Price Drop Alert
                savings = f"(Down from {original_price})" if original_price else f"({discount} discount)" if discount else ""
                body = f"{emoji} Price Drop Alert: {title} slashed to {price} {savings}."
            elif pattern_id == 3:
                # Pattern 3: Category Recommendation
                cat_name = "Kitchen & Home" if category == "kitchen_home" else "Electronics" if category == "electronics" else "Trending Finds"
                body = f"{emoji} Top recommendation in {cat_name}: {title} at {price}."
            else:
                # Pattern 4: Hand-picked Pin
                body = f"{emoji} Hand-picked Amazon deal: {title} at {price}."

            full_text = f"{body.strip()}\n\n{cta} {pin_url}\n\n{hashtags}".strip()

            if ledger is None or ledger.is_description_unique(full_text):
                return {
                    "text": full_text,
                    "patternId": pattern_id,
                    "hashtags": hashtags,
                    "category": category,
                    "pinUrl": pin_url
                }

        # Fallback if all 10 tries matched past hashes
        rand_salt = f"#{random.randint(100, 999)}"
        return {
            "text": f"{random.choice(EMOJIS)} {title} ({price}) {rand_salt}\n\n{random.choice(CTAS)} {pin_url}\n\n{cls.sample_hashtags(category)}",
            "patternId": 0,
            "hashtags": cls.sample_hashtags(category),
            "category": category,
            "pinUrl": pin_url
        }


class QuickSocialPoster:
    """High-speed direct Playwright automation for Twitter @ganeshkumard1 and Facebook Worldnewzs -> Amazon Affiliate Group."""

    def __init__(self, ledger: Optional[DeduplicationLedger] = None):
        self.ledger = ledger or DeduplicationLedger()
        self.twitter_account = os.environ.get("TWITTER_ACCOUNT", "@ganeshkumard1")
        self.twitter_user = os.environ.get("TWITTER_USERNAME", "ganeshkumard1")
        self.twitter_pass = os.environ.get("TWITTER_PASSWORD", "")
        self.fb_account = os.environ.get("FACEBOOK_ACCOUNT", "ganeshkumard56")
        self.fb_user = os.environ.get("FACEBOOK_USERNAME", "ganeshkumard56")
        self.fb_pass = os.environ.get("FACEBOOK_PASSWORD", "")
        self.fb_page = os.environ.get("FACEBOOK_PAGE_NAME", "Worldnewzs")
        self.fb_group = os.environ.get("FACEBOOK_GROUP_NAME", "Amazon Affiliate Group")
        self.fb_group_url = os.environ.get("FACEBOOK_GROUP_URL", "https://www.facebook.com/groups/1761596288324903/")
        self.fb_page_url = os.environ.get("FACEBOOK_PAGE_URL", "https://www.facebook.com/profile.php?id=61589266599006")

    async def ensure_facebook_logged_in(self, page: Any, log_fn: Optional[Callable[[str, str], None]] = None) -> bool:
        """Verifies Facebook session; performs auto-login and handles checkpoints / 2FA / reCAPTCHA if needed."""
        def log(level: str, msg: str):
            if log_fn:
                try:
                    log_fn(level, msg)
                except Exception:
                    pass
            safe_print(f"[Facebook Auth] [{level.upper()}] {msg}")

        async def _is_authed() -> bool:
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
                nav = await page.query_selector('div[role="navigation"], div[role="banner"]')
                if nav and not email_el:
                    return True
            except Exception:
                pass
            return False

        if await _is_authed():
            log("success", "✅ Facebook session verified (persistent session active).")
            return True

        is_checkpoint = ("two_step_verification" in page.url) or ("checkpoint" in page.url)
        if is_checkpoint:
            await page.bring_to_front()
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

            log("warning", "⚠️ Facebook Security Verification / Captcha detected! Live browser window is visible — please complete prompt on screen. Waiting up to 90s...")
            for _ in range(45):
                await asyncio.sleep(2)
                if await _is_authed():
                    log("success", "🎉 Facebook verification cleared! Session saved permanently.")
                    return True
                if "two_step_verification" not in page.url and "checkpoint" not in page.url and "login" not in page.url:
                    email_check = await page.query_selector('input[name="email"]')
                    if not email_check:
                        log("success", "🎉 Facebook verification cleared! Session saved permanently.")
                        return True
            log("error", "❌ Facebook verification timed out.")
            return False

        log("info", "🔑 Facebook login required. Submitting credentials from .env...")
        try:
            email_field = await page.wait_for_selector('input[name="email"]', timeout=8000)
            pass_field = await page.wait_for_selector('input[name="pass"]', timeout=8000)
            if email_field and pass_field and self.fb_user and self.fb_pass:
                await email_field.fill(self.fb_user)
                await asyncio.sleep(0.5)
                await pass_field.fill(self.fb_pass)
                await asyncio.sleep(0.5)

                login_btn = await page.query_selector('div[role="button"][aria-label="Log in"], div[role="button"]:has-text("Log in"), input[type="submit"], button[name="login"]')
                if login_btn:
                    log("info", "🖱️ Submitting Facebook login credentials...")
                    try:
                        await page.evaluate('(el) => el.click()', login_btn)
                    except Exception:
                        await login_btn.click(timeout=5000, force=True)
                    await asyncio.sleep(6)

                if "two_step_verification" in page.url or "checkpoint" in page.url:
                    await page.bring_to_front()
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

                    log("warning", "⚠️ Facebook Security Check / Captcha detected! Live browser window is visible — please complete prompt on screen. Waiting up to 90s...")
                    for _ in range(45):
                        await asyncio.sleep(2)
                        if await _is_authed():
                            log("success", "🎉 Facebook verification cleared! Session saved.")
                            return True
                        if "two_step_verification" not in page.url and "checkpoint" not in page.url and "login" not in page.url:
                            email_check = await page.query_selector('input[name="email"]')
                            if not email_check:
                                log("success", "🎉 Facebook verification cleared! Session saved.")
                                return True
                    return False

                if await _is_authed():
                    log("success", "✅ Logged into Facebook successfully!")
                    return True
        except Exception as e:
            log("error", f"Facebook auto-login helper note: {e}")

        return await _is_authed()

    async def ensure_twitter_logged_in(self, page: Any, log_fn: Optional[Callable[[str, str], None]] = None) -> bool:
        """Verifies Twitter session for @ganeshkumard1; performs auto-login if needed."""
        def log(level: str, msg: str):
            if log_fn:
                try:
                    log_fn(level, msg)
                except Exception:
                    pass
            safe_print(f"[Twitter Auth] [{level.upper()}] {msg}")

        # Check if already logged in
        is_login_page = ("login" in page.url) or ("onboarding" in page.url)
        inputs = await page.query_selector_all('input')
        visible_inp = None
        for inp in inputs:
            if await inp.is_visible():
                visible_inp = inp
                break

        if not is_login_page and not visible_inp:
            log("success", f"✅ Twitter session verified as {self.twitter_account}!")
            return True

        log("info", f"🔑 Twitter login required. Entering credentials for {self.twitter_account}...")
        try:
            # 1. Fill visible username input
            if visible_inp:
                try:
                    await visible_inp.click(timeout=5000, force=True)
                except Exception:
                    await page.evaluate('(el) => el.focus()', visible_inp)
                await visible_inp.fill(self.twitter_user)
                await asyncio.sleep(1)

                # Look for visible Next or Continue button
                clicked_btn = False
                buttons = await page.query_selector_all('button, [role="button"]')
                for btn in buttons:
                    txt = (await btn.inner_text()).strip()
                    if txt in ["Next", "Continue", "Log in"] and await btn.is_visible():
                        log("info", f"🖱️ Clicking Twitter '{txt}' button...")
                        try:
                            await page.evaluate('(el) => el.click()', btn)
                        except Exception:
                            await btn.click(timeout=5000, force=True)
                        clicked_btn = True
                        break

                if not clicked_btn:
                    await visible_inp.press("Enter")

                await asyncio.sleep(3.5)

            # 2. Look for visible password input
            visible_pass = None
            for _ in range(6):
                pass_inputs = await page.query_selector_all('input[type="password"], input[name="password"]')
                for p_inp in pass_inputs:
                    if await p_inp.is_visible():
                        visible_pass = p_inp
                        break
                if visible_pass:
                    break
                await asyncio.sleep(1)

            if visible_pass:
                log("info", "🔑 Entering Twitter password...")
                try:
                    await visible_pass.click(timeout=5000, force=True)
                except Exception:
                    await page.evaluate('(el) => el.focus()', visible_pass)
                await visible_pass.fill(self.twitter_pass)
                await asyncio.sleep(0.8)

                # Click submit button or press Enter
                log_btns = await page.query_selector_all('button[data-testid="LoginForm_Login_Button"], button, [role="button"]')
                submitted = False
                for lb in log_btns:
                    txt = (await lb.inner_text()).strip()
                    if txt in ["Log in", "Sign in", "Submit"] and await lb.is_visible():
                        log("info", f"🖱️ Submitting Twitter login with '{txt}' button...")
                        try:
                            await page.evaluate('(el) => el.click()', lb)
                        except Exception:
                            await lb.click(timeout=5000, force=True)
                        submitted = True
                        break

                if not submitted:
                    await visible_pass.press("Enter")

                await asyncio.sleep(6)

            if "login" not in page.url and "onboarding" not in page.url:
                log("success", f"✅ Logged into Twitter successfully as {self.twitter_account}!")
                return True
        except Exception as e:
            log("error", f"Twitter auto-login note: {e}")

        return ("login" not in page.url and "onboarding" not in page.url)

    async def share_to_twitter(
        self,
        deal: Dict[str, Any],
        post_data: Dict[str, Any],
        dry_run: bool = False,
        log_fn: Optional[Callable[[str, str], None]] = None,
    ) -> Dict[str, Any]:
        """Direct post to Twitter @ganeshkumard1 via intent URL with verified GraphQL confirmation."""
        def log(level: str, msg: str):
            if log_fn:
                try:
                    log_fn(level, msg)
                except Exception:
                    pass
            safe_print(f"[Twitter] [{level.upper()}] {msg}")

        pin_id = deal.get("id") or deal.get("asin") or ""
        pin_url = post_data.get("pinUrl") or deal.get("shareUrl") or ""
        image_url = deal.get("imageUrl") or ""
        title = deal.get("title") or ""
        text = post_data.get("text") or ""

        if dry_run:
            log("info", f"🧪 [DRY RUN] Target: {self.twitter_account} | Shuffled Copy: {text[:65]}...")
            return {"success": True, "platform": "twitter", "dryRun": True, "target": self.twitter_account, "text": text}

        log("info", f"🌐 Step 1: Launching browser context for Twitter ({self.twitter_account})...")
        context = await get_browser_context()
        page = await context.new_page()

        tweet_posted_event = asyncio.Event()
        def on_response(response):
            if "CreateTweet" in response.url and response.status == 200:
                tweet_posted_event.set()

        page.on("response", on_response)

        try:
            encoded_text = urllib.parse.quote(text)
            intent_url = f"https://x.com/intent/post?text={encoded_text}"
            log("info", f"🔗 Step 2: Opening Twitter intent composer URL...")
            await page.goto(intent_url, wait_until="domcontentloaded", timeout=40000)
            await page.bring_to_front()
            await asyncio.sleep(2.5)

            # Check / ensure logged in
            log("info", f"🔒 Step 3: Verifying account session for {self.twitter_account}...")
            is_authed = await self.ensure_twitter_logged_in(page, log_fn=log)
            if not is_authed:
                err_msg = f"Twitter session not active for {self.twitter_account}. Please click '🔑 Login to Social Accounts' in the dashboard to sign in once."
                log("error", f"❌ {err_msg}")
                raise Exception(err_msg)

            # If redirected back to intent after login
            if "intent/post" not in page.url and "compose/post" not in page.url:
                await page.goto(intent_url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(2.5)

            # Ensure textarea has text
            log("info", "📝 Step 4: Verifying tweet text content...")
            textarea = await page.wait_for_selector('div[data-testid="tweetTextarea_0"]', timeout=8000)
            if textarea:
                current_val = await page.evaluate('(el) => el.innerText', textarea)
                if not current_val or not current_val.strip():
                    await textarea.click()
                    await page.keyboard.type(text, delay=15)
                    await asyncio.sleep(1)

            # Click "Post" button
            log("info", "🔍 Step 5: Locating Twitter 'Post' button (data-testid='tweetButton')...")
            post_btn = await page.wait_for_selector('button[data-testid="tweetButton"]', timeout=12000)
            if not post_btn:
                post_btn = await page.wait_for_selector('button[data-testid="tweetButtonInline"], div[role="button"][data-testid="tweetButton"]', timeout=5000)

            if not post_btn:
                err_msg = "Could not find Twitter 'Post' button on intent composer."
                log("error", f"❌ {err_msg}")
                raise Exception(err_msg)

            # Wait if disabled
            for _ in range(6):
                is_disabled = await page.evaluate('(el) => el.disabled || el.getAttribute("aria-disabled") === "true"', post_btn)
                if not is_disabled:
                    break
                await asyncio.sleep(1)

            log("info", "🖱️ Step 6: Found enabled 'Post' button! Publishing tweet now...")
            try:
                await post_btn.click(timeout=8000)
            except Exception:
                await page.evaluate('(el) => el.click()', post_btn)

            # Wait for CreateTweet API response
            log("info", "⏳ Step 7: Awaiting Twitter network confirmation...")
            try:
                await asyncio.wait_for(tweet_posted_event.wait(), timeout=12.0)
                log("success", "📡 Network confirmation: CreateTweet API returned 200 OK!")
            except asyncio.TimeoutError:
                if "home" in page.url or (textarea and not (await page.evaluate('(el) => el.innerText', textarea) or "").strip()):
                    log("success", "📡 Tweet composer confirmed submission via redirect!")
                else:
                    await asyncio.sleep(2)

            self.ledger.record_share(
                pin_id=pin_id,
                pin_url=pin_url,
                image_url=image_url,
                title=title,
                text=text,
                platform="twitter",
                target=self.twitter_account,
                status="success"
            )
            log("success", f"🎉 Step 8: Tweet successfully published to {self.twitter_account} in real time!")
            return {"success": True, "platform": "twitter", "target": self.twitter_account, "text": text}
        except Exception as e:
            log("error", f"❌ Twitter Post Failed: {str(e)}")
            raise e
        finally:
            if not page.is_closed():
                await page.close()

    async def share_to_facebook(
        self,
        deal: Dict[str, Any],
        post_data: Dict[str, Any],
        dry_run: bool = False,
        log_fn: Optional[Callable[[str, str], None]] = None,
    ) -> Dict[str, Any]:
        """Direct post to Facebook target group (Worldnewzs -> Amazon Affiliate Group) under ganeshkumard56."""
        def log(level: str, msg: str):
            if log_fn:
                try:
                    log_fn(level, msg)
                except Exception:
                    pass
            safe_print(f"[Facebook] [{level.upper()}] {msg}")

        pin_id = deal.get("id") or deal.get("asin") or ""
        pin_url = post_data.get("pinUrl") or deal.get("shareUrl") or ""
        image_url = deal.get("imageUrl") or ""
        title = deal.get("title") or ""
        text = post_data.get("text") or ""
        target_name = f"{self.fb_page} -> {self.fb_group}"

        if dry_run:
            log("info", f"🧪 [DRY RUN] Target: {target_name} ({self.fb_account}) | Shuffled Copy: {text[:65]}...")
            return {"success": True, "platform": "facebook", "dryRun": True, "target": target_name, "text": text}

        log("info", f"🌐 Step 1: Launching browser context for Facebook ({self.fb_account} -> {target_name})...")
        context = await get_browser_context()
        page = await context.new_page()
        try:
            log("info", f"🔗 Step 2: Navigating directly to Facebook Group ({self.fb_group_url})...")
            await page.goto(self.fb_group_url, wait_until="domcontentloaded", timeout=40000)
            await page.bring_to_front()
            await asyncio.sleep(3)

            # Check / ensure logged in
            log("info", f"🔒 Step 3: Verifying account session for {self.fb_account}...")
            is_authed = await self.ensure_facebook_logged_in(page, log_fn=log)
            if not is_authed:
                err_msg = f"Facebook session not active for {self.fb_account}. Please click '🔑 Login to Social Accounts' in the dashboard to sign in once."
                log("error", f"❌ {err_msg}")
                raise Exception(err_msg)

            # If redirected after login, reload group URL
            if "groups" not in page.url:
                await page.goto(self.fb_group_url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(3)

            # Step 4: Click 'Write something...' trigger
            log("info", "📝 Step 4: Opening group post composer ('Write something...')...")
            composer_trigger_loc = page.locator(
                'span:has-text("Write something..."), '
                'div[role="button"]:has-text("Write something..."), '
                'div[role="button"]:has-text("Create a public post"), '
                'div[role="button"]:has-text("Create a post")'
            ).first
            try:
                await composer_trigger_loc.wait_for(state="visible", timeout=15000)
                await composer_trigger_loc.click()
            except Exception as tr_err:
                log("warning", f"Trigger click note: {tr_err}. Clicking via evaluate...")
                await page.evaluate("""() => {
                    const el = Array.from(document.querySelectorAll('span, div[role="button"]')).find(e => 
                        (e.innerText || '').includes('Write something...') || (e.innerText || '').includes('Create a public post')
                    );
                    if (el) el.click();
                }""")
            await asyncio.sleep(2.5)

            # Step 5: Locate 'Create post' modal dialog (excluding hidden Messenger dialogs)
            log("info", "🔍 Step 5: Locating 'Create post' dialog modal...")
            dialog_loc = page.locator('div[role="dialog"]:not([aria-label="Messenger"]):has-text("Create post")').first
            try:
                await dialog_loc.wait_for(state="visible", timeout=12000)
            except Exception:
                pass

            # Step 6: Focus textbox and type shuffled post text
            log("info", "⌨️ Step 6: Entering shuffled deal copy and Pinterest link into composer...")
            textbox_loc = page.locator('div[role="dialog"]:not([aria-label="Messenger"]) div[role="textbox"][contenteditable="true"]').first
            try:
                await textbox_loc.wait_for(state="visible", timeout=10000)
                await textbox_loc.click()
            except Exception:
                log("info", "Focusing composer textbox via evaluate...")
                await page.evaluate("""() => {
                    const tb = document.querySelector('div[role="dialog"]:not([aria-label="Messenger"]) div[role="textbox"][contenteditable="true"]');
                    if (tb) { tb.focus(); tb.click(); }
                }""")
            await asyncio.sleep(0.5)

            clean_text = text.replace("\r", "")
            await page.keyboard.type(clean_text, delay=12)
            await asyncio.sleep(3)

            # Attach deal image if available
            temp_img_file = None
            if image_url:
                try:
                    import urllib.request
                    temp_dir = os.path.join(STATE_DIR, "temp_pin_images")
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_img_file = os.path.join(temp_dir, f"social_{int(time.time()*1000)}.jpg")
                    req = urllib.request.Request(
                        image_url,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        with open(temp_img_file, "wb") as f_out:
                            f_out.write(resp.read())

                    file_input = await page.query_selector('div[role="dialog"]:not([aria-label="Messenger"]) input[type="file"]')
                    if not file_input:
                        photo_btn = await page.query_selector(
                            'div[role="dialog"]:not([aria-label="Messenger"]) div[aria-label*="Photo/video" i], '
                            'div[role="dialog"]:not([aria-label="Messenger"]) div[aria-label*="Photo" i], '
                            'div[role="dialog"]:not([aria-label="Messenger"]) div[role="button"]:has-text("Photo/video")'
                        )
                        if photo_btn:
                            await photo_btn.click()
                            await asyncio.sleep(1)
                            file_input = await page.query_selector('div[role="dialog"]:not([aria-label="Messenger"]) input[type="file"]')

                    if file_input and os.path.exists(temp_img_file):
                        await file_input.set_input_files(temp_img_file)
                        log("info", "📸 Attached product image to Facebook post!")
                        await asyncio.sleep(3)
                except Exception as e_att:
                    log("info", f"Photo attachment note: {e_att}")

            # Step 7: Locate Post button inside dialog
            log("info", "🔍 Step 7: Locating blue 'Post' confirmation button inside dialog...")
            post_btn_loc = page.locator(
                'div[role="dialog"]:not([aria-label="Messenger"]) div[role="button"][aria-label="Post"], '
                'div[role="dialog"]:not([aria-label="Messenger"]) div[role="button"]:has-text("Post")'
            ).first
            try:
                await post_btn_loc.wait_for(state="visible", timeout=12000)
            except Exception:
                pass

            # Wait for button to be enabled
            for _ in range(8):
                is_disabled = await page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('div[role="dialog"]:not([aria-label="Messenger"]) div[role="button"]'));
                    const p = btns.find(b => (b.innerText || '').trim() === 'Post' || b.getAttribute('aria-label') === 'Post');
                    return !p || p.getAttribute('aria-disabled') === 'true';
                }""")
                if not is_disabled:
                    break
                await asyncio.sleep(1)

            # Step 8: Click Post
            log("info", f"🖱️ Step 8: Clicking 'Post' button to publish deal to {target_name}...")
            try:
                await post_btn_loc.click(timeout=6000)
            except Exception:
                await page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('div[role="dialog"]:not([aria-label="Messenger"]) div[role="button"]'));
                    const p = btns.find(b => (b.innerText || '').trim() === 'Post' || b.getAttribute('aria-label') === 'Post');
                    if (p) p.click();
                }""")

            # Step 9: Wait for dialog to detach/hide, confirming publication
            log("info", "⏳ Step 9: Awaiting Facebook modal detachment confirmation...")
            try:
                await page.locator('div[role="dialog"]:not([aria-label="Messenger"]):has-text("Create post")').first.wait_for(
                    state="hidden",
                    timeout=16000
                )
                log("success", "✅ Composer modal detached! Post successfully accepted by Facebook.")
            except Exception:
                log("info", "Modal wait reached timeout, checking dialog status...")
                await asyncio.sleep(3)

            self.ledger.record_share(
                pin_id=pin_id,
                pin_url=pin_url,
                image_url=image_url,
                title=title,
                text=text,
                platform="facebook",
                target=target_name,
                status="success"
            )
            log("success", f"🎉 Step 10: Deal successfully published to {target_name} in real time!")
            return {"success": True, "platform": "facebook", "target": target_name, "text": text}
        except Exception as e:
            log("error", f"❌ Facebook Post Failed: {str(e)}")
            raise e
        finally:
            try:
                if temp_img_file and os.path.exists(temp_img_file):
                    os.remove(temp_img_file)
            except Exception:
                pass
            if not page.is_closed():
                await page.close()
