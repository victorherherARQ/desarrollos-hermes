# Apigee-stub — Spring Boot Resource Server

Stub de **Apigee** implementado como API REST mínima con Spring Boot 3.2.

Su única responsabilidad en este PoC es **validar JWT** emitidos por
Keycloak (realm `agent-poc`) y exigir los *scopes* correctos en cada
endpoint. Reemplaza a Apigee real para no necesitar su plano de OAuth.

---

## Endpoints

| Método | Ruta                  | Auth          | Scope            | Descripción                                |
|--------|-----------------------|---------------|------------------|--------------------------------------------|
| GET    | `/health`             | público       | —                | Liveness básico                            |
| GET    | `/actuator/health`    | público       | —                | Health de Spring Boot Actuator             |
| GET    | `/api/calendar/events?user_id=ana` | JWT | `calendar.read`  | Devuelve eventos mock del calendario       |
| POST   | `/api/email/send`     | JWT           | `email.send`     | Simula envío de email (con `act` y `sub`)  |

Los *scopes* se extraen de los claims estándar del access token JWT:
`scope` (string space-separated, RFC 6749) o `scp` (array). Se mapean a
`SCOPE_<x>` mediante un `JwtAuthenticationConverter` propio.

> Para usar `hasAuthority('SCOPE_xxx')` se requiere la anotación
> `@EnableMethodSecurity` activa, habilitada por defecto en Spring
> Security 6 / Spring Boot 3.

---

## Estructura

```
spring-boot-api/
├── pom.xml
├── README.md
└── src/main/
    ├── java/com/poc/api/
    │   ├── ApiApplication.java
    │   ├── config/SecurityConfig.java
    │   └── controller/
    │       ├── HealthController.java
    │       ├── CalendarController.java
    │       └── EmailController.java
    └── resources/application.yml
```

---

## Cómo ejecutar

### 1) Requisitos

- Java 17 (`java -version`)
- Maven 3.9+ (`mvn -version`)
- Keycloak accesible en `http://keycloak:8080/realms/agent-poc`
  (configurado en `application.yml`).

### 2) Arranque local (standalone)

```bash
# desde la raíz de spring-boot-api/
mvn clean spring-boot:run
```

La API queda escuchando en `http://localhost:9090`.

> Si arrancas **fuera de Docker**, el `issuer-uri` apuntará a
> `http://keycloak:8080/...`, que solo resuelve dentro de la red
> `agent-poc-net`. Para pruebas en host, exporta:
>
> ```bash
> export SPRING_SECURITY_OAUTH2_RESOURCESERVER_JWT_ISSUER_URI=\
>   http://localhost:8080/realms/agent-poc
> mvn spring-boot:run
> ```
>
> o sobrescribe la propiedad en `application.yml` con tu IP/host.

### 3) Arranque vía Docker Compose (recomendado en la PoC)

```bash
# desde agent-oauth-poc/
docker compose up -d keycloak spring-boot-api
docker compose logs -f spring-boot-api
```

El `issuer-uri` interno (`http://keycloak:8080/realms/agent-poc`) está
resuelto por la red `agent-poc-net`.

---

## Probarlo a mano

```bash
# 1) Token (CIBA o client_credentials) desde Keycloak
TOKEN="eyJhbGciOi..."   # bearer real

# 2) Calendar
curl -sS http://localhost:9090/api/calendar/events?user_id=ana \
     -H "Authorization: Bearer $TOKEN" | jq

# 3) Email
curl -sS -X POST http://localhost:9090/api/email/send \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"to":"ana@acme.io","subject":"Hola","body":"prueba"}' | jq
```

Errores esperados:

| Código | Significado                                       |
|--------|---------------------------------------------------|
| 401    | Falta `Authorization` o el token está caducado    |
| 403    | Token válido pero sin el scope requerido          |

---

## Notas para la PoC

- Este servicio **NO** emite tokens. Solo los valida.
- La cadena de delegación usuario → agente se observa en el controller
  de email: claim `sub` = usuario real, claim `act` = agente que actúa.
- Para producción se sustituiría por Apigee (o Kong + plugin `jwt`)
  con la misma pareja issuer/scopes.
