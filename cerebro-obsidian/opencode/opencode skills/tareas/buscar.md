# Buscar Tareas

## Prompt para opencode

```
Busca en el vault de Obsidian todas las notas con tag #tarea/pendiente.
Devuelve una lista numerada con:
1. Título de la nota
2. Proyecto al que pertenece (si tiene tag #proyecto)
3. Prioridad (alta/media/baja)
4. Fecha de creación
5. Primeros 100 chars del contenido

Organiza por prioridad y luego por fecha.
```

## Ejemplo de uso

```bash
opencode "Busca todas las tareas pendientes del proyecto synchealth"
```
