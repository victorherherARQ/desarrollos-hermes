---
fecha_creada: 2026-08-06
prioridad: media
persona: Victor
proyecto: ""
fecha_limite: ""
tags: [tarea/pendiente, prioridad/media]
---

# Investigar integración Hermes con Google Calendar

Cómo integrarme con Google Calendar para gestionar recordatorios automáticos a Víctor.

## Objetivo

Que yo (Hermes) pueda:
- Crear eventos en el calendario de Víctor
- Leer eventos próximos para contexto
- Configurar recordatorios automáticos (cron jobs, deadlines)
- Vincular eventos con tareas del vault (`Tareas/*.md`)

## Opciones técnicas

### Opción A: Google Calendar API directa
- OAuth 2.0 con Google
- Endpoints REST: `calendar.events.list`, `calendar.events.insert`
- Requiere credenciales OAuth en Google Cloud Console
- Scope: `https://www.googleapis.com/auth/calendar`

### Opción B: Apps Script + Webhook
- Crear un Apps Script público en la cuenta de Víctor
- Hermes envía webhook → Apps Script crea evento
- Más simple, menos código backend

### Opción C: MCP server de Google Calendar
- Si hay MCP server oficial/comunitario
- Integración nativa con agentes
- Buscar: `modelcontextprotocol/google-calendar`

### Opción D: n8n / Zapier / Make
- Workflows visuales
- Trigger: "nueva tarea en cerebro-obsidian" → crear evento
- Sin código, pero cloud-based

## Pasos a seguir

- [ ] Investigar opciones B y C (las más rápidas)
- [ ] Crear OAuth credentials (si opción A)
- [ ] Test integración: crear evento de prueba
- [ ] Diseñar casos de uso:
  - [ ] Recordatorios para deadlines de tareas
  - [ ] Resumen diario 9 AM con eventos del día
  - [ ] Auto-crear evento para reuniones

## Notas

- Google Calendar API requiere proyecto en Google Cloud Console
- Victor tiene cuenta Gmail (asumido) → puede crear OAuth app personal
- Restricción: solo eventos del calendario primario (no compartidos)
- Free tier: 1M queries/día (más que suficiente)

## Referencias

- [Google Calendar API](https://developers.google.com/calendar/api/v3/reference)
- [OAuth 2.0 Setup](https://developers.google.com/calendar/api/quickstart/python)
- [MCP servers](https://github.com/modelcontextprotocol/servers)
