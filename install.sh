#!/usr/bin/env bash
# ===========================================================================
# ChatGPT Bridge for Claude Code — Automated Installer
#
# Usage:  bash install.sh
#
# What it does (idempotent — safe to re-run):
#   1. Install Python dependencies (pip)
#   2. Install Playwright Chrome browser
#   3. Register MCP server with Claude Code (scope: user)
#   4. Install /chatgpt-review skill (symlink or copy)
#   5. Verify registration
#
# What it does NOT do (manual steps):
#   - ChatGPT login (requires browser interaction)
#   - Restart Claude Code (must be done by user)
# ===========================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
step()  { echo -e "\n${GREEN}==> $1${NC}"; }

# Resolve absolute path to this script's directory
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Plugin directory: $PLUGIN_DIR"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
step "Pre-flight checks"

command -v python >/dev/null 2>&1 || fail "Python nicht gefunden. Bitte Python >= 3.10 installieren."
PYTHON_VERSION=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python $PYTHON_VERSION gefunden"

command -v pip >/dev/null 2>&1 || fail "pip nicht gefunden. Bitte pip installieren."
info "pip gefunden"

# Check Claude Code CLI (may not be available if running inside Claude Code)
if command -v claude >/dev/null 2>&1; then
    info "Claude Code CLI gefunden"
else
    warn "Claude Code CLI nicht im PATH. MCP-Registrierung muss manuell erfolgen."
fi

# Check Chrome
CHROME_FOUND=false
for chrome_path in \
    "/c/Program Files/Google/Chrome/Application/chrome.exe" \
    "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
    "/usr/bin/google-chrome" \
    "/usr/bin/google-chrome-stable" \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
    if [ -f "$chrome_path" ]; then
        CHROME_FOUND=true
        info "Chrome gefunden: $chrome_path"
        break
    fi
done
if [ "$CHROME_FOUND" = false ]; then
    warn "Chrome nicht in Standard-Pfaden gefunden. Installation fortsetzen — Playwright bringt ggf. eigenes Chrome mit."
fi

# ---------------------------------------------------------------------------
# Step 1: Python dependencies
# ---------------------------------------------------------------------------
step "Schritt 1: Python-Abhaengigkeiten installieren"

pip install -r "$PLUGIN_DIR/requirements.txt" 2>&1 | tail -5
info "Python-Abhaengigkeiten installiert"

# ---------------------------------------------------------------------------
# Step 2: Playwright Chrome
# ---------------------------------------------------------------------------
step "Schritt 2: Playwright Chrome installieren"

python -m playwright install chrome 2>&1 | tail -3
info "Playwright Chrome installiert"

# ---------------------------------------------------------------------------
# Step 3: Register MCP server
# ---------------------------------------------------------------------------
step "Schritt 3: MCP-Server registrieren"

# Convert plugin dir to format suitable for the current environment
MCP_SCRIPT="$PLUGIN_DIR/mcp_server.py"

# Remove existing registration (ignore errors if not registered)
if command -v claude >/dev/null 2>&1; then
    # Unset CLAUDECODE to avoid nested-session error if running from inside Claude Code
    CLAUDECODE= claude mcp remove chatgpt-bridge 2>/dev/null || true

    CLAUDECODE= claude mcp add chatgpt-bridge \
        --transport stdio \
        --scope user \
        -e PYTHONPATH="$PLUGIN_DIR" \
        -e PYTHONUTF8=1 \
        -e PYTHONIOENCODING=utf-8 \
        -- python "$MCP_SCRIPT"

    info "MCP-Server 'chatgpt-bridge' registriert (scope: user)"
else
    warn "Claude CLI nicht verfuegbar. Bitte manuell registrieren:"
    echo "  claude mcp add chatgpt-bridge --transport stdio --scope user \\"
    echo "    -e PYTHONPATH=\"$PLUGIN_DIR\" \\"
    echo "    -e PYTHONUTF8=1 \\"
    echo "    -e PYTHONIOENCODING=utf-8 \\"
    echo "    -- python \"$MCP_SCRIPT\""
fi

# ---------------------------------------------------------------------------
# Step 4: Install skill
# ---------------------------------------------------------------------------
step "Schritt 4: Skill /chatgpt-review installieren"

SKILL_SOURCE="$PLUGIN_DIR/skill"
SKILL_TARGET="$HOME/.claude/skills/chatgpt-review"

mkdir -p "$HOME/.claude/skills"

if [ -d "$SKILL_TARGET" ] || [ -L "$SKILL_TARGET" ]; then
    info "Skill-Verzeichnis existiert bereits: $SKILL_TARGET"
elif [ "$(uname -o 2>/dev/null)" = "Msys" ] || [ "$(uname -o 2>/dev/null)" = "Cygwin" ]; then
    # Windows: try junction via cmd
    WIN_TARGET="$(cygpath -w "$SKILL_TARGET")"
    WIN_SOURCE="$(cygpath -w "$SKILL_SOURCE")"
    if cmd //c "mklink /J \"$WIN_TARGET\" \"$WIN_SOURCE\"" 2>/dev/null; then
        info "Skill als Windows Junction verlinkt"
    else
        warn "Junction fehlgeschlagen (Developer Mode noetig?). Kopiere stattdessen..."
        mkdir -p "$SKILL_TARGET"
        cp "$SKILL_SOURCE/SKILL.md" "$SKILL_TARGET/SKILL.md"
        info "Skill-Datei kopiert (kein Symlink)"
    fi
else
    # Linux/macOS: symbolic link
    ln -sf "$SKILL_SOURCE" "$SKILL_TARGET"
    info "Skill als Symlink verlinkt"
fi

# Verify skill
if [ -f "$SKILL_TARGET/SKILL.md" ]; then
    info "Skill verifiziert: $SKILL_TARGET/SKILL.md"
else
    warn "Skill-Datei nicht gefunden. Bitte manuell pruefen."
fi

# ---------------------------------------------------------------------------
# Step 5: Verify
# ---------------------------------------------------------------------------
step "Schritt 5: Registrierung pruefen"

if command -v claude >/dev/null 2>&1; then
    echo ""
    CLAUDECODE= claude mcp list 2>&1 || true
    echo ""
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "==========================================================================="
echo -e "${GREEN}Installation abgeschlossen!${NC}"
echo "==========================================================================="
echo ""
echo "Noch 2 manuelle Schritte:"
echo ""
echo -e "  ${YELLOW}1. ChatGPT-Login (einmalig):${NC}"
echo "     cd \"$PLUGIN_DIR\""
echo "     python chatgpt_bridge.py login"
echo ""
echo -e "  ${YELLOW}2. Claude Code neu starten${NC}"
echo "     MCP-Tools werden erst nach Neustart verfuegbar."
echo ""
echo "Danach testen mit:"
echo "  /chatgpt-review Was ist 2+2?"
echo ""
echo "==========================================================================="
