# Investigación completada (2026-08-06)

## ✅ Recomendación justificada

**Empezar con Google Calendar API directa en Python** (no Apps Script, no MCP, no Zapier):

| Criterio | API directa | Apps Script | MCP | Zapier |
|----------|-------------|-------------|-----|--------|
| Tiempo inicial | 1-3h | 30-90m | 1-4h | 30m-2h |
| Coste | Gratis | Gratis | Gratis | Pago mensual |
| Adecuación para Hermes | **Muy alta** | Alta (prototipo) | Alta | Media |
| Control | Total | Limitado | Comunitario | Bajo |
| Seguridad | OAuth local | Webhook público | Variable | Cloud |

**Razones**:
- No depende de servicios cloud de pago
- Permite leer, crear, modificar y borrar eventos
- OAuth token se guarda local en WSL (`~/.hermes/calendar/`)
- Arquitectura evolucionable: Python hoy, MCP server mañana

## 🏗️ Arquitectura recomendada

```
Hermes (con memoria + tools)
  │
  ├── Lee notas del vault Obsidian
  │
  ├── Detecta tareas con frontmatter `calendar: true`
  │
  └── Ejecuta calendar_cli.py
          │
          └── Google Calendar API via OAuth 2.0
                  │
                  └── Calendar principal de Víctor
```

## 🔧 Setup paso a paso

### 1. Google Cloud Console

```text
1. https://console.cloud.google.com/
2. Crear proyecto "hermes-calendar"
3. APIs & Services → Library → Google Calendar API → Enable
4. OAuth consent screen → External → añadir email Víctor como test user
5. Credentials → Create → OAuth client ID → Desktop app
6. Descargar JSON como calendar-credentials.json
```

```bash
# Mover a directorio seguro
mkdir -p /home/vhdez/.hermes/calendar
mv ~/Downloads/calendar-credentials.json /home/vhdez/.hermes/calendar/
chmod 600 /home/vhdez/.hermes/calendar/calendar-credentials.json
```

### 2. Venv con dependencias

```bash
cd /home/vhdez/.hermes/calendar
python3 -m venv .venv
source .venv/bin/activate
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### 3. .gitignore estricto

```gitignore
calendar-credentials.json
token.json
.venv/
```

## 💻 Código Python funcional (60 líneas)

Archivo: `/home/vhdez/.hermes/calendar/calendar_demo.py`

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE = Path(__file__).parent
CLIENT_SECRET = BASE / "calendar-credentials.json"
TOKEN = BASE / "token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def service():
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json())
        os.chmod(TOKEN, 0o600)
    return build("calendar", "v3", credentials=creds)


def list_events(calendar_id="primary", limit=10):
    now = datetime.now(timezone.utc).isoformat()
    res = service().events().list(
        calendarId=calendar_id, timeMin=now,
        maxResults=limit, singleEvents=True, orderBy="startTime"
    ).execute()
    for e in res.get("items", []):
        start = e["start"].get("dateTime", e["start"].get("date"))
        print(start, "-", e.get("summary", "(sin título)"))


def create_event(title, start, minutes=30, calendar_id="primary"):
    end = start + timedelta(minutes=minutes)
    body = {
        "summary": title,
        "start": {"dateTime": start.isoformat(), "timeZone": "Europe/Madrid"},
        "end": {"dateTime": end.isoformat(), "timeZone": "Europe/Madrid"},
        "reminders": {"useDefault": False, "overrides": [
            {"method": "popup", "minutes": 10},
            {"method": "email", "minutes": 60},
        ]},
    }
    ev = service().events().insert(calendarId=calendar_id, body=body).execute()
    print("Creado:", ev["htmlLink"])


if __name__ == "__main__":
    create_event(
        "Recordatorio Hermes",
        datetime(2026, 8, 7, 10, 0),
        minutes=30,
    )
    list_events()
```

## 🔌 Integración con vault Obsidian

Plantilla YAML para tareas con calendario:

```yaml
---
calendar: true
start: 2026-08-07T10:00:00+02:00
duration: 45
reminder: 15
google_event_id: ""  # se rellena tras crear
---
```

Flujo automático propuesto (`calendar_sync.py`):

```text
1. Recorre /home/vhdez/desarrollos-hermes/cerebro-obsidian/obsidian-vault/**/*.md
2. Filtrar por frontmatter `calendar: true`
3. Si google_event_id == "" → create_event
4. Si google_event_id != "" → update_event (compara start/title)
5. Log resultado en /home/vhdez/.hermes/calendar/sync.log
6. Cron cada 30 min: 0,30 * * * *
```

## 📋 Roadmap ejecución

| Fase | Acción | ETA |
|------|--------|-----|
| **Fase 1** | Setup Google Cloud + calendar_demo.py funcional | 1h |
| **Fase 2** | calendar_cli.py con subcommands (list/create/sync-vault) | 1h |
| **Fase 3** | calendar_sync.py que lee vault y crea eventos | 1h |
| **Fase 4** | Cron cada 30 min para sync automático | 30m |
| **Fase 5** | Integrar como tool de Hermes (request_user_confirm antes de crear) | 1h |

## 🔒 Seguridad

1. NO subir `calendar-credentials.json` ni `token.json` al repo
2. `chmod 600` en ambos archivos
3. Scope mínimo: `https://www.googleapis.com/auth/calendar` (no `gmail` ni `drive`)
4. Confirmar manualmente antes de crear eventos en Fase 1
5. Revocar credenciales en https://myaccount.google.com/permissions si compromete

## 🌐 Endpoints relevantes

- Google Calendar API: https://developers.google.com/workspace/calendar/api
- Quickstart Python: https://developers.google.com/workspace/calendar/api/quickstart/python
- events.list: https://developers.google.com/workspace/calendar/api/v3/reference/events/list
- events.insert: https://developers.google.com/workspace/calendar/api/v3/reference/events/insert
- OAuth scopes: https://developers.google.com/calendar/api/auth
- Cloud Console: https://console.cloud.google.com/

## MCP servers encontrados (no usar ahora)

| Proyecto | URL | Notas |
|----------|-----|-------|
| taylorwilsdon/google_workspace_mcp | github.com/taylorwilsdon/google_workspace_mcp | Workspace completo |
| takumi0706/google-calendar-mcp | github.com/takumi0706/google-calendar-mcp | Calendar focus |
| @cocal/google-calendar-mcp | npmjs.com/package/@cocal/google-calendar-mcp | npm package |

**Recomendación**: validar primero con script Python. Si funciona, exponer como MCP server propio.

## ✨ Decisión

Empezar implementación **Fase 1+2** esta semana (2h total). Decidir Fase 3-5 según resultado.
