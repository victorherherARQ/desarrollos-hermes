# Buscar Tareas

## Prompt para opencode

Busca en el vault de Obsidian todas las notas con tag `#tarea`.
Devuelve una lista numerada con:
1. Título de la nota
2. Prioridad (alta/media/baja)
3. Proyecto al que pertenece
4. Fecha de creación
5. Primeros 100 chars del contenido

Organiza: primero urgente, luego por proyecto, luego por fecha.

## Ejemplo

```
opencode "Busca todas las tareas pendientes del proyecto synchealth"
```
