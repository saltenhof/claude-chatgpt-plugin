"""MCP Server for ChatGPT Browser Bridge.

Exposes ChatGPT interaction as MCP tools via stdio transport.
The browser session persists across tool calls (lazy-initialized on first use).

Self-healing features:
  - Auto-restart on dead browser context
  - Auto-dismiss error dialogs (Try again, Regenerate)
  - Auto-visible-login when session expires in headless mode
  - Diagnostic tools (screenshot, diagnose, reset)

Usage:
    claude mcp add chatgpt-bridge -- python mcp_server.py
"""

import os
import sys

# Force UTF-8 on Windows — must happen before any I/O.
# MCP stdio transport expects UTF-8, but Windows Python defaults to CP1252/CP437.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONUTF8", "1")

import asyncio
import logging
import traceback
from pathlib import Path

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
# Startup validation
# ---------------------------------------------------------------------------

def _validate_environment():
    """Pre-flight check: verify all prerequisites before accepting tool calls."""
    errors = []

    try:
        import playwright  # noqa: F401
    except ImportError:
        errors.append("playwright nicht installiert (pip install playwright)")

    try:
        import pyperclip  # noqa: F401
    except ImportError:
        errors.append("pyperclip nicht installiert (pip install pyperclip)")

    chrome_paths = [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    ]
    if not any(p.exists() for p in chrome_paths):
        errors.append("Chrome nicht gefunden (erwartet in Program Files)")

    if errors:
        for error in errors:
            logger.error("PRE-FLIGHT FAIL: %s", error)
    else:
        logger.info("PRE-FLIGHT OK: Alle Voraussetzungen erfuellt")


_validate_environment()


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
        await _browser.start(headless=False)
    return _browser


async def _ensure_ready(new_chat: bool = True) -> ChatGPTBrowser:
    """Get browser, auto-heal problems, and verify login.

    Self-healing sequence:
      1. Check if browser context is alive → auto-restart if dead
      2. Detect and dismiss error dialogs (Cloudflare, session expired, etc.)
      3. Verify login → trigger auto-visible-login if needed

    Args:
        new_chat: If True (default), navigate to chatgpt.com to start a fresh
            chat.  If False and the browser has already navigated at least once,
            skip navigation so the current conversation is preserved.
    """
    global _navigated
    browser = await _get_browser()

    # Step 1: Liveness check
    if not await browser.check_context_alive():
        logger.warning("Browser-Kontext ist tot — starte neu...")
        await browser.switch_mode(headless=browser.headless)
        _navigated = False

    # Step 2: Navigate if needed
    if new_chat or not _navigated:
        await browser.navigate_to_chat()
        await browser.dismiss_cookie_consent()
        _navigated = True

    # Step 3: Detect and handle error states
    error_state = await browser.detect_and_dismiss_errors()
    if error_state == "cloudflare_challenge":
        raise RuntimeError(
            "Cloudflare-Challenge erkannt. Im Headless-Modus nicht lösbar. "
            "Optionen:\n"
            "  1. chatgpt_reset aufrufen und erneut versuchen\n"
            "  2. Manuell im Browser einloggen: python chatgpt_bridge.py login"
        )
    if error_state == "session_expired":
        logger.info("Session abgelaufen — starte Auto-Login...")
        await _auto_visible_login(browser)
        return browser

    # Step 4: Login check
    if not await browser.is_logged_in():
        logger.info("Nicht eingeloggt — starte Auto-Login...")
        await _auto_visible_login(browser)

    return browser


async def _auto_visible_login(browser: ChatGPTBrowser) -> None:
    """Switch to visible browser, wait for manual login, switch back to headless.

    Flow:
      1. Switch to visible mode (headless=False)
      2. Navigate to ChatGPT + dismiss cookie consent
      3. Wait up to 5 minutes for manual login
      4. Wait 3s for cookie persistence
      5. Switch back to headless mode
      6. Verify login works in headless
    """
    global _navigated

    logger.info("Öffne sichtbaren Browser für manuellen Login...")
    await browser.switch_mode(headless=False)
    _navigated = False

    await browser.navigate_to_chat()
    await browser.dismiss_cookie_consent()

    if await browser.is_logged_in():
        logger.info("Bereits eingeloggt — überspringe Login-Wartezeit.")
    else:
        logger.info("Warte auf manuellen Login (max 5 Min)...")
        login_ok = await browser.wait_for_login()
        if not login_ok:
            # Leave browser visible so user can still log in
            raise RuntimeError(
                "Login-Timeout (5 Min). Browser bleibt sichtbar.\n"
                "Optionen:\n"
                "  1. Im offenen Browser einloggen, dann chatgpt_send erneut aufrufen\n"
                "  2. chatgpt_reset aufrufen und nochmal versuchen"
            )

    # Wait for cookies to persist
    await browser.page.wait_for_timeout(3000)

    # Switch back to headless
    logger.info("Login erfolgreich — wechsle zurück in Headless-Modus...")
    await browser.switch_mode(headless=True)
    _navigated = False

    # Verify headless session works
    await browser.navigate_to_chat()
    await browser.dismiss_cookie_consent()
    _navigated = True

    if not await browser.is_logged_in():
        raise RuntimeError(
            "Login war sichtbar erfolgreich, aber Headless-Session ist nicht eingeloggt. "
            "Cookies wurden möglicherweise nicht korrekt persistiert.\n"
            "Optionen:\n"
            "  1. chatgpt_reset, dann erneut versuchen\n"
            "  2. python chatgpt_bridge.py login manuell ausführen"
        )

    logger.info("Headless-Session nach Auto-Login verifiziert.")


async def _gather_diagnostics(browser: ChatGPTBrowser) -> str:
    """Collect diagnostic information after a failure."""
    parts = []

    try:
        parts.append(f"URL: {browser.page.url}")
    except Exception:
        parts.append("URL: <unavailable>")

    parts.append(f"Headless: {browser.headless}")

    try:
        alive = await browser.check_context_alive()
        parts.append(f"Context alive: {alive}")
    except Exception:
        parts.append("Context alive: <check failed>")

    try:
        logged_in = await browser.is_logged_in()
        parts.append(f"Logged in: {logged_in}")
    except Exception:
        parts.append("Logged in: <check failed>")

    try:
        error_state = await browser.detect_and_dismiss_errors()
        parts.append(f"Error state: {error_state or 'none'}")
    except Exception:
        parts.append("Error state: <check failed>")

    try:
        screenshot_path = await browser.take_screenshot()
        parts.append(f"Screenshot: {screenshot_path}")
    except Exception:
        parts.append("Screenshot: <failed>")

    return "\n".join(parts)


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

    IMPORTANT — presentation rules for the response:
    - The raw tool result is already visible to the user. Do NOT repeat or
      quote the full response. Only reference specific parts when relevant.
    - Present your follow-up in a non-technical, conversational style.
      Never mention tool names, MCP, JSON, or internal mechanics.
    - Good: "ChatGPT meint dazu: [brief summary or comment]"
    - Bad:  Repeating the entire response, showing JSON, or mentioning
      chatgpt_send / MCP internals.
    - If the response is self-explanatory, a one-liner like
      "ChatGPT hat geantwortet." is enough.
    - On errors: explain the problem in plain language and suggest next
      steps without exposing stack traces or internal diagnostics.

    Args:
        message: The message to send to ChatGPT.
        file_path: Optional absolute path to a file to attach.
        new_chat: If True (default), navigate to chatgpt.com to start a fresh
            chat.  If False, continue in the current conversation.
    """
    try:
        browser = await _ensure_ready(new_chat)
        return await send_message(browser.page, message, file_path)
    except Exception as exc:
        logger.error("chatgpt_send fehlgeschlagen: %s", exc)
        # Try to gather diagnostics for actionable error message
        diag = ""
        try:
            if _browser is not None:
                diag = await _gather_diagnostics(_browser)
        except Exception:
            diag = "<Diagnose fehlgeschlagen>"

        return (
            f"Fehler: {exc}\n\n"
            f"Diagnostics:\n{diag}\n\n"
            "Empfohlene Aktionen:\n"
            "  1. chatgpt_status aufrufen für aktuellen Status\n"
            "  2. chatgpt_reset aufrufen für Neustart\n"
            "  3. chatgpt_diagnose aufrufen für detaillierte Analyse"
        )


@mcp.tool()
async def chatgpt_status() -> str:
    """Check ChatGPT login status and browser state.

    Returns a human-readable status string.
    """
    global _browser

    if _browser is None:
        return "Browser: not started. Will launch on first chatgpt_send call."

    try:
        alive = await _browser.check_context_alive()
        logged_in = await _browser.is_logged_in() if alive else False
        error_state = await _browser.detect_and_dismiss_errors() if alive else None

        try:
            current_url = _browser.page.url
        except Exception:
            current_url = "<unavailable>"

        return (
            f"Browser: {'running' if alive else 'DEAD'}\n"
            f"URL: {current_url}\n"
            f"Headless: {_browser.headless}\n"
            f"Logged in: {logged_in}\n"
            f"Error state: {error_state or 'none'}"
        )
    except Exception as exc:
        return f"Browser: error — {exc}"


@mcp.tool()
async def chatgpt_diagnose() -> str:
    """Detailed browser diagnostics including screenshot.

    Returns status details and a screenshot path for visual debugging.
    """
    global _browser

    if _browser is None:
        return "Browser nicht gestartet. Noch kein chatgpt_send aufgerufen."

    try:
        return await _gather_diagnostics(_browser)
    except Exception as exc:
        return f"Diagnose fehlgeschlagen: {exc}\n{traceback.format_exc()}"


@mcp.tool()
async def chatgpt_reset() -> str:
    """Force-kill browser and clear state. Next call will start fresh.

    Use this when the browser is stuck, crashed, or in an unrecoverable state.
    """
    global _browser, _navigated

    if _browser is not None:
        try:
            await _browser.close()
        except Exception as exc:
            logger.warning("Browser close fehlgeschlagen: %s", exc)
    _browser = None
    _navigated = False

    return "Browser zurückgesetzt. Nächster chatgpt_send startet frisch."


@mcp.tool()
async def chatgpt_screenshot() -> str:
    """Take a screenshot of the current browser page for visual debugging.

    Returns the file path to the screenshot PNG.
    """
    global _browser

    if _browser is None:
        return "Browser nicht gestartet. Kein Screenshot möglich."

    try:
        path = await _browser.take_screenshot()
        return f"Screenshot gespeichert: {path}"
    except Exception as exc:
        return f"Screenshot fehlgeschlagen: {exc}"


@mcp.tool()
async def chatgpt_health() -> str:
    """Quick health check. Returns 'ok' if MCP server is responsive.

    This is a lightweight liveness probe — no browser interaction.
    Use this to verify the MCP server is reachable before sending messages.
    """
    return "ok"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
