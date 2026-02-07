"""
Central selectors for ChatGPT Web UI elements.

Each key maps to a list of CSS selector candidates (tried in order via comma-join).
Update these when ChatGPT changes its frontend.
"""

CHATGPT_URL = "https://chatgpt.com"

# ---------------------------------------------------------------------------
# Login & session selectors (used directly, not via SELECTORS dict)
# ---------------------------------------------------------------------------

# Cookie consent banner "Accept all" button
COOKIE_ACCEPT_BTN = (
    'button:has-text("Alle akzeptieren"), '
    'button:has-text("Accept all")'
)

# Login/register buttons visible when NOT logged in
NOT_LOGGED_IN_INDICATORS = (
    'button:has-text("Anmelden"), '
    'button:has-text("Log in"), '
    'button:has-text("Kostenlos registrieren"), '
    'button:has-text("Sign up")'
)

# Elements only visible when truly logged in (sidebar, user name, etc.)
LOGGED_IN_INDICATORS = (
    'a:has-text("Neuer Chat"), '
    'a:has-text("New chat"), '
    'button:has-text("Neuer Chat"), '
    'button:has-text("New chat"), '
    'nav[aria-label="Chat-Verlauf"], '
    'nav[aria-label="Chat history"]'
)

# ---------------------------------------------------------------------------
# Chat interaction selectors (used via find_element)
# ---------------------------------------------------------------------------

SELECTORS = {
    "prompt_textarea": [
        "#prompt-textarea",
        'div[contenteditable="true"]',
    ],
    "send_button": [
        'button[data-testid="send-button"]',
        'button[aria-label="Send prompt"]',
        'button[aria-label="Nachricht senden"]',
        'button[aria-label="Send"]',
    ],
    "stop_button": [
        'button[data-testid="stop-button"]',
        'button[aria-label="Stop generating"]',
        'button[aria-label="Antwort stoppen"]',
        'button[aria-label="Stop"]',
    ],
    "copy_button": [
        'button[data-testid="copy-turn-action-button"]',
        'button[aria-label="Copy"]',
        'button[aria-label="Kopieren"]',
    ],
    "file_input": [
        'input[type="file"]',
    ],
    "model_selector": [
        'button[data-testid="model-selector"]',
    ],
}

# Pre-built combined selectors for query_selector_all calls
COPY_BUTTON_ALL = ", ".join(SELECTORS["copy_button"])
STOP_BUTTON_ALL = ", ".join(SELECTORS["stop_button"])

# Conversation turn articles (each turn = one message)
CONVERSATION_TURN = 'article[data-testid^="conversation-turn"]'

# Assistant message content
ASSISTANT_MESSAGE = '[data-message-author-role="assistant"]'


async def find_element(page, key, timeout=10000):
    """Find a UI element using combined CSS selectors for the given key.

    Tries all selector candidates simultaneously via CSS comma-join.
    Returns the first matching element or raises RuntimeError.
    """
    candidates = SELECTORS.get(key)
    if not candidates:
        raise ValueError(f"Unknown selector key: {key}")
    combined = ", ".join(candidates)
    try:
        return await page.wait_for_selector(combined, timeout=timeout)
    except Exception:
        raise RuntimeError(f"Element '{key}' not found. Tried: {combined}")
