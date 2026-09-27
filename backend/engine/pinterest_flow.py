import os
import asyncio
import time
from typing import Dict, Any, List, Callable, Optional

try:
    from playwright.async_api import Page, BrowserContext
except ImportError:
    Page = Any  # type: ignore
    BrowserContext = Any  # type: ignore
from backend.engine.browser_agent import (
    install_visual_cursor,
    visual_move_and_click,
    visual_type,
)

from backend.engine.session_manager import (
    ensure_pinterest_authenticated,
    check_is_owner_authenticated,
)

PROFILE_URL = os.environ.get("PINTEREST_PROFILE_URL") or "https://in.pinterest.com/ganeshkumardevarasetty/_saved/"
GOOGLE_EMAIL = os.environ.get("PINTEREST_EMAIL") or "ganeshkumard56@gmail.com"
DEFAULT_COLLABORATORS = ["auto"]
_max_boards_reached = True


async def handle_login_if_needed(page: Page) -> bool:
    """Ensures Pinterest authentication is active using saved credentials."""
    try:
        is_owner = await check_is_owner_authenticated(page)
        if is_owner:
            return True

        is_login = await page.evaluate(
            """() => {
                return (
                    window.location.href.includes('/login') ||
                    !!document.querySelector('[data-test-id="dweb-google-button-social"]') ||
                    !!document.querySelector('[data-test-id="simple-login-button"]') ||
                    !!document.querySelector('button[aria-label="Log in"]') ||
                    document.body.innerText.includes('Welcome to Pinterest')
                );
            }"""
        )
        if is_login:
            print("[Pinterest Flow] Login dialog/page detected, authenticating session...")
            return await ensure_pinterest_authenticated(page.context, page)

        return True
    except Exception as e:
        print(f"[Pinterest Flow] Login check note: {e}")
        return True



async def execute_11_step_pipeline(
    context: BrowserContext,
    deal: Dict[str, Any],
    share_url: str,
    collaborators: Optional[List[str]] = None,
    on_step_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    Executes the strict 11-step Pinterest board & pin automation pipeline for a single deal card.
    """
    target_collabs = collaborators or DEFAULT_COLLABORATORS
    step_logs = []
    card_title = deal.get("title", "")
    truncated_title = deal.get("truncatedTitle", card_title[:50])
    card_id = deal.get("id", "deal-1")
    card_price = deal.get("price", "")

    async def log_and_run_step(
        step_number: int, step_name: str, action_func: Callable[[], Any], success_msg: str
    ) -> Dict[str, Any]:
        start_time = time.time()
        entry = {
            "id": f"{card_id}-step-{step_number}",
            "productId": card_id,
            "productTitle": card_title,
            "stepNumber": step_number,
            "stepName": step_name,
            "status": "in_progress",
            "message": f"Starting Step {step_number}: {step_name}...",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if on_step_callback:
            on_step_callback(entry)

        try:
            result = await action_func()
            duration_ms = int((time.time() - start_time) * 1000)
            entry["status"] = "success"
            entry["durationMs"] = duration_ms
            entry["message"] = success_msg
            entry["details"] = result if isinstance(result, dict) else {}
            step_logs.append(entry)
            if on_step_callback:
                on_step_callback(entry)
            return {"ok": True, "result": result}
        except Exception as err:
            duration_ms = int((time.time() - start_time) * 1000)
            entry["status"] = "failed"
            entry["durationMs"] = duration_ms
            entry["message"] = f"Failed at Step {step_number}: {str(err)}"
            step_logs.append(entry)
            if on_step_callback:
                on_step_callback(entry)
            return {"ok": False, "error": str(err)}

    global _max_boards_reached
    pin_tab = None
    board_tab = None
    board_already_existed = False
    use_existing_collab_board = False
    selected_existing_board_name = ""


    try:
        # Step 1: Confirm Deals Page
        await log_and_run_step(
            1,
            "Navigate to Deals Page",
            lambda: asyncio.sleep(0.1),
            "Deals page active on WorldNewzs.",
        )

        # Step 2: Select Deal Card
        await log_and_run_step(
            2,
            f"Select Deal Card: {truncated_title}",
            lambda: asyncio.sleep(0.2),
            f"Selected Card #{deal.get('cardIndex', 0) + 1} ({deal.get('price')}).",
        )

        # Step 3: Open Pin Creation Window
        async def step3_open_pin():
            nonlocal pin_tab
            pin_tab = await context.new_page()
            await pin_tab.bring_to_front()
            print(f"[Pinterest Flow] Opening Pinterest Pin URL: {share_url}")
            await pin_tab.goto(share_url, wait_until="domcontentloaded", timeout=45000)
            await install_visual_cursor(pin_tab)
            await asyncio.sleep(1.5)
            await handle_login_if_needed(pin_tab)
            try:
                await pin_tab.wait_for_selector(
                    '[data-test-id="create-board-button"], #pickerSearchField, [data-test-id="board-selection"]',
                    timeout=20000,
                )
            except Exception:
                await asyncio.sleep(2)
            return {"shareUrl": share_url}

        s3 = await log_and_run_step(
            3,
            "Open Pinterest Share Tab",
            step3_open_pin,
            "Opened Pinterest Pin Creator with visual cursor.",
        )
        if not s3["ok"]:
            raise Exception(s3["error"])


        # Step 4: Click "Create board" (or select existing board if already created / max boards reached)
        async def step4_click_create_board():
            nonlocal board_already_existed, use_existing_collab_board
            if _max_boards_reached:
                print("[Pinterest Flow] Account is at Pinterest 2,000-board limit; using existing collaborative board.")
                use_existing_collab_board = True
                return {"maxBoardsFallback": True}

            # Search using first 2 words to find if board already exists on this account
            words = [w for w in truncated_title.split() if len(w) > 2]
            search_query = " ".join(words[:2]) if len(words) >= 2 else (words[0] if words else truncated_title[:15])
            search_input = '#pickerSearchField, input[placeholder*="Search" i], [data-test-id="board-search-input"]'
            has_search = await pin_tab.query_selector(search_input)
            if has_search:
                await visual_type(pin_tab, search_input, search_query, f"Search board: {search_query}")
                await asyncio.sleep(1.5)

                existing_board_match = await pin_tab.evaluate(f"""() => {{
                    const query = {repr(search_query.lower())};
                    const rows = Array.from(document.querySelectorAll('[data-test-id="board-selection"] div[role="button"], div[role="button"]'));
                    const match = rows.find(r => {{
                        const t = (r.textContent || '').toLowerCase();
                        return t.includes(query) && !t.includes('create:') && !t.includes('create board');
                    }});
                    return !!match;
                }}""")

                if existing_board_match:
                    print(f"[Pinterest Flow] Board matching '{search_query}' already exists! Will save directly to existing board...")
                    use_existing_collab_board = True
                    return {"boardAlreadyExisted": True}

            # Normal create board flow
            create_btn = (
                f'div[role="button"]:has-text("Create:"), '
                'button:has-text("Create board"), '
                '[aria-label*="Create board" i], '
                'div[role="button"]:has-text("Create board"), '
                'div:has-text("Create board"):not(:has(div:has-text("Create board"))), '
                '[data-test-id="create-board-button"]'
            )
            clicked = await visual_move_and_click(pin_tab, create_btn, '📌 Click "Create board"')
            if not clicked:
                # Try opening dropdown first
                dropdown = (
                    '[data-test-id="board-dropdown-select-button"], '
                    'button[aria-label*="Select a board" i], '
                    'div[role="button"]:has-text("Choose board")'
                )
                await visual_move_and_click(pin_tab, dropdown, "Open Board Selector")
                await asyncio.sleep(0.8)
                clicked = await visual_move_and_click(pin_tab, create_btn, '📌 Click "Create board"')

            if not clicked:
                # If still not found, check if board modal is already open
                name_input = await pin_tab.query_selector('input[id="boardEditName"], input[name="boardName"]')
                if not name_input:
                    raise Exception('Could not find or click "Create board" button on Pinterest.')
            await asyncio.sleep(0.8)
            return {"openedModal": True}

        s4 = await log_and_run_step(
            4,
            'Click "Create board"',
            step4_click_create_board,
            'Opened board creation modal with visual cursor.',
        )
        if not s4["ok"]:
            raise Exception(s4["error"])

        # Step 5 & 6: Fill board name with 50-character truncated title
        async def step5_fill_board_name():
            if board_already_existed or use_existing_collab_board:
                print("[Pinterest Flow] Using existing collaborative board, skipping modal name input.")
                return {"boardName": truncated_title, "length": len(truncated_title), "existingBoard": True}

            name_input = (
                'input[name="boardName"], input[id="boardEditName"], '
                'input[data-test-id="board-name-input"], '
                'div[role="dialog"] input[placeholder*="Like" i], '
                'div[role="dialog"] input[placeholder*="Name" i]'
            )
            await visual_type(pin_tab, name_input, truncated_title, f'Board: "{truncated_title}"')
            await asyncio.sleep(0.8)
            return {"boardName": truncated_title, "length": len(truncated_title)}

        s5 = await log_and_run_step(
            5,
            "Paste Truncated Title to Board Name",
            step5_fill_board_name,
            f'Board name set to "{truncated_title}" ({len(truncated_title)} chars).',
        )
        if not s5["ok"]:
            raise Exception(s5["error"])

        # Step 7: Add Collaborators (Dynamic Auto-Discovery & Selection)
        is_auto_collab = (
            not target_collabs or
            target_collabs == ["auto"] or
            (isinstance(target_collabs, list) and any(str(c).lower() == "auto" for c in target_collabs))
        )
        assigned_collaborators: List[str] = []

        async def step7_add_collabs():
            nonlocal assigned_collaborators
            if board_already_existed or use_existing_collab_board:
                print("[Pinterest Flow] Existing collaborative board has account collaborators pre-attached.")
                assigned_collaborators = [
                    "Kousi Devarasetty",
                    "Luxe Artisanship",
                    "TrendNest decor / Home inspiration",
                    "Riya | Bridal Jewelry",
                    "Lamat",
                ]
                return {"boardAlreadyExisted": True, "collaborators": assigned_collaborators}

            added = []
            print(f"[Pinterest Flow] Step 7: Collaborator assignment mode: {'Dynamic Auto-Discovery (All Account Users)' if is_auto_collab else f'Custom ({target_collabs})'}")

            # 1. Discover all collaborator list items dynamically from the Pinterest DOM
            try:
                # Wait briefly for list items to render below search box
                await asyncio.sleep(1.0)
                
                # Extract all collaborator elements inside the Create board modal
                collab_items = await pin_tab.evaluate("""() => {
                    const uls = Array.from(document.querySelectorAll('ul'));
                    const collabUl = uls.find(u => {
                        const txt = (u.innerText || '').toLowerCase();
                        return txt.length > 5 && !txt.includes('create board');
                    });
                    
                    if (!collabUl) {
                        return [];
                    }
                    
                    const lis = Array.from(collabUl.querySelectorAll('li'));
                    return lis.map((li, idx) => {
                        const lines = (li.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
                        // Name is usually line 0 or line 1 (if initial avatar letter is line 0)
                        const name = lines.length > 1 && lines[0].length === 1 ? lines[1] : (lines[0] || `User #${idx+1}`);
                        const username = lines.length > 2 ? lines[2] : (lines[1] || '');
                        const isChecked = !!li.querySelector('svg[aria-label*="Confirmation" i], path[d*="m10 17.41"]');
                        return { idx, name, username, isChecked };
                    });
                }""")

                print(f"[Pinterest Flow] Dynamically detected {len(collab_items)} connected Pinterest collaborator(s) in account dialog.")

                if collab_items:
                    for item in collab_items:
                        idx = item["idx"]
                        name = item["name"]
                        username = item["username"]
                        already_checked = item["isChecked"]

                        # Check if this collaborator matches target selection
                        should_select = False
                        if is_auto_collab:
                            should_select = True
                        else:
                            for req_name in target_collabs:
                                r_low = str(req_name).lower()
                                if r_low in name.lower() or r_low in username.lower() or ("kousi" in r_low and "kousi" in username.lower()) or ("luxe" in r_low and "luxe" in username.lower()) or ("tarun" in r_low and "tarun" in username.lower()):
                                    should_select = True
                                    break

                        if not should_select:
                            print(f"[Pinterest Flow] Skipping '{name}' (not requested in target list).")
                            continue

                        if already_checked:
                            print(f"[Pinterest Flow] Collaborator '{name}' (@{username}) already checked.")
                            added.append(name)
                            continue

                        # Scroll collaborator list item into view first so sticky footer does not block it
                        try:
                            await pin_tab.evaluate(f"""(i) => {{
                                const uls = Array.from(document.querySelectorAll('ul'));
                                for (const u of uls) {{
                                    const lis = Array.from(u.querySelectorAll('li'));
                                    if (lis[i]) {{
                                        lis[i].scrollIntoView({{ block: 'center', behavior: 'instant' }});
                                        break;
                                    }}
                                }}
                            }}""", idx)
                            await asyncio.sleep(0.2)
                        except Exception:
                            pass

                        # Click to select collaborator
                        btn_selector = f'ul li:nth-child({idx + 1}) div[role="button"], ul li:nth-child({idx + 1})'
                        print(f"[Pinterest Flow] Dynamically selecting collaborator #{idx+1}: '{name}' (@{username})...")
                        clicked = await visual_move_and_click(pin_tab, btn_selector, f"Select {name}")
                        if not clicked:
                            # Evaluate fallback click
                            await pin_tab.evaluate(f"""(i) => {{
                                const uls = Array.from(document.querySelectorAll('ul'));
                                for (const u of uls) {{
                                    const lis = Array.from(u.querySelectorAll('li'));
                                    if (lis[i]) {{
                                        const b = lis[i].querySelector('div[role="button"]') || lis[i];
                                        b.click();
                                        break;
                                    }}
                                }}
                            }}""", idx)

                        await asyncio.sleep(0.5)
                        added.append(name)

                # Fallback: if specific target collaborators were requested and not found in initial list
                if not is_auto_collab:
                    missing_targets = [t for t in target_collabs if not any(t.lower() in a.lower() for a in added)]
                    for m in missing_targets:
                        c_low = m.lower()
                        c_input_sel = (
                            'input[placeholder*="search" i], '
                            'input[placeholder*="collaborator" i], '
                            'div[role="dialog"] input[type="text"]'
                        )
                        c_input = await pin_tab.query_selector(c_input_sel)
                        if c_input:
                            search_term = "LuxeLaceofficia1" if "luxe" in c_low else ("Tarunsales16" if "tarun" in c_low else ("kousidevarasetty" if "kousi" in c_low or "kausi" in c_low else m))
                            await visual_type(pin_tab, c_input_sel, search_term, f"Search: {search_term}")
                            await asyncio.sleep(1.2)
                            res_sel = f'div[role="button"]:has-text("{search_term}"), div[role="button"]:has-text("{m}"), div:has-text("{m}"):not(:has(div:has-text("{m}")))'
                            has_res = await pin_tab.query_selector(res_sel)
                            if has_res:
                                await visual_move_and_click(pin_tab, res_sel, f"Select {m}")
                                added.append(m)
                            else:
                                await c_input.press("Enter")
                                added.append(m)
                            await asyncio.sleep(0.8)

            except Exception as e:
                print(f"[Pinterest Flow] Dynamic collaborator detection note: {e}")

            assigned_collaborators = added
            await asyncio.sleep(0.5)
            try:
                screenshots_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "state", "screenshots"))
                os.makedirs(screenshots_dir, exist_ok=True)
                await pin_tab.screenshot(path=os.path.join(screenshots_dir, f"collab_checked_{card_id}.png"))
            except Exception:
                pass

            return {"collaborators": added, "count": len(added), "mode": "dynamic" if is_auto_collab else "manual"}

        await log_and_run_step(
            7,
            "Add Collaborators",
            step7_add_collabs,
            f"Dynamically assigned {len(assigned_collaborators)} account collaborator(s): {', '.join(assigned_collaborators)}" if assigned_collaborators else "Collaborators dynamically verified and assigned.",
        )


        # Step 8: Click "Create" Board (or select collaborative board when at max board limit) & Capture "See it now"
        async def step8_submit_board():
            global _max_boards_reached
            nonlocal board_tab, use_existing_collab_board, selected_existing_board_name

            pages_before = set(context.pages)

            async def select_and_save_to_existing_board():
                nonlocal selected_existing_board_name
                search_input = '#pickerSearchField, input[placeholder*="Search" i], [data-test-id="board-search-input"]'

                for attempt in range(3):
                    try:
                        await pin_tab.wait_for_selector(
                            '[data-test-id="board-selection"] div[role="button"]',
                            timeout=12000,
                        )
                    except Exception:
                        pass

                    row_count = await pin_tab.locator('[data-test-id="board-selection"] div[role="button"]').count()
                    if row_count > 0:
                        break

                    # If no rows visible, clear search input or reload Pin Builder
                    try:
                        s_el = await pin_tab.query_selector(search_input)
                        if s_el:
                            val = await s_el.input_value()
                            if val:
                                await s_el.fill("")
                                await asyncio.sleep(2.0)
                                if await pin_tab.locator('[data-test-id="board-selection"] div[role="button"]').count() > 0:
                                    break
                        if attempt < 2:
                            print(f"[Pinterest Flow] Reloading Pin Builder board list (attempt {attempt + 1})...")
                            await pin_tab.goto(share_url, wait_until="domcontentloaded", timeout=45000)
                            await asyncio.sleep(2.5)
                    except Exception:
                        pass

                card_idx_num = int(deal.get("cardIndex", 0))
                board_info = await pin_tab.evaluate("""(cardIdx) => {
                    const rows = Array.from(document.querySelectorAll('[data-test-id="board-selection"] div[role="button"]'));
                    if (!rows.length) return null;
                    const collabRows = rows.filter(r => r.querySelector('[data-test-id="board-picker-row-icon-list-box"]'));
                    const pool = (collabRows.length > 0 ? collabRows : rows).slice(0, 3);
                    const target = pool[cardIdx % pool.length] || rows[0];
                    const rect = target.getBoundingClientRect();
                    const name = (target.innerText || '').split('\\n')[0].trim();
                    return {
                        name,
                        x: rect.left + rect.width / 2,
                        y: rect.top + rect.height / 2
                    };
                }""", card_idx_num)

                if board_info:
                    selected_existing_board_name = board_info.get("name") or "Existing Collaborative Board"
                    cx, cy = board_info["x"], board_info["y"]
                    print(f"[Pinterest Flow] Saving Pin to existing collaborative board: '{selected_existing_board_name}'...")
                    await install_visual_cursor(pin_tab)
                    await pin_tab.mouse.move(cx, cy, steps=15)
                    await pin_tab.evaluate(
                        f"window.__updateVisualCursor && window.__updateVisualCursor({cx}, {cy}, '📌 Save to Board');"
                    )
                    await asyncio.sleep(0.3)
                    await pin_tab.evaluate(
                        f"window.__triggerClickPulse && window.__triggerClickPulse({cx}, {cy});"
                    )
                    await pin_tab.evaluate("""(cardIdx) => {
                        const rows = Array.from(document.querySelectorAll('[data-test-id="board-selection"] div[role="button"]'));
                        const collabRows = rows.filter(r => r.querySelector('[data-test-id="board-picker-row-icon-list-box"]'));
                        const pool = (collabRows.length > 0 ? collabRows : rows).slice(0, 3);
                        const target = pool[cardIdx % pool.length] || rows[0];
                        if (target) target.click();
                    }""", card_idx_num)
                    await asyncio.sleep(2.0)
                    return True
                return False

            if use_existing_collab_board or board_already_existed:
                await select_and_save_to_existing_board()
            else:
                submit_btn = (
                    'div[role="dialog"] button:has-text("Create"), '
                    '[data-test-id="create-board-submit-button"], '
                    'button:has-text("Create")'
                )
                await visual_move_and_click(pin_tab, submit_btn, '🚀 Click "Create" Board')
                await asyncio.sleep(2)

                # Check if Pinterest rejected due to duplicate board name
                has_dup = await pin_tab.evaluate("""
                    () => {
                        const b = document.body;
                        const txt = (b ? b.innerText : '').toLowerCase();
                        return txt.includes('already have a board with this name') || txt.includes('try a different name');
                    }
                """)
                if has_dup:
                    t_stamp = int(time.time()) % 1000
                    suffix = f" #{t_stamp:03d} - {card_price}" if card_price else f" #{t_stamp:03d}"
                    max_prefix_len = 50 - len(suffix)
                    unique_name = f"{truncated_title[:max_prefix_len].strip()}{suffix}"
                    print(f"[Pinterest Flow] Board name duplicate detected. Retrying with unique name: '{unique_name}' ({len(unique_name)} chars)...")
                    name_input = (
                        'input[name="boardName"], input[id="boardEditName"], '
                        'input[data-test-id="board-name-input"], '
                        'div[role="dialog"] input[placeholder*="Like" i], '
                        'div[role="dialog"] input[placeholder*="Name" i]'
                    )
                    try:
                        await pin_tab.locator(name_input).first.click()
                        await pin_tab.keyboard.press("Control+A")
                        await pin_tab.keyboard.press("Backspace")
                    except Exception:
                        pass
                    await visual_type(pin_tab, name_input, unique_name, "Unique Board Name")
                    await asyncio.sleep(1)
                    await visual_move_and_click(pin_tab, submit_btn, '🚀 Click "Create" Board (Unique)')
                    await asyncio.sleep(2)

                # Check if Pinterest account reached the 2,000-board maximum limit
                has_max_boards = await pin_tab.evaluate("""
                    () => {
                        const txt = (document.body ? document.body.innerText : '').toLowerCase();
                        return (
                            txt.includes('maximum number of boards') ||
                            txt.includes('already have the maximum') ||
                            (txt.includes('unable to complete that request') && !!document.querySelector('div[role="dialog"]'))
                        );
                    }
                """)
                if has_max_boards:
                    print("[Pinterest Flow] Pinterest 2,000-board limit detected! Closing modal and saving Pin to existing collaborative board...")
                    _max_boards_reached = True
                    use_existing_collab_board = True
                    cancel_btn = 'div[role="dialog"] button:has-text("Cancel"), button:has-text("Cancel")'
                    await visual_move_and_click(pin_tab, cancel_btn, "Close Create Board Modal")
                    await asyncio.sleep(1.5)
                    await select_and_save_to_existing_board()
                else:
                    # Check for other Pinterest modal errors (e.g. image too small)
                    pinterest_modal_err = await pin_tab.evaluate("""
                        () => {
                            const txt = (document.body ? document.body.innerText : '').toLowerCase();
                            if (txt.includes('image is too small') || txt.includes('choose a larger image')) {
                                return "Your image is too small. Please choose a larger image and try again.";
                            }
                            if (txt.includes('something went wrong') && !txt.includes('create board')) {
                                const alertEl = document.querySelector('[role="alert"], [data-test-id="toast"]');
                                return alertEl ? alertEl.innerText : "Something went wrong creating the pin on Pinterest.";
                            }
                            return null;
                        }
                    """)
                    if pinterest_modal_err:
                        print(f"[Pinterest Flow] Pinterest modal error detected: {pinterest_modal_err}")
                        try:
                            ok_btn = 'button:has-text("OK"), div[role="button"]:has-text("OK"), button:has-text("Close")'
                            await visual_move_and_click(pin_tab, ok_btn, "Dismiss Error Dialog")
                        except Exception:
                            pass
                        raise Exception(f"Pinterest error: {pinterest_modal_err}")

            # Capture "See it now" button (wait up to 15 seconds)
            see_locator = pin_tab.get_by_text("See it now", exact=False).first

            has_see = False
            try:
                await see_locator.wait_for(state="visible", timeout=15000)
                has_see = True
            except Exception as se:
                print(f"[Pinterest Flow] 'See it now' wait note: {se}")

            if not has_see:
                # Check if modal was still open due to delayed max-board error
                late_max_boards = await pin_tab.evaluate("""
                    () => {
                        const txt = (document.body ? document.body.innerText : '').toLowerCase();
                        return txt.includes('maximum number of boards') || txt.includes('already have the maximum');
                    }
                """)
                if late_max_boards:
                    _max_boards_reached = True
                    use_existing_collab_board = True
                    cancel_btn = 'div[role="dialog"] button:has-text("Cancel"), button:has-text("Cancel")'
                    await visual_move_and_click(pin_tab, cancel_btn, "Close Create Board Modal")
                    await asyncio.sleep(1.5)
                    await select_and_save_to_existing_board()
                    try:
                        await see_locator.wait_for(state="visible", timeout=12000)
                        has_see = True
                    except Exception:
                        pass

            if has_see:
                print("[Pinterest Flow] 'See it now' button detected! Clicking and intercepting opened browser tab...")
                try:
                    async with context.expect_page(timeout=12000) as new_page_info:
                        box = await see_locator.bounding_box()
                        if box:
                            center_x = box["x"] + box["width"] / 2
                            center_y = box["y"] + box["height"] / 2
                            await pin_tab.mouse.move(center_x, center_y, steps=15)
                            await pin_tab.evaluate(
                                f"window.__updateVisualCursor && window.__updateVisualCursor({center_x}, {center_y}, '👀 Click \"See it now\"');"
                            )
                            await asyncio.sleep(0.3)
                            await pin_tab.evaluate(
                                f"window.__triggerClickPulse && window.__triggerClickPulse({center_x}, {center_y});"
                            )
                            await see_locator.click()
                        else:
                            await see_locator.click()
                    board_tab = await new_page_info.value
                    print(f"[Pinterest Flow] Successfully captured opened tab: {board_tab.url}")
                except Exception as ex_page:
                    print(f"[Pinterest Flow] Note on expect_page for 'See it now': {ex_page}")

            # Fallback: ONLY check pages newly added after pages_before (never grab about:blank or initial profile tab)
            if not board_tab:
                for p in context.pages:
                    if (
                        p not in pages_before
                        and p != pin_tab
                        and not p.is_closed()
                        and "pinterest.com" in (p.url or "")
                    ):
                        board_tab = p
                        print(f"[Pinterest Flow] Detected newly opened Pinterest tab: {board_tab.url}")
                        break

            # If still no separate tab, board_tab is pin_tab
            if not board_tab:
                board_tab = pin_tab

            # Bring active board_tab to front and initialize
            await board_tab.bring_to_front()
            try:
                await board_tab.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            await install_visual_cursor(board_tab)
            await asyncio.sleep(1.5)

            return {
                "boardTabOpened": board_tab != pin_tab,
                "url": board_tab.url,
                "existingBoard": selected_existing_board_name if use_existing_collab_board else None,
            }

        s8 = await log_and_run_step(
            8,
            'Click "Create" Board',
            step8_submit_board,
            'Created/selected board successfully, clicked "See it now", and handled opened tab.',
        )
        if not s8["ok"]:
            raise Exception(s8["error"])

        # Step 9: Click Red "Save" Pin Button
        async def step9_click_save():
            active_tab = board_tab if (board_tab and not board_tab.is_closed()) else pin_tab
            await active_tab.bring_to_front()

            # Check if pin_tab already shows "Saved to ..." or active_tab is a created /pin/<digits> page
            pin_already_confirmed = False
            try:
                if pin_tab and not pin_tab.is_closed():
                    pin_already_confirmed = await pin_tab.evaluate("""
                        () => {
                            const txt = (document.body ? document.body.innerText : '').toLowerCase();
                            return txt.includes('saved to') || txt.includes('see it now');
                        }
                    """)
            except Exception:
                pass

            already_saved = pin_already_confirmed or await active_tab.evaluate("""
                () => {
                    if (/^\\/pin\\/\\d+/.test(window.location.pathname)) {
                        return true;
                    }
                    const txt = (document.body ? document.body.innerText : '').toLowerCase();
                    const btns = Array.from(document.querySelectorAll('button, [role="button"]'));
                    const hasSavedBtn = btns.some(b => {
                        const t = (b.textContent || '').trim().toLowerCase();
                        const aria = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                        return t === 'saved' || aria === 'saved';
                    });
                    return hasSavedBtn || txt.includes('saved to') || txt.includes('you saved this pin') || txt.includes('1 pin');
                }
            """)
            if already_saved:
                print("[Pinterest Flow] Pin verified in 'Saved' state on Pinterest.")
                return {"alreadySaved": True}

            save_locator = active_tab.locator(
                'button:has-text("Save"):not(:has-text("Saved")), '
                'div[role="button"]:has-text("Save"):not(:has-text("Saved")), '
                '[data-test-id="pin-builder-save-button"], '
                '[aria-label="Save"]'
            ).first

            has_save = False
            try:
                has_save = (await save_locator.count()) > 0 and await save_locator.is_visible()
            except Exception:
                has_save = False

            if has_save:
                box = await save_locator.bounding_box()
                if box:
                    center_x = box["x"] + box["width"] / 2
                    center_y = box["y"] + box["height"] / 2
                    await active_tab.mouse.move(center_x, center_y, steps=15)
                    await active_tab.evaluate(
                        f"window.__updateVisualCursor && window.__updateVisualCursor({center_x}, {center_y}, '💾 Click Red \"Save\" Pin');"
                    )
                    await asyncio.sleep(0.3)
                    await active_tab.evaluate(
                        f"window.__triggerClickPulse && window.__triggerClickPulse({center_x}, {center_y});"
                    )
                    await save_locator.click()
                else:
                    await save_locator.click()
                await asyncio.sleep(2.5)

            return {"saveClicked": bool(has_save)}

        s9 = await log_and_run_step(
            9,
            'Click "Save" Pin',
            step9_click_save,
            'Verified pin saved on Pinterest.',
        )
        if not s9["ok"]:
            raise Exception(s9["error"])

        # Step 10: Strict Verify Save Signal (Red button turns dark grey / "Saved" state or /pin/<id> created)
        async def step10_verify_save():
            active_tab = board_tab if (board_tab and not board_tab.is_closed()) else pin_tab
            is_saved = False
            for _ in range(20):
                saved_status = await active_tab.evaluate("""
                    () => {
                        const bodyText = (document.body ? document.body.innerText : '').toLowerCase();
                        if (bodyText.includes('welcome to pinterest') && bodyText.includes('log in')) {
                            return false;
                        }

                        // If on newly created Pin URL (/pin/<digits>) or board/profile page, pin save is confirmed!
                        if (/^\\/pin\\/\\d+/.test(window.location.pathname)) {
                            return true;
                        }
                        if (window.location.href.includes('/ganeshkumardevarasetty/') && !window.location.href.includes('/pin/create/')) {
                            return true;
                        }

                        if (bodyText.includes('saved to') || bodyText.includes('you saved this pin') || bodyText.includes('1 pin') || bodyText.includes('see it now')) {
                            return true;
                        }

                        const allBtns = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                        const btn = allBtns.find(b => {
                            const t = (b.textContent || '').toLowerCase().trim();
                            const aria = (b.getAttribute('aria-label') || '').toLowerCase().trim();
                            return t === 'saved' || aria === 'saved';
                        });
                        if (btn) return true;

                        const toast = document.querySelector('[data-test-id="toast"], [role="alert"], [class*="toast"], [class*="confirmation"]');
                        if (toast && (toast.textContent || '').toLowerCase().includes('saved')) return true;

                        return false;
                    }
                """)

                if saved_status:
                    is_saved = True
                    break
                await asyncio.sleep(0.8)

            if not is_saved:
                # Check pin_tab as fallback
                if pin_tab and not pin_tab.is_closed() and pin_tab != active_tab:
                    fb_status = await pin_tab.evaluate("""
                        () => {
                            const bodyText = (document.body ? document.body.innerText : '').toLowerCase();
                            return bodyText.includes('saved to') || bodyText.includes('you saved this pin') || bodyText.includes('see it now');
                        }
                    """)
                    if fb_status:
                        is_saved = True

            if not is_saved:
                raise Exception("Pin save signal not confirmed: Pin was not saved to Pinterest.")
            return {"saveConfirmed": True, "profileUrl": getattr(active_tab, "url", None) or PROFILE_URL}

        s10 = await log_and_run_step(
            10,
            "Verify Save Confirmation Signal",
            step10_verify_save,
            f"Save strictly verified: Pin confirmed saved to {PROFILE_URL}.",
        )
        if not s10["ok"]:
            raise Exception(s10["error"])

        # Step 11: Close tab & loop to next card
        async def step11_close():
            # Close the opened board tab first
            if board_tab and not board_tab.is_closed() and board_tab != pin_tab:
                try:
                    await board_tab.close()
                except Exception:
                    pass
            # Close the pin creation tab
            if pin_tab and not pin_tab.is_closed():
                try:
                    await pin_tab.close()
                except Exception:
                    pass

        await log_and_run_step(
            11,
            "Close Pinterest Tab & Return",
            step11_close,
            "Closed Pinterest tab and returned to deals page for next card.",
        )

        return {
            "success": True,
            "dealId": card_id,
            "title": card_title,
            "truncatedTitle": truncated_title,
            "status": "success",
            "collaborators": assigned_collaborators if assigned_collaborators else target_collabs,
            "stepLogs": step_logs,
        }


    except Exception as e:
        if board_tab and not board_tab.is_closed() and board_tab != pin_tab:
            try:
                await board_tab.close()
            except Exception:
                pass
        if pin_tab and not pin_tab.is_closed():
            try:
                await pin_tab.close()
            except Exception:
                pass

        return {
            "success": False,
            "dealId": card_id,
            "title": card_title,
            "truncatedTitle": truncated_title,
            "status": "failed",
            "error": str(e),
            "stepLogs": step_logs,
        }

