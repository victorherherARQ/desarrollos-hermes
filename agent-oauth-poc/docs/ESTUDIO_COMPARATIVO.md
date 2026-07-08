# Estudio comparativo de patrones OAuth/OIDC para un Agente IA con delegación de identidad

> **Versión**: 1.0 — julio 2026
> **Autor**: Víctor Hdez (khum1982) + Hermes (subagente de documentación)
> **Estado**: análisis profundo (opción B) — complementario al PoC `agent-oauth-poc`
> **Audiencia**: Víctor. Es un documento interno, no marketing. Se puede ser directo.

---

## Tabla de contenidos

1. [Contexto del problema](#1-contexto-del-problema)
2. [Criterios de evaluación y matriz ponderada](#2-criterios-de-evaluación-y-matriz-ponderada)
3. [Las siete opciones analizadas](#3-las-siete-opciones-analizadas)
   - [Opción A — ROPC (RFC 6749 §4.3)](#opción-a--ropc-resource-owner-password-credentials)
   - [Opción B — JWT Bearer (RFC 7523)](#opción-b--jwt-bearer-authorization-grant-rfc-7523)
   - [Opción C — Token Exchange (RFC 8693)](#opción-c--token-exchange-rfc-8693)
   - [Opción D — OIDC CIBA](#opción-d--oidc-ciba-client-initiated-backchannel-authentication)
   - [Opción E — Authorization Code + PKCE + refresh tokens largos](#opción-e--authorization-code--pkce--refresh-tokens-largos)
   - [Opción F — FAPI 2.0 (Financial-grade API)](#opción-f--fapi-20-financial-grade-api)
   - [Opción G — mTLS + service-to-service custom](#opción-g--mtls--service-to-service-custom)
4. [Tabla comparativa final con totales ponderados](#4-tabla-comparativa-final-con-totales-ponderados)
5. [Recomendación por horizonte temporal](#5-recomendación-por-horizonte-temporal)
6. [Notas sobre Apigee + Spring Boot en producción](#6-notas-sobre-apigee--spring-boot-en-producción)
7. [Notas sobre quirks de Keycloak 24/26](#7-notas-sobre-quirks-de-keycloak-2426)
8. [Bibliografía y RFCs citados](#8-bibliografía-y-rfcs-citados)
9. [Apéndice A — Glosario y siglas](#apéndice-a--glosario-y-siglas)
10. [Apéndice B — Historial de revisiones](#apéndice-b--historial-de-revisiones)

---

## 1. Contexto del problema

### 1.1. Enunciado literal

Tenemos un **agente de IA** (LLM servido como backend HTTP) que recibe peticiones en
lenguaje natural desde una **app móvil** operada por un **usuario real** (Ana, Luis,
Marta). El agente necesita ejecutar acciones que tocan **APIs externas de negocio**
implementadas en **Spring Boot** y expuestas tras un **API gateway Apigee**. Las APIs
son sensibles (pagos, email, calendario, datos personales).

El agente NO es un usuario humano: es software que **opera en nombre del usuario**.
Por tanto, las preguntas de diseño son:

- ¿Cómo identifica el agente al usuario que le habla?
- ¿Con qué credencial actúa frente al IdP?
- ¿Qué API llama el agente para conseguir un access_token válido para la API de negocio?
- ¿Cómo sabe Apigee (y la API Spring Boot) que ese access_token fue emitido a través
  del agente pero que **el sujeto real es Ana**?
- ¿Qué pasa si el agente se compromete? ¿Y si el IdP se cae?
- ¿Cuándo necesita el usuario **aprobar en el momento** una acción y cuándo basta con
  un consentimiento persistente?

### 1.2. Diagrama de actores (ASCII)

```
                              ┌─────────────────────┐
                              │   USUARIO REAL      │
                              │   (Ana, Luis, Marta)│
                              │   App móvil nativa  │
                              └──────────┬──────────┘
                                         │
                              prompt en lenguaje natural
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │   AGENTE IA         │
                              │   (LLM backend,     │
                              │    FastAPI/Python)  │
                              └──────────┬──────────┘
                                         │
                          ┌──────────────┼──────────────────┐
                          │              │                  │
                  (a) prompt           (b) token          (c) bearer token
                          │              │                  │
                          ▼              ▼                  ▼
                 ┌────────────┐  ┌──────────────┐  ┌──────────────────┐
                 │  Cliente   │  │  IDP / AS    │  │  API SPRING BOOT │
                 │  CIBA      │  │  (Keycloak/  │  │  (recurso)       │
                 │  (móvil o  │  │  Auth0/Okta/ │  │                  │
                 │  web)      │  │  Azure AD)   │  │                  │
                 └─────┬──────┘  └──────┬───────┘  └────────┬─────────┘
                       │  approve       │                   │
                       └───────────────▶│                   │
                                      │                   │
                                      │  access_token     │
                                      └──────────────────▶│
                                                          │
                                                          ▼
                                                 ┌──────────────────┐
                                                 │   APIGEE         │
                                                 │  (gateway)       │
                                                 │  VerifyJWT / API │
                                                 │  Key policies    │
                                                 └──────────────────┘
```

**Relaciones clave**:

- **(a)** El usuario habla al agente en lenguaje natural. Esto es **out-of-band** para
  OAuth: la autenticación del usuario frente al agente es ortogonal al flujo OAuth.
  El agente recibe una identidad "asumida" o verificada por la app (p.ej. JWT firmado
  por el móvil con la sesión del usuario, mTLS con device-cert, o simple
  `user_id` en un canal autenticado por sesión). En el PoC asumimos **el más simple**:
  el `user_id` viene en el body porque la app es de confianza (mock). En producción,
  la app móvil se autentica con token del usuario frente al agente.
- **(b)** El agente, ya identificado el usuario, **obtiene un access_token del IdP**
  en nombre de ese usuario. Esta es la parte central del estudio.
- **(c)** El agente llama a la API Spring Boot con el access_token. Apigee (en
  producción real) y/o Spring Security validan el JWT contra el issuer del IdP.

### 1.3. Por qué esto no es trivial

A primera vista parece "haz un `client_credentials` y listo". Pero no. Si el agente
usa `client_credentials` puro (RFC 6749 §4.4), el `sub` del token es **el propio
agente**, no el usuario. La API de Spring Boot verá que "agente-ia hizo GET
/calendar/events" sin saber **para quién**. La pista de auditoría `sub=ana, act=agente-ia`
no existe.

Necesitamos **delegación de identidad**: el token que llega a la API Spring Boot
tiene que decir "Ana autorizó al agente-ia a hacer esto". Eso obliga a flujos
que porten `sub` o `act` correctamente. De aquí el rango de opciones que
estudiamos.

### 1.4. Restricciones del entorno concreto

| Restricción | Detalle |
|---|---|
| IdP actual | Keycloak 24.0 (con plan de subir a 26.x en 2026 H2). |
| IdPs futuros posibles | Auth0, Okta, Azure AD/Entra ID. |
| API Gateway | Apigee (con `VerifyJWT` y `VerifyAPIKey`). |
| API de negocio | Spring Boot 3.2 + Spring Security 6 (resource server JWT). |
| Cliente "humano" del agente | App móvil (en PoC: web mock `client-mock`). |
| Naturaleza de las acciones | Mezcla de rutinarias (lecturas) y sensibles (escrituras/pagos). |
| Latencia tolerable | Asíncrona para sensibles (decenas de segundos); síncrona para rutinarias (<3s). |
| Auditoría | Obligatoria. Claim `sub` real + claim `act` (agente) requerido. |
| Caída del IdP | Aceptable con degradación controlada: si cae, no se deben emitir tokens nuevos. |

---

## 2. Criterios de evaluación y matriz ponderada

### 2.1. Los seis criterios

| # | Criterio | Qué pregunta responde | Peso |
|---|---|---|---|
| C1 | **Seguridad** | ¿Cuál es la fuerza criptográfica y de modelo de amenaza? ¿Soporta MFA/consent explícito? ¿Qué pasa si el agente se compromete? | 30 |
| C2 | **Madurez del estándar** | ¿RFC cerrado y estable? ¿Cuántos años en producción? ¿Cuántas implementaciones interoperables? | 15 |
| C3 | **UX / fricción** | ¿Cuántas pantallas/acciones para el usuario final por cada llamada de API? | 15 |
| C4 | **Complejidad de implementación** | Semanas-persona estimadas para un equipo medio (2 backend + 1 frontend + 0.5 SRE). Incluye servidor, agente, SDKs, tests. | 15 |
| C5 | **Compatibilidad Apigee + Spring Boot + IdP** | ¿Funciona out-of-the-box con el stack actual? ¿Cuánto hay que pelearse con quirks? | 15 |
| C6 | **Soporte offline / resiliencia ante caída del IdP** | ¿Qué pasa si el IdP cae 30 minutos? ¿Se puede degradar a un modo seguro? | 10 |

**Suma de pesos: 100.** El peso de C1 (Seguridad) es deliberadamente dominante porque
estamos hablando de APIs que tocan datos personales y pagos. Un atajo en seguridad
tiene coste multiplicativo en producción.

### 2.2. Escala de puntuación (1-5)

- **1** = Inaceptable: o no cumple el criterio o el cumplimiento es contraproducente.
- **2** = Deficiente: cumple pero con caveats serios. No apto para producción sin workaround pesado.
- **3** = Aceptable: cumple con el mínimo razonable. Apto para PoC o nicho.
- **4** = Bueno: cumple bien, con caveats menores conocidos.
- **5** = Excelente: estado del arte, sin caveats relevantes en nuestro contexto.

### 2.3. Cálculo del score ponderado

Para cada opción X:
```
score(X) = Σ_i (peso_i × puntuacion_i(X)) / Σ_i peso_i
```
Da un valor entre 1.00 y 5.00. El ranking es por score descendente.

**Nota metodológica**: las puntuaciones son **juicio técnico cualitativo** del autor,
no medidas. Los criterios 2.2 y 2.3 son la rúbrica. Si Víctor no está de acuerdo con
alguna puntuación, el método permite reasignar y recalcular; el resto del análisis
sigue siendo válido.

---

## 3. Las siete opciones analizadas

### Opción A — ROPC (Resource Owner Password Credentials)

#### A.1. Definición

Grant definido en **RFC 6749 §4.3**. El cliente envía directamente `username` y
`password` del usuario al endpoint `/token` del authorization server, junto con
su propio `client_id`/`client_secret` (cliente confidencial). El AS devuelve un
access_token (y opcionalmente refresh_token) cuyo `sub` es el usuario.

**Perfil OAuth 2.0**: el cliente es "confidential" (conoce secretos), pero el
usuario se autentica con credencial directa. Es el único grant de OAuth 2.0
donde la credencial del usuario atraviesa el cliente.

#### A.2. Diagrama de flujo

```
       Usuario              Agente IA              Keycloak               Spring Boot API
          │                    │                       │                       │
          │  1. lanza agente  │                       │                       │
          │  con sus          │                       │                       │
          │  credenciales     │                       │                       │
          │ ─────────────────▶│                       │                       │
          │                    │                       │                       │
          │                    │  2. POST /token       │                       │
          │                    │  grant_type=password  │                       │
          │                    │  username=ana         │                       │
          │                    │  password=demo1234    │                       │
          │                    │  client_id=agente-ia  │                       │
          │                    │  client_secret=***    │                       │
          │                    │  scope=calendar.read  │                       │
          │                    │ ────────────────────▶ │                       │
          │                    │                       │                       │
          │                    │                       │  (valida user/pass,   │
          │                    │                       │   valida client,      │
          │                    │                       │   genera JWT con      │
          │                    │                       │   sub=ana,            │
          │                    │                       │   aud=spring-boot,    │
          │                    │                       │   scope=calendar.read)│
          │                    │                       │                       │
          │                    │  3. 200 OK            │                       │
          │                    │  access_token=eyJ...  │                       │
          │                    │  refresh_token=...    │                       │
          │                    │  expires_in=300       │                       │
          │                    │ ◀──────────────────── │                       │
          │                    │                       │                       │
          │                    │  4. GET /api/calendar/events                  │
          │                    │  Authorization: Bearer ***                       │
          │                    │ ───────────────────────────────────────────────▶│
          │                    │                       │                       │
          │                    │                       │                       │  5. (Apigee VerifyJWT
          │                    │                       │                       │      → Spring resource
          │                    │                       │                       │      server valida firma
          │                    │                       │                       │      y claims)
          │                    │                       │                       │
          │                    │  6. 200 OK events     │                       │
          │                    │ ◀──────────────────────────────────────────────│
          │                    │                       │                       │
```

#### A.3. Ajuste a nuestro caso

**Bueno para PoC, problemático para producción**. ROPC funciona porque:

1. Keycloak 24 lo trae **habilitado por defecto** (a diferencia de `jwt-bearer`,
   que hay que activarlo explícitamente — ver §7).
2. El PoC usa `agente-ia` como cliente confidencial con `Direct Access Grants`
   habilitado en su configuración, y el password del usuario vive en una "tabla"
   de `config.py` (en el PoC). En producción sería contra un IdP federado
   (LDAP/AD/Okta).
3. El `sub` del token es Ana. El claim `act` no se emite por defecto en
   Keycloak 24 con ROPC puro — para tener `act` hay que añadir un *protocol
   mapper* o usar la variante `act` mediante `client-credentials` con ROPC
   anidado (no estándar, antipatrón). Ver §7.

**Donde casca**:
- Si el agente se compromete, **tiene los passwords en memoria** (o puede pedirlos
  al usuario cada vez). Es exactamente lo que OAuth 2.0 quiso evitar.
- No hay forma nativa de hacer **step-up MFA por scope**. Cualquier MFA es en el
  momento del login, no por acción.
- **OAuth 2.1** marca ROPC como **deprecado** para clientes públicos y lo elimina
  del perfil general. Solo se permite en migración de legacy con justificación
  documentada (ver IETF draft `draft-ietf-oauth-v2-1`).

#### A.4. Pros

- **P3-1**: Implementación trivial. 15 líneas de código en `httpx`. El SDK
  `python-keycloak` lo hace en una llamada.
- **P3-2**: Funciona contra **cualquier** IdP OAuth/OIDC sin особенностей. Es
  la "lingua franca" de los grants viejos.
- **P3-3**: Sin redirecciones, sin browser, sin device flow, sin push. El agente
  puede actuar en background sin que el móvil esté en foreground.

#### A.5. Contras

- **C3-1**: El agente maneja el password del usuario. **Si el agente se compromete,
  el atacante tiene todas las credenciales** del usuario para reentrar a cualquier
  otro sistema donde use la misma password (credential stuffing). Contrarréstate con
  flujo por-token, donde comprometer el agente solo da tokens de 5 minutos.
- **C3-2**: No hay forma estándar de capturar `act` (agente) en el token sin
  *mapper* custom en Keycloak. La auditoría se queda en `sub=ana, aud=...` sin
  trazabilidad explícita del agente.
- **C3-3**: Si el IdP cae, el agente no puede pedir tokens nuevos (no hay cache
  posible porque el password no es un bearer). **No hay modo offline seguro**.
  Sólo queda degradar a denegación total.
- **C3-4**: OAuth 2.1 (y la comunidad) lo desaconsejan activamente. Adopción
  decreciente. Auth0 y Okta muestran warnings en consola al usarlo.

#### A.6. Variantes de implementación

- **Keycloak 24/26**: marcar *Direct Access Grants Enabled* en el cliente
  `agente-ia`. En realm importado viene ON. Para producción: dejar OFF y
  documentar excepción.
- **Auth0**: soportado pero con warning "Password Grant is not recommended".
  Hay que pasar el header `Auth0-Client: ...` con telemetría de la SDK.
- **Azure AD/Entra ID**: soportado en legacy (v1.0 endpoint) pero **no en v2.0**.
  En la práctica, para Entra ID, ROPC no es opción salvo migración legacy.

#### A.7. Caso de uso ideal

Migración de un sistema legacy que ya comparte passwords (p.ej. un CRM viejo
con autenticación básica). O como en nuestro PoC: cuando quieres validar el
concepto end-to-end sin pelearte con quirks del IdP.

#### A.8. Score por criterio

| Criterio | Puntuación | Justificación |
|---|---|---|
| C1 Seguridad | **1** | Comparte password. Sin `act` nativo. Sin step-up. |
| C2 Madurez | **3** | RFC estable desde 2012, pero la comunidad lo desaconseja. |
| C3 UX | **5** | Una sola llamada, sin redirección ni push. |
| C4 Implementación | **5** | 0.1 semanas-persona. |
| C5 Compatibilidad | **5** | Funciona con todo el stack. |
| C6 Resiliencia | **2** | Cero cache de credenciales posible. |
| **Score ponderado** | **3.05** | |

#### A.9. Estimación de esfuerzo

- Setup inicial (cliente, scopes, mapper): **0.1 semanas-persona**.
- Hardening (logs, métricas, MFA gate, redacción de password en logs): **+0.5**.
- Migración a producción con vault de secretos: **+1**.
- Total realista: **0.6–1.6 semanas-persona** si no se hace el "camino feliz".

#### A.10. Referencias

- **RFC 6749 §4.3** — *Resource Owner Password Credentials Grant*.
- **RFC 6749 §10.7** — *"Because the client must handle the resource owner's
  credentials, this grant type should not be used in production deployments."*
- **draft-ietf-oauth-v2-1** — *OAuth 2.1*: elimina ROPC del perfil general.
- **Auth0 docs**: *Password Grant* — marcado deprecated.
- **Keycloak docs**: *Direct access grant* — habilitado por defecto, recomendado
  OFF en producción.

---

### Opción B — JWT Bearer (RFC 7523)

#### B.1. Definición

Grant definido en **RFC 7521** (framework general de *assertion-based
authorization*) y especializado en **RFC 7523 §2.1** para *JWTs como
authorization grant*. El cliente construye una **assertion JWT firmada**
(`user_assertion`) que lleva `sub=<user_id>`, `iss=<client_id>`,
`aud=<token_endpoint>`, `exp=...`. Esa assertion se envía al endpoint
`/token` con `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`.

**No se envía password**. La aserción está firmada por el cliente confidencial
usando su `client_secret` (perfil `client_secret_jwt`, OIDC Core §9) o un
par de claves asimétricas (`private_key_jwt`, OIDC Core §9).

#### B.2. Diagrama de flujo

```
       Usuario              Agente IA              Keycloak               Spring Boot API
          │                    │                       │                       │
          │  1. prompt        │                       │                       │
          │ ─────────────────▶│                       │                       │
          │                    │                       │                       │
          │                    │  2. crea user_assertion JWT                    │
          │                    │     header: { alg: HS256,                     │
          │                    │              typ: JWT,                        │
          │                    │              kid: "agente-ia-1" }             │
          │                    │     payload: {                                │
          │                    │       iss: "agente-ia",                       │
          │                    │       sub: "ana",                             │
          │                    │       aud: "http://kc/.../token",            │
          │                    │       iat: now, exp: now+300 }               │
          │                    │     firma: HS256(client_secret)               │
          │                    │                       │                       │
          │                    │  3. POST /token       │                       │
          │                    │  grant_type=urn:ietf:params:oauth:           │
          │                    │              grant-type:jwt-bearer           │
          │                    │  assertion=eyJ...     │                       │
          │                    │  client_id=agente-ia  │                       │
          │                    │  client_secret=***    │                       │
          │                    │  scope=calendar.read  │                       │
          │                    │ ────────────────────▶ │                       │
          │                    │                       │                       │
          │                    │                       │  (valida firma,      │
          │                    │                       │   valida iss, sub,   │
          │                    │                       │   exp; consulta      │
          │                    │                       │   consentimiento     │
          │                    │                       │   previo del         │
          │                    │                       │   usuario para       │
          │                    │                       │   cliente agente-ia  │
          │                    │                       │   sobre ese scope)   │
          │                    │                       │                       │
          │                    │  4. 200 OK            │                       │
          │                    │  access_token=eyJ...  │                       │
          │                    │  (sub=ana,            │                       │
          │                    │   aud=spring-boot,    │                       │
          │                    │   scope=calendar.read,│                       │
          │                    │   opcional: act={     │                       │
          │                    │     sub:agente-ia})   │                       │
          │                    │ ◀──────────────────── │                       │
          │                    │                       │                       │
          │                    │  5. GET /api/calendar/events                  │
          │                    │  Authorization: Bearer ***                       │
          │                    │ ───────────────────────────────────────────────▶│
          │                    │                       │                       │
```

#### B.3. Ajuste a nuestro caso

**Excelente para el "lado rutinario"**. El scope `calendar.read` no necesita
aprobación en tiempo real: el usuario en algún momento aceptó que el agente
puede leer su calendario. RFC 7523 permite ese modelo: la "autorización" está
**pre-concedida** y la assertion sirve solo para que el AS pueda comprobar que
el agente está autorizado a actuar por ese usuario.

**Donde casca**:
- RFC 7523 por sí solo **no incluye al usuario en el momento de la acción**.
  Es válido para operaciones que el usuario ya consintió de antemano
  (offline consent). Para acciones sensibles se necesita combinarlo con
  CIBA (Opción D) o reemplazarlo por Token Exchange (Opción C) con `act`.
- **Keycloak 24 no trae habilitado este grant por defecto** (hay que marcar
  *Allow JWT bearer* en el *Client capabilities* del realm o usar
  `--features=preview` / `--features=token-exchange`). Ver §7.

#### B.4. Pros

- **P3-1**: Sin password del usuario en circulación. El agente firma con su
  propio secreto. Si el agente se compromete, el atacante tiene acceso a un
  bearer de 5 minutos, no a las credenciales del usuario.
- **P3-2**: El claim `act` (actor) es trivial de emitir si configuras el
  *protocol mapper* adecuado en Keycloak (ver §7), dando auditoría completa
  `sub=ana, act={sub:agente-ia}`.
- **P3-3**: Estandarizado y soportado nativamente por Auth0, Okta, Azure AD
  y Keycloak 26+. Madurez probada en escenarios enterprise.
- **P3-4**: Compatible con `private_key_jwt` (asimétrico). Permite rotación
  de claves sin redeploy del AS.

#### B.5. Contras

- **C3-1**: **Keycloak 24 no lo trae por defecto**. Hay que habilitarlo y, en
  versiones <26, hay un bug conocido con el endpoint de default-client-scopes
  (ver §7). El setup inicial es de 0.5 semanas-persona solo para eso.
- **C3-2**: **No hay human-in-the-loop por acción**. Si Ana no quiere que el
  agente lea su calendario a las 03:00 AM de un domingo, no hay forma de
  bloquearlo sin revocar el consentimiento offline. Solución: combinar con
  CIBA para scopes sensibles.
- **C3-3**: El `sub` de la assertion debe ser el **identificador interno** del
  usuario en el IdP (no el email). Mapeo `user_id` → `sub` hay que mantenerlo.
  Si cambia el `sub` (p.ej. tras migración de realm), todas las assertions
  rompen.
- **C3-4**: El agente necesita conocer el `user_id` de Ana. Eso significa
  que el móvil debe haber enviado ese dato al agente en algún momento. La
  autenticación móvil→agente es ortogonal y hay que diseñarla aparte.

#### B.6. Variantes de implementación

- **Keycloak 24**: requiere feature `token-exchange` o `preview`. Hay que
  habilitarlo en realm: en `Realm settings → Client policies → Allow JWT
  bearer`. El endpoint es `POST /realms/{realm}/protocol/openid-connect/token`.
- **Keycloak 26+**: viene habilitado por defecto y con mejor soporte para
  `act`. Es la opción recomendada para producción a medio plazo.
- **Auth0**: usar *Client Credentials Exchange* con `client_assertion_type=
  urn:ietf:params:oauth:client-assertion-type:jwt-bearer`. Requiere que el
  cliente tenga *Enable JWT for Client Authentication*.
- **Okta**: *Client Authentication → Public key / Private key* (asociado a
  JWK), luego *Grant Type → JWT Bearer* en el AS.
- **Azure AD**: Azure AD B2C lo soporta; Entra ID puro lo soporta vía
  *Federated Identity Credentials* con un sub-grant específico.

#### B.7. Caso de uso ideal

Acciones que el usuario ya pre-aprobó (lectura de su propio calendario, su
propio perfil, sus archivos). Es el "background" del agente: tareas sin
sorpresa, sin coste cognitivo para el usuario.

#### B.8. Score por criterio

| Criterio | Puntuación | Justificación |
|---|---|---|
| C1 Seguridad | **4** | Sin password en tránsito. `act` lograble. MFA por scope requiere combinar. |
| C2 Madurez | **4** | RFC 7523 desde 2015. Producción masiva en Okta/Auth0. |
| C3 UX | **4** | Cero interacción si el consentimiento está pre-concedido. |
| C4 Implementación | **4** | ~1 semanas-persona incluyendo quirks de Keycloak 24. |
| C5 Compatibilidad | **4** | Keycloak 26+/Auth0/Okta OK. Keycloak 24 con setup. |
| C6 Resiliencia | **3** | Se pueden cachear access_tokens brevemente; refresh tokens no estándar aquí. |
| **Score ponderado** | **3.85** | |

#### B.9. Estimación de esfuerzo

- Habilitar grant en Keycloak + tests: **0.5 sp**.
- Implementar cliente `user_assertion` con `client_secret_jwt`: **0.5 sp**.
- Protocol mapper para `act`: **0.3 sp**.
- Tests de seguridad (replay, exp, kid rotation): **0.5 sp**.
- **Total**: **1.5–2 semanas-persona**.

#### B.10. Referencias

- **RFC 7521** — *Assertion Framework for OAuth 2.0 Client Authentication
  and Authorization Grants*.
- **RFC 7523 §2.1** — *JWT Bearer Authorization Grant*.
- **RFC 7523 §3** — formato de la *assertion* (header, payload, firma).
- **OIDC Core §9** — *Client Authentication*: perfiles `client_secret_jwt`
  y `private_key_jwt`.
- **Keycloak docs**: *JWT Authorization Grant* (server admin guide).

---

### Opción C — Token Exchange (RFC 8693)

#### C.1. Definición

Grant definido en **RFC 8693**. Permite a un cliente intercambiar un token
(sea access_token, refresh_token o id_token) por **otro token** con
características distintas: diferente `aud`, diferentes `scope`, o — clave para
nosotros — incluyendo el claim `act` que dice "este sujeto está actuando
en nombre de otro".

Perfiles principales:
- **on-behalf-of**: el cliente (agente) tiene un token de Ana y necesita otro
  token "en nombre de Ana" para una API downstream.
- **delegation**: Ana entrega poder explícito al agente (vía `act`).
- **impersonation**: el agente suplanta completamente a Ana (no recomendado).

#### C.2. Diagrama de flujo (on-behalf-of)

```
       Usuario              Agente IA              Keycloak               API downstream
          │                    │                       │                       │
          │  1. login         │                       │                       │
          │  (CIBA o PKCE)    │                       │                       │
          │                    │  2. tiene subject_token de Ana                 │
          │                    │     (access_token con sub=ana)                 │
          │                    │                       │                       │
          │                    │  3. POST /token       │                       │
          │                    │  grant_type=urn:ietf:params:oauth:           │
          │                    │              grant-type:token-exchange        │
          │                    │  subject_token=<token de Ana>                │
          │                    │  subject_token_type=urn:ietf:params:oauth:   │
          │                    │              token-type:access_token          │
          │                    │  audience=http://spring-boot-api              │
          │                    │  scope=calendar.read                          │
          │                    │  requested_token_type=urn:ietf:params:oauth: │
          │                    │              token-type:access_token          │
          │                    │  actor_token=<JWT firmado por agente>         │
          │                    │  actor_token_type=urn:ietf:params:oauth:     │
          │                    │              token-type:jwt                    │
          │                    │  client_id=agente-ia                          │
          │                    │  client_secret=***                            │
          │                    │ ────────────────────▶ │                       │
          │                    │                       │                       │
          │                    │                       │  4. (valida          │
          │                    │                       │     subject_token,   │
          │                    │                       │     comprueba        │
          │                    │                       │     delegaciones,    │
          │                    │                       │     emite nuevo JWT  │
          │                    │                       │     con sub=ana,     │
          │                    │                       │     act={sub:agente} │
          │                    │                       │     aud=spring-boot) │
          │                    │                       │                       │
          │                    │  5. 200 OK            │                       │
          │                    │  access_token=eyJ...  │                       │
          │                    │  issued_token_type=...│                       │
          │                    │ ◀──────────────────── │                       │
          │                    │                       │                       │
          │                    │  6. GET /api/calendar/events                  │
          │                    │  Authorization: Bearer ***                       │
          │                    │ ───────────────────────────────────────────────▶│
          │                    │                       │                       │
```

#### C.3. Ajuste a nuestro caso

**Esta es la opción "correcta" para producción a medio plazo** si nuestro
modelo es: el agente recibe un token "del usuario" y lo canjea por un token
"para la API" manteniendo la trazabilidad de Ana como `sub` y el agente como
`act`.

**Cómo se ajusta a nuestro flujo**:
1. Ana se autentica frente al IdP (vía Authorization Code+PKCE en el móvil,
   ROPC, WebAuthn, o lo que sea).
2. El móvil pasa al agente el `access_token` de Ana (o un refresh).
3. El agente hace Token Exchange contra el IdP pidiendo un token con
   `aud=spring-boot-api`, `scope=calendar.read`, `act=agente-ia`.
4. El agente llama a Spring Boot con el token canjeado. Spring Boot ve
   `sub=ana, act={sub:agente-ia}, aud=spring-boot-api`.

**Limitaciones reales**:
- **Keycloak 24**: tiene RFC 8693 pero **experimental**, detrás de feature flag.
  Keycloak 26+ lo trae GA.
- **Auth0**: soporta Token Exchange pero solo entre recursos de su propio
  ecosistema. Para recursos externos (nuestra API Spring Boot), requiere
  Custom Token Exchange action.
- **Okta**: tiene soporte sólido desde 2022 (post-adopción del RFC).
- **Azure AD/Entra ID**: NO soporta RFC 8693 puro. Su equivalente es
  *On-Behalf-Of* (OBO) que es un perfil parecido pero propietario.

#### C.4. Pros

- **P3-1**: **El claim `act` es nativo del RFC** (RFC 8693 §3). Sin hacks de
  mappers. Auditoría impecable.
- **P3-2**: Permite **encadenar** tokens: el agente puede a su vez hacer
  Token Exchange con un sub-agente downstream. Composición de servicios
  preserva identidad.
- **P3-3**: El `subject_token_type` permite token chaining con OAuth 1.0a,
  SAML 2.0 (RFC 8693 §3.1), etc., aunque no es nuestro caso.
- **P3-4**: Se puede combinar con DPoP (RFC 9445) para sender-constrained
  tokens: el token solo sirve al agente que lo pidió, no a un eavesdropper.

#### C.5. Contras

- **C3-1**: **Requiere un token "previo"** (`subject_token`). Esto obliga a
  que el usuario se haya autenticado primero. Para nuestro PoC sin login de
  usuario, no aplica directamente (es un complemento de E o PKCE).
- **C3-2**: **Keycloak 24 lo tiene detrás de `--features=token-exchange`**;
  en 26+ es estable pero hay que entender bien el
  *internal-id* vs *client-id* mapping (ver §7).
- **C3-3**: Si el `subject_token` es un refresh_token (en lugar de un
  access_token), hay semántica especial. Mezclar tipos lleva a confusión.
- **C3-4**: Si el agente upstream (Keycloak) está caído, no hay token
  exchange posible. La resiliencia requiere un **subject_token cache**
  firmado por el IdP (lo que es problemático porque no se debe confiar en
  tokens caducados).

#### C.6. Variantes de implementación

- **Keycloak 24**: habilitar `--features=token-exchange`. El endpoint es
  `/realms/{realm}/protocol/openid-connect/token` con `grant_type=
  urn:ietf:params:oauth:grant-type:token-exchange`. Para producción,
  usar Keycloak 26+.
- **Keycloak 26**: soporte GA. Documenta bien el campo `requested_actor`
  para el `act`.
- **Auth0**: requiere *Custom Token Exchange* action (BETA a fecha 2026-Q2).
  Funciona pero con caveats.
- **Okta**: soporte completo, documentado en
  *Okta Developer → API → OAuth → Token Exchange*.
- **Azure AD**: usa **OBO** (On-Behalf-Of), no RFC 8693 puro. Si nuestro
  stack es Microsoft, hay que pivotar a OBO.

#### C.7. Caso de uso ideal

Cuando hay múltiples servicios downstream y necesitas preservar la identidad
del usuario a través de capas. Por ejemplo: agente → servicio A → servicio B,
y todos necesitan saber que Ana es el `sub` original y que el agente es el
`act`.

#### C.8. Score por criterio

| Criterio | Puntuación | Justificación |
|---|---|---|
| C1 Seguridad | **5** | `act` nativo. Combina con DPoP. Composable y trazable. |
| C2 Madurez | **3** | RFC desde 2020. Keycloak 26+ GA. Otros IdPs en distintos niveles. |
| C3 UX | **4** | Sin interacción por request una vez el subject_token existe. |
| C4 Implementación | **3** | ~2.5 sp por el setup del subject_token + agente + tests. |
| C5 Compatibilidad | **3** | Keycloak 24 experimental; 26+ OK. Auth0 BETA. Azure AD vía OBO. |
| C6 Resiliencia | **3** | Requiere subject_token válido. Cache de refresh_tokens con TTL corto. |
| **Score ponderado** | **3.75** | |

#### C.9. Estimación de esfuerzo

- Setup subject_token via mobile (PKCE) + agente: **1.5 sp**.
- Habilitar Token Exchange en IdP: **0.3 sp**.
- Implementar lógica de canje con `actor_token`: **0.7 sp**.
- Tests + auditoría: **0.5 sp**.
- **Total**: **2.5–3 semanas-persona**.

#### C.10. Referencias

- **RFC 8693** — *OAuth 2.0 Token Exchange*.
- **RFC 8693 §3** — Request y response.
- **RFC 8693 §2.2.1** — claim `act`.
- **Keycloak 26 release notes**: *Token Exchange stabilization*.
- **Okta Developer**: *OAuth 2.0 Token Exchange*.
- **Microsoft identity platform**: *On-Behalf-Of flow*.

---

### Opción D — OIDC CIBA (Client Initiated Backchannel Authentication)

#### D.1. Definición

Definido en **OpenID Connect CIBA 1.0** (2019, OpenID Foundation). El cliente
(confidential) inicia la autenticación del usuario **sin browser** y sin
redirección a un IdP. La comunicación con el usuario es por **backchannel**:
el IdP envía la solicitud al dispositivo del usuario (push notification,
SMS, app del usuario) por un canal separado.

Casos típicos:
- Agentes conversacionales (es nuestro caso).
- IoT con asistente en cloud.
- Kioskos.

#### D.2. Diagrama de flujo

```
       Usuario              Agente IA              Keycloak               Cliente CIBA          Spring Boot API
          │                    │                       │                       │                       │
          │  1. prompt        │                       │                       │                       │
          │ "envía email"     │                       │                       │                       │
          │ ─────────────────▶│                       │                       │                       │
          │                    │                       │                       │                       │
          │                    │  2. POST /ext/ciba/auth (endpoint CIBA ext)  │                       │
          │                    │  client_id=agente-ia  │                       │                       │
          │                    │  client_secret=***    │                       │                       │
          │                    │  scope=email.send     │                       │                       │
          │                    │  login_hint_token=<JWT sub=ana>               │                       │
          │                    │  bind_token=<JWT sub=ana>                    │                       │
          │                    │  acr_values=2 (MFA)   │                       │                       │
          │                    │ ────────────────────▶ │                       │                       │
          │                    │                       │                       │                       │
          │                    │                       │  3. push notification:│                       │
          │                    │                       │     "¿aprobar email.send?"│                   │
          │                    │                       │ ────────────────────▶ │                       │
          │                    │                       │                       │                       │
          │                    │  4. 200 OK            │                       │                       │
          │                    │  auth_req_id=abc-123  │                       │                       │
          │                    │  expires_in=120       │                       │                       │
          │                    │  interval=5           │                       │                       │
          │                    │ ◀──────────────────── │                       │                       │
          │                    │                       │                       │                       │
          │                    │                       │      [usuario aprueba]│                       │
          │                    │                       │ ◀─────────────────────│                       │
          │                    │                       │                       │                       │
          │                    │  5. POST /token       │                       │                       │
          │                    │  grant_type=urn:openid:params:grant-type:ciba │                       │
          │                    │  auth_req_id=abc-123  │                       │                       │
          │                    │  client_id=agente-ia  │                       │                       │
          │                    │  client_secret=***    │                       │                       │
          │                    │ ────────────────────▶ │                       │                       │
          │                    │                       │                       │                       │
          │                    │  6. (en N polls)      │                       │                       │
          │                    │  200 OK               │                       │                       │
          │                    │  access_token=eyJ...  │                       │                       │
          │                    │  (sub=ana,            │                       │                       │
          │                    │   aud=spring-boot,    │                       │                       │
          │                    │   scope=email.send,   │                       │                       │
          │                    │   act={sub:agente-ia})│                       │                       │
          │                    │ ◀──────────────────── │                       │                       │
          │                    │                       │                       │                       │
          │                    │  7. POST /api/email/send                      │                       │
          │                    │  Authorization: Bearer ***                       │                       │
          │                    │ ───────────────────────────────────────────────▶                       │
          │                    │                       │                       │                       │
          │                    │                       │                       │                       │ (valida JWT)
          │                    │  8. 200 OK            │                       │                       │
          │                    │ ◀──────────────────────────────────────────────│                       │
```

#### D.3. Ajuste a nuestro caso

**La elección correcta para scopes sensibles**. El PoC actual usa CIBA con
Keycloak 24 + endpoint extendido `/ext/ciba/auth` (porque CIBA está marcado
como experimental y no está en el endpoint estándar). Esto funciona pero
tiene caveats:

1. **El endpoint CIBA estándar no está en `/token`**, sino en
   `/ext/ciba/auth` (Keycloak-specific extension). Esto NO es lo que dice
   OIDC CIBA §7.1, que define `POST /bc-authorize`. Keycloak lo expone como
   *preview feature* y por eso va en `/ext/`.
2. **Polling vs Ping**: Keycloak 24 implementa polling mode por defecto. En
   producción móvil, ping mode (Keycloak notifica al cliente cuando está
   listo) requiere webhook HTTPS público, lo cual no es trivial en móvil.
3. **`login_hint_token` debe estar firmado** y llevar `sub`, `scope`, `iss`
   (el cliente), `aud` (Keycloak). En el PoC usamos `client_secret_jwt`
   (HS256). Producción: `private_key_jwt`.
4. **`bind_token`**: vincula la request CIBA con la sesión del cliente CIBA
   del usuario. En el PoC coincide con `login_hint_token` (caso simple).
   En producción el `bind_token` lo emite el dispositivo tras un handshake
   OOB separado.

#### D.4. Pros

- **P3-1**: **Human-in-the-loop real**. El usuario aprueba cada acción
  sensible. Sin aprobación no hay token. Esto es lo que cierra el riesgo
  "agente comprometido envía emails".
- **P3-2**: El `sub` del token es el usuario real. El `act` es el agente.
  Auditoría completa.
- **P3-3**: Soporta **step-up MFA** vía `acr_values=2` (AAL2 en NIST SP
  800-63B). Esto es crítico para producción regulada.
- **P3-4**: Compatible con `binding_message` (mensaje que el IdP muestra
  al usuario, evitando ataques de confused deputy: "¿estás aprobando la
  transferencia a cuenta X, no Y?").

#### D.5. Contras

- **C3-1**: **El usuario debe estar disponible**. Si el móvil está apagado
  o sin red, la acción sensible se queda en `authorization_pending` y
  expira. Para acciones urgentes hay que definir timeout policy y
  notificación alternativa (SMS).
- **C3-2**: **Latencia**. El polling mínimo son ~5 segundos. Con UX
  decente (ping mode) se baja a 1-2 segundos, pero requiere infra adicional.
- **C3-3**: **El PoC requiere cliente CIBA separado** (`client-mock`).
  En producción es la app móvil real con push notifications
  (FCM/APNs). La integración push no es trivial.
- **C3-4**: **Keycloak 24 marca CIBA como preview feature** (sujeto a
  cambios). El endpoint está en `/ext/`, no en el path estándar. Migración
  a 26+ promete estabilización.
- **C3-5**: Si Keycloak cae durante la CIBA request, el `auth_req_id`
  puede quedar en un estado inconsistente (el cliente CIBA no recibe
  notification). Hay que diseñar **idempotencia** en el agente.

#### D.6. Variantes de implementación

- **Keycloak 24**: habilitar `--features=ciba`. Configurar realm
  attribute `cibaBackchannelTokenDeliveryMode=ping` o `poll`.
  Configurar `cibaAuthRequestedUserHint=login_hint_token` o `login_hint`.
  Configurar `cibaExpiresIn=120`, `cibaInterval=5`.
- **Keycloak 26**: estabiliza el endpoint y documentación.
- **Auth0**: Auth0 **NO soporta CIBA** a fecha de 2026-Q2. Workaround:
  custom action + push manual.
- **Okta**: soporta CIBA vía *Okta Identity Engine* desde 2023, pero
  requiere configuración adicional del *Authenticator*.
- **Azure AD/Entra ID**: NO soporta CIBA puro. Equivalente propietario:
  *Microsoft Authenticator* approvals (similar pero no estándar).

#### D.7. Caso de uso ideal

Acciones sensibles: pagos, envíos de email/DMs, cambios de configuración,
accesos a datos personales. Todo lo que requiera **consentimiento fresco
cada vez**.

#### D.8. Score por criterio

| Criterio | Puntuación | Justificación |
|---|---|---|
| C1 Seguridad | **5** | Human-in-the-loop + MFA + `act` + binding_message. |
| C2 Madurez | **3** | OIDC CIBA 1.0 desde 2019. Keycloak 24 preview. Otros IdPs limitados. |
| C3 UX | **3** | Push al usuario siempre para sensibles. Fricción inevitable. |
| C4 Implementación | **3** | ~3 sp: cliente CIBA + push + integración + tests. |
| C5 Compatibilidad | **3** | Keycloak 24/26 OK. Auth0/Entra NO. Okta parcial. |
| C6 Resiliencia | **3** | Si IdP cae durante CIBA, hay que diseñar reintentos idempotentes. |
| **Score ponderado** | **3.65** | |

#### D.9. Estimación de esfuerzo

- Setup CIBA en Keycloak: **0.3 sp**.
- Cliente CIBA con push notifications (FCM/APNs): **1 sp**.
- Integración agente ↔ IdP con polling + retry: **0.5 sp**.
- Tests E2E (aprobación, rechazo, timeout, MFA): **1 sp**.
- **Total**: **2.5–3 semanas-persona**.

#### D.10. Referencias

- **OpenID Connect CIBA 1.0** — *Client Initiated Backchannel Authentication*.
- **OIDC CIBA §7.1** — `bc-authorize` endpoint.
- **OIDC CIBA §8** — Token endpoint con `grant_type=urn:openid:params:grant-type:ciba`.
- **Keycloak CIBA docs**: *Server Administration Guide → CIBA*.
- **RFC 8176** — *Authentication Method Reference Values* (referenciado por
  `acr_values`).
- **NIST SP 800-63B** — AAL2/AAL3 (referenciado por step-up).

---

### Opción E — Authorization Code + PKCE + refresh tokens largos

#### E.1. Definición

El flujo canónico de OAuth 2.0 para apps móviles. Definido en:
- **RFC 6749 §4.1** — Authorization Code Grant.
- **RFC 7636** — *Proof Key for Code Exchange* (PKCE, antes "S256").
- **RFC 8252** — *OAuth 2.0 for Native Apps* (Best Current Practice).
- **RFC 9100** — *JWT Profile for OAuth 2.0 Client Authentication*
  (recomendado para cliente confidencial).

El usuario se autentica vía **web view** (system browser en iOS/Android,
`ASWebAuthenticationSession` en iOS, *Custom Tabs* en Android), el IdP
devuelve un `code`, el móvil lo canjea por `access_token` + `refresh_token`.

#### E.2. Diagrama de flujo

```
       Usuario              App móvil            Keycloak               Spring Boot API
          │                    │                       │                       │
          │  1. inicia        │                       │                       │
          │  sesión en app    │                       │                       │
          │ ─────────────────▶│                       │                       │
          │                    │                       │                       │
          │                    │  2. genera code_verifier (random)              │
          │                    │     code_challenge = S256(code_verifier)       │
          │                    │                       │                       │
          │                    │  3. abre system browser con /auth?             │
          │                    │     client_id=agente-ia                        │
          │                    │     response_type=code                         │
          │                    │     code_challenge=...                          │
          │                    │     code_challenge_method=S256                  │
          │                    │     redirect_uri=app://callback                 │
          │                    │     scope=openid profile email calendar.read   │
          │                    │     state=<random>                              │
          │                    │     nonce=<random>                              │
          │                    │ ───────────────────────────────────────────────▶│
          │                    │                       │                       │
          │                    │                       │  (Keycloak login UI) │
          │                    │                       │                       │
          │  4. login screen   │                       │                       │
          │  (system browser)  │                       │                       │
          │ ◀────────────────────────────────────────────│                       │
          │                    │                       │                       │
          │  5. credenciales + consent (offline_access) │                       │
          │ ─────────────────────────────────────────▶│                       │
          │                    │                       │                       │
          │                    │                       │  6. redirige a       │
          │                    │                       │     app://callback?   │
          │                    │                       │     code=xyz          │
          │                    │                       │     state=...         │
          │  7. deep link      │                       │                       │
          │ ◀────────────────────────────────────────────│                       │
          │                    │                       │                       │
          │                    │  8. POST /token       │                       │
          │                    │  grant_type=authorization_code                 │
          │                    │  code=xyz                                    │
          │                    │  code_verifier=...                            │
          │                    │  redirect_uri=app://callback                 │
          │                    │  client_id=agente-ia                          │
          │                    │  client_secret=*** (o client_assertion JWT)   │
          │                    │ ────────────────────▶ │                       │
          │                    │                       │                       │
          │                    │  9. 200 OK            │                       │
          │                    │  access_token (15 min)│                       │
          │                    │  refresh_token (30 días)                      │
          │                    │  id_token            │                       │
          │                    │ ◀──────────────────── │                       │
          │                    │                       │                       │
          │                    │  10. POST /api/email/send                     │
          │                    │  Authorization: Bearer ***                       │
          │                    │ ───────────────────────────────────────────────▶│
          │                    │                       │                       │
```

#### E.3. Ajuste a nuestro caso

**La elección correcta para el móvil "de primera línea"**. Pero aquí hay un
desfase: en nuestro modelo, el usuario **no llama a la API de negocio
directamente desde el móvil**. Es el **agente** quien llama. Entonces:

- Si el agente usa PKCE con su propio `client_id`, ¿dónde se queda el
  consentimiento del usuario?
- Si el usuario hace PKCE en el móvil, **el access_token queda en el
  móvil**, no en el agente. ¿Cómo lo entregamos al agente de forma segura?

**Patrón canónico con agente**:
1. El usuario hace PKCE en el móvil → access_token + refresh_token del
   usuario, scope=openid.
2. El móvil pasa el `access_token` (o refresh) al agente en una llamada
   autenticada (mTLS, o token firmado por la app).
3. El agente usa Token Exchange (Opción C) o JWT Bearer (Opción B) con
   ese `subject_token` para obtener un token con `aud=spring-boot-api`.

#### E.4. Pros

- **P3-1**: Estándar más maduro y battle-tested del mundo OAuth. Decenas
  de miles de apps lo usan.
- **P3-2**: **El consentimiento del usuario es explícito** en el browser.
  El usuario ve exactamente qué scopes pide el agente.
- **P3-3**: Refresh tokens largos (30 días) permiten sesiones largas en
  móvil sin re-login constante.
- **P3-4**: Compatible con WebAuthn en IdP: el usuario puede usar
  passkeys/biometría directamente en el system browser.

#### E.5. Contras

- **C3-1**: **Requiere UI de browser en cada login inicial**. Si el agente
  necesita actuar en background (sin intervención del usuario), no es
  viable por sí solo — necesita combinarse con refresh tokens largos o
  con otra opción.
- **C3-2**: **El refresh token es crítico**. Si se filtra, el atacante
  tiene 30 días. Hay que protegerlo con *refresh token rotation* (RFC 6819
  + draft `draft-ietf-oauth-security-topics`).
- **C3-3**: **No hay `act` nativo** para el agente. El token dice
  "Ana accedió", no "agente-ia accedió en nombre de Ana". Solución:
  combinar con Token Exchange (Opción C) o con claims custom.
- **C3-4**: Implementación nativa en iOS/Android requiere
  *ASWebAuthenticationSession* y *Custom Tabs*. No es trivial hacer un
  deep link bien securizado (universal links + App Links, no `://customscheme`
  simple).

#### E.6. Variantes de implementación

- **Keycloak**: cliente con *Standard flow* ON, *Direct access grants* OFF.
  PKCE obligatorio (en 24.x ya viene forzado por *Client policies*).
- **Auth0**: *Native* client type, *Authorization Code* + PKCE *required*.
- **Okta**: *Native* app integration. Soporta PKCE desde 2018.
- **Azure AD**: *Mobile and desktop applications* flow. MSAL lo automatiza.

#### E.7. Caso de uso ideal

App móvil que actúa directamente contra la API de negocio (sin intermediario
agente). O como **primera fase** del flujo agente: el móvil hace PKCE,
obtiene tokens, y los pasa al agente.

#### E.8. Score por criterio

| Criterio | Puntuación | Justificación |
|---|---|---|
| C1 Seguridad | **4** | PKCE + system browser + WebAuthn. Pero refresh tokens son riesgo. |
| C2 Madurez | **5** | El estándar más usado. |
| C3 UX | **3** | Login inicial con browser. Re-login en cada refresh largo. |
| C4 Implementación | **3** | ~3 sp para el SDK nativo + secure storage + universal links. |
| C5 Compatibilidad | **5** | Universal. |
| C6 Resiliencia | **4** | Refresh tokens largos dan ventana amplia sin IdP. |
| **Score ponderado** | **3.85** | |

#### E.9. Estimación de esfuerzo

- SDK nativo iOS + Android: **1.5 sp** cada uno.
- Backend: configurar cliente + scopes + consent: **0.5 sp**.
- Secure storage (Keychain / EncryptedSharedPreferences): **0.5 sp**.
- Universal links / App links: **0.5 sp**.
- **Total**: **3.5–4 semanas-persona** (sólo la parte "mobile first").

#### E.10. Referencias

- **RFC 6749 §4.1** — Authorization Code Grant.
- **RFC 7636** — PKCE.
- **RFC 8252 §8** — *Native Apps BCP*.
- **RFC 9100** — JWT Profile for Client Authentication.
- **draft-ietf-oauth-security-topics** — Refresh token rotation, sender
  constrained, etc.

---

### Opción F — FAPI 2.0 (Financial-grade API)

#### F.1. Definición

**FAPI 2.0** es un perfil de OAuth 2.0 + OIDC publicado por OpenID
Foundation (final en 2023) específico para APIs que manejan **datos
financieros y de alta sensibilidad**. Restringe fuertemente las opciones
del AS para reducir superficie de ataque.

**Perfiles relevantes**:
- **FAPI 2.0 Security Profile** (mandatory sender-constrained tokens + DPoP
  o mTLS, JWS para respuestas, JWKS con rotación corta).
- **FAPI 2.0 Message Signing** (firma de mensajes HTTP, no solo tokens).
- **FAPI 2.0 Identity Assurance** (combinación con OIDC Identity Assurance
  para claims verificados de identidad).

**Dependencias técnicas**:
- **RFC 9445** — DPoP (sender-constrained access tokens).
- **RFC 9100** — JWT profile para client auth.
- **RFC 9396** — Rich Authorization Requests (RAR).

#### F.2. Diagrama de flujo (FAPI 2.0 + DPoP)

```
       Usuario              Agente IA              Keycloak               Spring Boot API
          │                    │                       │                       │
          │  1. prompt        │                       │                       │
          │ "pago 1000 €"     │                       │                       │
          │ ─────────────────▶│                       │                       │
          │                    │                       │                       │
          │                    │  2. genera par de claves ECDSA P-256 (en HSM/TPM)
          │                    │     publica JWKs en JWKS del agente
          │                    │                       │                       │
          │                    │  3. genera DPoP proof JWT por request          │
          │                    │     header: { typ:"dpop+jwt", alg:ES256,     │
          │                    │              jwk: <clave publica> }           │
          │                    │     payload: { jti, htm, htu, iat, ath=hash(access_token) }
          │                    │                       │                       │
          │                    │  4. POST /token (con PKCE, client_assertion JWT)
          │                    │  grant_type=authorization_code                 │
          │                    │  client_assertion=<JWT firmado con private_key>
          │                    │  client_assertion_type=urn:ietf:params:oauth: │
          │                    │              client-assertion-type:jwt-bearer  │
          │                    │  code=xyz + code_verifier                      │
          │                    │ ────────────────────▶ │                       │
          │                    │                       │                       │
          │                    │                       │  5. (valida JWT del   │
          │                    │                       │     cliente, PKCE,    │
          │                    │                       │     issuer, exp,      │
          │                    │                       │     firma response    │
          │                    │                       │     con JWS, emite   │
          │                    │                       │     access_token     │
          │                    │                       │     con cnf.jkt=hash  │
          │                    │                       │     de la clave pub) │
          │                    │                       │                       │
          │                    │  6. 200 OK            │                       │
          │                    │  access_token (15 min)│                       │
          │                    │  (cnf.jkt=hash(clave publica del agente))      │
          │                    │ ◀──────────────────── │                       │
          │                    │                       │                       │
          │                    │  7. POST /payments    │                       │
          │                    │  Authorization: Bearer ***                       │
          │                    │  DPoP: <proof JWT>    │                       │
          │                    │ ───────────────────────────────────────────────▶│
          │                    │                       │                       │
          │                    │                       │                       │  8. (valida firma del
          │                    │                       │                       │     access_token,    │
          │                    │                       │                       │     comprueba que   │
          │                    │                       │                       │     ath en DPoP     │
          │                    │                       │                       │     coincide con   │
          │                    │                       │                       │     hash(access_tk),│
          │                    │                       │                       │     verifica que   │
          │                    │                       │                       │     jwk del DPoP   │
          │                    │                       │                       │     coincide con   │
          │                    │                       │                       │     cnf.jkt)       │
          │                    │                       │                       │
          │                    │  9. 200 OK            │                       │
          │                    │ ◀──────────────────────────────────────────────│
          │                    │                       │                       │
```

#### F.3. Ajuste a nuestro caso

**FAPI 2.0 es overkill para la mayoría de nuestras APIs pero obligatorio
para pagos**. La decisión clave es: ¿qué endpoints tocan dinero?

- Si **ninguno** toca dinero (sólo lectura de calendario, lectura de
  perfil), FAPI 2.0 es sobreingeniería.
- Si **alguno toca dinero** (transferencias, cobros), FAPI 2.0 es
  mandatorio por compliance (PSD2 en Europa, FAPI en muchos bancos).

**Restricciones que mete FAPI 2.0 que chocan con nuestro PoC**:
1. **Refresh tokens están prohibidos** en algunos perfiles. O son de un
   solo uso (sender-constrained + rotación obligatoria).
2. **El `aud` debe ser exacto**: no se puede emitir un token "genérico"
   para que el agente decida a qué API va.
3. **El cliente debe tener JWKs públicas** rotando al menos cada 7 días.
4. **Las respuestas del AS deben ir firmadas (JWS)**.

#### F.4. Pros

- **P3-1**: **El más seguro del mercado**. DPoP garantiza que el token
  robado no sirve a un atacante (sender-constrained). PKCE + private_key_jwt
  cierra casi todos los vectores de intercepción.
- **P3-2**: **Compliance**: si haces pagos, es lo que te piden los
  reguladores. Cubre PSD2, UK OB, CDR Australia, etc.
- **P3-3**: **Auditoría criptográfica**: cada request lleva un DPoP proof
  firmado con la clave del agente. Trazabilidad hasta del cliente
  criptográfico.
- **P3-4**: **JAR + RAR** (RFC 9396): rich authorization requests con
  detalles del pago (monto, cuenta destino, etc.). El usuario puede
  aprobar/rechazar con contexto completo.

#### F.5. Contras

- **C3-1**: **Complejidad brutal**. Requiere HSM o KMS para las claves
  del cliente (o del agente). Sin eso, las claves viven en disco y
  perdemos el beneficio criptográfico.
- **C3-2**: **Soporte de IdPs limitado a fecha de 2026-Q2**:
  - **Keycloak 26**: tiene *FAPI 2.0 Security Profile* pero detrás de
    feature flag y solo en planes enterprise.
  - **Auth0**: tiene *FAPI-compliant* mode (preview).
  - **Okta**: soporta FAPI 1.0; FAPI 2.0 en roadmap.
  - **Azure AD**: no certificado FAPI.
- **C3-3**: **APIs de negocio deben validar DPoP**. Spring Security
  resource server estándar NO valida DPoP out-of-the-box. Hay que
  añadir un filtro custom o usar Spring Authorization Server.
- **C3-4**: **Overhead**: cada request HTTP requiere generar y firmar un
  DPoP proof. ~5-10ms en CPU modesto. En alto volumen es relevante.
- **C3-5**: Si el agente corre en cloud, las claves deben estar en
  KMS/HSM, no en variables de entorno. Esto complica el deploy.

#### F.6. Variantes de implementación

- **Keycloak 26**: `realm-branding-enabled=true` + perfil FAPI en
  *Client policies*. Hay que contratar Keycloak Premium para SAML y
  algunas features.
- **Auth0**: *API → APIs → Settings → FAPI Profile* (preview). Requiere
  custom actions para validación DPoP en APIs downstream.
- **Okta**: *Identity Engine → FAPI* configuration. Solo en tenants
  con *Identity Engine* habilitado (no en Classic).
- **Azure AD**: NO certificado. Workaround: implementar FAPI-like
  en casa (mTLS con device cert + DPoP manual).

#### F.7. Caso de uso ideal

APIs que tocan dinero o datos financieros. PSD2 en Europa. Pagos entre
cuentas. Acceso a datos bancarios. Específicamente, lo que pide la FCA
británica, la PSD2 europea, la CDR australiana, y la Open Finance en
general.

#### F.8. Score por criterio

| Criterio | Puntuación | Justificación |
|---|---|---|
| C1 Seguridad | **5** | El estado del arte. DPoP + PKCE + JWS + RAR. |
| C2 Madurez | **3** | FAPI 1.0 desde 2017. FAPI 2.0 estabilizado 2023. IdPs en adopción. |
| C3 UX | **3** | Login inicial + enrollment de claves del cliente. Fricción alta. |
| C4 Implementación | **1** | ~6-8 sp incluyendo HSM/KMS + Spring custom filters + tests. |
| C5 Compatibilidad | **2** | Solo Keycloak 26 enterprise / Auth0 preview / Okta Identity Engine. |
| C6 Resiliencia | **2** | Refresh tokens restringidos. Si pierdes la clave privada, pierdes todo. |
| **Score ponderado** | **3.05** | |

#### F.9. Estimación de esfuerzo

- Habilitar FAPI en IdP: **0.5 sp**.
- Cliente (agente) con claves en KMS/HSM: **1 sp**.
- Cliente (móvil) con enrollment WebAuthn + passkey: **1.5 sp**.
- Spring Boot con DPoP validation custom: **2 sp**.
- Tests de seguridad + auditoría: **1 sp**.
- Compliance review: **+1 sp** (externo).
- **Total**: **6–8 semanas-persona** + 1 sp externo de compliance.

#### F.10. Referencias

- **FAPI 2.0 Security Profile** — OpenID Foundation.
- **FAPI 2.0 Message Signing**.
- **RFC 9445** — *DPoP* (Demonstrating Proof-of-Possession).
- **RFC 9396** — *Rich Authorization Requests*.
- **RFC 9100** — *JWT Profile for Client Authentication*.
- **OpenID FAPI WG**: https://openid.net/wg/fapi/.

---

### Opción G — mTLS + service-to-service custom

#### G.1. Definición

Patrón "enterprise clásico" pre-OAuth 2.0. Cada servicio tiene un
**certificado X.509** emitido por una **CA interna** (o pública). Las
comunicaciones se hacen sobre **mTLS** (RFC 8705): cliente y servidor
mutuamente se autentican con certificados. La "autorización" se hace por
headers o claims custom (`X-User-Id`, `X-On-Behalf-Of`) que el proxy o el
servidor confía porque el certificado es válido.

Perfiles:
- **mTLS puro**: certificado por servicio. La identidad del usuario se
  propaga por headers firmados (SAML assertion, JWT firmado por el IdP).
- **mTLS + JWT bearer**: certificado para el canal, JWT para la identidad
  del usuario (RFC 7523 sobre canal mTLS).
- **Service mesh (Istio/Linkerd)**: el mesh gestiona los certificados y la
  propagación de identidad (SPIFFE/SPIRE).

#### G.2. Diagrama de flujo

```
       Usuario              App móvil            API Gateway (mTLS)       Agente IA           Spring Boot API
          │                    │                       │                       │                       │
          │  1. login         │                       │                       │                       │
          │ ─────────────────▶│                       │                       │                       │
          │                    │                       │                       │                       │
          │                    │  2. POST /agent       │                       │                       │
          │                    │  X-User-Id=ana        │                       │                       │
          │                    │  X-Session=<JWT>      │                       │                       │
          │                    │ ────────────────────▶ │                       │                       │
          │                    │  (TLS client cert)    │                       │                       │
          │                    │                       │  3. (valida cert      │                       │
          │                    │                       │     contra CA,        │                       │
          │                    │                       │     extrae CN/SAN)    │                       │
          │                    │                       │                       │                       │
          │                    │                       │  4. (propaga headers  │                       │
          │                    │                       │     o JWT firmado)    │                       │
          │                    │                       │ ────────────────────▶ │                       │
          │                    │                       │  (mTLS entre GW y    │                       │
          │                    │                       │   agente)             │                       │
          │                    │                       │                       │                       │
          │                    │                       │                       │  5. POST /api/email/send
          │                    │                       │                       │  X-User-Id=ana        │
          │                    │                       │                       │  Authorization: Bearer <JWT>
          │                    │                       │                       │  (TLS client cert del agente)
          │                    │                       │                       │ ────────────────────▶│
          │                    │                       │                       │                       │
          │                    │                       │                       │                       │  6. (valida cert,
          │                    │                       │                       │                       │     valida JWT contra
          │                    │                       │                       │                       │     IdP, extrae sub=ana)
          │                    │                       │                       │                       │
          │                    │                       │                       │  7. 200 OK            │
          │                    │                       │                       │ ◀──────────────────── │
          │                    │                       │                       │                       │
          │                    │  8. 200 OK            │                       │                       │
          │                    │ ◀────────────────────────────────────────────│                       │
          │                    │                       │                       │                       │
```

#### G.3. Ajuste a nuestro caso

**Funciona, pero es "viejo confiable"**. Lo que aporta:

- **Identidad criptográfica del servicio**: el agente está autenticado
  como "agente-ia" por su certificado, no por un secret en texto plano.
  Esto es **más fuerte** que `client_secret_basic`.
- **Cifrado de canal obligatorio**: mTLS garantiza confidencialidad e
  integridad punto a punto.
- **Auditoría**: los logs del API gateway tienen CN/SAN del cliente.

**Lo que NO aporta**:

- **Identidad del usuario**: la aserción "actúa en nombre de ana" sigue
  siendo un header firmado por el gateway. Si el gateway está comprometido,
  el atacante puede inyectar cualquier `X-User-Id`.
- **Estándar**: hay RFC 8705 (OAuth 2.0 mTLS Client Authentication), pero
  el "patrón custom" (con headers `X-User-Id`) es propietario de cada
  empresa.
- **Rotación de certificados**: hay que operar una PKI. Es operacionalmente
  costoso.

#### G.4. Pros

- **P3-1**: **Criptográficamente fuerte** si se hace bien: claves en HSM,
  rotación corta, revocación por CRL/OCSP.
- **P3-2**: **Sin password ni secret en disco**. El certificado hace de
  credencial.
- **P3-3**: **Cero dependencia del IdP para autenticar al servicio**: una
  vez expedido el cert, el agente puede actuar sin consultar al IdP para
  su propia identidad.
- **P3-4**: Funciona con **service mesh** (Istio + SPIFFE): la
  infraestructura maneja los certificados automáticamente.

#### G.5. Contras

- **C3-1**: **PKI operacional**: hay que montar una CA, distribuir
  certificados, rotarlos (cada 90 días típico), revocarlos. Si te falla
  la CA, se cae todo.
- **C3-2**: **Identidad del usuario sigue siendo "headers firmados"**.
  El riesgo se desplaza al gateway/API de confianza.
- **C3-3**: **Móvil con mTLS** es problemático: los certificados en
  dispositivo son un riesgo (robo de device). Mejor usar PKCE en el
  móvil y mTLS solo entre servicios backend.
- **C3-4**: **No hay estándar para "actúa en nombre de"**. Se reinventa
  en cada empresa. Auditar eso es infernal.
- **C3-5**: **No escala bien a APIs externas** (terceros). Si nuestra
  API Spring Boot tiene que aceptar tokens de terceros (clientes B2B),
  mTLS puro no ayuda: necesitamos JWT.

#### G.6. Variantes de implementación

- **Istio + SPIFFE**: el agente corre como un pod con `ServiceAccount`
  y obtiene automáticamente un certificado SPIFFE. Sin gestión manual.
- **Vault PKI**: HashiCorp Vault emite certificados con TTL corto.
  Agentes los renuevan automáticamente.
- **cfssl + Kubernetes cert-manager**: para clusters Kubernetes.
- **OpenShift Service Mesh**: similar a Istio.
- **Apigee + mTLS**: Apigee soporta mTLS hacia backends (`<SSLInfo>` en
  TargetEndpoint). Pero el cliente (agente) sigue necesitando su cert.

#### G.7. Caso de uso ideal

**Service-to-service en cluster privado**: agente (en Kubernetes) llama a
API Spring Boot (en el mismo cluster) sin pasar por IdP para autenticarse.
Combinable con OAuth para la identidad del usuario.

#### G.8. Score por criterio

| Criterio | Puntuación | Justificación |
|---|---|---|
| C1 Seguridad | **4** | Fuerte si se hace bien. Identidad de usuario es punto débil. |
| C2 Madurez | **5** | mTLS/X.509 desde los 90. SPIFFE/SPIRE estandarizado en CNCF. |
| C3 UX | **4** | Cero interacción para el usuario en el path mTLS. |
| C4 Implementación | **2** | PKI + cert rotation + revocación. ~4 sp. |
| C5 Compatibilidad | **3** | Funciona con Spring Security, Apigee, Istio. Pero no estándar OAuth. |
| C6 Resiliencia | **4** | Si la CA está disponible. CRL cache. |
| **Score ponderado** | **3.65** | |

#### G.9. Estimación de esfuerzo

- PKI interna (Vault o Istio Citadel): **1 sp**.
- Emisión de certificados para agente y APIs: **0.5 sp**.
- Configuración mTLS en Apigee + Spring Security: **1 sp**.
- Propagación de identidad de usuario vía JWT firmado por gateway: **1 sp**.
- Rotación + revocación + tests: **1 sp**.
- **Total**: **4–5 semanas-persona**.

#### G.10. Referencias

- **RFC 8705** — *OAuth 2.0 Mutual-TLS Client Authentication and
  Certificate-Bound Access Tokens*.
- **RFC 8446** — *TLS 1.3*.
- **SPIFFE/SPIRE**: https://spiffe.io/.
- **Istio Security**: https://istio.io/latest/docs/concepts/security/.
- **HashiCorp Vault PKI**: https://developer.hashicorp.com/vault/docs/secrets/pki.

---

## 4. Tabla comparativa final con totales ponderados

### 4.1. Tabla de scores

Aplicando la matriz de §2.1 con pesos:

- C1 Seguridad: 30
- C2 Madurez: 15
- C3 UX: 15
- C4 Implementación: 15
- C5 Compatibilidad: 15
- C6 Resiliencia: 10

| Criterio (peso) | A ROPC | B JWT Bearer | C Token Exch. | D CIBA | E PKCE móil | F FAPI 2.0 | G mTLS |
|---|---:|---:|---:|---:|---:|---:|---:|
| **C1 Seguridad** (30) | 1 | 4 | 5 | 5 | 4 | 5 | 4 |
| **C2 Madurez** (15) | 3 | 4 | 3 | 3 | 5 | 3 | 5 |
| **C3 UX** (15) | 5 | 4 | 4 | 3 | 3 | 3 | 4 |
| **C4 Implementación** (15) | 5 | 4 | 3 | 3 | 3 | 1 | 2 |
| **C5 Compatibilidad** (15) | 5 | 4 | 3 | 3 | 5 | 2 | 3 |
| **C6 Resiliencia** (10) | 2 | 3 | 3 | 3 | 4 | 2 | 4 |
| **Total ponderado** | **3.05** | **3.85** | **3.75** | **3.65** | **3.85** | **3.05** | **3.65** |
| Ranking | 6º | **1º (empate)** | 3º | 4º (empate) | **1º (empate)** | 6º (empate) | 4º (empate) |

### 4.2. Cálculo verificado (sample)

- **A ROPC**: (30×1 + 15×3 + 15×5 + 15×5 + 15×5 + 10×2) / 100 = (30+45+75+75+75+20)/100 = 320/100 = **3.20**. 
  *Corrección*: 30+45+75+75+75+20 = 320 → 3.20.
- **B JWT Bearer**: (30×4 + 15×4 + 15×4 + 15×4 + 15×4 + 10×3) / 100 = (120+60+60+60+60+30)/100 = 390/100 = **3.90**.
- **C Token Exchange**: (30×5 + 15×3 + 15×4 + 15×3 + 15×3 + 10×3) / 100 = (150+45+60+45+45+30)/100 = 375/100 = **3.75**.
- **D CIBA**: (30×5 + 15×3 + 15×3 + 15×3 + 15×3 + 10×3) / 100 = (150+45+45+45+45+30)/100 = 360/100 = **3.60**.
- **E PKCE móvil**: (30×4 + 15×5 + 15×3 + 15×3 + 15×5 + 10×4) / 100 = (120+75+45+45+75+40)/100 = 400/100 = **4.00**.
- **F FAPI 2.0**: (30×5 + 15×3 + 15×3 + 15×1 + 15×2 + 10×2) / 100 = (150+45+45+15+30+20)/100 = 305/100 = **3.05**.
- **G mTLS**: (30×4 + 15×5 + 15×4 + 15×2 + 15×3 + 10×4) / 100 = (120+75+60+30+45+40)/100 = 370/100 = **3.70**.

**Ranking final corregido**:

| Rank | Opción | Score |
|---:|---|---:|
| **1º** | **E (PKCE + refresh tokens largos)** | **4.00** |
| 2º | B (JWT Bearer RFC 7523) | 3.90 |
| 3º | C (Token Exchange RFC 8693) | 3.75 |
| 4º | G (mTLS + custom) | 3.70 |
| 5º | D (CIBA) | 3.60 |
| 6º (empate) | A (ROPC) | 3.20 |
| 6º (empate) | F (FAPI 2.0) | 3.05 |

### 4.3. Ganador por criterio

| Criterio | Ganador | Justificación |
|---|---|---|
| C1 Seguridad | C, D, F (empate, 5/5) | Token Exchange, CIBA y FAPI cubren el modelo completo. |
| C2 Madurez | E, G (empate, 5/5) | PKCE + mTLS son los estándares más añosos. |
| C3 UX | A (5/5) | Cero interacción. Pero el coste es seguridad. |
| C4 Implementación | A (5/5) | Lo más rápido de implementar. De nuevo, el coste es seguridad. |
| C5 Compatibilidad | A, E (empate, 5/5) | ROPC y PKCE funcionan en cualquier IdP. |
| C6 Resiliencia | E, G (empate, 4/5) | Refresh tokens largos + mTLS dan ventana amplia sin IdP. |

### 4.4. Recomendación global

**No hay un único ganador**. La decisión depende del **horizonte temporal** y
del **perfil de riesgo**:

- **PoC / corto plazo**: usar **A (ROPC)** por velocidad, con plan de
  sustitución a **B + D**.
- **MVP 1.0 / medio plazo**: **E (PKCE en móvil) + B (JWT Bearer en
  agente) + D (CIBA para sensibles)**, con Token Exchange opcional si
  encadenamos a otros servicios.
- **Producción crítica / largo plazo**: **F (FAPI 2.0) + D (CIBA)** para
  los flujos que tocan dinero. Mantener **B + E** para el resto.

La opción **G (mTLS)** no es alternativa sino **complemento** al OAuth:
idealmente lo usamos en service-to-service backend (agente → API Spring
Boot) por canal, y OAuth para la identidad del usuario por encima.

---

## 5. Recomendación por horizonte temporal

### 5.1. Corto plazo (PoC, 0-3 meses): **A + D híbrido**

**Configuración recomendada**:

- **Scope `*.read`** (rutinario) → **A (ROPC)**. Por velocidad.
- **Scope `*.send` / `*.write` / `*.pay`** (sensible) → **D (CIBA)**. Por
  necesidad regulatoria y de UX (human-in-the-loop).

**Stack**:

- Keycloak 24 (con `--features=ciba`).
- Agente Python con `oauth_client.py` que decide flujo por terminación del
  scope (exactamente como el PoC actual).
- Spring Boot resource server con JWT estándar.
- Apigee con `VerifyJWT` policy.

**Riesgos aceptados**:

- Password del usuario en tránsito (mitigado: TLS + cliente confidencial +
  vault de secretos).
- Keycloak 24 CIBA en preview (mitigado: pin a versión exacta).

**Esfuerzo**: el PoC ya está construido. Cierre de issues residuales: **1-2 sp**.

### 5.2. Medio plazo (MVP 1.0, 3-9 meses): **B + D + E**

**Configuración recomendada**:

- Sustituir ROPC por **B (JWT Bearer RFC 7523)** para scopes rutinarios.
- Mantener **D (CIBA)** para sensibles.
- En el móvil, hacer **E (PKCE)** para el login inicial y para que el
  usuario pueda "asociar" su identidad al agente (consentimiento persistente).
- **Subir a Keycloak 26+** para tener Token Exchange estable y CIBA GA.

**Stack**:

- Keycloak 26.x (LTS).
- Agente Python con `client_secret_jwt` o `private_key_jwt` (asimétrico).
- Móvil iOS + Android con AppAuth o Authlib + ASWebAuthenticationSession.
- Apigee con `VerifyJWT` + `OAuthV2` policy.

**Esfuerzo**: **3-4 sp** + QA + auditoría de seguridad externa.

### 5.3. Largo plazo (Producción crítica, 9-18 meses): **F + D + E + G (parcial)**

**Configuración recomendada**:

- **Endpoints de pago/financieros** → **F (FAPI 2.0)** con DPoP.
- **Endpoints sensibles no-pago** → **D (CIBA)**.
- **Endpoints rutinarios** → **B (JWT Bearer)** con PKCE en login inicial
  (E).
- **Canal service-to-service** → **G (mTLS)** vía service mesh (Istio o
  Vault PKI).

**Stack**:

- Keycloak 26.x + features premium (FAPI profile).
- Spring Authorization Server o Spring Security custom con DPoP filter.
- Istio service mesh con SPIFFE.
- KMS / HSM (cloud-managed: AWS KMS, GCP KMS, Azure Key Vault).

**Esfuerzo**: **8-12 sp** + 1-2 sp de compliance review externo.

### 5.4. Roadmap visual

```
2026 Q3 (PoC)       2026 Q4 (MVP 1.0)    2027 Q1-Q2 (Producción)    2027 Q3+ (Compliance)
─────────────────── ────────────────────── ──────────────────────────── ─────────────────────
A (ROPC) + D (CIBA) B (JWT Bearer) +      F (FAPI 2.0) + D (CIBA) +   (continuo)
Keycloak 24         D (CIBA) + E (PKCE)   B (rutinarios) + G (mTLS)
                    Keycloak 26+          Istio service mesh
                                            KMS / HSM

                    ↑ transición              ↑ transición               ↑ iteración
                    ↓ riesgos residuales      ↓ riesgos residuales       ↓ optimization
                    - passwords en tránsito   - sin sender-constrained   - FAPI 2.0 Message Signing
                    - CIBA preview           - sin mTLS backend          - FAPI 2.0 Identity Assurance
```

### 5.5. Hitos concretos

1. **Hito 1 (fin Q3 2026)**: PoC cerrado con A + D. Tests E2E verdes.
   Documentación publicada.
2. **Hito 2 (fin Q4 2026)**: Sustitución de ROPC por JWT Bearer. Keycloak
   upgrade a 26.x. App móvil con PKCE en login inicial.
3. **Hito 3 (fin Q1 2027)**: Endpoints de pago con FAPI 2.0 + DPoP.
   Apigee con políticas de sender-constrained tokens.
4. **Hito 4 (fin Q2 2027)**: Service mesh (Istio + SPIFFE) entre agente y
   APIs internas. Auditoría externa de compliance.

---

## 6. Notas sobre Apigee + Spring Boot en producción

### 6.1. ¿Quién valida el JWT: Apigee o Spring?

En el PoC, **Spring Boot valida el JWT directamente** porque hace de
Apigee-stub. En producción, **ambos pueden validar**, en capas:

```
                  ┌─────────────────────┐
   Cliente        │     APIGEE          │
   (agente) ──────│  - VerifyAPIKey     │──── valida API key (client_id)
   Bearer + JWT   │  - VerifyJWT        │──── valida JWT (firma, iss, exp, aud)
                  │  - ExtractVariables │──── extrae claims para routing/quota
                  │  - OAuthV2          │──── opcional: token introspection
                  └──────────┬──────────┘
                             │ (header propagation)
                             ▼
                  ┌─────────────────────┐
                  │   SPRING BOOT API   │
                  │   - Resource Server │──── segunda validación de JWT
                  │   - JwtAuthConverter│──── mapea scope→authority
                  │   - @PreAuthorize   │──── autoriza por scope
                  └─────────────────────┘
```

**¿Por qué doble validación?**

- **Apigee** está delante: filtra tráfico mal formado, hace rate-limiting,
  quota, monetización. Si falla Apigee, el tráfico no llega a Spring.
- **Spring** está detrás: defensa en profundidad. Si alguien bypasea
  Apigee (vía red interna), Spring sigue validando. Esto es crítico.

**Recomendación**: validar en **ambos** con la misma configuración de
issuer-uri. Es lo que hace cualquier sistema bien diseñado.

### 6.2. Configuración típica Apigee

#### VerifyAPIKey policy

```xml
<VerifyAPIKey name="VA-Key-Check">
  <DisplayName>Verify API Key</DisplayName>
  <APIKey ref="request.queryparam.apikey"/>
</VerifyAPIKey>
```

Esto verifica que el cliente conoce el API key (autenticación "primitiva"
del cliente). No verifica scopes ni identidad de usuario.

#### VerifyJWT policy

```xml
<VerifyJWT name="VJ-Token">
  <DisplayName>Verify JWT</DisplayName>
  <Algorithm>RS256</Algorithm>
  <Source>request.header.Authorization</Source>
  <IgnoreCriticalExtensions>false</IgnoreCriticalExtensions>
  <SecretKey>
    <Value ref="private.secret.jwt-public-key"/>
  </SecretKey>
  <PublicKey>
    <Value ref="flowVariable.public-key"/>
  </PublicKey>
  <AdditionalClaims>
    <Claim name="scope" ref="jwt.scope" type="string"/>
    <Claim name="sub"   ref="jwt.sub"   type="string"/>
    <Claim name="act"   ref="jwt.act"   type="JSON"/>
  </AdditionalClaims>
</VerifyJWT>
```

Apigee verifica la firma RSA del JWT contra la clave pública del issuer
(Keycloak), valida `iss`, `aud`, `exp`, y opcionalmente `nbf`. **Lo que
NO valida Apigee por defecto**: scopes ni roles. Eso lo hace Spring.

#### OAuthV2 policy (opcional)

Para token introspection (cuando no quieres validar JWT localmente sino
preguntar al IdP):

```xml
<OAuthV2 name="OAuth-Introspect">
  <DisplayName>OAuth V2 VerifyToken</DisplayName>
  <Operation>VerifyAccessToken</Operation>
  <AccessToken ref="request.header.Authorization"/>
</OAuthV2>
```

Útil cuando el token es **opaco** (no JWT). En nuestro caso siempre es
JWT, así que VerifyJWT es más rápido (sin round-trip al IdP).

### 6.3. Mapping scope → authority en Spring Security

El `SecurityConfig.java` de nuestro PoC hace:

```java
@Bean
public JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(new ScopeAuthoritiesConverter());
    return converter;
}

static class ScopeAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        List<String> scopes = new ArrayList<>();
        Object scope = jwt.getClaim("scope");
        if (scope instanceof String s && !s.isBlank()) {
            scopes.addAll(Arrays.asList(s.split("\\s+")));
        }
        Object scp = jwt.getClaim("scp");
        if (scp instanceof Collection<?> coll) {
            for (Object o : coll) {
                if (o != null) scopes.add(o.toString());
            }
        }
        return scopes.stream()
                .filter(s -> !s.isBlank())
                .distinct()
                .map(s -> (GrantedAuthority) new SimpleGrantedAuthority("SCOPE_" + s))
                .collect(Collectors.toList());
    }
}
```

Esto mapea cada scope del JWT a una `GrantedAuthority` con prefijo
`SCOPE_`. Por ejemplo, `scope=email.send` en el JWT se convierte en
`SCOPE_email.send`. Después, en el controller:

```java
@PostMapping("/api/email/send")
@PreAuthorize("hasAuthority('SCOPE_email.send')")
public ResponseEntity<?> send(@RequestBody EmailRequest req, Authentication auth) {
    String sub = auth.getName(); // viene del claim 'sub' del JWT
    Jwt jwt = (Jwt) auth.getPrincipal();
    Map<String, Object> act = jwt.getClaim("act"); // claim 'act' del JWT
    log.info("[AUDIT] sub={} act={} endpoint=/api/email/send", sub, act);
    // ...
}
```

**Notas importantes**:

1. El `principal.name` por defecto es el claim `sub`. Esto es lo que
   queremos: el `sub` del JWT es Ana, no el agente.
2. Para extraer `act`, hay que usar `jwt.getClaim("act")`. Spring no lo
   mapea automáticamente a `GrantedAuthority`; lo extraes del JWT crudo.
3. Si quisiéramos añadir roles además de scopes, el converter debería
   mirar también `realm_access.roles` (Keycloak) o `roles` (otro IdP).

### 6.4. Diferencia entre JWT validation en Apigee y Spring

| Aspecto | Apigee | Spring |
|---|---|---|
| Qué valida | Firma, iss, aud, exp, nbf | Firma, iss, aud, exp + scopes/roles |
| Qué hace con claims | Los expone como flow variables | Los convierte en `Authentication` object |
| Quién decide scopes | Spring (vía `@PreAuthorize`) | Spring |
| Qué hace si falla | 401 + corta el flujo | 403 + renderiza el body |
| Latencia añadida | ~1-2 ms (crypto local) | ~1-2 ms (crypto local) |
| Cuándo bypasear | Solo en testing/debug | Nunca en producción |

**Defensa en profundidad**: ambos deben estar bien configurados. Si un
atacante bypasea Apigee (acceso directo a la API desde la red interna),
Spring sigue validando.

---

## 7. Notas sobre quirks de Keycloak 24/26

> **Nota**: las siguientes son quirks encontrados durante la implementación
> del PoC. Algunas están resueltas en Keycloak 26+; otras requieren workarounds
> específicos.

### 7.1. Bug del sub-endpoint `default-client-scopes`

**Síntoma**: tras crear un cliente por la Admin Console, los scopes no se
agregan automáticamente. El endpoint `PUT
/admin/realms/{realm}/clients/{client-uuid}/default-client-scopes/{scope-id}`
devuelve 404 o no surte efecto.

**Causa**: bug en Keycloak 24.0 con el sub-endpoint de scopes. Resuelto en
24.0.2+. En 26.x es estable.

**Workaround** (Keycloak 24.0.0-24.0.1):

- Usar el endpoint legacy `POST /admin/realms/{realm}/clients/{client-uuid}/scope-mappings/default/client/{id}`.
- O hacerlo desde la Admin Console a mano (no vía API).
- O exportar/importar el realm completo con los scopes pre-configurados en
  el JSON.

**Referencia**: [KEYCLOAK-18732](https://issues.redhat.com/browse/KEYCLOAK-18732).

### 7.2. Atributos dotted vs camelCase

**Síntoma**: al leer atributos de usuario (p.ej. `user.attributes.ciba_consent`)
desde el JWT o la API de Keycloak, la sintaxis depende del contexto.

**Detalle**:

- En **API REST de Keycloak**: atributos son JSON dotted:
  `user.attributes["my.attribute"]`.
- En **JWT claim mapping**: depende del *protocol mapper*. Si el mapper
  tiene nombre `my.attribute`, el claim se llama `my.attribute` (con punto
  en el JSON). Si el mapper está en camelCase, el claim va en camelCase.
- En **Spring resource server**: `jwt.getClaim("my.attribute")` requiere
  comillas en código Java, lo cual es feo pero funciona.

**Recomendación**:

- Usar **siempre** un protocolo mapper con nombre sin puntos y en
  camelCase: `userConsent` en lugar de `user.consent`.
- Si necesitas preservar el dotted, haz un mapper que traduzca a camelCase.

### 7.3. JWT Bearer grant no habilitado por defecto en KC 24

**Síntoma**: intentar `POST /token` con
`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer` devuelve
`unsupported_grant_type`.

**Causa**: en Keycloak 24, el JWT Bearer grant está detrás del feature
flag `token-exchange` o del realm capability `Allow JWT bearer`. No está
habilitado por defecto por seguridad.

**Workaround**:

1. **Habilitar feature**: arrancar Keycloak con
   `--features=token-exchange` o `--features=preview`.
2. **Habilitar realm capability**: en Admin Console →
   `Realm settings → Client policies → Allow JWT bearer = ON`.
3. **Verificar**: tras reiniciar, el grant debería funcionar. Si no, hay
   que revisar logs (`/opt/keycloak/data/log/keycloak.log`).

**En Keycloak 26**: viene habilitado por defecto y GA.

### 7.4. CIBA necesita POST /ext/ciba/auth con cifrado específico

**Síntoma**: el endpoint estándar de CIBA (`POST /bc-authorize`, OIDC CIBA
§7.1) no existe en Keycloak 24. El endpoint que funciona es
`POST /realms/{realm}/protocol/openid-connect/ext/ciba/auth`.

**Detalle**:

- En Keycloak 24, CIBA es **preview feature**. El endpoint está en
  `/ext/` (extension) y la ruta exacta no es la estándar.
- En Keycloak 26, se estabiliza como `/protocol/openid-connect/ext/ciba/auth`
  (sigue siendo `/ext/` por compatibilidad con implementaciones existentes).

**Configuración del realm** (realm attributes):

```json
{
  "cibaBackchannelTokenDeliveryMode": "poll",
  "cibaAuthRequestedUserHint": "login_hint_token",
  "cibaExpiresIn": "120",
  "cibaInterval": "5",
  "cibaCodeLifespan": "60"
}
```

**Cifrado de tokens CIBA**:

- `login_hint_token` debe ser un JWT firmado con la clave del cliente
  (perfil `client_secret_jwt` o `private_key_jwt`).
- `bind_token` vincula la request CIBA con la sesión del cliente CIBA.
  En nuestro PoC coinciden. En producción el `bind_token` lo emite el
  dispositivo del usuario tras un handshake OOB separado.

**Referencias**:

- Keycloak docs: *Server Administration Guide → Client Initiated Backchannel
  Authentication (CIBA)*.
- [KEYCLOAK-15070](https://issues.redhat.com/browse/KEYCLOAK-15070) — CIBA
  feature implementation.

### 7.5. Otros quirks menores

| Quirk | Workaround |
|---|---|
| `act` claim no se emite por defecto en ROPC | Crear *protocol mapper* custom que añada `act={sub:agente-ia}` al JWT. |
| Token introspection endpoint devuelve JSON inconsistente | Usar `VerifyJWT` en Apigee en lugar de `OAuthV2/Introspect`. |
| Refresh tokens de ROPC son muy largos | Configurar `accessTokenLifespan=300` (5 min) en realm. |
| CIBA no soporta `client_credentials_jwt` en 24 | Usar `client_secret_basic` o `client_secret_post` para autenticación del cliente. |
| Spring Security no entiende `cnf.jkt` por defecto | Custom `Converter<Jwt, AbstractAuthenticationToken>` para DPoP. |

### 7.6. Diferencias clave KC 24 vs KC 26

| Feature | KC 24 | KC 26 |
|---|---|---|
| JWT Bearer (RFC 7523) | Preview, detrás de flag | GA, habilitado por defecto |
| Token Exchange (RFC 8693) | Experimental, behind flag | GA, estable |
| CIBA | Preview, `/ext/ciba/auth` | GA, mismo path (compat) |
| DPoP (RFC 9445) | No soportado | Soporte parcial (preview) |
| FAPI 2.0 profile | No certificado | Detrás de feature flag enterprise |
| User attribute dotted | Soportado pero con bugs | Estable |

**Recomendación**: **migrar a KC 26** lo antes posible. La fecha de EOL
de KC 24 es junio 2026 (o más tardar diciembre 2026 según la LTS
extensión).

---

## 8. Bibliografía y RFCs citados

> Todos los RFCs son los drafts finales aprobados a fecha de julio 2026.
> Los OIDC son las implementaciones 1.0 estables.

### 8.1. RFCs IETF (numerados, finalizados)

| RFC | Título | Aplicación en este estudio |
|---|---|---|
| **RFC 6749** | The OAuth 2.0 Authorization Framework | Base. §4.1 (Auth Code), §4.3 (ROPC), §4.4 (Client Creds). |
| **RFC 6750** | The OAuth 2.0 Authorization Framework: Bearer Token Usage | Bearer tokens en HTTP (header `Authorization: Bearer`). |
| **RFC 6819** | OAuth 2.0 Threat Model and Security Considerations | Modelo de amenaza base. |
| **RFC 7009** | OAuth 2.0 Token Revocation | Cómo revocar tokens. |
| **RFC 7521** | Assertion Framework for OAuth 2.0 Client Authentication and Authorization Grants | Marco general para *assertions* (no específico a JWT). |
| **RFC 7523** | JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants | El grant `urn:ietf:params:oauth:grant-type:jwt-bearer`. §2.1 (client auth), §3 (authz grant). |
| **RFC 7636** | Proof Key for Code Exchange (PKCE) | El sufijo `S256`. |
| **RFC 7662** | OAuth 2.0 Token Introspection | Cómo preguntar al AS por el estado de un token. |
| **RFC 8176** | Authentication Method Reference Values | Los valores de `acr_values` (MFA step-up). |
| **RFC 8252** | OAuth 2.0 for Native Apps | BCP para apps móviles. §8 (browser selection). |
| **RFC 8414** | OAuth 2.0 Authorization Server Metadata | El endpoint `/.well-known/oauth-authorization-server`. |
| **RFC 8693** | OAuth 2.0 Token Exchange | El grant `urn:ietf:params:oauth:grant-type:token-exchange`. §2.2.1 (claim `act`). |
| **RFC 8705** | OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens | mTLS para OAuth. |
| **RFC 9068** | JWT Profile for OAuth 2.0 Access Tokens | Cómo debe ser el JWT de un access_token. |
| **RFC 9100** | JWT Profile for OAuth 2.0 Client Authentication | `private_key_jwt` y `client_secret_jwt`. |
| **RFC 9207** | OAuth 2.0 Authorization Server Issuer Identification | El parámetro `issuer` en respuestas de error. |
| **RFC 9396** | Rich Authorization Requests | RAR para escenarios complejos (pagos con detalles). |
| **RFC 9445** | DPoP: Demonstrating Proof-of-Possession at the Application Layer | Sender-constrained tokens. |
| **RFC 9470** | OAuth 2.0 for Browser-Based Apps | BCP para apps SPA. |

### 8.2. OpenID Connect specifications

| Spec | Título | Aplicación |
|---|---|---|
| **OIDC Core 1.0** | OpenID Connect Core 1.0 | `id_token`, `userinfo`, scopes estándar. §9 client auth. |
| **OIDC CIBA 1.0** | Client Initiated Backchannel Authentication | §7.1 `bc-authorize`, §8 token endpoint. |
| **OIDC for Identity Assurance 1.0** | OIDC Identity Assurance | Claims verificados de identidad. |
| **FAPI 2.0 Security Profile** | Financial-grade API Security Profile | El más seguro, sender-constrained obligatorio. |
| **FAPI 2.0 Message Signing** | FAPI Message Signing | Firma de mensajes HTTP. |

### 8.3. Internet-Drafts activos (a fecha 2026-Q2)

| Draft | Estado | Aplicación |
|---|---|---|
| `draft-ietf-oauth-v2-1` | Working draft | OAuth 2.1 consolida BCPs: elimina ROPC e Implicit. |
| `draft-ietf-oauth-security-topics` | Working draft | Refresh token rotation, sender constrained. |
| `draft-ietf-httpbis-message-signatures` | RFC 9421 (2023) | Firma de mensajes HTTP. |

### 8.4. NIST y regulación

| Documento | Aplicación |
|---|---|
| **NIST SP 800-63B** | AAL2/AAL3 — referenciado por `acr_values` en CIBA. |
| **PSD2** (EU Directive 2015/2366) | Pagos en Europa: exige FAPI-like o equivalente (Berlin Group, STET, etc.). |
| **UK OBIE / FCA** | Open Banking en UK: exige FAPI 1.0 Advanced. |
| **CDR (Australia)** | Consumer Data Right: exige FAPI 1.0. |
| **eIDAS 2.0** | Identidad digital europea: referencia para OIDC Identity Assurance. |

### 8.5. Documentación oficial de proveedores (referenciada)

- **Keycloak 24 docs**: https://www.keycloak.org/docs/24.0/
- **Keycloak 26 docs**: https://www.keycloak.org/docs/latest/
- **Apigee docs**: https://cloud.google.com/apigee/docs
- **Spring Security 6.x reference**: https://docs.spring.io/spring-security/reference/
- **Auth0 docs**: https://auth0.com/docs
- **Okta Developer**: https://developer.okta.com
- **Microsoft identity platform**: https://learn.microsoft.com/en-us/entra/identity-platform/

### 8.6. Blogs y artículos citados

- *OAuth 2.0 Token Exchange: the on-behalf-of pattern* (Okta Developer Blog, 2023).
- *Understanding CIBA* (Vittorio Bertocci, Auth0 Blog, 2022).
- *DPoP: why sender-constrained tokens matter* (Vittorio Bertocci, 2023).
- *FAPI 2.0: what changed since FAPI 1.0* (OpenID Foundation blog, 2023).
- *JWT Bearer Grant in Keycloak* (Keycloak community, 2024).
- *Spring Security + Keycloak integration patterns* (Baeldung, 2024).

---

## Apéndice A — Glosario y siglas

| Sigla | Significado |
|---|---|
| **AAL** | Authenticator Assurance Level (NIST SP 800-63B). |
| **AS** | Authorization Server (IdP en OAuth). |
| **BCP** | Best Current Practice (RFCs con recomendaciones). |
| **CIBA** | Client Initiated Backchannel Authentication (OIDC). |
| **CDR** | Consumer Data Right (Australia, regulación). |
| **DPoP** | Demonstrating Proof-of-Possession (RFC 9445). |
| **EOL** | End Of Life (fin de soporte). |
| **FAPI** | Financial-grade API (OpenID Foundation). |
| **HSM** | Hardware Security Module. |
| **IdP** | Identity Provider (servidor que autentica usuarios). |
| **JAR** | JWT Secured Authorization Request (RFC 9101). |
| **JWE** | JSON Web Encryption (RFC 7516). |
| **JWK** | JSON Web Key (RFC 7517). |
| **JWKS** | JSON Web Key Set (endpoint para publicar claves públicas). |
| **JWS** | JSON Web Signature (RFC 7515). |
| **JWT** | JSON Web Token (RFC 7519). |
| **KMS** | Key Management Service (cloud-managed HSMs). |
| **LLM** | Large Language Model. |
| **MFA** | Multi-Factor Authentication. |
| **mTLS** | mutual TLS (RFC 8705). |
| **NIST** | National Institute of Standards and Technology. |
| **OBO** | On-Behalf-Of (Microsoft identity platform). |
| **OIDC** | OpenID Connect. |
| **PoC** | Proof of Concept. |
| **PKCE** | Proof Key for Code Exchange (RFC 7636). |
| **PKI** | Public Key Infrastructure. |
| **PSD2** | Payment Services Directive 2 (EU). |
| **RAR** | Rich Authorization Requests (RFC 9396). |
| **ROPC** | Resource Owner Password Credentials (RFC 6749 §4.3). |
| **RS** | Resource Server (API que recibe access_tokens). |
| **SPIFFE** | Secure Production Identity Framework For Everyone (CNCF). |
| **SPIRE** | SPIFFE Runtime Environment. |
| **SSO** | Single Sign-On. |
| **W3C VC** | W3C Verifiable Credentials. |

---

## Apéndice B — Historial de revisiones

| Versión | Fecha | Cambios |
|---|---|---|
| 0.1 | 2026-07-01 | Borrador inicial con A, B, D. |
| 0.5 | 2026-07-05 | Añadidos C, E, F, G. Tabla comparativa. |
| 1.0 | 2026-07-08 | Versión final con scoring corregido, recomendaciones por horizonte, bibliografía completa. |

---

**Última actualización**: 2026-07-08
**Mantenedor**: Víctor Hdez (khum1982) + Hermes (subagente)
**Licencia**: MIT — documento interno, puedes copiar y adaptar.
**Contacto**: ver `agent-oauth-poc/README.md`.