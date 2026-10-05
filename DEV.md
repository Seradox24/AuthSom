# Entorno de desarrollo

Instancia Keycloak local para pruebas de integración, sin TLS y con proyecto
Docker propio (`authsom-dev`), de modo que puede convivir con la instalación de
producción (`authsom`) sin compartir base de datos, volumen ni puertos.

## Arranque

1. Copiar `.env.dev.example` a `.env` y cambiar los valores `cambiame-*`.
2. Validar con `docker compose -f compose.yaml -f compose.dev.yaml config --quiet`.
3. Ejecutar `docker compose -f compose.yaml -f compose.dev.yaml up -d --wait --wait-timeout 300`.

| Recurso | URL |
| --- | --- |
| Administración | `http://localhost:8081/admin/` |
| Discovery OIDC | `http://localhost:8081/realms/educacion/.well-known/openid-configuration` |
| Issuer | `http://localhost:8081/realms/educacion` |

Los secretos viven solo en `.env`, que no se versiona.

## Usuario de prueba

El realm no importa usuarios. Crear uno con:

```bash
docker compose -f compose.yaml -f compose.dev.yaml exec keycloak bash -ec '
  /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 --realm master \
    --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD" &&
  /opt/keycloak/bin/kcadm.sh create users -r educacion \
    -s username=devuser -s enabled=true -s email=devuser@example.com -s emailVerified=true &&
  /opt/keycloak/bin/kcadm.sh set-password -r educacion --username devuser --new-password "CAMBIA_ESTA_CLAVE"
'
```

## Apuntar otros servicios al SSO dev

| Servicio | Configuración |
| --- | --- |
| Web Login (SPA, navegador) | Issuer `http://localhost:8081/realms/educacion`, client `web-login` |
| Flutter escritorio | Issuer `http://localhost:8081/realms/educacion`, client `flutter-desktop` |
| `lrs_bridge` (contenedor) | `OIDC_ISSUER=http://localhost:8081/realms/educacion` y `OIDC_JWKS_URL=http://host.docker.internal:8081/realms/educacion/protocol/openid-connect/certs` |
| Moodle (contenedor) | Issuer `http://localhost:8081/realms/educacion`, client `moodle` y el secreto `MOODLE_OIDC_CLIENT_SECRET`; añadir `extra_hosts: ["localhost:host-gateway"]` al servicio para que el contenedor alcance Keycloak |

Cambios de redirect URI o clientes: hacerlos en la administración o por API. La
importación del realm solo se aplica en el primer arranque; para reimportar el
JSON desde cero, `docker compose -f compose.yaml -f compose.dev.yaml down --volumes`.

Ajustes del puerto o de la URL (por ejemplo, para probar desde otro equipo):
editar `KEYCLOAK_HOSTNAME`, `KEYCLOAK_BIND_ADDRESS` y `KEYCLOAK_HTTP_PORT` en
`.env` y volver a levantar. El issuer cambia con `KEYCLOAK_HOSTNAME`.

## Diferencias con producción

- `start-dev` con HTTP, proyecto `authsom-dev` y puerto 8081.
- Sin proxy TLS ni cabeceras de reenvío reales.
- Datos y realm desechables; no migrar este volumen a producción.
- Para producción usar `main` y las instrucciones de `README.md`.
