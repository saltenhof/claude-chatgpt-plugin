"""CLI tool to interact with ChatGPT via Playwright browser automation.

Usage:
    python chatgpt_bridge.py login          -- one-time manual login
    python chatgpt_bridge.py send -m "Hi"   -- send message, print response
    python chatgpt_bridge.py send -m "Review this" -f doc.md
"""

import asyncio
import logging
import sys

import click
import pyperclip

from browser import ChatGPTBrowser
from chatgpt_selectors import (
    ASSISTANT_MESSAGE,
    CONVERSATION_TURN,
    COPY_BUTTON_ALL,
    find_element,
)

logger = logging.getLogger(__name__)

RESPONSE_POLL_INTERVAL_MS = 1000
RESPONSE_TIMEOUT_MS = 2_400_000  # 40 minutes

UPLOAD_TIMEOUT_MS = 60_000
UPLOAD_POLL_INTERVAL_MS = 500

# Overall timeout for send_message (prevents indefinite blocking)
SEND_TIMEOUT_S = 2_500  # ~41.7 min, slightly above response timeout

# Clipboard paste verification
MAX_PASTE_RETRIES = 3


# ---------------------------------------------------------------------------
# Core message logic (reusable from CLI and MCP server)
# ---------------------------------------------------------------------------

async def send_message(page, message: str, file_path: str | None = None) -> str:
    """Send a message to ChatGPT on an already-navigated, logged-in page.

    This function handles: optional file upload, typing the message,
    pressing Enter, and waiting for + extracting the response.
    Wraps the actual implementation with an overall timeout guard
    to prevent indefinite blocking.

    Returns the response as markdown text (or plain text fallback).

    Raises:
        TimeoutError: If the entire send/receive cycle exceeds SEND_TIMEOUT_S.
    """
    try:
        return await asyncio.wait_for(
            _send_message_impl(page, message, file_path),
            timeout=SEND_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        try:
            current_url = page.url
        except Exception:
            current_url = "<unavailable>"
        raise TimeoutError(
            f"send_message Gesamt-Timeout ({SEND_TIMEOUT_S}s) überschritten. "
            f"URL: {current_url}"
        )


async def _send_message_impl(page, message: str, file_path: str | None = None) -> str:
    """Internal implementation of send_message (without timeout guard)."""
    # --- count existing assistant messages (for conversation-continuation) ---
    existing_msgs = await page.query_selector_all(ASSISTANT_MESSAGE)
    previous_count = len(existing_msgs)

    # --- optional file upload ---
    if file_path:
        await _upload_file(page, file_path)

    # --- clear textarea and paste message via clipboard (verified) ---
    textarea = await find_element(page, "prompt_textarea")
    await _clear_paste_and_verify(page, textarea, message)

    # --- send via Enter key, fall back to send button ---
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(1000)

    # If send button is still visible, Enter didn't send — click it directly
    send_btn = await page.query_selector('button[data-testid="send-button"]')
    if send_btn:
        await send_btn.click(force=True)

    # --- wait for response & grab via copy button ---
    return await _wait_and_copy_response(page, previous_count)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """ChatGPT Browser Bridge - interact with ChatGPT from the command line."""


@cli.command()
def login():
    """Open browser for manual ChatGPT login. Session is persisted."""
    asyncio.run(_login())


@cli.command()
@click.option("--message", "-m", required=True, help="Message to send")
@click.option("--file", "-f", "file_path", default=None, help="File to attach")
@click.option("--headless/--no-headless", default=False, help="Run headless")
def send(message: str, file_path: str | None, headless: bool):
    """Send a message to ChatGPT and print the response (markdown)."""
    result = asyncio.run(_send(message, file_path, headless))
    if result:
        click.echo(result)
    else:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------

async def _login():
    browser = ChatGPTBrowser()
    try:
        await browser.start(headless=False)
        await browser.navigate_to_chat()
        await browser.dismiss_cookie_consent()

        if await browser.is_logged_in():
            click.echo("Bereits eingeloggt. Session ist gueltig.")
            # Keep open briefly to confirm, then close gracefully
            await browser.page.wait_for_timeout(3000)
            return

        click.echo(
            "Browser-Fenster geoeffnet. Bitte dort einloggen:\n"
            "  1. Auf 'Anmelden' klicken\n"
            "  2. Google SSO durchlaufen\n"
            "  3. Workspace 'QAware' auswaehlen\n"
            "Warte automatisch bis Login erkannt wird (max 5 Min)..."
        )

        if await browser.wait_for_login():
            click.echo("Login erfolgreich erkannt! Session wird gespeichert.")
            # Keep browser open so cookies/storage are fully written
            await browser.page.wait_for_timeout(5000)
        else:
            click.echo("Login nicht erkannt (Timeout). Bitte erneut versuchen.", err=True)
    finally:
        await browser.close()


# ---------------------------------------------------------------------------
# Send message flow (CLI wrapper)
# ---------------------------------------------------------------------------

async def _send(message: str, file_path: str | None, headless: bool) -> str:
    browser = ChatGPTBrowser()
    try:
        await browser.start(headless=headless)
        await browser.navigate_to_chat()
        await browser.dismiss_cookie_consent()

        if not await browser.is_logged_in():
            logger.error("Nicht eingeloggt. Erst 'login' ausfuehren.")
            return ""

        return await send_message(browser.page, message, file_path)

    finally:
        await browser.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _upload_file(page, file_path: str) -> None:
    """Attach a file via the hidden <input type='file'> element."""
    file_input = await page.query_selector('input[type="file"]')
    if file_input:
        await file_input.set_input_files(file_path)
    else:
        attach_btn = await find_element(page, "file_input", timeout=5000)
        await attach_btn.set_input_files(file_path)

    await _wait_for_upload_complete(page)
    logger.info("Attached: %s", file_path)


async def _wait_for_upload_complete(page, timeout_ms: int = UPLOAD_TIMEOUT_MS) -> None:
    """Wait until the file upload is finished by checking the send button state.

    During upload ChatGPT wraps the send button in a <span> and sets
    disabled="" on it.  Once the upload is complete the wrapper <span>
    disappears and the disabled attribute is removed.
    """
    # Give the UI a moment to start the upload and disable the button
    await page.wait_for_timeout(1000)

    elapsed_ms = 0
    while elapsed_ms < timeout_ms:
        disabled_btn = await page.query_selector(
            'button[data-testid="send-button"][disabled]'
        )
        if not disabled_btn:
            # Button is not disabled — upload is done (or was instant)
            return
        await page.wait_for_timeout(UPLOAD_POLL_INTERVAL_MS)
        elapsed_ms += UPLOAD_POLL_INTERVAL_MS

    logger.warning("Upload-Timeout erreicht, sende trotzdem...")


async def _clear_paste_and_verify(page, textarea, message: str) -> None:
    """Clear textarea, paste message via OS clipboard, and verify content.

    Replaces character-by-character typing with instant clipboard paste.
    This prevents race conditions where Enter is pressed before typing
    finishes, and ensures no leftover text from previous messages remains.

    Strategy per attempt:
      1. Focus textarea, select all (Ctrl+A), delete (Backspace)
      2. Copy message to OS clipboard, paste (Ctrl+V)
      3. Read textarea content back and compare with expected message

    Args:
        page: Playwright page object.
        textarea: The prompt textarea element handle.
        message: The exact message text to paste.

    Raises:
        RuntimeError: If verification fails after MAX_PASTE_RETRIES attempts.
    """
    expected = _normalize_text(message)

    for attempt in range(1, MAX_PASTE_RETRIES + 1):
        # Step 1: Focus and clear any existing content
        await textarea.click()
        await page.wait_for_timeout(200)
        await page.keyboard.press("Control+A")
        await page.wait_for_timeout(100)
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(300)

        # Step 2: Paste via OS clipboard (instant, React-safe)
        pyperclip.copy(message)
        await page.keyboard.press("Control+V")
        await page.wait_for_timeout(500)

        # Step 3: Verify textarea contains exactly the intended message
        actual = _normalize_text(await textarea.inner_text())

        if actual == expected:
            logger.info(
                "Textarea verified (%d chars, attempt %d)", len(expected), attempt
            )
            return

        logger.warning(
            "Textarea verification failed (attempt %d/%d): "
            "expected %d chars, got %d chars. First 100: %r",
            attempt,
            MAX_PASTE_RETRIES,
            len(expected),
            len(actual),
            actual[:100],
        )

        if attempt < MAX_PASTE_RETRIES:
            await page.wait_for_timeout(500)

    raise RuntimeError(
        f"Textarea content mismatch after {MAX_PASTE_RETRIES} attempts. "
        f"Expected {len(expected)} chars, "
        f"got {len(_normalize_text(await textarea.inner_text()))} chars."
    )


def _normalize_text(text: str) -> str:
    """Normalize text for comparison: strip whitespace and unify line endings."""
    return text.strip().replace("\r\n", "\n").replace("\r", "\n")


async def _wait_and_copy_response(page, previous_count: int = 0) -> str:
    """Wait for ChatGPT to finish responding, then extract via copy button.

    Args:
        previous_count: Number of assistant messages already present before
            sending.  The function polls until a *new* message appears
            (count > previous_count), which is essential for conversation
            continuation where old assistant messages already exist.

    Strategy:
      1. Poll until a new assistant message appears (count > previous_count).
      2. Wait for generation to complete (stop button disappears).
      3. Hover over the assistant's conversation turn to reveal action buttons.
      4. Click the copy button within that turn -> markdown in clipboard.
      5. Read clipboard. Fallback: DOM inner_text().
    """
    # Step 1: Poll until a NEW assistant message appears
    elapsed_ms = 0
    while elapsed_ms < 30000:
        msgs = await page.query_selector_all(ASSISTANT_MESSAGE)
        if len(msgs) > previous_count:
            break
        await page.wait_for_timeout(RESPONSE_POLL_INTERVAL_MS)
        elapsed_ms += RESPONSE_POLL_INTERVAL_MS
    else:
        logger.error("Keine neue Assistant-Antwort erkannt.")
        return ""

    # Step 2: Wait for generation to complete (stop button gone)
    elapsed_ms = 0
    while elapsed_ms < RESPONSE_TIMEOUT_MS:
        stop_btn = await page.query_selector(
            'button[data-testid="stop-button"], '
            'button[aria-label="Stop generating"], '
            'button[aria-label="Antwort stoppen"]'
        )
        if not stop_btn:
            break
        await page.wait_for_timeout(RESPONSE_POLL_INTERVAL_MS)
        elapsed_ms += RESPONSE_POLL_INTERVAL_MS

    if elapsed_ms >= RESPONSE_TIMEOUT_MS:
        raise TimeoutError("ChatGPT hat nicht innerhalb des Timeouts geantwortet")

    # Extra settle time
    await page.wait_for_timeout(1500)

    # Step 3: Find the last conversation turn (should be the assistant's)
    turns = await page.query_selector_all(CONVERSATION_TURN)
    if not turns:
        logger.warning("Keine Conversation-Turns gefunden, versuche DOM-Fallback.")
        return await _dom_scrape_response(page)

    last_turn = turns[-1]

    # Hover to reveal action buttons (copy, thumbs up/down, etc.)
    await last_turn.hover()
    await page.wait_for_timeout(800)

    # Step 4: Find copy button within this turn
    copy_btn = await last_turn.query_selector(
        'button[data-testid="copy-turn-action-button"], '
        'button[aria-label="Kopieren"], '
        'button[aria-label="Copy"]'
    )

    if not copy_btn:
        logger.warning("Copy-Button im Turn nicht gefunden, versuche DOM-Fallback.")
        return await _dom_scrape_response(page)

    # Clear clipboard sentinel
    pyperclip.copy("__SENTINEL__")

    # Click with force=True (trusted event, bypasses overlay)
    await copy_btn.click(force=True)
    await page.wait_for_timeout(800)

    # Step 5: Read clipboard
    clipboard_text = _read_clipboard(page)

    # If clipboard was updated, we have the markdown response
    if clipboard_text and clipboard_text != "__SENTINEL__":
        return clipboard_text

    # Fallback: try JS clipboard API
    try:
        js_text = await page.evaluate("navigator.clipboard.readText()")
        if js_text and js_text != "__SENTINEL__":
            return js_text
    except Exception:
        pass

    # Last resort: DOM scrape
    logger.warning("Clipboard nicht aktualisiert, verwende DOM-Fallback.")
    return await _dom_scrape_response(page)


def _read_clipboard(page) -> str:
    """Read OS-level clipboard via pyperclip."""
    try:
        return pyperclip.paste()
    except Exception:
        return ""


async def _dom_scrape_response(page) -> str:
    """Extract the last assistant response directly from the DOM (plain text)."""
    response_divs = await page.query_selector_all(ASSISTANT_MESSAGE)
    if response_divs:
        return await response_divs[-1].inner_text()
    return ""


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    cli()
