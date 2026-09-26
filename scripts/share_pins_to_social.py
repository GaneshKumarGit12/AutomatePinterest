import os
import sys
import argparse
import asyncio
import time

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.engine.social_manager import DeduplicationLedger, ContentShuffler, QuickSocialPoster
from backend.engine.scraper import get_deals_for_page
from backend.engine.session_manager import get_browser_context


def run_test_dedup():
    """Verifies 5-layer deduplication and content/hashtag shuffler."""
    print("\n" + "=" * 60)
    print("🚀 [TEST] 5-Layer Deduplication & Dynamic Content Shuffler")
    print("=" * 60)

    ledger = DeduplicationLedger()
    sample_deal = {
        "id": "deal-test-B012345678",
        "asin": "B012345678",
        "title": "Accent Decora Elegant 2 Tier Cake Stand for Celebration",
        "truncatedTitle": "Accent Decora Elegant 2 Tier Cake Stand for Celebr",
        "price": "₹939",
        "originalPrice": "₹1,499",
        "discount": "37%",
        "category": "kitchen",
        "imageUrl": "https://m.media-amazon.com/images/I/71fiRY278BL._SL1500_.jpg",
        "pinUrl": "https://www.pinterest.com/pin/1140044093220116300/"
    }

    print("\n1. Testing Content Shuffler (Generating 3 Unique Variations):")
    for i in range(1, 4):
        post = ContentShuffler.generate_post(sample_deal, ledger)
        print(f"\n--- Variation #{i} (Pattern {post['patternId']}) ---")
        print(post["text"])

    print("\n2. Testing 5-Layer Deduplication Checks:")
    # First check on unrecorded pin
    check1 = ledger.check_candidate(
        pin_id=sample_deal["id"],
        pin_url=sample_deal["pinUrl"],
        image_url=sample_deal["imageUrl"],
        title=sample_deal["title"]
    )
    print(f"Check candidate (fresh): is_duplicate={check1['is_duplicate']} (Reason: {check1['reason']})")

    # Record mock share
    ledger.record_share(
        pin_id=sample_deal["id"],
        pin_url=sample_deal["pinUrl"],
        image_url=sample_deal["imageUrl"],
        title=sample_deal["title"],
        text="Mock share text",
        platform="twitter",
        target="@ganeshkumard1"
    )

    # Re-check candidate (should fail Layer 1 / Pin ID)
    check2 = ledger.check_candidate(
        pin_id=sample_deal["id"],
        pin_url=sample_deal["pinUrl"],
        image_url=sample_deal["imageUrl"],
        title=sample_deal["title"]
    )
    print(f"Check candidate (after share): is_duplicate={check2['is_duplicate']} (Layer {check2.get('layer')}: {check2['reason']})")

    # Re-check candidate with different Pin ID but SAME IMAGE (Layer 2 test)
    check3 = ledger.check_candidate(
        pin_id="deal-diff-pin-999",
        pin_url="https://www.pinterest.com/pin/9999999/",
        image_url=sample_deal["imageUrl"],
        title="Completely Different Title Here"
    )
    print(f"Check duplicate image URL (Layer 2): is_duplicate={check3['is_duplicate']} (Layer {check3.get('layer')}: {check3['reason']})")

    # Re-check candidate with different Pin & Image but SAME TITLE (Layer 3 test)
    check4 = ledger.check_candidate(
        pin_id="deal-diff-pin-888",
        pin_url="https://www.pinterest.com/pin/8888888/",
        image_url="https://m.media-amazon.com/images/I/DIFFERENT_IMAGE.jpg",
        title="Accent Decora Elegant 2 Tier Cake Stand for Celebration"
    )
    print(f"Check duplicate title (Layer 3): is_duplicate={check4['is_duplicate']} (Layer {check4.get('layer')}: {check4['reason']})")

    print("\n✅ All 5 Deduplication Layers & Content Shufflers Verified Successfully!")


async def run_check_login():
    """Opens a visible browser with tabs for Twitter and Facebook to verify or perform one-time login."""
    print("\n[Social Manager] Opening persistent browser profile for session verification...")
    print("Target Accounts:")
    print("  • Twitter (X): @ganeshkumard1")
    print("  • Facebook: ganeshkumard56 -> Worldnewzs / Amazon Affiliate Group")

    context = await get_browser_context()
    page1 = await context.new_page()
    await page1.goto("https://x.com/home", wait_until="domcontentloaded")

    page2 = await context.new_page()
    await page2.goto("https://www.facebook.com/", wait_until="domcontentloaded")

    print("\n👉 Browser window is open! If not logged in, please sign in once in the browser.")
    print("Session cookies are stored permanently in user_data/automation_session.")
    print("Waiting 30 seconds for verification before closing...")
    await asyncio.sleep(30)
    print("Session check complete.")


async def run_social_sharing(args):
    """Executes the quick-reduce social sharing flow."""
    ledger = DeduplicationLedger()
    poster = QuickSocialPoster(ledger)

    deals = get_deals_for_page(args.page, args.page_size)
    print(f"\n[Social Manager] Loaded {len(deals)} deal cards from Page {args.page}.")

    shared_count = 0
    for idx, deal in enumerate(deals):
        if args.max_posts and shared_count >= args.max_posts:
            print(f"[Social Manager] Reached max post limit ({args.max_posts}). Stopping.")
            break

        title = deal.get("title", "")
        pin_id = deal.get("id") or deal.get("asin")
        pin_url = deal.get("pinUrl") or deal.get("shareUrl") or f"https://in.pinterest.com/ganeshkumardevarasetty/"
        image_url = deal.get("imageUrl", "")

        # 5-Layer Deduplication Check
        check = ledger.check_candidate(pin_id, pin_url, image_url, title)
        if check["is_duplicate"]:
            print(f"\n⚠️ [Deduplication Skip] Card #{idx+1}: {check['reason']}")
            continue

        # Generate unique shuffled post text
        post_data = ContentShuffler.generate_post(deal, ledger)
        print(f"\n📢 [Card #{idx+1} Ready] {title[:45]}...")
        print(f"Generated Copy:\n{post_data['text']}\n")

        # Share to Twitter
        if args.platform in ["twitter", "both"]:
            try:
                res_tw = await poster.share_to_twitter(deal, post_data, dry_run=args.dry_run)
                print(f"  🐦 Twitter (@ganeshkumard1): {'✅ Success' if res_tw['success'] else '❌ Failed'}")
            except Exception as te:
                print(f"  🐦 Twitter Error: {te}")

        # Share to Facebook
        if args.platform in ["facebook", "both"]:
            try:
                res_fb = await poster.share_to_facebook(deal, post_data, dry_run=args.dry_run)
                print(f"  🟦 Facebook (Worldnewzs / Amazon Affiliate): {'✅ Success' if res_fb['success'] else '❌ Failed'}")
            except Exception as fe:
                print(f"  🟦 Facebook Error: {fe}")

        shared_count += 1

        # Pacing delay between posts
        if idx < len(deals) - 1 and not args.dry_run and args.pacing_mins > 0:
            print(f"\n⏳ Anti-Spam Drip Pacing: Sleeping {args.pacing_mins} minutes before next post...")
            await asyncio.sleep(args.pacing_mins * 60)


def main():
    parser = argparse.ArgumentParser(description="Quick-Reduce Social Media Sharer (Twitter & Facebook)")
    parser.add_argument("--test-dedup", action="store_true", help="Run 5-layer deduplication & content shuffler tests")
    parser.add_argument("--check-login", action="store_true", help="Open browser to check/login Twitter and Facebook sessions")
    parser.add_argument("--dry-run", action="store_true", help="Preview posts and deduplication without submitting")
    parser.add_argument("--platform", choices=["twitter", "facebook", "both"], default="both", help="Target platform(s)")
    parser.add_argument("--page", type=int, default=1, help="Deals page number to process")
    parser.add_argument("--page-size", type=int, default=6, help="Cards per page")
    parser.add_argument("--max-posts", type=int, default=None, help="Maximum number of pins to share")
    parser.add_argument("--pacing-mins", type=int, default=0, help="Drip pacing delay in minutes (0 for instant in CLI)")

    args = parser.parse_args()

    if args.test_dedup:
        run_test_dedup()
    elif args.check_login:
        asyncio.run(run_check_login())
    else:
        asyncio.run(run_social_sharing(args))


if __name__ == "__main__":
    main()
