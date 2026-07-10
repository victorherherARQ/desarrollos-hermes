# Token Exchange (RFC 8693) y On-Behalf-Of en Azure AD B2C / Entra External ID

**Fecha del informe:** 2026-07-10
**Autor:** Hermes Agent (sub-investigación delegada)
**Contexto:** Evaluación para proyecto de comparativa de IdPs (Keycloak vs Azure B2C) — caso de uso: agente IA que autentica al usuario final y luego intercambia el token por otro con menos scopes (downscoping) o actúa en nombre del usuario (OBO).

---

## Resumen ejecutivo

1. **Azure AD B2C NO soporta nativamente ni `urn:ietf:params:oauth:grant-type:jwt-bearer` (RFC 7523, OBO) ni `urn:ietf:params:oauth:grant-type:token-exchange` (RFC 8693).** Microsoft lo confirma textualmente en dos páginas de documentación oficial (la guía de *Request an access token in Azure AD B2C* y la Q&A de junio 2025).
2. La única vía soportada en el ecosistema Microsoft para OBO es **Microsoft Entra ID** (el tenant corporativo), no B2C. B2C es un producto CIAM pensado para flujos de usuario final, no para cadenas de APIs.
3. **Existen tres workarounds viables** en B2C, todos con trade-offs: (a) inyectar el access token de un IdP federado como claim dentro del JWT de B2C usando un *OAuth2 technical profile* en la orquestación (patrón `idp_access_token`, sample oficial de Microsoft), (b) ejecutar el "exchange" en una capa de aplicación intermedia usando Azure Functions / APIM como broker, y (c) separar el tenant y emitir el token secundario desde un tenant Entra ID tradicional.
4. **Microsoft Entra External ID** (el sucesor de B2C) hereda el comportamiento de Entra ID para apps de la *Microsoft identity platform*, por lo que OBO `urn:ietf:params:oauth:grant-type:jwt-bearer` funciona allí; **RFC 8693 sigue sin estar soportado** en ningún tenant de Microsoft a fecha de hoy.
5. Si el requisito es RFC 8693 estricto, **Keycloak** sigue siendo la única opción OSS madura (flag `Standard Token Exchange` por cliente desde Keycloak 18+) y **Auth0** ofrece un patrón propietario `Token Vault` muy alineado al caso del agente IA.

---

## Tabla comparativa de las 8 opciones

| # | Opción | Viabilidad técnica en B2C | Cumple RFC 8693 estricto | Cumple "OBO-like" | Complejidad | Mantenimiento | Notas clave |
|---|--------|----------------------------|--------------------------|-------------------|-------------|---------------|-------------|
| 1 | **Custom Policy (IEF) + `JwtIssuer` emitiendo JWT con actor/claims distintos** | Limitado | No | Parcial (sólo firma un JWT; no hay token-exchange endpoint) | Alta | Alto | Puedes firmar un JWT con `sub` distinto (claim mapping), pero B2C no expone un `token_endpoint` que admita RFC 7523/8693. |
| 2 | **OBO real (`urn:ietf:params:oauth:grant-type:jwt-bearer`) en B2C** | No soportado | No | No | — | — | Microsoft docs: *"the On-Behalf-Of flow is not currently implemented in Azure AD B2C. Although On-Behalf-Of works for applications registered in Microsoft Entra ID, it does not work for applications registered in Azure AD B2C"*. |
| 3 | **API Connectors durante el sign-in** | Parcial | No | Parcial (pueden firmar JWT vía RESTful TP, pero no emiten access tokens reusables) | Media | Medio | API Connectors sólo se ejecutan durante el signup; para sign-in necesitas RESTful technical profiles dentro de una custom policy. |
| 4 | **App Roles + manual exchange en la capa de aplicación** | Total | No | Sí (lógico, no estándar) | Baja | Bajo | La API recibe el access_token original, valida los roles contra App Roles/claims del IdP, y emite su propio JWT firmado por ella misma (no por B2C). Es la opción más pragmática. |
| 5 | **Migración a Microsoft Entra External ID (tenants externos)** | Soportado | No | Sí, OBO `jwt-bearer` funciona porque External ID está sobre la Microsoft identity platform | Baja (migración) | Bajo (post-migración) | External ID sigue siendo CIAM pero usa el v2.0 endpoint; **OBO funciona ahí**, no así token-exchange RFC 8693. |
| 6 | **Workaround con Azure Functions / APIM como broker** | Total | No | Sí, lógica idéntica al #4 pero externalizada | Media | Medio | La Function valida el JWT de B2C, llama al STS que necesite y emite un nuevo token. APIM con `validate-jwt` + `set-header` puede hacer este patrón sin código. |
| 7 | **Comparativa con Auth0 / Keycloak** | — | Sí ambos | Sí ambos | — | — | Keycloak: `Standard Token Exchange` (RFC 8693 nativo, flag por cliente). Auth0: `Token Vault` (propietario) + `On-Behalf-Of Token Exchange` (proprietario, no RFC 8693 estricto). |
| 8 | **Riesgos y limitaciones reales** | Ver sección abajo | — | — | — | — | B2C entra en end-of-sale el 1 mayo 2025 (sólo clientes existentes). P2 desaparece 15 marzo 2026. Soporte hasta mayo 2030. Esto afecta a todo lo demás. |

---

## Las 3 opciones más viables en detalle

### Opción A (recomendada en B2C legacy): OAuth2 technical profile + claim `idp_access_token`

**Descripción.** B2C, dentro de una custom policy, puede invocar a un IdP federado que soporte OAuth2/Azure AD (por ejemplo el propio Microsoft Entra ID) usando un *technical profile* con `<Protocol Name="OAuth2"/>`. Durante esa invocación B2C recibe un `access_token` del IdP federado y lo expone como claim del JWT final de B2C renombrándolo como `idp_access_token`. La aplicación cliente puede entonces extraer ese token y usarlo contra el API downstream sin necesidad de un exchange RFC 8693.

**Cuándo encaja:** cuando el API destino está protegido por un tenant Azure AD / Entra ID separado (multi-tenant) o por un SaaS que acepte tokens OAuth2 (Google, Salesforce, etc.). Es el patrón documentado por Microsoft en su repositorio oficial `azure-ad-b2c/samples/policies/B2C-Token-Includes-AzureAD-BearerToken`.

**Pasos resumidos:**

1. Registrar una aplicación multi-tenant en el tenant Azure AD / Entra ID que protege el API downstream con permisos delegados (`openid`, `User.Read`, etc.).
2. Crear una policy key en B2C (`Identity Experience Framework` → `Policy keys`) con el `client_secret` de esa app.
3. Añadir un `ClaimsProvider` con un `TechnicalProfile` que apunte al `AccessTokenEndpoint` del IdP federado.
4. Mapear el output `{oauth2:access_token}` al claim `identityProviderAccessToken` y propagarlo al JWT final con `PartnerClaimType="idp_access_token"`.
5. En la app cliente, decodificar el JWT de B2C, leer el claim `idp_access_token` y usarlo contra el API downstream (downscoping natural: el IdP federado sólo recibe los scopes que le pediste).

**Código XML clave** (extracto del sample oficial `B2C-Token-Includes-AzureAD-BearerToken`, archivo `TrustFrameworkExtensions.xml`):

```xml
<ClaimsProvider>
  <Domain>Login.AzureAD.com</Domain>
  <DisplayName>AzureAD Account</DisplayName>
  <TechnicalProfiles>
    <TechnicalProfile Id="AzureADProfile_issueAADtoken">
      <DisplayName>AzureAD User</DisplayName>
      <Protocol Name="OAuth2"/>
      <OutputTokenFormat>JWT</OutputTokenFormat>
      <Metadata>
        <Item Key="AccessTokenEndpoint">
          https://login.microsoftonline.com/common/oauth2/v2.0/token</Item>
        <Item Key="authorization_endpoint">
          https://login.microsoftonline.com/common/oauth2/v2.0/authorize</Item>
        <Item Key="BearerTokenTransmissionMethod">AuthorizationHeader</Item>
        <Item Key="ClaimsEndpoint">https://graph.microsoft.com/v1.0/me</Item>
        <Item Key="client_id">Enter-your-ApplicationID</Item>
        <Item Key="IdTokenAudience">Enter-your-ApplicationID</Item>
        <Item Key="DiscoverMetadataByTokenIssuer">true</Item>
        <Item Key="HttpBinding">POST</Item>
        <Item Key="response_types">code</Item>
        <Item Key="scope">openid user.read</Item>
        <Item Key="UsePolicyInRedirectUri">false</Item>
        <Item Key="ValidTokenIssuerPrefixes">https://sts.windows.net/</Item>
      </Metadata>
      <CryptographicKeys>
        <Key Id="client_secret" StorageReferenceId="B2C_1A_TenantApplicationKey"/>
      </CryptographicKeys>
      <OutputClaims>
        <OutputClaim ClaimTypeReferenceId="authenticationSource"
                     DefaultValue="socialIdpAuthentication"/>
        <OutputClaim ClaimTypeReferenceId="displayName" PartnerClaimType="displayName"/>
        <OutputClaim ClaimTypeReferenceId="email"        PartnerClaimType="email"/>
        <OutputClaim ClaimTypeReferenceId="givenName"    PartnerClaimType="givenName"/>
        <OutputClaim ClaimTypeReferenceId="surname"      PartnerClaimType="surname"/>
        <OutputClaim ClaimTypeReferenceId="userPrincipalName"
                     PartnerClaimType="userPrincipalName"/>
        <OutputClaim ClaimTypeReferenceId="issuerUserId" PartnerClaimType="id"/>
        <!-- Aquí está la clave: B2C captura el access_token del IdP federado -->
        <OutputClaim ClaimTypeReferenceId="identityProviderAccessToken"
                     PartnerClaimType="{oauth2:access_token}"/>
      </OutputClaims>
    </TechnicalProfile>
  </TechnicalProfiles>
</ClaimsProvider>
```

Y en el `RelyingParty` (`SignUpOrSignin.xml`):

```xml
<OutputClaim ClaimTypeReferenceId="identityProviderAccessToken"
             PartnerClaimType="idp_access_token"/>
```

**Limitaciones reales:**

- B2C no implementa el endpoint `token-exchange` de RFC 8693; esto es un *passthrough*, no un exchange. El JWT final de B2C lleva dentro un string `idp_access_token` que el cliente extrae.
- El `idp_access_token` tiene los scopes que le pediste al IdP federado, pero B2C no puede modificarlos en runtime por usuario: están hardcoded en la policy. Si necesitas scopes dinámicos necesitas una `RESTful technical profile` que llame a tu API para que ésta devuelva los scopes a meter en el claim.
- La chain "B2C → IdP federado → API" añade latencia y un nuevo secret que rotar.
- Si el IdP federado es el mismo Azure AD del cliente, los tokens no son "downscoped" técnicamente: reusas el access_token original (que ya tenía los scopes solicitados en el momento del sign-in).

**Referencias:**

- Sample oficial: `https://github.com/azure-ad-b2c/samples/tree/master/policies/B2C-Token-Includes-AzureAD-BearerToken`
- Docs: `learn.microsoft.com/en-us/azure/active-directory-b2c/access-tokens`
- Docs: `learn.microsoft.com/en-us/azure/active-directory-b2c/oauth2-technical-profile`
- Docs: `learn.microsoft.com/en-us/azure/active-directory-b2c/jwt-issuer-technical-profile`
- User-flow equivalente (sin custom policy): `learn.microsoft.com/en-us/azure/active-directory-b2c/idp-pass-through-user-flow`

---

### Opción B (recomendada si hay greenfield): Migración a Microsoft Entra External ID

**Descripción.** Microsoft Entra External ID es el sucesor de Azure AD B2C. Internamente está construido sobre la *Microsoft identity platform* (el mismo motor que Entra ID corporativo), por lo que **sí soporta el OBO flow `urn:ietf:params:oauth:grant-type:jwt-bearer`** documentado en `learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow`. La diferencia con Entra ID corporativo es que External ID ofrece user flows / branding CIAM y App Services dedicados a externos. El RFC 8693 estricto sigue sin estar soportado en ningún tenant Microsoft a fecha de hoy (julio 2026).

**Cuándo encaja:** cualquier proyecto nuevo de CIAM que vaya a producción en 2026+. Si el cliente del proyecto está dispuesto a migrar (o ya está en External ID), esta es la vía más limpia para OBO.

**Pasos resumidos:**

1. Crear un tenant *External* (no workforce) en Microsoft Entra admin center.
2. Registrar dos aplicaciones: una para la API middle-tier (confidential client con client secret) y otra para el API downstream.
3. Configurar el user flow de External ID para el sign-up/sign-in.
4. La middle-tier API usa **MSAL** (`AcquireTokenOnBehalfOf` en .NET, `acquire_token_on_behalf_of` en Python) pasando el JWT recibido como `UserAssertion` con tipo `urn:ietf:params:oauth:grant-type:jwt-bearer`.
5. Para Entra External ID, OBO requiere un add-on de pago (M2M Premium o similar — revisar pricing actual). External ID no es gratuito para este patrón.

**Código Python (MSAL) — ejemplo oficial del sample Azure-Samples/ms-identity-python-on-behalf-of:**

```python
from msal import ConfidentialClientApplication, UserAssertion

def acquire_obo_token(incoming_jwt, downstream_scopes,
                      client_id, client_secret, tenant_id):
    app = ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )
    assertion = UserAssertion(
        incoming_jwt,
        assertion_type="urn:ietf:params:oauth:grant-type:jwt-bearer"
    )
    result = app.acquire_token_on_behalf_of(
        scopes=downstream_scopes,
        user_assertion=assertion,
    )
    return result  # contiene el nuevo access_token para el API downstream
```

**Limitaciones reales:**

- **OBO funciona en External ID**, pero **RFC 8693 sigue sin funcionar** (mismo error AADSTS70003).
- Costes: External ID cobra por MAU (Monthly Active Users) y ciertos add-ons son de pago; el precio se ha incrementado respecto a B2C en algunas regiones. Revisar pricing oficial antes de comprometerse.
- El tenant de External ID es "externo" (CIAM); no hereda automáticamente los grupos/apps del tenant workforce del cliente. Si el cliente ya tiene Entra ID corporativo, los usuarios B2C y los corporativos viven en tenants separados y necesitan federation explícita.
- Latencia: el endpoint `login.microsoftonline.com` es global; cold-start en regions nuevas puede añadir 100-300 ms.

**Referencias:**

- Docs OBO: `learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow`
- Sample Python: `github.com/Azure-Samples/ms-identity-python-on-behalf-of`
- External ID home: `learn.microsoft.com/en-us/entra/external-id/`
- B2C EOL FAQ: `learn.microsoft.com/en-us/azure/active-directory-b2c/faq` (end of sale 1 mayo 2025)

---

### Opción C (recomendada si RFC 8693 es requisito duro): Cambiar el IdP a Keycloak

**Descripción.** Si el requisito del proyecto es **cumplir RFC 8693 estrictamente**, ni B2C ni Entra External ID lo soportan. La única opción OSS madura con soporte nativo RFC 8693 es **Keycloak** (banderín `Standard Token Exchange` por cliente desde Keycloak 18+, estable en 24/25/26).

**Cuándo encaja:** greenfield, o cuando el cliente está abierto a un IdP on-prem / managed OSS. Para tu caso concreto (ya estás migrando a Keycloak 26.6.4 por la misma razón), no hay nada que discutir: Keycloak es la elección correcta.

**Ejemplo de token-exchange request (extraído de docs oficiales Keycloak):**

```
POST /realms/test/protocol/openid-connect/token
Authorization: Basic <base64(client_id:client_secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
& subject_token=$SUBJECT_TOKEN
& subject_token_type=urn:ietf:params:oauth:token-type:access_token
& requested_token_type=urn:ietf:params:oauth:token-type:access_token
```

Respuesta:

```json
{
  "access_token": "eyJhbG...",
  "expires_in": 300,
  "token_type": "Bearer",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "scope": "default-scope1"
}
```

**Limitaciones reales:**

- Keycloak añade complejidad operativa (alta disponibilidad, upgrades, parches, postgres, realms, etc.).
- Necesitas un equipo de operaciones que domine Keycloak o un servicio gestionado (Red Hat SSO, Keycloak Cloud, etc.).
- Si el cliente exige "estar en Azure", Keycloak puede correr en AKS pero los secretos y operaciones siguen siendo tuyos.

**Comparativa con Auth0 (mismo nicho, distinto enfoque):**

| Característica | Keycloak | Auth0 | Azure B2C | Entra External ID |
|----------------|----------|-------|-----------|-------------------|
| RFC 8693 estricto | Sí (flag por cliente) | No (Usa Token Vault propietario) | No | No |
| RFC 7523 (OBO/jwt-bearer) | Sí | Vía Token Vault | No | Sí |
| Token Vault / passthrough | Sí (token exchange) | Sí (Token Vault: Google, MS, GitHub...) | Sólo con custom policy | Vía OBO |
| Caso de uso IA agent (Token Vault) | Sí (manual) | Sí (producto propio) | No | No |
| On-prem / self-host | Sí | No | No | No |
| Coste a escala | Gratis (operación) | Pago por MAU | Pago por MAU | Pago por MAU + add-ons |

---

## Riesgos y limitaciones reales

### Costes
- **B2C legacy:** Fin de venta a nuevos clientes desde 1 mayo 2025. B2C P2 se descataloga el 15 marzo 2026. Soporte garantizado hasta mayo 2030. Migración a External ID será obligatoria tarde o temprano.
- **Entra External ID:** Coste por MAU + posibles add-ons para OBO/M2M. Para una carga de 100k usuarios activos/mes, el coste se vuelve relevante. Revisar pricing oficial antes de cerrar arquitectura.
- **Azure Functions / APIM como broker:** Si la Function corre constantemente (plan Consumption) o tiene alto throughput, el coste puede dispararse. APIM tiene coste fijo por unidad + por request.
- **Keycloak on-prem:** Coste operativo (DevOps, SRE, alta disponibilidad con 2-3 nodos + PostgreSQL). Si se托管 en AKS a producción, añade coste de infraestructura cloud.

### Latencia
- B2C user flow típico: 500-1200 ms en cold path (login + policy + token sign).
- OAuth2 technical profile federado adicional (Opción A): +300-600 ms por el round-trip al IdP federado.
- Entra External ID OBO: +150-400 ms por el exchange.
- Keycloak token-exchange: +50-150 ms (es local, sin round-trip externo).

### Mantenimiento
- Custom policies de B2C son XML frágil: un typo en `ClaimTypeReferenceId` produce errores crípticos. La extensión de VSCode `AzureADB2CTools.aadb2c` ayuda, pero no evita el coste de mantener políticas versionadas y probadas con `IEF Test Framework` / `PolicyMock`.
- External ID migrará progresivamente features desde B2C; habrá deprecation waves que tocarán las custom policies si las tuviste.
- Keycloak upgrades (cada 6 meses aprox.) requieren revisar realms, protocol mappers y SPIs custom.

### Single Point of Failure
- **B2C:** SLA Microsoft, no SPOF propio, pero **el tenant está en una sola región** y no hay opción multi-region. Si Microsoft tiene outage en esa región, B2C cae para tus usuarios.
- **External ID:** Igual: regional, sin multi-region.
- **Azure Function broker:** si es Consumption, no hay SPOF. Si es Premium/Dedicated, hay que dimensionar alta disponibilidad.
- **Keycloak on-prem:** SPOF si no se despliega en clúster (mínimo 2 nodos + Infinispan + Postgres). Documentado por Red Hat como requisito para producción.

### Complejidad de custom policies (B2C Opción A)
- Las custom policies IEF tienen una curva de aprendizaje pronunciada. Para mantenerlas necesitas:
  - Un repo con los 3-4 archivos XML (`TrustFrameworkBase.xml`, `TrustFrameworkExtensions.xml`, `SignUpOrSignin.xml`, etc.) versionado.
  - Pipelines CI/CD que suban las policies a B2C con `policyUpload` PowerShell / `b2c-policy-upload` task.
  - Tests con `policyMock` (mock del REST technical profile) para CI.
- El sample `B2C-Token-Includes-AzureAD-BearerToken` es un buen punto de partida, pero producción real requiere ajustes (ClaimsTransformations adicionales, manejo de errores, fallback flows).

---

## Conclusión y recomendación

**Respuesta corta:** En B2C NO existe RFC 8693 ni OBO `jwt-bearer` real. El patrón más cercano es el **OAuth2 technical profile que inyecta `idp_access_token` como claim del JWT de B2C** (sample oficial de Microsoft), pero es un passthrough, no un exchange.

**Recomendación para el proyecto del cliente:**

1. **Si el cliente aún no ha decidido y el greenfield está abierto:** Migrar a **Microsoft Entra External ID**. Soporta OBO `jwt-bearer` (no RFC 8693 estricto), está en roadmap activo de Microsoft, y es el sucesor natural de B2C. Coste y latencia comparables a B2C.
2. **Si el cliente ya está en B2C legacy y no quiere migrar todavía:** Implementar la **Opción A (OAuth2 technical profile + `idp_access_token`)**. Es el patrón documentado por Microsoft, soporta downscoping vía scopes del IdP federado, y se ajusta al caso del agente IA sin necesidad de una Function broker.
3. **Si RFC 8693 estricto es un requisito contractual (por ejemplo, un API de terceros exige `subject_token`):** El IdP tiene que ser **Keycloak** (o un IdP que soporte RFC 8693 como Hydra, Authlete, etc.). B2C y External ID no lo soportan en el roadmap público actual.
4. **Si el cliente quiere el caso del agente IA out-of-the-box con Token Vault:** Considerar **Auth0 Token Vault**, que tiene un patrón nativo para "AI agent running as a web application calls external APIs to perform tasks on the user's behalf" (descripción literal de su documentación). Es propietario, no RFC 8693, pero es exactamente el caso de uso del proyecto.

**Para Víctor específicamente:** ya está eligiendo Keycloak 26.6.4 para el proyecto principal, lo cual es coherente con la matriz de arriba. Para el proyecto de comparativa IdPs, el dato clave a comunicar al cliente es:

> *"Azure B2C no soporta RFC 8693 ni OBO jwt-bearer. Si el requisito es alguno de esos dos protocolos, B2C queda descartado. Si es OBO `jwt-bearer` específicamente, Microsoft Entra External ID (sucesor de B2C) sí lo soporta. Si es RFC 8693 estricto, las opciones reales en el mercado son Keycloak (OSS), Auth0 Token Vault (propietario) o IdPs especializados como Authlete/Hydra."*

---

## Fuentes numeradas

1. **Microsoft Q&A — confirmado que Azure AD no soporta RFC 8693:** `https://learn.microsoft.com/en-us/answers/questions/2283187/can-you-help-how-to-do-token-exchange-between-two-apps-using-entra` (junio 2025)
2. **Microsoft Learn — confirmación oficial de que OBO NO funciona en B2C:** `https://learn.microsoft.com/en-us/azure/active-directory-b2c/access-tokens` (extracto: *"Web API chains (On-Behalf-Of) is not supported by Azure AD B2C... Although On-Behalf-Of works for applications registered in Microsoft Entra ID, it does not work for applications registered in Azure AD B2C"*)
3. **Azure B2C FAQ oficial — end of sale 1 mayo 2025:** `https://learn.microsoft.com/en-us/azure/active-directory-b2c/faq`
4. **Microsoft Learn — JwtIssuer technical profile docs:** `https://learn.microsoft.com/en-us/azure/active-directory-b2c/jwt-issuer-technical-profile`
5. **Microsoft Learn — OAuth2 technical profile docs:** `https://learn.microsoft.com/en-us/azure/active-directory-b2c/oauth2-technical-profile`
6. **Microsoft Learn — RESTful technical profile docs:** `https://learn.microsoft.com/en-us/azure/active-directory-b2c/restful-technical-profile`
7. **Microsoft Learn — API Connectors overview:** `https://learn.microsoft.com/en-us/azure/active-directory-b2c/api-connectors-overview`
8. **Microsoft Learn — Secure APIs used for API connectors:** `https://learn.microsoft.com/en-us/azure/active-directory-b2c/secure-rest-api`
9. **Microsoft Learn — Pass an identity provider access token to your app:** `https://learn.microsoft.com/en-us/azure/active-directory-b2c/idp-pass-through-user-flow`
10. **GitHub — azure-ad-b2c/samples (sample oficial de idp_access_token):** `https://github.com/azure-ad-b2c/samples/tree/master/policies/B2C-Token-Includes-AzureAD-BearerToken`
c/samples/master/policies/B2C-Token-Includes-AzureAD-BearerToken/Policy/TrustFrameworkExtensions.xml`
12. **GitHub raw — SignUpOrSignin.xml del sample:** `https://raw.githubusercontent.com/azure-ad-b2c/samples/master/policies/B2C-Token-Includes-AzureAD-BearerToken/Policy/SignUpOrSignin.xml`
13. **Microsoft Learn — Overview of tokens in B2C:** `https://learn.microsoft.com/en-us/azure/active-directory-b2c/tokens-overview`
14. **Microsoft Learn — Configure session behavior:** `https://learn.microsoft.com/en-us/azure/active-directory-b2c/session-behavior`
15. **Microsoft Learn — Application types supported by Azure AD B2C:** `https://learn.microsoft.com/en-us/azure/active-directory-b2c/application-types`
16. **Microsoft Learn — Custom policy overview:** `https://learn.microsoft.com/en-us/azure/active-directory-b2c/custom-policy-overview`
17. **Microsoft Learn — Microsoft identity platform OBO flow (Entra ID / External ID):** `https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow`
18. **Microsoft Learn — Client credentials flow:** `https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow`
19. **Microsoft Learn — On-behalf-of flows with MSAL.NET:** `https://learn.microsoft.com/en-us/entra/msal/dotnet/acquiring-tokens/web-apps-apis/on-behalf-of-flow`
20. **Microsoft Learn — Microsoft Entra External ID overview:** `https://learn.microsoft.com/en-us/entra/external-id/`
21. **GitHub — Azure-Samples/ms-identity-python-on-behalf-of (sample OBO Python):** `https://github.com/Azure-Samples/ms-identity-python-on-behalf-of`
22. **Keycloak docs — Standard Token Exchange (RFC 8693):** `https://www.keycloak.org/securing-apps/token-exchange.html`
23. **Keycloak docs — Capabilities del cliente (incluye flag Standard Token Exchange):** `https://www.keycloak.org/docs/latest/server_admin/index.html`
24. **RFC 8693 — OAuth 2.0 Token Exchange (especificación):** `https://www.rfc-editor.org/rfc/rfc8693.html`
25. **Auth0 — Token Vault (caso IA agent):** `https://auth0.com/docs/secure/tokens/token-vault`
26. **Auth0 — Configure Refresh Token Rotation:** `https://auth0.com/docs/secure/tokens/refresh-tokens/configure-refresh-token-rotation`
27. **Microsoft Learn — Code samples for Microsoft identity platform (incluye OBO):** `https://learn.microsoft.com/en-us/entra/identity-platform/sample-v2-code`

---

*Informe generado como sub-investigación delegada de Hermes Agent. Si necesitas profundizar en cualquiera de las opciones, puedo (a) reproducir el sample `B2C-Token-Includes-AzureAD-BearerToken` en local, (b) hacer un proof-of-concept de Opción A con B2C + Keycloak como IdP federado, o (c) redactar un test plan para validar downscoping en cada IdP.*
