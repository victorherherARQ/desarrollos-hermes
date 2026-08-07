# oauth-flow-html skill

Genera un HTML único autocontenido con un **diagrama de secuencia animado** de cualquier flujo OAuth/OIDC.

## Uso rápido

```bash
# Renderizar un ejemplo
python3 ~/.hermes/skills/oauth-flow-html/build_standalone.py \
    --spec ~/.hermes/skills/oauth-flow-html/examples/ciba-flow.json \
    --output /tmp/ciba.html

# Abrir con navegador
xdg-open /tmp/ciba.html
```

## Ejemplos incluidos

- `examples/flow-c-jwt-auth-grant.json` — JWT Authorization Grant (Agent + Keycloak)
- `examples/ciba-flow.json` — **CIBA** (Client Initiated Backchannel Authentication)

## Dónde está

- **Mi home**: `~/.hermes/skills/oauth-flow-html/`
- **Repo**: `/home/vhdez/desarrollos-hermes/.hermes/skills/oauth-flow-html/`

Las dos copias están sincronizadas. Si añades un ejemplo en una, cópialo a la otra.

## Cuándo invocarlo

Cuando el usuario pide:
- "Visualiza el flujo X"
- "Hazme un diagrama de CIBA / OAuth / OIDC"
- "Genera el HTML del flujo"
- "Diagram the JWT bearer grant"

## Cambios recientes

| Fecha | Cambio |
|-------|--------|
| 2026-08-07 | Generalizada: ahora cubre CIBA, OIDC, SAML, etc. Añadido ejemplo CIBA. Sincronizada en 2 ubicaciones. |

## Ver también

- [OpenID Connect CIBA Core 1.0](https://openid.net/specs/openid-client-initiated-backchannel-authentication-core-1_0.html)
- Skill `oauth-agent-on-behalf-of-user` (en `~/.hermes/skills/`)
- ADR-001 (`agent-oauth-poc/docs/CIBA_CONSOLIDATION_DECISION.md`)
