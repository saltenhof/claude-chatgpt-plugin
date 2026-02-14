# ChatGPT Browser Bridge — Projekt-Kontext

## Projekt-Ziel
MCP Server + CLI-Tool (Python + Playwright) das Claude Code ermöglicht, mit ChatGPT über das Web-Interface zu interagieren.

## Dateien
- `mcp_server.py` — FastMCP Server mit Self-Healing (auto-restart, auto-login, error-dismiss)
- `chatgpt_bridge.py` — CLI-Entrypoint (click) + Core Message Logic, Kommandos: `login`, `send`
- `browser.py` — Playwright Browser-Management, persistentes Chrome-Profil
- `chatgpt_selectors.py` — Zentrale CSS-Selektoren für ChatGPT-UI (inkl. Error/Recovery)
- `diagnose.py` — Diagnose-Script für manuelles Debugging
- `requirements.txt` — playwright, click, pyperclip, playwright-stealth, mcp
- `.claude-plugin/` — Plugin-Manifest für Claude Code Marketplace

## Was funktioniert
- **Login**: Google SSO + Workspace-Auswahl (QAware Team Account)
- **Session-Persistenz**: Chrome-Profil in `~/.chatgpt-bridge/user_data/` überlebt Neustarts
- **Cookie-Consent**: Automatisch weggeklickt
- **Nachricht senden**: Text eingeben + Enter-Taste
- **Antwort empfangen**: Über Copy-Button des letzten Assistant-Turns (Markdown!)
- **Retry-Logik**: 30s Timeout pro Versuch, bis zu 3 Versuche mit Browser-Neustart
- **Stealth**: `playwright-stealth` Paket gegen Anti-Automation-Erkennung
- **Lock-File Cleanup**: Automatische Bereinigung von SingletonLock etc.
- **Self-Healing MCP**: Auto-restart bei totem Browser, Auto-dismiss von Error-Dialogen
- **Auto-Login**: Wechsel zu sichtbarem Browser wenn Session abläuft
- **Gesamt-Timeout**: 360s Guard um send_message() verhindert Endlos-Blockierung
- **Diagnostics**: Screenshot, Status, Reset als MCP-Tools

## Bekannte Bugs — NOCH ZU FIXEN

### 1. Navigation flaky (~50% Fehlerrate)
**Problem**: `page.goto("https://chatgpt.com")` schlägt bei ca. jedem zweiten Start fehl (Timeout oder `net::ERR_ABORTED`). Retry-Mechanik mit Browser-Neustart ist eingebaut und hilft.
**Status**: Workaround funktioniert (3 Retries), Grundursache unklar. Möglicherweise Cloudflare oder Chrome-Profil-Locking.

## Gelöste Bugs

### Encoding-Probleme mit Umlauten (gelöst 2026-02-14)
**Problem**: ChatGPT-Antworten mit Umlauten (ä, ö, ü, ß) kamen verstümmelt an, weil Python auf Windows standardmäßig CP1252 für stdio nutzt, während JSON-RPC (MCP) UTF-8 erwartet.
**Lösung**: Dreistufiger Fix:
1. `mcp_server.py` rekonfiguriert `sys.stdout`/`sys.stderr` auf UTF-8 vor jedem I/O
2. MCP-Config setzt `PYTHONUTF8=1` und `PYTHONIOENCODING=utf-8` als Umgebungsvariablen
3. Skill prüft Antworten auf Encoding-Artefakte (Phase 5)

## Neue Features (2026-02-14)

### Health-Check Tool
- `chatgpt_health()` — leichtgewichtiger Lebendigkeitstest, keine Browser-Interaktion
- Wird vom Skill in Phase 0 als Pre-Flight-Check genutzt

### Startup-Validierung
- `_validate_environment()` — prüft playwright, pyperclip, Chrome beim Server-Start
- Loggt `PRE-FLIGHT OK` oder `PRE-FLIGHT FAIL` auf stderr
- Server startet trotz Fehlern (Tools schlagen dann graceful fehl)

## Noch nicht implementiert
- **Deep Research**: ChatGPT Deep Research anstoßen (langer async Workflow mit Polling)
- **Model/Modus wechseln**: Dropdown "ChatGPT 5.2 Thinking" umschalten, "Längerer Denkvorgang" → "Standard" etc.

## Technische Details

### Browser-Setup
- `channel="chrome"` — nutzt installierten Chrome (x86), nicht Playwright Chromium
- Chrome-Pfad: `C:/Program Files (x86)/Google/Chrome/Application/chrome.exe`
- `playwright-stealth` v2.0: `Stealth().apply_stealth_async(page)` — entfernt `navigator.webdriver` etc.
- `ignore_default_args=["--enable-automation", "--no-sandbox"]`
- Persistentes Profil via `launch_persistent_context(user_data_dir=...)`

### ChatGPT-UI Selektoren (deutsch!)
- Prompt: `#prompt-textarea`
- Send: `button[data-testid="send-button"]`  (aber wir nutzen Enter-Taste statt Button)
- Stop: `button[data-testid="stop-button"]`
- Copy: `button[data-testid="copy-turn-action-button"]` (aria-label="Kopieren")
- Conversation Turn: `article[data-testid^="conversation-turn"]`
- Assistant Message: `[data-message-author-role="assistant"]`
- Login-Check: Abwesenheit von `button:has-text("Anmelden")` + Präsenz von `a:has-text("Neuer Chat")`

### Antwort-Extraktion (Copy-Button-Strategie)
1. Warte auf `[data-message-author-role="assistant"]` (Antwort erscheint)
2. Warte bis Stop-Button verschwindet (Generation fertig)
3. Finde letzten `article[data-testid^="conversation-turn"]` (= Assistant-Turn)
4. Hover über den Turn → Action-Buttons erscheinen
5. Klicke Copy-Button (`force=True`) → Markdown im Clipboard
6. Lese OS-Clipboard via `pyperclip.paste()`
7. Fallback: `inner_text()` aus DOM

### ChatGPT Account
- Team Account: "QAware" Workspace
- User: Stefan Altenhof
- Google SSO Login
- Aktuelles Modell im Screenshot: ChatGPT 5.2 Thinking, "Längerer Denkvorgang"

### Navigation-Retry
```
30s Timeout pro Versuch
3 Versuche max
Bei Fehlschlag: context.close() → 2s Pause → _launch_context() → erneut goto
Lock-Files (SingletonLock etc.) werden automatisch bereinigt
```
