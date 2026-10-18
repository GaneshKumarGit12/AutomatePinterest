import json
import os
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Tuple

# Path to local dataset
LOCAL_DATASET_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "src", "data", "amazonProducts.json")
)
WORLDNEWZS_API_URL = os.environ.get(
    "WORLDNEWZS_API_URL",
    "https://worldnewz.onrender.com/api/amazonproducts"
)

_cached_products = []


def sync_live_products() -> Dict[str, Any]:
    """
    Fetches latest live Amazon products directly from WorldNewzs (https://worldnewzs.in/amazon-products),
    sanitizes all images, computes accurate discounts, updates local dataset cache file,
    and invalidates memory cache.
    """
    global _cached_products
    print(f"[Scraper] Syncing live products from WorldNewzs (https://worldnewzs.in/amazon-products via {WORLDNEWZS_API_URL})...")
    live_prods = None

    # Retry up to 2 times with a 60-second timeout to handle cold-start on Render free tier
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                WORLDNEWZS_API_URL,
                headers={"User-Agent": "AutomatePinterest/2.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=60) as res:
                live_data = json.loads(res.read().decode("utf-8"))
                live_prods = live_data.get("products") if isinstance(live_data, dict) else live_data
                if isinstance(live_prods, list) and len(live_prods) > 0:
                    break
        except Exception as e:
            print(f"[Scraper] WorldNewzs direct API attempt {attempt+1} note: {e}")
            import time
            time.sleep(3)

        # Sanitize images and compute accurate discounts
        for p in live_prods:
            asin = str(p.get("asin") or "").strip()
            p["imageUrl"] = sanitize_image_url(p.get("imageUrl") or "", asin)
            price = p.get("price")
            orig = p.get("originalPrice")
            if price and orig and float(orig) > float(price):
                p["discount"] = f"{round((1 - float(price) / float(orig)) * 100)}% OFF"
            raw_url = str(p.get("productUrl") or p.get("dealUrl") or "").strip()
            if not raw_url or "tag=" not in raw_url or "amzn.to" in raw_url:
                if asin and len(asin) == 10:
                    p["productUrl"] = f"https://www.amazon.in/dp/{asin}?tag=ganeshd12-21&linkCode=ll2&linkId=309384296fe1c1e72569a81c50402f7a&ref_=as_li_ss_tl"

        try:
            os.makedirs(os.path.dirname(LOCAL_DATASET_PATH), exist_ok=True)
            with open(LOCAL_DATASET_PATH, "w", encoding="utf-8") as f:
                json.dump({"products": live_prods}, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

        _cached_products = live_prods
        print(f"[Scraper] Successfully synced {len(_cached_products)} products from WorldNewzs.")
        return {
            "success": True,
            "totalProducts": len(_cached_products),
            "totalPages": (len(_cached_products) + 5) // 6,
            "message": f"Successfully synced {len(_cached_products)} deals from WorldNewzs (https://worldnewzs.in/amazon-products)."
        }

    # Resilient fallback: ensure cached dataset is loaded and sanitized
    prods = load_products_dataset(force_refresh=True)
    if prods:
        for p in prods:
            asin = p.get("asin", "")
            p["imageUrl"] = sanitize_image_url(p.get("imageUrl") or "", asin)
            price = p.get("price")
            orig = p.get("originalPrice")
            if price and orig and float(orig) > float(price) and not p.get("discount"):
                p["discount"] = f"{round((1 - float(price) / float(orig)) * 100)}% OFF"
        _cached_products = prods
        return {
            "success": True,
            "totalProducts": len(_cached_products),
            "totalPages": (len(_cached_products) + 5) // 6,
            "message": f"Using cached dataset with {len(_cached_products)} deals."
        }

    return {"success": False, "totalProducts": 0, "totalPages": 0, "error": "No products found."}


def load_products_dataset(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Loads all Amazon products from local JSON cache, or live API if not present."""
    global _cached_products
    if _cached_products and not force_refresh:
        return _cached_products

    if os.path.exists(LOCAL_DATASET_PATH):
        try:
            with open(LOCAL_DATASET_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                prods = data.get("products") if isinstance(data, dict) else data
                if isinstance(prods, list) and prods:
                    _cached_products = prods
                    print(f"[Scraper] Loaded {len(_cached_products)} Amazon products from cache.")
                    return _cached_products
        except Exception as e:
            print(f"[Scraper] Error reading local dataset: {e}")

    # Fallback to live sync if local dataset is missing
    sync_res = sync_live_products()
    if sync_res.get("success"):
        return _cached_products

    return []


def truncate_title(title: str, max_length: int = 50) -> Tuple[str, bool]:
    """
    Truncates product title to maximum 50 characters (hard cut, no word boundary trimming).
    Returns (truncated_string, is_truncated).
    """
    clean_title = (title or "").strip()
    if len(clean_title) <= max_length:
        return clean_title, False
    return clean_title[:max_length], True


def sanitize_image_url(image_url: str, asin: str = "") -> str:
    """Sanitizes image URLs to ensure Pinterest-compatible, high-resolution media."""
    if not image_url:
        return f"https://m.media-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_SX500_.jpg" if asin else "https://worldnewzs.in/favicon.ico"

    # Replace known defective promo banners
    if "41z4rsHgIjL" in image_url:
        asin_maps = {
            "B0CX1VCQHC": "https://m.media-amazon.com/images/I/51aD9TAhtbL._SX425_.jpg",
            "B0DQV8T2JZ": "https://m.media-amazon.com/images/I/51RVfLDk4-L._SX425_.jpg",
            "B0H55R1S7C": "https://m.media-amazon.com/images/I/41DjGYzQ0HL.jpg",
        }
        if asin in asin_maps:
            return asin_maps[asin]

    # Prepend domain for relative URLs
    if image_url.startswith("/"):
        return f"https://worldnewzs.in{image_url}"

    # Pinterest rejects SVG media for pin creation
    if image_url.lower().endswith(".svg"):
        return f"https://m.media-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_SX500_.jpg" if asin else "https://worldnewzs.in/favicon.ico"

    return image_url


def format_amazon_product_card(p: Dict[str, Any], idx: int = 0, page_number: int = 1, serial_number: int = 1) -> Dict[str, Any]:
    """Formats a raw WorldNewzs Amazon product into a unified Deal/Pin card object."""
    raw_title = p.get("title") or p.get("name") or "Amazon Deal Product"
    truncated, is_trunc = truncate_title(raw_title, 50)
    price_val = p.get("price")
    if isinstance(price_val, str) and "₹" in price_val:
        price_str = price_val
        try:
            price_num = float(price_val.replace("₹", "").replace(",", "").strip())
        except Exception:
            price_num = 499.0
    else:
        price_num = float(price_val) if price_val else 499.0
        price_str = f"₹{int(price_num):,}"

    original_price_val = p.get("originalPrice")
    if isinstance(original_price_val, str) and "₹" in original_price_val:
        original_price_str = original_price_val
        try:
            orig_num = float(original_price_val.replace("₹", "").replace(",", "").strip())
        except Exception:
            orig_num = price_num * 1.5
    else:
        orig_num = float(original_price_val) if original_price_val else round(price_num * 1.5)
        original_price_str = f"₹{int(orig_num):,}"

    asin = str(p.get("asin") or f"P{page_number}C{idx+1}").strip()
    raw_url = str(p.get("productUrl") or p.get("dealUrl") or "").strip()
    if raw_url and "tag=" in raw_url and not ("amzn.to" in raw_url and asin not in raw_url):
        product_url = raw_url
    elif asin and not asin.startswith("deal-") and not asin.startswith("P"):
        product_url = f"https://www.amazon.in/dp/{asin}?tag=ganeshd12-21&linkCode=ll2&linkId=309384296fe1c1e72569a81c50402f7a&ref_=as_li_ss_tl"
    else:
        product_url = raw_url or f"https://www.amazon.in/dp/{asin}?tag=ganeshd12-21&linkCode=ll2"
    raw_img = p.get("imageUrl") or f"https://m.media-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_SX500_.jpg"
    image_url = sanitize_image_url(raw_img, asin)

    disc_val = p.get("discount")
    if not disc_val and orig_num > price_num > 0:
        disc_val = f"{round((1 - price_num / orig_num) * 100)}% OFF"
    if not disc_val:
        disc_val = "26% OFF"

    category = p.get("category") or p.get("tag") or "AMAZON DEALS"
    deal = {
        "id": f"deal-p{page_number}-c{idx+1}-{asin}",
        "pinId": asin,
        "asin": asin,
        "title": raw_title,
        "truncatedTitle": truncated,
        "isTruncated": is_trunc,
        "price": price_str,
        "originalPrice": original_price_str,
        "discount": disc_val,
        "category": category,
        "tag": category,
        "dealUrl": product_url,
        "productUrl": product_url,
        "amazonUrl": product_url,
        "pinterestUrl": p.get("pinterestUrl") or "https://in.pinterest.com/ganeshkumardevarasetty/_created/",
        "pinUrl": p.get("pinterestUrl") or product_url,
        "imageUrl": image_url,
        "pageNumber": page_number,
        "cardIndex": idx,
        "cardIndexOnPage": idx + 1,
        "serialNumber": serial_number,
        "dateAdded": p.get("dateAdded") or "",
        "isPinned": bool(p.get("isPinned", False)),
        "status": "pinned" if p.get("isPinned") else "pending",
        "statusLabel": "Moved to Pinterest" if p.get("isPinned") else "Ready to Pin",
    }
    deal["shareUrl"] = build_pinterest_share_url(deal)
    return deal


def get_deals_paginated(
    page_number: int = 1,
    page_size: int = 6,
    filter_mode: str = "pending",
    ledger: Any = None,
) -> Dict[str, Any]:
    """
    Returns paginated deals and statistics for the requested filter ('pending', 'pinned', 'all').
    'pending' filters out all 508+ already-pinned products so active queue starts from fresh products.
    """
    if ledger is None:
        try:
            from backend.engine.pinterest_ledger import PinterestLedger
            ledger = PinterestLedger()
        except Exception:
            ledger = None
    elif hasattr(ledger, "ensure_fresh"):
        ledger.ensure_fresh()

    products = load_products_dataset()
    if not products:
        return {
            "deals": [],
            "page": page_number,
            "pageSize": page_size,
            "totalPages": 1,
            "totalProducts": 0,
            "pendingCount": 0,
            "pinnedCount": 0,
            "totalCatalog": 0,
            "filter": filter_mode,
        }

    pending_list = []
    pinned_list = []

    for idx, p in enumerate(products):
        asin = str(p.get("asin") or "").strip()
        title = str(p.get("title") or "").strip()
        is_pin = ledger.is_pinned(asin, title) if ledger else False
        p_copy = dict(p)
        p_copy["isPinned"] = is_pin
        p_copy["catalogIndex"] = idx + 1
        if is_pin:
            pinned_list.append(p_copy)
        else:
            pending_list.append(p_copy)

    total_catalog = len(products)
    pending_count = len(pending_list)
    pinned_count = len(pinned_list)

    if filter_mode == "pinned":
        active_list = pinned_list
    elif filter_mode == "all":
        active_list = pending_list + pinned_list
    else:  # "pending"
        active_list = pending_list

    total_filtered = len(active_list)
    total_pages = max(1, (total_filtered + page_size - 1) // page_size)
    safe_page = min(max(1, page_number), total_pages)

    start_idx = (safe_page - 1) * page_size
    end_idx = start_idx + page_size
    slice_items = active_list[start_idx:end_idx]

    deals = []
    for idx, p in enumerate(slice_items):
        serial_num = start_idx + idx + 1
        card = format_amazon_product_card(p, idx=idx, page_number=safe_page, serial_number=serial_num)
        card["isPinned"] = p.get("isPinned", False)
        if card["isPinned"]:
            card["status"] = "pinned"
            card["statusLabel"] = "Moved to Pinterest"
        deals.append(card)

    return {
        "deals": deals,
        "page": safe_page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "totalProducts": total_filtered,
        "pendingCount": pending_count,
        "pinnedCount": pinned_count,
        "totalCatalog": total_catalog,
        "filter": filter_mode,
    }


def get_deals_for_page(
    page_number: int = 1,
    page_size: int = 6,
    filter_mode: str = "pending",
    ledger: Any = None,
) -> List[Dict[str, Any]]:
    """Returns 6 deals for the selected page index with 50-character truncated titles."""
    res = get_deals_paginated(
        page_number=page_number,
        page_size=page_size,
        filter_mode=filter_mode,
        ledger=ledger,
    )
    return res.get("deals", [])


def clean_pinned_deals(ledger: Any = None) -> Dict[str, Any]:
    """
    Purges/syncs pinned items from the active queue and returns updated counts.
    """
    if ledger is None:
        try:
            from backend.engine.pinterest_ledger import PinterestLedger
            ledger = PinterestLedger()
        except Exception:
            ledger = None

    if ledger and hasattr(ledger, "clean_pinned"):
        ledger.clean_pinned()

    summary = get_deals_paginated(page_number=1, page_size=6, filter_mode="pending", ledger=ledger)
    return {
        "success": True,
        "cleanedCount": summary.get("pinnedCount", 0),
        "remainingCount": summary.get("pendingCount", 0),
        "totalCatalog": summary.get("totalCatalog", 0),
        "message": f"Successfully cleared {summary.get('pinnedCount', 0)} already-moved product(s) from Pinterest queue ({summary.get('pendingCount', 0)} new deals ready).",
    }


def get_unposted_facebook_deals(
    page_number: int = 1,
    page_size: int = 6,
    ledger: Any = None,
    force_sync: bool = False,
) -> Dict[str, Any]:
    """
    Returns ONLY newly added / unposted Amazon products from worldnewzs.in/amazon-products,
    paginated at 6 products per page (matching Amazon Deal Cards).
    Products already posted to Facebook are automatically filtered out and cleared.
    """
    if force_sync:
        sync_live_products()

    if ledger is None:
        try:
            from backend.engine.social_manager import DeduplicationLedger
            ledger = DeduplicationLedger()
        except Exception:
            ledger = None
    elif hasattr(ledger, "ensure_fresh"):
        ledger.ensure_fresh()

    products = load_products_dataset(force_refresh=force_sync)
    if not products:
        return {
            "deals": [],
            "pins": [],
            "page": page_number,
            "pageSize": page_size,
            "totalPages": 1,
            "totalCount": 0,
            "pendingCount": 0,
            "postedCount": 0,
            "totalCatalog": 0,
        }

    unposted_raw = []
    posted_count = 0
    seen_asins = set()

    for p in products:
        asin = str(p.get("asin") or "").strip()
        p_url = str(p.get("productUrl") or p.get("dealUrl") or "").strip()
        p_title = str(p.get("title") or p.get("name") or "").strip()
        if asin and asin in seen_asins:
            continue
        if asin:
            seen_asins.add(asin)

        is_posted = False
        if ledger is not None:
            is_posted = ledger.is_posted_to_facebook(asin, p_url, p_title)

        if is_posted:
            posted_count += 1
        else:
            unposted_raw.append(p)

    total_unposted = len(unposted_raw)
    total_pages = max(1, (total_unposted + page_size - 1) // page_size)
    safe_page = min(max(1, page_number), total_pages)

    start_idx = (safe_page - 1) * page_size
    end_idx = start_idx + page_size
    slice_items = unposted_raw[start_idx:end_idx]

    page_deals = []
    for idx, p in enumerate(slice_items):
        serial_num = start_idx + idx + 1
        page_deals.append(
            format_amazon_product_card(p, idx=idx, page_number=safe_page, serial_number=serial_num)
        )

    return {
        "deals": page_deals,
        "pins": page_deals,
        "page": safe_page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "totalCount": total_unposted,
        "pendingCount": total_unposted,
        "postedCount": posted_count,
        "totalCatalog": len(seen_asins),
    }


def build_pinterest_share_url(deal: Dict[str, Any]) -> str:
    """Builds the Pinterest Pin Creation URL for an Amazon deal card."""
    target_url = deal.get("productUrl") or deal.get("dealUrl") or "https://worldnewzs.in/amazon-products"
    asin = deal.get("asin") or ""
    raw_media = deal.get("imageUrl") or ""
    media_url = sanitize_image_url(raw_media, asin)
    desc = f"{deal.get('truncatedTitle')} | {deal.get('price')} | Dhanvi Collections on Amazon & WorldNewzs Deals"

    params = {
        "url": target_url,
        "media": media_url,
        "description": desc,
    }
    return f"https://in.pinterest.com/pin/create/button/?{urllib.parse.urlencode(params)}"

