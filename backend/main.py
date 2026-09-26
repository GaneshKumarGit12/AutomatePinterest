import os
import re
import sys
import json
import asyncio
import time
import subprocess
from typing import Dict, Any, List, Optional

if hasattr(sys.stdout, 'reconfigure') and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from backend.engine.scraper import (
    get_deals_for_page,
    build_pinterest_share_url,
    load_products_dataset,
    sync_live_products,
)
from backend.engine.pdf_reporter import (
    generate_daily_activity_pdf,
    ensure_report_directory,
    REPORT_DIR,
)
from backend.engine.session_manager import (
    get_browser_context,
    close_browser_context,
    launch_native_edge_login,
    ensure_pinterest_authenticated,
)
from backend.engine.pinterest_flow import execute_11_step_pipeline, DEFAULT_COLLABORATORS
from backend.engine.social_manager import (
    DeduplicationLedger,
    ContentShuffler,
    QuickSocialPoster,
)
from backend.engine.facebook_share_flow import (
    execute_pinterest_facebook_share,
    harvest_dhanvi_collection_pins,
    clean_posted_pins_from_cache,
    resolve_pin_image_from_pinterest,
    DHANVI_PINS_CACHE,
    PROJECT_ROOT,
    SCREENSHOTS_DIR,
)
from backend.engine.facebook_report_exporter import (
    export_facebook_shares_excel,
    generate_facebook_pdf_report,
)

app = FastAPI(title="AutomatePinterest Python FastAPI Engine", version="2.0.0")

# Social Manager Instances
social_ledger = DeduplicationLedger()
social_poster = QuickSocialPoster(social_ledger)

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3001,http://127.0.0.1:3001,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State
_run_state = {
    "isRunning": False,
    "selectedPages": 1,
    "currentPage": 1,
    "currentCardIndex": 0,
    "totalCardsProcessed": 0,
    "currentProductTitle": "",
    "processedCards": [],
    "stepLogs": [],
    "lastReportPath": None,
    "startTime": None,
}

_event_queues: List[asyncio.Queue] = []


def broadcast_event(event_type: str, data: Dict[str, Any]):
    """Pushes SSE events to all connected clients."""
    for q in _event_queues:
        q.put_nowait({"event": event_type, "data": json.dumps(data)})


class StartRunRequest(BaseModel):
    startPage: int = 1
    endPage: Optional[int] = None
    pages: Optional[int] = None
    collaborators: Optional[List[str]] = ["auto"]
    startCardIndex: Optional[int] = None
    startDealNumber: Optional[int] = None



class SocialShareRequest(BaseModel):
    deals: List[Dict[str, Any]]
    platform: str = "twitter"  # "twitter", "facebook", "both"
    enablePacing: bool = False
    pacingMinutes: int = 15
    dryRun: bool = False


class SocialPreviewRequest(BaseModel):
    deals: List[Dict[str, Any]]


class PinterestFacebookShareRequest(BaseModel):
    pinCount: int = 10
    delaySeconds: int = 60
    targetBoardUrl: Optional[str] = None
    specificPinIds: Optional[List[str]] = None
    destination: Optional[str] = "both"  # "both", "page", "group"


@app.get("/api/status")
async def get_status():
    """Returns engine health and active run state without memory bloat."""
    # Keep runState lightened (< 25 KB) to eliminate MemoryError on frequent polling
    safe_run_state = {
        **_run_state,
        "stepLogs": _run_state.get("stepLogs", [])[-25:],
        "processedCards": _run_state.get("processedCards", [])[-50:],
    }
    return {
        "status": "online",
        "engine": "Python FastAPI + Browser-Use CDP",
        "runState": safe_run_state,
        "datasetSize": len(load_products_dataset()),
        "reportDir": REPORT_DIR,
    }


@app.get("/api/deals")
async def get_deals(page: int = Query(1, ge=1), page_size: int = Query(6, ge=1, le=50)):
    """Returns 6 product deals for the specified pagination page."""
    deals = get_deals_for_page(page, page_size)
    total_products = len(load_products_dataset())
    total_pages = (total_products + page_size - 1) // page_size if total_products > 0 else 1

    return {
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "totalProducts": total_products,
        "deals": deals,
    }


@app.post("/api/deals/sync")
async def sync_deals_endpoint():
    """Syncs live Amazon deals directly from WorldNewzs into AutomatePinterest."""
    res = sync_live_products()
    total_products = res.get("totalProducts", len(load_products_dataset()))
    total_pages = (total_products + 6 - 1) // 6 if total_products > 0 else 1

    broadcast_event("log", {
        "level": "success" if res.get("success") else "warning",
        "message": f"🔄 [Deals Sync] WorldNewzs sync complete: {total_products} total deals across {total_pages} pages."
    })

    return {
        "success": res.get("success", False),
        "totalProducts": total_products,
        "totalPages": total_pages,
        "message": res.get("message") or f"Synced {total_products} products from WorldNewzs.",
    }


async def get_healthy_context(current_ctx=None):
    """Ensures a live, healthy browser context is returned, re-opening if disconnected."""
    if current_ctx is not None:
        try:
            if not getattr(current_ctx, "is_closed", lambda: False)():
                _ = len(current_ctx.pages)
                return current_ctx
        except Exception:
            pass
    return await get_browser_context()


async def run_automation_worker(
    start_page: int,
    end_page: int,
    collaborators: List[str],
    start_card_index: int = 0,
    start_deal_number: Optional[int] = None,
):
    """Background worker executing the 11-step automation loop across pages with auto-recovery and memory bounding."""
    global _run_state
    total_pages = end_page - start_page + 1
    _run_state["isRunning"] = True
    _run_state["selectedPages"] = total_pages
    _run_state["startPage"] = start_page
    _run_state["endPage"] = end_page
    _run_state["currentPage"] = start_page
    _run_state["startCardIndex"] = start_card_index
    _run_state["startDealNumber"] = start_deal_number
    _run_state["totalCardsProcessed"] = 0
    _run_state["processedCards"] = []
    _run_state["stepLogs"] = []
    _run_state["startTime"] = time.time()

    all_cards_for_report = []

    start_deal_msg = f" starting at Deal #{start_deal_number}" if start_deal_number else (f" starting at Card {start_card_index+1}" if start_card_index > 0 else "")
    broadcast_event("log", {
        "level": "info",
        "message": f"🚀 Starting 11-step automation for Page {start_page} to {end_page} ({total_pages} page(s)){start_deal_msg}..."
    })

    collab_mode_str = "Dynamic Auto-Discovery (All Connected Pinterest Collaborators)" if (not collaborators or collaborators == ["auto"] or any(str(c).lower() == "auto" for c in collaborators)) else f"Custom: {', '.join(collaborators)}"
    broadcast_event("log", {
        "level": "info",
        "message": f"👥 Collaborators Mode: {collab_mode_str}"
    })


    try:
        context = await get_browser_context()

        broadcast_event("log", {"level": "info", "message": "🔐 Verifying Pinterest account session..."})
        is_authenticated = await ensure_pinterest_authenticated(context)
        if not is_authenticated:
            broadcast_event("log", {
                "level": "error",
                "message": "❌ Pinterest authentication failed. Please check credentials or log in via browser."
            })
            _run_state["isRunning"] = False
            return

        broadcast_event("log", {"level": "success", "message": "✅ Pinterest owner session verified (Dhanvi Collections)!"})

        for page_idx in range(start_page, end_page + 1):
            if not _run_state["isRunning"]:
                broadcast_event("log", {"level": "warn", "message": "Automation stopped by user."})
                break

            _run_state["currentPage"] = page_idx
            deals = get_deals_for_page(page_idx, 6)

            broadcast_event("log", {
                "level": "info",
                "message": f"--- Processing Page {page_idx} of {end_page} (Range: {start_page} to {end_page}): Found {len(deals)} Deal Cards ---"
            })

            for card_idx, deal in enumerate(deals):
                if not _run_state["isRunning"]:
                    break

                # Skip cards before start_card_index on the initial start_page
                if page_idx == start_page and card_idx < start_card_index:
                    deal_overall_idx = (page_idx - 1) * 6 + card_idx + 1
                    broadcast_event("log", {
                        "level": "info",
                        "message": f"⏩ Skipping previously completed Deal #{deal_overall_idx}: {deal.get('truncatedTitle')}"
                    })
                    continue

                _run_state["currentCardIndex"] = card_idx
                _run_state["currentProductTitle"] = deal["truncatedTitle"]

                broadcast_event("step_update", {
                    "card": deal,
                    "page": page_idx,
                    "cardIndex": card_idx,
                    "message": f"Card [{card_idx+1}/{len(deals)}]: {deal['truncatedTitle']} ({deal['price']})"
                })

                share_url = build_pinterest_share_url(deal)

                def on_step(step_entry):
                    _run_state["stepLogs"].append(step_entry)
                    if len(_run_state["stepLogs"]) > 50:
                        _run_state["stepLogs"] = _run_state["stepLogs"][-50:]
                    broadcast_event("step_log", step_entry)

                # Ensure browser context is healthy before execution
                context = await get_healthy_context(context)

                result = await execute_11_step_pipeline(
                    context=context,
                    deal=deal,
                    share_url=share_url,
                    collaborators=collaborators,
                    on_step_callback=on_step,
                )

                # Auto-recovery if browser disconnected or closed
                if not result.get("success") and ("closed" in str(result.get("error", "")).lower() or "target page" in str(result.get("error", "")).lower()):
                    broadcast_event("log", {
                        "level": "warn",
                        "message": f"⚠️ Browser disconnected during Card [{card_idx+1}/{len(deals)}]. Reconnecting browser session and retrying card..."
                    })
                    try:
                        await close_browser_context()
                    except Exception:
                        pass
                    await asyncio.sleep(2)
                    context = await get_browser_context()
                    result = await execute_11_step_pipeline(
                        context=context,
                        deal=deal,
                        share_url=share_url,
                        collaborators=collaborators,
                        on_step_callback=on_step,
                    )

                # Clean card record without duplicate nested stepLogs to avoid memory explosion
                card_record = {
                    "id": deal.get("id"),
                    "asin": deal.get("asin"),
                    "title": deal.get("title"),
                    "truncatedTitle": deal.get("truncatedTitle"),
                    "price": deal.get("price"),
                    "dealUrl": deal.get("dealUrl") or deal.get("productUrl"),
                    "imageUrl": deal.get("imageUrl"),
                    "pageNumber": page_idx,
                    "cardIndex": card_idx,
                    "status": "success" if result.get("success") else "failed",
                    "collaborators": result.get("collaborators") or collaborators,
                    "error": result.get("error"),
                }
                _run_state["processedCards"].append(card_record)
                all_cards_for_report.append(card_record)
                _run_state["totalCardsProcessed"] += 1

                if result["success"]:
                    broadcast_event("log", {
                        "level": "success",
                        "message": f"✅ Card [{card_idx+1}/{len(deals)}] COMPLETED: {deal['truncatedTitle']}"
                    })
                else:
                    broadcast_event("log", {
                        "level": "error",
                        "message": f"❌ Card [{card_idx+1}/{len(deals)}] FAILED: {result.get('error', 'Unknown error')}"
                    })

                await asyncio.sleep(1)

        # Generate dated PDF activity report
        duration_sec = int(time.time() - (_run_state["startTime"] or time.time()))
        summary = {
            "total_cards": len(all_cards_for_report),
            "success_count": sum(1 for c in all_cards_for_report if c.get("status") == "success"),
            "failed_count": sum(1 for c in all_cards_for_report if c.get("status") == "failed"),
            "pages_count": total_pages,
            "start_page": start_page,
            "end_page": end_page,
            "duration_seconds": duration_sec,
        }

        report_info = generate_daily_activity_pdf(summary, all_cards_for_report, REPORT_DIR)
        _run_state["lastReportPath"] = report_info["fullPath"]

        completion_msg = f"Automate process between page {start_page} to {end_page} completed"
        broadcast_event("log", {
            "level": "success",
            "message": f"🎉 {completion_msg}! PDF Activity Report created: {report_info['fileName']}"
        })
        broadcast_event("run_complete", {
            "summary": summary,
            "report": report_info,
            "startPage": start_page,
            "endPage": end_page,
            "message": completion_msg,
        })

    except Exception as e:
        broadcast_event("log", {"level": "error", "message": f"Automation error: {str(e)}"})
    finally:
        _run_state["isRunning"] = False
        broadcast_event("state_change", {"isRunning": False})


@app.post("/api/automation/start")
async def start_automation(req: StartRunRequest, background_tasks: BackgroundTasks):
    """Starts the 11-step automation process across user-selected page range."""
    if _run_state["isRunning"]:
        raise HTTPException(status_code=400, detail="Automation is already running.")

    start_card_index = 0
    start_deal_number = req.startDealNumber
    if start_deal_number is not None and start_deal_number > 0:
        calc_page = ((start_deal_number - 1) // 6) + 1
        calc_card = (start_deal_number - 1) % 6
        start_page = calc_page
        start_card_index = calc_card
        if req.endPage is not None:
            end_page = max(start_page, req.endPage)
        else:
            end_page = max(start_page, req.pages or 20)
        total_pages = end_page - start_page + 1
    else:
        start_page = max(1, req.startPage)
        start_card_index = req.startCardIndex or 0
        if req.endPage is not None:
            end_page = max(start_page, req.endPage)
            total_pages = end_page - start_page + 1
        else:
            total_pages = max(1, req.pages or 1)
            end_page = start_page + total_pages - 1

    background_tasks.add_task(
        run_automation_worker,
        start_page,
        end_page,
        req.collaborators or DEFAULT_COLLABORATORS,
        start_card_index,
        start_deal_number,
    )
    return {
        "success": True,
        "message": f"Automation started for Page {start_page} to {end_page} ({total_pages} page(s))" + (f" resuming from Deal #{start_deal_number}" if start_deal_number else "") + ".",
        "startPage": start_page,
        "endPage": end_page,
        "totalPages": total_pages,
        "startCardIndex": start_card_index,
        "startDealNumber": start_deal_number,
    }



@app.post("/api/automation/stop")
async def stop_automation():
    """Stops the active automation run."""
    _run_state["isRunning"] = False
    return {"success": True, "message": "Stop signal sent to automation worker."}


@app.get("/api/automation/stream")
async def sse_stream(request: Request):
    """
    Server-Sent Events endpoint streaming live activity logs and step updates.
    Includes 15-second heartbeat comments to prevent net::ERR_NETWORK_IO_SUSPENDED
    and browser socket suspension.
    """
    queue = asyncio.Queue()
    _event_queues.append(queue)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield item
                except asyncio.TimeoutError:
                    # Send periodic keep-alive comment so browsers do not suspend the socket
                    yield {"comment": "keep-alive"}
        except asyncio.CancelledError:
            pass
        finally:
            if queue in _event_queues:
                _event_queues.remove(queue)

    return EventSourceResponse(event_generator(), ping=15)


@app.post("/api/auth/login")
async def open_login_window():
    """Opens visible browser window directly to Pinterest login."""
    launch_native_edge_login()
    return {
        "success": True,
        "message": "Opened Microsoft Edge to Pinterest Login. Please log in with Google (ganeshkumard56@gmail.com).",
    }


@app.post("/api/auth/sync-edge")
async def sync_edge():
    """Copies Microsoft Edge profile cookies into automation directory."""
    import subprocess
    ps_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "copy_edge_cookies.ps1"))
    try:
        res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_path], capture_output=True, text=True)
        if "COPIED_COOKIES_SUCCESS" in res.stdout:
            return {"success": True, "message": "Successfully imported Pinterest session from Microsoft Edge!"}
        return {"success": False, "message": "Edge cookies locked. You can also click 'Open Browser Window' to log in."}
    except Exception as e:
        return {"success": False, "message": f"Sync note: {str(e)}"}


@app.get("/api/reports")
async def get_reports():
    """Returns list of generated daily PDF activity reports."""
    ensure_report_directory(REPORT_DIR)
    files = [f for f in os.listdir(REPORT_DIR) if f.endswith(".pdf")]
    reports = []
    for f in files:
        full = os.path.join(REPORT_DIR, f)
        st = os.stat(full)
        reports.append({
            "fileName": f,
            "fullPath": full,
            "sizeBytes": st.st_size,
            "createdAt": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
        })
    reports.sort(key=lambda r: r["createdAt"], reverse=True)
    return {"reports": reports}


@app.get("/api/reports/download/{filename}")
async def download_report(filename: str):
    """Downloads a specific PDF activity report safely (preventing path traversal)."""
    clean_name = os.path.basename(filename)
    if not clean_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid report filename.")
    full = os.path.realpath(os.path.join(REPORT_DIR, clean_name))
    report_dir_real = os.path.realpath(REPORT_DIR)
    if not full.startswith(report_dir_real) or not os.path.exists(full):
        raise HTTPException(status_code=404, detail="Report file not found.")
    return FileResponse(
        full,
        media_type="application/pdf",
        filename=clean_name,
        headers={"Content-Disposition": f'attachment; filename="{clean_name}"'}
    )


# --- Social Media Hub Endpoints (Twitter @ganeshkumard1 & Facebook Worldnewzs) ---

async def run_social_worker(deals: List[Dict[str, Any]], platform: str, enable_pacing: bool, pacing_minutes: int, dry_run: bool):
    """Asynchronous worker that posts selected pins with 5-layer deduplication and content shuffling."""
    plat_label = "Twitter (@ganeshkumard1)" if platform == "twitter" else "Facebook (Worldnewzs / Amazon Affiliate)" if platform == "facebook" else "Twitter & Facebook"

    def stream_log(lvl: str, msg: str):
        broadcast_event("log", {"level": lvl, "message": msg})
        broadcast_event("social_log", {"level": lvl, "message": msg, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    stream_log("info", f"🚀 [Social Hub] Starting quick-reduce sharing for {len(deals)} selected pin(s) to {plat_label} (Dry Run: {dry_run})...")

    success_count = 0
    skipped_count = 0
    failed_count = 0
    auth_failed_platforms = set()

    for idx, deal in enumerate(deals):
        pin_id = deal.get("id") or deal.get("asin") or f"card-{idx+1}"
        pin_url = deal.get("pinUrl") or deal.get("shareUrl") or "https://in.pinterest.com/ganeshkumardevarasetty/"
        image_url = deal.get("imageUrl", "")
        title = deal.get("title", f"Amazon Deal #{idx+1}")

        # Check if platform authentication has already failed for this batch to prevent repetitive 30s hangs
        if (platform == "twitter" and "twitter" in auth_failed_platforms) or \
           (platform == "facebook" and "facebook" in auth_failed_platforms) or \
           (platform == "both" and "twitter" in auth_failed_platforms and "facebook" in auth_failed_platforms):
            skipped_count += 1
            broadcast_event("social_card_status", {
                "dealId": pin_id,
                "status": "error",
                "platform": platform,
                "message": "Aborted: Platform session not authenticated.",
            })
            social_ledger.record_share(
                pin_id=pin_id,
                pin_url=pin_url,
                image_url=image_url,
                title=title,
                text="",
                platform=platform,
                target=plat_label,
                status="failed",
                error_message="Aborted: Platform session not authenticated."
            )
            continue

        # 5-Layer Deduplication Check
        check = social_ledger.check_candidate(pin_id, pin_url, image_url, title)
        if check["is_duplicate"]:
            skipped_count += 1
            broadcast_event("social_card_status", {
                "dealId": pin_id,
                "status": "skipped",
                "platform": platform,
                "message": check["reason"],
            })
            stream_log("warning", f"⚠️ [Deduplication Skip] Card #{idx+1} ({title[:35]}...): {check['reason']}")
            social_ledger.record_share(
                pin_id=pin_id,
                pin_url=pin_url,
                image_url=image_url,
                title=title,
                text="",
                platform=platform,
                target=plat_label,
                status="skipped",
                error_message=check["reason"]
            )
            continue

        broadcast_event("social_card_status", {
            "dealId": pin_id,
            "status": "posting",
            "platform": platform,
            "message": f"Publishing to {plat_label}...",
        })

        # Dynamic Content & Hashtag Shuffler
        post_data = ContentShuffler.generate_post(deal, social_ledger)
        stream_log("info", f"📝 [Card #{idx+1} Shuffled Copy]: \"{post_data['text'][:70]}...\"")

        card_errors = []

        # Post to Twitter (@ganeshkumard1)
        if platform in ["twitter", "both"] and "twitter" not in auth_failed_platforms:
            try:
                await social_poster.share_to_twitter(deal, post_data, dry_run=dry_run, log_fn=stream_log)
                success_count += 1
            except Exception as te:
                err_str = str(te)
                failed_count += 1
                card_errors.append(f"Twitter: {err_str}")
                stream_log("error", f"❌ Twitter error on Card #{idx+1}: {err_str}")
                social_ledger.record_share(
                    pin_id=pin_id,
                    pin_url=pin_url,
                    image_url=image_url,
                    title=title,
                    text=post_data.get("text", ""),
                    platform="twitter",
                    target=social_poster.twitter_account,
                    status="failed",
                    error_message=err_str
                )
                if any(w in err_str.lower() for w in ["session not active", "login required", "login failed", "credentials"]):
                    auth_failed_platforms.add("twitter")
                    stream_log("warning", "🚨 Twitter authentication issue detected. Pausing Twitter posts for remaining cards in this batch. Please click '🔑 Login to Social Accounts'.")

        # Post to Facebook (Worldnewzs -> Amazon Affiliate Group)
        if platform in ["facebook", "both"] and "facebook" not in auth_failed_platforms:
            try:
                await social_poster.share_to_facebook(deal, post_data, dry_run=dry_run, log_fn=stream_log)
                success_count += 1
            except Exception as fe:
                err_str = str(fe)
                failed_count += 1
                card_errors.append(f"Facebook: {err_str}")
                stream_log("error", f"❌ Facebook error on Card #{idx+1}: {err_str}")
                social_ledger.record_share(
                    pin_id=pin_id,
                    pin_url=pin_url,
                    image_url=image_url,
                    title=title,
                    text=post_data.get("text", ""),
                    platform="facebook",
                    target=f"{social_poster.fb_page} -> {social_poster.fb_group}",
                    status="failed",
                    error_message=err_str
                )
                if any(w in err_str.lower() for w in ["session not active", "login required", "checkpoint", "2fa"]):
                    auth_failed_platforms.add("facebook")
                    stream_log("warning", "🚨 Facebook authentication issue detected. Pausing Facebook posts for remaining cards in this batch. Please click '🔑 Login to Social Accounts'.")

        card_status = "error" if card_errors else "success"
        card_msg = "; ".join(card_errors) if card_errors else "Published successfully!"
        broadcast_event("social_card_status", {
            "dealId": pin_id,
            "status": card_status,
            "platform": platform,
            "message": card_msg,
        })

        # Drip Pacing Delay
        if idx < len(deals) - 1 and enable_pacing and pacing_minutes > 0 and not dry_run and not card_errors:
            stream_log("info", f"⏳ [Anti-Spam Pacing] Pausing {pacing_minutes} minute(s) before next deal card...")
            await asyncio.sleep(pacing_minutes * 60)

    stream_log("success", f"🎉 [Social Hub Batch Complete] Successfully shared: {success_count} | Skipped: {skipped_count} | Errors: {failed_count}")


@app.post("/api/social/share")
async def share_to_social(req: SocialShareRequest, background_tasks: BackgroundTasks):
    """Triggers direct quick-reduce social sharing for selected pins."""
    if not req.deals:
        raise HTTPException(status_code=400, detail="No product deals provided for sharing.")

    background_tasks.add_task(
        run_social_worker,
        req.deals,
        req.platform,
        req.enablePacing,
        req.pacingMinutes,
        req.dryRun
    )
    return {
        "success": True,
        "message": f"Social sharing queued for {len(req.deals)} pins on {req.platform.upper()} (Pacing: {req.enablePacing})."
    }


@app.post("/api/social/preview")
async def preview_social_posts(req: SocialPreviewRequest):
    """Returns deduplication status and freshly shuffled preview texts for candidate deals."""
    previews = []
    for d in req.deals:
        pin_id = d.get("id") or d.get("asin") or ""
        pin_url = d.get("pinUrl") or d.get("shareUrl") or ""
        image_url = d.get("imageUrl") or ""
        title = d.get("title") or ""

        check = social_ledger.check_candidate(pin_id, pin_url, image_url, title)
        post_data = ContentShuffler.generate_post(d, social_ledger)

        previews.append({
            "dealId": pin_id,
            "title": title,
            "isDuplicate": check["is_duplicate"],
            "dedupReason": check["reason"],
            "shuffledText": post_data["text"],
            "hashtags": post_data["hashtags"],
            "category": post_data["category"]
        })
    return {"previews": previews}


@app.get("/api/social/history")
async def get_social_history():
    """Returns deduplication stats and recent post logs."""
    return social_ledger.get_stats()


@app.get("/api/social/session-status")
async def get_social_session_status():
    """Returns target accounts and configurations."""
    return {
        "twitterAccount": os.environ.get("TWITTER_ACCOUNT", "@ganeshkumard1"),
        "facebookAccount": os.environ.get("FACEBOOK_ACCOUNT", "ganeshkumard56"),
        "facebookPage": os.environ.get("FACEBOOK_PAGE_NAME", "Worldnewzs"),
        "facebookGroup": os.environ.get("FACEBOOK_GROUP_NAME", "Amazon Affiliate Group"),
        "facebookGroupUrl": os.environ.get("FACEBOOK_GROUP_URL", "https://www.facebook.com/groups/1761596288324903/"),
        "facebookTarget": f"{os.environ.get('FACEBOOK_PAGE_NAME', 'Worldnewzs')} -> {os.environ.get('FACEBOOK_GROUP_NAME', 'Amazon Affiliate Group')}",
    }


@app.post("/api/social/login")
async def trigger_social_login(background_tasks: BackgroundTasks):
    """Launches headful browser and runs automated login with 2FA assistance."""
    async def do_login():
        def stream_log(lvl: str, msg: str):
            broadcast_event("log", {"level": lvl, "message": msg})
            broadcast_event("social_log", {"level": lvl, "message": msg, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

        stream_log("info", "🌐 Launching headful browser for Facebook & Twitter login...")
        ctx = await get_browser_context()
        
        # Facebook Tab
        p_fb = await ctx.new_page()
        try:
            await p_fb.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=45000)
            await social_poster.ensure_facebook_logged_in(p_fb, log_fn=stream_log)
        except Exception as e:
            stream_log("error", f"Facebook login error: {e}")

        # Twitter Tab
        p_tw = await ctx.new_page()
        try:
            await p_tw.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=45000)
            await social_poster.ensure_twitter_logged_in(p_tw, log_fn=stream_log)
        except Exception as e:
            stream_log("error", f"Twitter login error: {e}")

    background_tasks.add_task(do_login)
    return {
        "success": True,
        "message": "Opened browser for Facebook and Twitter login. Complete any 2FA challenge on screen."
    }


@app.post("/api/social/check-session")
async def check_social_session(background_tasks: BackgroundTasks):
    """Opens browser with tabs for Twitter and Facebook to verify active sessions."""
    return await trigger_social_login(background_tasks)


@app.post("/api/social/launch-edge-facebook")
async def launch_edge_facebook():
    """Directly opens native Microsoft Edge in foreground with the automation profile to solve Facebook verification."""
    try:
        from backend.engine.session_manager import close_browser_context, kill_stale_automation_processes, clean_stale_lockfiles, USER_DATA_DIR
        await close_browser_context()
        kill_stale_automation_processes()
        clean_stale_lockfiles(USER_DATA_DIR)

        cmd = f'Start-Process msedge.exe -ArgumentList \'--user-data-dir="{USER_DATA_DIR}"\', \'https://www.facebook.com/\''
        subprocess.Popen(["powershell", "-Command", cmd])
        return {
            "success": True,
            "message": "Microsoft Edge opened on your screen. Complete any Facebook verification, then close Edge."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Pinterest → Facebook Group Share Endpoints ---

_fb_share_state = {
    "isRunning": False,
    "currentStep": 0,
    "totalSteps": 7,
    "currentPin": 0,
    "totalPins": 0,
    "results": [],
    "error": None,
    "lastExcelReport": None,
    "lastPdfReport": None,
}


async def run_pinterest_facebook_worker(
    pin_count: int = 10,
    delay_seconds: int = 60,
    target_board_url: Optional[str] = None,
    specific_pin_ids: Optional[List[str]] = None,
    destination: str = "both",
):
    """Background worker for Pinterest → Facebook Page & Group share flow."""
    global _fb_share_state
    _fb_share_state["isRunning"] = True
    _fb_share_state["currentPin"] = 0
    _fb_share_state["totalPins"] = pin_count
    _fb_share_state["results"] = []
    _fb_share_state["error"] = None

    def stream_log(lvl: str, msg: str):
        broadcast_event("log", {"level": lvl, "message": msg})
        broadcast_event("social_log", {
            "level": lvl,
            "message": msg,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        # Track step progress from log messages
        step_num = None
        m_step = re.search(r'Step\s+(\d+)(?:-(\d+))?(?:/7|\s*:\s*|\s+complete)', msg, re.I)
        if m_step:
            try:
                # Use second number if range (e.g. 4-5/7 -> 4 or 5) or first number
                step_num = int(m_step.group(1))
            except Exception:
                pass
        elif "WorldNewzs Facebook Page Feed" in msg and "Publishing" in msg:
            step_num = 4
        elif "Amazon Affiliate Group" in msg and "Publishing" in msg:
            step_num = 5
        elif "successfully published" in msg.lower():
            step_num = 7

        if step_num is not None:
            _fb_share_state["currentStep"] = step_num
            broadcast_event("fb_share_step", {
                "step": step_num,
                "totalSteps": 7,
                "message": msg,
            })

        if "Evaluating Pin" in msg or "Publishing" in msg or "Step" in msg:
            broadcast_event("fb_share_update", {
                "message": msg,
                "currentStep": _fb_share_state["currentStep"],
            })

    def stream_live_frame(frame_name: str):
        broadcast_event("fb_live_frame", {
            "frame": frame_name,
            "url": f"/api/social/live-frame?t={int(time.time()*1000)}",
            "timestamp": time.time(),
        })

    try:
        result = await execute_pinterest_facebook_share(
            pin_count=pin_count,
            delay_seconds=delay_seconds,
            target_board_url=target_board_url,
            specific_pin_ids=specific_pin_ids,
            destination=destination,
            log_fn=stream_log,
            live_frame_fn=stream_live_frame,
        )
        _fb_share_state["results"] = result.get("results", [])
        _fb_share_state["lastExcelReport"] = result.get("excelReport")
        _fb_share_state["lastPdfReport"] = result.get("pdfReport")
        broadcast_event("fb_share_complete", result)
    except Exception as e:
        _fb_share_state["error"] = str(e)
        stream_log("error", f"❌ Pinterest → Facebook share failed: {e}")
    finally:
        _fb_share_state["isRunning"] = False
        broadcast_event("state_change", {"fbShareRunning": False})


@app.post("/api/social/pinterest-facebook-share")
async def start_pinterest_facebook_share(
    req: PinterestFacebookShareRequest,
    background_tasks: BackgroundTasks,
):
    """Triggers the Pinterest → Facebook Page & Group share flow."""
    if _fb_share_state["isRunning"]:
        raise HTTPException(
            status_code=400,
            detail="Pinterest → Facebook share is already running.",
        )

    dest = req.destination or "both"
    background_tasks.add_task(
        run_pinterest_facebook_worker,
        req.pinCount,
        req.delaySeconds,
        req.targetBoardUrl,
        req.specificPinIds,
        dest,
    )
    dest_name = "WorldNewzs Page & Amazon Affiliate Group" if dest == "both" else "WorldNewzs Facebook Page Feed" if dest == "page" else "Amazon Affiliate Group"
    return {
        "success": True,
        "message": f"Pinterest → Facebook share started for {req.pinCount} unposted pin(s) to {dest_name} with {req.delaySeconds}s delay.",
        "pinCount": req.pinCount,
        "delaySeconds": req.delaySeconds,
        "targetBoardUrl": req.targetBoardUrl,
        "destination": dest,
    }


@app.get("/api/social/pinterest-facebook-status")
async def get_pinterest_facebook_status():
    """Returns current Pinterest → Facebook share flow status."""
    return _fb_share_state


@app.get("/api/social/facebook-pins")
async def get_facebook_pins_endpoint(
    page: int = Query(1, ge=1),
    pageSize: int = Query(12, ge=1, le=100),
    filter: str = Query("pending"),
    forceRefresh: bool = Query(False),
):
    """
    Returns lazy-loadable unposted Pinterest pins from Dhanvi Collection ready for Facebook automation.
    Posted pins are cleaned out and never shown in Facebook Automation Hub.
    """
    clean_posted_pins_from_cache(social_ledger)

    all_pins = await harvest_dhanvi_collection_pins(max_pins=300, force_live=forceRefresh)

    # Strictly exclude any posted pins
    unposted_pins = [p for p in all_pins if p.get("status") != "posted"]

    total_count = len(unposted_pins)
    total_pages = (total_count + pageSize - 1) // pageSize if total_count > 0 else 1
    start_idx = (page - 1) * pageSize
    paginated = unposted_pins[start_idx : start_idx + pageSize]

    # Verification checkpoint: auto-repair any missing image URLs on the active page
    cache_dirty = False
    for p in paginated:
        if not p.get("imageUrl") and p.get("pinId"):
            resolved = resolve_pin_image_from_pinterest(p["pinId"], p.get("pinUrl", ""))
            if resolved:
                p["imageUrl"] = resolved
                cache_dirty = True

    if cache_dirty:
        try:
            with open(DHANVI_PINS_CACHE, "w", encoding="utf-8") as f:
                json.dump(all_pins, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    posted_count = len(social_ledger.get_facebook_posted_ids())

    return {
        "pins": paginated,
        "totalCount": total_count,
        "page": page,
        "pageSize": pageSize,
        "totalPages": total_pages,
        "pendingCount": total_count,
        "postedCount": posted_count,
    }


@app.post("/api/social/clean-posted-pins")
async def clean_posted_pins_endpoint():
    """
    Purges all pins already posted to Facebook from the active Facebook Automation Hub cache.
    """
    res = clean_posted_pins_from_cache(social_ledger)
    return {
        "success": True,
        "message": f"Successfully cleaned {res['cleanedCount']} posted pin(s) from Facebook Automation Hub.",
        "cleanedCount": res["cleanedCount"],
        "remainingCount": res["remainingCount"],
        "totalBefore": res["totalBefore"],
    }


@app.get("/api/social/export-excel")
async def export_excel_endpoint():
    """Downloads formatted Excel (.xlsx) report of completed Facebook shares."""
    records = _fb_share_state.get("results") or social_ledger.get_facebook_records()
    if not records:
        records = [l for l in social_ledger.data.get("post_logs", []) if l.get("platform") == "facebook"]

    exp_res = export_facebook_shares_excel(records)
    if os.path.exists(exp_res["fullPath"]):
        return FileResponse(
            exp_res["fullPath"],
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=exp_res["fileName"],
        )
    raise HTTPException(status_code=404, detail="Excel report could not be generated.")


@app.get("/api/social/export-pdf")
async def export_pdf_endpoint():
    """Downloads dated PDF activity report with proof screenshots."""
    records = _fb_share_state.get("results") or social_ledger.get_facebook_records()
    if not records:
        records = [l for l in social_ledger.data.get("post_logs", []) if l.get("platform") == "facebook"]

    summary = {
        "totalPins": len(records),
        "successCount": sum(1 for r in records if r.get("status") == "success"),
        "skippedCount": sum(1 for r in records if r.get("status") == "skipped"),
        "failedCount": sum(1 for r in records if r.get("status") == "failed"),
    }
    pdf_res = generate_facebook_pdf_report(records, summary)
    if os.path.exists(pdf_res["fullPath"]):
        return FileResponse(
            pdf_res["fullPath"],
            media_type="application/pdf",
            filename=pdf_res["fileName"],
        )
    raise HTTPException(status_code=404, detail="PDF report could not be generated.")


@app.get("/api/social/live-frame")
async def get_live_frame():
    """Serves the latest live browser screenshot frame."""
    for fname in ["fb_live_frame.png", "fb_share_step2_created_page.png", "fb_share_step1_session_check.png"]:
        for base_dir in [SCREENSHOTS_DIR, PROJECT_ROOT]:
            candidate = os.path.join(base_dir, fname)
            if os.path.exists(candidate):
                return FileResponse(candidate, media_type="image/png")
    raise HTTPException(status_code=404, detail="No live frame available.")


@app.get("/api/social/proof/{image_name}")
async def get_proof_image(image_name: str):
    """Serves a proof screenshot file."""
    clean_name = os.path.basename(image_name)
    candidates = [
        os.path.join(SCREENSHOTS_DIR, clean_name),
        os.path.join(PROJECT_ROOT, clean_name),
        os.path.join(PROJECT_ROOT, "proofs", clean_name),
        os.path.join(PROJECT_ROOT, "backend", "reports", clean_name),
    ]
    for c in candidates:
        if os.path.exists(c):
            return FileResponse(c, media_type="image/png")
    raise HTTPException(status_code=404, detail="Proof image not found.")


# Serve React build in production
dist_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dist"))
if os.path.exists(dist_path):
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("[FastAPI] Starting AutomatePinterest on http://localhost:8000 (and proxy port 3001)")
    uvicorn.run(app, host="0.0.0.0", port=8000)
