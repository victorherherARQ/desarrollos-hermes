---
tipo: indice
tags: [proyecto/activo, meta/indice]
---

# Proyectos — Índice

## Activos
- [[agentgateway-poc]]
- [[minipc-docs]]
- [[synchealth]]

## Bloqueados
- [[quiniela-analyzer]]

## Archivados

## Vista Dataview

```dataview
LIST
FROM "Proyectos"
WHERE contains(tags, "#proyecto/activo") OR contains(tags, "#proyecto/bloqueado")
SORT file.name ASC
```
