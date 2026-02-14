# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP Server (Python + Playwright) that lets Claude Code interact with ChatGPT via browser automation. Uses a persistent Chrome profile for session persistence across invocations. Also usable as CLI tool for login and debugging.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# One-time manual login (opens browser for Google SSO)
python chatgpt_bridge.py login

# Send a message and print the response (markdown)
python chatgpt_bridge.py send -m "Hello"

# Send with file attachment
python chatgpt_bridge.py send -m "Review this" -f test_upload.md

# Headless mode
python chatgpt_bridge.py send -m "Hello" --headless

# Register as MCP server
claude mcp add chatgpt-bridge -- python mcp_server.py
```

No automated test suite exists — testing is manual via the CLI commands above.

## Architecture

Three-layer design, all async:

1. **`mcp_server.py`** — FastMCP server (stdio transport). Forces UTF-8 on Windows before any I/O (stdout/stderr reconfigure + PYTHONUTF8 env var). Runs pre-flight validation on startup (playwright, pyperclip, Chrome). Self-healing features: auto-restart on dead browser, auto-dismiss error dialogs, auto-visible-login when session expires. Exposes 6 MCP tools: `chatgpt_send`, `chatgpt_status`, `chatgpt_diagnose`, `chatgpt_reset`, `chatgpt_screenshot`, `chatgpt_health`.

2. **`chatgpt_bridge.py`** — Click CLI entrypoint + core message logic. Two CLI commands: `login` and `send`. The `send_message()` function is reused by the MCP server. Owns the message-sending flow: file upload → type message → press Enter → wait for response → copy via clipboard. Includes overall timeout guard (360s).

3. **`browser.py`** (`ChatGPTBrowser` class) — Playwright lifecycle. Launches system Chrome (`channel="chrome"`) with a persistent profile in `~/.chatgpt-bridge/user_data/`. Handles navigation retries (3 attempts with full browser restart), cookie consent, login detection, error detection/dismissal, mode switching (headless/visible), and `playwright-stealth` for anti-automation bypass.

4. **`chatgpt_selectors.py`** — Central CSS selector registry. Each UI element has multiple fallback selectors (German + English variants). Includes error/recovery selectors (Cloudflare, session expired, error dialogs). The `find_element(page, key)` helper tries all candidates via CSS comma-join. **When ChatGPT changes its frontend, update selectors here.**

### Message Input Strategy

Messages are entered via clipboard paste (not character-by-character typing):
1. Focus the textarea (`#prompt-textarea`)
2. Select all existing content (`Ctrl+A`) and delete (`Backspace`) — prevents leftover text
3. Copy message to OS clipboard (`pyperclip.copy`) and paste (`Ctrl+V`) — instant, no race condition
4. **Verify**: Read textarea content back via `inner_text()` and compare with expected message
5. Retry up to 3 times on verification failure, then raise `RuntimeError`
6. Only after verification passes: press `Enter` to send

### Response Extraction Strategy

The copy-button approach extracts markdown (not plain text):
1. Wait for `[data-message-author-role="assistant"]` to appear
2. Poll until the stop button disappears (generation complete, up to 40 min timeout)
3. Hover the last `article[data-testid^="conversation-turn"]` to reveal action buttons
4. Click the copy button (`force=True`) → markdown lands in OS clipboard
5. Read clipboard via `pyperclip.paste()`
6. Fallback chain: JS clipboard API → DOM `inner_text()` scrape

### Session Persistence

`~/.chatgpt-bridge/user_data/` stores the Chrome profile (cookies, localStorage). After one manual `login`, subsequent calls reuse the session. Stale lock files (`SingletonLock` etc.) are auto-cleaned on startup. The path is configurable via `CHATGPT_BRIDGE_DATA` env var.

## Key Conventions

- **Language**: UI selectors include German variants (`"Kopieren"`, `"Anmelden"`, `"Neuer Chat"`) — the ChatGPT account uses German locale.
- **Selectors**: Always add new selectors to `chatgpt_selectors.py`, never hardcode in bridge/browser code. Include English fallback variants.
- **Anti-detection**: `playwright-stealth` handles stealth; do not add `--disable-blink-features=AutomationControlled` to Chrome args (causes a visible warning).
- **Enter key over button click**: Messages are sent via `keyboard.press("Enter")`, not by clicking the send button — more reliable especially with file attachments.
- **Clipboard paste over typing**: Messages are entered via `Ctrl+V` paste, never via `keyboard.type()` or `fill()` — instant, no race condition with Enter key, no leftover text issues.
- **Timeouts**: Response timeout is 40 min (`RESPONSE_TIMEOUT_MS`), overall send timeout ~41.7 min (`SEND_TIMEOUT_S`), MCP gateway timeout 45 min (`.claude.json` / `.mcp.json`).

## Encoding

Windows Python defaults to CP1252/CP437 for stdio, but MCP stdio transport expects UTF-8. This is handled at three levels:
1. **`mcp_server.py`** reconfigures `sys.stdout`/`sys.stderr` to UTF-8 before any I/O
2. **MCP config** (`.claude.json`, `.mcp.json`) sets `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` as env vars
3. **Skill** (`SKILL.md`) checks responses for encoding artifacts (garbled umlauts) in Phase 5

## Known Issues

See `CONTEXT.md` for detailed bug descriptions and fix guidance. Key issues:
- Navigation to chatgpt.com fails ~50% of the time (workaround: 3 retries with browser restart)
