# Actuación — 2026-08-02

## Objetivo
Crear proyecto `cerebro-obsidian` con:
1. Vault de Obsidian para gestión de conocimiento
2. Skills de OpenCode para tareas, personas y temas
3. Carpeta de actuaciones como historial

## Acciones realizadas

### 1. Creación de estructura
- Carpeta principal: `/home/vhdez/desarrollos-hermes/cerebro-obsidian/`
- Vault: `obsidian-vault/` (todo el contenido vive dentro)
- Repo git: `git@github.com:victorherherARQ/cerebro-obsidian.git`

> **Nota:** La versión inicial tenía `opencode/` y `actuaciones/` como subcarpetas
> hermanas del vault. El **2026-08-03** se reorganizó para meterlas dentro de
> `obsidian-vault/` y simplificar el versionado.

### 2. Vault de Obsidian
Creados dentro de `obsidian-vault/`:
- `README.md` — índice del vault
- `00 Meta/INDICE.md` — índice general (enlaces a Tareas, Personas, Temas, Proyectos, opencode, actuaciones)
- `Tareas/Pendientes.md` — lista de tareas pendientes
- `Tareas/Completadas.md` — historial de completadas
- `Tareas/Proximas.md` — tareas para próxima semana
- `Personas/Victor.md` — ficha propia
- `Personas/Contactos.md` — directorio de contactos
- `Temas/Index.md` — índice temático
- `Temas/IA-Agents.md` — notas sobre agentes AI
- `Temas/LLMs.md` — notas sobre modelos de lenguaje
- `Temas/OAuth2.md` — notas sobre OAuth 2.0
- `Proyectos/Index.md` — índice de proyectos
- `Proyectos/agentgateway-poc.md`
- `Proyectos/minipc-docs.md`
- `Proyectos/synchealth.md`
- `Proyectos/quiniela-analyzer.md`

Tags definidos:
- `#tarea` / `#tarea/completada` / `#tarea/urgente`
- `#persona` / `#contacto`
- `#proyecto`
- `#tema` / `#nota` / `#referencia`

### 3. OpenCode Skills (dentro del vault)
Creados en `obsidian-vault/opencode/`:
- `README.md` — índice
- `tareas/INDEX.md`
- `tareas/buscar.md` — buscar tareas
- `tareas/crear.md` — crear tarea
- `tareas/completar.md` — completar tarea
- `tareas/reporte.md` — generar reporte
- `personas/INDEX.md`
- `personas/buscar.md` — buscar persona
- `personas/crear.md` — crear ficha
- `temas/INDEX.md`
- `temas/investigar.md` — investigar tema
- `temas/resumir.md` — resumir tema

### 4. Actuaciones (dentro del vault)
Creados en `obsidian-vault/actuaciones/`:
- `README.md` — índice de actuaciones
- `2026-08-02-cerebro-obsidian.md` — esta nota

## Resultado
✅ Proyecto `cerebro-obsidian` creado y estructurado
✅ Todo el contenido versionado en un único repo git (`cerebro-obsidian`)
✅ Cron diario a las 23h escribe `actuaciones/YYYY-MM-DD.md` desde `hermes insights`

## Archivos creados
Total: ~25 archivos markdown (todo dentro de `obsidian-vault/`)

## Estructura final

```
cerebro-obsidian/
└── obsidian-vault/          ← Vault de Obsidian + repo git único
    ├── Tareas/
    ├── Personas/
    ├── Temas/
    ├── Proyectos/
    ├── 00 Meta/
    ├── opencode/             ← Skills para OpenCode CLI
    └── actuaciones/          ← Historial diario
```

## Siguiente paso
- Abrir vault en Obsidian (`Open folder as vault` → `obsidian-vault/`)
- Empezar a usar para gestionar tareas reales
- Verificar que el cron diario escribe correctamente en `actuaciones/`
