import os
import json
import time
from typing import Dict, Any, List, Set, Optional

PINTEREST_HISTORY_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "state", "pinterest_pinned_history.json")
)
AMAZON_PRODUCTS_JSON = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "src", "data", "amazonProducts.json")
)


class PinterestLedger:
    """
    Tracks and enforces deduplication for Pinterest pins.
    Maintains an atomic, persistent record of all ASINs, titles, and timestamps
    of products moved/pinned to Pinterest.
    Pre-seeds the 508 products already moved to Pinterest on Dhanvi Collections.
    """

    def __init__(self, filepath: str = PINTEREST_HISTORY_FILE):
        self.filepath = filepath
        self._last_mtime: float = 0.0
        self._pinned_asins: Set[str] = set()
        self._pinned_titles: Set[str] = set()
        self.data: Dict[str, Any] = {
            "pinned_asins": [],
            "pinned_records": [],
            "last_cleaned_at": None,
            "seed_count": 0,
        }
        self._load_and_seed()

    def ensure_fresh(self):
        """Reloads ledger from disk if modified by another process."""
        try:
            if os.path.exists(self.filepath):
                mtime = os.path.getmtime(self.filepath)
                if mtime > self._last_mtime:
                    self._load()
        except Exception:
            pass

    def _load(self):
        """Loads existing ledger data from disk and rebuilds fast lookup sets."""
        if not os.path.exists(self.filepath):
            return
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            self._last_mtime = os.path.getmtime(self.filepath)
            self._rebuild_lookup_cache()
        except Exception as e:
            print(f"[PinterestLedger] Error loading {self.filepath}: {e}")

    def _rebuild_lookup_cache(self):
        """Precomputes O(1) lookup sets for pinned ASINs and normalized titles."""
        self._pinned_asins = {
            str(a).strip().upper()
            for a in self.data.get("pinned_asins", [])
            if str(a).strip()
        }
        self._pinned_titles = set()
        for rec in self.data.get("pinned_records", []):
            if isinstance(rec, dict):
                asin = str(rec.get("asin") or "").strip().upper()
                if asin:
                    self._pinned_asins.add(asin)
                title = str(rec.get("title") or "").strip().lower()[:60]
                if title:
                    self._pinned_titles.add(title)

    def _save(self):
        """Persists ledger data to disk atomically."""
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            temp_path = f"{self.filepath}.tmp.{int(time.time() * 1000)}"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, self.filepath)
            self._last_mtime = os.path.getmtime(self.filepath)
        except Exception as e:
            print(f"[PinterestLedger] Failed to save ledger: {e}")

    def _load_and_seed(self):
        """Loads ledger or pre-seeds the first 508 products from amazonProducts.json."""
        if os.path.exists(self.filepath):
            self._load()
            # If ledger exists but has no pinned ASINs, perform seeding
            if len(self.data.get("pinned_asins", [])) >= 508:
                return

        # Seed the first 508 products from catalog as already moved to Pinterest
        if os.path.exists(AMAZON_PRODUCTS_JSON):
            try:
                with open(AMAZON_PRODUCTS_JSON, "r", encoding="utf-8") as f:
                    cat_data = json.load(f)
                products = cat_data.get("products", []) if isinstance(cat_data, dict) else cat_data
                if isinstance(products, list) and products:
                    first_508 = products[:508]
                    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    for idx, p in enumerate(first_508):
                        asin = str(p.get("asin") or "").strip().upper()
                        title = str(p.get("title") or "").strip()
                        if not asin:
                            asin = f"DEAL-SEED-{idx+1:04d}"
                        if asin not in self.data.get("pinned_asins", []):
                            self.data["pinned_asins"].append(asin)
                        self.data["pinned_records"].append({
                            "asin": asin,
                            "title": title,
                            "price": str(p.get("price") or ""),
                            "originalPrice": str(p.get("originalPrice") or ""),
                            "discount": str(p.get("discount") or ""),
                            "dealUrl": str(p.get("productUrl") or p.get("dealUrl") or ""),
                            "imageUrl": str(p.get("imageUrl") or ""),
                            "pinnedAt": now_iso,
                            "source": "pre_seeded_508",
                            "seedIndex": idx + 1,
                        })
                    self.data["seed_count"] = len(first_508)
                    self._save()
                    self._rebuild_lookup_cache()
                    print(f"[PinterestLedger] Successfully pre-seeded {len(first_508)} already-moved products into Pinterest ledger.")
            except Exception as e:
                print(f"[PinterestLedger] Error seeding initial 508 products: {e}")

    def is_pinned(self, asin: str, title: str = "") -> bool:
        """
        Fast O(1) check if a product is already moved/pinned to Pinterest.
        Checks by ASIN and normalized title prefix.
        """
        self.ensure_fresh()
        clean_asin = str(asin or "").strip().upper()
        if clean_asin and clean_asin in self._pinned_asins:
            return True

        clean_title = str(title or "").strip().lower()[:60]
        if clean_title and clean_title in self._pinned_titles:
            return True

        return False

    def mark_pinned(self, deal: Dict[str, Any]) -> bool:
        """
        Records a newly pinned product into the ledger upon 11-step automation success.
        Returns True if newly recorded, False if already present.
        """
        self.ensure_fresh()
        asin = str(deal.get("asin") or deal.get("id") or "").strip().upper()
        title = str(deal.get("title") or deal.get("truncatedTitle") or "").strip()

        if self.is_pinned(asin, title):
            return False

        if asin and asin not in self.data["pinned_asins"]:
            self.data["pinned_asins"].append(asin)

        record = {
            "asin": asin,
            "title": title,
            "truncatedTitle": deal.get("truncatedTitle") or title[:50],
            "price": str(deal.get("price") or ""),
            "originalPrice": str(deal.get("originalPrice") or ""),
            "discount": str(deal.get("discount") or ""),
            "dealUrl": deal.get("dealUrl") or deal.get("productUrl") or "",
            "imageUrl": deal.get("imageUrl") or "",
            "shareUrl": deal.get("shareUrl") or "",
            "pinnedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "automation_worker",
        }
        self.data["pinned_records"].append(record)
        self._save()
        self._rebuild_lookup_cache()
        return True

    def mark_asins_pinned(self, asins: List[str]) -> int:
        """Batch marks a list of ASINs as pinned."""
        self.ensure_fresh()
        added = 0
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for a in asins:
            clean_a = str(a).strip().upper()
            if clean_a and clean_a not in self._pinned_asins:
                self.data["pinned_asins"].append(clean_a)
                self.data["pinned_records"].append({
                    "asin": clean_a,
                    "pinnedAt": now_iso,
                    "source": "manual_batch",
                })
                added += 1
        if added > 0:
            self._save()
            self._rebuild_lookup_cache()
        return added

    def get_counts(self, total_catalog: int = 0) -> Dict[str, int]:
        """Returns accurate counts of pinned vs. pending products."""
        self.ensure_fresh()
        pinned_count = len(self._pinned_asins)
        pending_count = max(0, total_catalog - pinned_count) if total_catalog > 0 else 0
        return {
            "pinnedCount": pinned_count,
            "pendingCount": pending_count,
            "totalCatalog": total_catalog,
        }

    def clean_pinned(self) -> Dict[str, Any]:
        """
        Refreshes cache timestamp and returns summary of cleaned vs. remaining.
        """
        self.ensure_fresh()
        self.data["last_cleaned_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save()
        return {
            "success": True,
            "pinnedCount": len(self._pinned_asins),
            "timestamp": self.data["last_cleaned_at"],
        }

    def clear_all_pinned(self) -> Dict[str, Any]:
        """
        Marks ALL products currently in the catalog as moved/pinned to Pinterest.
        Clears the pending queue immediately so only brand new deals will appear when synced.
        """
        self.ensure_fresh()
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        marked_count = 0

        if os.path.exists(AMAZON_PRODUCTS_JSON):
            try:
                with open(AMAZON_PRODUCTS_JSON, "r", encoding="utf-8") as f:
                    cat_data = json.load(f)
                products = cat_data.get("products", []) if isinstance(cat_data, dict) else cat_data
                for idx, p in enumerate(products):
                    asin = str(p.get("asin") or "").strip().upper()
                    if not asin:
                        asin = f"DEAL-CAT-{idx+1:04d}"
                    title = str(p.get("title") or "").strip()
                    if asin not in self._pinned_asins:
                        self.data["pinned_asins"].append(asin)
                        self.data["pinned_records"].append({
                            "asin": asin,
                            "title": title,
                            "price": str(p.get("price") or ""),
                            "originalPrice": str(p.get("originalPrice") or ""),
                            "discount": str(p.get("discount") or ""),
                            "dealUrl": str(p.get("productUrl") or p.get("dealUrl") or ""),
                            "imageUrl": str(p.get("imageUrl") or ""),
                            "pinnedAt": now_iso,
                            "source": "clear_all_action",
                            "catalogIndex": idx + 1,
                        })
                        marked_count += 1
            except Exception as e:
                print(f"[PinterestLedger] Error in clear_all_pinned: {e}")

        self.data["last_cleaned_at"] = now_iso
        self._save()
        self._rebuild_lookup_cache()
        return {
            "success": True,
            "markedCount": marked_count,
            "totalPinned": len(self._pinned_asins),
            "remainingPending": 0,
            "message": f"Successfully marked all {len(self._pinned_asins)} products as moved to Pinterest. Active queue is cleared.",
        }

    def restore_latest_deals(self, latest_count: int = 48) -> Dict[str, Any]:
        """
        Configures the ledger so that ONLY the latest `latest_count` deals (48)
        from worldnewzs.in/amazon-products are unpinned and ready to pin.
        All remaining older products (3,048) are recorded as moved to Pinterest.
        """
        self.ensure_fresh()
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        if not os.path.exists(AMAZON_PRODUCTS_JSON):
            return {"success": False, "error": "Catalog file not found."}

        with open(AMAZON_PRODUCTS_JSON, "r", encoding="utf-8") as f:
            cat_data = json.load(f)
        products = cat_data.get("products", []) if isinstance(cat_data, dict) else cat_data

        latest_deals = products[:latest_count]
        older_deals = products[latest_count:]

        latest_asins = {
            str(p.get("asin") or "").strip().upper()
            for p in latest_deals
            if str(p.get("asin") or "").strip()
        }
        latest_titles = {
            str(p.get("title") or "").strip().lower()[:60]
            for p in latest_deals
            if str(p.get("title") or "").strip()
        }

        # Reset pinned collections completely
        self.data["pinned_asins"] = []
        self.data["pinned_records"] = []
        self._pinned_asins = set()
        self._pinned_titles = set()

        for idx, p in enumerate(older_deals, start=latest_count + 1):
            asin = str(p.get("asin") or "").strip().upper()
            if not asin:
                asin = f"DEAL-OLD-{idx:04d}"
            # Prevent pinning an ASIN belonging to the latest active deals
            if asin in latest_asins:
                continue
            if asin not in self.data["pinned_asins"]:
                self.data["pinned_asins"].append(asin)

            raw_title = str(p.get("title") or "").strip()
            norm_title = raw_title.lower()[:60]
            # Avoid title collision so new products with similar names remain active
            saved_title = raw_title if norm_title not in latest_titles else f"[ARCHIVED] {raw_title}"

            self.data["pinned_records"].append({
                "asin": asin,
                "title": saved_title,
                "price": str(p.get("price") or ""),
                "originalPrice": str(p.get("originalPrice") or ""),
                "discount": str(p.get("discount") or ""),
                "dealUrl": str(p.get("productUrl") or p.get("dealUrl") or ""),
                "imageUrl": str(p.get("imageUrl") or ""),
                "pinnedAt": now_iso,
                "source": "older_catalog_moved",
                "dealIndex": idx,
            })

        self.data["last_cleaned_at"] = now_iso
        self._save()
        self._rebuild_lookup_cache()

        ready_count = len(latest_deals)
        moved_count = len(older_deals)
        return {
            "success": True,
            "readyCount": ready_count,
            "pinnedCount": moved_count,
            "totalCatalog": len(products),
            "message": f"Successfully restored {ready_count} latest deals to Ready to Pin. {moved_count} older deals remain in Moved to Pinterest.",
        }


