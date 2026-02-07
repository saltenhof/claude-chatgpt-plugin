"""Playwright browser management with persistent ChatGPT session."""

import asyncio
import logging
import os
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext, Page
from playwright_stealth import Stealth

from chatgpt_selectors import (
    CHATGPT_URL,
    COOKIE_ACCEPT_BTN,
    LOGGED_IN_INDICATORS,
    NOT_LOGGED_IN_INDICATORS,
)

logger = logging.getLogger(__name__)

# Browser profile lives in the user's home directory so it survives plugin
# updates (the plugin cache is ephemeral).  Override with CHATGPT_BRIDGE_DATA.
USER_DATA_DIR = Path(
    os.environ.get("CHATGPT_BRIDGE_DATA", Path.home() / ".chatgpt-bridge")
) / "user_data"

# Navigation: 30s per attempt, up to 3 attempts
NAV_TIMEOUT_MS = 30_000
NAV_MAX_RETRIES = 3

# Maximum time to wait for manual login (5 minutes)
LOGIN_TIMEOUT_MS = 300_000
LOGIN_POLL_INTERVAL_MS = 2000


class ChatGPTBrowser:
    """Manages a persistent Chromium browser context for ChatGPT interaction.

    The browser profile is stored in ~/.chatgpt-bridge/user_data/ so that the
    ChatGPT login session (cookies, localStorage) survives across invocations.
    """

    def __init__(self):
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._stealth = Stealth()
        self._headless = False

    @property
    def page(self) -> Page:
        """Return the active page. Raises if browser was not started."""
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def start(self, headless: bool = False) -> None:
        """Launch system Chrome with a persistent profile and clipboard permissions."""
        self._headless = headless
        await self._launch_context()

    async def _launch_context(self) -> None:
        """Internal: create Playwright context and page with stealth."""
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        # Clean stale lock files from previous crashed sessions
        for lock_file in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            lock_path = USER_DATA_DIR / lock_file
            if lock_path.exists():
                lock_path.unlink(missing_ok=True)

        if self._playwright is None:
            self._playwright = await async_playwright().start()

        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            channel="chrome",
            headless=self._headless,
            permissions=["clipboard-read", "clipboard-write"],
            viewport={"width": 1280, "height": 900},
            ignore_default_args=["--enable-automation", "--no-sandbox"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()

        await self._stealth.apply_stealth_async(self._page)

    async def _restart(self) -> None:
        """Close and relaunch the browser context (for retry after failed nav)."""
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        self._context = None
        self._page = None
        await asyncio.sleep(2)
        await self._launch_context()

    async def navigate_to_chat(self) -> None:
        """Open ChatGPT and wait for textarea. Retries up to 3x with full restart."""
        last_error = None

        for attempt in range(1, NAV_MAX_RETRIES + 1):
            try:
                await self.page.goto(
                    CHATGPT_URL, timeout=NAV_TIMEOUT_MS, wait_until="commit"
                )
                # Wait for textarea as "page ready" signal
                await self.page.wait_for_selector(
                    "#prompt-textarea", timeout=NAV_TIMEOUT_MS
                )
                await self.page.wait_for_timeout(1000)
                return  # success
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Navigation Versuch %d/%d fehlgeschlagen, starte Browser neu...",
                    attempt, NAV_MAX_RETRIES,
                )
                if attempt < NAV_MAX_RETRIES:
                    await self._restart()

        raise RuntimeError(
            f"ChatGPT nicht erreichbar nach {NAV_MAX_RETRIES} Versuchen"
        ) from last_error

    async def dismiss_cookie_consent(self) -> None:
        """Click 'Accept all' on the cookie consent banner if present."""
        try:
            accept_btn = await self.page.wait_for_selector(
                COOKIE_ACCEPT_BTN, timeout=3000
            )
            if accept_btn:
                await accept_btn.click()
                logger.info("Cookie-Consent akzeptiert.")
                await self.page.wait_for_timeout(500)
        except Exception:
            pass

    async def is_logged_in(self) -> bool:
        """Check whether the user is truly logged in (not just free mode).

        Returns False during page navigations (safe for polling).
        """
        try:
            current_url = self.page.url
            if "chatgpt.com" not in current_url:
                return False

            not_logged_in = await self.page.query_selector(NOT_LOGGED_IN_INDICATORS)
            if not_logged_in:
                is_visible = await not_logged_in.is_visible()
                if is_visible:
                    return False

            logged_in = await self.page.wait_for_selector(
                LOGGED_IN_INDICATORS, timeout=3000
            )
            return logged_in is not None
        except Exception:
            return False

    async def wait_for_login(self) -> bool:
        """Poll until the user completes login or timeout is reached."""
        elapsed_ms = 0
        while elapsed_ms < LOGIN_TIMEOUT_MS:
            try:
                if await self.is_logged_in():
                    return True
                await self.page.wait_for_timeout(LOGIN_POLL_INTERVAL_MS)
            except Exception:
                await asyncio.sleep(LOGIN_POLL_INTERVAL_MS / 1000)
            elapsed_ms += LOGIN_POLL_INTERVAL_MS
        return False

    async def close(self) -> None:
        """Shut down browser context and Playwright."""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
