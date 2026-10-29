# Consideraciones de instalación y ejecución

Notas operativas para levantar AuthSom (Keycloak) e integrarlo con otros
servicios. Recoge los problemas encontrados durante las pruebas de integración
locales y cómo evitarlos.

## 1. Arranque del servicio

- Producción: `compose.yaml` + `.env` (TLS y proxy a cargo del entorno).
- Desarrollo: `compose.yaml` + `compose.dev.yaml` + `.env` (proyecto
  `authsom-dev`, puerto 8081, sin TLS). Ver `DEV.md`.
- Usar siempre proyectos Compose y volúmenes distintos entre dev y producción;
  `down --volumes` borra la base y el realm se reimporta solo en un volumen nuevo.
- La importación del realm aplica una única vez (primer arranque). Los cambios
  posteriores en `keycloak/educacion-realm.json` no modifican una instalación
  existente: se aplican por consola/API o reimportando con volumen limpio.
- `.env` contiene secretos y no se versiona. Protegerlo con permisos restrictivos.

## 2. Registro de clientes en Keycloak

Reglas generales al crear o ajustar un cliente OIDC:

- **Redirect URI exacta**: debe coincidir carácter por carácter con la que usa
  el servicio (incluida la barra final). Ejemplo Moodle: `<wwwroot>/auth/oidc/`.
- **Post logout redirect URIs**: necesarias para el cierre de sesión
  (Moodle envía `post_logout_redirect_uri=<wwwroot>`). Para Moodle:
  `<wwwroot>` y `<wwwroot>/*`.
- **Front-channel logout URL**: endpoint del servicio que Keycloak llama al
  cerrar sesión. Para Moodle: `<wwwroot>/auth/oidc/logout.php`.
- Cliente confidencial con secreto para servicios con backend (Moodle);
  públicos con PKCE S256 para apps de navegador/escritorio.
- El secreto del cliente debe coincidir exactamente con el configurado en el
  servicio.

## 3. Endpoints: navegador vs. contenedor (crítico)

El flujo OIDC usa URLs distintas según quién realiza la petición:

| Uso | Quién la consume | Valor correcto |
| --- | --- | --- |
| Authorization endpoint | Navegador (redirección) | URL que resuelve el navegador (`http://localhost:8081`, o el host público) |
| Logout endpoint | Navegador (redirección) | Igual que el anterior |
| Token endpoint | Servidor del servicio (backchannel) | URL alcanzable **desde dentro del contenedor** |

- Servicios en contenedor **no pueden usar `localhost`** para el token endpoint:
  dentro del contenedor `localhost` es el propio contenedor.
- En Docker Desktop (Windows/macOS): usar `http://host.docker.internal:<puerto>`.
- En Linux con contenedor en red puente: añadir
  `extra_hosts: ["host.docker.internal:host-gateway"]` y usar ese nombre para
  el token endpoint, o utilizar una red Docker compartida con Keycloak.
  No redefinir `localhost`: debe seguir apuntando al propio contenedor.
- En producción, si Keycloak se publica con URL/DNS resoluble desde los
  contenedores, esa misma URL sirve para todos los endpoints.
- Síntoma típico de un token endpoint inalcanzable: Keycloak autentica bien
  pero el servicio muestra un error genérico al volver (en Moodle: "Error en
  OpenID Connect"), sin eventos de error en Keycloak.

## 4. Integración con Moodle (`auth_oidc`)

Configuración probada (Administración del sitio → Plugins → Autenticación):

| Ajuste | Valor |
| --- | --- |
| IdP Type | Other |
| Application/Client ID | `moodle` |
| Método de autenticación | Client secret (el de `MOODLE_OIDC_CLIENT_SECRET`) |
| Authorization endpoint | `http(s)://<host-keycloak>/realms/educacion/protocol/openid-connect/auth` |
| Token endpoint | URL alcanzable desde el contenedor de Moodle (ver sección 3) |
| OIDC resource | **vacío** |
| OIDC scope | `openid profile email` |
| Binding username claim | `preferred_username` (no dejar `auto`: cae a `sub`, un UUID) |
| Field mapping | Nombre → `givenName`, Apellido → `surname`, Email → `mail` |
| Single sign out | Sí; logout endpoint = `.../protocol/openid-connect/logout` |
| Silent Login Mode | Desaconsejado: el `prompt=none` añade errores tras logout; el SSO funciona igual sin él |
| Show friendly error page | Recomendado |

Notas:

- **OIDC resource**: mantener vacío con esta configuración. Las bitácoras
  locales registraron `Invalid resource: moodle` e `Invalid resource:` en
  intentos anteriores. El plugin instalado añade por defecto
  `resource=https://graph.microsoft.com` aunque el ajuste esté vacío; la
  petición actual con `scope=openid profile email` devuelve la página de login
  correctamente. No confundir ese parámetro heredado con el scope ni usar
  `moodle` como scope. No fue necesario modificar el código del plugin.
- **Field mapping**: los scopes de Keycloak proporcionan `given_name`,
  `family_name` y `email`. El código instalado de `auth_oidc` los transforma
  internamente en `givenName`, `surname` y `mail`; por eso los valores de la
  tabla son correctos. Completar nombre, apellido y correo del usuario en
  Keycloak para que Moodle pueda construir su perfil.
- **Force redirect** salta el login de Moodle hacia Keycloak. Se puede
  esquivar con `http://<wwwroot>/login/index.php?noredirect=1`, útil para la
  cuenta admin local de emergencia.
- **"Unknown state" o "Estado desconocido"**: el callback trae un `state` que
  no existe en la sesión (intentos solapados, pestañas viejas, expiración).
  No es un problema de credenciales; se evita sin abrir varios flujos en
  paralelo. Con la página amigable activada redirige al login.
- El plugin no verifica la firma del `id_token` contra JWKS (confía en el TLS
  del token endpoint). En producción exigir HTTPS extremo a extremo.
- Sin `local_o365` no hay Single Logout por backchannel: el cierre es
  RP-initiated + front-channel.
- Roles: un rol de Keycloak no otorga administración en Moodle; el
  administrador del sitio se asigna en Moodle tras el primer login SSO.

## 5. Otros clientes

- Aplicaciones de navegador (`web-login`, Flutter): el `issuer` configurado
  debe ser la URL que resuelve el navegador; registrar sus redirect URIs.
- Servicios que validan tokens Bearer (p. ej. `lrs_bridge`): separar
  `OIDC_ISSUER` (valor del `iss` del token, tal como lo ve el navegador) de
  `OIDC_JWKS_URL` (URL alcanzable desde el contenedor).

## 6. Verificación rápida

```bash
curl --fail http://<host-keycloak>/realms/educacion/.well-known/openid-configuration
```

- El `issuer` del discovery debe coincidir con el configurado en los servicios.
- Ante errores de login: revisar primero los eventos de Keycloak
  (`Invalid redirect_uri`, `Invalid resource`, `login_required`) y luego la
  bitácora del servicio.

## 7. Producción

- Mismas reglas con URLs HTTPS públicas y siempre alcanzables desde los
  contenedores (no `localhost` en backchannel).
- Sincronizar `keycloak/educacion-realm.json` con los cambios de clientes
  probados en dev; en instalaciones ya existentes se aplican por API/consola.
- No reutilizar el volumen del entorno de desarrollo.

## 8. Corrección aplicada al bloqueo HTTP de Moodle (2026-10-05)

Entorno revisado: Keycloak 26.7.5, Moodle local con `auth_oidc` versión
`2026042001`, Docker Desktop en Windows. Ambos contenedores estaban sanos.
El error actual no era falta de conectividad: el curl del sistema llegaba a
Keycloak, pero el cliente HTTP de Moodle respondía `Esta URL está bloqueada.`
Esto provocaba `erroroidccall` al intentar interpretar la respuesta como JSON.

Endpoints efectivos:

| Ajuste | Valor local verificado |
| --- | --- |
| Moodle wwwroot | `http://localhost:18080` |
| Authorization | `http://localhost:8081/realms/educacion/protocol/openid-connect/auth` |
| Token (desde Moodle) | `http://host.docker.internal:8081/realms/educacion/protocol/openid-connect/token` |
| Logout | `http://localhost:8081/realms/educacion/protocol/openid-connect/logout` |
| Callback auth_oidc | `http://localhost:18080/auth/oidc/` |

El cliente `moodle` existente admite ese callback y también
`http://localhost:18080/admin/oauth2callback.php`. El JSON de importación del
repositorio solo declara el segundo: en una instalación nueva de `auth_oidc`
hay que añadir el primero, por consola/API o al preparar el JSON. Son rutas
para integraciones distintas y no se deben intercambiar.

### Aplicar la excepción en una instalación local

1. Entrar con el administrador local de Moodle en
   `http://localhost:18080/login/index.php?noredirect=1`.
2. Ir a Administración del sitio → Seguridad → Seguridad HTTP. Guardar una
   copia de **Hosts bloqueados por cURL** (`curlsecurityblockedhosts`) y
   **Puertos permitidos por cURL** (`curlsecurityallowedport`).
3. Consultar la IP desde el contenedor:

   ```powershell
   docker exec lms-moodle-dev-app-1 getent hosts host.docker.internal
   ```

4. Añadir `8081` a los puertos permitidos, conservando `80` y `443`.
5. La IP verificada fue `192.168.65.254`. Para permitir exclusivamente esa IP,
   sustituir **solo** `192.168.0.0/16` en los hosts bloqueados por los siguientes
   rangos, conservando las demás entradas:

   ```text
   192.168.128.0/17
   192.168.0.0/18
   192.168.96.0/19
   192.168.80.0/20
   192.168.72.0/21
   192.168.68.0/22
   192.168.66.0/23
   192.168.64.0/24
   192.168.65.0/25
   192.168.65.128/26
   192.168.65.192/27
   192.168.65.224/28
   192.168.65.240/29
   192.168.65.248/30
   192.168.65.252/31
   192.168.65.255/32
   ```

Esta lista cubre el /16 completo salvo `192.168.65.254`. No copiarla si Docker
resuelve otra IP: recalcular los rangos para esa IP. No vaciar los hosts
bloqueados ni quitar el /16 completo. Moodle no ofrece una excepción por ruta
en estos ajustes: la IP queda accesible para las solicitudes cURL de Moodle
en los puertos permitidos, y `8081` queda permitido para los hosts no bloqueados.

Los cambios se guardaron en la base de Moodle; persisten al recrear sus
contenedores, pero deben reaplicarse si se crea una base nueva. El respaldo
anterior está en el volumen de datos, dentro del contenedor:
`/var/moodledata/oidc-curl-backup-20261005.json`. Para revertir, restaurar sus
dos valores desde Seguridad HTTP. No es un archivo del repositorio Windows.

### Validación y límites

- La prueba con el cliente HTTP real de `auth_oidc`, el secreto configurado y
  un código deliberadamente inválido pasó de `Esta URL está bloqueada.` a JSON
  de Keycloak: `invalid_grant` / `Code not valid`. Esto comprueba que la
  petición llega al endpoint; no sustituye un intercambio con código válido.
- La petición de autorización actual devuelve HTTP 200 y la pantalla de login.
- Falta confirmar un login completo con usuario real, la creación/sincronización
  del perfil y el logout. No marcar estas pruebas como realizadas.
- El cliente revisado tiene `frontchannelLogout=false` y no tiene atributos de
  post logout configurados. Los ajustes de la sección 2 son pasos de
  configuración pendientes de validar, no el estado comprobado del cliente.
- Si vuelve a fallar, comprobar primero la IP de Docker, ambos ajustes cURL,
  el secreto, el callback exacto y las bitácoras. Un curl del sistema exitoso
  no demuestra que el cliente HTTP de Moodle permita la URL.

## 9. Logo oficial de Moodle en Keycloak

Se creó el tema `moodle`, heredado de `keycloak.v2`, con estos archivos:

- `keycloak/themes/moodle/login/theme.properties`: herencia y hojas de estilo.
- `keycloak/themes/moodle/login/resources/css/moodle.css`: coloca el logo en
  `#kc-header-wrapper`, reemplazando visualmente el encabezado del realm.
- `keycloak/themes/moodle/login/resources/img/moodle-logo.svg`: SVG obtenido
  de https://moodle.com/wp-content/uploads/2022/02/logo.svg y servido localmente.

`compose.dev.yaml` monta el tema en modo lectura:

```yaml
services:
  keycloak:
    volumes:
      - ./keycloak/themes/moodle:/opt/keycloak/themes/moodle:ro
```

Desde `D:\Servidor\sso\AuthSom`, validar y recrear el servicio:

```powershell
docker compose -f compose.yaml -f compose.dev.yaml config --quiet
docker compose -f compose.yaml -f compose.dev.yaml up -d --no-deps keycloak
```

Después, seleccionar el realm **educacion** → Realm settings → Themes →
Login theme → **moodle** → Save. Esta selección ya se aplicó al realm existente
y persiste en PostgreSQL. En una base nueva hay que volver a seleccionarla;
el JSON de importación no declara `loginTheme`.

Se verificaron HTTP 200 de la página de autorización, de `css/moodle.css` y
del SVG (`Content-Type: image/svg+xml`). Para ver el cambio, iniciar un flujo
nuevo desde Moodle; un enlace antiguo puede contener un `state` expirado.

El montaje se añadió únicamente al Compose de desarrollo. Para implementar
el tema en producción, incluir el mismo montaje en su configuración o empaquetar
el tema en la imagen, y seleccionar `moodle` en ese realm. Conservar HTTPS y
las restricciones HTTP apropiadas para esa red; la excepción de Docker Desktop
no es una configuración de producción.

Referencia sobre herencia, recursos y selección de temas:
https://www.keycloak.org/ui-customization/themes
