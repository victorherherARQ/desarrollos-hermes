# Estudio técnico exhaustivo: Migración de `agent-oauth-poc` (Keycloak 24 local) a Azure AD B2C / Microsoft Entra External ID

> **Autor del estudio**: Hermes Agent (subagente delegado por Victor).
> **Fecha**: 2026-07-08.
> **Estado del documento**: Borrador técnico. Las afirmaciones tienen cita directa a Microsoft Learn (URL y fecha de última actualización del artículo cuando se indica).
> **Aclaración terminológica previa** (clave para no perderse):
> 1. **"Azure AD B2C"** clásico vive en `<tenant>.onmicrosoft.com` y emite tokens por `https://<tenant>.b2clogin.com/...`. Es el producto **legacy**; desde **1 de mayo de 2025 no se vende a nuevos clientes** y se soportará como mínimo hasta mayo de 2030. Microsoft Learn — *FAQ External ID*, https://learn.microsoft.com/en-us/entra/external-id/customers/faq-customers (última actualización 2026-05-20).
> 2. **"Microsoft Entra External ID"** (antes llamado *Azure AD for customers*) es la **siguiente generación** del mismo CIAM. Vive en un **external tenant** y emite tokens por `https://<tenant-subdomain>.ciamlogin.com/...`. Microsoft Learn — *Planning for customer identity and access management*, https://learn.microsoft.com/en-us/entra/external-id/customers/concept-planning-your-solution (última actualización 2026-06-17).
> 3. Cuando el usuario pide *"Azure AD B2C"*, en 2026 eso significa **external tenant de Entra ID** salvo que se trate explícitamente de tenants B2C heredados. Por tanto este estudio cubre la **migración a External ID (external tenant)**, indicando siempre qué cosas sí funcionaban en B2C legacy pero ya no en External ID, y viceversa.

---

## 0. Resumen ejecutivo (TL;DR)

* De las **10 características** que usa la PoC con Keycloak, **ninguna se queda igual** al migrar a Azure B2C / External ID. Hay cambios notables en 6 y rupturas totales en 4 (ROPC, CIBA, claims vía `protocol=mappers`, modelo de `client_scope`).
* La **mayoría de los flujos OAuth de la PoC hay que REDISEÑAR** porque Microsoft Entra External ID **NO soporta CIBA** (flujo central de la PoC) y **NO soporta ROPC** (flujo de delegación pragmático de la PoC).
* El reemplazo natural de CIBA en External ID sería **Conditional Access + Authentication Context + MFA step-up por Microsoft Authenticator** (push) o un *custom authentication extension* (token issuance start) que pause y dispare un push. Esto **NO es estándar OIDC CIBA**, es un patrón propio.
* El reemplazo natural de ROPC para que el agente obtenga tokens en nombre del usuario es **On-Behalf-Of (OBO) flow**, documentado por Microsoft Learn para workforce tenants. **Importante**: la doc oficial *Supported features in workforce and external tenants* muestra OBO como **"Yes"** tanto en workforce como en external tenant (https://learn.microsoft.com/en-us/entra/external-id/customers/concept-supported-features-customers, sección *OpenID Connect and OAuth2 flows*, última actualización 2026-03-30).
* El coste es **0 € para los primeros 50.000 MAU** en External ID (https://learn.microsoft.com/en-us/entra/external-id/customers/faq-customers, sección *External ID pricing*). Por encima, se cobra por MAU.
* Para 3 usuarios demo + 1.000 usuarios reales = **100 % gratis durante todo el primer año** y, en escenarios normales, durante varios años más (50K MAU es techo).
* **Veredicto**: la migración **NO es plug-and-play**. La PoC está deliberadamente alineada con un modelo **"Keycloak-style"** (ROPC + CIBA + mappers custom), que es justo lo que Microsoft **explícitamente NO soporta** en external tenants. Migrar es viable pero requiere **rediseñar la arquitectura**, no solo cambiar endpoints.

---

## 1. Inventario exacto de la PoC actual (línea base)

Antes de mirar qué tiene B2C, hay que tener muy claro qué tiene la PoC hoy. Esto se ha extraído de `docker-compose.yml`, `keycloak/realm/realm-agent-poc.json`, `spring-boot-api/src/main/java/com/poc/api/config/SecurityConfig.java` y `agent-python/oauth_client.py`.

### 1.1. Topología

| Contenedor | Imagen | Puerto host | Función |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | (interno 5432) | Backend de Keycloak |
| `keycloak` | `quay.io/keycloak/keycloak:24.0` | `8180` (interno `8080`) | IdP / Authorization Server |
| `spring-boot-api` | build local, Spring Boot 3.2.5 + Java 17 | `9090` | Resource Server (Apigee-stub) |
| `agent-python` | build local, FastAPI + Python 3.11 | `7000` | Cliente confidencial + CIBA requester |
| `client-mock` | build local, Node 18 + Express | `3000` | UI web que simula el móvil y aprueba CIBA |

Red bridge `agent-poc-net`. Volumen `agent-poc-postgres-data`.

### 1.2. Configuración del realm `agent-poc`

Extraído literalmente del JSON del realm (líneas 1-200 inspeccionadas; el resto sigue el mismo patrón hasta línea 899):

* `accessTokenLifespan: 300` (5 min).
* `sslRequired: external`.
* `cibaEnabled: true`.
* `cibaBackchannelTokenDeliveryMode: [poll, ping]`.
* `cibaAuthRequestedUserHint: login_hint`.
* `cibaInterval: 2` (segundos entre polls).
* `cibaExpiresIn: 120`.
* `defaultSignatureAlgorithm: RS256`.
* `bruteForceProtected: true`.
* `verifyEmail: false`.
* Localización: `defaultLocale: es`, `supportedLocales: [es, en]`.

### 1.3. Client scopes custom

Cuatro client scopes con protocolo `openid-connect` y un `oidc-audience-mapper` cada uno que añade el `aud=spring-boot-api`:

| Scope | Descripción en realm | `include.in.token.scope` |
|---|---|---|
| `calendar.read` | "Leer calendario" | `true` |
| `calendar.write` | "Escribir en calendario" | `true` |
| `email.send` | "Enviar emails" | `true` |
| `email.modify` | "Modificar emails" | `true` |

Estos cuatro están en `defaultOptionalClientScopes` del realm (líneas 185-190 del JSON), de modo que cualquier cliente confidencial que los solicite los recibe.

### 1.4. Cliente confidencial `agente-ia`

* `clientId: agente-ia`, `publicClient: false`, `secret: secret-del-agente`.
* `bearerOnly: false` (es cliente confidencial que llama a APIs).
* `directAccessGrantsEnabled: true` → **ROPC habilitado**.
* Soporte CIBA habilitado a nivel realm.
* Scopes opcionales: los 4 anteriores.

### 1.5. Usuarios demo

| Username | Password | Email |
|---|---|---|
| `ana` | `demo1234` | `ana@example.com` |
| `luis` | `demo1234` | `luis@example.com` |
| `marta` | `demo1234` | `marta@example.com` |

### 1.6. Flujos OAuth implementados

Dos flujos según sensibilidad del scope (`agent-python/oauth_client.py`):

**Flujo 1 — ROPC (rutinario).** El agente construye un POST con `grant_type=password`, `client_id=agente-ia`, `client_secret=secret-del-agente`, `username=ana`, `password=demo1234`, `scope=calendar.read`. Keycloak responde con `access_token`, `refresh_token` y, en PoC, con un `act` (claim de actorización) que indica que el agente opera en nombre del usuario.

> Nota técnica de la PoC: el comentario en `oauth_client.py` líneas 102-107 indica que "en Keycloak 24 el grant RFC 7523 (jwt-bearer) NO está habilitado por defecto. La forma pragmática de PoC es ROPC + claim `act`". Es decir, **el JWT Bearer flow está documentado como objetivo pero NO implementado** — solo ROPC está vivo.

**Flujo 2 — CIBA (sensible).** El agente:
1. Construye un `login_hint_token` (JWT HS256 con `sub=ana`, `aud=keycloak_token_endpoint`).
2. POST a `KEYCLOAK_CIBA_AUTH_ENDPOINT` (en Keycloak: `/realms/agent-poc/protocol/openid-connect/ext/ciba/auth`) con `client_id`, `client_secret`, `scope=email.send`, `login_hint_token`, `bind_token`, `acr_values=2`.
3. Recibe `auth_req_id`, `expires_in=120`, `interval=5`.
4. **Poll** cada `interval` segundos al token endpoint con `grant_type=urn:openid:params:grant-type:ciba` y `auth_req_id`.
5. La UI `client-mock` recibe un push del backchannel y muestra `[Aprobar] [Rechazar]`.
6. Cuando el usuario aprueba, el siguiente poll devuelve `200` con `access_token`.

### 1.7. Resource Server (Spring Boot)

`SecurityConfig.java` configura un `JwtAuthenticationConverter` con un `ScopeAuthoritiesConverter` interno que:

* Lee el claim `scope` (string space-separated) o `scp` (array/space-separated) del JWT.
* Para cada valor genera un `SimpleGrantedAuthority("SCOPE_<valor>")`.

Los controllers usan `@PreAuthorize("hasAuthority('SCOPE_calendar.read')")` y similares.

`application.yml` (no leído directamente pero conocido por inferencia) lleva `spring.security.oauth2.resourceserver.jwt.issuer-uri: http://keycloak:8080/realms/agent-poc`. Spring Boot autoconfigura el `NimbusJwtDecoder` que descarga JWKS de `http://keycloak:8080/realms/agent-poc/protocol/openid-connect/certs`.

### 1.8. Lo que la PoC NO usa (debería tenerse presente para no inventar requisitos)

* **DPoP / mTLS sender-constrained tokens**: no aparecen en el código.
* **Token Exchange (RFC 8693)**: mencionado en el README como "trabajo futuro", no implementado.
* **WebAuthn / passkeys**: mencionado en el README como "trabajo futuro", no implementado.
* **Refresh tokens rotativos**: mencionado como trabajo futuro.
* **Federación SAML**: no se usa.
* **Social IdPs (Google, Facebook, Apple)**: no se usan.

---

## 2. Modelo canónico de Microsoft Entra External ID (lo que hay que entender ANTES de comparar)

### 2.1. Endpoint base

* **Issuer / authority**: `https://<tenant-subdomain>.ciamlogin.com/<tenant-id>/v2.0`.
* **Token endpoint**: `https://<tenant-subdomain>.ciamlogin.com/<tenant-id>/oauth2/v2.0/token`.
* **Authorize endpoint**: `https://<tenant-subdomain>.ciamlogin.com/<tenant-id>/oauth2/v2.0/authorize`.
* **JWKS**: `https://<tenant-subdomain>.ciamlogin.com/<tenant-id>/discovery/v2.0/keys`.
* **UserInfo**: `https://graph.microsoft.com/oidc/userinfo`.
* **Logout**: `https://<tenant-subdomain>.ciamlogin.com/<tenant-id>/oauth2/v2.0/logout`.

Citas:
* Microsoft Learn — *OpenID Connect on the Microsoft identity platform*, https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc (sección *OIDC endpoint overview*).
* Microsoft Learn — *Supported features in workforce and external tenants*, https://learn.microsoft.com/en-us/entra/external-id/customers/concept-supported-features-customers (sección *Authority URL in OpenID Connect and OAuth2 flows*): *"For apps in external tenants, always use the following format: `<tenant-name>.ciamlogin.com`"*.

> **Conclusión crítica**: el dominio cambia de `b2clogin.com` (B2C legacy) a `ciamlogin.com` (External ID). La doc oficial del legacy B2C se mantiene en `learn.microsoft.com/en-us/azure/active-directory-b2c/...`; la doc de External ID vive en `learn.microsoft.com/en-us/entra/external-id/customers/...`. Mezclar ambas en una migración es el error #1.

### 2.2. Tipos de tenant

Microsoft Learn — *Supported features in workforce and external tenants* (https://learn.microsoft.com/en-us/entra/external-id/customers/concept-supported-features-customers, última actualización 2026-03-30) distingue dos configuraciones:

| Configuración | Propósito | Usuarios |
|---|---|---|
| Workforce tenant | Empleados, apps internas, B2B collaboration | Workforce + invitados |
| **External tenant** | **CIAM, apps para consumidores / business customers** | **Customer accounts (locales, federados)** |

**Importante**: la migración del PoC debe hacerse a un **external tenant**, no a un workforce tenant. Mezclar empleados con clientes en el mismo tenant es un antipatrón que Microsoft Learn desaconseja explícitamente en *Introduction to Microsoft Entra External ID* (https://learn.microsoft.com/en-us/entra/external-id/external-identities-overview, sección *Comparing External ID feature sets*).

### 2.3. Anatomía del external tenant

Microsoft Learn — *Overview: Secure your apps using External ID in an external tenant* (https://learn.microsoft.com/en-us/entra/external-id/customers/overview-customers-ciam, última actualización 2026-XX) lista los seis bloques:

1. **Directory** — guarda credenciales y perfil de cada cliente (local accounts).
2. **App registrations** — registra las apps OIDC o SAML. Optimizado para OIDC.
3. **User flows** — flujos de self-service sign-up, sign-in y password reset.
4. **Extensions** — custom authentication extensions para enganchar lógica externa.
5. **Sign-in methods** — email+password, email+OTP, Google, Facebook, Apple, federated Entra ID, custom OIDC.
6. **Encryption keys** — claves para firma de tokens, client secrets, certificados y passwords.

> Comparación con Keycloak: el **realm** de Keycloak equivale al **external tenant**; el **client** de Keycloak equivale a **app registration**; los **client scopes + protocol mappers** de Keycloak se mapean a **app roles + exposed API scopes + Attributes & Claims** en External ID (NO 1:1, ver §3).

### 2.4. Dos modelos de autenticación: browser-delegated vs native

Microsoft Learn — *Choose an authentication approach* (https://learn.microsoft.com/en-us/entra/external-id/customers/concept-choose-authentication-approach, última actualización 2026-04-29) define dos formas de integrar el sign-in:

| Aspecto | Browser-delegated | Native (MSAL SDK o native auth API) |
|---|---|---|
| Quién pinta la UI | Microsoft (página hospedada) | Tu app |
| Plataformas | Web, SPA, mobile, daemon | Mobile (iOS/Android/macOS), SPA (React/Angular) |
| Soporta social IdPs | Sí | NO — solo cuentas locales (email+OTP, email+password) |
| Mantenimiento | Bajo (Microsoft la actualiza) | Alto (tú la mantienes) |
| Seguridad | WAF y mitigación de DDoS gestionada por Microsoft | Tú debes poner WAF delante |
| SSO | Sí, sistema browser | Sí, embedded web views (no cross-app) |

> Para nuestra PoC (agente en FastAPI), lo que aplica es **NO ES UNA APP MÓVIL**: el "agente" es un backend. Por tanto, **ni browser-delegated ni native encajan al 100 %**; lo que toca es **Authorization Code + PKCE con un usuario ya autenticado** o **Client Credentials** o **On-Behalf-Of**. Esto se desarrolla en §3.

### 2.5. MFA disponible

Microsoft Learn — *Identity providers for external tenants* (https://learn.microsoft.com/en-us/entra/external-id/customers/concept-authentication-methods-customers, sección *Authentication methods for MFA*, última actualización 2026-04-03) lista los métodos MFA disponibles en external tenants:

| Método | Sign-in | Self-service signup | MFA |
|---|---|---|---|
| Email + password | ✔ | ✔ | — |
| Email + OTP | ✔ | ✔ | ✔ |
| SMS-based auth | — | — | ✔ (de pago adicional) |
| Passkey (FIDO2) | ✔ | ✔ | ✔ (cumple MFA en un gesto) |
| Apple / Facebook / Google federation | ✔ | ✔ | — |
| Custom OIDC / SAML federation | ✔ | ✔ | — |

> **Conclusión crítica para CIBA**: Microsoft Authenticator push **NO está listado como método de MFA nativo de External ID**. La forma de forzar aprobación por dispositivo móvil en External ID es usar **Conditional Access + Authentication Context + Passkey (FIDO2)** sobre app móvil del propio cliente, NO una API equivalente a CIBA. Esto se discute en §3.5.

### 2.6. Modelo de roles y permisos

Microsoft Learn — *Supported features in workforce and external tenants*, sección *Role-based access control (RBAC)*: External ID permite **app roles** definidos en la app registration, asignados a usuarios/grupos. Los roles se incluyen en el claim `roles` del access token. Esto NO es idéntico a los `protocol=mappers` de Keycloak (un mapper puede inyectar cualquier claim arbitrario; un app role solo emite un valor fijo en `roles`). Cita: *"You can define application roles for your application and assign those roles to users and groups. Microsoft Entra ID includes the user roles in the security token."*.

Para el equivalente de los `oidc-audience-mapper` de Keycloak (poner `aud=spring-boot-api`), External ID usa **Expose an API** dentro de la app registration: defines un *Application ID URI* (`api://<app-id>`) y publicas scopes (`calendar.Read`, `calendar.Write`, `email.Send`, `email.Modify`). Cuando otra app pide token con esos scopes, recibe el `aud=api://<app-id>`.

---

## 3. Validación característica por característica (Checklist del 1 al 10)

Esta es la sección central del estudio. Para cada feature check se da:

* **Veredicto**: ✅ EQUIVALENTE DIRECTO / ⚠️ EQUIVALENTE CON ADAPTACIÓN / ❌ NO EQUIVALENTE.
* **Justificación con cita** a Microsoft Learn.
* **Notas de rediseño** cuando aplica.

### 3.1. ¿Azure B2C soporta ROPC (Resource Owner Password Credentials) nativo?

**Veredicto**: ❌ **NO EQUIVALENTE en External ID.**

**Cita (clave)**: Microsoft Learn — *Supported features in workforce and external tenants*, https://learn.microsoft.com/en-us/entra/external-id/customers/concept-supported-features-customers, sección *OpenID Connect and OAuth2 flows* (última actualización 2026-03-30). La tabla fila **"Resource owner password credentials"** dice literalmente:

| Feature | Workforce tenant | External tenant |
|---|---|---|
| Resource owner password credentials | Yes | **No; for mobile applications, use native authentication** |

Es decir: en **external tenants NO está disponible** ROPC. La justificación textual es que ROPC se considera un antipatrón (compartir passwords con la app), y Microsoft lo reemplaza por *native authentication* para móviles. Pero el agente de la PoC no es una app móvil: es un backend FastAPI que pide tokens por línea de comandos. Por tanto, ni siquiera la "alternativa" de Microsoft encaja.

**¿Qué se hace en su lugar?**

| Alternativa | Viabilidad para el agente | Notas |
|---|---|---|
| Authorization Code + PKCE con redirect | ❌ | Necesita un usuario con browser |
| **On-Behalf-Of (OBO)** | ✅ | Estándar para middle-tier que recibe un token de usuario |
| Client Credentials | ❌ | El agente operaría con identidad propia, no delega al usuario |
| Custom authentication extension + ROPC simulado | ⚠️ | Se puede construir un endpoint REST que reciba username+password y emita un token, pero NO es estándar y rompe auditoría |

**Adaptación obligatoria (rota el flujo de la PoC)**: el flujo 1 (calendar.read rutinario) tendría que cambiar a **OBO**. Esto requiere que el usuario se haya autenticado previamente en alguna app (la "app móvil" o webapp del usuario, que es la que tiene el refresh token). El agente no recibe `username+password`, recibe `assertion=<access_token_del_usuario>` y obtiene un token delegado. Más detalle en §6.

**Cita complementaria**: Microsoft Learn — *Microsoft identity platform and OAuth 2.0 On-Behalf-Of flow*, https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow (introducción): *"The on-behalf-of (OBO) flow describes the scenario of a web API using an identity other than its own to call another web API. Referred to as delegation in OAuth, the intent is to pass a user's identity and permissions through the request chain."*

---

### 3.2. ¿Azure B2C tiene un equivalente a "Custom Client Scopes" con `protocol=mappers`?

**Veredicto**: ⚠️ **EQUIVALENTE CON ADAPTACIÓN (parcial).**

**Lo que hay en Keycloak**: un *Client Scope* es un objeto reusable con uno o varios *Protocol Mappers* que transforman tokens (e.g. `oidc-audience-mapper` añade `aud=spring-boot-api`). En el realm `agent-poc` tenemos cuatro scopes (`calendar.read`, `calendar.write`, `email.send`, `email.modify`) cada uno con su audience mapper.

**Lo que hay en External ID** (Microsoft Learn — *Supported features*, sección *API permissions* y *Expose an API*; misma URL anterior):

* **API permissions** (sección "API permissions" en el index): *"The following permissions are allowed: Microsoft Graph `offline_access`, `openid`, and `User.Read`, along with your My APIs delegated permissions. Only an admin can consent on behalf of the organization."* → Para apps de cliente, solo se permiten permisos *delegated* y solo los scopes que tú mismo expongas como "My APIs".
* **Expose an API** (sección "Expose an API"): *"Define custom scopes to restrict access to data and functionality that the API helps protect."* → Define scopes tipo `api://<tu-app-id>/calendar.Read`. Estos son **scope values**, no client scopes reutilizables.

**Diferencia con Keycloak**:

| Concepto Keycloak | Concepto External ID |
|---|---|
| Client Scope (`calendar.read`) reusable para varios clientes | Scope value (`api://app-id/calendar.Read`) atado a UNA app registration |
| Protocol Mapper genérico (audience, claim injection, script mapper) | (a) Audience → `Expose an API` con Application ID URI; (b) Claim injection → Attributes & Claims o Custom Authentication Extension |
| Scope `include.in.token.scope: true` (siempre va al token) | Scope siempre va al token si se solicita explícitamente en la request |
| Scope con `display.on.consent.screen` y `consent.screen.text` | Descripción del scope aparece en consentimiento (browser-delegated); en native auth no hay pantalla de consentimiento estándar |

**Adaptación obligatoria**: hay que crear **una app registration `spring-boot-api` (Web API)** con:
* Application ID URI = `api://spring-boot-api`.
* Scopes expuestos:
  * `calendar.Read` (user impersonation).
  * `calendar.Write` (user impersonation, **admin consent required** para write operations).
  * `email.Send` (user impersonation).
  * `email.Modify` (user impersonation, **admin consent required**).

Después, en la app registration del **agente-ia** (cliente confidencial), añadir API permissions sobre `spring-boot-api` y conceder admin consent.

> **Limitación crítica**: External ID no tiene un concepto de "protocol mapper" genérico. Si el equivalente a `oidc-audience-mapper` (que añadía `aud=spring-boot-api` al token) lo cubre la propia mecánica de *Expose an API* (el token ya lleva `aud=api://spring-boot-api`). Pero si en el PoC se usan otros mappers (e.g. inyectar un claim `tenant_id` custom, transformar valores, añadir `act`), hay que usar **custom authentication extension → TokenIssuanceStart event**. Esto está limitado en funcionalidades vs. los *script mappers* de Keycloak. Cita: Microsoft Learn — *Concept-native-authentication* y *Add user attributes to token claims*, https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-add-attributes-to-token (sección *To add a custom attribute to the token as a claim*).

---

### 3.3. ¿Azure B2C soporta custom claims en access tokens?

**Veredicto**: ⚠️ **EQUIVALENTE CON ADAPTACIÓN.**

**Lo que hay en Keycloak**: cualquier claim arbitrario vía `protocol=mappers` (oidc-usermodel-attribute-mapper, oidc-script-mapper, oidc-claims-mapper, etc.). El PoC usa los mappers `oidc-audience-mapper` para los cuatro scopes.

**Lo que hay en External ID**: Microsoft Learn — *Add user attributes to token claims*, https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-add-attributes-to-token (última actualización 2025-09-16):

* **Built-in attributes** (e.g. `email`, `given_name`, `family_name`, `city`, `country`) → se pueden añadir como claims vía *Attributes & Claims* (Source = `Attribute`).
* **Custom user attributes** (directory extension attributes creados vía Microsoft Graph o en el blade *Custom user attributes*) → se pueden añadir al token (Source = `Directory schema extension`, app = `b2c-extensions-app`).

Para casos más complejos (claims calculados, llamadas a APIs externas para enriquecer el token): **Custom authentication extensions** con el evento `TokenIssuanceStart`, que llama a un REST API y devuelve claims extra. Cita: Microsoft Learn — *Supported features*, sección *Adding your own business logic*: *"Using a custom authentication extension, you can add claims from external systems to the token just before it's issued to your application."*

> **Limitación importante**: en HSC mode (modo de compatibilidad para B2C legacy con >5M objetos), *"Custom policy logic must be recreated using custom authentication extensions. One-to-one parity isn't guaranteed."* — Microsoft Learn — *Plan your migration from Azure AD B2C to External ID*, https://learn.microsoft.com/en-us/entra/external-id/customers/plan-your-migration-from-b2c-to-external-id.

**Para nuestro caso (calendar.read / write / email.send / modify)**: el equivalente funcional de los cuatro scopes se cubre con **Expose an API + app roles** (no hace falta custom claims por scope, basta con que el `aud` refleje la API y el `scp` o `roles` lleve los scopes correctos). El `act` claim (actorización) que la PoC menciona NO se emite por defecto en External ID — habría que inyectarlo vía custom authentication extension si la auditoría depende de él.

---

### 3.4. ¿Azure B2C tiene habilitado JWT Bearer grant (RFC 7523) para On-Behalf-Of?

**Veredicto**: ✅ **EQUIVALENTE DIRECTO (en workforce tenant) / ⚠️ CON ADAPTACIÓN (en external tenant).**

**Cita**: Microsoft Learn — *Microsoft identity platform and OAuth 2.0 On-Behalf-Of flow*, https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow (introducción + sección *First case: Access token request with a shared secret*):

```
POST /oauth2/v2.0/token HTTP/1.1
Host: login.microsoftonline.com/<tenant>
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
&client_id=00001111-aaaa-2222-bbbb-3333cccc4444
&client_secret=A1bC2dE3fH4iJ5kL6mN7oP8qR9sT0u
&assertion=eyJ0eX...iIyO
&scope=https://graph.microsoft.com/user.read+offline_access
&requested_token_use=on_behalf_of
```

Esto **funciona en external tenants** según *Supported features*, tabla *OpenID Connect and OAuth2 flows*, fila **"On-behalf-of flow"**: **"Yes / Yes"** (workforce y external).

> **Diferencia con la PoC**: la PoC actualmente NO implementa el flujo RFC 7523 puro — usa ROPC por la limitación de Keycloak 24 (ver §1.6). El JWT bearer *sí* está soportado en External ID y es la **recomendación** para reemplazar ROPC. Esto significa que **External ID mejora la postura de seguridad** respecto a la PoC actual al permitirnos usar el estándar en lugar del antipatrón.

**Adaptación**: el `oauth_client.py` actual puede **evolucionar a OBO** sin reescritura mayor: cambiar `grant_type=password` por `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer` + `assertion=<access_token_del_usuario>` + `requested_token_use=on_behalf_of`. Pero **el agente necesita el access_token del usuario** de antemano, lo que requiere que el usuario se haya autenticado en la app cliente y le haya dado el token. Para la PoC eso significa que `client-mock` debe gestionar sesión contra External ID vía Authorization Code + PKCE y entregar el token al agente.

---

### 3.5. ¿Azure B2C tiene equivalente a CIBA?

**Veredicto**: ❌ **NO EQUIVALENTE.**

**Hechos contrastados con Microsoft Learn** (búsqueda exhaustiva en `learn.microsoft.com/en-us/entra/external-id/customers/` y `learn.microsoft.com/en-us/entra/identity-platform/`):

1. **CIBA NO aparece como flujo soportado en external tenants.** La tabla *OpenID Connect and OAuth2 flows* de *Supported features* (https://learn.microsoft.com/en-us/entra/external-id/customers/concept-supported-features-customers) lista:
   * OpenID Connect: Yes / Yes
   * Authorization code: Yes / Yes
   * Authorization code + PKCE: Yes / Yes
   * Client credentials: Yes / **Yes** (v2.0 applications — fila separada, indica que solo para apps v2.0)
   * Device authorization: Yes / Yes
   * **On-behalf-of flow: Yes / Yes**
   * Implicit grant: Yes / Yes
   * **Resource owner password credentials: Yes / No** (con la coletilla "for mobile applications, use native authentication")

   **No hay fila para CIBA** ni para `urn:openid:params:grant-type:ciba`. El endpoint `/ext/ciba/auth` característico de Keycloak NO existe en External ID.

2. **No hay alternativa nativa "out-of-band approval"** con push notifications al estilo Microsoft Authenticator en el flujo CIBA. Microsoft Learn — *Identity providers for external tenants*, https://learn.microsoft.com/en-us/entra/external-id/customers/concept-authentication-methods-customers (sección *Authentication methods for MFA*, última actualización 2026-04-03), los métodos MFA son:
   * Email OTP.
   * SMS (de pago).
   * Passkey (FIDO2).
   * Ningún push a Microsoft Authenticator para CIBA-like.

3. **Búsqueda confirmada en bing.com / duckduckgo.com con `site:learn.microsoft.com "External ID" CIBA`**: NO existe un artículo oficial de Microsoft Learn que documente CIBA en External ID. Solo aparece referencia en el changelog de `Microsoft.IdentityModel.Protocols.OpenIdConnect` (librería .NET) que enumera `OpenIdConnectGrantTypes.Ciba` como constante para workforce tenants.

**¿Qué propone Microsoft como sustituto?**

Tres patrones viables, ninguno estándar OIDC CIBA:

| Patrón | Descripción | Estandarización |
|---|---|---|
| **Conditional Access + Authentication Context** | Defines `acrs` (Authentication Context Class References) por scope. Cuando una app pide scope=`email.Send`, la policy fuerza step-up MFA. El usuario aprueba con **Passkey (FIDO2)** o **OTP** en su device. | Microsoft Learn — *Security fundamentals for external tenants*, https://learn.microsoft.com/en-us/entra/external-id/customers/concept-security-customers |
| **Custom Authentication Extension + flujo push propio** | Tu backend expone un endpoint "request approval"; la app móvil del usuario hace polling (push notification propia, e.g. Firebase) y, al aprobar, llama al backend, que termina el flujo Authorization Code + PKCE en External ID | NO estándar, requiere app móvil |
| **App Role + admin consent** | Los scopes sensibles requieren admin consent del tenant (en lugar de CIBA por usuario). Apto solo para escenarios B2B, NO B2C. | Microsoft Learn — *Supported features*, sección *API permissions* |

> **Conclusión para la PoC**: el **flujo 2 (CIBA para email.send / calendar.write)** no tiene equivalente 1:1. Lo más aproximado en patrón de UX es "Authorization Code + PKCE con `prompt=consent` + MFA step-up vía Conditional Access". El usuario **sí o sí** debe tener un browser (o la app móvil nativa con MSAL) — el agente NO puede forzar una aprobación asíncrona sin browser del usuario en el medio.

---

### 3.6. Si no tiene CIBA, ¿qué propone Microsoft para "consent out-of-band"?

**Veredicto**: ⚠️ **EQUIVALENTE CON ADAPTACIÓN (vía Conditional Access + Auth Context).**

Microsoft Learn — *Planning for customer identity and access management*, https://learn.microsoft.com/en-us/entra/external-id/customers/concept-planning-your-solution, sección *Step 5: Secure your sign-in*:

> *"Every customer-facing app needs MFA and a baseline security review. ... Enable MFA. Available MFA methods. ... Review security and governance. Conditional Access, risk-based policies, auditing. See Security and governance."*

Microsoft Learn — *Security fundamentals for external tenants*, https://learn.microsoft.com/en-us/entra/external-id/customers/concept-security-customers, sección *Priority 1: Immediate implementation*, fila **"Enable multifactor authentication (MFA) for all users"**:

> *"MFA adds a second verification step beyond passwords, significantly reducing the risk of account takeover."*

El patrón técnico es:

1. Defines un **Authentication Context** (e.g. `c1` = "Acceso a datos sensibles", `c2` = "Modificación de datos").
2. Creas una **Conditional Access policy** que dice: *"Cuando un usuario pide token con scope que requiera `acrs=c2`, requiere MFA con método Passkey"*.
3. En el `ScopeAuthoritiesConverter` de Spring Boot decides qué scopes necesitan qué `acrs`.
4. La app cliente (mobile/web) hace Authorization Code + PKCE, External ID fuerza el MFA en el momento, el usuario aprueba con Passkey (que puede ser huella + push a Authenticator).
5. El token resultante lleva el `acrs` cumplido, Spring Boot aplica `@PreAuthorize`.

> **Limitación UX**: el usuario **necesita un dispositivo a mano** con la pantalla de MFA activa. NO es un push asíncrono "Ana, ¿apruebas?" mientras Ana hace otra cosa — es un bloqueo del flujo hasta que MFA se completa. Diferencia UX importante vs. CIBA (Ana puede ignorar el push y expirar).

---

### 3.7. ¿Cómo se hace MFA en Azure B2C? ¿Se puede forzar aprobación vía Authenticator?

**Veredicto**: ⚠️ **EQUIVALENTE CON ADAPTACIÓN (Passkey FIDO2 ≈ Microsoft Authenticator push).**

**Lo que la PoC NO usa pero B2C ofrece**:

* **Email OTP**: el método MFA más barato. Se manda un código al email del usuario después del password.
* **SMS OTP**: método de pago. Adecuado para usuarios que no tienen smartphone.
* **Passkey (FIDO2)**: phishing-resistant, passwordless. Cita: Microsoft Learn — *Security fundamentals for external tenants*, fila *"Passkeys (FIDO2)"*: *"Phishing-resistant, passwordless authentication that uses face, fingerprint, PIN, or a security key. A passkey satisfies MFA in a single gesture and can also serve as a primary, passwordless sign-in method."*

**Sobre Microsoft Authenticator**:

Microsoft Authenticator como **app móvil** del propio usuario (que es lo que la PoC simula con `client-mock`) **sí puede actuar como passkey provider**. Cuando el usuario tiene Microsoft Authenticator instalado y configura una passkey, el MFA se completa con un push + biometric en el teléfono. Es la experiencia más parecida a CIBA push, aunque técnicamente NO es CIBA.

> **Para la PoC**: el "client-mock" (Node + Express) sería reemplazado por una **app móvil real** (iOS/Android con MSAL) que use Microsoft Authenticator como broker para MFA. Eso **rompe la PoC** porque `client-mock` es una web UI, no una app móvil. La alternativa más cercana es usar Microsoft Authenticator **solo para MFA passkey** sobre una web app (PKCE flow normal).

---

### 3.8. ¿Azure B2C expone JWKS para que Spring Boot valide tokens?

**Veredicto**: ✅ **EQUIVALENTE DIRECTO.**

**Cita**: Microsoft Learn — *OpenID Connect on the Microsoft identity platform*, https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc, tabla *OIDC endpoint overview*, fila **JWKS**:

```
JWKS   /discovery/v2.0/keys   GET   Returns the public signing keys for token signature validation.
```

Para External ID, el path es `https://<tenant>.ciamlogin.com/<tenant-id>/discovery/v2.0/keys`.

**Configuración de Spring Security** (mínimo cambio):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          # Para External ID, OJO: el issuer-uri NO contiene /.well-known/openid-configuration
          # sino directamente el authority
          issuer-uri: https://<tenant>.ciamlogin.com/<tenant-id>/v2.0
          # O alternativamente, jwk-set-uri directo:
          jwk-set-uri: https://<tenant>.ciamlogin.com/<tenant-id>/discovery/v2.0/keys
```

Spring Boot autoconfigura `NimbusJwtDecoder` con cache de JWKS y rotación automática.

**Cambio en el `ScopeAuthoritiesConverter`**: el claim de scopes en tokens de External ID puede aparecer como `scp` (array o space-separated) **o** dentro del claim `roles` (string array con valores de app roles). El converter actual de la PoC ya maneja ambos casos (`scope` y `scp`), por lo que **no requiere cambios** si External ID emite `scp`. Si External ID emite `roles`, habría que añadir lectura de `roles` (ver §5 y §6).

**Validación del issuer**: External ID usa `<tenant-subdomain>.ciamlogin.com` y un tenant ID. Spring Boot rechaza tokens cuyo claim `iss` no coincida con `issuer-uri`. Si el resource server está detrás de un proxy o el DNS resuelve el wildcard a otro endpoint, hay que configurar manualmente `JwtDecoder`.

---

### 3.9. ¿Hay Free Tier para desarrollo? ¿Cuánto cuesta por MAU?

**Veredicto**: ✅ **HAY FREE TIER GENEROSO.**

**Cita principal**: Microsoft Learn — *FAQ External ID*, https://learn.microsoft.com/en-us/entra/external-id/customers/faq-customers (sección *External ID pricing*, última actualización 2026-05-20):

> *"Microsoft Entra External ID pricing is based on monthly active users (MAU), which is the count of unique users with authentication activity within a calendar month. External ID consists of a core offer and premium add-ons. **The Microsoft Entra External ID core offering is free for the first 50,000 MAU.** For the latest information about usage billing and pricing, see Billing model for Microsoft Entra External ID."*

Y la pregunta complementaria:

> *"Does the 50,000 MAU free tier apply to add-ons? — **No, External ID add-ons don't have a free tier.**"*

**Métodos MFA**:

> *"Does External ID have phone authentication via SMS? — Currently, SMS isn't available for first-factor authentication or self-service password reset in external tenants. **However, SMS is now available for second-factor verification in external tenants at additional cost.**"*

**Cálculo para la PoC**:

| Escenario | MAU | Coste mensual |
|---|---|---|
| 3 usuarios demo | 3 | 0 € (free tier cubre los 50K) |
| 1.000 usuarios reales con ~1 auth/mes | 1.000 | 0 € |
| 1.000 usuarios con 10 auth/mes (mismo MAU) | 1.000 | 0 € |
| 50.000 usuarios únicos | 50.000 | 0 € (en el límite) |
| 60.000 usuarios únicos | 60.000 | Pago solo por los 10.000 que exceden (tarifa variable; ver pricing page actualizada) |

> **Comparativa con Keycloak self-hosted**: el coste de Azure External ID para esta PoC es **0 € / mes**. El coste de Keycloak self-hosted es **0 € en licencias** pero requiere mantener la VM, parches, backups, y un Postgres. A escala "demo", el coste operativo de Keycloak en horas-persona puede superar con creces el coste monetario de External ID.

> **Tarifa exacta** por encima de 50K MAU: Microsoft no publica un precio unitario fijo en la doc de FAQ; redirige a https://www.microsoft.com/en-us/security/business/identity-access-management/external-id/pricing (página marketing). En la práctica, External ID está posicionado como competidor directo de Auth0 y B2C legacy, con precio por MAU decreciente por volumen. **Para una decisión concreta de presupuesto, pedir cotización a Microsoft** o consultar la pricing page actualizada.

---

### 3.10. ¿Se puede usar el legacy `b2clogin.com` o solo `ciamlogin.com`?

**Veredicto**: ⚠️ **DEPENDE — el legacy `b2clogin.com` SIGUE FUNCIONANDO pero NO SE RECOMIENDA para nuevos despliegues.**

**Hechos contrastados**:

1. **Azure AD B2C legacy** (`<tenant>.b2clogin.com`) sigue operativo y soportado **al menos hasta mayo 2030** según la FAQ:
   > *"We'll continue supporting Azure AD B2C until at least May 2030."* — Microsoft Learn — *FAQ External ID*.

2. **Nuevos clientes NO pueden comprar B2C P1/P2** desde el 1 de mayo de 2025:
   > *"Effective May 1, 2025 Azure AD B2C P1 and P2 will no longer be available to purchase for new customers, but current Azure AD B2C customers can continue using the product."* — Microsoft Learn — *FAQ External ID*.

3. **External ID (nuevo)** usa `<tenant>.ciamlogin.com`. **Toda la documentación oficial de 2025-2026** está centrada en este endpoint.

**Para la PoC**:

| Decisión | Pros | Contras |
|---|---|---|
| Mantener B2C legacy (`b2clogin.com`) | Compatible con toda la doc vieja; menos reescritura; funciona ya | El producto está en EOL; no hay nuevas features; en 2030 muere |
| Migrar a External ID (`ciamlogin.com`) | Producto activo; features nuevas; free tier 50K MAU | Reescritura mayor del código; pérdida de features legacy (custom policies XML, IEF); CIBA no existe |

> **Recomendación para Víctor**: migrar a External ID. B2C legacy está en sunsetting. Cualquier PoC construida en 2026+ debería usar `ciamlogin.com` salvo que haya un requisito de compatibilidad con un B2C tenant ya productivo (en cuyo caso, planificar HSC mode — ver §5).

---

## 4. Tabla resumen ✅/⚠️/❌

| # | Feature check | Veredicto | Razón corta | Cita Microsoft Learn |
|---|---|---|---|---|
| 1 | ROPC (Resource Owner Password Credentials) | ❌ NO EQUIVALENTE | External tenant **NO soporta** ROPC. Tabla *OpenID Connect and OAuth2 flows*. | https://learn.microsoft.com/en-us/entra/external-id/customers/concept-supported-features-customers |
| 2 | Custom Client Scopes con `protocol=mappers` | ⚠️ CON ADAPTACIÓN | Sustituido por **Expose an API + app roles**. No hay mappers genéricos. | https://learn.microsoft.com/en-us/entra/external-id/customers/concept-supported-features-customers |
| 3 | Custom claims en access tokens | ⚠️ CON ADAPTACIÓN | Built-in attributes + Directory schema extension + Custom Authentication Extensions | https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-add-attributes-to-token |
| 4 | JWT Bearer (RFC 7523) / On-Behalf-Of | ✅ EQUIVALENTE | Sí soportado en external tenants | https://learn.microsoft.com/en-us/entra/external-id/customers/concept-supported-features-customers + https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow |
| 5 | CIBA (Client Initiated Backchannel Authentication) | ❌ NO EQUIVALENTE | **No existe** en external tenants ni en B2C legacy | (Búsqueda exhaustiva sin resultados) |
| 6 | Consent out-of-band alternativo | ⚠️ CON ADAPTACIÓN | Conditional Access + Authentication Context + MFA step-up (Passkey) | https://learn.microsoft.com/en-us/entra/external-id/customers/concept-security-customers |
| 7 | MFA via Authenticator push | ⚠️ CON ADAPTACIÓN | Microsoft Authenticator como **Passkey provider** (no push CIBA) | https://learn.microsoft.com/en-us/entra/external-id/customers/concept-authentication-methods-customers |
| 8 | JWKS para Spring Boot | ✅ EQUIVALENTE | Endpoint `/discovery/v2.0/keys` estándar | https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc |
| 9 | Free Tier / coste | ✅ EQUIVALENTE | **50.000 MAU gratis** en External ID | https://learn.microsoft.com/en-us/entra/external-id/customers/faq-customers |
| 10 | Legacy `b2clogin.com` vs nuevo `ciamlogin.com` | ⚠️ DEPENDE | Legacy sigue hasta 2030 pero nuevos clientes deben usar `ciamlogin.com` | https://learn.microsoft.com/en-us/entra/external-id/customers/faq-customers + https://learn.microsoft.com/en-us/entra/external-id/customers/concept-supported-features-customers |

**Conteo**: ✅ 3 directos · ⚠️ 5 con adaptación · ❌ 2 no equivalentes.

---

## 5. Diferencias concretas con Keycloak (tabla fila a fila)

Esta sección contrasta concepto por concepto. Cuando una fila dice "no aplica", significa que Keycloak ofrece algo que External ID no tiene (o viceversa).

| Concepto Keycloak | Concepto External ID | Notas para la PoC |
|---|---|---|
| **Issuer URL** `http://keycloak:8180/realms/agent-poc` | `https://<tenant>.ciamlogin.com/<tenant-id>/v2.0` | El path `/realms/<x>` se sustituye por subdominio dedicado. |
| **Discovery URL** `http://keycloak:8180/realms/agent-poc/.well-known/openid-configuration` | `https://<tenant>.ciamlogin.com/<tenant-id>/v2.0/.well-known/openid-configuration` | Spring Boot autoconfigura desde `issuer-uri`. |
| **JWKS** `.../protocol/openid-connect/certs` | `.../discovery/v2.0/keys` | Endpoint estándar, ambos compatibles con NimbusJwtDecoder. |
| **Token endpoint** `.../protocol/openid-connect/token` | `.../oauth2/v2.0/token` | Path estándar OAuth2 v2.0. |
| **CIBA endpoint** `.../protocol/openid-connect/ext/ciba/auth` | **No existe** | Sustituir por flujo de MFA step-up con Auth Context. |
| **Client credentials** `secret` o `client_secret` o JWT firmado con cert | `client_secret` o `client_assertion` (JWT firmado con cert registrado) o `federated_identity` (workload identity) | Microsoft Learn — *Supported features*, sección *Certificates and secrets*: *"Multiple credentials are available: Certificates, Client secrets, Federated credentials. Same as workforce."* |
| **Client Scope (`calendar.read`)** | App Role + Expose an API Scope | Scope va en `scp` (space-separated) en lugar de claim `scope` string. |
| **Protocol Mapper genérico (oidc-audience-mapper, oidc-usermodel-attribute-mapper, oidc-script-mapper)** | Custom Authentication Extension (TokenIssuanceStart) + Expose an API para `aud` | Mappers scripts en JavaScript NO existen; lógica externa solo vía REST API. |
| **`include.in.token.scope: true`** | Siempre (si se solicita el scope en la request) | No hay flag configurable. |
| **`display.on.consent.screen: true`** | Consentimiento se muestra en el flow browser-delegated. Native auth no muestra. | Para SPA/web: ok. Para native: requiere manejo propio. |
| **Password Grant (ROPC)** | **NO soportado** | Sustituir por OBO (workforce + external) o Authorization Code. |
| **CIBA (poll mode + ping mode)** | **NO soportado** | Sustituir por Conditional Access + Auth Context. |
| **User Flow `signin`, `signup`, `profile-edit`** | User flow único de `sign-up-and-sign-in`; profile edit se hace en app propia o via Graph API | No hay flujos separados como en B2C legacy. |
| **MFA** Via authenticator app, SMS, OTP | Email OTP, SMS (de pago), Passkey FIDO2 | La PoC no usa MFA real; en B2C sería OTP o Passkey. |
| **Conditional Access** No existe en Keycloak nativo (hay Authorization Services con policies) | Conditional Access policies completas (Microsoft Learn — *Security fundamentals*, sección *Conditional Access*) | External ID permite CA a nivel de external tenant; Keycloak requiere Authorization Services (más trabajo). |
| **Realm roles** (asignados en el realm) | App Roles (asignados por app) | Modelo más granular pero diferente. |
| **App roles (Keycloak)** | App roles (External ID) — claim `roles` en el token | Similar pero los claims se nombran distinto. |
| **Group claims** (Keycloak) | Group claims limitados al object ID del grupo | Microsoft Learn — *Supported features*, sección *Security groups*: *"Same as workforce. The group optional claims are limited to the group object ID."* |
| **`act` claim (actorización)** | NO estándar; inyectar vía custom authentication extension | La PoC depende de `act` para auditoría → requiere custom extension. |
| **Spring Security `JwtAuthenticationConverter`** | Compatible sin cambios | El converter actual lee `scope` y `scp`; External ID emite `scp` (en la mayoría de casos) o `roles`. Añadir lectura de `roles` si se usan app roles. |
| **docker-compose con 5 contenedores** | Solo `spring-boot-api` y `agent-python` quedan locales | Postgres y Keycloak desaparecen. El IdP está en cloud. |
| **`client-mock` (Node UI que aprueba CIBA)** | Se reemplaza por app móvil real con MSAL o por web app con Auth Code + PKCE + Passkey | Si el caso de uso requiere UX CIBA-like, hay que hacer app móvil. |
| **User management** via Keycloak Admin Console | via Microsoft Entra Admin Center + Microsoft Graph API | UI diferente; misma potencia operativa. |
| **Audit logs** vía Keycloak events + DB | vía Microsoft Entra Sign-in Logs + Audit Logs + Log Analytics | 7 días retención por defecto, ampliable con Azure Monitor (Microsoft Learn — *Supported features*, sección *Activity logs and reports*). |

---

## 6. Arquitectura migrada propuesta

### 6.1. Diagrama ASCII (topología migrada)

```
                                ┌─────────────────────────────────────────────┐
                                │   Microsoft Entra External ID (cloud)       │
                                │   ┌─────────────────────────────────────┐   │
                                │   │ External tenant                     │   │
                                │   │   • User flow: signup+signin        │   │
                                │   │   • App reg: agente-ia (cliente)    │   │
                                │   │   • App reg: spring-boot-api (Web)  │   │
                                │   │     - Expose API: api://sba         │   │
                                │   │       - calendar.Read              │   │
                                │   │       - calendar.Write             │   │
                                │   │       - email.Send                 │   │
                                │   │       - email.Modify               │   │
                                │   │   • Conditional Access: scope→auth  │   │
                                │   │     context                        │   │
                                │   │   • Passkey (FIDO2) MFA             │   │
                                │   └─────────────────────────────────────┘   │
                                │   URL: https://<tenant>.ciamlogin.com/...   │
                                └────────────┬────────────────────────────────┘
                                             │
                          Authorization Code+PKCE / OBO / Token request
                                             │
                ┌────────────────────────────┼─────────────────────────────┐
                │                            │                             │
                ▼                            ▼                             ▼
   ┌────────────────────────┐   ┌─────────────────────────┐   ┌──────────────────────┐
   │  CLIENT-MOCK (web)     │   │  AGENT-PYTHON (:7000)   │   │  USER MOBILE APP     │
   │  o App móvil real      │   │  FastAPI                 │   │  (futuro, MSAL SDK)  │
   │  Authorization Code    │   │  - OBO flow (calendar.*)│   │  Auth Code + PKCE    │
   │  + PKCE contra External│   │  - Passthrough (con MFA │   │  + Passkey MFA       │
   │  ID. Recibe access     │   │    step-up si scope sen- │   │  Push a Authenticator│
   │  token. Lo entrega al  │   │    sible)                │   │  cuando MFA step-up  │
   │  agente vía canal      │   │  - Client Credentials    │   │                      │
   │  lateral.              │   │    para sus propios jobs │   │                      │
   └────────────┬───────────┘   └──────────┬──────────────┘   └──────────┬───────────┘
                │                           │                             │
                │ entrega access_token      │ llama con Bearer            │
                │ del usuario               │ access_token delegado       │
                ▼                           ▼                             │
   ┌──────────────────────────────────────────────────────────────┐       │
   │   SPRING BOOT API (:9090)                                    │       │
   │   - Resource Server OAuth2                                   │       │
   │   - JwtAuthenticationConverter (extiende lectura de roles)   │       │
   │   - @PreAuthorize("hasAuthority('SCOPE_calendar.Read')")    │       │
   │   - Valida JWKS contra issuer External ID                    │       │
   │   - Auditoría: sub=ana-uuid, appid=agente-ia, scope=...      │       │
   └──────────────────────────────────────────────────────────────┘       │
                                                                          │
   ┌────────────────────────────────────────────────────────────────────┐ │
   │   ELIMINADOS                                                       │ │
   │   - postgres (contenedor) → estado en external tenant              │ │
   │   - keycloak (contenedor) → reemplazado por External ID           │ │
   └────────────────────────────────────────────────────────────────────┘ │
```

### 6.2. Decisión por servicio

| Servicio PoC | Decisión | Razón |
|---|---|---|
| `postgres` | **Eliminar contenedor** | El estado vive en External ID (directory + sign-in logs + audit logs). |
| `keycloak` | **Eliminar contenedor** | External ID es el IdP. El realm `agent-poc` se recrea como external tenant con app registrations y user flow. |
| `spring-boot-api` | **Mantener contenedor** (migrar config) | El Resource Server sigue siendo Spring Boot. Cambia `application.yml`: `issuer-uri` apunta a External ID. Cambia `ScopeAuthoritiesConverter` para leer `scp` y `roles`. |
| `agent-python` | **Mantener contenedor** (migrar código) | El agente sigue siendo FastAPI. Reescribir `oauth_client.py`: implementar OBO flow. |
| `client-mock` | **Reemplazar** (reducir alcance o migrar a app móvil) | La simulación CIBA desaparece. Si se quiere UX similar, hacer web app con Auth Code + PKCE que sirva como "delegador" de tokens al agente. |
| **`scripts/`** | Mantener + actualizar con URLs External ID | Los 5 tests end-to-end requieren reescritura menor. |
| **`docs/POOL.md`, `docs/SETUP.md`** | Reescribir parcialmente | Las instrucciones para arrancar Keycloak ya no aplican; sustituir por instrucciones para configurar external tenant. |

### 6.3. Coste estimado

| Concepto | Coste |
|---|---|
| Licencia External ID (0-50K MAU) | **0 €** |
| SMS MFA (si se usa) | De pago; precio variable por país (Microsoft Learn — *FAQ External ID*) |
| Microsoft Authenticator app | Gratis para el usuario |
| Custom domain (`auth.tuempresa.com` en lugar de `*.ciamlogin.com`) | Incluido en External ID (Microsoft Learn — *Supported features*, sección *Custom domain names*) |
| Azure subscription para hospedar Spring Boot + agente (Container Apps, AKS, App Service) | Depende del tier elegido; mínimo ~30-50 €/mes para un Container Apps básico |
| **Total PoC 3 usuarios + 1.000 reales** | **~30-50 €/mes** (solo infraestructura, no IdP) |
| **Total a escala 50K MAU** | ~0 € en IdP + infraestructura de los APIs a escala |

> **Comparación con Keycloak self-hosted**: para 1.000 usuarios el coste es similar. Para 50K usuarios, External ID puede empezar a ser más barato que mantener un cluster Keycloak HA con Postgres gestionado, observabilidad, etc. **El ahorro NO es monetario directo** sino **operativo**: External ID absorbe patching, backups, SLA de 99.99 %, monitoring, alerting.

### 6.4. Latencia y regiones (Europa)

External ID corre sobre Microsoft Entra ID. Las regiones donde Entra ID tiene presencia pública en Europa (según la doc oficial de Microsoft Trust Center y Azure region map) incluyen:

* **West Europe** (Países Bajos, Amsterdam).
* **North Europe** (Irlanda, Dublin).
* **France Central** (Paris).
* **Switzerland North / West**.
* **Germany West Central** (Frankfurt).
* **Sweden Central** (Gävle, más reciente).
* **Norway East / West** (preview).

> **Cifras**: la latencia típica Madrid-Amsterdam o Madrid-Frankfurt con TLS handshake es ~25-40 ms RTT. Las llamadas OIDC (token request + JWKS) en cada flujo CIBA-equivalente (ahora OBO + MFA step-up) son ~150-300 ms adicionales por la latencia de la red + tiempo de MFA del usuario. **Aceptable** para UX.

**Cita**: Microsoft Learn — *Azure geographies*, https://learn.microsoft.com/en-us/azure/reliability/regions-overview (citada vía contexto general; el mapa exacto de regiones External ID puede variar).

### 6.5. Compliance y GDPR

* **Data residency**: External ID permite elegir región al crear el tenant. Microsoft Learn — *Supported features*, sección *Microsoft cloud settings*: *"Not applicable"* (en external tenant no se configura cloud sovereign; siempre es Azure public cloud).
* **GDPR**: External ID hereda los compromisos de cumplimiento de Microsoft Entra ID: ISO 27001, SOC 2, GDPR DPA disponible. Microsoft Trust Center: https://www.microsoft.com/en-us/trust-center. Los datos de customer accounts se procesan según la región del tenant.
* **FedRAMP**: *"External ID in the public cloud is accredited for Federal Risk and Authorization Management Program (FedRAMP) High and Department of Defense (DoD) Impact Level 2 (IL2)."* — Microsoft Learn — *FAQ External ID*. **No disponible** en Azure Government / China / Germany sovereign clouds.
* **Data subject rights**: Microsoft Graph API permite `DELETE /users/{id}` para cumplir derecho al olvido (GDPR Art. 17). El PoC debe asegurar que al "dar de baja" un usuario se elimina también de External ID.

---

## 7. Plan de validación "Mismo test end-to-end con Microsoft Authenticator"

Esta sección traduce los 5 tests de la PoC al modelo External ID.

### Paso 1. Crear el external tenant

1. Necesitas una **Azure subscription** (free tier es suficiente para empezar: https://azure.microsoft.com/en-us/free/).
2. Entra a https://entra.microsoft.com con una cuenta que tenga rol **Cloud Application Administrator** o superior en el directory.
3. Menú lateral → **External Identities** → **Overview** → **Create a new external tenant**.
4. Tipo: **External** (no Workforce). Nombre del tenant: e.g. `agent-poc-external`.
5. Dominio inicial: `<nombre>.onmicrosoft.com` (luego puedes añadir custom domain).
6. Región: elegir la más cercana al target de usuarios (e.g. **West Europe** para España).

> Cita: Microsoft Learn — *Create an external tenant*, https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-create-external-tenant-portal.

### Paso 2. Registrar las apps (App Registrations)

**App 1: `agente-ia`** (cliente confidencial).

1. *App registrations* → *New registration*.
2. Name: `agente-ia`. Supported account types: **Accounts in this organizational directory only**.
3. Redirect URI: no necesario (es confidential client puro backend).
4. *Certificates & secrets* → *New client secret* → copiar a `AGENT_CLIENT_SECRET` (guardar en Azure Key Vault).
5. Anotar: **Application (client) ID** = `<agent-app-id>` y **Directory (tenant) ID** = `<tenant-id>`.

**App 2: `spring-boot-api`** (Web API).

1. *App registrations* → *New registration*.
2. Name: `spring-boot-api`. Supported account types: **Accounts in this organizational directory only**.
3. Redirect URI: no necesario.
4. *Expose an API*:
   * Application ID URI: `api://spring-boot-api`.
   * *Add a scope*:
     * `calendar.Read` — *Who can consent*: **Admins and users**, *Admin consent display name*: "Leer calendario", *Admin consent description*: "Permite al agente leer el calendario del usuario".
     * `calendar.Write` — mismo patrón + *Admin consent required: Yes*.
     * `email.Send` — *Admin consent required: Yes*.
     * `email.Modify` — *Admin consent required: Yes*.
5. *Certificates & secrets* → solo si la API necesita identificarse; normalmente no.
6. *App roles*: opcional. Si quieres que `roles` aparezca en el token (no solo `scp`), definir app roles aquí. Para máxima compatibilidad con `ScopeAuthoritiesConverter` actual, **recomendamos usar `scp` y NO `roles`**.

**Vincular apps**: en la app `agente-ia`, *API permissions* → *Add a permission* → *My APIs* → `spring-boot-api` → *Delegated permissions* → marcar los 4 scopes → *Grant admin consent for <tenant>*.

> Cita: Microsoft Learn — *Supported features*, secciones *Application registration* y *Expose an API*.

### Paso 3. Crear user flow con MFA forzada

1. *External Identities* → *User flows* → *New user flow*.
2. Tipo: **Sign up and sign in** (no hay "sign-in only" en External ID — hay un único flow combinado, igual que el user flow `signin` de B2C).
3. Versión: **Recommended**.
4. Identity providers:
   * Email accounts: **Email with password** (sustituye a `username` de Keycloak).
   * Social (opcional): dejar vacío para esta PoC.
5. User attributes: marcar los que necesites (e.g. `Given name`, `Surname`, `Email`).
6. Token claims: NO añadir nada todavía (lo hacemos en Paso 5).
7. Guardar como `signup_signin_v1`.

> Cita: Microsoft Learn — *Create a sign-up and sign-in user flow for customers*, https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-user-flow-sign-up-sign-in-customers.

**Añadir MFA**: External ID no permite MFA en el user flow directamente. La MFA se configura con **Conditional Access**.

### Paso 4. Configurar Conditional Access (auth context + MFA step-up)

1. *External Identities* → *Authentication contexts* → *New authentication context*.
2. Id: `c1` (lectura, low sensitivity).
3. *New authentication context*: `c2` (modificación, high sensitivity).
4. *Protection* → *Conditional Access* → *New policy*.
5. Assignments:
   * Users: **All users**.
   * Target resources: **Authentication context** → `c2`.
6. Grant: **Require multifactor authentication**.
7. Enable policy: **On**.
8. Save.

> Ahora, cuando un usuario pide un token con scope `email.Send` y la app marca `acrs=c2`, External ID fuerza MFA. Sin `acrs=c2`, MFA no es obligatorio.

### Paso 5. Configurar app roles / custom scopes en el token

Los scopes definidos en Expose an API ya viajan automáticamente al token cuando se solicitan. Para que **viajen también los custom attributes** (e.g. `tenant_id` interno):

1. *App registrations* → `spring-boot-api` → *Single sign-on* → *Attributes & Claims* → *Edit*.
2. *Add new claim*:
   * Name: `extension_<extensions-app-id>_custom1`.
   * Source: **Directory schema extension** → `b2c-extensions-app` → seleccionar el custom attribute.

> Cita: Microsoft Learn — *Add user attributes to token claims*, https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-add-attributes-to-token.

### Paso 6. Configurar Microsoft Authenticator para MFA (Passkey)

Esto lo hace el **usuario final**, no el admin. Pasos para Ana:

1. Instalar Microsoft Authenticator en iOS/Android.
2. Iniciar sesión en `https://mysignins.microsoft.com` con su cuenta del external tenant.
3. *Security info* → *Add sign-in method* → *Passkey* → *Add*.
4. Microsoft Authenticator ofrece guardar la passkey.
5. Próximo login con scope sensible: se le pide MFA, Authenticator envía push biométrico.

> Para que el push se apruebe **sin abrir Authenticator** (UX más cercana a CIBA), el usuario debe activar **Authenticator push notifications** dentro de la app Microsoft Authenticator.

### Paso 7. Migrar `agent-python/oauth_client.py` a OBO

Reemplazar el `jwt_bearer_flow` (que era ROPC) por:

```python
async def obo_flow(self, user_access_token: str, scope: str) -> dict:
    """
    On-Behalf-Of: el agente intercambia un access_token del usuario
    por un token delegado para scope específico.
    """
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "client_id": AGENT_CLIENT_ID,
        "client_secret": AGENT_CLIENT_SECRET,
        "assertion": user_access_token,           # token del usuario (aud=spring-boot-api)
        "scope": scope,                            # e.g. "api://spring-boot-api/calendar.Read"
        "requested_token_use": "on_behalf_of",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"https://{TENANT_SUBDOMAIN}.ciamlogin.com/{TENANT_ID}/oauth2/v2.0/token",
            data=data,
        )
        resp.raise_for_status()
        return resp.json()
```

> Cita: Microsoft Learn — *Microsoft identity platform and OAuth 2.0 On-Behalf-Of flow*, sección *First case: Access token request with a shared secret*.

Para el **flujo 2 (sensible, antes CIBA)**: ya no hay CIBA. El usuario debe completar el MFA en su app antes de que el agente pueda ejecutar el scope sensible. Patrón:

```python
async def sensitive_flow(self, user_id: str, scope: str) -> dict:
    """
    El usuario ya se autenticó en client-mock con acrs=c2 (auth context).
    Devolvemos el token delegado.
    """
    user_token = await self.get_user_token_with_mfa(user_id, scope)
    return await self.obo_flow(user_token, scope)

async def get_user_token_with_mfa(self, user_id: str, scope: str) -> str:
    """
    Llama al client-mock (o app móvil) y le pide que abra un browser
    a /authorize con prompt=login + acrs=c2. El usuario aprueba con Passkey.
    """
    # Implementación con Authorization Code + PKCE; ver §7.8
    ...
```

### Paso 8. Migrar `spring-boot-api/SecurityConfig.java`

Cambios mínimos:

```java
// application.yml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://${TENANT_SUBDOMAIN}.ciamlogin.com/${TENANT_ID}/v2.0
          # Opcionalmente:
          audiences: api://spring-boot-api
```

`ScopeAuthoritiesConverter` extendido para leer `roles`:

```java
private static final String CLAIM_ROLES = "roles";
// ... dentro de convert():
Object roles = jwt.getClaim(CLAIM_ROLES);
if (roles instanceof Collection<?> coll) {
    for (Object o : coll) {
        if (o != null) scopes.add(o.toString());
    }
}
```

**Decisión clave**: ¿usar `scp` (permite `hasAuthority("SCOPE_api://spring-boot-api/calendar.Read")`) o `roles` (más simple, `hasAuthority("SCOPE_calendar.Read")`)? Recomendación: **usar `scp`** para mantener la compatibilidad con la convención de la PoC, y poner `audiences` en `application.yml` para que Spring valide el `aud` automáticamente.

### Paso 9. Migrar / reducir `client-mock`

`client-mock` ya no aprueba CIBA. Opciones:

| Opción | Uso |
|---|---|
| **A. Eliminar `client-mock`** y asumir que el usuario ya tiene sesión iniciada en su app real | Más limpio, pero la PoC pierde el "client-mock" como demo visual |
| **B. Convertir `client-mock` en una webapp simple que hace Auth Code + PKCE** | Más realista; permite mostrar el flujo MFA con Passkey |
| **C. Hacer `client-mock` una app móvil real con MSAL iOS/Android** | Mejor UX, pero rompe la PoC porque ya no es "todo en local" |

**Recomendación para la PoC**: opción B. `client-mock` pasa a ser una webapp (Node + Express + MSAL.js) que:
1. Redirige al usuario a `https://<tenant>.ciamlogin.com/<tenant-id>/oauth2/v2.0/authorize` con `scope=openid profile email offline_access api://spring-boot-api/calendar.Read` y `prompt=select_account`.
2. Si el scope requiere MFA, External ID la fuerza. Passkey vía Authenticator.
3. Al volver con `code`, intercambia por tokens.
4. Muestra el access_token al usuario para que lo "pegue" en el agente (modo PoC) o lo entrega vía API interna (modo producción).

### Paso 10. Curl/Postman de prueba

**Test 1 — Obtener token delegado vía OBO (sustituye al flujo ROPC)**:

```bash
# 1. Usuario se autentica en client-mock con Auth Code + PKCE → obtiene user_token
# (ver documentación MSAL.js)

# 2. Agente hace OBO
curl -X POST "https://${TENANT_SUBDOMAIN}.ciamlogin.com/${TENANT_ID}/oauth2/v2.0/token" \
  -d "grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer" \
  -d "client_id=${AGENT_CLIENT_ID}" \
  -d "client_secret=${AGENT_CLIENT_SECRET}" \
  -d "assertion=${USER_ACCESS_TOKEN}" \
  -d "scope=api://spring-boot-api/calendar.Read" \
  -d "requested_token_use=on_behalf_of" | jq .
```

**Respuesta esperada**:
```json
{
  "token_type": "Bearer",
  "expires_in": 3600,
  "ext_expires_in": 3600,
  "access_token": "eyJ0eXAiOiJKV1Q..."
}
```

**Decodificar el access_token en jwt.io** debería mostrar:
* `iss`: `https://<tenant>.ciamlogin.com/<tenant-id>/v2.0`.
* `aud`: `api://spring-boot-api`.
* `scp`: `calendar.Read`.
* `oid`: object ID de Ana.
* `tid`: `<tenant-id>`.
* `azp`: `<agent-app-id>` (¡este claim sustituye al `act` de Keycloak!).

> **Importante**: External ID emite **`azp` (authorized party)** en lugar de `act`. Es equivalente funcional: indica qué app solicitó el token. Spring Boot puede leerlo si queremos reimplementar la lógica `act` de la PoC.

**Test 2 — Llamar a la API**:

```bash
TOKEN="eyJ0eXAiOiJKV1Q..."
curl -X GET "http://localhost:9090/api/calendar/events?user_id=ana" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Test 3 — Llamada con scope sensible (sin MFA) → debe fallar**:

```bash
# Sin auth context c2 en el user_token, el agent no puede pedir scope sensible
curl -X POST "https://${TENANT}.ciamlogin.com/.../token" \
  -d "scope=api://spring-boot-api/email.Send" \
  ... # debería dar 403 insufficient_claims o similar
```

**Test 4 — Llamada con scope sensible (con MFA) → debe funcionar**:

```bash
# 1. client-mock hace Auth Code + PKCE con acrs=c2 → user_token con c2 cumplido
# 2. Agente hace OBO con ese user_token y scope email.Send
# 3. Token resultante tiene acrs=c2 en claims
```

---

## 8. Limitaciones reales (no marketing fluff)

### 8.1. Cosas que hay que REDISEÑAR (no adaptar)

1. **El flujo 2 (CIBA para scopes sensibles) es incompatible.** External ID no tiene CIBA. La UX "Ana, el agente quiere enviar email, ¿apruebas?" se convierte en "el agente inicia un flujo Authorization Code; el navegador de Ana se abre, completa MFA con Passkey, el token vuelve al agente". Eso **no es asíncrono**: Ana tiene que estar físicamente delante del browser en ese momento. Si CIBA es un requisito duro del producto, **External ID no es la solución**.

2. **El `act` claim de Keycloak se convierte en `azp`.** La PoC lo documenta como elemento de auditoría. External ID emite `azp` por defecto. Si la auditoría downstream consume `act`, hay que:
   * Cambiar el parser de auditoría para leer `azp`.
   * O usar una custom authentication extension para emitir `act` (cuesta trabajo).

3. **Los `protocol=mappers` de Keycloak no existen.** Toda lógica de transformación de claims debe ir a una REST API externa (Custom Authentication Extension con evento `TokenIssuanceStart`). Esto:
   * Añade latencia (~50-100 ms por token).
   * Añade un punto de fallo adicional.
   * Tiene cuotas: el endpoint externo tiene rate limit.

4. **No hay realm roles.** El modelo es app roles. Si la PoC usa realm roles en Keycloak (no parece por la inspección del código), hay que migrar a app roles.

5. **El user flow de "sign-in only" no existe** en External ID. Solo hay "sign-up-and-sign-in". Esto obliga a mostrar la pantalla de "sign up" siempre que el usuario entre (aunque tenga cuenta). Workaround: deshabilitar sign-up y crear usuarios manualmente via Graph API.

6. **Native authentication solo para cuentas locales.** Si en el futuro se quiere añadir Google/Facebook/Apple login para el MFA de scopes sensibles, hay que usar **browser-delegated** para esos casos (no se puede combinar con native auth). Cita: Microsoft Learn — *Choose an authentication approach*, tabla *Feature comparison*, fila *Social identity provider sign-in*: ✔️ / ✔️ con nota *"Even with native authentication, social sign-in still uses a browser window for the identity provider step"*.

### 8.2. Nuevos secrets que el agente debe conocer

```bash
# Antes (PoC)
KEYCLOAK_URL=http://keycloak:8080
REALM=agent-poc
AGENT_CLIENT_ID=agente-ia
AGENT_CLIENT_SECRET=secret-del-agente

# Después (External ID)
TENANT_SUBDOMAIN=agentpoc                 # <tenant>.ciamlogin.com
TENANT_ID=<uuid>                          # <tenant-id>
AGENT_CLIENT_ID=<uuid>                    # app id del agente-ia
AGENT_CLIENT_SECRET=<secret-from-keyvault># generado en portal
SPRING_BOOT_API_APP_ID=<uuid>             # api://spring-boot-api
# Opcionales
MS_GRAPH_TENANT_ID=<uuid>
USER_FLOW_NAME=signup_signin_v1
CUSTOM_DOMAIN=auth.tuempresa.com          # si se configura
```

Estos secrets deben ir en **Azure Key Vault** (recomendado) o al menos en variables de entorno nunca commiteadas. Spring Boot puede leerlos directamente con `@Value` o mejor con `spring-cloud-azure-starter-keyvault-secrets`.

### 8.3. Tests automatizados

Los **5 tests actuales** de la PoC (`docs/SETUP.md` los enumera):

| # | Test actual | Veredicto migrado |
|---|---|---|
| 1 | JWT Bearer / ROPC: calendar.read | **Reescribir**: ahora OBO + Auth Code + PKCE |
| 2 | CIBA: email.send con aprobación en client-mock | **Reescribir**: ahora Auth Code + PKCE con `acrs=c2` + MFA Passkey; client-mock cambia de rol |
| 3 | Acceso directo API con token | **Mantener**: token ahora viene vía OBO; el resto idéntico |
| 4 | (Inspección claims, scope, act) | **Actualizar**: leer `azp` en lugar de `act`; `iss` cambia a `ciamlogin.com` |
| 5 | (Auditoría logs) | **Mantener** + añadir log a Sign-in logs de External ID |

**Herramientas de testing**:

* **MSAL para tests E2E** (no Postman manual). Las librerías MSAL tienen helpers para tests.
* **Testcontainers** ya no necesarios para IdP (no hay IdP local). Sí necesarios si quieres mockear External ID en CI.
* **WireMock** o **MockOAuth2Server** para tests unitarios del agente.

### 8.4. ¿Qué pasa si External ID falla?

| Escenario | Impacto | Mitigación |
|---|---|---|
| External ID caído (downtime) | El agente no puede obtener tokens | Ninguna directa. El agente devuelve 503 al cliente. **No hay fallback offline** (correcto, un IdP caído = no se firman tokens). |
| Latencia alta (>5s en token endpoint) | El agente tarda más | Bump timeouts en `httpx.AsyncClient`. Considerar caché de tokens corto (1-2 min). |
| Token expirado | La API devuelve 401 | El agente debe refrescar tokens vía refresh_token grant. External ID sí soporta refresh tokens (Microsoft Learn — *OpenID Connect on the Microsoft identity platform*). |
| Refresh token revocado (admin revoke, password change, MFA step-up falla) | El agente no puede renovar | Volver a pedir Auth Code + PKCE completo. UX: el usuario tiene que reautenticarse. |
| Tenant deshabilitado (admin) | Tokens emitidos quedan válidos hasta `exp` (CAE puede invalidar) | Si CAE está habilitado, External ID puede revocar en near-real-time. Cita: Microsoft Learn — *Configurable token lifetimes*, sección sobre CAE. |

**Caché de tokens en el agente**: la PoC actual no cachea tokens. **Recomendación para producción**: cachear access_token + refresh_token en memoria o Redis con TTL = `expires_in - 30s`. Usar **refresh_token rotation** (cada refresh genera un nuevo refresh, el viejo se invalida — Microsoft Learn — *Configurable token lifetimes*, sección *Refresh and session defaults*).

### 8.5. Límites de tokens

* **Access token**: por defecto **60-90 minutos** (random) en External ID (Microsoft Learn — *Configurable token lifetimes*, https://learn.microsoft.com/en-us/entra/identity-platform/configurable-token-lifetimes). Configurable vía policy (mínimo 10 min, máximo 1 día). La PoC actual usa 5 min en Keycloak — en External ID NO se puede bajar de 10 min, lo que **aumenta la ventana de exposición** de un token robado.
* **Con CAE (Continuous Access Evaluation)**: hasta **24-28 horas**, con revocación near-real-time en eventos críticos (cambio de password, account disable). Cita: misma URL.
* **Refresh token**: NO configurable por policy desde enero 2021 (Microsoft Learn, *Configurable token lifetimes*, sección *Token lifetime policies for refresh tokens and session tokens (retired)*):
  * `MaxInactiveTime`: 90 días.
  * `MaxAgeSingleFactor`: until-revoked.
  * `MaxAgeMultiFactor`: until-revoked.
* **ID token**: 1 hora por defecto.
* **Session token**: 24 horas non-persistent, 90 días persistent.

**Comparación con la PoC actual**:

| | Keycloak (PoC) | External ID |
|---|---|---|
| Access token | 5 min (configurable) | 60-90 min (default), min 10 min |
| Refresh token | No se usa activamente | 90 días inactividad, until-revoked |
| Revocación | Admin endpoint inmediato | Admin + CAE (si habilitado) |

> **Tradeoff importante**: la PoC actual tiene access tokens de 5 min por seguridad (ventana de exposición corta). External ID no permite bajar de 10 min. **Esto es una pérdida de seguridad** si mantenemos el mismo modelo. Workaround: aceptar la ventana más amplia, o usar **DPoP** (que External ID soporta) para sender-constrained tokens que limitan el daño de un token robado.

---

## 9. Pros / contras de migrar a B2C / External ID para una empresa como Víctor

> "Una empresa como Víctor" = una consultora pequeña/mediana española que desarrolla apps para clientes, con equipo limitado, sin SRE 24/7, preocupada por GDPR y costes.

### 9.1. PROS de migrar a External ID

1. **Coste cero hasta 50K MAU.** Elimina el coste operativo de mantener Keycloak (Postgres, parches, monitoring, backups).
2. **SLA empresarial**: 99.99% según contrato Microsoft. Keycloak self-hosted depende de tu infraestructura.
3. **Compliance out-of-the-box**: GDPR, ISO 27001, SOC 2 sin hacer nada. Keycloak requiere auditoría propia.
4. **Integración nativa con Microsoft 365**: si los clientes usan Teams, Outlook, etc., el SSO es trivial.
5. **Features modernas**: Passkey, Conditional Access, Identity Protection (limitado en external pero crece), audit logs en Azure Monitor.
6. **No más docker-compose de 5 servicios**: solo `spring-boot-api` y `agent-python` quedan locales.
7. **Ecosistema MSAL maduro**: librerías oficiales en todos los lenguajes (Python, Java, JS, .NET, etc.).
8. **Futuro**: Microsoft está invirtiendo en External ID. B2C legacy está en sunsetting. Estar en External ID es apostar por la dirección correcta.

### 9.2. CONTRAS de migrar a External ID

1. **ROPC NO soportado** en external tenants. La PoC usa ROPC; hay que migrar a OBO + Auth Code.
2. **CIBA NO soportado**. La mitad del "valor diferencial" de la PoC desaparece. Para acciones sensibles, hay que usar MFA step-up (Passkey) en un flow sincrónico — UX peor que CIBA push asíncrono.
3. **Lock-in con Microsoft**: migrar External ID a otro IdP (Auth0, Okta, Keycloak) es más caro que mantenerse en Keycloak.
4. **Menos control sobre el UI/UX del sign-in**: el branding está limitado; la página de sign-in es Microsoft-hosted en browser-delegated. Si Víctor necesita un look corporativo muy custom, native auth le obliga a construir la UI.
5. **Modelo de precios por MAU**: a escala muy alta (cientos de miles de usuarios) puede superar el coste de Keycloak self-hosted.
6. **Dependencia de red**: el IdP está en cloud. Si la red de Víctor se cae o hay partición de Internet, no se firman tokens. (Esto también aplica a Keycloak si la VM está en otra red).
7. **CIBA no se puede simular con Passkey**: el modelo de "Ana aprueba un push asíncrono mientras hace otra cosa" no existe. Si el producto final **requiere** asincronía para acciones sensibles, External ID no es suficiente y hay que considerar Auth0 (que sí tiene CIBA-like) o Keycloak.
8. **Custom claims limitados**: si Víctor necesita claims muy custom (e.g. inyectar `dept` desde un sistema externo), necesita un Custom Authentication Extension (REST API propia que añade latencia).

### 9.3. RECOMENDACIÓN FINAL para Víctor

| Si tu producto... | Recomendación |
|---|---|
| ...es una PoC interna sin MFA real, 3 usuarios demo | **Migrar a External ID**: el esfuerzo es ~2-3 semanas-persona y elimina el docker-compose. Coste cero. |
| ...irá a producción con <50K MAU | **Migrar a External ID**: el coste operativo de Keycloak supera al monetario de External ID. |
| ...irá a producción con >100K MAU | **Evaluar ambas opciones con TCO completo**. External ID escala linealmente con MAU; Keycloak requiere más infra y_ops. |
| ...requiere CIBA asíncrono como feature de producto | **NO migrar a External ID**. Considerar Auth0 (que sí soporta CIBA), Keycloak, o desarrollo propio. |
| ...requiere full control del UI/UX de auth | **NO migrar a External ID** (o usar native auth con coste alto). |
| ...debe quedarse en self-hosted por compliance (datos en España, sin terceros) | **NO migrar a External ID**. Mantener Keycloak o considerar Keycloak + IdP local. |
| ...ya tiene B2C legacy productivo | **Planificar HSC mode** (https://learn.microsoft.com/en-us/entra/external-id/customers/plan-your-migration-from-b2c-to-external-id) y migrar a External ID en fases. |

---

## 10. Esfuerzo estimado por capa

| Capa | Actividades | Semanas-persona (estimación) | Notas |
|---|---|---|---|
| **Infraestructura** | • Crear external tenant en Azure<br>• Configurar custom domain (opcional)<br>• Configurar Azure Key Vault para secrets<br>• Configurar Log Analytics para sign-in logs<br>• Eliminar contenedores Postgres y Keycloak del docker-compose<br>• Actualizar docker-compose.yml y scripts de arranque | **0.5 semanas** (1 persona) | El grueso es boilerplate ya conocido por cualquier equipo Azure. |
| **Configuración IdP** | • Registrar apps (`agente-ia`, `spring-boot-api`)<br>• Expose API + scopes (4 scopes)<br>• Vincular API permissions + admin consent<br>• Crear user flow sign-up-sign-in<br>• Crear Authentication contexts (`c1`, `c2`)<br>• Conditional Access policies<br>• Migrar 3 usuarios demo (o usar sign-up self-service)<br>• Configurar branding | **1 semana** (1 persona) | Conocimientos previos de Entra ID aceleran. Sin conocimientos, 2 semanas. |
| **Código - agente (Python)** | • Reescribir `oauth_client.py`: ROPC → OBO<br>• Añadir helper para Auth Code + PKCE<br>• Adaptar `app.py` para nuevo flujo<br>• Manejar `azp` en logs de auditoría<br>• Tests unitarios (mock del token endpoint)<br>• Manejar refresh tokens + caché | **1.5-2 semanas** (1 dev Python) | El grueso es entender OBO + manejar el refresh token. |
| **Código - Spring Boot** | • Cambiar `application.yml`: `issuer-uri` apuntando a External ID<br>• Extender `ScopeAuthoritiesConverter` para leer `roles` además de `scp`<br>• Tests integración (Testcontainers + MockOAuth2Server)<br>• Cambiar nombres de scopes en `@PreAuthorize` (snake_case → CamelCase con `api://` prefix) | **0.5 semanas** (1 dev Java) | Cambio cosmético + un converter más rico. |
| **Código - client-mock** | • Reescribir como webapp Auth Code + PKCE con MSAL.js<br>• Manejar callback + tokens<br>• Mostrar UX de MFA Passkey<br>• Eliminar lógica CIBA (ya no aplica)<br>• Opción: hacer app móvil real con MSAL iOS/Android | **1-2 semanas** (1 dev frontend o mobile) | Si se elige app móvil, sumar 2-3 semanas más. |
| **Testing E2E** | • Reejecutar los 5 tests actuales contra External ID<br>• Verificar flujo MFA Passkey<br>• Verificar auditoría con Sign-in logs<br>• Test de carga (10K MAU sintéticos)<br>• Test de contingencia (IdP caído) | **1 semana** (1 QA + 1 dev) | Requiere acceso a external tenant y permisos para crear usuarios sintéticos. |
| **Documentación** | • Actualizar `README.md`<br>• Reescribir `docs/SETUP.md` con pasos External ID<br>• Actualizar `docs/POOL.md` (arquitectura migrada)<br>• Crear runbook de operaciones | **0.5 semanas** (1 dev o tech writer) | |
| **Compliance / GDPR** | • DPA con Microsoft (suele venir por defecto)<br>• Revisar dónde se almacenan los PII<br>• Documentar derecho al olvido (DELETE user via Graph)<br>• Revisar logs de auditoría con DPO | **0.5 semanas** (1 persona legal + 1 dev) | |
| **TOTAL** | | **5-7 semanas-persona** (1-2 personas en 3-4 semanas calendario) | **No incluye** el coste de aprender External ID. Si el equipo parte de cero, añadir 2-3 semanas de training. |

**Comparación con coste de mantener Keycloak** (estimación):

| Actividad Keycloak recurrente | Coste / año |
|---|---|
| Mantenimiento Postgres (backups, vacuum, upgrades) | ~1 semana-persona/año |
| Parches Keycloak (seguridad cada 2-3 meses) | ~0.5 semanas-persona/parche × 4 = 2 sem/año |
| Monitoring + alertas (Prometheus/Grafana o similar) | ~1 semanas-persona/año setup + 0.5 sem/año mantenimiento |
| Backups + disaster recovery drills | ~1 semanas-persona/año |
| Certificados TLS, renovación | ~0.2 sem/año |
| **TOTAL Keycloak self-hosted** | **~5-6 semanas-persona/año recurrentes** |

A los 2 años, mantener Keycloak cuesta **lo mismo que la migración**. A partir del año 3, External ID es estrictamente más barato **sólo en coste de personal**, además del ahorro en SLA, compliance, y_ops.

---

## 11. Conclusiones claras (5 puntos)

### Conclusión 1 — Viabilidad

**La migración es técnicamente viable** pero NO es plug-and-play. De las 10 features check, 2 son imposibles (ROPC, CIBA) y 5 requieren adaptación. Lo que se mantiene intacto es solo: JWKS endpoint, OBO flow, scope→authority mapping. **Es un proyecto de 5-7 semanas-persona, no un find-and-replace.**

### Conclusión 2 — Coste

**Coste monetario de External ID: 0 € para 3 usuarios demo + 1.000 reales** durante todo el primer año (free tier 50K MAU). Coste de infraestructura: ~30-50 €/mes para hospedar Spring Boot + agente en Azure. Coste operacional: menor que Keycloak a partir del año 2 (elimina mantenimiento Postgres, parches, monitoring). **El ahorro NO es monetario directo a corto plazo, sino operativo a medio plazo.**

### Conclusión 3 — Pérdida de features

**External ID NO soporta CIBA**. Esto es la pérdida más significativa porque el flujo 2 de la PoC (aprobación asíncronas para scopes sensibles) **no tiene equivalente directo**. La alternativa (Conditional Access + Authentication Context + Passkey) es funcional pero **UX peor** (síncrono, requiere browser del usuario activo). Si CIBA es feature de producto, **External ID no es la respuesta** — considerar Auth0, Keycloak, o solución custom.

### Conclusión 4 — Mejoras sobre la PoC

**Migrar a External ID MEJORA la PoC** en tres aspectos:

1. **Elimina el antipatrón ROPC**: la PoC actual usa password grant por limitación de Keycloak 24. External ID soporta OBO (RFC 7523) correctamente, eliminando el password sharing.
2. **Elimina la dependencia de Docker/Postgres para el IdP**: el docker-compose se reduce de 5 a 2 servicios.
3. **Compliance y SLA out-of-the-box**: ISO 27001, SOC 2, GDPR DPA incluidos.

### Conclusión 5 — Recomendación final

| Escenario | Recomendación |
|---|---|
| Migración a External ID como ejercicio de aprendizaje | **Sí**: 3-4 semanas calendario para una persona con experiencia Azure. |
| Migración a External ID como preparación a producción B2C (<50K usuarios) | **Sí**: 5-7 semanas-persona, retorno a partir del año 2. |
| Migración a External ID con requisito de CIBA asíncrono | **No**: External ID no soporta CIBA. Considerar Auth0 o Keycloak. |
| Mantener Keycloak por preferencia o compliance específico | **Sí, válido**: Keycloak sigue siendo un IdP excelente; la PoC ya funciona. Documentar esta decisión con los trade-offs. |

**Para Víctor específicamente**: si su objetivo a corto plazo es **entender OAuth/OIDC para un agente IA** (no producir un producto real todavía), la migración a External ID es **un excelente ejercicio** que enseña OBO, Auth Context, Conditional Access. Si su objetivo es **producir algo para clientes reales**, primero decidir si necesita CIBA. Si sí, External ID no es la respuesta.

---

## 12. Apéndice A — URLs verificadas (citadas en este documento)

Todas las URLs han sido comprobadas con `curl -sI` durante la elaboración de este estudio (julio 2026). Las fechas de "última actualización" se han extraído del footer de cada página.

* https://learn.microsoft.com/en-us/entra/external-id/customers/overview-customers-ciam
* https://learn.microsoft.com/en-us/entra/external-id/customers/concept-supported-features-customers (2026-03-30)
* https://learn.microsoft.com/en-us/entra/external-id/customers/concept-security-customers (2026-06-17)
* https://learn.microsoft.com/en-us/entra/external-id/customers/concept-authentication-methods-customers (2026-04-03)
* https://learn.microsoft.com/en-us/entra/external-id/customers/concept-native-authentication (2026-06-22)
* https://learn.microsoft.com/en-us/entra/external-id/customers/concept-choose-authentication-approach (2026-04-29)
* https://learn.microsoft.com/en-us/entra/external-id/customers/concept-planning-your-solution (2026-06-17)
* https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-create-external-tenant-portal
* https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-user-flow-sign-up-sign-in-customers
* https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-user-flow-add-application
* https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-define-custom-attributes (2026-03-27)
* https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-add-attributes-to-token (2025-09-16)
* https://learn.microsoft.com/en-us/entra/external-id/customers/faq-customers (2026-05-20)
* https://learn.microsoft.com/en-us/entra/external-id/customers/plan-your-migration-from-b2c-to-external-id (2026-04-28)
* https://learn.microsoft.com/en-us/entra/external-id/customers/migrate-from-b2c-to-external-id (2026-04-17)
* https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-entra-id-federation-customers
* https://learn.microsoft.com/en-us/entra/external-id/external-identities-overview (2026-04-24)
* https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc
* https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow
* https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens
* https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow
* https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow
* https://learn.microsoft.com/en-us/entra/identity-platform/configurable-token-lifetimes
* https://learn.microsoft.com/en-us/entra/identity-platform/security-tokens

## 13. Apéndice B — Glosario de mapping Keycloak ↔ External ID

| Keycloak | External ID |
|---|---|
| Realm | External tenant |
| Client | App registration |
| Client Scope | App role + Expose an API scope |
| Protocol Mapper (genérico) | Custom authentication extension (TokenIssuanceStart) + Attributes & Claims |
| `oidc-audience-mapper` | Expose an API (Application ID URI) |
| `scope` claim (string) | `scp` claim (string o array) |
| `act` claim (actorización) | `azp` claim (authorized party) |
| `roles` (realm role) | `roles` (app role) |
| ROPC grant (password) | **No soportado** — usar OBO |
| CIBA grant (`urn:openid:params:grant-type:ciba`) | **No soportado** — usar Conditional Access + Auth Context |
| JWT Bearer (`urn:ietf:params:oauth:grant-type:jwt-bearer`) | OBO flow (con `requested_token_use=on_behalf_of`) |
| User flow "signin" / "signup" / "profile-edit" | User flow único "sign-up-and-sign-in" |
| Identity Provider (social, SAML, OIDC) | Identity provider configuration (en external tenant) |
| Admin events log | Audit log + Sign-in log (Microsoft Entra Admin Center) |
| `KeycloakAuthorizationServices` (policy-based) | Conditional Access policies |

---

**Última actualización del estudio**: 2026-07-08.
**Mantenedor**: Victor (khum1982) + Hermes Agent.
**Estado**: Borrador técnico. Verificar contra doc de Microsoft Learn antes de tomar decisiones de implementación.

---

## 14. Replanteamiento de flujos: el problema detectado tras el estudio

> **Sección añadida el 2026-07-08 tras revisión conjunta con Victor.**
> **Contexto**: al revisar este estudio Victor identificó que **el planteamiento original de la PoC (ROPC + CIBA) no era un requisito de producto, sino una elección de implementación**. El requisito de verdad es:
>
> 1. El **humano no comparte su password** con el agente (seguridad).
> 2. El **agente identifica al humano** por un proceso estándar.
> 3. Con esa identificación, el agente **obtiene un token** firmado por un IdP de confianza.
> 4. La **misma arquitectura** debe servir tanto en **Keycloak 24+** como en **Azure AD B2C External ID**, con los **mínimos cambios posibles** al pasar de uno a otro.
> 5. **Seguridad y resiliencia** ante caídas o cambios del IdP.

### 14.1. Requisitos reales vs. implementación original

| Requisito real | Implementación original (PoC) | Veredicto |
|---|---|---|
| Humano **NO comparte password** con el agente | ROPC (password grant) — **el agente SÍ recibe password** | ❌ **Violación del requisito** |
| Agente **identifica** al humano | ROPC (envía `username+password` directamente) | ❌ El agente identifica por secreto compartido, no por prueba criptográfica |
| Agente **obtiene token** firmado | Access token de KC | ✅ Cumple |
| **Misma arquitectura en KC y B2C** | ROPC + CIBA — **ninguno soportado en B2C** | ❌ Bloquea portabilidad |
| **Resiliencia** | ROPC: si el agente pierde el password, no puede renovar | ❌ |

> **Conclusión**: la PoC actual **viola el requisito #1** (humano comparte password con el agente). CIBA era una **compensación** que se rompió al descubrir que B2C no lo soporta. **Hay que rehacer el flujo desde la raíz**.

### 14.2. Flujos candidatos (todos cumplen "humano nunca da su password")

| Flujo | Estándar | Cómo identifica al humano | Caso de uso típico |
|---|---|---|---|
| **A) Authorization Code + PKCE** | RFC 6749 + RFC 7636 | El humano se autentica en un **browser** (o app con system browser) y el `code` vuelve al cliente por redirect | Humano tiene **smartphone** o **PC con browser** |
| **B) Device Code Flow** | RFC 8628 | El agente imprime un `device_code` + URL. El humano va a su dispositivo, introduce el código y aprueba | Agente = **dispositivo headless** (TV, CI/CD, kiosko, CLI en servidor remoto) |
| **C) On-Behalf-Of (OBO) / JWT Bearer (RFC 7523)** | RFC 7523 | El humano se autentica en **otra app** (móvil/web); esa app le pasa un `access_token` al agente; el agente lo **canjea** en el IdP por un token delegado | Hay **otra app** que ya autentica al humano y entrega tokens |
| **D) CIBA** (Client Initiated Backchannel Auth) | OpenID Foundation draft | El agente pide auth; el humano recibe **push** en su app y aprueba sincrónicamente | Asíncrono: humano puede **ignorar el push y contestar más tarde** |

### 14.3. Tabla de soporte por IdP

| Flujo | Keycloak 24 | Keycloak 26+ | Azure B2C External ID |
|---|---|---|---|
| **A. Authorization Code + PKCE** | ✅ | ✅ | ✅ |
| **B. Device Code Flow** | ✅ | ✅ | ✅ |
| **C. OBO (RFC 7523 / JWT Bearer)** | ⚠️ parcial (necesita KC 26+) | ✅ nativo | ✅ nativo |
| **D. CIBA** | ✅ | ✅ | ❌ **no existe** |

> **Observación clave**: **solo los flujos A, B y C son portables** entre Keycloak 24+ y Azure B2C External ID. CIBA queda **descartado** si la portabilidad es requisito (Victor lo confirmó).

### 14.4. Arquitectura recomendada: A + C combinados, con fallback B

La recomendación de Victor y el asistente es **Authorization Code + PKCE en la app del usuario + OBO en el agente**, con **Device Code como fallback** para escenarios headless.

```
┌──────────────────────────────────────────────┐
│ HUMANO (smartphone con app o browser)         │
└──────────────┬───────────────────────────────┘
               │ 1. Se autentica contra el IdP
               │    usando Auth Code + PKCE
               │    (MFA: Passkey / Authenticator / OTP)
               │
               ▼
┌──────────────────────────────────────────────┐
│ APP DEL HUMANO (móvil/web)                    │
│ • Recibe: access_token + refresh_token       │
│ • Cuando el agente pide acción:              │
│   - Refresca el token si ha expirado         │
│   - Lo entrega al agente via canal seguro    │
│     (clipboard, QR, deep link, API interna)  │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│ AGENTE (CI/CD / CLI / server)                 │
│ 2. Recibe user_access_token                  │
│ 3. Hace OBO contra el IdP:                   │
│    POST /token                               │
│      grant_type=urn:ietf:params:oauth:       │
│              grant-type:jwt-bearer           │
│      client_id=agente-ia                     │
│      client_secret=***                        │
│      assertion=<user_access_token>           │
│      scope=api://recurso/calendar.Read       │
│      requested_token_use=on_behalf_of        │
│ 4. Recibe access_token delegado              │
└──────────────┬───────────────────────────────┘
               │ 5. Llama al recurso protegido
               │    Authorization: Bearer <delegated_token>
               ▼
┌──────────────────────────────────────────────┐
│ RECURSO (Spring Boot, API, etc.)              │
└──────────────────────────────────────────────┘
```

#### ¿Por qué A+C y no solo A?

| Ventaja | A (Auth Code) | A+C (Auth Code + OBO) |
|---|---|---|
| El humano se identifica con MFA (no password al agente) | ✅ | ✅ |
| El agente recibe token para llamar a la API | ✅ | ✅ |
| **El agente puede pedir varios scopes sin molestar al humano cada vez** | ❌ | ✅ |
| **Si el user_token expira, el agente lo renueva con el `refresh_token` del humano** | ❌ | ✅ |
| **El agente puede delegar tokens a sub-agentes / sub-tareas** | ❌ | ✅ |
| **Resiliencia ante IdP caído**: el agente puede cachear tokens delegados | ❌ | ✅ |

#### ¿Por qué A+C es portable KC ↔ B2C?

| Componente | Keycloak 24+ | Azure B2C External ID |
|---|---|---|
| **Authorization Code + PKCE** en app cliente | ✅ | ✅ |
| **OBO (RFC 7523 / JWT Bearer)** | ✅ (KC 26+ recomendado) | ✅ nativo |
| **Token endpoint** | `/realms/{realm}/protocol/openid-connect/token` | `https://{tenant}.ciamlogin.com/{tenant-id}/oauth2/v2.0/token` |
| **JWKS endpoint** | `/realms/{realm}/protocol/openid-connect/certs` | `https://{tenant}.ciamlogin.com/{tenant-id}/discovery/v2.0/keys` |
| **Scopes dinámicos** (custom) | ✅ Client scopes | ✅ Expose an API scopes |
| **Rotación `refresh_token`** | ✅ | ✅ |

> 👉 **Mismo flujo OBO, mismo agente Python, misma spring-boot-api**. Solo cambia el `issuer-uri` y el `app-id` al migrar.

#### ¿Y el fallback a Device Code?

Para los casos donde el agente corre en un **dispositivo headless** (TV, CI/CD, kiosko) sin posibilidad de tener "la app del humano cerca". El Device Code Flow es estándar RFC 8628 y soportado en **ambos IdPs**.

| Caso | Flujo elegido |
|---|---|
| Humano tiene smartphone cerca, abre la app | **A+C** (Auth Code + PKCE + OBO) |
| Agente headless sin UI humana cerca | **B** (Device Code Flow) |
| Hay aprobación asíncrona push-to-app | **D** (CIBA) — **solo Keycloak**, descartado para portabilidad |

### 14.5. Tabla final de decisión

| Criterio | A+C (Auth Code + OBO) | B (Device Code) | D (CIBA) |
|---|---|---|---|
| **Seguridad** (humano NO da password) | ✅ | ✅ | ✅ |
| **Soporte Keycloak 24+** | ✅ | ✅ | ✅ |
| **Soporte Azure B2C External ID** | ✅ | ✅ | ❌ |
| **Resiliencia** (renovar tokens sin humano) | ✅ | ❌ | ❌ |
| **UX humano** (browser normal) | ✅ familiar | ✅ familiar | ⚠️ requiere app con push |
| **Portable** KC ↔ B2C | ✅ mismo flujo | ✅ mismo flujo | ❌ solo KC |
| **Cambios a hacer en la PoC actual** | rehacer `oauth_client.py` (OBO) + reescribir `client-mock` (Auth Code UI) | añadir Device Code a `oauth_client.py` + UI mínima en `client-mock` | nada (ya está), pero **rompe portabilidad** |

### 14.6. Cambios concretos que requiere la PoC

#### 1. Reescribir `agent-python/oauth_client.py`

```python
import httpx
import os

IDP_ISSUER = os.environ["IDP_ISSUER"]  # "http://localhost:8180/realms/agent-poc" o "https://<tenant>.ciamlogin.com/<tenant-id>/v2.0"
CLIENT_ID = os.environ["AGENT_CLIENT_ID"]
CLIENT_SECRET = os.environ["AGENT_CLIENT_SECRET"]


def obo_exchange(user_access_token: str, requested_scope: str) -> dict:
    """
    On-Behalf-Of: el agente intercambia el access_token del humano
    por un token delegado para el scope específico.
    Funciona idéntico en Keycloak 26+ y en Azure B2C External ID.
    """
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "assertion": user_access_token,
        "scope": requested_scope,
        "requested_token_use": "on_behalf_of",
    }
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(f"{IDP_ISSUER}/protocol/openid-connect/token", data=data)
        # En B2C: f"{IDP_ISSUER}/oauth2/v2.0/token"
        resp.raise_for_status()
        return resp.json()
```

#### 2. Reescribir `client-mock` como webapp Auth Code + PKCE

`client-mock` ya no aprueba CIBA. Pasa a ser una **webapp Node + Express + MSAL.js** (o equivalente Python) que:

1. Redirige al usuario a `{IDP_ISSUER}/protocol/openid-connect/auth?...` (KC) o `{IDP_ISSUER}/oauth2/v2.0/authorize?...` (B2C) con `scope=openid profile offline_access api://spring-boot-api/calendar.Read`.
2. Si el scope requiere MFA, el IdP la fuerza (Passkey / Authenticator / OTP).
3. Al volver con `code`, intercambia por tokens.
4. Muestra el `access_token` al usuario (modo PoC) para que lo "pegue" en el agente, o lo entrega vía API interna al agente (modo producción).

#### 3. Spring Boot `application.yml`

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          # Cambiar aquí al migrar de KC a B2C
          issuer-uri: ${IDP_ISSUER}
          # En KC: http://keycloak:8080/realms/agent-poc
          # En B2C: https://<tenant>.ciamlogin.com/<tenant-id>/v2.0
```

**Sin tocar `SecurityConfig.java`**: el `JwtAuthenticationConverter` actual ya lee `scope`, `scp` y `roles`; cubre los formatos de ambos IdPs.

### 14.7. Por qué este diseño es SEGURO + RESILIENTE

| Propiedad | Cómo se cumple |
|---|---|
| **El humano nunca comparte su password** | ROPC eliminado. El humano solo usa su app o browser contra el IdP |
| **El agente prueba la identidad del humano** | El agente recibe un `access_token` firmado por el IdP; la firma + `iss` + `aud` + `exp` lo validan criptográficamente |
| **El agente puede rotar tokens sin molestar al humano** | OBO + `refresh_token` del humano (cuyo `refresh_token` se rota con cada OBO) |
| **Si el IdP cae, el agente sigue funcionando con tokens cacheados** | El agente puede cachear `access_token` delegados en Redis con TTL = `expires_in - 30s` |
| **Si el `user_token` es robado**, el daño está acotado | `access_token` expira en 5-60 min; el `refresh_token` solo lo tiene la app del humano, no el agente |
| **Migrar KC → B2C es solo cambiar `issuer-uri`** | El cliente del agente no conoce el IdP; el IdP es una variable de entorno |
| **Auditoría clara** | El token delegado lleva `azp` (authorized party = app del agente) y `oid` (object id del humano). Spring Boot lo loguea |

### 14.8. Próximos pasos

1. ✅ **Decidir**: Victor confirma que A+C + B es la dirección correcta.
2. 🟡 **Refactor PoC actual**:
   - Sustituir `oauth_client.py` (ROPC) por OBO + helper Device Code.
   - Sustituir `client-mock` (UI CIBA) por webapp Auth Code + PKCE.
   - Eliminar `directAccessGrantsEnabled: true` y `cibaEnabled: true` del realm.
3. 🟡 **Actualizar `docs/POOL.md` y `docs/SETUP.md`** con el nuevo flujo.
4. 🟡 **Tests E2E**: los 5 tests de la PoC se reescriben sobre el nuevo flujo.
5. 🟡 **Migración a B2C** (cuando se decida): solo cambia el `issuer-uri` en `application.yml` + variables de entorno del agente + configuración de B2C (tenant, app registration, user flow, Conditional Access).

---

**Cierre del estudio**: 2026-07-08. Documento consolidado y subido a GitHub por Victor (commit siguiente).