# ChatGPT Bridge — Claude Code Plugin

MCP server that lets Claude Code interact with ChatGPT via Playwright browser automation. Send messages to ChatGPT and get markdown responses back — directly from Claude Code.

## Prerequisites

- Python 3.10+
- Google Chrome installed
- pip dependencies (see below)

## Installation

### 1. Install Python dependencies

```bash
pip install playwright playwright-stealth click pyperclip mcp
playwright install chrome
```

### 2. One-time ChatGPT login

The plugin uses a persistent Chrome profile stored in `~/.chatgpt-bridge/user_data/`. You need to log in once:

```bash
# Clone the repo (or use the plugin's install location)
python chatgpt_bridge.py login
```

This opens a browser window. Log in to ChatGPT via Google SSO. The session is saved automatically.

### 3. Install the plugin

```bash
claude plugin install chatgpt-bridge@saltenhof/claude-chatgpt-plugin
```

Or add manually:

```bash
claude mcp add --transport stdio --scope user chatgpt-bridge -- python /path/to/mcp_server.py
```

## MCP Tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `chatgpt_send` | `message` (required), `file_path` (optional) | Send a message to ChatGPT, get markdown response |
| `chatgpt_status` | — | Check browser and login status |

## CLI Usage (for login and debugging)

```bash
# Manual login (opens browser window)
python chatgpt_bridge.py login

# Send a message via CLI
python chatgpt_bridge.py send -m "Hello"

# Send with file attachment
python chatgpt_bridge.py send -m "Review this" -f document.md
```

## Configuration

The browser profile is stored at `~/.chatgpt-bridge/user_data/` by default. Override with the `CHATGPT_BRIDGE_DATA` environment variable:

```bash
export CHATGPT_BRIDGE_DATA=/custom/path
```

## Architecture

```
mcp_server.py          FastMCP server (stdio transport)
  ├── chatgpt_bridge.py  Core message logic (send_message)
  ├── browser.py         Playwright browser lifecycle
  └── chatgpt_selectors.py  CSS selector registry
```

The browser session is lazy-initialized on the first tool call and persists across subsequent calls.
