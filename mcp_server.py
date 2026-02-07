"""MCP Server for ChatGPT Browser Bridge.

Exposes ChatGPT interaction as MCP tools via stdio transport.
The browser session persists across tool calls (lazy-initialized on first use).

Usage:
    claude mcp add chatgpt-bridge -- python T:\\codebase\\claude_chatgpt\\mcp_server.py
"""

import asyncio
import logging
import sys

from mcp.server.fastmcp import FastMCP

from browser import ChatGPTBrowser
from chatgpt_bridge import send_message

# Logging to stderr — stdout is reserved for JSON-RPC (stdio transport)
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP("chatgpt-bridge")

# ---------------------------------------------------------------------------
# Persistent browser session
# ---------------------------------------------------------------------------

_browser: ChatGPTBrowser | None = None
_navigated: bool = False


async def _get_browser() -> ChatGPTBrowser:
    """Return the shared browser instance, launching it on first call."""
    global _browser
    if _browser is None:
        logger.info("Starte Browser (erster Aufruf)...")
        _browser = ChatGPTBrowser()
        await _browser.start(headless=True)
    return _browser


async def _ensure_ready(new_chat: bool = True) -> ChatGPTBrowser:
    """Get browser, optionally navigate to ChatGPT, and verify login.

    Args:
        new_chat: If True (default), navigate to chatgpt.com to start a fresh
            chat.  If False and the browser has already navigated at least once,
            skip navigation so the current conversation is preserved.
    """
    global _navigated
    browser = await _get_browser()

    if new_chat or not _navigated:
        await browser.navigate_to_chat()
        await browser.dismiss_cookie_consent()
        _navigated = True

    if not await browser.is_logged_in():
        raise RuntimeError(
            "Nicht eingeloggt. Bitte zuerst 'python chatgpt_bridge.py login' ausfuehren."
        )
    return browser


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def chatgpt_send(
    message: str,
    file_path: str | None = None,
    new_chat: bool = True,
) -> str:
    """Send a message to ChatGPT and return the response as markdown.

    Args:
        message: The message to send to ChatGPT.
        file_path: Optional absolute path to a file to attach.
        new_chat: If True (default), navigate to chatgpt.com to start a fresh
            chat.  If False, continue in the current conversation.
    """
    browser = await _ensure_ready(new_chat)
    return await send_message(browser.page, message, file_path)


@mcp.tool()
async def chatgpt_status() -> str:
    """Check ChatGPT login status and browser state.

    Returns a human-readable status string.
    """
    global _browser

    if _browser is None:
        return "Browser: not started. Will launch on first chatgpt_send call."

    try:
        logged_in = await _browser.is_logged_in()
        return (
            f"Browser: running\n"
            f"URL: {_browser.page.url}\n"
            f"Logged in: {logged_in}"
        )
    except Exception as exc:
        return f"Browser: error — {exc}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
