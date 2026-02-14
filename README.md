# ChatGPT Bridge for Claude Code

MCP-Server + Skill, der Claude Code mit ChatGPT verbindet. Playwright-basierte
Browser-Automation mit persistentem Chrome-Profil. Kein API-Key noetig.

**Zielbild:** Diesen Ordner auf einen neuen Rechner kopieren, Claude Code sagen
"lies die README und installiere alles" — fertig.

---

## Voraussetzungen

| Was                  | Version  | Pruefung                     |
|----------------------|----------|------------------------------|
| Python               | >= 3.10  | `python --version`           |
| pip                  | aktuell  | `pip --version`              |
| Google Chrome        | aktuell  | Muss installiert sein (x86 oder x64, Program Files) |
| Claude Code CLI      | aktuell  | `claude --version`           |
| Git Bash (Windows)   | —        | Standard-Shell in Claude Code |

---

## Installation

### Automatisch (empfohlen)

```bash
# Aus dem Projektverzeichnis heraus:
bash install.sh
```

Das Script fuehrt alle Schritte 1-5 automatisch aus. Danach nur noch
Schritt 6 (Login) und 7 (Restart) manuell.

### Manuell (Schritt fuer Schritt)

#### Schritt 1: Python-Abhaengigkeiten installieren

```bash
pip install -r requirements.txt
```

Dependencies: `playwright`, `playwright-stealth`, `click`, `pyperclip`, `mcp`

#### Schritt 2: Playwright Chrome installieren

```bash
python -m playwright install chrome
```

Dies installiert die Playwright-kompatible Chrome-Version. Der MCP-Server
nutzt den lokal installierten System-Chrome (`channel="chrome"`), aber
Playwright muss trotzdem initialisiert werden.

#### Schritt 3: MCP-Server registrieren

```bash
# PLUGIN_DIR = absoluter Pfad zu diesem Verzeichnis
PLUGIN_DIR="$(cd "$(dirname "$0")" && pwd)"

claude mcp add chatgpt-bridge \
  --transport stdio \
  --scope user \
  -e PYTHONPATH="$PLUGIN_DIR" \
  -e PYTHONUTF8=1 \
  -e PYTHONIOENCODING=utf-8 \
  -- python "$PLUGIN_DIR/mcp_server.py"
```

**Scope `user`** = der MCP-Server steht in allen Projekten zur Verfuegung.
Alternativ `--scope project` fuer nur das aktuelle Projekt.

**Wichtig:** Die Env-Vars `PYTHONUTF8=1` und `PYTHONIOENCODING=utf-8` sind
auf Windows zwingend, damit Umlaute in ChatGPT-Antworten korrekt ueber das
JSON-RPC (stdio) transportiert werden.

#### Schritt 4: Skill installieren (Symlink)

Der Skill `/chatgpt-review` muss in `~/.claude/skills/` verlinkt werden:

**Windows (Git Bash mit Admin oder Developer Mode):**
```bash
SKILL_TARGET="$HOME/.claude/skills/chatgpt-review"
mkdir -p "$HOME/.claude/skills"
# Symlink erstellen (Windows Junction)
cmd //c "mklink /J \"$(cygpath -w "$SKILL_TARGET")\" \"$(cygpath -w "$PLUGIN_DIR/skill")\""
```

**Linux/macOS:**
```bash
mkdir -p ~/.claude/skills
ln -sf "$(pwd)/skill" ~/.claude/skills/chatgpt-review
```

Pruefung: `ls ~/.claude/skills/chatgpt-review/SKILL.md` muss die Datei zeigen.

#### Schritt 5: Registrierung pruefen

```bash
claude mcp list
```

Erwartete Ausgabe:
```
chatgpt-bridge: python /pfad/zu/mcp_server.py - ✓ Connected
```

Falls "not connected": Env-Vars und Pfad pruefen. Haeufigster Fehler:
Python findet die Module nicht (PYTHONPATH fehlt).

#### Schritt 6: Einmaliger ChatGPT-Login (manuell!)

```bash
python chatgpt_bridge.py login
```

Dies oeffnet ein Chrome-Fenster. Dort manuell einloggen:
1. "Anmelden" klicken
2. Google SSO durchlaufen
3. Ggf. Workspace auswaehlen (z.B. "QAware")
4. Warten bis "Login erfolgreich erkannt" erscheint

Die Session wird in `~/.chatgpt-bridge/user_data/` gespeichert und ueberlebt
Neustarts. Muss nur wiederholt werden wenn die Session ablaeuft (selten).

#### Schritt 7: Claude Code neu starten

MCP-Server werden beim Start von Claude Code geladen. Nach der Registrierung
muss Claude Code einmal neu gestartet werden:

```bash
# Claude Code beenden (Ctrl+C oder /exit) und neu starten
claude
```

---

## Verifizierung

Nach dem Neustart von Claude Code:

1. **MCP-Tools pruefen:** Im Chat eingeben:
   ```
   Rufe chatgpt_health auf
   ```
   Erwartete Antwort: `ok`

2. **Skill pruefen:** Im Chat eingeben:
   ```
   /chatgpt-review Was ist 2+2?
   ```
   Erwartete Antwort: ChatGPT antwortet mit "4" (o.ae.)

---

## Nutzung

### Per Skill (empfohlen)

```
/chatgpt-review Erklaere mir Transformer-Architektur
/chatgpt-review --file /pfad/zu/datei.md Reviewe dieses Konzept
```

### Per MCP-Tool direkt

```
Frage ChatGPT: Was ist der Taco Trade?
```

Claude Code erkennt den Kontext und nutzt `chatgpt_send` automatisch, wenn
der Skill geladen ist.

---

## MCP-Tools Referenz

| Tool                  | Parameter                                | Beschreibung |
|-----------------------|------------------------------------------|-------------|
| `chatgpt_send`        | `message` (Pflicht), `file_path`, `new_chat` | Nachricht an ChatGPT senden, Markdown-Antwort erhalten |
| `chatgpt_status`      | —                                        | Browser- und Login-Status |
| `chatgpt_health`      | —                                        | Schneller Lebendigkeitstest (kein Browser) |
| `chatgpt_diagnose`    | —                                        | Detaillierte Diagnostik mit Screenshot |
| `chatgpt_reset`       | —                                        | Browser killen, Zustand zuruecksetzen |
| `chatgpt_screenshot`  | —                                        | Screenshot der aktuellen Seite |

### Conversation Continuation

Standardmaessig startet jeder `chatgpt_send`-Aufruf einen neuen Chat.
Fuer Follow-ups im selben Chat: `new_chat: false`.

---

## Dateistruktur

```
claude-chatgpt-plugin/
  mcp_server.py            # MCP-Server (6 Tools, Self-Healing, UTF-8)
  chatgpt_bridge.py        # Core-Logik: send_message(), CLI (login/send)
  browser.py               # Playwright-Lifecycle, Navigation, Stealth
  chatgpt_selectors.py     # CSS-Selektoren fuer ChatGPT-UI
  diagnose.py              # Manuelles Debug-Script
  requirements.txt         # Python-Abhaengigkeiten
  install.sh               # Automatisches Install-Script
  .mcp.json                # MCP-Config (fuer Plugin-System)
  .gitignore
  skill/
    SKILL.md               # Skill-Definition fuer /chatgpt-review
  .claude-plugin/
    plugin.json             # Plugin-Manifest
    marketplace.json        # Marketplace-Deskriptor
  CLAUDE.md                 # Entwickler-Kontext fuer Claude Code
  CONTEXT.md                # Bekannte Bugs, Features, Tech-Details
  README.md                 # <-- diese Datei
```

---

## Architektur

```
Claude Code
  |
  |  stdio (JSON-RPC)
  v
mcp_server.py                FastMCP Server
  |-- _validate_environment()   Pre-Flight: playwright, pyperclip, Chrome
  |-- _ensure_ready()           Self-Healing: Liveness, Error-Dismiss, Auto-Login
  |-- chatgpt_send()            Haupttool
  |-- chatgpt_health()          Lebendigkeitstest
  |-- chatgpt_status()          Status
  |-- chatgpt_diagnose()        Diagnostik
  |-- chatgpt_reset()           Neustart
  |-- chatgpt_screenshot()      Screenshot
  |
  v
chatgpt_bridge.py            Core Message Logic
  |-- send_message()            Upload, Typing, Enter, Response-Extraktion
  |-- CLI: login, send          Manueller Zugang
  |
  v
browser.py                   Playwright Browser Management
  |-- ChatGPTBrowser            Persistentes Chrome-Profil
  |-- navigate_to_chat()        3 Retries mit Browser-Restart
  |-- detect_and_dismiss_errors()  Cloudflare, Session, Error-Dialoge
  |-- switch_mode()             Headless <-> Sichtbar
  |
  v
chatgpt_selectors.py        CSS-Selektoren
  |-- Deutsche + Englische Varianten
  |-- Error/Recovery-Selektoren
  |-- find_element() Helper
```

### Session-Persistenz

Das Chrome-Profil (Cookies, localStorage) liegt in `~/.chatgpt-bridge/user_data/`.
Dieser Pfad ist bewusst NICHT im Plugin-Verzeichnis, weil:
- Plugin-Cache ist ephemer (wird bei Updates ueberschrieben)
- Login-Session muss Updates ueberleben
- Konfigurierbar via `CHATGPT_BRIDGE_DATA` Env-Var

### Response-Extraktion

Antworten werden per Copy-Button extrahiert (Markdown, nicht Plaintext):
1. Warte auf `[data-message-author-role="assistant"]`
2. Warte bis Stop-Button verschwindet (Generation fertig)
3. Hover ueber letzten Conversation-Turn (Action-Buttons erscheinen)
4. Klicke Copy-Button → Markdown im OS-Clipboard
5. Lese Clipboard via `pyperclip.paste()`
6. Fallback: JS Clipboard API → DOM `inner_text()`

---

## Konfiguration

| Env-Var                  | Default                    | Beschreibung |
|--------------------------|----------------------------|-------------|
| `CHATGPT_BRIDGE_DATA`   | `~/.chatgpt-bridge`       | Basisverzeichnis fuer Browser-Profil |
| `PYTHONUTF8`            | `1` (via MCP-Config)       | Python UTF-8 Mode (Windows) |
| `PYTHONIOENCODING`       | `utf-8` (via MCP-Config)   | Python IO Encoding (Windows) |

---

## Troubleshooting

### Problem: MCP-Tools nicht verfuegbar nach Installation

**Ursache:** MCP-Server werden beim Start geladen. Registrierung waehrend
einer laufenden Session wird erst nach Neustart wirksam.

**Loesung:** Claude Code neu starten.

### Problem: "chatgpt_health Tool nicht gefunden"

**Ursache:** MCP-Server nicht registriert.

**Loesung:**
```bash
claude mcp list
```
Falls `chatgpt-bridge` nicht aufgelistet: Schritt 3 wiederholen.

### Problem: "PRE-FLIGHT FAIL" in Logs

**Ursache:** Fehlende Python-Pakete oder Chrome nicht installiert.

**Loesung:**
```bash
pip install -r requirements.txt
python -m playwright install chrome
```

### Problem: "Nicht eingeloggt"

**Ursache:** Session abgelaufen oder noch nie eingeloggt.

**Loesung:**
```bash
python chatgpt_bridge.py login
```

Der MCP-Server versucht auch Auto-Login (oeffnet sichtbaren Browser
automatisch). Falls das fehlschlaegt: manuell ueber CLI.

### Problem: Umlaute kaputt (Ã¤ statt ae)

**Ursache:** Python nutzt auf Windows CP1252 statt UTF-8.

**Loesung:** Pruefen ob die Env-Vars gesetzt sind:
```bash
claude mcp list  # Sollte die env vars zeigen
```
Falls nicht: MCP-Server deregistrieren und mit Env-Vars neu registrieren
(Schritt 3). Dann Claude Code neu starten.

### Problem: Navigation schlaegt fehl (~50% Fehlerrate)

**Ursache:** Bekanntes Problem. Cloudflare-Challenge oder Chrome-Profil-
Locking beim ersten goto().

**Workaround:** Bereits eingebaut (3 Retries mit Browser-Neustart).
Normalerweise klappt es beim 2. oder 3. Versuch. Falls dauerhaft:
```bash
# Browser-Profil loeschen und neu einloggen
rm -rf ~/.chatgpt-bridge/user_data/
python chatgpt_bridge.py login
```

### Problem: chatgpt_send haengt (Timeout nach 90s)

**Moegliche Ursachen:**
1. Chrome "Restore Session?" Dialog blockiert Automation
2. Zwei Tabs offen, ChatGPT im Hintergrund-Tab
3. Cloudflare-Challenge oder Wartungsseite

**Diagnose:**
```bash
# Screenshot machen
# In Claude Code: chatgpt_screenshot aufrufen
# Oder manuell:
python diagnose.py
```

**Loesung je nach Ursache:**
- Dialog/Tabs: `chatgpt_reset` aufrufen (raeumen Lock-Files und Tabs)
- Cloudflare: Spaeter erneut versuchen
- Wartung: Abwarten

### Problem: Symlink fuer Skill schlaegt fehl (Windows)

**Ursache:** Windows braucht Admin-Rechte oder Developer Mode fuer Symlinks.

**Loesung A:** Developer Mode aktivieren:
Settings → Update & Security → For Developers → Developer Mode ON

**Loesung B:** Skill-Datei direkt kopieren (statt Symlink):
```bash
mkdir -p ~/.claude/skills/chatgpt-review
cp skill/SKILL.md ~/.claude/skills/chatgpt-review/SKILL.md
```
Nachteil: Bei Updates muss manuell nachkopiert werden.

### Problem: Module nicht gefunden ("ModuleNotFoundError: No module named 'browser'")

**Ursache:** PYTHONPATH zeigt nicht auf das Plugin-Verzeichnis.

**Loesung:** MCP-Server deregistrieren und mit korrektem PYTHONPATH registrieren:
```bash
claude mcp remove chatgpt-bridge
claude mcp add chatgpt-bridge \
  --transport stdio \
  --scope user \
  -e PYTHONPATH="/absoluter/pfad/zu/claude-chatgpt-plugin" \
  -e PYTHONUTF8=1 \
  -e PYTHONIOENCODING=utf-8 \
  -- python "/absoluter/pfad/zu/claude-chatgpt-plugin/mcp_server.py"
```

### Debug-Workflow: Sichtbarer Browser

Wenn headless nicht funktioniert und die Ursache unklar ist:

1. In `mcp_server.py`, Zeile mit `await _browser.start(headless=...)`:
   `headless=False` setzen
2. Claude Code neu starten
3. `chatgpt_send` aufrufen und Chrome-Fenster beobachten
4. Problem identifizieren
5. Fix anwenden, zurueck auf `headless=True`

---

## Wartung

### MCP-Server aktualisieren (nach Code-Aenderungen)

```bash
# Server deregistrieren und neu registrieren
claude mcp remove chatgpt-bridge
# Schritt 3 von oben wiederholen
# Claude Code neu starten
```

### Session erneuern

```bash
python chatgpt_bridge.py login
```

### Browser-Profil zuruecksetzen

```bash
rm -rf ~/.chatgpt-bridge/user_data/
python chatgpt_bridge.py login
```

### Abhaengigkeiten aktualisieren

```bash
pip install --upgrade -r requirements.txt
python -m playwright install chrome
```
