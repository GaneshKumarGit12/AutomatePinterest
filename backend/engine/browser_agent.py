import asyncio
from typing import Any

try:
    from playwright.async_api import Page, BrowserContext
except ImportError:
    Page = Any  # type: ignore
    BrowserContext = Any  # type: ignore

VISUAL_CURSOR_INJECTION = """
(() => {
  if (window.__visualCursorInstalled) return;
  window.__visualCursorInstalled = true;

  let cursor = document.getElementById('agent-visual-cursor');
  if (!cursor) {
    cursor = document.createElement('div');
    cursor.id = 'agent-visual-cursor';
    cursor.style.position = 'fixed';
    cursor.style.width = '24px';
    cursor.style.height = '24px';
    cursor.style.borderRadius = '50%';
    cursor.style.backgroundColor = '#E60023';
    cursor.style.border = '2px solid #ffffff';
    cursor.style.boxShadow = '0 0 16px rgba(230, 0, 35, 0.9)';
    cursor.style.pointerEvents = 'none';
    cursor.style.zIndex = '999999999';
    cursor.style.transform = 'translate(-50%, -50%)';
    cursor.style.transition = 'all 0.25s cubic-bezier(0.2, 0.9, 0.3, 1)';
    cursor.style.display = 'flex';
    cursor.style.alignItems = 'center';
    cursor.style.justifyContent = 'center';

    const badge = document.createElement('div');
    badge.id = 'agent-cursor-badge';
    badge.style.position = 'absolute';
    badge.style.left = '28px';
    badge.style.top = '-8px';
    badge.style.backgroundColor = 'rgba(15, 23, 42, 0.95)';
    badge.style.color = '#ffffff';
    badge.style.padding = '4px 10px';
    badge.style.borderRadius = '8px';
    badge.style.fontFamily = 'system-ui, sans-serif';
    badge.style.fontSize = '11px';
    badge.style.fontWeight = '700';
    badge.style.whiteSpace = 'nowrap';
    badge.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
    badge.style.border = '1px solid rgba(255,255,255,0.2)';
    badge.innerText = '⚡ AutomatePinterest';
    cursor.appendChild(badge);

    document.documentElement.appendChild(cursor);
  }

  window.__updateVisualCursor = (x, y, label) => {
    const c = document.getElementById('agent-visual-cursor');
    const b = document.getElementById('agent-cursor-badge');
    if (c) {
      c.style.left = x + 'px';
      c.style.top = y + 'px';
      c.style.display = 'flex';
    }
    if (b && label) b.innerText = label;
  };

  window.__triggerClickPulse = (x, y) => {
    const pulse = document.createElement('div');
    pulse.style.position = 'fixed';
    pulse.style.left = x + 'px';
    pulse.style.top = y + 'px';
    pulse.style.width = '12px';
    pulse.style.height = '12px';
    pulse.style.borderRadius = '50%';
    pulse.style.backgroundColor = 'transparent';
    pulse.style.border = '3px solid #E60023';
    pulse.style.transform = 'translate(-50%, -50%)';
    pulse.style.pointerEvents = 'none';
    pulse.style.zIndex = '999999998';
    pulse.style.transition = 'all 0.45s ease-out';
    document.documentElement.appendChild(pulse);

    requestAnimationFrame(() => {
      pulse.style.width = '64px';
      pulse.style.height = '64px';
      pulse.style.opacity = '0';
    });

    setTimeout(() => pulse.remove(), 500);
  };
})();
"""


async def install_visual_cursor(page: Page):
    """Installs visual animated cursor in the page DOM."""
    try:
        await page.evaluate(VISUAL_CURSOR_INJECTION)
    except Exception:
        pass


async def visual_move_and_click(page: Page, selector: str, label: str = "Clicking...") -> bool:
    """Moves mouse smoothly across screen to target selector, triggers pulse, and clicks."""
    try:
        el = await page.wait_for_selector(selector, state="visible", timeout=7000)
        if not el:
            return False

        box = await el.bounding_box()
        if not box:
            return False

        center_x = box["x"] + box["width"] / 2
        center_y = box["y"] + box["height"] / 2

        await install_visual_cursor(page)
        # Smooth mouse trajectory
        await page.mouse.move(center_x, center_y, steps=18)
        await page.evaluate(
            f"window.__updateVisualCursor && window.__updateVisualCursor({center_x}, {center_y}, '{label}');"
        )
        await asyncio.sleep(0.2)

        # Pulse and click
        await page.evaluate(
            f"window.__triggerClickPulse && window.__triggerClickPulse({center_x}, {center_y});"
        )
        try:
            await page.mouse.click(center_x, center_y)
        except Exception:
            await page.evaluate('(el) => el.click()', el)
        await asyncio.sleep(0.3)
        return True
    except Exception:
        # Fallback direct click if selector exists
        try:
            el = await page.query_selector(selector)
            if el:
                try:
                    await page.evaluate('(el) => el.click()', el)
                except Exception:
                    await el.click(timeout=5000, force=True)
                return True
        except Exception:
            pass
        return False


async def visual_type(page: Page, selector: str, text: str, label: str = "Typing..."):
    """Smoothly moves to input, focuses, and types text with visual feedback."""
    try:
        el = await page.wait_for_selector(selector, state="visible", timeout=7000)
        if not el:
            return

        box = await el.bounding_box()
        if box:
            center_x = box["x"] + box["width"] / 2
            center_y = box["y"] + box["height"] / 2
            await install_visual_cursor(page)
            await page.mouse.move(center_x, center_y, steps=15)
            await page.evaluate(
                f"window.__updateVisualCursor && window.__updateVisualCursor({center_x}, {center_y}, '{label}');"
            )

        try:
            await el.click(timeout=5000, force=True)
        except Exception:
            await page.evaluate('(el) => el.focus()', el)
        await el.fill("")
        await el.type(text, delay=20)
    except Exception:
        try:
            el = await page.query_selector(selector)
            if el:
                try:
                    await el.click(timeout=5000, force=True)
                except Exception:
                    await page.evaluate('(el) => el.focus()', el)
                await el.fill("")
                await el.type(text, delay=20)
        except Exception:
            pass
