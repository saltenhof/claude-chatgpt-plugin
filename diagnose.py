"""Diagnostic script - opens ChatGPT and dumps page state."""

import asyncio
from browser import ChatGPTBrowser


async def diagnose():
    browser = ChatGPTBrowser()
    try:
        await browser.start(headless=False)
        await browser.navigate_to_chat()
        await browser.dismiss_cookie_consent()

        page = browser.page

        # Wait a bit for page to settle
        await page.wait_for_timeout(5000)

        # Take screenshot
        await page.screenshot(path="diagnose_screenshot.png", full_page=False)
        print("Screenshot saved: diagnose_screenshot.png")

        # Dump current URL
        print(f"\nURL: {page.url}")

        # Check for NOT logged in indicators
        for selector in [
            'button:has-text("Anmelden")',
            'button:has-text("Log in")',
            'button:has-text("Kostenlos registrieren")',
            'button:has-text("Sign up")',
        ]:
            el = await page.query_selector(selector)
            if el:
                visible = await el.is_visible()
                print(f"FOUND [{selector}] visible={visible}")
            else:
                print(f"NOT FOUND [{selector}]")

        # Check for logged in indicators
        for selector in [
            'a:has-text("Neuer Chat")',
            'a:has-text("New chat")',
            'nav',
            'nav[aria-label="Chat-Verlauf"]',
            'nav[aria-label="Chat history"]',
            '#prompt-textarea',
        ]:
            el = await page.query_selector(selector)
            if el:
                visible = await el.is_visible()
                print(f"FOUND [{selector}] visible={visible}")
            else:
                print(f"NOT FOUND [{selector}]")

        # Dump all <nav> elements
        navs = await page.query_selector_all('nav')
        print(f"\nTotal <nav> elements: {len(navs)}")
        for idx, nav in enumerate(navs):
            outer = await nav.evaluate("el => el.outerHTML.substring(0, 300)")
            print(f"  nav[{idx}]: {outer}")

        # Dump all <a> elements with text
        links = await page.query_selector_all('a')
        print(f"\nTotal <a> elements: {len(links)}")
        for link in links:
            text = await link.inner_text()
            if text.strip():
                href = await link.get_attribute("href")
                print(f"  <a href='{href}'>{text.strip()[:60]}</a>")

        # Keep browser open for manual inspection
        print("\nBrowser bleibt offen. ENTER druecken zum Schliessen...")
        input()
    finally:
        await browser.close()

asyncio.run(diagnose())
