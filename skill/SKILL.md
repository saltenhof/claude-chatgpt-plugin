---
name: chatgpt-review
description: Sends a prompt (optionally with file content) to ChatGPT via browser-automation MCP and returns the response.
allowed-tools: Read, Bash, chatgpt_send, chatgpt_status, chatgpt_diagnose, chatgpt_reset, chatgpt_screenshot, chatgpt_health
argument-hint: "<prompt> [--file <path>]"
---

# ChatGPT Review — Execution Plan

Du sendest einen Prompt (optional mit Dateiinhalt) an ChatGPT ueber den MCP-Server
`claude-chatgpt-plugin`, der ChatGPT per Playwright-Browser-Automation ansteuert.
Arbeite diesen Plan Schritt fuer Schritt ab. Ueberspringe keine Schritte.

## Kontext

- **MCP-Server**: `claude-chatgpt-plugin` (Playwright-basierte Browser-Automation)
- **Kein API-Key noetig**: Der MCP-Server nutzt ein persistentes Chrome-Profil mit Login-Session
- **Verfuegbare MCP-Tools**:
  - `chatgpt_health()` — Schneller Lebendigkeitstest des MCP-Servers (keine Browser-Interaktion)
  - `chatgpt_send(message, file_path?, new_chat?)` — Sendet Nachricht an ChatGPT, gibt Markdown-Antwort zurueck
  - `chatgpt_status()` — Browser/Login-Status pruefen
  - `chatgpt_diagnose()` — Detaillierte Diagnostics
  - `chatgpt_reset()` — Browser-Reset bei Problemen
  - `chatgpt_screenshot()` — Screenshot des aktuellen Browserzustands

## Argument-Parsing

Argumente: `$ARGUMENTS`

Zerlege `$ARGUMENTS` in:

1. **Prompt** (PFLICHT):
   - Der Text, der an ChatGPT gesendet wird
   - Kann in Anfuehrungszeichen stehen oder als freier Text nach den Flags
   - Beispiel: `"Reviewe dieses Konzept auf Schwaechen"`

2. **`--file <path>`** (optional):
   - Absoluter Pfad zu einer Datei, deren Inhalt zusammen mit dem Prompt gesendet werden soll
   - Beispiel: `--file T:\codebase\project\concept.md`

## Execution Plan

### Phase 0: MCP-Server Verfuegbarkeit pruefen

1. Rufe `chatgpt_health()` auf.
2. **Bei Erfolg** (Antwort "ok"): Weiter zu Phase 1.
3. **Bei Fehler** (Tool nicht gefunden, Timeout, Connection refused):
   - Dem Nutzer mitteilen: **"Der ChatGPT MCP-Server ist nicht erreichbar."**
   - Diagnose-Hinweise ausgeben (siehe Abschnitt "MCP-Server Management" unten).
   - **STOP** — nicht weiter fortfahren.

### Phase 1: Argumente parsen

1. Extrahiere den **Prompt** aus `$ARGUMENTS`.
2. Pruefe ob `--file <path>` angegeben ist. Falls ja, extrahiere den Dateipfad.
3. Validierung:
   - Prompt darf nicht leer sein. Falls leer: Fehlermeldung und STOP.
   - Falls `--file` angegeben: Pruefe ob der Pfad syntaktisch gueltig aussieht.

### Phase 2: Dateiinhalt laden (falls --file angegeben)

1. Lies die angegebene Datei mit dem **Read**-Tool.
2. Falls die Datei nicht existiert oder nicht lesbar ist: Fehlermeldung und STOP.
3. Pruefe die Laenge des Dateiinhalts:
   - **Unter 50.000 Zeichen**: Vollstaendig verwenden.
   - **Ueber 50.000 Zeichen**: Warnung an den Nutzer ausgeben:
     > "Die Datei ist sehr gross (X Zeichen). ChatGPT koennte den Inhalt nicht vollstaendig verarbeiten.
     > Soll ich die ersten 50.000 Zeichen senden oder abbrechen?"
   - Warte auf Nutzer-Entscheidung bevor du fortfaehrst.

### Phase 3: Nachricht zusammenbauen

1. Baue die Nachricht fuer ChatGPT zusammen:
   - **Ohne Datei**: Die Nachricht ist identisch mit dem Prompt.
   - **Mit Datei**: Kombiniere Prompt und Dateiinhalt im folgenden Format:
     ```
     {prompt}

     ---
     Dateiinhalt ({dateiname}):
     ---

     {dateiinhalt}
     ```

### Phase 4: An ChatGPT senden

1. Rufe `chatgpt_send` auf mit:
   - `message`: Die zusammengebaute Nachricht aus Phase 3
   - `new_chat`: `true` (immer einen neuen Chat starten)

2. **Bei Erfolg**: Weiter zu Phase 5.

3. **Bei Fehler**: Fehlerbehandlung ausfuehren (siehe unten).

### Phase 5: Antwort praesentieren

1. Pruefe die Antwort auf Encoding-Artefakte:
   - Suche nach typischen Anzeichen kaputter Umlaute: `Ã¤`, `Ã¶`, `Ã¼`, `ÃŸ`, `Ã„`, `Ã–`, `Ãœ`
   - Falls solche Artefakte gefunden werden: Hinweis an den Nutzer, dass Encoding-Probleme
     vorliegen. Empfehlung: MCP-Server neustarten (Claude Code neustarten oder `chatgpt_reset`).
2. Gib die Antwort von ChatGPT dem Nutzer aus:
   ```
   --- ChatGPT-Antwort ---

   {antwort}

   --- Ende ChatGPT-Antwort ---
   ```

## Fehlerbehandlung

Falls `chatgpt_send` fehlschlaegt, folge dieser dreistufigen Eskalation:

### Stufe 1: Status pruefen
- Rufe `chatgpt_status()` auf.
- Analysiere die Antwort:
  - **Browser: not started** → Normaler Zustand beim ersten Aufruf, `chatgpt_send` erneut versuchen.
  - **Browser: DEAD** → Weiter zu Stufe 3 (Reset).
  - **Logged in: False** → Browser ist ok, aber Session abgelaufen. `chatgpt_send` erneut aufrufen
    (Auto-Login wird automatisch ausgeloest).
  - **Error state** vorhanden → Weiter zu Stufe 2.

### Stufe 2: Diagnose
- Rufe `chatgpt_diagnose()` auf.
- Dem Nutzer die Diagnoseinformationen zeigen.
- Falls Screenshot verfuegbar: Pfad mitteilen.

### Stufe 3: Reset und Retry
- Rufe `chatgpt_reset()` auf.
- Warte 5 Sekunden (Bash: `sleep 5`).
- Versuche `chatgpt_send` erneut (maximal 1 Retry).
- **Bei erneutem Fehler**: Screenshot via `chatgpt_screenshot()` und dem Nutzer die Situation
  erklaeren mit konkreten naechsten Schritten:
  - "Browser-Session abgelaufen → `python chatgpt_bridge.py login` ausfuehren"
  - "ChatGPT-Seite nicht erreichbar → Spaeter erneut versuchen"
  - "MCP-Server nicht gestartet → Claude Code neustarten"

## MCP-Server Management

### Server-Status pruefen
Der schnellste Weg: `chatgpt_health()` aufrufen. Antwort "ok" = Server laeuft.

### Server nicht erreichbar — Ursachen und Loesungen

| Symptom | Wahrscheinliche Ursache | Loesung |
|---------|------------------------|---------|
| `chatgpt_health` Tool nicht gefunden | MCP-Server nicht registriert | Claude Code neustarten; pruefen ob `chatgpt-bridge` in MCP-Config steht |
| `chatgpt_health` Timeout | Python-Prozess haengt | Claude Code neustarten |
| `chatgpt_health` Connection refused | Server-Prozess nicht gestartet | Claude Code neustarten |
| Pre-flight Fehler in stderr | Fehlende Dependency | `pip install -r requirements.txt` und/oder Chrome installieren |

### Encoding-Probleme erkennen
Falls ChatGPT-Antworten verstümmelte Umlaute enthalten (z.B. `Ã¤` statt `ae`):
1. MCP-Server wurde ohne UTF-8-Umgebung gestartet
2. Loesung: Claude Code neustarten (env vars `PYTHONUTF8=1` und `PYTHONIOENCODING=utf-8` werden beim Neustart gesetzt)

## Wichtige Regeln

1. **Kein API-Key**: Dieser Skill nutzt Browser-Automation, keinen OpenAI-API-Zugang.
2. **Keine Python-Skripte**: Alles laeuft ueber die MCP-Tools des `claude-chatgpt-plugin`.
3. **Nutzer-Daten schuetzen**: Keine sensiblen Dateien (Credentials, .env) an ChatGPT senden.
   Falls der Dateiinhalt verdaechtig aussieht (API-Keys, Passwoerter), warnen und Bestaetigung einholen.
4. **Laengenlimit respektieren**: Bei Dateien ueber 50.000 Zeichen den Nutzer warnen.
5. **Neuer Chat**: Standardmaessig wird immer ein neuer Chat gestartet (`new_chat: true`),
   damit keine Kontextvermischung mit vorherigen ChatGPT-Konversationen stattfindet.
6. **Projektunabhaengig**: Dieser Skill ist nicht an ein bestimmtes Projekt gebunden.
