# ChatGPT Bridge — Claude Code Plugin

MCP server that lets Claude Code interact with ChatGPT via Playwright browser automation. Send messages to ChatGPT and get markdown responses back — directly from Claude Code.

## Prerequisites

- Python 3.10+
- Google Chrome installed

## Installation

### 1. Install Python dependencies

```bash
pip install playwright playwright-stealth click pyperclip mcp
playwright install chrome
```

### 2. Install the plugin

```bash
# Add the marketplace
claude plugin marketplace add saltenhof/claude-chatgpt-plugin

# Install the plugin (user scope = available in all projects)
claude plugin install chatgpt-bridge
```

### 3. One-time ChatGPT login

The plugin runs Chrome headless — but the first login needs a visible browser window for Google SSO. Clone the repo and run:

```bash
git clone https://github.com/saltenhof/claude-chatgpt-plugin.git
cd claude-chatgpt-plugin
python chatgpt_bridge.py login
```

This opens Chrome, you log in manually, and the session is persisted to `~/.chatgpt-bridge/user_data/`. After that, the plugin works headless without further interaction.

### 4. Restart Claude Code

The MCP server starts automatically when Claude Code launches. After installing the plugin, restart Claude Code (or start a new session) for the tools to appear.

## MCP Tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `chatgpt_send` | `message` (required), `file_path` (optional), `new_chat` (optional, default `true`) | Send a message to ChatGPT, get markdown response |
| `chatgpt_status` | — | Check browser and login status |

### Conversation continuation

By default, every `chatgpt_send` call navigates to chatgpt.com and starts a **fresh chat**. To continue in the current conversation instead, pass `new_chat: false`:

```
# First message — starts a new chat (default)
chatgpt_send(message="Explain Python decorators")

# Follow-up — stays in the same conversation
chatgpt_send(message="Now show me a caching example", new_chat=false)
```

On the very first call (browser not yet navigated), `new_chat: false` still navigates once to establish the session.

## Design Decisions

### Browser profile in home directory

The Chrome profile (cookies, localStorage, login session) is stored at `~/.chatgpt-bridge/user_data/` — **not** inside the plugin directory. This is intentional:

- The plugin cache (`~/.claude/plugins/...`) is ephemeral and gets replaced on plugin updates
- The login session must survive plugin updates, otherwise you'd have to re-login every time
- The path is configurable via the `CHATGPT_BRIDGE_DATA` environment variable

### Lazy browser initialization

The browser is **not** started when the MCP server launches. It starts on the first `chatgpt_send` call and then stays alive for subsequent calls. This means:

- No Chrome process running when you're not using the tool
- First call is slower (~5-10s for browser startup + navigation)
- Subsequent calls are fast (browser already on chatgpt.com)

### Login stays CLI-only

Login requires a visible browser window for Google SSO interaction. This doesn't fit the MCP model (headless, no UI), so login remains a separate CLI command. The MCP server checks login status on every call and returns a clear error if not logged in.

### Response extraction via clipboard

ChatGPT responses are extracted by clicking the "copy" button on the last assistant message, which copies **markdown** to the clipboard. This preserves formatting (code blocks, lists, headers) that would be lost with a plain DOM scrape. Fallback chain: clipboard → JS clipboard API → DOM inner_text().

## Architecture

```
mcp_server.py              FastMCP server (stdio transport)
  ├── _get_browser()       Lazy-init, cached global ChatGPTBrowser instance
  ├── chatgpt_send()       MCP tool → calls send_message()
  └── chatgpt_status()     MCP tool → checks browser state
      │
      ├── chatgpt_bridge.py    Core logic: send_message(), file upload, response extraction
      ├── browser.py           Playwright lifecycle, navigation retries, stealth
      └── chatgpt_selectors.py CSS selector registry (German + English variants)
```

## CLI Usage (for login and debugging)

```bash
# Manual login (opens visible browser window)
python chatgpt_bridge.py login

# Send a message via CLI (useful for debugging)
python chatgpt_bridge.py send -m "Hello"

# Send with file attachment
python chatgpt_bridge.py send -m "Review this" -f document.md

# Headless mode
python chatgpt_bridge.py send -m "Hello" --headless
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CHATGPT_BRIDGE_DATA` | `~/.chatgpt-bridge` | Base directory for browser profile and data |

## Alternative: Manual MCP registration (without plugin)

If you prefer not to use the plugin system:

```bash
claude mcp add --transport stdio --scope user chatgpt-bridge -- python /path/to/mcp_server.py
```

Set `PYTHONPATH` to the directory containing the Python files if they're not in the current working directory.
