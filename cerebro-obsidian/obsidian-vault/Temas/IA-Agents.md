---
area: ai
tags: [tema/investigacion, area/trabajo]
---

# IA Agents

## Conceptos
- Agente AI: sistema que percibe, decide y actúa
- Tool calling: capacidad de usar herramientas externas
- Memory: contexto corto y largo plazo
- Planning: descomponer tareas en sub-tareas

## Frameworks
- LangGraph — grafos de estados para agentes
- CrewAI — multi-agent orchestration
- AutoGen — Microsoft multi-agent
- kagent — Solo.io, Kubernetes-native

## Herramientas
- MCP (Model Context Protocol)
- OpenAI Functions
- LangChain tools

## Notas relacionadas

```dataview
LIST
FROM "Proyectos"
WHERE contains(tags, "#proyecto/activo") AND contains(file.name, "agent")
```
