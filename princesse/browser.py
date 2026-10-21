"""Browser automation tool (optional playwright)."""

from __future__ import annotations

from typing import Any

PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright  # type: ignore
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    sync_playwright = None  # type: ignore


def _require():
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("playwright not installed; pip install playwright && playwright install")


def browser_open(url: str, timeout: int = 30000) -> dict[str, Any]:
    _require()
    with sync_playwright() as p:  # type: ignore[misc]
        browser = p.chromium.launch(headless=True)  # type: ignore[union-attr]
        page = browser.new_page()
        page.goto(url, timeout=timeout)
        title = page.title()
        text = page.inner_text("body")[:5000]
        browser.close()
        return {"url": url, "title": title, "text": text}


def browser_screenshot(url: str, path: str = "screenshot.png") -> dict[str, Any]:
    _require()
    with sync_playwright() as p:  # type: ignore[misc]
        browser = p.chromium.launch(headless=True)  # type: ignore[union-attr]
        page = browser.new_page()
        page.goto(url)
        page.screenshot(path=path, full_page=True)
        browser.close()
        return {"url": url, "screenshot": path}


def register_browser_tools(registry=None) -> int:
    """Register browser tools only when playwright is installed.

    Advertising a tool that always fails wastes a model turn and tokens, so
    the tools are omitted entirely when the backend is unavailable.
    """
    from .tools import ToolRegistry, ToolCategory, ToolParameter, register_tool
    reg = registry or ToolRegistry.get_instance()
    if not PLAYWRIGHT_AVAILABLE:
        return 0
    register_tool(reg, "browser_open", browser_open, "Open a URL and extract text",
                 category=ToolCategory.NETWORK,
                 parameters=[ToolParameter(name="url", type="string", description="URL"),
                            ToolParameter(name="timeout", type="integer", description="Timeout ms", required=False, default=30000)])
    register_tool(reg, "browser_screenshot", browser_screenshot, "Screenshot a URL",
                 category=ToolCategory.NETWORK,
                 parameters=[ToolParameter(name="url", type="string", description="URL"),
                            ToolParameter(name="path", type="string", description="Output path", required=False, default="screenshot.png")])
    return 2
