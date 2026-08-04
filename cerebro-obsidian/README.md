# cerebro-obsidian

> **El vault está en:** `obsidian-vault/` (git remote: `git@github.com:victorherherARQ/cerebro-obsidian.git`)

Este directorio contiene el vault de Obsidian y sus recursos.

## Estructura

```
cerebro-obsidian/
└── obsidian-vault/       ← Vault de Obsidian (repo github.com:victorherherARQ/cerebro-obsidian)
    ├── Tareas/
    ├── Personas/
    ├── Temas/
    ├── Proyectos/
    ├── 00 Meta/
    ├── opencode/          ← Skills para OpenCode CLI
    └── actuaciones/       ← Historial diario
```

## En otro ordenador

```bash
# Clonar el vault
git clone git@github.com:victorherherARQ/cerebro-obsidian.git
cd cerebro-obsidian/obsidian-vault

# Abrir en Obsidian como vault
# En Obsidian: Open folder as vault → seleccionar obsidian-vault/

# Trabajar normalmente y hacer push cuando quieras
git add .
git commit -m "..."
git push

# En otro sitio: git pull para sincronizar
git pull
```
