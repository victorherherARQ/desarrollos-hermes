---
area: security
tags: [tema/investigacion, area/trabajo]
---

# OAuth 2.0

## Flows
- **Authorization Code** — Web apps con backend
- **CIBA** — Client Initiated Backchannel Authentication
- **OBO** — On-Behalf-Of (delegación de tokens)
- **Client Credentials** — Machine-to-machine

## Conceptos
- Access Token — token de acceso
- Refresh Token — token de renovación
- ID Token — token de identidad (OIDC)
- Scope — permisos solicitados

## Providers
- Keycloak — Identity provider self-hosted
- Auth0 — Cloud
- Azure AD B2C — Microsoft

## Proyectos relacionados

```dataview
LIST
FROM "Proyectos"
WHERE contains(tags, "#proyecto/activo") AND contains(file.name, "oauth")
```
